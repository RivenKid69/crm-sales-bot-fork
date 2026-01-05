"""
Metrics Tracker для CRM Sales Bot.

Трекинг метрик для анализа эффективности.
Критично для data-driven улучшений.

Использование:
    from metrics import ConversationMetrics

    metrics = ConversationMetrics()
    metrics.record_turn("spin_situation", "company_size")
    metrics.record_objection("price")
    summary = metrics.get_summary()
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from enum import Enum


class ConversationOutcome(Enum):
    """Возможные исходы диалога"""
    SUCCESS = "success"           # Контакт получен
    DEMO_SCHEDULED = "demo_scheduled"  # Демо запланировано
    SOFT_CLOSE = "soft_close"     # Мягкое завершение
    REJECTED = "rejected"         # Отказ
    ABANDONED = "abandoned"       # Диалог не завершён
    TIMEOUT = "timeout"           # Таймаут
    ERROR = "error"               # Ошибка


@dataclass
class TurnRecord:
    """Запись одного хода диалога"""
    turn_number: int
    state: str
    intent: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    tone: Optional[str] = None
    response_time_ms: Optional[float] = None
    fallback_used: bool = False
    fallback_tier: Optional[str] = None


class ConversationMetrics:
    """
    Трекинг метрик для одного диалога.

    Собирает:
    - Количество ходов (turns)
    - Распределение по фазам
    - Последовательность интентов
    - Возражения
    - Fallback usage
    - История тона
    - Lead score history
    - Время ответов
    """

    def __init__(self, conversation_id: Optional[str] = None):
        self.conversation_id = conversation_id
        self.created_at = datetime.now(timezone.utc)
        self.reset()

    def reset(self) -> None:
        """Сбросить все метрики"""
        self.turns = 0
        self.phase_turns: Dict[str, int] = defaultdict(int)
        self.intents_sequence: List[str] = []
        self.objections: List[Dict[str, Any]] = []
        self.fallback_count = 0
        self.fallback_by_tier: Dict[str, int] = defaultdict(int)
        self.tone_history: List[Dict[str, Any]] = []
        self.lead_score_history: List[Dict[str, Any]] = []
        self.turn_records: List[TurnRecord] = []
        self.collected_data: Dict[str, Any] = {}
        self.outcome: Optional[ConversationOutcome] = None
        self.end_time: Optional[datetime] = None
        self._start_times: Dict[str, float] = {}

    def start_turn_timer(self) -> None:
        """Запустить таймер для измерения времени ответа"""
        import time
        self._start_times["current_turn"] = time.time()

    def record_turn(
        self,
        state: str,
        intent: str,
        tone: Optional[str] = None,
        fallback_used: bool = False,
        fallback_tier: Optional[str] = None
    ) -> None:
        """
        Записать ход диалога.

        Args:
            state: Текущее состояние FSM
            intent: Распознанный интент
            tone: Тон клиента (optional)
            fallback_used: Был ли использован fallback
            fallback_tier: Уровень fallback (tier_1, tier_2, etc.)
        """
        import time

        self.turns += 1
        self.phase_turns[state] += 1
        self.intents_sequence.append(intent)

        # Вычисляем время ответа
        response_time_ms = None
        if "current_turn" in self._start_times:
            response_time_ms = (time.time() - self._start_times["current_turn"]) * 1000
            del self._start_times["current_turn"]

        # Создаём запись хода
        record = TurnRecord(
            turn_number=self.turns,
            state=state,
            intent=intent,
            tone=tone,
            response_time_ms=response_time_ms,
            fallback_used=fallback_used,
            fallback_tier=fallback_tier
        )
        self.turn_records.append(record)

        # Записываем тон
        if tone:
            self.tone_history.append({
                "turn": self.turns,
                "tone": tone,
                "state": state
            })

        # Записываем fallback
        if fallback_used:
            self.fallback_count += 1
            if fallback_tier:
                self.fallback_by_tier[fallback_tier] += 1

    def record_objection(
        self,
        objection_type: str,
        resolved: bool = False,
        attempts: int = 1
    ) -> None:
        """
        Записать возражение.

        Args:
            objection_type: Тип возражения (price, competitor, no_time, etc.)
            resolved: Было ли возражение разрешено
            attempts: Количество попыток разрешить
        """
        self.objections.append({
            "turn": self.turns,
            "type": objection_type,
            "resolved": resolved,
            "attempts": attempts
        })

    def record_fallback(self, tier: Optional[str] = None) -> None:
        """
        Записать использование fallback.

        Args:
            tier: Уровень fallback (tier_1, tier_2, tier_3, tier_4)
        """
        self.fallback_count += 1
        if tier:
            self.fallback_by_tier[tier] += 1

    def record_lead_score(self, score: int, temperature: str, signal: Optional[str] = None) -> None:
        """
        Записать изменение lead score.

        Args:
            score: Текущий score (0-100)
            temperature: Температура лида (cold, warm, hot, very_hot)
            signal: Сигнал который привёл к изменению
        """
        self.lead_score_history.append({
            "turn": self.turns,
            "score": score,
            "temperature": temperature,
            "signal": signal
        })

    def record_collected_data(self, key: str, value: Any) -> None:
        """Записать собранные данные о клиенте"""
        self.collected_data[key] = value

    def set_outcome(self, outcome: ConversationOutcome) -> None:
        """Установить итог диалога"""
        self.outcome = outcome
        self.end_time = datetime.now(timezone.utc)

    def get_duration_seconds(self) -> Optional[float]:
        """Получить длительность диалога в секундах"""
        if self.end_time:
            return (self.end_time - self.created_at).total_seconds()
        return None

    def get_average_response_time_ms(self) -> Optional[float]:
        """Получить среднее время ответа в миллисекундах"""
        times = [r.response_time_ms for r in self.turn_records if r.response_time_ms is not None]
        if times:
            return sum(times) / len(times)
        return None

    def get_phase_distribution(self) -> Dict[str, float]:
        """Получить распределение ходов по фазам в процентах"""
        if self.turns == 0:
            return {}

        return {
            state: (count / self.turns) * 100
            for state, count in self.phase_turns.items()
        }

    def get_dominant_tone(self) -> Optional[str]:
        """Получить преобладающий тон в диалоге"""
        if not self.tone_history:
            return None

        from collections import Counter
        tones = [t["tone"] for t in self.tone_history]
        most_common = Counter(tones).most_common(1)
        return most_common[0][0] if most_common else None

    def get_final_lead_score(self) -> Optional[int]:
        """Получить финальный lead score"""
        if self.lead_score_history:
            return self.lead_score_history[-1]["score"]
        return None

    def get_summary(self) -> Dict[str, Any]:
        """
        Получить полную сводку метрик.

        Returns:
            Dict со всеми метриками диалога
        """
        return {
            "conversation_id": self.conversation_id,
            "created_at": self.created_at.isoformat() + "Z",
            "duration_seconds": self.get_duration_seconds(),

            # Основные метрики
            "total_turns": self.turns,
            "phase_distribution": dict(self.phase_turns),
            "phase_percentage": self.get_phase_distribution(),

            # Интенты
            "intents_sequence": self.intents_sequence,
            "unique_intents": len(set(self.intents_sequence)),

            # Возражения
            "objection_count": len(self.objections),
            "objections": self.objections,
            "objections_resolved": sum(1 for o in self.objections if o.get("resolved")),

            # Fallback
            "fallback_count": self.fallback_count,
            "fallback_by_tier": dict(self.fallback_by_tier),
            "fallback_rate": (self.fallback_count / self.turns * 100) if self.turns > 0 else 0,

            # Тон
            "tone_history": self.tone_history,
            "dominant_tone": self.get_dominant_tone(),

            # Lead scoring
            "final_lead_score": self.get_final_lead_score(),
            "lead_score_history": self.lead_score_history,

            # Performance
            "average_response_time_ms": self.get_average_response_time_ms(),

            # Итог
            "outcome": self.outcome.value if self.outcome else "in_progress",
            "collected_data_count": len(self.collected_data),

            # Derived
            "final_outcome": self._determine_outcome()
        }

    def _determine_outcome(self) -> str:
        """Определить итог диалога на основе интентов"""
        if self.outcome:
            return self.outcome.value

        # Проверяем по интентам
        if "contact_provided" in self.intents_sequence:
            return "success"
        if "demo_request" in self.intents_sequence:
            return "demo_scheduled"
        if any(i in self.intents_sequence for i in ["rejection", "hard_rejection"]):
            return "rejected"
        if "soft_close" in self.intents_sequence:
            return "soft_close"

        return "abandoned"

    def to_log_dict(self) -> Dict[str, Any]:
        """
        Краткая версия для логирования (без больших списков).
        """
        return {
            "conversation_id": self.conversation_id,
            "total_turns": self.turns,
            "fallback_count": self.fallback_count,
            "objection_count": len(self.objections),
            "outcome": self._determine_outcome(),
            "duration_seconds": self.get_duration_seconds(),
            "avg_response_ms": self.get_average_response_time_ms(),
            "final_lead_score": self.get_final_lead_score(),
        }


# =============================================================================
# Агрегированные метрики (для нескольких диалогов)
# =============================================================================

class AggregatedMetrics:
    """
    Агрегатор метрик по нескольким диалогам.
    Для аналитики и отчётов.
    """

    def __init__(self):
        self.conversations: List[ConversationMetrics] = []

    def add(self, metrics: ConversationMetrics) -> None:
        """Добавить метрики диалога"""
        self.conversations.append(metrics)

    def clear(self) -> None:
        """Очистить все метрики"""
        self.conversations.clear()

    @property
    def count(self) -> int:
        """Количество диалогов"""
        return len(self.conversations)

    def get_success_rate(self) -> float:
        """Процент успешных диалогов"""
        if not self.conversations:
            return 0.0

        success_outcomes = {"success", "demo_scheduled"}
        successful = sum(
            1 for m in self.conversations
            if m._determine_outcome() in success_outcomes
        )
        return (successful / len(self.conversations)) * 100

    def get_average_turns(self) -> float:
        """Среднее количество ходов"""
        if not self.conversations:
            return 0.0
        return sum(m.turns for m in self.conversations) / len(self.conversations)

    def get_average_fallback_rate(self) -> float:
        """Средний процент fallback"""
        if not self.conversations:
            return 0.0

        rates = []
        for m in self.conversations:
            if m.turns > 0:
                rates.append((m.fallback_count / m.turns) * 100)

        return sum(rates) / len(rates) if rates else 0.0

    def get_outcome_distribution(self) -> Dict[str, int]:
        """Распределение итогов"""
        distribution: Dict[str, int] = defaultdict(int)
        for m in self.conversations:
            outcome = m._determine_outcome()
            distribution[outcome] += 1
        return dict(distribution)

    def get_summary(self) -> Dict[str, Any]:
        """Сводка агрегированных метрик"""
        return {
            "total_conversations": self.count,
            "success_rate": self.get_success_rate(),
            "average_turns": self.get_average_turns(),
            "average_fallback_rate": self.get_average_fallback_rate(),
            "outcome_distribution": self.get_outcome_distribution(),
        }


# =============================================================================
# CLI для демонстрации
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("METRICS DEMO")
    print("=" * 60)

    # Создаём метрики для демо-диалога
    metrics = ConversationMetrics(conversation_id="demo_123")

    # Симулируем диалог
    metrics.start_turn_timer()
    import time
    time.sleep(0.1)  # Имитация обработки
    metrics.record_turn("greeting", "greeting", tone="neutral")

    metrics.start_turn_timer()
    time.sleep(0.05)
    metrics.record_turn("spin_situation", "company_size", tone="neutral")
    metrics.record_collected_data("company_size", 10)

    metrics.start_turn_timer()
    time.sleep(0.08)
    metrics.record_turn("spin_problem", "pain_point", tone="frustrated")
    metrics.record_objection("price", resolved=True, attempts=1)

    metrics.start_turn_timer()
    time.sleep(0.06)
    metrics.record_turn("presentation", "interest", tone="interested")
    metrics.record_lead_score(45, "warm", "explicit_interest")

    metrics.start_turn_timer()
    time.sleep(0.04)
    metrics.record_turn("close", "contact_provided", tone="positive")
    metrics.set_outcome(ConversationOutcome.SUCCESS)

    # Выводим сводку
    print("\n--- Conversation Summary ---")
    import json
    summary = metrics.get_summary()
    print(json.dumps(summary, indent=2, ensure_ascii=False, default=str))

    print("\n--- Log Dict (краткая версия) ---")
    print(json.dumps(metrics.to_log_dict(), indent=2, default=str))

    # Демо агрегированных метрик
    print("\n--- Aggregated Metrics ---")
    agg = AggregatedMetrics()
    agg.add(metrics)

    # Добавим ещё один диалог
    metrics2 = ConversationMetrics(conversation_id="demo_456")
    metrics2.record_turn("greeting", "greeting")
    metrics2.record_turn("spin_situation", "unclear")
    metrics2.record_fallback("tier_1")
    metrics2.record_turn("spin_situation", "unclear")
    metrics2.set_outcome(ConversationOutcome.ABANDONED)
    agg.add(metrics2)

    print(json.dumps(agg.get_summary(), indent=2))

    print("\n" + "=" * 60)
