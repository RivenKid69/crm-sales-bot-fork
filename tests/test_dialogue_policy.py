"""
Тесты для DialoguePolicy и ContextPolicyMetrics.

Phase 3 из PLAN_CONTEXT_POLICY.md:
- DialoguePolicy: контекстные оверлеи для action
- PolicyOverride: результат решения policy
- ContextPolicyMetrics: метрики policy decisions
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from dialogue_policy import (
    DialoguePolicy,
    PolicyDecision,
    PolicyOverride,
    ContextPolicyMetrics,
)
from context_envelope import ContextEnvelope, ReasonCode
from feature_flags import flags


class TestPolicyDecision:
    """Тесты для PolicyDecision enum."""

    def test_policy_decision_values(self):
        """Проверить значения типов решений."""
        assert PolicyDecision.NO_OVERRIDE.value == "no_override"
        assert PolicyDecision.REPAIR_CLARIFY.value == "repair_clarify"
        assert PolicyDecision.REPAIR_CHOICES.value == "repair_choices"
        assert PolicyDecision.REPAIR_SUMMARIZE.value == "repair_summarize"
        assert PolicyDecision.OBJECTION_REFRAME.value == "objection_reframe"
        assert PolicyDecision.OBJECTION_ESCALATE.value == "objection_escalate"
        assert PolicyDecision.BREAKTHROUGH_CTA.value == "breakthrough_cta"
        assert PolicyDecision.CONSERVATIVE.value == "conservative"


class TestPolicyOverride:
    """Тесты для PolicyOverride dataclass."""

    def test_default_values(self):
        """Проверить default значения."""
        override = PolicyOverride()

        assert override.action is None
        assert override.next_state is None
        assert override.reason_codes == []
        assert override.decision == PolicyDecision.NO_OVERRIDE
        assert override.signals_used == {}
        assert override.expected_effect == ""

    def test_has_override_false(self):
        """Проверить has_override когда нет override."""
        override = PolicyOverride()
        assert override.has_override is False

    def test_has_override_true(self):
        """Проверить has_override когда есть override."""
        override = PolicyOverride(action="clarify_one_question")
        assert override.has_override is True

    def test_to_dict(self):
        """Проверить сериализацию."""
        override = PolicyOverride(
            action="reframe_value",
            decision=PolicyDecision.OBJECTION_REFRAME,
            reason_codes=["objection.repeat"],
            signals_used={"total_objections": 2},
            expected_effect="Reframe value",
        )

        d = override.to_dict()

        assert d["action"] == "reframe_value"
        assert d["decision"] == "objection_reframe"
        assert d["reason_codes"] == ["objection.repeat"]
        assert d["signals_used"] == {"total_objections": 2}


class TestDialoguePolicy:
    """Тесты для DialoguePolicy."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Включить feature flag для policy."""
        flags.set_override("context_policy_overlays", True)
        yield
        flags.clear_override("context_policy_overlays")

    def test_init_default(self):
        """Проверить инициализацию по умолчанию."""
        policy = DialoguePolicy()

        assert policy.shadow_mode is False
        assert policy._decision_history == []

    def test_init_shadow_mode(self):
        """Проверить инициализацию в shadow mode."""
        policy = DialoguePolicy(shadow_mode=True)
        assert policy.shadow_mode is True

    def test_maybe_override_disabled(self):
        """Проверить что overlay отключён без feature flag."""
        flags.set_override("context_policy_overlays", False)

        policy = DialoguePolicy()
        envelope = ContextEnvelope(is_stuck=True)
        sm_result = {"next_state": "spin_situation", "action": "continue"}

        result = policy.maybe_override(sm_result, envelope)

        assert result is None

    def test_maybe_override_protected_state(self):
        """Проверить что protected states не получают overlay."""
        policy = DialoguePolicy()

        # Greeting state is protected
        envelope = ContextEnvelope(
            state="greeting",
            is_stuck=True,
        )
        sm_result = {"next_state": "greeting", "action": "greet"}

        result = policy.maybe_override(sm_result, envelope)

        assert result is None

        # Close state is protected
        envelope2 = ContextEnvelope(state="close")
        sm_result2 = {"next_state": "close", "action": "close"}

        result2 = policy.maybe_override(sm_result2, envelope2)

        assert result2 is None

    def test_repair_overlay_stuck(self):
        """Проверить repair overlay при stuck."""
        policy = DialoguePolicy()

        envelope = ContextEnvelope(
            state="spin_situation",
            is_stuck=True,
            reason_codes=[ReasonCode.POLICY_REPAIR_MODE.value],
        )
        sm_result = {"next_state": "spin_situation", "action": "ask_company_size"}

        result = policy.maybe_override(sm_result, envelope)

        assert result is not None
        assert result.action == "clarify_one_question"
        assert result.decision == PolicyDecision.REPAIR_CLARIFY
        assert "is_stuck" in result.signals_used

    def test_repair_overlay_oscillation(self):
        """Проверить repair overlay при oscillation."""
        policy = DialoguePolicy()

        envelope = ContextEnvelope(
            state="spin_problem",
            has_oscillation=True,
            reason_codes=[ReasonCode.POLICY_REPAIR_MODE.value],
        )
        sm_result = {"next_state": "spin_problem", "action": "ask_pain"}

        result = policy.maybe_override(sm_result, envelope)

        assert result is not None
        assert result.action == "summarize_and_clarify"
        assert result.decision == PolicyDecision.REPAIR_SUMMARIZE

    def test_repair_overlay_repeated_question(self):
        """Проверить repair overlay при repeated question."""
        policy = DialoguePolicy()

        envelope = ContextEnvelope(
            state="spin_situation",
            repeated_question="question_price",
            reason_codes=[ReasonCode.POLICY_REPAIR_MODE.value],
        )
        sm_result = {"next_state": "spin_situation", "action": "continue"}

        result = policy.maybe_override(sm_result, envelope)

        assert result is not None
        assert result.action == "answer_with_summary"
        assert result.decision == PolicyDecision.REPAIR_CLARIFY

    def test_objection_overlay_escalate(self):
        """Проверить objection overlay при >= 3 возражениях."""
        policy = DialoguePolicy()

        envelope = ContextEnvelope(
            state="handle_objection",
            total_objections=3,
            repeated_objection_types=["objection_price"],
        )
        sm_result = {"next_state": "handle_objection", "action": "handle_price"}

        result = policy.maybe_override(sm_result, envelope)

        assert result is not None
        assert result.action == "handle_repeated_objection"
        assert result.decision == PolicyDecision.OBJECTION_ESCALATE
        assert ReasonCode.OBJECTION_ESCALATE.value in result.reason_codes

    def test_objection_overlay_reframe(self):
        """Проверить objection overlay reframe."""
        policy = DialoguePolicy()

        envelope = ContextEnvelope(
            state="handle_objection",
            total_objections=2,
            repeated_objection_types=["objection_price"],
        )
        sm_result = {"next_state": "handle_objection", "action": "handle"}

        result = policy.maybe_override(sm_result, envelope)

        assert result is not None
        assert result.action == "reframe_value"
        assert result.decision == PolicyDecision.OBJECTION_REFRAME

    def test_breakthrough_overlay(self):
        """Проверить breakthrough overlay."""
        policy = DialoguePolicy()

        envelope = ContextEnvelope(
            state="presentation",
            has_breakthrough=True,
            turns_since_breakthrough=2,
            breakthrough_action="show_demo",
            reason_codes=[ReasonCode.BREAKTHROUGH_CTA.value],
        )
        sm_result = {"next_state": "presentation", "action": "present"}

        result = policy.maybe_override(sm_result, envelope)

        assert result is not None
        assert result.action is None  # Не меняем action, только сигнализируем
        assert result.decision == PolicyDecision.BREAKTHROUGH_CTA
        assert ReasonCode.BREAKTHROUGH_CTA.value in result.reason_codes

    def test_conservative_overlay(self):
        """Проверить conservative overlay."""
        policy = DialoguePolicy()

        envelope = ContextEnvelope(
            state="spin_implication",
            confidence_trend="decreasing",
            momentum_direction="negative",
            reason_codes=[ReasonCode.POLICY_CONSERVATIVE.value],
        )
        sm_result = {"next_state": "presentation", "action": "transition_to_presentation"}

        result = policy.maybe_override(sm_result, envelope)

        assert result is not None
        assert result.action == "continue_current_goal"
        assert result.decision == PolicyDecision.CONSERVATIVE

    def test_shadow_mode(self):
        """Проверить shadow mode."""
        policy = DialoguePolicy(shadow_mode=True)

        envelope = ContextEnvelope(
            state="spin_situation",
            is_stuck=True,
            reason_codes=[ReasonCode.POLICY_REPAIR_MODE.value],
        )
        sm_result = {"next_state": "spin_situation", "action": "ask"}

        result = policy.maybe_override(sm_result, envelope)

        # В shadow mode возвращается None
        assert result is None

        # Но решение записывается в историю
        assert len(policy._decision_history) == 1

    def test_decision_history(self):
        """Проверить запись истории решений."""
        policy = DialoguePolicy()

        envelope1 = ContextEnvelope(
            state="spin_situation",
            is_stuck=True,
            reason_codes=[ReasonCode.POLICY_REPAIR_MODE.value],
        )
        sm_result1 = {"next_state": "spin_situation", "action": "ask"}

        policy.maybe_override(sm_result1, envelope1)

        # Use oscillation instead of breakthrough (breakthrough_cta has action=None
        # and doesn't get added to history)
        envelope2 = ContextEnvelope(
            state="presentation",
            has_oscillation=True,
            reason_codes=[ReasonCode.POLICY_REPAIR_MODE.value],
        )
        sm_result2 = {"next_state": "presentation", "action": "present"}

        policy.maybe_override(sm_result2, envelope2)

        history = policy.get_decision_history()

        assert len(history) == 2
        assert history[0]["decision"] == "repair_clarify"
        assert history[1]["decision"] == "repair_summarize"

    def test_get_override_rate(self):
        """Проверить расчёт override rate."""
        policy = DialoguePolicy()

        # Без решений
        assert policy.get_override_rate() == 0.0

        # С решениями
        envelope1 = ContextEnvelope(
            state="spin_situation",
            is_stuck=True,
            reason_codes=[ReasonCode.POLICY_REPAIR_MODE.value],
        )
        sm_result1 = {"next_state": "spin_situation", "action": "ask"}
        policy.maybe_override(sm_result1, envelope1)

        # Override был (action != None)
        assert policy.get_override_rate() > 0

    def test_get_decision_distribution(self):
        """Проверить распределение типов решений."""
        policy = DialoguePolicy()

        # Добавляем несколько решений
        for _ in range(2):
            envelope = ContextEnvelope(
                state="spin_situation",
                is_stuck=True,
                reason_codes=[ReasonCode.POLICY_REPAIR_MODE.value],
            )
            sm_result = {"next_state": "spin_situation", "action": "ask"}
            policy.maybe_override(sm_result, envelope)

        # Use oscillation instead of breakthrough (breakthrough_cta has action=None
        # and doesn't get added to history)
        envelope2 = ContextEnvelope(
            state="presentation",
            has_oscillation=True,
            reason_codes=[ReasonCode.POLICY_REPAIR_MODE.value],
        )
        sm_result2 = {"next_state": "presentation", "action": "present"}
        policy.maybe_override(sm_result2, envelope2)

        distribution = policy.get_decision_distribution()

        assert distribution["repair_clarify"] == 2
        assert distribution["repair_summarize"] == 1

    def test_reset(self):
        """Проверить сброс истории."""
        policy = DialoguePolicy()

        envelope = ContextEnvelope(
            state="spin_situation",
            is_stuck=True,
            reason_codes=[ReasonCode.POLICY_REPAIR_MODE.value],
        )
        sm_result = {"next_state": "spin_situation", "action": "ask"}
        policy.maybe_override(sm_result, envelope)

        assert len(policy._decision_history) == 1

        policy.reset()

        assert len(policy._decision_history) == 0

    def test_priority_guard_first(self):
        """Проверить приоритет guard intervention.

        Guard intervention (e.g. TIER_2) must stop the policy evaluation
        to prevent repair overlays (like answer_with_summary) from clearing
        the guard's fallback response and causing a loop.
        """
        policy = DialoguePolicy()

        envelope = ContextEnvelope(
            state="spin_situation",
            is_stuck=True,  # Repair trigger
            guard_intervention="tier_2",  # Guard trigger (fires first)
            reason_codes=[ReasonCode.POLICY_REPAIR_MODE.value],
        )
        sm_result = {"next_state": "spin_situation", "action": "ask"}

        result = policy.maybe_override(sm_result, envelope)

        # Guard fires first and we MUST stop there.
        # handle_guard_intervention returns NO_OVERRIDE (action=None).
        assert result is not None
        assert not result.has_override
        assert result.decision == PolicyDecision.NO_OVERRIDE
        assert ReasonCode.GUARD_INTERVENTION.value in result.reason_codes


