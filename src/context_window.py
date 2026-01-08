"""
Context Window — расширенный контекст для классификатора

Уровень 1: Sliding Window
- Хранит последние N ходов диалога с полной информацией
- Предоставляет историю интентов и actions
- Вычисляет паттерны поведения (повторы, тренды)

Исследования показали:
- Окно 3-5 ходов оптимально (arXiv 2024)
- Полная история создаёт шум и ухудшает классификацию на 20%+
- Последний ход пользователя — самый важный контекст
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from collections import Counter
import time


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
        return {
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

    def __len__(self) -> int:
        """Количество ходов в окне."""
        return len(self.turns)

    def __bool__(self) -> bool:
        """True если есть хотя бы один ход."""
        return len(self.turns) > 0
