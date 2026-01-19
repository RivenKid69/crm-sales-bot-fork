"""
Integration Tests for DialoguePolicy with Declarative Conditions.

This module provides comprehensive tests for the refactored DialoguePolicy
that uses declarative conditions from the policy domain.

Part of Phase 5: DialoguePolicy Domain (ARCHITECTURE_UNIFIED_PLAN.md)
"""

import pytest
import sys
import os
from unittest.mock import Mock, patch, MagicMock
from typing import Dict, Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from dialogue_policy import (
    DialoguePolicy,
    PolicyDecision,
    PolicyOverride,
    ContextPolicyMetrics,
)
from context_envelope import ContextEnvelope, ReasonCode
from src.conditions.policy import (
    PolicyContext,
    policy_registry,
    OVERLAY_ALLOWED_STATES,
    PROTECTED_STATES,
)


# =============================================================================
# TEST FIXTURES
# =============================================================================

@pytest.fixture
def policy():
    """Create a DialoguePolicy instance."""
    return DialoguePolicy()


@pytest.fixture
def policy_with_trace():
    """Create a DialoguePolicy with tracing enabled."""
    return DialoguePolicy(trace_enabled=True)


@pytest.fixture
def shadow_policy():
    """Create a DialoguePolicy in shadow mode."""
    return DialoguePolicy(shadow_mode=True)


def create_mock_envelope(
    state: str = "spin_situation",
    is_stuck: bool = False,
    has_oscillation: bool = False,
    repeated_question: str = None,
    confidence_trend: str = "stable",
    unclear_count: int = 0,
    momentum: float = 0.0,
    momentum_direction: str = "neutral",
    engagement_level: str = "medium",
    engagement_trend: str = "stable",
    funnel_velocity: float = 0.0,
    is_progressing: bool = False,
    is_regressing: bool = False,
    total_objections: int = 0,
    repeated_objection_types: list = None,
    has_breakthrough: bool = False,
    turns_since_breakthrough: int = None,
    most_effective_action: str = None,
    least_effective_action: str = None,
    frustration_level: int = 0,
    guard_intervention: str = None,
    last_intent: str = None,
    last_action: str = None,
    collected_data: Dict[str, Any] = None,
    spin_phase: str = None,
    total_turns: int = 0,
    reason_codes: list = None,
) -> Mock:
    """Create a mock ContextEnvelope for testing."""
    envelope = Mock(spec=ContextEnvelope)
    envelope.state = state
    envelope.is_stuck = is_stuck
    envelope.has_oscillation = has_oscillation
    envelope.repeated_question = repeated_question
    envelope.confidence_trend = confidence_trend
    envelope.unclear_count = unclear_count
    envelope.momentum = momentum
    envelope.momentum_direction = momentum_direction
    envelope.engagement_level = engagement_level
    envelope.engagement_trend = engagement_trend
    envelope.funnel_velocity = funnel_velocity
    envelope.is_progressing = is_progressing
    envelope.is_regressing = is_regressing
    envelope.total_objections = total_objections
    envelope.repeated_objection_types = repeated_objection_types or []
    envelope.has_breakthrough = has_breakthrough
    envelope.turns_since_breakthrough = turns_since_breakthrough
    envelope.most_effective_action = most_effective_action
    envelope.least_effective_action = least_effective_action
    envelope.frustration_level = frustration_level
    envelope.guard_intervention = guard_intervention
    envelope.last_intent = last_intent
    envelope.last_action = last_action
    envelope.collected_data = collected_data or {}
    envelope.spin_phase = spin_phase
    envelope.total_turns = total_turns
    envelope.reason_codes = reason_codes or []

    # Mock has_reason method
    envelope.has_reason = Mock(return_value=False)

    return envelope


# =============================================================================
# BASIC FUNCTIONALITY TESTS
# =============================================================================