class TestContextPolicyMetrics:
    """Тесты для ContextPolicyMetrics."""

    def test_init(self):
        """Проверить инициализацию."""
        metrics = ContextPolicyMetrics()

        assert metrics.total_decisions == 0
        assert metrics.override_count == 0
        assert metrics.shadow_decisions == 0

    def test_record_decision(self):
        """Проверить запись решения."""
        metrics = ContextPolicyMetrics()

        override = PolicyOverride(
            action="clarify_one_question",
            decision=PolicyDecision.REPAIR_CLARIFY,
            reason_codes=["repair.stuck"],
        )

        metrics.record_decision(override)

        assert metrics.total_decisions == 1
        assert metrics.override_count == 1
        assert metrics.reason_code_counts["repair.stuck"] == 1
        assert metrics.decision_type_counts["repair_clarify"] == 1

    def test_record_decision_shadow(self):
        """Проверить запись shadow решения."""
        metrics = ContextPolicyMetrics()

        override = PolicyOverride(
            action="clarify",
            decision=PolicyDecision.REPAIR_CLARIFY,
        )

        metrics.record_decision(override, shadow=True)

        assert metrics.shadow_decisions == 1

    def test_record_decision_no_override(self):
        """Проверить запись решения без override."""
        metrics = ContextPolicyMetrics()

        override = PolicyOverride(
            action=None,
            decision=PolicyDecision.NO_OVERRIDE,
        )

        metrics.record_decision(override)

        assert metrics.total_decisions == 1
        assert metrics.override_count == 0

    def test_get_override_rate(self):
        """Проверить расчёт override rate."""
        metrics = ContextPolicyMetrics()

        # Без решений
        assert metrics.get_override_rate() == 0.0

        # С решениями
        metrics.record_decision(PolicyOverride(action="clarify"))
        metrics.record_decision(PolicyOverride(action=None))
        metrics.record_decision(PolicyOverride(action="reframe"))

        assert metrics.get_override_rate() == pytest.approx(2/3)

    def test_get_summary(self):
        """Проверить получение summary."""
        metrics = ContextPolicyMetrics()

        metrics.record_decision(PolicyOverride(
            action="clarify",
            decision=PolicyDecision.REPAIR_CLARIFY,
            reason_codes=["repair.stuck"],
        ))
        metrics.record_decision(PolicyOverride(
            action=None,
            decision=PolicyDecision.BREAKTHROUGH_CTA,
            reason_codes=["breakthrough.cta"],
        ), shadow=True)

        summary = metrics.get_summary()

        assert summary["total_decisions"] == 2
        assert summary["override_count"] == 1
        assert summary["shadow_decisions"] == 1
        assert "repair.stuck" in summary["reason_code_distribution"]
        assert "repair_clarify" in summary["decision_type_distribution"]

    def test_reset(self):
        """Проверить сброс метрик."""
        metrics = ContextPolicyMetrics()

        metrics.record_decision(PolicyOverride(action="clarify"))

        assert metrics.total_decisions == 1

        metrics.reset()

        assert metrics.total_decisions == 0
        assert metrics.override_count == 0


