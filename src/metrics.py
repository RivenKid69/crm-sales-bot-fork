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
# Disambiguation Metrics
# =============================================================================

class DisambiguationMetrics:
    """
    Метрики для отслеживания эффективности disambiguation.

    Собирает:
    - Количество срабатываний
    - Успешность разрешения
    - Количество попыток
    - Распределение по интентам
    """

    def __init__(self):
        self.reset()

    def reset(self) -> None:
        """Сбросить все метрики."""
        self.total_disambiguations: int = 0
        self.resolved_on_first_try: int = 0
        self.resolved_on_second_try: int = 0
        self.fallback_to_unclear: int = 0
        self.user_provided_new_info: int = 0

        self.disambiguation_by_intent: Dict[str, int] = {}
        self.resolution_by_intent: Dict[str, Dict[str, int]] = {}
        self.score_gaps: List[float] = []

    def record_disambiguation(self, options: List[str], scores: Dict) -> None:
        """
        Записать срабатывание disambiguation.

        Args:
            options: Список интентов в опциях
            scores: Merged scores всех интентов
        """
        self.total_disambiguations += 1

        # Записываем score gap
        sorted_scores = sorted(scores.values(), reverse=True)
        if len(sorted_scores) >= 2:
            gap = sorted_scores[0] - sorted_scores[1]
            self.score_gaps.append(gap)

        # Записываем какие интенты были в disambiguation
        for intent in options:
            self.disambiguation_by_intent[intent] = \
                self.disambiguation_by_intent.get(intent, 0) + 1

    def record_resolution(
        self,
        resolved_intent: str,
        attempt: int,
        success: bool
    ) -> None:
        """
        Записать разрешение disambiguation.

        Args:
            resolved_intent: Выбранный интент
            attempt: Номер попытки (1 или 2)
            success: Успешно ли разрешён
        """
        if success:
            if attempt == 1:
                self.resolved_on_first_try += 1
            else:
                self.resolved_on_second_try += 1
        else:
            self.fallback_to_unclear += 1

        # Записываем статистику по интентам
        if resolved_intent not in self.resolution_by_intent:
            self.resolution_by_intent[resolved_intent] = {"resolved": 0, "failed": 0}

        key = "resolved" if success else "failed"
        self.resolution_by_intent[resolved_intent][key] += 1

    def get_effectiveness_rate(self) -> float:
        """
        Получить процент успешных disambiguation.

        Returns:
            Процент (0.0 - 1.0)
        """
        if self.total_disambiguations == 0:
            return 0.0
        resolved = self.resolved_on_first_try + self.resolved_on_second_try
        return resolved / self.total_disambiguations

    def get_first_try_rate(self) -> float:
        """Получить процент разрешения с первой попытки."""
        if self.total_disambiguations == 0:
            return 0.0
        return self.resolved_on_first_try / self.total_disambiguations

    def get_fallback_rate(self) -> float:
        """Получить процент fallback в unclear."""
        if self.total_disambiguations == 0:
            return 0.0
        return self.fallback_to_unclear / self.total_disambiguations

    def get_average_score_gap(self) -> float:
        """Получить средний score gap при disambiguation."""
        if not self.score_gaps:
            return 0.0
        return sum(self.score_gaps) / len(self.score_gaps)

    def to_log_dict(self) -> Dict:
        """
        Получить словарь для логирования.

        Returns:
            Словарь с ключевыми метриками
        """
        return {
            "total_disambiguations": self.total_disambiguations,
            "effectiveness_rate": self.get_effectiveness_rate(),
            "first_try_rate": self.get_first_try_rate(),
            "fallback_rate": self.get_fallback_rate(),
            "avg_score_gap": self.get_average_score_gap(),
        }

    def get_summary(self) -> Dict:
        """
        Получить полную сводку метрик.

        Returns:
            Словарь со всеми метриками
        """
        return {
            "total_disambiguations": self.total_disambiguations,
            "resolved_on_first_try": self.resolved_on_first_try,
            "resolved_on_second_try": self.resolved_on_second_try,
            "fallback_to_unclear": self.fallback_to_unclear,
            "effectiveness_rate": self.get_effectiveness_rate(),
            "first_try_rate": self.get_first_try_rate(),
            "fallback_rate": self.get_fallback_rate(),
            "avg_score_gap": self.get_average_score_gap(),
            "disambiguation_by_intent": self.disambiguation_by_intent,
            "resolution_by_intent": self.resolution_by_intent,
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


@dataclass
class FallbackMetrics:
    """Metrics for tracking taxonomy fallback usage.

    This class tracks how often taxonomy-based intelligent fallback is used
    and at what level (category, super_category, domain, default).

    The goal is to minimize DEFAULT_ACTION fallback usage (<1%) while
    category/domain fallback should be 40-60% (intelligent fallback working).

    Attributes:
        total_fallbacks: Total number of fallback resolutions
        fallback_by_intent: Count per intent that triggered fallback
        fallback_by_level: Count per fallback level (exact, category, super_category, domain, default)
        fallback_by_action: Count per fallback action used
        default_fallback_intents: List of intents that hit DEFAULT_ACTION (should be empty)
    """
    total_fallbacks: int = 0
    fallback_by_intent: Dict[str, int] = field(default_factory=dict)
    fallback_by_level: Dict[str, int] = field(default_factory=dict)
    fallback_by_action: Dict[str, int] = field(default_factory=dict)
    default_fallback_intents: List[str] = field(default_factory=list)

    def record_fallback(
        self,
        intent: str,
        level: str,
        action: str
    ) -> None:
        """Record a fallback resolution.

        Args:
            intent: The intent that triggered fallback
            level: Fallback level (exact, category, super_category, domain, default)
            action: The fallback action used
        """
        self.total_fallbacks += 1
        self.fallback_by_intent[intent] = self.fallback_by_intent.get(intent, 0) + 1
        self.fallback_by_level[level] = self.fallback_by_level.get(level, 0) + 1
        self.fallback_by_action[action] = self.fallback_by_action.get(action, 0) + 1

        # Track DEFAULT_ACTION fallback (should never happen with proper taxonomy)
        if level == "default":
            self.default_fallback_intents.append(intent)
            import structlog
            logger = structlog.get_logger(__name__)
            logger.error(
                "DEFAULT_ACTION fallback triggered",
                intent=intent,
                action=action,
                total_default_fallbacks=len(self.default_fallback_intents)
            )

    def get_fallback_rate_by_level(self) -> Dict[str, float]:
        """Get fallback rate percentage by level.

        Returns:
            Dict with level -> percentage
        """
        if self.total_fallbacks == 0:
            return {}

        return {
            level: (count / self.total_fallbacks) * 100
            for level, count in self.fallback_by_level.items()
        }

    def get_default_fallback_rate(self) -> float:
        """Get DEFAULT_ACTION fallback rate (target: <1%).

        Returns:
            Percentage of fallbacks that hit DEFAULT_ACTION
        """
        if self.total_fallbacks == 0:
            return 0.0

        default_count = self.fallback_by_level.get("default", 0)
        return (default_count / self.total_fallbacks) * 100

    def get_intelligent_fallback_rate(self) -> float:
        """Get intelligent fallback rate (category/domain, target: 40-60%).

        Returns:
            Percentage of fallbacks using category or domain fallback
        """
        if self.total_fallbacks == 0:
            return 0.0

        intelligent_count = (
            self.fallback_by_level.get("category", 0) +
            self.fallback_by_level.get("domain", 0)
        )
        return (intelligent_count / self.total_fallbacks) * 100

    def get_summary(self) -> Dict[str, Any]:
        """Get fallback metrics summary.

        Returns:
            Dict with summary statistics
        """
        return {
            "total_fallbacks": self.total_fallbacks,
            "default_fallback_rate": self.get_default_fallback_rate(),
            "intelligent_fallback_rate": self.get_intelligent_fallback_rate(),
            "fallback_by_level": self.fallback_by_level,
            "fallback_rate_by_level": self.get_fallback_rate_by_level(),
            "fallback_by_action": self.fallback_by_action,
            "default_fallback_intents": self.default_fallback_intents,
            "top_fallback_intents": sorted(
                self.fallback_by_intent.items(),
                key=lambda x: x[1],
                reverse=True
            )[:10]
        }

    def check_health(self) -> Dict[str, Any]:
        """Check if fallback metrics are healthy (meeting targets).

        Targets:
        - DEFAULT_ACTION fallback < 1%
        - Intelligent fallback 40-60%

        Returns:
            Dict with health status and issues
        """
        issues = []
        default_rate = self.get_default_fallback_rate()
        intelligent_rate = self.get_intelligent_fallback_rate()

        # Check DEFAULT_ACTION usage
        if default_rate > 1.0:
            issues.append({
                "severity": "critical",
                "type": "high_default_fallback",
                "message": f"DEFAULT_ACTION fallback rate {default_rate:.1f}% exceeds target (<1%)",
                "intents": self.default_fallback_intents
            })

        # Check intelligent fallback usage
        if intelligent_rate < 40.0:
            issues.append({
                "severity": "warning",
                "type": "low_intelligent_fallback",
                "message": f"Intelligent fallback rate {intelligent_rate:.1f}% below target (40-60%)",
            })
        elif intelligent_rate > 60.0:
            issues.append({
                "severity": "info",
                "type": "high_intelligent_fallback",
                "message": f"Intelligent fallback rate {intelligent_rate:.1f}% above target (40-60%)",
            })

        is_healthy = len([i for i in issues if i["severity"] == "critical"]) == 0

        return {
            "is_healthy": is_healthy,
            "default_fallback_rate": default_rate,
            "intelligent_fallback_rate": intelligent_rate,
            "issues": issues
        }


# =============================================================================
# Secondary Intent Detection Metrics
# =============================================================================

class SecondaryIntentMetrics:
    """Monitor secondary intent detection effectiveness.

    Tracks detection rates, misses, and alerts when fact keywords
    are present but not detected. This helps identify gaps in
    secondary intent patterns.

    Usage:
        from metrics import SecondaryIntentMetrics

        SecondaryIntentMetrics.record_detection(
            message="100 человек. Как насчёт SSL?",
            primary_intent="info_provided",
            secondary_intents=["question_security"],
        )
    """

    # Keywords that should trigger fact question detection
    FACT_KEYWORDS = {
        "ssl", "tls", "api", "webhook",
        "безопасность", "аудит", "шифрование",
        "интеграция", "настройка", "документация",
    }

    _detections: List[Dict[str, Any]] = []
    _misses: List[Dict[str, Any]] = []

    @classmethod
    def record_detection(
        cls,
        message: str,
        primary_intent: str,
        secondary_intents: List[str],
        expected_intents: Optional[List[str]] = None
    ) -> None:
        """
        Record secondary intent detection for monitoring.

        Args:
            message: User message
            primary_intent: Primary intent from classifier
            secondary_intents: Detected secondary intents
            expected_intents: Expected intents (for testing/validation)
        """
        import structlog
        logger = structlog.get_logger(__name__)

        # Check if fact keywords present but not detected
        message_lower = message.lower()
        has_fact_keyword = any(kw in message_lower for kw in cls.FACT_KEYWORDS)
        has_fact_intent = any("question_" in i for i in secondary_intents)

        record = {
            "message": message[:100],
            "primary_intent": primary_intent,
            "secondary_intents": secondary_intents,
            "has_fact_keyword": has_fact_keyword,
            "has_fact_intent": has_fact_intent,
            "detected_keywords": [kw for kw in cls.FACT_KEYWORDS if kw in message_lower],
        }

        if has_fact_keyword and not has_fact_intent:
            # Detection miss - alert
            cls._misses.append(record)
            logger.warning(
                "Secondary intent detection miss: fact keyword present but not detected",
                message=message[:50],
                primary_intent=primary_intent,
                secondary_intents=secondary_intents,
                detected_keywords=record["detected_keywords"],
                alert="secondary_intent_miss"
            )
        else:
            cls._detections.append(record)

    @classmethod
    def get_detection_rate(cls) -> float:
        """Get detection success rate.

        Returns:
            Percentage of messages where fact keywords were correctly detected
        """
        total = len(cls._detections) + len(cls._misses)
        if total == 0:
            return 100.0
        return (len(cls._detections) / total) * 100

    @classmethod
    def get_miss_rate(cls) -> float:
        """Get detection miss rate (should be <5%).

        Returns:
            Percentage of messages with fact keywords that weren't detected
        """
        total = len(cls._detections) + len(cls._misses)
        if total == 0:
            return 0.0
        return (len(cls._misses) / total) * 100

    @classmethod
    def get_summary(cls) -> Dict[str, Any]:
        """Get summary of detection metrics.

        Returns:
            Dict with detection statistics
        """
        return {
            "total_detections": len(cls._detections),
            "total_misses": len(cls._misses),
            "detection_rate": cls.get_detection_rate(),
            "miss_rate": cls.get_miss_rate(),
            "recent_misses": cls._misses[-10:],  # Last 10 misses for debugging
            "missed_keywords": cls._get_missed_keyword_stats(),
        }

    @classmethod
    def _get_missed_keyword_stats(cls) -> Dict[str, int]:
        """Get statistics on which keywords are most commonly missed."""
        from collections import Counter
        all_missed_keywords = []
        for miss in cls._misses:
            all_missed_keywords.extend(miss.get("detected_keywords", []))
        return dict(Counter(all_missed_keywords).most_common(10))

    @classmethod
    def reset(cls) -> None:
        """Reset all metrics (for testing)."""
        cls._detections = []
        cls._misses = []


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