class TestDialoguePolicyBasic:
    """Basic tests for DialoguePolicy."""

    def test_create_policy(self):
        """Test creating a DialoguePolicy instance."""
        policy = DialoguePolicy()
        assert policy.shadow_mode is False
        assert policy.trace_enabled is False
        assert policy._decision_history == []

    def test_create_policy_shadow_mode(self):
        """Test creating a policy in shadow mode."""
        policy = DialoguePolicy(shadow_mode=True)
        assert policy.shadow_mode is True

    def test_create_policy_with_trace(self):
        """Test creating a policy with tracing."""
        policy = DialoguePolicy(trace_enabled=True)
        assert policy.trace_enabled is True

    @patch('dialogue_policy.flags')
    def test_disabled_feature_flag(self, mock_flags, policy):
        """Test that policy returns None when feature flag is disabled."""
        mock_flags.is_enabled.return_value = False

        envelope = create_mock_envelope()
        sm_result = {"action": "ask_question"}

        result = policy.maybe_override(sm_result, envelope)

        assert result is None
        mock_flags.is_enabled.assert_called_once_with("context_policy_overlays")


# =============================================================================
# PROTECTED STATE TESTS
# =============================================================================

class TestProtectedStates:
    """Tests for protected state handling."""

    @patch('dialogue_policy.flags')
    def test_protected_state_returns_none(self, mock_flags, policy):
        """Test that protected states return None."""
        mock_flags.is_enabled.return_value = True

        for state in PROTECTED_STATES:
            envelope = create_mock_envelope(state=state, is_stuck=True)
            sm_result = {"action": "ask_question"}

            result = policy.maybe_override(sm_result, envelope)

            assert result is None, f"Should return None for protected state: {state}"

    @patch('dialogue_policy.flags')
    def test_non_overlay_state_returns_none(self, mock_flags, policy):
        """Test that non-overlay states return None."""
        mock_flags.is_enabled.return_value = True

        envelope = create_mock_envelope(state="some_unknown_state", is_stuck=True)
        sm_result = {"action": "ask_question"}

        result = policy.maybe_override(sm_result, envelope)

        assert result is None


# =============================================================================
# REPAIR OVERLAY TESTS
# =============================================================================

class TestRepairOverlay:
    """Tests for repair mode overlay."""

    @patch('dialogue_policy.flags')
    def test_stuck_triggers_repair(self, mock_flags, policy):
        """Test that stuck state triggers repair overlay."""
        mock_flags.is_enabled.return_value = True

        envelope = create_mock_envelope(
            state="spin_situation",
            is_stuck=True,
            unclear_count=3
        )
        sm_result = {"action": "ask_question"}

        result = policy.maybe_override(sm_result, envelope)

        assert result is not None
        assert result.action == "clarify_one_question"
        assert result.decision == PolicyDecision.REPAIR_CLARIFY
        assert ReasonCode.POLICY_REPAIR_MODE.value in result.reason_codes

    @patch('dialogue_policy.flags')
    def test_oscillation_triggers_repair(self, mock_flags, policy):
        """Test that oscillation triggers repair overlay."""
        mock_flags.is_enabled.return_value = True

        envelope = create_mock_envelope(
            state="spin_problem",
            has_oscillation=True
        )
        sm_result = {"action": "ask_question"}

        result = policy.maybe_override(sm_result, envelope)

        assert result is not None
        assert result.action == "summarize_and_clarify"
        assert result.decision == PolicyDecision.REPAIR_SUMMARIZE

    @patch('dialogue_policy.flags')
    def test_repeated_question_triggers_repair(self, mock_flags, policy):
        """Test that repeated question triggers repair overlay."""
        mock_flags.is_enabled.return_value = True

        envelope = create_mock_envelope(
            state="spin_situation",
            repeated_question="price_question"
        )
        sm_result = {"action": "ask_question"}

        result = policy.maybe_override(sm_result, envelope)

        assert result is not None
        assert result.action == "answer_with_summary"
        assert result.decision == PolicyDecision.REPAIR_CLARIFY


# =============================================================================
# OBJECTION OVERLAY TESTS
# =============================================================================

