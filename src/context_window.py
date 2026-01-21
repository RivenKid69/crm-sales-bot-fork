"""
Context Window — расширенный контекст для классификатора

Уровень 1: Sliding Window
- Хранит последние N ходов диалога с полной информацией
- Предоставляет историю интентов и actions
- Вычисляет паттерны поведения (повторы, тренды)

Уровень 2: Structured Context
- Классификация типов ходов (progress, regress, lateral, stuck)
- Анализ связей между ходами (триггеры возражений/согласий)
- Engagement Score (вовлечённость клиента)
- Funnel Progress Analysis (скорость по воронке)
- Momentum (инерция диалога)

Уровень 3: Episodic Memory
- Хранит ключевые эпизоды ВСЕГО диалога (не удаляются при ротации окна)
- Первое/последнее возражение, переломные моменты
- Собранный профиль клиента (данные, боли)
- Успешные и неуспешные actions за весь диалог
- Темы которые триггерят позитив/негатив

Исследования показали:
- Окно 3-5 ходов оптимально (arXiv 2024)
- Полная история создаёт шум и ухудшает классификацию на 20%+
- Последний ход пользователя — самый важный контекст
- Но ключевые эпизоды (первое возражение) важны независимо от давности
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any, Tuple, TYPE_CHECKING
from collections import Counter
from enum import Enum
import time

# CRITICAL FIX: Import intent categories from single source of truth (constants.yaml)
# This ensures ContextWindow uses the complete, up-to-date list of intents
from src.yaml_config.constants import (
    OBJECTION_INTENTS,
    POSITIVE_INTENTS,
    QUESTION_INTENTS,
)

if TYPE_CHECKING:
    from src.config_loader import LoadedConfig


class TurnType(Enum):
    """Тип хода по влиянию на воронку."""
    PROGRESS = "progress"      # Движение вперёд по воронке
    REGRESS = "regress"        # Откат назад (возражение, отказ)
    LATERAL = "lateral"        # Движение в сторону (вопрос, уточнение)
    STUCK = "stuck"            # Застревание (unclear, повтор)
    NEUTRAL = "neutral"        # Нейтральный (приветствие, благодарность)


class EngagementLevel(Enum):
    """Уровень вовлечённости клиента."""
    HIGH = "high"              # Активно участвует, даёт данные
    MEDIUM = "medium"          # Отвечает, но кратко
    LOW = "low"                # Минимальные ответы
    DISENGAGED = "disengaged"  # Потерял интерес


# Порядок SPIN фаз для расчёта прогресса (DEFAULT - используется как fallback)
DEFAULT_PHASE_ORDER = {
    "greeting": 0,
    "situation": 1,
    "problem": 2,
    "implication": 3,
    "need_payoff": 4,
    "presentation": 5,
    "close": 6,
    "success": 7,
}
# Backward compatibility alias
SPIN_PHASE_ORDER = DEFAULT_PHASE_ORDER

# Порядок состояний для расчёта прогресса (DEFAULT - используется как fallback)
DEFAULT_STATE_ORDER = {
    "greeting": 0,
    "spin_situation": 1,
    "spin_problem": 2,
    "spin_implication": 3,
    "spin_need_payoff": 4,
    "presentation": 5,
    "handle_objection": 5,  # Параллельно с presentation
    "close": 6,
    "success": 7,
    "soft_close": -1,  # Негативный прогресс
}
# Backward compatibility alias
STATE_ORDER = DEFAULT_STATE_ORDER

# Progress intents that indicate forward movement (DEFAULT - используется как fallback)
DEFAULT_PROGRESS_INTENTS = {
    "agreement", "demo_request", "callback_request", "contact_provided",
    "situation_provided", "problem_revealed", "implication_acknowledged",
    "need_expressed", "info_provided"
}


@dataclass
class TurnContext:
    """Контекст одного хода диалога."""

    # Сообщения
    user_message: str
    bot_response: Optional[str] = None

    # Классификация
    intent: str = "unknown"
    confidence: float = 0.0
    method: str = "unknown"  # root, lemma, data, context, etc.

    # State Machine
    action: str = "unknown"
    state: str = "greeting"
    next_state: str = "greeting"

    # Дополнительно
    extracted_data: Dict = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    # Флаги
    is_disambiguation: bool = False
    is_fallback: bool = False
    fallback_tier: Optional[str] = None

    # =========================================================================
    # УРОВЕНЬ 2: Структурированные данные хода
    # =========================================================================

    # Тип хода (вычисляется автоматически)
    turn_type: Optional[TurnType] = None

    # Прогресс по воронке (разница между state и next_state)
    funnel_delta: int = 0

    # Метрики сообщения
    message_length: int = 0  # Длина сообщения клиента
    word_count: int = 0      # Количество слов
    has_data: bool = False   # Предоставил ли клиент данные

    # Config-driven mappings (use DEFAULT_* if None)
    state_order: Optional[Dict[str, int]] = field(default=None, repr=False)
    progress_intents: Optional[set] = field(default=None, repr=False)

    def __post_init__(self):
        """Автоматически вычисляем производные поля."""
        # Длина и слова
        self.message_length = len(self.user_message)
        self.word_count = len(self.user_message.split())
        self.has_data = bool(self.extracted_data)

        # Прогресс по воронке (use config or default)
        # IMPORTANT: Use None for unknown states to avoid false delta calculations
        order = self.state_order if self.state_order is not None else DEFAULT_STATE_ORDER
        state_pos = order.get(self.state)  # None if unknown
        next_state_pos = order.get(self.next_state)  # None if unknown

        # If either state is unknown, funnel_delta = 0 (neutral/unknown transition)
        if state_pos is None or next_state_pos is None:
            self.funnel_delta = 0
        else:
            self.funnel_delta = next_state_pos - state_pos

        # Тип хода (если не задан явно)
        if self.turn_type is None:
            self.turn_type = self._compute_turn_type()

    def _compute_turn_type(self) -> TurnType:
        """Вычислить тип хода на основе intent и funnel_delta.

        ВАЖНО: Intent-based classification имеет ПРИОРИТЕТ над delta-based,
        т.к. intent лучше отражает семантику хода (возражение - всегда регресс,
        даже если state machine перешла в handle_objection).
        """
        # 1. РЕГРЕСС (возражения, отказы) - ПРИОРИТЕТ над delta
        if self.intent in {
            "objection_price", "objection_competitor", "objection_no_time",
            "objection_think", "objection_timing", "objection_complexity",
            "objection_no_need", "objection_trust", "rejection", "farewell"
        }:
            return TurnType.REGRESS

        # 2. Lateral (вопросы, уточнения)
        if self.intent in {
            "question_features", "question_integrations", "price_question",
            "pricing_details", "comparison", "consultation_request"
        }:
            return TurnType.LATERAL

        # 3. Застревание
        if self.intent in {"unclear", "needs_clarification"}:
            return TurnType.STUCK

        # 4. Нейтральный (приветствие, благодарность)
        if self.intent in {"greeting", "gratitude"}:
            return TurnType.NEUTRAL

        # 5. Прогресс по intent (agreement, demo_request и т.д.)
        progress = (
            self.progress_intents
            if self.progress_intents is not None
            else DEFAULT_PROGRESS_INTENTS
        )
        if self.intent in progress:
            return TurnType.PROGRESS

        # 6. Прогресс по delta
        if self.funnel_delta > 0:
            return TurnType.PROGRESS

        # 7. Регресс или нейтральный по delta
        if self.funnel_delta < 0:
            return TurnType.REGRESS

        # 8. По умолчанию — нейтральный (funnel_delta == 0)
        return TurnType.NEUTRAL


# =============================================================================
# УРОВЕНЬ 3: Episodic Memory
# =============================================================================

class EpisodeType(Enum):
    """Тип эпизода для долгосрочной памяти."""
    FIRST_OBJECTION = "first_objection"       # Первое возражение
    BREAKTHROUGH = "breakthrough"              # Прорыв (переход от негатива к позитиву)
    DATA_REVEALED = "data_revealed"           # Клиент раскрыл данные
    PAIN_POINT = "pain_point"                 # Выявленная боль
    TURNING_POINT = "turning_point"           # Переломный момент (смена тренда)
    REPEATED_OBJECTION = "repeated_objection" # Повторное возражение того же типа
    SUCCESSFUL_CLOSE = "successful_close"     # Успешное согласие на CTA


@dataclass
class Episode:
    """Один эпизод для долгосрочной памяти."""
    episode_type: EpisodeType
    turn_number: int                          # Номер хода (с начала диалога)
    intent: str                               # Интент в момент эпизода
    action_before: Optional[str] = None       # Action который привёл к эпизоду
    data: Dict = field(default_factory=dict)  # Дополнительные данные
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict:
        """Сериализация в словарь."""
        return {
            "type": self.episode_type.value,
            "turn": self.turn_number,
            "intent": self.intent,
            "action_before": self.action_before,
            "data": self.data,
        }


@dataclass
class ClientProfile:
    """Профиль клиента собранный за диалог."""
    # Базовые данные
    company_name: Optional[str] = None
    company_size: Optional[int] = None
    industry: Optional[str] = None
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None

    # Выявленные боли
    pain_points: List[str] = field(default_factory=list)

    # Интересы
    interested_features: List[str] = field(default_factory=list)

    # Возражения которые были
    objection_types: List[str] = field(default_factory=list)

    def update_from_data(self, extracted_data: Dict) -> None:
        """Обновить профиль из extracted_data."""
        if not extracted_data:
            return

        # Базовые данные
        if "company_name" in extracted_data:
            self.company_name = extracted_data["company_name"]
        if "company_size" in extracted_data:
            self.company_size = extracted_data["company_size"]
        if "industry" in extracted_data:
            self.industry = extracted_data["industry"]
        if "contact_name" in extracted_data:
            self.contact_name = extracted_data["contact_name"]
        if "phone" in extracted_data:
            self.contact_phone = extracted_data["phone"]
        if "email" in extracted_data:
            self.contact_email = extracted_data["email"]

        # Боли
        if "pain_point" in extracted_data:
            pain = extracted_data["pain_point"]
            if pain and pain not in self.pain_points:
                self.pain_points.append(pain)

        # Интересы
        if "interested_in" in extracted_data:
            feature = extracted_data["interested_in"]
            if feature and feature not in self.interested_features:
                self.interested_features.append(feature)

    def add_objection(self, objection_type: str) -> None:
        """Добавить тип возражения."""
        if objection_type not in self.objection_types:
            self.objection_types.append(objection_type)

    def has_data(self) -> bool:
        """Проверить есть ли собранные данные."""
        return bool(
            self.company_name or self.company_size or
            self.contact_name or self.contact_phone or
            self.pain_points
        )

    def to_dict(self) -> Dict:
        """Сериализация в словарь."""
        return {
            "company_name": self.company_name,
            "company_size": self.company_size,
            "industry": self.industry,
            "contact_name": self.contact_name,
            "contact_phone": self.contact_phone,
            "contact_email": self.contact_email,
            "pain_points": self.pain_points,
            "interested_features": self.interested_features,
            "objection_types": self.objection_types,
        }


class EpisodicMemory:
    """
    Долгосрочная память ключевых эпизодов диалога.

    В отличие от скользящего окна (Level 1-2), эпизоды НЕ удаляются.
    Хранит важные моменты всего диалога для контекста.
    """

    def __init__(self):
        """Инициализация эпизодической памяти."""
        self.episodes: List[Episode] = []
        self.client_profile = ClientProfile()
        self.total_turns = 0

        # Статистика за весь диалог
        self.all_objections: Dict[str, int] = {}  # тип -> количество
        self.all_questions: Dict[str, int] = {}   # тип -> количество
        self.successful_actions: Dict[str, int] = {}  # action -> сколько раз привёл к progress
        self.failed_actions: Dict[str, int] = {}     # action -> сколько раз привёл к regress

        # Флаги состояния
        self._first_objection_recorded = False
        self._breakthrough_recorded = False
        self._last_momentum_direction: Optional[str] = None

    def record_turn(self, turn: 'TurnContext', turn_number: int,
                    prev_turn: Optional['TurnContext'] = None,
                    momentum_direction: Optional[str] = None) -> List[Episode]:
        """
        Записать ход и определить нужно ли создать эпизод.

        Args:
            turn: Текущий ход
            turn_number: Номер хода (с начала диалога)
            prev_turn: Предыдущий ход (для анализа триггеров)
            momentum_direction: Текущий momentum ("positive", "negative", "neutral")

        Returns:
            Список созданных эпизодов
        """
        self.total_turns = turn_number
        new_episodes = []

        action_before = prev_turn.action if prev_turn else None

        # -----------------------------------------------------------------
        # 1. Обновляем профиль клиента
        # -----------------------------------------------------------------
        if turn.extracted_data:
            self.client_profile.update_from_data(turn.extracted_data)
            # Эпизод: клиент раскрыл данные
            if turn.has_data:
                ep = Episode(
                    episode_type=EpisodeType.DATA_REVEALED,
                    turn_number=turn_number,
                    intent=turn.intent,
                    action_before=action_before,
                    data=turn.extracted_data.copy(),
                )
                new_episodes.append(ep)

        # -----------------------------------------------------------------
        # 2. Обрабатываем возражения
        # -----------------------------------------------------------------
        if turn.turn_type == TurnType.REGRESS:
            objection_type = turn.intent

            # Первое возражение
            if not self._first_objection_recorded:
                ep = Episode(
                    episode_type=EpisodeType.FIRST_OBJECTION,
                    turn_number=turn_number,
                    intent=objection_type,
                    action_before=action_before,
                )
                new_episodes.append(ep)
                self._first_objection_recorded = True

            # Повторное возражение того же типа
            elif objection_type in self.all_objections and self.all_objections[objection_type] >= 1:
                ep = Episode(
                    episode_type=EpisodeType.REPEATED_OBJECTION,
                    turn_number=turn_number,
                    intent=objection_type,
                    action_before=action_before,
                    data={"count": self.all_objections[objection_type] + 1},
                )
                new_episodes.append(ep)

            # Обновляем статистику возражений
            self.all_objections[objection_type] = self.all_objections.get(objection_type, 0) + 1
            self.client_profile.add_objection(objection_type)

            # Неэффективный action
            if action_before:
                self.failed_actions[action_before] = self.failed_actions.get(action_before, 0) + 1

        # -----------------------------------------------------------------
        # 3. Обрабатываем прогресс
        # -----------------------------------------------------------------
        if turn.turn_type == TurnType.PROGRESS:
            # Эффективный action
            if action_before:
                self.successful_actions[action_before] = self.successful_actions.get(action_before, 0) + 1

            # Breakthrough: первый прогресс после возражений
            if not self._breakthrough_recorded and self._first_objection_recorded:
                ep = Episode(
                    episode_type=EpisodeType.BREAKTHROUGH,
                    turn_number=turn_number,
                    intent=turn.intent,
                    action_before=action_before,
                )
                new_episodes.append(ep)
                self._breakthrough_recorded = True

        # -----------------------------------------------------------------
        # 4. Обрабатываем вопросы
        # -----------------------------------------------------------------
        if turn.turn_type == TurnType.LATERAL:
            self.all_questions[turn.intent] = self.all_questions.get(turn.intent, 0) + 1

        # -----------------------------------------------------------------
        # 5. Обнаружение переломных моментов
        # -----------------------------------------------------------------
        if momentum_direction and self._last_momentum_direction:
            # Смена с негативного на позитивный
            if self._last_momentum_direction == "negative" and momentum_direction == "positive":
                ep = Episode(
                    episode_type=EpisodeType.TURNING_POINT,
                    turn_number=turn_number,
                    intent=turn.intent,
                    action_before=action_before,
                    data={"from": "negative", "to": "positive"},
                )
                new_episodes.append(ep)

            # Смена с позитивного на негативный
            elif self._last_momentum_direction == "positive" and momentum_direction == "negative":
                ep = Episode(
                    episode_type=EpisodeType.TURNING_POINT,
                    turn_number=turn_number,
                    intent=turn.intent,
                    action_before=action_before,
                    data={"from": "positive", "to": "negative"},
                )
                new_episodes.append(ep)

        self._last_momentum_direction = momentum_direction

        # -----------------------------------------------------------------
        # 6. Сохраняем эпизоды
        # -----------------------------------------------------------------
        self.episodes.extend(new_episodes)

        return new_episodes

    def record_successful_close(self, turn: 'TurnContext', turn_number: int,
                                action_before: Optional[str] = None) -> Episode:
        """Записать успешное закрытие."""
        ep = Episode(
            episode_type=EpisodeType.SUCCESSFUL_CLOSE,
            turn_number=turn_number,
            intent=turn.intent,
            action_before=action_before,
        )
        self.episodes.append(ep)
        return ep

    def reset(self) -> None:
        """Очистить память для нового диалога."""
        self.episodes.clear()
        self.client_profile = ClientProfile()
        self.total_turns = 0
        self.all_objections.clear()
        self.all_questions.clear()
        self.successful_actions.clear()
        self.failed_actions.clear()
        self._first_objection_recorded = False
        self._breakthrough_recorded = False
        self._last_momentum_direction = None

    # -------------------------------------------------------------------------
    # Получение эпизодов
    # -------------------------------------------------------------------------

    def get_first_objection(self) -> Optional[Episode]:
        """Получить первое возражение."""
        for ep in self.episodes:
            if ep.episode_type == EpisodeType.FIRST_OBJECTION:
                return ep
        return None

    def get_breakthrough(self) -> Optional[Episode]:
        """Получить момент прорыва."""
        for ep in self.episodes:
            if ep.episode_type == EpisodeType.BREAKTHROUGH:
                return ep
        return None

    def get_turning_points(self) -> List[Episode]:
        """Получить все переломные моменты."""
        return [ep for ep in self.episodes if ep.episode_type == EpisodeType.TURNING_POINT]

    def get_repeated_objections(self) -> List[Episode]:
        """Получить повторные возражения."""
        return [ep for ep in self.episodes if ep.episode_type == EpisodeType.REPEATED_OBJECTION]

    def get_episodes_by_type(self, episode_type: EpisodeType) -> List[Episode]:
        """Получить эпизоды определённого типа."""
        return [ep for ep in self.episodes if ep.episode_type == episode_type]

    # -------------------------------------------------------------------------
    # Статистика и анализ
    # -------------------------------------------------------------------------

    def get_most_common_objection(self) -> Optional[Tuple[str, int]]:
        """Получить самый частый тип возражения."""
        if not self.all_objections:
            return None
        return max(self.all_objections.items(), key=lambda x: x[1])

    def get_most_effective_action(self) -> Optional[Tuple[str, int]]:
        """Получить самый эффективный action."""
        if not self.successful_actions:
            return None
        return max(self.successful_actions.items(), key=lambda x: x[1])

    def get_least_effective_action(self) -> Optional[Tuple[str, int]]:
        """Получить наименее эффективный action."""
        if not self.failed_actions:
            return None
        return max(self.failed_actions.items(), key=lambda x: x[1])

    def is_objection_repeated(self, objection_type: str) -> bool:
        """Проверить было ли такое возражение раньше."""
        return self.all_objections.get(objection_type, 0) >= 1

    def get_objection_count(self, objection_type: str) -> int:
        """Получить количество возражений определённого типа."""
        return self.all_objections.get(objection_type, 0)

    def get_total_objections(self) -> int:
        """Получить общее количество возражений."""
        return sum(self.all_objections.values())

    def has_breakthrough(self) -> bool:
        """Был ли прорыв в диалоге."""
        return self._breakthrough_recorded

    def get_action_effectiveness(self, action: str) -> float:
        """
        Получить эффективность action (0-1).

        Returns:
            Отношение успехов к общему количеству
        """
        successes = self.successful_actions.get(action, 0)
        failures = self.failed_actions.get(action, 0)
        total = successes + failures
        if total == 0:
            return 0.5  # Нет данных
        return successes / total

    # -------------------------------------------------------------------------
    # Контекст для классификатора
    # -------------------------------------------------------------------------

    def get_episodic_context(self) -> Dict[str, Any]:
        """
        Получить контекст из эпизодической памяти.

        Returns:
            Dict с ключевыми эпизодами и статистикой
        """
        first_objection = self.get_first_objection()
        breakthrough = self.get_breakthrough()
        most_common_obj = self.get_most_common_objection()
        most_effective = self.get_most_effective_action()
        least_effective = self.get_least_effective_action()

        return {
            # Ключевые эпизоды
            "first_objection_type": first_objection.intent if first_objection else None,
            "first_objection_turn": first_objection.turn_number if first_objection else None,
            "first_objection_trigger": first_objection.action_before if first_objection else None,

            "has_breakthrough": self._breakthrough_recorded,
            "breakthrough_turn": breakthrough.turn_number if breakthrough else None,
            "breakthrough_action": breakthrough.action_before if breakthrough else None,

            "turning_points_count": len(self.get_turning_points()),

            # Статистика возражений
            "total_objections": self.get_total_objections(),
            "objection_types_seen": list(self.all_objections.keys()),
            "most_common_objection": most_common_obj[0] if most_common_obj else None,
            "most_common_objection_count": most_common_obj[1] if most_common_obj else 0,
            "repeated_objection_types": [
                ep.intent for ep in self.get_repeated_objections()
            ],

            # Эффективность actions
            "most_effective_action": most_effective[0] if most_effective else None,
            "least_effective_action": least_effective[0] if least_effective else None,
            "successful_actions": dict(self.successful_actions),
            "failed_actions": dict(self.failed_actions),

            # Профиль клиента
            "client_has_data": self.client_profile.has_data(),
            "client_company_size": self.client_profile.company_size,
            "client_pain_points": self.client_profile.pain_points,
            "client_objection_history": self.client_profile.objection_types,

            # Мета
            "total_turns": self.total_turns,
            "episodes_count": len(self.episodes),
        }

    def get_client_profile(self) -> Dict[str, Any]:
        """Получить профиль клиента."""
        return self.client_profile.to_dict()

    def __len__(self) -> int:
        """Количество записанных эпизодов."""
        return len(self.episodes)


class ContextWindow:
    """
    Скользящее окно контекста для классификатора.

    Хранит последние N ходов с полной информацией и предоставляет:
    - Историю интентов и actions
    - Детекцию паттернов (повторы, осцилляции)
    - Агрегированные метрики (счётчики, тренды)

    Attributes:
        max_size: Максимальный размер окна (по умолчанию 5)
        turns: Список TurnContext
    """

    # CRITICAL FIX: Use imported INTENT categories from yaml_config/constants.py
    # This ensures consistency with IntentTracker and EvaluatorContext
    # Convert to set for O(1) lookup (module-level constants are lists)
    # These are class attributes for backward compatibility (tests use ContextWindow.OBJECTION_INTENTS)
    OBJECTION_INTENTS: set = set(OBJECTION_INTENTS)
    POSITIVE_INTENTS: set = set(POSITIVE_INTENTS)
    QUESTION_INTENTS: set = set(QUESTION_INTENTS)

    @classmethod
    def _get_objection_intents(cls) -> set:
        """Get objection intents as set."""
        return cls.OBJECTION_INTENTS

    @classmethod
    def _get_positive_intents(cls) -> set:
        """Get positive intents as set."""
        return cls.POSITIVE_INTENTS

    @classmethod
    def _get_question_intents(cls) -> set:
        """Get question intents as set."""
        return cls.QUESTION_INTENTS

    def __init__(
        self,
        max_size: int = 5,
        config: Optional["LoadedConfig"] = None
    ):
        """
        Инициализация окна контекста.

        Args:
            max_size: Максимальное количество ходов в окне (3-10 оптимально)
            config: LoadedConfig for state_order, phase_order, progress_intents
        """
        self.max_size = max_size
        self.turns: List[TurnContext] = []

        # Уровень 3: Episodic Memory (не сбрасывается при ротации окна)
        self.episodic_memory = EpisodicMemory()
        self._total_turn_count = 0  # Счётчик всех ходов за диалог

        # Config-driven order mappings (fallback to defaults)
        self._state_order = self._load_state_order(config)
        self._phase_order = self._load_phase_order(config)
        self._progress_intents = self._load_progress_intents(config)

    def _load_state_order(
        self, config: Optional["LoadedConfig"]
    ) -> Dict[str, int]:
        """Load state order from config or use default."""
        if config is None:
            return DEFAULT_STATE_ORDER
        order = config.context.get("state_order", {})
        return order if order else DEFAULT_STATE_ORDER

    def _load_phase_order(
        self, config: Optional["LoadedConfig"]
    ) -> Dict[str, int]:
        """Load phase order from config or use default."""
        if config is None:
            return DEFAULT_PHASE_ORDER
        order = config.context.get("phase_order", {})
        return order if order else DEFAULT_PHASE_ORDER

    def _load_progress_intents(self, config: Optional["LoadedConfig"]) -> set:
        """Load progress intents from config or use default."""
        if config is None:
            return DEFAULT_PROGRESS_INTENTS
        # Try spin.progress_intents first (keys are intents)
        spin_config = config.constants.get("spin", {})
        progress_intents = spin_config.get("progress_intents", {})
        if progress_intents:
            return set(progress_intents.keys())
        # Fallback: try intents.categories.positive
        intents_config = config.constants.get("intents", {})
        categories = intents_config.get("categories", {})
        positive = categories.get("positive", [])
        return set(positive) if positive else DEFAULT_PROGRESS_INTENTS

    def add_turn(self, turn: TurnContext) -> None:
        """
        Добавить ход в окно.

        Если окно переполнено, удаляет самый старый ход.
        Также записывает в Episodic Memory (Level 3).

        Args:
            turn: Контекст хода
        """
        # Level 1-2: Скользящее окно
        prev_turn = self.turns[-1] if self.turns else None
        self.turns.append(turn)
        if len(self.turns) > self.max_size:
            self.turns.pop(0)

        # Level 3: Episodic Memory
        self._total_turn_count += 1
        momentum_direction = self.get_momentum_direction()
        self.episodic_memory.record_turn(
            turn=turn,
            turn_number=self._total_turn_count,
            prev_turn=prev_turn,
            momentum_direction=momentum_direction,
        )

    def add_turn_from_dict(
        self,
        user_message: str,
        bot_response: Optional[str],
        intent: str,
        confidence: float,
        action: str,
        state: str,
        next_state: str,
        method: str = "unknown",
        extracted_data: Dict = None,
        is_fallback: bool = False,
        fallback_tier: Optional[str] = None,
        is_disambiguation: bool = False,
    ) -> None:
        """
        Добавить ход из отдельных параметров.

        Удобный метод для интеграции с bot.py.
        """
        turn = TurnContext(
            user_message=user_message,
            bot_response=bot_response,
            intent=intent,
            confidence=confidence,
            method=method,
            action=action,
            state=state,
            next_state=next_state,
            extracted_data=extracted_data or {},
            is_fallback=is_fallback,
            fallback_tier=fallback_tier,
            is_disambiguation=is_disambiguation,
            state_order=self._state_order,
            progress_intents=self._progress_intents,
        )
        self.add_turn(turn)

    def reset(self) -> None:
        """Очистить окно для нового диалога."""
        self.turns.clear()
        self.episodic_memory.reset()
        self._total_turn_count = 0

    # =========================================================================
    # Получение истории
    # =========================================================================

    def get_intent_history(self, limit: Optional[int] = None) -> List[str]:
        """
        Получить историю интентов.

        Args:
            limit: Ограничение количества (None = все в окне)

        Returns:
            Список интентов от старых к новым
        """
        turns = self.turns[-limit:] if limit else self.turns
        return [t.intent for t in turns]

    def get_action_history(self, limit: Optional[int] = None) -> List[str]:
        """
        Получить историю actions.

        Args:
            limit: Ограничение количества (None = все в окне)

        Returns:
            Список actions от старых к новым
        """
        turns = self.turns[-limit:] if limit else self.turns
        return [t.action for t in turns]

    def get_state_history(self, limit: Optional[int] = None) -> List[str]:
        """
        Получить историю состояний.

        Args:
            limit: Ограничение количества (None = все в окне)

        Returns:
            Список состояний от старых к новым
        """
        turns = self.turns[-limit:] if limit else self.turns
        return [t.state for t in turns]

    def get_last_turn(self) -> Optional[TurnContext]:
        """Получить последний ход."""
        return self.turns[-1] if self.turns else None

    def get_last_n_turns(self, n: int) -> List[TurnContext]:
        """Получить последние N ходов."""
        return self.turns[-n:] if self.turns else []

    # =========================================================================
    # Детекция паттернов
    # =========================================================================

    def count_intent(self, intent: str, last_n: Optional[int] = None) -> int:
        """
        Подсчитать сколько раз встречался интент.

        Args:
            intent: Интент для подсчёта
            last_n: Только в последних N ходах (None = все)

        Returns:
            Количество вхождений
        """
        history = self.get_intent_history(last_n)
        return history.count(intent)

    def count_consecutive_intent(self, intent: str) -> int:
        """
        Подсчитать сколько раз подряд (с конца) встречается интент.

        Returns:
            Количество последовательных вхождений с конца
        """
        count = 0
        for turn in reversed(self.turns):
            if turn.intent == intent:
                count += 1
            else:
                break
        return count

    def has_repeated_intent(self, intent: str, min_count: int = 2, last_n: int = 5) -> bool:
        """
        Проверить повторяется ли интент.

        Args:
            intent: Интент для проверки
            min_count: Минимальное количество повторов
            last_n: В последних N ходах

        Returns:
            True если интент повторяется >= min_count раз
        """
        return self.count_intent(intent, last_n) >= min_count

    def detect_oscillation(self, last_n: int = 4) -> bool:
        """
        Обнаружить осцилляцию (колебание между позитивным и негативным).

        Паттерн: objection → agreement → objection → agreement
        Означает что клиент колеблется, а не соглашается.

        Args:
            last_n: Проверять последние N ходов

        Returns:
            True если обнаружена осцилляция
        """
        history = self.get_intent_history(last_n)
        if len(history) < 3:
            return False

        # Маппим в категории: positive, objection, other
        categories = []
        positive_set = self._get_positive_intents()
        objection_set = self._get_objection_intents()
        for intent in history:
            if intent in positive_set:
                categories.append("positive")
            elif intent in objection_set:
                categories.append("objection")
            else:
                categories.append("other")

        # Ищем паттерн чередования positive/objection
        oscillation_count = 0
        for i in range(1, len(categories)):
            if categories[i] != categories[i-1] and categories[i] in ("positive", "objection") and categories[i-1] in ("positive", "objection"):
                oscillation_count += 1

        return oscillation_count >= 2

    def detect_stuck_pattern(self, last_n: int = 3) -> bool:
        """
        Обнаружить застревание (одинаковые интенты подряд).

        Паттерн: unclear → unclear → unclear
        Означает что классификатор не понимает клиента.

        Args:
            last_n: Проверять последние N ходов

        Returns:
            True если обнаружено застревание
        """
        history = self.get_intent_history(last_n)
        if len(history) < last_n:
            return False

        # Все интенты одинаковые?
        return len(set(history)) == 1

    def detect_repeated_question(self) -> Optional[str]:
        """
        Обнаружить повторный вопрос от клиента.

        Returns:
            Интент повторного вопроса или None
        """
        history = self.get_intent_history()

        # Ищем вопросительные интенты которые встречаются > 1 раза
        question_set = self._get_question_intents()
        question_counts = Counter(
            intent for intent in history
            if intent in question_set
        )

        for intent, count in question_counts.most_common(1):
            if count >= 2:
                return intent

        return None

    # =========================================================================
    # Агрегированные метрики
    # =========================================================================

    def get_objection_count(self, last_n: Optional[int] = None) -> int:
        """Подсчитать количество возражений."""
        history = self.get_intent_history(last_n)
        objection_set = self._get_objection_intents()
        return sum(1 for intent in history if intent in objection_set)

    def get_positive_count(self, last_n: Optional[int] = None) -> int:
        """Подсчитать количество позитивных сигналов."""
        history = self.get_intent_history(last_n)
        positive_set = self._get_positive_intents()
        return sum(1 for intent in history if intent in positive_set)

    def get_question_count(self, last_n: Optional[int] = None) -> int:
        """Подсчитать количество вопросов."""
        history = self.get_intent_history(last_n)
        question_set = self._get_question_intents()
        return sum(1 for intent in history if intent in question_set)

    def get_unclear_count(self, last_n: Optional[int] = None) -> int:
        """Подсчитать количество unclear интентов."""
        return self.count_intent("unclear", last_n)

    def get_fallback_count(self, last_n: Optional[int] = None) -> int:
        """Подсчитать количество fallback-ов."""
        turns = self.turns[-last_n:] if last_n else self.turns
        return sum(1 for t in turns if t.is_fallback)

    def get_average_confidence(self, last_n: Optional[int] = None) -> float:
        """Получить среднюю уверенность классификации."""
        turns = self.turns[-last_n:] if last_n else self.turns
        if not turns:
            return 0.0
        return sum(t.confidence for t in turns) / len(turns)

    def get_confidence_trend(self, last_n: int = 3) -> str:
        """
        Определить тренд уверенности.

        Returns:
            "increasing", "decreasing", "stable", или "unknown"
        """
        turns = self.turns[-last_n:]
        if len(turns) < 2:
            return "unknown"

        confidences = [t.confidence for t in turns]

        # Считаем разницу между последним и первым
        diff = confidences[-1] - confidences[0]

        if diff > 0.1:
            return "increasing"
        elif diff < -0.1:
            return "decreasing"
        else:
            return "stable"

    # =========================================================================
    # Формирование контекста для классификатора
    # =========================================================================

    def get_classifier_context(self) -> Dict[str, Any]:
        """
        Получить полный контекст для классификатора.

        Returns:
            Dict с историей и агрегированными метриками
        """
        # Уровень 1: Базовый контекст
        context = {
            # История (основное)
            "intent_history": self.get_intent_history(),
            "action_history": self.get_action_history(),

            # Последний ход (самый важный по исследованиям)
            "last_intent": self.turns[-1].intent if self.turns else None,
            "last_action": self.turns[-1].action if self.turns else None,
            "last_confidence": self.turns[-1].confidence if self.turns else 0.0,

            # Счётчики
            "objection_count": self.get_objection_count(),
            "positive_count": self.get_positive_count(),
            "question_count": self.get_question_count(),
            "unclear_count": self.get_unclear_count(),
            "fallback_count": self.get_fallback_count(),

            # Паттерны
            "has_oscillation": self.detect_oscillation(),
            "is_stuck": self.detect_stuck_pattern(),
            "repeated_question": self.detect_repeated_question(),

            # Тренды
            "confidence_trend": self.get_confidence_trend(),
            "avg_confidence": self.get_average_confidence(),

            # Мета
            "window_size": len(self.turns),
        }

        # Уровень 2: Структурированный контекст
        context.update(self.get_structured_context())

        # Уровень 3: Episodic Memory
        context.update(self.get_episodic_context())

        return context

    # =========================================================================
    # УРОВЕНЬ 2: Структурированный контекст
    # =========================================================================

    def get_structured_context(self, use_v2_engagement: bool = False) -> Dict[str, Any]:
        """
        Получить структурированный контекст (Уровень 2).

        Включает:
        - Типы ходов и их распределение
        - Engagement метрики
        - Funnel progress
        - Momentum (инерция)
        - Trigger analysis

        Args:
            use_v2_engagement: Использовать улучшенный расчёт engagement (v2)
                             без зависимости от word_count

        Returns:
            Dict со структурированными метриками
        """
        # Выбираем версию engagement
        if use_v2_engagement:
            engagement_level = self.get_engagement_level_v2().value
            engagement_score = self.get_engagement_score_v2()
            engagement_trend = self.get_engagement_trend_v2()
        else:
            engagement_level = self.get_engagement_level().value
            engagement_score = self.get_engagement_score()
            engagement_trend = self.get_engagement_trend()

        return {
            # Типы ходов
            "turn_types": self.get_turn_type_history(),
            "turn_type_counts": self.get_turn_type_counts(),
            "last_turn_type": self.get_last_turn_type(),

            # Engagement
            "engagement_level": engagement_level,
            "engagement_score": engagement_score,
            "engagement_trend": engagement_trend,

            # Funnel Progress
            "funnel_progress": self.get_funnel_progress(),
            "funnel_velocity": self.get_funnel_velocity(),
            "is_progressing": self.is_progressing(),
            "is_regressing": self.is_regressing(),

            # Momentum
            "momentum": self.get_momentum(),
            "momentum_direction": self.get_momentum_direction(),

            # Triggers
            "last_objection_trigger": self.get_last_objection_trigger(),
            "last_progress_trigger": self.get_last_progress_trigger(),
            "effective_actions": self.get_effective_actions(),

            # Message metrics
            "avg_message_length": self.get_avg_message_length(),
            "data_provided_count": self.get_data_provided_count(),
        }

    # -------------------------------------------------------------------------
    # Turn Type Analysis
    # -------------------------------------------------------------------------

    def get_turn_type_history(self, limit: Optional[int] = None) -> List[str]:
        """Получить историю типов ходов."""
        turns = self.turns[-limit:] if limit else self.turns
        return [t.turn_type.value if t.turn_type else "unknown" for t in turns]

    def get_turn_type_counts(self) -> Dict[str, int]:
        """Подсчитать количество каждого типа хода."""
        counts = Counter(t.turn_type for t in self.turns if t.turn_type)
        return {tt.value: counts.get(tt, 0) for tt in TurnType}

    def get_last_turn_type(self) -> Optional[str]:
        """Получить тип последнего хода."""
        if not self.turns:
            return None
        return self.turns[-1].turn_type.value if self.turns[-1].turn_type else None

    def count_turn_type(self, turn_type: TurnType, last_n: Optional[int] = None) -> int:
        """Подсчитать количество ходов определённого типа."""
        turns = self.turns[-last_n:] if last_n else self.turns
        return sum(1 for t in turns if t.turn_type == turn_type)

    # -------------------------------------------------------------------------
    # Engagement Analysis
    # -------------------------------------------------------------------------

    def get_engagement_score(self) -> float:
        """
        Вычислить score вовлечённости (0-1).

        Факторы:
        - Длина сообщений (больше = лучше)
        - Предоставление данных (есть = лучше)
        - Тип ходов (progress > lateral > stuck > regress)
        """
        if not self.turns:
            return 0.5  # Нейтральный начальный score

        scores = []
        for turn in self.turns:
            turn_score = 0.5  # Базовый

            # Длина сообщения (нормализуем к 0-0.3)
            length_score = min(turn.word_count / 10, 1.0) * 0.3
            turn_score += length_score

            # Предоставление данных (+0.2)
            if turn.has_data:
                turn_score += 0.2

            # Тип хода
            if turn.turn_type == TurnType.PROGRESS:
                turn_score += 0.2
            elif turn.turn_type == TurnType.LATERAL:
                turn_score += 0.1  # Вопросы — признак интереса
            elif turn.turn_type == TurnType.REGRESS:
                turn_score -= 0.2
            elif turn.turn_type == TurnType.STUCK:
                turn_score -= 0.1

            scores.append(max(0, min(1, turn_score)))

        return sum(scores) / len(scores)

    def get_engagement_level(self) -> EngagementLevel:
        """Определить уровень вовлечённости."""
        score = self.get_engagement_score()

        if score >= 0.7:
            return EngagementLevel.HIGH
        elif score >= 0.5:
            return EngagementLevel.MEDIUM
        elif score >= 0.3:
            return EngagementLevel.LOW
        else:
            return EngagementLevel.DISENGAGED

    def get_engagement_trend(self) -> str:
        """
        Определить тренд вовлечённости.

        Returns:
            "improving", "declining", "stable", или "unknown"
        """
        if len(self.turns) < 3:
            return "unknown"

        # Считаем engagement для первой и второй половины
        mid = len(self.turns) // 2

        first_half_scores = []
        for turn in self.turns[:mid]:
            score = 0.5
            if turn.has_data:
                score += 0.3
            if turn.turn_type == TurnType.PROGRESS:
                score += 0.2
            elif turn.turn_type == TurnType.REGRESS:
                score -= 0.2
            first_half_scores.append(score)

        second_half_scores = []
        for turn in self.turns[mid:]:
            score = 0.5
            if turn.has_data:
                score += 0.3
            if turn.turn_type == TurnType.PROGRESS:
                score += 0.2
            elif turn.turn_type == TurnType.REGRESS:
                score -= 0.2
            second_half_scores.append(score)

        first_avg = sum(first_half_scores) / len(first_half_scores) if first_half_scores else 0.5
        second_avg = sum(second_half_scores) / len(second_half_scores) if second_half_scores else 0.5

        diff = second_avg - first_avg
        if diff > 0.1:
            return "improving"
        elif diff < -0.1:
            return "declining"
        else:
            return "stable"

    # -------------------------------------------------------------------------
    # Engagement V2 (улучшенный расчёт без зависимости от word_count)
    # Phase 3: context_engagement_v2 (PLAN_CONTEXT_POLICY.md)
    # -------------------------------------------------------------------------

    # Короткие положительные ответы которые НЕ означают disengagement
    POSITIVE_SHORT_RESPONSES = {
        "да", "ок", "окей", "хорошо", "понял", "понятно", "ясно",
        "угу", "ага", "конечно", "верно", "точно", "согласен",
        "давайте", "можно", "да конечно", "да хорошо",
    }

    def get_engagement_score_v2(self) -> float:
        """
        Улучшенный расчёт engagement без зависимости от word_count.

        Факторы (Phase 3: PLAN_CONTEXT_POLICY.md):
        - has_data: предоставление данных (+0.25)
        - turn_type: тип хода (progress +0.2, lateral +0.1, regress -0.15, stuck -0.1)
        - question_count: вопросы от клиента (+0.1, признак интереса)
        - repeated_question: повторные вопросы (-0.1, признак непонимания)
        - objection частота: частые возражения (-0.1)
        - positive short response: НЕ штрафуем за краткость

        Returns:
            Score от 0.0 до 1.0
        """
        if not self.turns:
            return 0.5

        scores = []
        for turn in self.turns:
            turn_score = 0.5  # Базовый нейтральный

            # 1. Предоставление данных (+0.25)
            if turn.has_data:
                turn_score += 0.25

            # 2. Тип хода
            if turn.turn_type == TurnType.PROGRESS:
                turn_score += 0.2
            elif turn.turn_type == TurnType.LATERAL:
                turn_score += 0.1  # Вопросы — признак интереса
            elif turn.turn_type == TurnType.REGRESS:
                turn_score -= 0.15
            elif turn.turn_type == TurnType.STUCK:
                turn_score -= 0.1

            # 3. Короткий позитивный ответ — НЕ штрафуем
            msg_lower = turn.user_message.lower().strip()
            if msg_lower in self.POSITIVE_SHORT_RESPONSES:
                # Нейтрализуем возможный негатив от краткости
                turn_score = max(turn_score, 0.5)

            scores.append(max(0.0, min(1.0, turn_score)))

        base_score = sum(scores) / len(scores)

        # 4. Глобальные модификаторы
        # Много вопросов = интерес (+0.05)
        if self.get_question_count() >= 2:
            base_score = min(1.0, base_score + 0.05)

        # Повторные вопросы = непонимание (-0.05)
        if self.detect_repeated_question():
            base_score = max(0.0, base_score - 0.05)

        # Много возражений = сопротивление (-0.05)
        if self.get_objection_count() >= 3:
            base_score = max(0.0, base_score - 0.05)

        return base_score

    def get_engagement_level_v2(self) -> EngagementLevel:
        """
        Определить уровень вовлечённости (v2).

        Использует улучшенный score без зависимости от word_count.
        """
        score = self.get_engagement_score_v2()

        if score >= 0.65:
            return EngagementLevel.HIGH
        elif score >= 0.45:
            return EngagementLevel.MEDIUM
        elif score >= 0.3:
            return EngagementLevel.LOW
        else:
            return EngagementLevel.DISENGAGED

    def get_engagement_trend_v2(self) -> str:
        """
        Определить тренд вовлечённости (v2).

        Использует улучшенный расчёт на основе типов ходов.
        """
        if len(self.turns) < 3:
            return "unknown"

        mid = len(self.turns) // 2

        def calc_half_score(turns_slice):
            if not turns_slice:
                return 0.5
            scores = []
            for turn in turns_slice:
                score = 0.5
                if turn.has_data:
                    score += 0.25
                if turn.turn_type == TurnType.PROGRESS:
                    score += 0.2
                elif turn.turn_type == TurnType.LATERAL:
                    score += 0.1
                elif turn.turn_type == TurnType.REGRESS:
                    score -= 0.15
                # Короткие позитивные ответы не штрафуем
                msg_lower = turn.user_message.lower().strip()
                if msg_lower in self.POSITIVE_SHORT_RESPONSES:
                    score = max(score, 0.5)
                scores.append(max(0.0, min(1.0, score)))
            return sum(scores) / len(scores)

        first_avg = calc_half_score(self.turns[:mid])
        second_avg = calc_half_score(self.turns[mid:])

        diff = second_avg - first_avg
        if diff > 0.08:
            return "improving"
        elif diff < -0.08:
            return "declining"
        else:
            return "stable"

    # -------------------------------------------------------------------------
    # Funnel Progress Analysis
    # -------------------------------------------------------------------------

    def get_funnel_progress(self) -> int:
        """
        Получить общий прогресс по воронке.

        Returns:
            Суммарный delta по всем ходам
        """
        return sum(t.funnel_delta for t in self.turns)

    def get_funnel_velocity(self) -> float:
        """
        Получить скорость движения по воронке (прогресс за ход).

        Returns:
            Средний delta за ход
        """
        if not self.turns:
            return 0.0
        return self.get_funnel_progress() / len(self.turns)

    def is_progressing(self) -> bool:
        """Проверить движется ли клиент вперёд по воронке."""
        if not self.turns:
            return False

        # Для 1 хода смотрим его delta (симметрично с is_regressing)
        if len(self.turns) == 1:
            return self.turns[0].funnel_delta > 0

        # Смотрим последние 2 хода
        recent_delta = sum(t.funnel_delta for t in self.turns[-2:])
        return recent_delta > 0

    def is_regressing(self) -> bool:
        """Проверить откатывается ли клиент назад."""
        if not self.turns:
            return False

        # Для 1 хода смотрим его delta
        if len(self.turns) == 1:
            return self.turns[0].funnel_delta < 0

        # Смотрим последние 2 хода
        recent_delta = sum(t.funnel_delta for t in self.turns[-2:])
        return recent_delta < 0

    def get_current_funnel_stage(self) -> Optional[str]:
        """Получить текущую стадию воронки."""
        if not self.turns:
            return None
        return self.turns[-1].next_state

    # -------------------------------------------------------------------------
    # Momentum Analysis
    # -------------------------------------------------------------------------

    def get_momentum(self) -> float:
        """
        Получить инерцию диалога (-1 до +1).

        Положительный = движение к закрытию
        Отрицательный = движение к отказу
        Ноль = застой

        Returns:
            Momentum score от -1 до +1
        """
        if not self.turns:
            return 0.0

        # Веса для типов ходов
        type_weights = {
            TurnType.PROGRESS: 1.0,
            TurnType.LATERAL: 0.2,   # Вопросы — слабый позитив
            TurnType.NEUTRAL: 0.0,
            TurnType.STUCK: -0.3,
            TurnType.REGRESS: -1.0,
        }

        # Weighted average с экспоненциальным затуханием (недавние важнее)
        total_weight = 0
        momentum = 0

        for i, turn in enumerate(self.turns):
            # Экспоненциальный вес: последний ход важнее
            recency_weight = 2 ** i  # 1, 2, 4, 8, 16...
            turn_weight = type_weights.get(turn.turn_type, 0)

            momentum += turn_weight * recency_weight
            total_weight += recency_weight

        if total_weight == 0:
            return 0.0

        # Нормализуем к -1..+1
        raw_momentum = momentum / total_weight
        return max(-1.0, min(1.0, raw_momentum))

    def get_momentum_direction(self) -> str:
        """
        Определить направление momentum.

        Returns:
            "positive", "negative", или "neutral"
        """
        momentum = self.get_momentum()

        if momentum > 0.2:
            return "positive"
        elif momentum < -0.2:
            return "negative"
        else:
            return "neutral"

    # -------------------------------------------------------------------------
    # Trigger Analysis
    # -------------------------------------------------------------------------

    def get_last_objection_trigger(self) -> Optional[Dict[str, str]]:
        """
        Найти что триггернуло последнее возражение.

        Returns:
            {"action": str, "intent_before": str} или None
        """
        for i in range(len(self.turns) - 1, 0, -1):
            if self.turns[i].turn_type == TurnType.REGRESS:
                prev_turn = self.turns[i - 1]
                return {
                    "action": prev_turn.action,
                    "intent_before": prev_turn.intent,
                    "objection_type": self.turns[i].intent,
                }
        return None

    def get_last_progress_trigger(self) -> Optional[Dict[str, str]]:
        """
        Найти что триггернуло последний прогресс.

        Returns:
            {"action": str, "intent_before": str} или None
        """
        for i in range(len(self.turns) - 1, 0, -1):
            if self.turns[i].turn_type == TurnType.PROGRESS:
                prev_turn = self.turns[i - 1]
                return {
                    "action": prev_turn.action,
                    "intent_before": prev_turn.intent,
                    "progress_intent": self.turns[i].intent,
                }
        return None

    def get_effective_actions(self) -> List[str]:
        """
        Получить список actions которые привели к прогрессу.

        Returns:
            Список эффективных actions
        """
        effective = []
        for i in range(1, len(self.turns)):
            if self.turns[i].turn_type == TurnType.PROGRESS:
                effective.append(self.turns[i - 1].action)
        return effective

    def get_ineffective_actions(self) -> List[str]:
        """
        Получить список actions которые привели к регрессу.

        Returns:
            Список неэффективных actions
        """
        ineffective = []
        for i in range(1, len(self.turns)):
            if self.turns[i].turn_type == TurnType.REGRESS:
                ineffective.append(self.turns[i - 1].action)
        return ineffective

    # -------------------------------------------------------------------------
    # Message Metrics
    # -------------------------------------------------------------------------

    def get_avg_message_length(self) -> float:
        """Получить среднюю длину сообщений клиента."""
        if not self.turns:
            return 0.0
        return sum(t.message_length for t in self.turns) / len(self.turns)

    def get_avg_word_count(self) -> float:
        """Получить среднее количество слов в сообщениях."""
        if not self.turns:
            return 0.0
        return sum(t.word_count for t in self.turns) / len(self.turns)

    def get_data_provided_count(self) -> int:
        """Подсчитать сколько раз клиент предоставил данные."""
        return sum(1 for t in self.turns if t.has_data)

    # -------------------------------------------------------------------------
    # Convenience: Уровень 2 only context
    # -------------------------------------------------------------------------

    def get_level2_context(self) -> Dict[str, Any]:
        """
        Получить ТОЛЬКО контекст Уровня 2 (для тестирования).

        Returns:
            Dict только с метриками Уровня 2
        """
        return self.get_structured_context()

    # =========================================================================
    # УРОВЕНЬ 3: Episodic Memory (долгосрочная память)
    # =========================================================================

    def get_episodic_context(self) -> Dict[str, Any]:
        """
        Получить контекст из Episodic Memory (Уровень 3).

        Returns:
            Dict с ключевыми эпизодами и статистикой за весь диалог
        """
        return self.episodic_memory.get_episodic_context()

    def get_level3_context(self) -> Dict[str, Any]:
        """
        Получить ТОЛЬКО контекст Уровня 3 (для тестирования).

        Returns:
            Dict только с метриками Уровня 3
        """
        return self.get_episodic_context()

    def get_client_profile(self) -> Dict[str, Any]:
        """Получить собранный профиль клиента."""
        return self.episodic_memory.get_client_profile()

    def get_first_objection(self) -> Optional[Episode]:
        """Получить первое возражение за диалог."""
        return self.episodic_memory.get_first_objection()

    def has_breakthrough(self) -> bool:
        """Был ли прорыв в диалоге (прогресс после возражения)."""
        return self.episodic_memory.has_breakthrough()

    def is_objection_repeated(self, objection_type: str) -> bool:
        """Проверить было ли такое возражение раньше в диалоге."""
        return self.episodic_memory.is_objection_repeated(objection_type)

    def get_total_turn_count(self) -> int:
        """Получить общее количество ходов за диалог (не только в окне)."""
        return self._total_turn_count

    def get_action_effectiveness(self, action: str) -> float:
        """Получить эффективность action за весь диалог (0-1)."""
        return self.episodic_memory.get_action_effectiveness(action)

    def __len__(self) -> int:
        """Количество ходов в окне."""
        return len(self.turns)

    def __bool__(self) -> bool:
        """True если есть хотя бы один ход."""
        return len(self.turns) > 0
