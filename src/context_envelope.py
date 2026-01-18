"""
Context Envelope — единый контракт контекста для всех подсистем.

Phase 0: Инфраструктура (docs/PLAN_CONTEXT_POLICY.md)

ContextEnvelope — это единая точка сбора всего контекста:
- Базовый контекст (state, spin_phase, collected_data)
- Расширенный контекст из ContextWindow (Level 1-3)
- Тон и защитные сигналы (frustration, guard)
- Reason codes для объяснимости решений

Использование:
    envelope = ContextEnvelopeBuilder(
        state_machine=sm,
        context_window=cw,
        tone_info=tone,
        guard_info=guard
    ).build()

    # Использовать для классификатора
    classifier.classify(message, envelope.for_classifier())

    # Использовать для генератора
    generator.generate(action, envelope.for_generator())
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum
import re


class ReasonCode(Enum):
    """
    Reason codes для объяснимости контекстных решений.

    Формат: category.subcategory.detail
    """
    # Repair (Level 1)
    REPAIR_STUCK = "repair.stuck"
    REPAIR_OSCILLATION = "repair.oscillation"
    REPAIR_REPEATED_QUESTION = "repair.repeated_question"
    REPAIR_CONFIDENCE_LOW = "repair.confidence_low"

    # Objection (Level 3)
    OBJECTION_FIRST = "objection.first"
    OBJECTION_REPEAT = "objection.repeat"
    OBJECTION_REPEAT_PRICE = "objection.repeat.price"
    OBJECTION_REPEAT_COMPETITOR = "objection.repeat.competitor"
    OBJECTION_ESCALATE = "objection.escalate"

    # Breakthrough (Level 3)
    BREAKTHROUGH_DETECTED = "breakthrough.detected"
    BREAKTHROUGH_WINDOW = "breakthrough.window"
    BREAKTHROUGH_CTA = "breakthrough.cta"

    # Momentum (Level 2)
    MOMENTUM_POSITIVE = "momentum.positive"
    MOMENTUM_NEGATIVE = "momentum.negative"
    MOMENTUM_NEUTRAL = "momentum.neutral"

    # Engagement (Level 2)
    ENGAGEMENT_HIGH = "engagement.high"
    ENGAGEMENT_LOW = "engagement.low"
    ENGAGEMENT_DECLINING = "engagement.declining"

    # Policy overlays
    POLICY_REPAIR_MODE = "policy.repair_mode"
    POLICY_CONSERVATIVE = "policy.conservative"
    POLICY_ACCELERATE = "policy.accelerate"
    POLICY_CTA_SOFT = "policy.cta_soft"

    # Guard/Fallback
    GUARD_INTERVENTION = "guard.intervention"
    GUARD_FRUSTRATION = "guard.frustration"
    FALLBACK_APPLIED = "fallback.applied"

    # Disambiguation
    DISAMBIGUATION_NEEDED = "disambiguation.needed"
    DISAMBIGUATION_RESOLVED = "disambiguation.resolved"


@dataclass
class ContextEnvelope:
    """
    Единый контракт контекста для всех подсистем.

    Собирает данные из:
    - StateMachine (state, collected_data, spin_phase)
    - ContextWindow (Level 1-3)
    - ToneAnalyzer (tone, frustration)
    - ConversationGuard (intervention signals)

    Attributes:
        # === Базовый контекст ===
        state: Текущее состояние FSM
        spin_phase: Текущая SPIN-фаза
        collected_data: Собранные данные о клиенте
        missing_data: Недостающие данные
        last_action: Последний action бота
        last_intent: Последний интент клиента

        # === Level 1: Sliding Window ===
        intent_history: История интентов (последние N)
        action_history: История actions (последние N)
        objection_count: Количество возражений в окне
        positive_count: Количество позитивных сигналов
        question_count: Количество вопросов
        unclear_count: Количество unclear
        has_oscillation: Обнаружена осцилляция
        is_stuck: Обнаружено застревание
        repeated_question: Повторный вопрос (intent или None)
        confidence_trend: Тренд уверенности
        avg_confidence: Средняя уверенность

        # === Level 2: Structured Context ===
        turn_types: История типов ходов
        momentum: Momentum score (-1 to +1)
        momentum_direction: Направление momentum
        engagement_level: Уровень вовлечённости
        engagement_score: Score вовлечённости
        engagement_trend: Тренд вовлечённости
        funnel_velocity: Скорость по воронке
        is_progressing: Движется ли вперёд
        is_regressing: Откатывается ли назад

        # === Level 3: Episodic Memory ===
        first_objection_type: Тип первого возражения
        total_objections: Общее количество возражений
        repeated_objection_types: Типы повторных возражений
        has_breakthrough: Был ли прорыв
        breakthrough_action: Action приведший к прорыву
        turns_since_breakthrough: Ходов с момента прорыва
        most_effective_action: Самый эффективный action
        least_effective_action: Наименее эффективный action
        client_profile: Профиль клиента

        # === Tone & Guard ===
        tone: Тон клиента
        frustration_level: Уровень фрустрации (0-5)
        should_apologize: Нужно ли извиняться
        should_offer_exit: Предложить ли выход
        guard_intervention: Интервенция guard (или None)

        # === Meta ===
        total_turns: Общее количество ходов
        window_size: Размер окна
        reason_codes: Активные reason codes
    """

    # === Базовый контекст ===
    state: str = "greeting"
    spin_phase: Optional[str] = None
    collected_data: Dict[str, Any] = field(default_factory=dict)
    missing_data: List[str] = field(default_factory=list)
    last_action: Optional[str] = None
    last_intent: Optional[str] = None
    turns_since_last_disambiguation: int = 0
    in_disambiguation: bool = False

    # === Level 1: Sliding Window ===
    intent_history: List[str] = field(default_factory=list)
    action_history: List[str] = field(default_factory=list)
    objection_count: int = 0
    positive_count: int = 0
    question_count: int = 0
    unclear_count: int = 0
    has_oscillation: bool = False
    is_stuck: bool = False
    repeated_question: Optional[str] = None
    confidence_trend: str = "unknown"
    avg_confidence: float = 0.0
    last_confidence: float = 0.0

    # === Level 2: Structured Context ===
    turn_types: List[str] = field(default_factory=list)
    turn_type_counts: Dict[str, int] = field(default_factory=dict)
    momentum: float = 0.0
    momentum_direction: str = "neutral"
    engagement_level: str = "medium"
    engagement_score: float = 0.5
    engagement_trend: str = "stable"
    funnel_velocity: float = 0.0
    funnel_progress: int = 0
    is_progressing: bool = False
    is_regressing: bool = False

    # === Level 3: Episodic Memory ===
    first_objection_type: Optional[str] = None
    first_objection_turn: Optional[int] = None
    total_objections: int = 0
    repeated_objection_types: List[str] = field(default_factory=list)
    objection_types_seen: List[str] = field(default_factory=list)
    has_breakthrough: bool = False
    breakthrough_turn: Optional[int] = None
    breakthrough_action: Optional[str] = None
    turns_since_breakthrough: Optional[int] = None
    most_effective_action: Optional[str] = None
    least_effective_action: Optional[str] = None
    successful_actions: Dict[str, int] = field(default_factory=dict)
    failed_actions: Dict[str, int] = field(default_factory=dict)
    client_has_data: bool = False
    client_company_size: Optional[int] = None
    client_pain_points: List[str] = field(default_factory=list)

    # === Tone & Guard ===
    tone: Optional[str] = None
    frustration_level: int = 0
    should_apologize: bool = False
    should_offer_exit: bool = False
    guard_intervention: Optional[str] = None

    # === Meta ===
    total_turns: int = 0
    window_size: int = 0
    reason_codes: List[str] = field(default_factory=list)

    def add_reason(self, reason: ReasonCode) -> None:
        """Добавить reason code."""
        if reason.value not in self.reason_codes:
            self.reason_codes.append(reason.value)

    def has_reason(self, reason: ReasonCode) -> bool:
        """Проверить есть ли reason code."""
        return reason.value in self.reason_codes

    def get_reasons_by_category(self, category: str) -> List[str]:
        """Получить reason codes по категории."""
        return [r for r in self.reason_codes if r.startswith(category)]

    def for_classifier(self) -> Dict[str, Any]:
        """
        Получить контекст для классификатора.

        Включает все необходимые данные для улучшения классификации.
        """
        return {
            # Базовый контекст
            "state": self.state,
            "spin_phase": self.spin_phase,
            "collected_data": self.collected_data,
            "missing_data": self.missing_data,
            "last_action": self.last_action,
            "last_intent": self.last_intent,
            "turns_since_last_disambiguation": self.turns_since_last_disambiguation,
            "in_disambiguation": self.in_disambiguation,

            # Level 1
            "intent_history": self.intent_history,
            "action_history": self.action_history,
            "objection_count": self.objection_count,
            "positive_count": self.positive_count,
            "question_count": self.question_count,
            "unclear_count": self.unclear_count,
            "has_oscillation": self.has_oscillation,
            "is_stuck": self.is_stuck,
            "repeated_question": self.repeated_question,
            "confidence_trend": self.confidence_trend,

            # Level 2
            "momentum_direction": self.momentum_direction,
            "engagement_level": self.engagement_level,
            "is_progressing": self.is_progressing,
            "is_regressing": self.is_regressing,

            # Level 3 (ключевые сигналы)
            "first_objection_type": self.first_objection_type,
            "total_objections": self.total_objections,
            "repeated_objection_types": self.repeated_objection_types,
            "has_breakthrough": self.has_breakthrough,
            "client_has_data": self.client_has_data,
        }

    def for_generator(self) -> Dict[str, Any]:
        """
        Получить контекст для генератора.

        Включает данные для персонализации и стиля ответа.
        """
        return {
            # Базовый
            "state": self.state,
            "spin_phase": self.spin_phase,
            "collected_data": self.collected_data,
            "missing_data": self.missing_data,

            # Тон и стиль
            "tone": self.tone,
            "frustration_level": self.frustration_level,
            "should_apologize": self.should_apologize,
            "should_offer_exit": self.should_offer_exit,

            # Паттерны для repair
            "is_stuck": self.is_stuck,
            "has_oscillation": self.has_oscillation,
            "repeated_question": self.repeated_question,

            # Episodic memory для персонализации
            "has_breakthrough": self.has_breakthrough,
            "repeated_objection_types": self.repeated_objection_types,
            "client_pain_points": self.client_pain_points,
            "client_company_size": self.client_company_size,

            # Reason codes
            "reason_codes": self.reason_codes,
        }

    def for_policy(self) -> Dict[str, Any]:
        """
        Получить контекст для DialoguePolicy.

        Включает сигналы для принятия решений об action overlays.
        """
        return {
            # Базовый
            "state": self.state,
            "spin_phase": self.spin_phase,
            "last_action": self.last_action,
            "last_intent": self.last_intent,

            # Level 1 сигналы
            "is_stuck": self.is_stuck,
            "has_oscillation": self.has_oscillation,
            "repeated_question": self.repeated_question,
            "confidence_trend": self.confidence_trend,
            "unclear_count": self.unclear_count,

            # Level 2 сигналы
            "momentum": self.momentum,
            "momentum_direction": self.momentum_direction,
            "engagement_level": self.engagement_level,
            "engagement_trend": self.engagement_trend,
            "funnel_velocity": self.funnel_velocity,
            "is_progressing": self.is_progressing,
            "is_regressing": self.is_regressing,

            # Level 3 сигналы (ключевые для policy)
            "total_objections": self.total_objections,
            "repeated_objection_types": self.repeated_objection_types,
            "has_breakthrough": self.has_breakthrough,
            "turns_since_breakthrough": self.turns_since_breakthrough,
            "most_effective_action": self.most_effective_action,
            "least_effective_action": self.least_effective_action,

            # Guard
            "frustration_level": self.frustration_level,
            "guard_intervention": self.guard_intervention,
        }

    def to_dict(self) -> Dict[str, Any]:
        """Сериализовать в словарь."""
        return {
            # === Базовый контекст ===
            "state": self.state,
            "spin_phase": self.spin_phase,
            "collected_data": self.collected_data,
            "missing_data": self.missing_data,
            "last_action": self.last_action,
            "last_intent": self.last_intent,

            # === Level 1 ===
            "intent_history": self.intent_history,
            "action_history": self.action_history,
            "objection_count": self.objection_count,
            "positive_count": self.positive_count,
            "question_count": self.question_count,
            "unclear_count": self.unclear_count,
            "has_oscillation": self.has_oscillation,
            "is_stuck": self.is_stuck,
            "repeated_question": self.repeated_question,
            "confidence_trend": self.confidence_trend,
            "avg_confidence": self.avg_confidence,

            # === Level 2 ===
            "turn_types": self.turn_types,
            "momentum": self.momentum,
            "momentum_direction": self.momentum_direction,
            "engagement_level": self.engagement_level,
            "engagement_score": self.engagement_score,
            "engagement_trend": self.engagement_trend,
            "funnel_velocity": self.funnel_velocity,
            "is_progressing": self.is_progressing,
            "is_regressing": self.is_regressing,

            # === Level 3 ===
            "first_objection_type": self.first_objection_type,
            "total_objections": self.total_objections,
            "repeated_objection_types": self.repeated_objection_types,
            "has_breakthrough": self.has_breakthrough,
            "breakthrough_action": self.breakthrough_action,
            "turns_since_breakthrough": self.turns_since_breakthrough,
            "most_effective_action": self.most_effective_action,
            "least_effective_action": self.least_effective_action,
            "client_pain_points": self.client_pain_points,

            # === Tone & Guard ===
            "tone": self.tone,
            "frustration_level": self.frustration_level,
            "guard_intervention": self.guard_intervention,

            # === Meta ===
            "total_turns": self.total_turns,
            "reason_codes": self.reason_codes,
        }


class ContextEnvelopeBuilder:
    """
    Builder для создания ContextEnvelope.

    Собирает контекст из всех источников и вычисляет reason codes.

    Usage:
        envelope = ContextEnvelopeBuilder(
            state_machine=sm,
            context_window=cw,
            tone_info=tone,
            guard_info=guard
        ).build()
    """

    def __init__(
        self,
        state_machine: Any = None,
        context_window: Any = None,
        tone_info: Optional[Dict] = None,
        guard_info: Optional[Dict] = None,
        last_action: Optional[str] = None,
        last_intent: Optional[str] = None,
        use_v2_engagement: bool = False,
    ):
        """
        Инициализация builder.

        Args:
            state_machine: StateMachine instance
            context_window: ContextWindow instance
            tone_info: Результат ToneAnalyzer
            guard_info: Результат ConversationGuard
            last_action: Последний action
            last_intent: Последний intent
            use_v2_engagement: Использовать улучшенный расчёт engagement
        """
        self.state_machine = state_machine
        self.context_window = context_window
        self.tone_info = tone_info or {}
        self.guard_info = guard_info or {}
        self.last_action = last_action
        self.last_intent = last_intent
        self.use_v2_engagement = use_v2_engagement

    def build(self) -> ContextEnvelope:
        """
        Построить ContextEnvelope.

        Returns:
            Заполненный ContextEnvelope
        """
        envelope = ContextEnvelope()

        # Заполняем из StateMachine
        if self.state_machine:
            self._fill_from_state_machine(envelope)

        # Заполняем из ContextWindow
        if self.context_window:
            self._fill_from_context_window(envelope)

        # Заполняем tone info
        self._fill_tone_info(envelope)

        # Заполняем guard info
        self._fill_guard_info(envelope)

        # Добавляем last_action/intent
        envelope.last_action = self.last_action
        envelope.last_intent = self.last_intent

        # Вычисляем reason codes
        self._compute_reason_codes(envelope)

        return envelope

    def _fill_from_state_machine(self, envelope: ContextEnvelope) -> None:
        """Заполнить данные из StateMachine."""
        from config import SALES_STATES

        sm = self.state_machine
        envelope.state = sm.state
        envelope.collected_data = sm.collected_data.copy()
        envelope.in_disambiguation = getattr(sm, 'in_disambiguation', False)
        envelope.turns_since_last_disambiguation = getattr(
            sm, 'turns_since_last_disambiguation', 0
        )

        # SPIN phase и missing data
        state_config = SALES_STATES.get(sm.state, {})
        envelope.spin_phase = state_config.get("spin_phase")

        required = state_config.get("required_data", [])
        collected = sm.collected_data
        envelope.missing_data = [f for f in required if not collected.get(f)]

        # Phase 4: Fill from IntentTracker if available
        if hasattr(sm, 'intent_tracker'):
            tracker = sm.intent_tracker
            envelope.last_intent = tracker.last_intent
            envelope.total_turns = tracker.turn_number

            # Get intent history from tracker
            envelope.intent_history = tracker.get_recent_intents(5)

            # Get objection stats from tracker
            envelope.total_objections = tracker.objection_total()
            envelope.objection_count = tracker.objection_consecutive()

    def _fill_from_context_window(self, envelope: ContextEnvelope) -> None:
        """Заполнить данные из ContextWindow (Level 1-3)."""
        cw = self.context_window

        # If state_machine not provided, get state from last turn
        if not self.state_machine:
            last_turn = cw.get_last_turn()
            if last_turn:
                # Use next_state as current state (after the turn was processed)
                envelope.state = last_turn.next_state or last_turn.state
                envelope.last_action = last_turn.action
                envelope.last_intent = last_turn.intent

        # === Level 1: Sliding Window ===
        # NOTE: intent_history, objection_count, total_objections may already be set
        # from IntentTracker (state_machine). IntentTracker is the authoritative source
        # when available, so we only fill from context_window if not already set.
        if not envelope.intent_history:
            envelope.intent_history = cw.get_intent_history()
        envelope.action_history = cw.get_action_history()
        if envelope.objection_count == 0:
            envelope.objection_count = cw.get_objection_count()
        envelope.positive_count = cw.get_positive_count()
        envelope.question_count = cw.get_question_count()
        envelope.unclear_count = cw.get_unclear_count()
        envelope.has_oscillation = cw.detect_oscillation()
        envelope.is_stuck = cw.detect_stuck_pattern()
        envelope.repeated_question = cw.detect_repeated_question()
        envelope.confidence_trend = cw.get_confidence_trend()
        envelope.avg_confidence = cw.get_average_confidence()
        envelope.window_size = len(cw)

        last_turn = cw.get_last_turn()
        if last_turn:
            envelope.last_confidence = last_turn.confidence

        # === Level 2: Structured Context ===
        # Используем v2 engagement если указано
        level2 = cw.get_structured_context(use_v2_engagement=self.use_v2_engagement)
        envelope.turn_types = level2.get("turn_types", [])
        envelope.turn_type_counts = level2.get("turn_type_counts", {})
        envelope.momentum = cw.get_momentum()
        envelope.momentum_direction = level2.get("momentum_direction", "neutral")
        envelope.engagement_level = level2.get("engagement_level", "medium")
        envelope.engagement_score = level2.get("engagement_score", 0.5)
        envelope.engagement_trend = level2.get("engagement_trend", "stable")
        envelope.funnel_velocity = level2.get("funnel_velocity", 0.0)
        envelope.funnel_progress = level2.get("funnel_progress", 0)
        envelope.is_progressing = level2.get("is_progressing", False)
        envelope.is_regressing = level2.get("is_regressing", False)

        # === Level 3: Episodic Memory ===
        level3 = cw.get_episodic_context()
        envelope.first_objection_type = level3.get("first_objection_type")
        envelope.first_objection_turn = level3.get("first_objection_turn")
        # total_objections: prefer IntentTracker value if already set
        if envelope.total_objections == 0:
            envelope.total_objections = level3.get("total_objections", 0)
        envelope.repeated_objection_types = level3.get("repeated_objection_types", [])
        envelope.objection_types_seen = level3.get("objection_types_seen", [])
        envelope.has_breakthrough = level3.get("has_breakthrough", False)
        envelope.breakthrough_turn = level3.get("breakthrough_turn")
        envelope.breakthrough_action = level3.get("breakthrough_action")
        envelope.most_effective_action = level3.get("most_effective_action")
        envelope.least_effective_action = level3.get("least_effective_action")
        envelope.successful_actions = level3.get("successful_actions", {})
        envelope.failed_actions = level3.get("failed_actions", {})
        envelope.client_has_data = level3.get("client_has_data", False)
        envelope.client_company_size = level3.get("client_company_size")
        envelope.client_pain_points = level3.get("client_pain_points", [])
        envelope.total_turns = level3.get("total_turns", 0)

        # Вычисляем turns_since_breakthrough
        if envelope.has_breakthrough and envelope.breakthrough_turn:
            envelope.turns_since_breakthrough = (
                envelope.total_turns - envelope.breakthrough_turn
            )

    def _fill_tone_info(self, envelope: ContextEnvelope) -> None:
        """Заполнить информацию о тоне."""
        envelope.tone = self.tone_info.get("tone")
        envelope.frustration_level = self.tone_info.get("frustration_level", 0)
        envelope.should_apologize = self.tone_info.get("should_apologize", False)
        envelope.should_offer_exit = self.tone_info.get("should_offer_exit", False)

    def _fill_guard_info(self, envelope: ContextEnvelope) -> None:
        """Заполнить информацию от guard."""
        envelope.guard_intervention = self.guard_info.get("intervention")

    def _compute_reason_codes(self, envelope: ContextEnvelope) -> None:
        """Вычислить reason codes на основе сигналов."""

        # === Repair signals (Level 1) ===
        if envelope.is_stuck:
            envelope.add_reason(ReasonCode.REPAIR_STUCK)

        if envelope.has_oscillation:
            envelope.add_reason(ReasonCode.REPAIR_OSCILLATION)

        if envelope.repeated_question:
            envelope.add_reason(ReasonCode.REPAIR_REPEATED_QUESTION)

        if envelope.confidence_trend == "decreasing":
            envelope.add_reason(ReasonCode.REPAIR_CONFIDENCE_LOW)

        # === Momentum signals (Level 2) ===
        if envelope.momentum_direction == "positive":
            envelope.add_reason(ReasonCode.MOMENTUM_POSITIVE)
        elif envelope.momentum_direction == "negative":
            envelope.add_reason(ReasonCode.MOMENTUM_NEGATIVE)
        else:
            envelope.add_reason(ReasonCode.MOMENTUM_NEUTRAL)

        # === Engagement signals (Level 2) ===
        if envelope.engagement_level == "high":
            envelope.add_reason(ReasonCode.ENGAGEMENT_HIGH)
        elif envelope.engagement_level in ("low", "disengaged"):
            envelope.add_reason(ReasonCode.ENGAGEMENT_LOW)

        if envelope.engagement_trend == "declining":
            envelope.add_reason(ReasonCode.ENGAGEMENT_DECLINING)

        # === Objection signals (Level 3) ===
        if envelope.first_objection_type and envelope.total_objections == 1:
            envelope.add_reason(ReasonCode.OBJECTION_FIRST)

        if envelope.repeated_objection_types:
            envelope.add_reason(ReasonCode.OBJECTION_REPEAT)

            # Специфичные типы повторных возражений
            for obj_type in envelope.repeated_objection_types:
                if "price" in obj_type:
                    envelope.add_reason(ReasonCode.OBJECTION_REPEAT_PRICE)
                elif "competitor" in obj_type:
                    envelope.add_reason(ReasonCode.OBJECTION_REPEAT_COMPETITOR)

        if envelope.total_objections >= 3:
            envelope.add_reason(ReasonCode.OBJECTION_ESCALATE)

        # === Breakthrough signals (Level 3) ===
        if envelope.has_breakthrough:
            envelope.add_reason(ReasonCode.BREAKTHROUGH_DETECTED)

            # Окно для CTA (1-3 хода после breakthrough)
            if envelope.turns_since_breakthrough is not None:
                if 1 <= envelope.turns_since_breakthrough <= 3:
                    envelope.add_reason(ReasonCode.BREAKTHROUGH_WINDOW)
                    envelope.add_reason(ReasonCode.BREAKTHROUGH_CTA)

        # === Guard signals ===
        if envelope.guard_intervention:
            envelope.add_reason(ReasonCode.GUARD_INTERVENTION)

        if envelope.frustration_level >= 3:
            envelope.add_reason(ReasonCode.GUARD_FRUSTRATION)

        # === Policy signals (derived) ===
        # Repair mode: stuck OR oscillation OR repeated question
        if (envelope.is_stuck or envelope.has_oscillation or
            envelope.repeated_question):
            envelope.add_reason(ReasonCode.POLICY_REPAIR_MODE)

        # Conservative mode: низкая confidence OR негативный momentum
        if (envelope.confidence_trend == "decreasing" or
            envelope.momentum_direction == "negative"):
            envelope.add_reason(ReasonCode.POLICY_CONSERVATIVE)

        # Accelerate: позитивный momentum AND прогресс
        if (envelope.momentum_direction == "positive" and
            envelope.is_progressing):
            envelope.add_reason(ReasonCode.POLICY_ACCELERATE)


class PIIRedactor:
    """
    Редактор для удаления PII из контекста.

    Phase 1: Защита и надёжность

    Маскирует:
    - Телефоны
    - Email
    - ФИО (при наличии паттернов)

    Usage:
        redactor = PIIRedactor()
        safe_data = redactor.redact(collected_data)
        safe_summary = redactor.redact_text(summary_text)
    """

    # Паттерны для PII
    PHONE_PATTERN = re.compile(
        r'(\+7|8)?[\s\-]?\(?[0-9]{3}\)?[\s\-]?[0-9]{3}[\s\-]?[0-9]{2}[\s\-]?[0-9]{2}'
    )
    EMAIL_PATTERN = re.compile(
        r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    )
    # Простой паттерн для ФИО (Имя Фамилия или Фамилия Имя Отчество)
    NAME_PATTERN = re.compile(
        r'\b[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё]+)?\b'
    )

    # Ключи данных которые содержат PII
    PII_KEYS = {
        "phone", "contact_phone", "phone_number", "mobile",
        "email", "contact_email", "email_address",
        "contact_name", "name", "full_name", "fio",
    }

    def __init__(self, mask_char: str = "*"):
        """
        Args:
            mask_char: Символ для маскирования
        """
        self.mask_char = mask_char

    def redact(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Редактировать PII из словаря данных.

        Args:
            data: Словарь с данными

        Returns:
            Копия словаря с замаскированными PII
        """
        if not data:
            return {}

        result = {}
        for key, value in data.items():
            if key.lower() in self.PII_KEYS:
                # Маскируем значение
                if isinstance(value, str) and value:
                    result[key] = self._mask_value(value)
                else:
                    result[key] = "[REDACTED]"
            elif isinstance(value, str):
                # Проверяем на PII в тексте
                result[key] = self.redact_text(value)
            elif isinstance(value, dict):
                # Рекурсивно обрабатываем вложенные словари
                result[key] = self.redact(value)
            elif isinstance(value, list):
                # Обрабатываем списки
                result[key] = [
                    self.redact_text(v) if isinstance(v, str) else v
                    for v in value
                ]
            else:
                result[key] = value

        return result

    def redact_text(self, text: str) -> str:
        """
        Редактировать PII из текста.

        Args:
            text: Текст для редактирования

        Returns:
            Текст с замаскированными PII
        """
        if not text:
            return text

        result = text

        # Маскируем телефоны
        result = self.PHONE_PATTERN.sub("[PHONE]", result)

        # Маскируем email
        result = self.EMAIL_PATTERN.sub("[EMAIL]", result)

        return result

    def _mask_value(self, value: str) -> str:
        """Замаскировать значение, оставив часть видимой."""
        if not value:
            return "[REDACTED]"

        if len(value) <= 4:
            return self.mask_char * len(value)

        # Показываем первые 2 и последние 2 символа
        visible_start = 2
        visible_end = 2
        mask_len = len(value) - visible_start - visible_end

        return (
            value[:visible_start] +
            self.mask_char * mask_len +
            value[-visible_end:]
        )

    def is_pii_key(self, key: str) -> bool:
        """Проверить является ли ключ PII."""
        return key.lower() in self.PII_KEYS


# Singleton instance
pii_redactor = PIIRedactor()


def build_context_envelope(
    state_machine: Any = None,
    context_window: Any = None,
    tone_info: Optional[Dict] = None,
    guard_info: Optional[Dict] = None,
    last_action: Optional[str] = None,
    last_intent: Optional[str] = None,
    use_v2_engagement: bool = False,
) -> ContextEnvelope:
    """
    Удобная функция для создания ContextEnvelope.

    Args:
        state_machine: StateMachine instance
        context_window: ContextWindow instance
        tone_info: Результат ToneAnalyzer
        guard_info: Результат ConversationGuard
        last_action: Последний action
        last_intent: Последний intent
        use_v2_engagement: Использовать улучшенный расчёт engagement

    Returns:
        ContextEnvelope
    """
    return ContextEnvelopeBuilder(
        state_machine=state_machine,
        context_window=context_window,
        tone_info=tone_info,
        guard_info=guard_info,
        last_action=last_action,
        last_intent=last_intent,
        use_v2_engagement=use_v2_engagement,
    ).build()