class TestObjectionOverlay:
    """Tests for objection overlay."""

    @patch('dialogue_policy.flags')
    def test_repeated_objections_trigger_reframe(self, mock_flags, policy):
        """Test that repeated objections trigger reframe."""
        mock_flags.is_enabled.return_value = True

        envelope = create_mock_envelope(
            state="handle_objection",
            repeated_objection_types=["price"],
            total_objections=2
        )
        sm_result = {"action": "handle_objection"}

        result = policy.maybe_override(sm_result, envelope)

        assert result is not None
        assert result.action == "reframe_value"
        assert result.decision == PolicyDecision.OBJECTION_REFRAME
        assert ReasonCode.OBJECTION_REPEAT.value in result.reason_codes

    @patch('dialogue_policy.flags')
    def test_high_objections_trigger_escalate(self, mock_flags, policy):
        """Test that 3+ objections trigger escalation."""
        mock_flags.is_enabled.return_value = True

        envelope = create_mock_envelope(
            state="handle_objection",
            repeated_objection_types=["price"],
            total_objections=3
        )
        sm_result = {"action": "handle_objection"}

        result = policy.maybe_override(sm_result, envelope)

        assert result is not None
        assert result.action == "handle_repeated_objection"
        assert result.decision == PolicyDecision.OBJECTION_ESCALATE
        assert ReasonCode.OBJECTION_ESCALATE.value in result.reason_codes


# =============================================================================
# BREAKTHROUGH OVERLAY TESTS
# =============================================================================

class TestBreakthroughOverlay:
    """Tests for breakthrough overlay."""

    @patch('dialogue_policy.flags')
    def test_breakthrough_window_triggers_cta(self, mock_flags, policy):
        """Test that breakthrough window triggers CTA overlay."""
        mock_flags.is_enabled.return_value = True

        envelope = create_mock_envelope(
            state="spin_problem",
            has_breakthrough=True,
            turns_since_breakthrough=2,
            momentum_direction="positive"
        )
        sm_result = {"action": "ask_question"}

        result = policy.maybe_override(sm_result, envelope)

        assert result is not None
        assert result.action is None  # CTA doesn't change action
        assert result.decision == PolicyDecision.BREAKTHROUGH_CTA
        assert ReasonCode.BREAKTHROUGH_CTA.value in result.reason_codes

    @patch('dialogue_policy.flags')
    def test_breakthrough_outside_window(self, mock_flags, policy):
        """Test that breakthrough outside window doesn't trigger."""
        mock_flags.is_enabled.return_value = True

        envelope = create_mock_envelope(
            state="spin_problem",
            has_breakthrough=True,
            turns_since_breakthrough=5
        )
        sm_result = {"action": "ask_question"}

        result = policy.maybe_override(sm_result, envelope)

        assert result is None  # No overlay applied


# =============================================================================
# CONSERVATIVE OVERLAY TESTS
# =============================================================================

class TestConservativeOverlay:
    """Tests for conservative mode overlay."""

    @patch('dialogue_policy.flags')
    def test_conservative_mode_with_aggressive_action(self, mock_flags, policy):
        """Test conservative mode with aggressive action."""
        mock_flags.is_enabled.return_value = True

        envelope = create_mock_envelope(
            state="spin_problem",
            confidence_trend="decreasing",
            momentum_direction="negative"
        )
        sm_result = {"action": "transition_to_presentation"}

        result = policy.maybe_override(sm_result, envelope)

        assert result is not None
        assert result.action == "continue_current_goal"
        assert result.decision == PolicyDecision.CONSERVATIVE
        assert ReasonCode.POLICY_CONSERVATIVE.value in result.reason_codes

    @patch('dialogue_policy.flags')
    def test_conservative_mode_with_safe_action(self, mock_flags, policy):
        """Test conservative mode doesn't trigger with safe action."""
        mock_flags.is_enabled.return_value = True

        envelope = create_mock_envelope(
            state="spin_problem",
            confidence_trend="decreasing",
            momentum_direction="negative"
        )
        sm_result = {"action": "ask_question"}  # Safe action

        result = policy.maybe_override(sm_result, envelope)

        # Should not trigger conservative overlay for non-aggressive actions
        assert result is None


# =============================================================================
# GUARD INTERVENTION TESTS
# =============================================================================

class TestGuardIntervention:
    """Tests for guard intervention handling."""

    @patch('dialogue_policy.flags')
    def test_guard_intervention_no_override(self, mock_flags, policy):
        """Test that guard intervention doesn't change action."""
        mock_flags.is_enabled.return_value = True

        envelope = create_mock_envelope(
            state="spin_situation",
            guard_intervention="frustration_high"
        )
        sm_result = {"action": "ask_question"}

        result = policy.maybe_override(sm_result, envelope)

        assert result is not None
        assert result.action is None  # Guard handles it
        assert result.decision == PolicyDecision.NO_OVERRIDE
        assert ReasonCode.GUARD_INTERVENTION.value in result.reason_codes


