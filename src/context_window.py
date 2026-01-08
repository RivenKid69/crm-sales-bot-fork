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

Исследования показали:
- Окно 3-5 ходов оптимально (arXiv 2024)
- Полная история создаёт шум и ухудшает классификацию на 20%+
- Последний ход пользователя — самый важный контекст
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any, Tuple
from collections import Counter
from enum import Enum
import time


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


# Порядок SPIN фаз для расчёта прогресса
SPIN_PHASE_ORDER = {
    "greeting": 0,
    "situation": 1,
    "problem": 2,
    "implication": 3,
    "need_payoff": 4,
    "presentation": 5,
    "close": 6,
    "success": 7,
}

# Порядок состояний для расчёта прогресса
STATE_ORDER = {
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

    def __post_init__(self):
        """Автоматически вычисляем производные поля."""
        # Длина и слова
        self.message_length = len(self.user_message)
        self.word_count = len(self.user_message.split())
        self.has_data = bool(self.extracted_data)

        # Прогресс по воронке
        state_order = STATE_ORDER.get(self.state, 0)
        next_state_order = STATE_ORDER.get(self.next_state, 0)
        self.funnel_delta = next_state_order - state_order

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

        # 5. Прогресс по delta
        if self.funnel_delta > 0:
            return TurnType.PROGRESS

        # 6. По умолчанию смотрим на delta
        if self.funnel_delta < 0:
            return TurnType.REGRESS
        elif self.funnel_delta == 0:
            return TurnType.NEUTRAL

        return TurnType.PROGRESS


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

    # Интенты возражений
    OBJECTION_INTENTS = {
        "objection_price", "objection_competitor",
        "objection_no_time", "objection_think",
        "objection_timing", "objection_complexity",
        "objection_no_need", "objection_trust"
    }

    # Позитивные интенты (сбрасывают негативные паттерны)
    POSITIVE_INTENTS = {
        "agreement", "demo_request", "callback_request", "contact_provided",
        "situation_provided", "problem_revealed", "implication_acknowledged",
        "need_expressed", "info_provided", "gratitude"
    }

    # Вопросительные интенты
    QUESTION_INTENTS = {
        "question_features", "question_integrations", "price_question",
        "pricing_details", "comparison", "consultation_request"
    }

    def __init__(self, max_size: int = 5):
        """
        Инициализация окна контекста.

        Args:
            max_size: Максимальное количество ходов в окне (3-10 оптимально)
        """
        self.max_size = max_size
        self.turns: List[TurnContext] = []

    def add_turn(self, turn: TurnContext) -> None:
        """
        Добавить ход в окно.

        Если окно переполнено, удаляет самый старый ход.

        Args:
            turn: Контекст хода
        """
        self.turns.append(turn)
        if len(self.turns) > self.max_size:
            self.turns.pop(0)

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
        )
        self.add_turn(turn)

    def reset(self) -> None:
        """Очистить окно для нового диалога."""
        self.turns.clear()

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
        for intent in history:
            if intent in self.POSITIVE_INTENTS:
                categories.append("positive")
            elif intent in self.OBJECTION_INTENTS:
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
        question_counts = Counter(
            intent for intent in history
            if intent in self.QUESTION_INTENTS
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
        return sum(1 for intent in history if intent in self.OBJECTION_INTENTS)

    def get_positive_count(self, last_n: Optional[int] = None) -> int:
        """Подсчитать количество позитивных сигналов."""
        history = self.get_intent_history(last_n)
        return sum(1 for intent in history if intent in self.POSITIVE_INTENTS)

    def get_question_count(self, last_n: Optional[int] = None) -> int:
        """Подсчитать количество вопросов."""
        history = self.get_intent_history(last_n)
        return sum(1 for intent in history if intent in self.QUESTION_INTENTS)

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

        return context

    # =========================================================================
    # УРОВЕНЬ 2: Структурированный контекст
    # =========================================================================

    def get_structured_context(self) -> Dict[str, Any]:
        """
        Получить структурированный контекст (Уровень 2).

        Включает:
        - Типы ходов и их распределение
        - Engagement метрики
        - Funnel progress
        - Momentum (инерция)
        - Trigger analysis

        Returns:
            Dict со структурированными метриками
        """
        return {
            # Типы ходов
            "turn_types": self.get_turn_type_history(),
            "turn_type_counts": self.get_turn_type_counts(),
            "last_turn_type": self.get_last_turn_type(),

            # Engagement
            "engagement_level": self.get_engagement_level().value,
            "engagement_score": self.get_engagement_score(),
            "engagement_trend": self.get_engagement_trend(),

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
        if len(self.turns) < 2:
            return False

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

    def __len__(self) -> int:
        """Количество ходов в окне."""
        return len(self.turns)

    def __bool__(self) -> bool:
        """True если есть хотя бы один ход."""
        return len(self.turns) > 0