class TestDialoguePolicyIntegration:
    """Интеграционные тесты для DialoguePolicy."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Включить feature flag."""
        flags.set_override("context_policy_overlays", True)
        yield
        flags.clear_override("context_policy_overlays")

    def test_full_conversation_flow(self):
        """Проверить policy в течение полного диалога."""
        policy = DialoguePolicy()

        # Turn 1: Нормальный ход
        envelope1 = ContextEnvelope(state="spin_situation")
        sm_result1 = {"next_state": "spin_situation", "action": "ask_company_size"}

        result1 = policy.maybe_override(sm_result1, envelope1)
        assert result1 is None or not result1.has_override

        # Turn 2: Клиент застрял
        envelope2 = ContextEnvelope(
            state="spin_situation",
            is_stuck=True,
            unclear_count=3,
            reason_codes=[ReasonCode.POLICY_REPAIR_MODE.value],
        )
        sm_result2 = {"next_state": "spin_situation", "action": "ask_company_size"}

        result2 = policy.maybe_override(sm_result2, envelope2)
        assert result2 is not None
        assert result2.action == "clarify_one_question"

        # Turn 3: Возражение
        envelope3 = ContextEnvelope(
            state="handle_objection",
            total_objections=1,
            repeated_objection_types=[],
        )
        sm_result3 = {"next_state": "handle_objection", "action": "handle_price"}

        result3 = policy.maybe_override(sm_result3, envelope3)
        # Первое возражение — нет оverlay
        assert result3 is None or not result3.has_override

        # Turn 4: Повторное возражение
        envelope4 = ContextEnvelope(
            state="handle_objection",
            total_objections=2,
            repeated_objection_types=["objection_price"],
        )
        sm_result4 = {"next_state": "handle_objection", "action": "handle_price"}

        result4 = policy.maybe_override(sm_result4, envelope4)
        assert result4 is not None
        assert result4.action == "reframe_value"

        # Проверяем историю
        history = policy.get_decision_history()
        assert len(history) >= 2

    def test_no_action_in_protected_states(self):
        """Проверить что protected states не получают overlay даже при сигналах."""
        policy = DialoguePolicy()

        protected_states = ["greeting", "close", "success", "soft_close"]

        for state in protected_states:
            envelope = ContextEnvelope(
                state=state,
                is_stuck=True,
                total_objections=5,
                reason_codes=[ReasonCode.POLICY_REPAIR_MODE.value],
            )
            sm_result = {"next_state": state, "action": "some_action"}

            result = policy.maybe_override(sm_result, envelope)

            assert result is None, f"Expected no override for {state}"