# =============================================================================
# PRIORITY TESTS
# =============================================================================

class TestOverlayPriority:
    """Tests for overlay priority ordering."""

    @patch('dialogue_policy.flags')
    def test_guard_has_highest_priority(self, mock_flags, policy):
        """Test that guard intervention has highest priority."""
        mock_flags.is_enabled.return_value = True

        envelope = create_mock_envelope(
            state="spin_situation",
            guard_intervention="frustration_high",
            is_stuck=True,  # Would trigger repair
            has_breakthrough=True,
            turns_since_breakthrough=2  # Would trigger breakthrough
        )
        sm_result = {"action": "ask_question"}

        result = policy.maybe_override(sm_result, envelope)

        assert result.decision == PolicyDecision.NO_OVERRIDE
        assert ReasonCode.GUARD_INTERVENTION.value in result.reason_codes

    @patch('dialogue_policy.flags')
    def test_repair_before_objection(self, mock_flags, policy):
        """Test that repair has priority over objection."""
        mock_flags.is_enabled.return_value = True

        envelope = create_mock_envelope(
            state="handle_objection",
            is_stuck=True,  # Triggers repair
            repeated_objection_types=["price"]  # Would trigger objection
        )
        sm_result = {"action": "handle_objection"}

        result = policy.maybe_override(sm_result, envelope)

        # Repair should win
        assert result.decision == PolicyDecision.REPAIR_CLARIFY

    @patch('dialogue_policy.flags')
    def test_objection_before_breakthrough(self, mock_flags, policy):
        """Test that objection has priority over breakthrough."""
        mock_flags.is_enabled.return_value = True

        envelope = create_mock_envelope(
            state="handle_objection",
            repeated_objection_types=["price"],
            has_breakthrough=True,
            turns_since_breakthrough=2
        )
        sm_result = {"action": "handle_objection"}

        result = policy.maybe_override(sm_result, envelope)

        # Objection should win
        assert result.decision == PolicyDecision.OBJECTION_REFRAME


# =============================================================================
# TRACING TESTS
# =============================================================================

class TestTracing:
    """Tests for condition tracing."""

    @patch('dialogue_policy.flags')
    def test_trace_enabled(self, mock_flags, policy_with_trace):
        """Test that trace is created when enabled."""
        mock_flags.is_enabled.return_value = True

        envelope = create_mock_envelope(
            state="spin_situation",
            is_stuck=True
        )
        sm_result = {"action": "ask_question"}

        result = policy_with_trace.maybe_override(sm_result, envelope)

        assert result is not None
        assert result.trace is not None
        assert len(result.trace.entries) > 0

    @patch('dialogue_policy.flags')
    def test_trace_in_to_dict(self, mock_flags, policy_with_trace):
        """Test that trace appears in to_dict."""
        mock_flags.is_enabled.return_value = True

        envelope = create_mock_envelope(
            state="spin_situation",
            is_stuck=True
        )
        sm_result = {"action": "ask_question"}

        result = policy_with_trace.maybe_override(sm_result, envelope)
        result_dict = result.to_dict()

        assert "trace" in result_dict
        assert result_dict["trace"] is not None


# =============================================================================
# SHADOW MODE TESTS
# =============================================================================

class TestShadowMode:
    """Tests for shadow mode functionality."""

    @patch('dialogue_policy.flags')
    @patch('logger.logger')
    def test_shadow_mode_returns_none(self, mock_logger, mock_flags, shadow_policy):
        """Test that shadow mode returns None but logs."""
        mock_flags.is_enabled.return_value = True

        envelope = create_mock_envelope(
            state="spin_situation",
            is_stuck=True
        )
        sm_result = {"action": "ask_question"}

        result = shadow_policy.maybe_override(sm_result, envelope)

        assert result is None
        # Decision should be recorded in history
        assert len(shadow_policy._decision_history) == 1
        # Logger should be called (from logger.logger.info)
        mock_logger.info.assert_called()


