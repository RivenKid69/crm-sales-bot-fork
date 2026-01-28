"""
Dialogue Policy — контекстные оверлеи для выбора action.

Phase 3: Оптимизация SPIN Flow (docs/PLAN_CONTEXT_POLICY.md)
Phase 5: Declarative conditions (ARCHITECTURE_UNIFIED_PLAN.md)

DialoguePolicy добавляет гибкость в поведение бота БЕЗ нарушения
инвариантов state machine. Оверлеи применяются только на
"железобетонных" сигналах:
- has_breakthrough + turns_since_breakthrough
- repeated_objection_types + total_objections
- is_stuck + repeated_question
- most_effective_action / least_effective_action

АНТИ-ПАТТЕРНЫ (запрещены):
- soft_close на основе engagement (noisy signal)
- пропуск SPIN фаз "по momentum"
- hard-branching без стабильных сигналов

Использование:
    from dialogue_policy import DialoguePolicy

    policy = DialoguePolicy()
    override = policy.maybe_override(sm_result, envelope)

    if override:
        action = override["action"]
        reason = override["reason_codes"]
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum

from context_envelope import ContextEnvelope, ReasonCode
from feature_flags import flags
from src.conditions.policy import (
    PolicyContext,
    policy_registry,
)
from src.conditions.trace import EvaluationTrace, Resolution


class PolicyDecision(Enum):
    """Тип решения policy."""
    NO_OVERRIDE = "no_override"              # Оставить action state machine
    REPAIR_CLARIFY = "repair_clarify"        # Перейти в режим уточнения
    REPAIR_CHOICES = "repair_choices"        # Предложить варианты
    REPAIR_SUMMARIZE = "repair_summarize"    # Суммировать понимание
    OBJECTION_REFRAME = "objection_reframe"  # Переформулировать ценность
    OBJECTION_ESCALATE = "objection_escalate"  # Эскалация возражения
    BREAKTHROUGH_CTA = "breakthrough_cta"    # Мягкий CTA после прорыва
    CONSERVATIVE = "conservative"             # Консервативный режим
    PRICE_QUESTION = "price_question"        # НОВОЕ: Override для вопроса о цене


@dataclass
class PolicyOverride:
    """
    Результат policy override.

    Attributes:
        action: Новый action (или None если без изменений)
        next_state: Новый state (или None если сохранить текущий)
        reason_codes: Reason codes объясняющие решение
        decision: Тип решения
        signals_used: Сигналы на которых основано решение
        expected_effect: Ожидаемый эффект
        trace: Evaluation trace for debugging
    """
    action: Optional[str] = None
    next_state: Optional[str] = None
    reason_codes: List[str] = field(default_factory=list)
    decision: PolicyDecision = PolicyDecision.NO_OVERRIDE
    signals_used: Dict[str, Any] = field(default_factory=dict)
    expected_effect: str = ""
    trace: Optional[EvaluationTrace] = None

    @property
    def has_override(self) -> bool:
        """Есть ли override."""
        return self.action is not None

    def to_dict(self) -> Dict[str, Any]:
        """Сериализовать в словарь."""
        result = {
            "action": self.action,
            "next_state": self.next_state,
            "reason_codes": self.reason_codes,
            "decision": self.decision.value,
            "signals_used": self.signals_used,
            "expected_effect": self.expected_effect,
        }
        if self.trace:
            result["trace"] = self.trace.to_dict()
        return result


class DialoguePolicy:
    """
    Контекстные оверлеи для выбора action.

    Принципы:
    1. State machine остаётся source-of-truth
    2. Оверлеи только на стабильных сигналах
    3. Каждое решение объяснимо (reason codes)
    4. Всё контролируется feature flags

    Оверлеи (консервативные):
    1. Repair mode: stuck/repeated_question → clarify/choices
    2. Repeated objection escalation: → reframe_value
    3. Breakthrough window: → soft CTA
    4. Conservative mode: низкая confidence → уточнение

    Usage:
        policy = DialoguePolicy()
        override = policy.maybe_override(sm_result, envelope)
    """

    # Mapping action для repair mode
    REPAIR_ACTIONS = {
        "stuck": "clarify_one_question",
        "oscillation": "summarize_and_clarify",
        "repeated_question": "answer_with_summary",
    }

    # Mapping action для возражений
    OBJECTION_ACTIONS = {
        "reframe": "reframe_value",
        "escalate": "handle_repeated_objection",
        "empathize": "empathize_and_redirect",
    }

    def __init__(self, shadow_mode: bool = False, trace_enabled: bool = False):
        """
        Args:
            shadow_mode: Если True, только логируем решения без применения
            trace_enabled: Если True, включить трассировку условий
        """
        self.shadow_mode = shadow_mode
        self.trace_enabled = trace_enabled
        self._decision_history: List[PolicyOverride] = []

    def maybe_override(
        self,
        sm_result: Dict[str, Any],
        envelope: ContextEnvelope,
    ) -> Optional[PolicyOverride]:
        """
        Проверить нужен ли override action.

        Args:
            sm_result: Результат state machine
            envelope: ContextEnvelope с полным контекстом

        Returns:
            PolicyOverride если нужен override, иначе None
        """
        # Проверяем feature flag
        if not flags.is_enabled("context_policy_overlays"):
            return None

        # Создаём PolicyContext из envelope
        current_action = sm_result.get("action", "")
        ctx = PolicyContext.from_envelope(envelope, current_action=current_action)

        # Создаём trace если включено
        trace = None
        if self.trace_enabled:
            trace = EvaluationTrace(
                rule_name="policy_override",
                intent=envelope.last_intent or "",
                state=envelope.state,
                domain="policy"
            )

        # Проверяем разрешён ли оверлей для текущего состояния
        if policy_registry.evaluate("is_protected_state", ctx, trace):
            return None

        if not policy_registry.evaluate("is_overlay_allowed", ctx, trace):
            return None

        # Проверяем оверлеи в порядке приоритета
        override = None

        # 1. Guard intervention имеет высший приоритет
        if policy_registry.evaluate("has_guard_intervention", ctx, trace):
            override = self._handle_guard_intervention(ctx, sm_result, trace)

        # 1.5 НОВОЕ: Price question override (гарантирует ответ о цене)
        if (not override or not override.has_override) and policy_registry.evaluate("is_price_question", ctx, trace):
            override = self._apply_price_question_overlay(ctx, sm_result, trace)

        # 2. Repair mode (stuck, oscillation, repeated question)
        if (not override or not override.has_override) and policy_registry.evaluate("needs_repair", ctx, trace):
            override = self._apply_repair_overlay(ctx, sm_result, trace)

        # 3. Repeated objection escalation
        if (not override or not override.has_override) and policy_registry.evaluate("has_repeated_objections", ctx, trace):
            override = self._apply_objection_overlay(ctx, sm_result, trace)

        # 4. Breakthrough window CTA
        if (not override or not override.has_override) and policy_registry.evaluate("in_breakthrough_window", ctx, trace):
            override = self._apply_breakthrough_overlay(ctx, sm_result, trace)

        # 5. Conservative mode (низкая confidence + aggressive action)
        if (not override or not override.has_override) and policy_registry.evaluate("should_apply_conservative_overlay", ctx, trace):
            override = self._apply_conservative_overlay(ctx, sm_result, trace)

        # Записываем в историю only for actual overrides (NO_OVERRIDE pollutes stats)
        if override and override.has_override:
            if trace:
                override.trace = trace
            self._decision_history.append(override)

            # Shadow mode: возвращаем None но логируем
            if self.shadow_mode:
                from logger import logger
                logger.info(
                    "Policy shadow decision",
                    decision=override.decision.value,
                    action=override.action,
                    reason_codes=override.reason_codes,
                )
                return None

        return override

    def _handle_guard_intervention(
        self,
        ctx: PolicyContext,
        sm_result: Dict[str, Any],
        trace: Optional[EvaluationTrace] = None
    ) -> Optional[PolicyOverride]:
        """Обработать интервенцию guard."""
        # Guard уже обрабатывается в bot.py, здесь только логируем
        if trace:
            trace.set_result("guard_handled", Resolution.NONE)

        return PolicyOverride(
            action=None,  # Не меняем action, guard сам обработает
            reason_codes=[ReasonCode.GUARD_INTERVENTION.value],
            decision=PolicyDecision.NO_OVERRIDE,
            signals_used={"guard_intervention": ctx.guard_intervention},
            expected_effect="Guard handles intervention",
        )

    def _apply_repair_overlay(
        self,
        ctx: PolicyContext,
        sm_result: Dict[str, Any],
        trace: Optional[EvaluationTrace] = None
    ) -> Optional[PolicyOverride]:
        """
        Применить оверлей для repair mode.

        Триггеры (проверяем через registry):
        - is_stuck: клиент застрял
        - has_oscillation: клиент колеблется
        - has_repeated_question: повторный вопрос

        Actions:
        - clarify_one_question: один конкретный вопрос
        - summarize_and_clarify: суммировать + уточнить
        - answer_with_summary: ответить + краткое резюме
        """
        signals = {}
        action = None
        decision = PolicyDecision.NO_OVERRIDE

        if policy_registry.evaluate("is_stuck", ctx, trace):
            signals["is_stuck"] = True
            signals["unclear_count"] = ctx.unclear_count
            action = self.REPAIR_ACTIONS["stuck"]
            decision = PolicyDecision.REPAIR_CLARIFY

        elif policy_registry.evaluate("has_oscillation", ctx, trace):
            signals["has_oscillation"] = True
            action = self.REPAIR_ACTIONS["oscillation"]
            decision = PolicyDecision.REPAIR_SUMMARIZE

        elif policy_registry.evaluate("has_repeated_question", ctx, trace):
            signals["repeated_question"] = ctx.repeated_question
            action = self.REPAIR_ACTIONS["repeated_question"]
            decision = PolicyDecision.REPAIR_CLARIFY

        if action:
            if trace:
                trace.set_result(action, Resolution.CONDITION_MATCHED, matched_condition="repair")

            return PolicyOverride(
                action=action,
                next_state=None,  # Сохраняем текущий state
                reason_codes=[ReasonCode.POLICY_REPAIR_MODE.value],
                decision=decision,
                signals_used=signals,
                expected_effect="Clarify understanding and recover dialogue",
            )

        return None

    def _apply_objection_overlay(
        self,
        ctx: PolicyContext,
        sm_result: Dict[str, Any],
        trace: Optional[EvaluationTrace] = None
    ) -> Optional[PolicyOverride]:
        """
        Применить оверлей для повторных возражений.

        Триггеры (проверяем через registry):
        - has_repeated_objections: типы повторных возражений
        - total_objections_3_plus: много возражений

        Actions:
        - reframe_value: переформулировать ценность
        - handle_repeated_objection: эскалация тактики
        """
        signals = {
            "repeated_objection_types": ctx.repeated_objection_types,
            "total_objections": ctx.total_objections,
        }

        # Эскалация при достижении лимита возражений (configurable via constants.yaml)
        if policy_registry.evaluate("total_objections_3_plus", ctx, trace):
            if trace:
                trace.set_result(
                    self.OBJECTION_ACTIONS["escalate"],
                    Resolution.CONDITION_MATCHED,
                    matched_condition="total_objections_3_plus"
                )

            return PolicyOverride(
                action=self.OBJECTION_ACTIONS["escalate"],
                next_state=None,
                reason_codes=[
                    ReasonCode.OBJECTION_ESCALATE.value,
                    ReasonCode.OBJECTION_REPEAT.value,
                ],
                decision=PolicyDecision.OBJECTION_ESCALATE,
                signals_used=signals,
                expected_effect="Escalate objection handling, change approach",
            )

        # Reframe при повторных возражениях
        if policy_registry.evaluate("has_repeated_objections", ctx, trace):
            # Проверяем least_effective_action чтобы не повторять
            signals["least_effective_action"] = ctx.least_effective_action

            if trace:
                trace.set_result(
                    self.OBJECTION_ACTIONS["reframe"],
                    Resolution.CONDITION_MATCHED,
                    matched_condition="has_repeated_objections"
                )

            return PolicyOverride(
                action=self.OBJECTION_ACTIONS["reframe"],
                next_state=None,
                reason_codes=[ReasonCode.OBJECTION_REPEAT.value],
                decision=PolicyDecision.OBJECTION_REFRAME,
                signals_used=signals,
                expected_effect="Reframe value proposition, avoid repeating failed approach",
            )

        return None

    def _apply_price_question_overlay(
        self,
        ctx: PolicyContext,
        sm_result: Dict[str, Any],
        trace: Optional[EvaluationTrace] = None
    ) -> Optional[PolicyOverride]:
        """
        НОВОЕ: Применить оверлей для вопросов о цене.

        Триггеры (проверяем через registry):
        - is_price_question: intent = price_question | pricing_details

        Actions:
        - answer_with_pricing: гарантирует ответ о цене

        Этот оверлей гарантирует что вопрос о цене НИКОГДА не игнорируется,
        даже если state machine вернул другой action.
        """
        current_action = ctx.current_action

        # Если action уже правильный — проверяем нет ли pending guard fallback
        if current_action in ("answer_with_pricing", "answer_with_facts", "answer_pricing_details"):
            if not ctx.guard_intervention:
                # No guard fallback pending — action is correct as-is
                if trace:
                    trace.set_result(None, Resolution.NONE, matched_condition="price_action_already_correct")
                return None
            # Guard fallback is pending — produce explicit override to clear it in bot.py
            # (preserve the current correct action)
            if trace:
                trace.set_result(
                    current_action, Resolution.CONDITION_MATCHED,
                    matched_condition="price_action_correct_but_guard_pending"
                )
            from logger import logger as _logger
            _logger.info(
                "Policy: Price action correct but guard fallback pending — explicit override",
                action=current_action,
                guard_intervention=ctx.guard_intervention,
            )
            return PolicyOverride(
                action=current_action,  # Keep the SM's correct action
                reason_codes=[ReasonCode.POLICY_PRICE_OVERRIDE.value],
                decision=PolicyDecision.PRICE_QUESTION,
                signals_used={"intent": ctx.last_intent, "guard_pending": True, "action_preserved": current_action},
                expected_effect="Explicit override to clear guard fallback for price question",
            )

        signals = {
            "intent": ctx.last_intent,
            "original_action": current_action,
        }

        if trace:
            trace.set_result(
                "answer_with_pricing",
                Resolution.CONDITION_MATCHED,
                matched_condition="is_price_question"
            )

        from logger import logger
        logger.info(
            "Policy: Price question override applied",
            original_action=current_action,
            new_action="answer_with_pricing",
            intent=ctx.last_intent
        )

        return PolicyOverride(
            action="answer_with_pricing",
            next_state=None,  # Сохраняем текущий state
            reason_codes=[ReasonCode.POLICY_PRICE_OVERRIDE.value],
            decision=PolicyDecision.PRICE_QUESTION,
            signals_used=signals,
            expected_effect="Answer price question directly instead of deflecting",
        )

    def _apply_breakthrough_overlay(
        self,
        ctx: PolicyContext,
        sm_result: Dict[str, Any],
        trace: Optional[EvaluationTrace] = None
    ) -> Optional[PolicyOverride]:
        """
        Применить оверлей для breakthrough window.

        Триггеры (проверяем через registry):
        - in_breakthrough_window: в окне после прорыва

        Actions:
        - добавить soft CTA (не меняем action, добавляем directive)
        """
        signals = {
            "has_breakthrough": True,
            "turns_since_breakthrough": ctx.turns_since_breakthrough,
            "breakthrough_action": ctx.most_effective_action,
        }

        if trace:
            trace.set_result(None, Resolution.CONDITION_MATCHED, matched_condition="in_breakthrough_window")

        # Не меняем action, но сигнализируем о CTA
        # Реальное добавление CTA происходит через ResponseDirectives
        return PolicyOverride(
            action=None,  # Не меняем action
            next_state=None,
            reason_codes=[
                ReasonCode.BREAKTHROUGH_CTA.value,
                ReasonCode.POLICY_CTA_SOFT.value,
            ],
            decision=PolicyDecision.BREAKTHROUGH_CTA,
            signals_used=signals,
            expected_effect="Add soft CTA, capitalize on breakthrough momentum",
        )

    def _apply_conservative_overlay(
        self,
        ctx: PolicyContext,
        sm_result: Dict[str, Any],
        trace: Optional[EvaluationTrace] = None
    ) -> Optional[PolicyOverride]:
        """
        Применить консервативный оверлей.

        Триггеры (проверяем через registry):
        - should_apply_conservative_overlay: combined condition

        Actions:
        - Более осторожные действия (уточнение вместо прогресса)
        """
        signals = {
            "confidence_trend": ctx.confidence_trend,
            "momentum_direction": ctx.momentum_direction,
            "current_action": ctx.current_action,
        }

        if trace:
            trace.set_result(
                "continue_current_goal",
                Resolution.CONDITION_MATCHED,
                matched_condition="should_apply_conservative_overlay"
            )

        return PolicyOverride(
            action="continue_current_goal",  # Остаёмся на текущем этапе
            next_state=None,
            reason_codes=[ReasonCode.POLICY_CONSERVATIVE.value],
            decision=PolicyDecision.CONSERVATIVE,
            signals_used=signals,
            expected_effect="Stay in current phase, avoid premature advancement",
        )

    def get_decision_history(self) -> List[Dict[str, Any]]:
        """Получить историю решений."""
        return [d.to_dict() for d in self._decision_history]

    def get_override_rate(self) -> float:
        """
        Получить процент оверлеев.

        Returns:
            Доля решений с override (0.0 - 1.0)
        """
        if not self._decision_history:
            return 0.0

        overrides = sum(1 for d in self._decision_history if d.has_override)
        return overrides / len(self._decision_history)

    def get_decision_distribution(self) -> Dict[str, int]:
        """Получить распределение типов решений."""
        distribution: Dict[str, int] = {}
        for d in self._decision_history:
            key = d.decision.value
            distribution[key] = distribution.get(key, 0) + 1
        return distribution

    def reset(self) -> None:
        """Сбросить историю."""
        self._decision_history.clear()


class ContextPolicyMetrics:
    """
    Метрики для context policy.

    Отслеживает:
    - action_override_rate: доля оверлеев
    - reason_code_distribution: распределение по reason codes
    - shadow_mode_stats: статистика shadow mode
    """

    def __init__(self):
        self.reset()

    def reset(self) -> None:
        """Сбросить метрики."""
        self.total_decisions: int = 0
        self.override_count: int = 0
        self.reason_code_counts: Dict[str, int] = {}
        self.decision_type_counts: Dict[str, int] = {}
        self.shadow_decisions: int = 0

    def record_decision(self, override: PolicyOverride, shadow: bool = False) -> None:
        """
        Записать решение policy.

        Args:
            override: PolicyOverride
            shadow: True если shadow mode
        """
        self.total_decisions += 1

        if shadow:
            self.shadow_decisions += 1

        if override.has_override:
            self.override_count += 1

        # Reason codes
        for code in override.reason_codes:
            self.reason_code_counts[code] = \
                self.reason_code_counts.get(code, 0) + 1

        # Decision type
        decision_type = override.decision.value
        self.decision_type_counts[decision_type] = \
            self.decision_type_counts.get(decision_type, 0) + 1

    def get_override_rate(self) -> float:
        """Получить долю оверлеев."""
        if self.total_decisions == 0:
            return 0.0
        return self.override_count / self.total_decisions

    def get_summary(self) -> Dict[str, Any]:
        """Получить сводку метрик."""
        return {
            "total_decisions": self.total_decisions,
            "override_count": self.override_count,
            "override_rate": self.get_override_rate(),
            "shadow_decisions": self.shadow_decisions,
            "reason_code_distribution": self.reason_code_counts,
            "decision_type_distribution": self.decision_type_counts,
        }
