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
from typing import Callable, Dict, List, Optional, Any, Set
from enum import Enum

from src.context_envelope import ContextEnvelope, ReasonCode
from src.feature_flags import flags
from src.conditions.policy import (
    PolicyContext,
    policy_registry,
)
from src.conditions.trace import EvaluationTrace, Resolution
from src.yaml_config.constants import (
    REPAIR_ACTIONS as _YAML_REPAIR_ACTIONS,
    REPAIR_PROTECTED_ACTIONS,
    PRICING_CORRECT_ACTIONS,
    REPAIR_ACTION_REPEAT_THRESHOLD,
    REPEATABLE_INTENT_GROUPS as _REPEATABLE_INTENT_GROUPS,
    get_escalated_action as _get_escalated_action,
    should_notify_operator as _should_notify_operator,
    notify_operator_stub as _notify_operator_stub,
)


class CascadeDisposition(Enum):
    """Explicit cascade control for PolicyOverride.

    STOP: "I made a decision. Do NOT consult lower-priority overlays." (DEFAULT)
    PASS: "I have no opinion. Continue to lower-priority overlays."
    """
    STOP = "stop"   # Default — safe-by-default
    PASS = "pass"   # Explicit opt-in to cascade continuation


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
    PRICE_QUESTION = "price_question"        # Override для вопроса о цене
    PRICE_ALREADY_CORRECT = "price_already_correct"  # Цена уже правильная
    REPAIR_SKIPPED = "repair_skipped"        # Repair пропущен (action уже отвечает)


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
    cascade_disposition: CascadeDisposition = CascadeDisposition.STOP

    @property
    def has_override(self) -> bool:
        """Есть ли override (action change). Used by bot.py to apply action."""
        return self.action is not None

    @property
    def should_stop_cascade(self) -> bool:
        """Whether this decision halts the priority cascade.
        Action override always stops cascade regardless of disposition."""
        if self.action is not None:
            return True  # Action override always stops
        return self.cascade_disposition == CascadeDisposition.STOP

    def to_dict(self) -> Dict[str, Any]:
        """Сериализовать в словарь."""
        result = {
            "action": self.action,
            "next_state": self.next_state,
            "reason_codes": self.reason_codes,
            "decision": self.decision.value,
            "signals_used": self.signals_used,
            "expected_effect": self.expected_effect,
            "cascade_disposition": self.cascade_disposition.value,
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

    # Mapping action для repair mode (from YAML SSOT)
    REPAIR_ACTIONS = _YAML_REPAIR_ACTIONS

    # Mapping action для возражений
    OBJECTION_ACTIONS = {
        "reframe": "reframe_value",
        "escalate": "handle_repeated_objection",
        "empathize": "empathize_and_redirect",
    }

    @staticmethod
    def _load_addressing_templates() -> Set[str]:
        """Auto-derive repair-protected actions from templates tagged addresses_question: true."""
        from pathlib import Path
        try:
            import yaml
        except ImportError:
            return set()
        base = Path(__file__).parent / "yaml_config" / "templates" / "_base" / "prompts.yaml"
        try:
            with open(base) as f:
                data = yaml.safe_load(f) or {}
            templates = data.get("templates", {})
            return {
                name for name, config in templates.items()
                if isinstance(config, dict) and config.get("addresses_question", False)
            }
        except Exception:
            return set()

    def __init__(self, shadow_mode: bool = False, trace_enabled: bool = False, flow=None):
        """
        Args:
            shadow_mode: Если True, только логируем решения без применения
            trace_enabled: Если True, включить трассировку условий
            flow: Optional FlowConfig for YAML template validation
        """
        self.shadow_mode = shadow_mode
        self.trace_enabled = trace_enabled
        self._flow = flow
        self._decision_history: List[PolicyOverride] = []
        # Merge explicit YAML list + auto-derived from template tags
        self._repair_protected: Set[str] = REPAIR_PROTECTED_ACTIONS | self._load_addressing_templates()
        self._validate_action_templates()

    def _validate_action_templates(self):
        """Cross-check all policy action mappings against available templates (YAML + Python)."""
        from src.config import PROMPT_TEMPLATES

        all_actions = set(self.REPAIR_ACTIONS.values()) | set(self.OBJECTION_ACTIONS.values())
        missing = []
        for a in all_actions:
            in_yaml = self._flow and self._flow.get_template(a)
            in_python = a in PROMPT_TEMPLATES
            if not in_yaml and not in_python:
                missing.append(a)

        if missing:
            from src.logger import logger
            logger.error(
                "POLICY ACTION→TEMPLATE VALIDATION FAILED: actions without templates",
                missing_templates=missing,
                note="These actions will silently fall back to continue_current_goal",
            )

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

        # Guard and StallGuard actions must not be overridden by policy
        if sm_result.get("action") in (
            "stall_guard_eject", "stall_guard_nudge",
            "guard_rephrase", "guard_offer_options",
            "guard_skip_phase", "guard_soft_close",
        ):
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
            # Если есть интервенция гуарда, мы ДОЛЖНЫ остановиться здесь,
            # чтобы не перекрыть её ремонтными экшнами (repair mode),
            # которые могут привести к бесконечному циклу.
            if ctx.guard_intervention:
                if trace:
                    trace.set_result("guard_stop", Resolution.NONE)
                return override

        # 1.5 – 5: Standard cascade — one line per overlay
        override = self._eval_cascade_overlay(override, "is_price_question",
            self._apply_price_question_overlay, ctx, sm_result, trace)
        override = self._eval_cascade_overlay(override, "can_apply_repair",
            self._apply_repair_overlay, ctx, sm_result, trace)
        override = self._eval_cascade_overlay(override, "should_apply_objection_overlay",
            self._apply_objection_overlay, ctx, sm_result, trace)
        override = self._eval_cascade_overlay(override, "in_breakthrough_window",
            self._apply_breakthrough_overlay, ctx, sm_result, trace)
        override = self._eval_cascade_overlay(override, "should_apply_conservative_overlay",
            self._apply_conservative_overlay, ctx, sm_result, trace)

        # Записываем в историю only for actual overrides (NO_OVERRIDE pollutes stats)
        if override and override.has_override:
            if trace:
                override.trace = trace
            self._decision_history.append(override)

            # Shadow mode: возвращаем None но логируем
            if self.shadow_mode:
                from src.logger import logger
                logger.info(
                    "Policy shadow decision",
                    decision=override.decision.value,
                    action=override.action,
                    reason_codes=override.reason_codes,
                )
                return None

        return override

    def _eval_cascade_overlay(
        self,
        override: Optional[PolicyOverride],
        condition_name: str,
        overlay_fn: Callable,
        ctx: PolicyContext,
        sm_result: Dict[str, Any],
        trace: Optional[EvaluationTrace] = None,
    ) -> Optional[PolicyOverride]:
        """Evaluate one overlay in the priority cascade.

        Centralizes cascade logic. Adding a new overlay = one line.
        """
        # Previous overlay stopped cascade — skip
        if override and override.should_stop_cascade:
            return override

        # Condition not met — skip
        if not policy_registry.evaluate(condition_name, ctx, trace):
            return override

        # Evaluate overlay
        result = overlay_fn(ctx, sm_result, trace)

        # None = overlay abstains — keep previous result
        if result is None:
            return override

        return result

    def _handle_guard_intervention(
        self,
        ctx: PolicyContext,
        sm_result: Dict[str, Any],
        trace: Optional[EvaluationTrace] = None
    ) -> Optional[PolicyOverride]:
        """Обработать интервенцию guard."""
        # Guard уже обрабатывается в bot.py, здесь только логируем.
        # Explicit PASS: pre-intervention doesn't block cascade.
        # Actual guard_intervention uses early return at the call site.
        if trace:
            trace.set_result("guard_handled", Resolution.NONE)

        return PolicyOverride(
            action=None,  # Не меняем action, guard сам обработает
            reason_codes=[ReasonCode.GUARD_INTERVENTION.value],
            decision=PolicyDecision.NO_OVERRIDE,
            signals_used={"guard_intervention": ctx.guard_intervention},
            expected_effect="Guard handles intervention",
            cascade_disposition=CascadeDisposition.PASS,
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
        # In handle_objection, yield to objection overlay (p3) when
        # trigger is only repeated_question (not stuck/oscillation which are more severe)
        if (ctx.state == "handle_objection"
                and ctx.repeated_question is not None
                and not ctx.is_stuck
                and not ctx.has_oscillation):
            if trace:
                trace.set_result(None, Resolution.NONE,
                    matched_condition="repair_yields_to_objection_handler")
            return None  # Explicit abstain — let objection overlay handle it

        signals = {}
        action = None
        decision = PolicyDecision.NO_OVERRIDE
        repair_protection_bypassed = False

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
            is_action_repeat_loop = (
                ctx.consecutive_same_action >= REPAIR_ACTION_REPEAT_THRESHOLD
            )
            # If current action already answers the question, protect it
            if ctx.current_action in self._repair_protected and not is_action_repeat_loop:
                if trace:
                    trace.set_result(None, Resolution.NONE,
                        matched_condition="repair_skipped_action_already_correct")
                return PolicyOverride(
                    action=None,
                    decision=PolicyDecision.REPAIR_SKIPPED,
                    signals_used={"repeated_question": ctx.repeated_question,
                                  "action_preserved": ctx.current_action},
                    expected_effect="Action already addresses question, skip repair",
                    # cascade_disposition=STOP (default) — protect from all lower overlays
                )
            elif ctx.current_action in self._repair_protected and is_action_repeat_loop:
                if trace:
                    trace.set_result(
                        None,
                        Resolution.NONE,
                        matched_condition="repair_protection_bypassed_action_repeat",
                    )
                repair_protection_bypassed = True
                signals["repeated_question"] = ctx.repeated_question
                signals["consecutive_same_action"] = ctx.consecutive_same_action
                rq = ctx.repeated_question
                _category = next(
                    (grp for grp, members in _REPEATABLE_INTENT_GROUPS.items()
                     if rq in members),
                    None
                ) if rq else None

                if _category:
                    _attempt_count = ctx.intent_category_attempts.get(_category, 0)
                    action = _get_escalated_action(_category, _attempt_count)
                    # Silent operator notify — client sees nothing, bot keeps talking
                    if _should_notify_operator(_attempt_count):
                        _notify_operator_stub(_category, _attempt_count, ctx.last_user_message or "")
                else:
                    action = self.REPAIR_ACTIONS["repeated_question"]  # answer_with_summary (safe default)
                decision = PolicyDecision.REPAIR_CLARIFY
            # If repeated question is answerable, skip repair
            elif policy_registry.evaluate("is_answerable_question", ctx, trace):
                if trace:
                    trace.set_result(None, Resolution.NONE,
                        matched_condition="repair_yields_to_question_answer")
                return PolicyOverride(
                    action=None,
                    decision=PolicyDecision.REPAIR_SKIPPED,
                    signals_used={
                        "repeated_question": ctx.repeated_question,
                        "reason": "answerable_question_type",
                    },
                    expected_effect="Answerable question — skip repair, let generator handle",
                    cascade_disposition=CascadeDisposition.PASS,
                )
            else:
                signals["repeated_question"] = ctx.repeated_question
                action = self.REPAIR_ACTIONS["repeated_question"]
                decision = PolicyDecision.REPAIR_CLARIFY

        # Mirroring Loop Detection
        elif policy_registry.evaluate("is_mirroring_bot", ctx, trace):
            signals["is_mirroring"] = True
            action = self.REPAIR_ACTIONS["mirroring"]
            decision = PolicyDecision.REPAIR_SUMMARIZE

        # Stall Detection (same state N turns without data progress)
        elif policy_registry.evaluate("is_stalled", ctx, trace):
            signals["is_stalled"] = True
            signals["consecutive_same_state"] = ctx.consecutive_same_state
            action = self.REPAIR_ACTIONS["stall"]
            decision = PolicyDecision.REPAIR_CLARIFY

        if action:
            if trace:
                matched_condition = (
                    "repair_protection_bypassed_action_repeat"
                    if repair_protection_bypassed
                    else "repair"
                )
                trace.set_result(
                    action,
                    Resolution.CONDITION_MATCHED,
                    matched_condition=matched_condition,
                )

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
            "current_intent": ctx.current_intent,
        }

        # Defense-in-depth: objection overlay can only run on eligible objection turns.
        if not policy_registry.evaluate("should_apply_objection_overlay", ctx, trace):
            if trace:
                trace.set_result(
                    None,
                    Resolution.NONE,
                    matched_condition="objection_overlay_not_eligible",
                )
            return None

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
        if current_action in PRICING_CORRECT_ACTIONS:
            if not ctx.guard_intervention:
                # No guard fallback pending — action is correct.
                # Return PRICE_ALREADY_CORRECT with STOP (default) to protect
                # this correct action from lower-priority overlays (repair, etc.)
                if trace:
                    trace.set_result(
                        current_action, Resolution.CONDITION_MATCHED,
                        matched_condition="price_action_already_correct"
                    )
                return PolicyOverride(
                    action=None,  # Don't change action — has_override=False, bot.py won't apply
                    reason_codes=[ReasonCode.POLICY_PRICE_OVERRIDE.value],
                    decision=PolicyDecision.PRICE_ALREADY_CORRECT,
                    signals_used={"intent": ctx.current_intent, "action_approved": current_action},
                    expected_effect="Protect correct price action from lower-priority overlays",
                    # cascade_disposition=STOP (default) — blocks repair, objection, etc.
                )
            # Guard fallback is pending — produce explicit override to clear it in bot.py
            # (preserve the current correct action)
            if trace:
                trace.set_result(
                    current_action, Resolution.CONDITION_MATCHED,
                    matched_condition="price_action_correct_but_guard_pending"
                )
            from src.logger import logger as _logger
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

        # Unified escalation: use intent_category_attempts (not unreliable keyword-count)
        intent_for_lookup = ctx.current_intent or ctx.last_intent or ""
        category = next(
            (grp for grp, members in _REPEATABLE_INTENT_GROUPS.items()
             if intent_for_lookup in members),
            "price_core"  # safe default for price overlay
        )
        attempt_count = ctx.intent_category_attempts.get(category, 0)
        action = _get_escalated_action(category, attempt_count)
        reason = f"price_escalated_attempt_{attempt_count}"

        signals = {
            "intent": ctx.last_intent,
            "original_action": current_action,
            "category": category,
            "attempt_count": attempt_count,
        }
        # Silent operator notify — client sees nothing, bot keeps talking
        if _should_notify_operator(attempt_count):
            _notify_operator_stub(category, attempt_count, ctx.last_user_message or "")

        if trace:
            trace.set_result(
                action,
                Resolution.CONDITION_MATCHED,
                matched_condition="is_price_question"
            )

        from src.logger import logger
        logger.info(
            "Policy: Price question override applied",
            original_action=current_action,
            new_action=action,
            intent=ctx.last_intent,
            attempt_count=attempt_count,
            category=category,
            reason=reason
        )

        return PolicyOverride(
            action=action,
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