# =============================================================================
# METRICS AND HISTORY TESTS
# =============================================================================

class TestMetricsAndHistory:
    """Tests for metrics and decision history."""

    @patch('dialogue_policy.flags')
    def test_decision_history(self, mock_flags, policy):
        """Test decision history recording."""
        mock_flags.is_enabled.return_value = True

        envelope = create_mock_envelope(
            state="spin_situation",
            is_stuck=True
        )
        sm_result = {"action": "ask_question"}

        policy.maybe_override(sm_result, envelope)
        policy.maybe_override(sm_result, envelope)

        history = policy.get_decision_history()
        assert len(history) == 2

    @patch('dialogue_policy.flags')
    def test_override_rate(self, mock_flags, policy):
        """Test override rate calculation.

        Note: Only decisions with has_override=True are added to history,
        so override_rate is always 1.0 for non-empty history.
        This test verifies that overrides are correctly counted.
        """
        mock_flags.is_enabled.return_value = True

        # Add repair override
        envelope_stuck = create_mock_envelope(state="spin_situation", is_stuck=True)
        policy.maybe_override({"action": "ask"}, envelope_stuck)

        # Add breakthrough override (both SPIN states now support overlays)
        envelope_bt = create_mock_envelope(
            state="spin_problem",
            has_breakthrough=True,
            turns_since_breakthrough=2
        )
        policy.maybe_override({"action": "ask"}, envelope_bt)

        rate = policy.get_override_rate()
        # Both calls create overrides, so rate is 1.0
        assert rate == 1.0

    @patch('dialogue_policy.flags')
    def test_decision_distribution(self, mock_flags, policy):
        """Test decision distribution.

        Note: Only overrides with action != None are added to history.
        breakthrough_cta has action=None (it adds CTA via ResponseDirectives),
        so we use repair overlays instead.
        """
        mock_flags.is_enabled.return_value = True

        # Add repair (stuck) - has action override
        envelope_stuck = create_mock_envelope(state="spin_situation", is_stuck=True)
        policy.maybe_override({"action": "ask"}, envelope_stuck)

        # Add repair (oscillation) - has action override
        envelope_osc = create_mock_envelope(
            state="spin_problem",
            has_oscillation=True
        )
        policy.maybe_override({"action": "ask"}, envelope_osc)

        distribution = policy.get_decision_distribution()
        assert "repair_clarify" in distribution
        assert "repair_summarize" in distribution

    @patch('dialogue_policy.flags')
    def test_reset(self, mock_flags, policy):
        """Test reset clears history."""
        mock_flags.is_enabled.return_value = True

        envelope = create_mock_envelope(state="spin_situation", is_stuck=True)
        policy.maybe_override({"action": "ask"}, envelope)

        assert len(policy._decision_history) == 1

        policy.reset()

        assert len(policy._decision_history) == 0
        assert policy.get_override_rate() == 0.0


# =============================================================================
# POLICY OVERRIDE TESTS
# =============================================================================

class TestPolicyOverride:
    """Tests for PolicyOverride dataclass."""

    def test_has_override_true(self):
        """Test has_override when action is set."""
        override = PolicyOverride(action="clarify")
        assert override.has_override is True

    def test_has_override_false(self):
        """Test has_override when action is None."""
        override = PolicyOverride(action=None)
        assert override.has_override is False

    def test_to_dict(self):
        """Test to_dict serialization."""
        override = PolicyOverride(
            action="clarify",
            next_state=None,
            reason_codes=["repair.stuck"],
            decision=PolicyDecision.REPAIR_CLARIFY,
            signals_used={"is_stuck": True},
            expected_effect="Clarify"
        )

        d = override.to_dict()

        assert d["action"] == "clarify"
        assert d["next_state"] is None
        assert d["reason_codes"] == ["repair.stuck"]
        assert d["decision"] == "repair_clarify"
        assert d["signals_used"] == {"is_stuck": True}
        assert d["expected_effect"] == "Clarify"


# =============================================================================
# CONTEXT POLICY METRICS TESTS
# =============================================================================

class TestContextPolicyMetrics:
    """Tests for ContextPolicyMetrics class."""

    def test_initial_state(self):
        """Test initial metrics state."""
        metrics = ContextPolicyMetrics()

        assert metrics.total_decisions == 0
        assert metrics.override_count == 0
        assert metrics.get_override_rate() == 0.0

    def test_record_decision(self):
        """Test recording a decision."""
        metrics = ContextPolicyMetrics()

        override = PolicyOverride(
            action="clarify",
            reason_codes=["repair.stuck"],
            decision=PolicyDecision.REPAIR_CLARIFY
        )
        metrics.record_decision(override)

        assert metrics.total_decisions == 1
        assert metrics.override_count == 1
        assert "repair.stuck" in metrics.reason_code_counts
        assert "repair_clarify" in metrics.decision_type_counts

    def test_record_shadow_decision(self):
        """Test recording a shadow decision."""
        metrics = ContextPolicyMetrics()

        override = PolicyOverride(action="clarify")
        metrics.record_decision(override, shadow=True)

        assert metrics.shadow_decisions == 1

    def test_get_summary(self):
        """Test get_summary method."""
        metrics = ContextPolicyMetrics()

        override = PolicyOverride(
            action="clarify",
            reason_codes=["repair.stuck"],
            decision=PolicyDecision.REPAIR_CLARIFY
        )
        metrics.record_decision(override)

        summary = metrics.get_summary()

        assert summary["total_decisions"] == 1
        assert summary["override_count"] == 1
        assert summary["override_rate"] == 1.0
        assert "repair.stuck" in summary["reason_code_distribution"]

    def test_reset(self):
        """Test reset method."""
        metrics = ContextPolicyMetrics()

        override = PolicyOverride(action="clarify")
        metrics.record_decision(override)
        metrics.reset()

        assert metrics.total_decisions == 0
        assert metrics.override_count == 0


# =============================================================================
# INTEGRATION WITH REGISTRY TESTS
# =============================================================================

class TestRegistryIntegration:
    """Tests for integration with policy_registry."""

    def test_registry_conditions_used(self):
        """Test that policy uses registry conditions."""
        # Verify key conditions exist
        assert policy_registry.has("is_stuck")
        assert policy_registry.has("needs_repair")
        assert policy_registry.has("has_repeated_objections")
        assert policy_registry.has("in_breakthrough_window")
        assert policy_registry.has("should_apply_conservative_overlay")

    def test_registry_evaluate(self):
        """Test direct registry evaluation."""
        ctx = PolicyContext.create_test_context(
            state="spin_situation",
            is_stuck=True
        )

        result = policy_registry.evaluate("is_stuck", ctx)
        assert result is True

        result = policy_registry.evaluate("needs_repair", ctx)
        assert result is True


# =============================================================================
# EDGE CASES TESTS
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases."""

    @patch('dialogue_policy.flags')
    def test_empty_sm_result(self, mock_flags, policy):
        """Test with empty sm_result."""
        mock_flags.is_enabled.return_value = True

        envelope = create_mock_envelope(
            state="spin_situation",
            is_stuck=True
        )

        result = policy.maybe_override({}, envelope)

        assert result is not None
        assert result.decision == PolicyDecision.REPAIR_CLARIFY

    @patch('dialogue_policy.flags')
    def test_no_triggers(self, mock_flags, policy):
        """Test when no triggers are active."""
        mock_flags.is_enabled.return_value = True

        envelope = create_mock_envelope(
            state="spin_situation",
            # All signals default to inactive
        )
        sm_result = {"action": "ask_question"}

        result = policy.maybe_override(sm_result, envelope)

        assert result is None

    @patch('dialogue_policy.flags')
    def test_multiple_decisions_isolated(self, mock_flags, policy):
        """Test that multiple decisions are isolated."""
        mock_flags.is_enabled.return_value = True

        # First decision
        envelope1 = create_mock_envelope(state="spin_situation", is_stuck=True)
        result1 = policy.maybe_override({"action": "ask"}, envelope1)

        # Second decision
        envelope2 = create_mock_envelope(
            state="spin_problem",
            has_breakthrough=True,
            turns_since_breakthrough=2
        )
        result2 = policy.maybe_override({"action": "ask"}, envelope2)

        # Results should be independent
        assert result1.decision == PolicyDecision.REPAIR_CLARIFY
        assert result2.decision == PolicyDecision.BREAKTHROUGH_CTA
