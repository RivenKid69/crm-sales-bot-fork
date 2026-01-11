"""
Tests for Policy Domain Conditions.

This module provides comprehensive tests for:
- PolicyContext (context.py)
- policy_registry (registry.py)
- All condition functions (conditions.py)
- DialoguePolicy integration

Part of Phase 5: DialoguePolicy Domain (ARCHITECTURE_UNIFIED_PLAN.md)
"""

import pytest
from typing import Dict, Any

from src.conditions.policy import (
    # Context
    PolicyContext,
    OVERLAY_ALLOWED_STATES,
    PROTECTED_STATES,
    AGGRESSIVE_ACTIONS,
    # Registry
    policy_registry,
    policy_condition,
    get_policy_registry,
    # Repair conditions
    is_stuck,
    has_oscillation,
    has_repeated_question,
    needs_repair,
    confidence_decreasing,
    high_unclear_count,
    # Objection conditions
    has_repeated_objections,
    total_objections_3_plus,
    total_objections_5_plus,
    should_escalate_objection,
    has_price_objection_repeat,
    has_competitor_objection_repeat,
    # Breakthrough conditions
    has_breakthrough,
    in_breakthrough_window,
    breakthrough_just_happened,
    should_add_soft_cta,
    # Momentum conditions
    momentum_positive,
    momentum_negative,
    momentum_neutral,
    engagement_high,
    engagement_low,
    engagement_declining,
    is_progressing,
    is_regressing,
    should_be_conservative,
    can_accelerate,
    # Guard conditions
    has_guard_intervention,
    frustration_high,
    frustration_critical,
    needs_empathy,
    # State conditions
    is_overlay_allowed,
    is_protected_state,
    is_aggressive_action,
    should_soften_action,
    is_spin_state,
    is_presentation_state,
    is_handle_objection_state,
    # Combined conditions
    should_apply_repair_overlay,
    should_apply_objection_overlay,
    should_apply_breakthrough_overlay,
    should_apply_conservative_overlay,
    has_effective_action_history,
    should_avoid_least_effective,
)
from src.conditions import ConditionRegistries
from src.conditions.trace import EvaluationTrace


# =============================================================================
# TEST FIXTURES
# =============================================================================

@pytest.fixture
def empty_context():
    """Create an empty context for testing."""
    return PolicyContext.create_test_context()


@pytest.fixture
def stuck_context():
    """Create a context with stuck pattern."""
    return PolicyContext.create_test_context(
        state="spin_situation",
        is_stuck=True,
        unclear_count=3
    )


@pytest.fixture
def breakthrough_context():
    """Create a context with breakthrough."""
    return PolicyContext.create_test_context(
        state="spin_problem",
        has_breakthrough=True,
        turns_since_breakthrough=2,
        momentum_direction="positive"
    )


@pytest.fixture
def objection_context():
    """Create a context with objections."""
    return PolicyContext.create_test_context(
        state="handle_objection",
        total_objections=3,
        repeated_objection_types=["price", "competitor"],
        frustration_level=2
    )


@pytest.fixture
def conservative_context():
    """Create a context requiring conservative mode."""
    return PolicyContext.create_test_context(
        state="spin_problem",
        current_action="transition_to_presentation",
        confidence_trend="decreasing",
        momentum_direction="negative",
        engagement_level="low"
    )


# =============================================================================
# CONTEXT TESTS
# =============================================================================

class TestPolicyContext:
    """Tests for PolicyContext class."""

    def test_create_empty_context(self):
        """Test creating empty context."""
        ctx = PolicyContext()
        assert ctx.collected_data == {}
        assert ctx.state == ""
        assert ctx.turn_number == 0
        assert ctx.is_stuck is False
        assert ctx.has_breakthrough is False

    def test_create_context_with_data(self):
        """Test creating context with data."""
        ctx = PolicyContext(
            collected_data={"company_size": 10},
            state="spin_situation",
            turn_number=3,
            is_stuck=True,
            has_breakthrough=True
        )
        assert ctx.collected_data["company_size"] == 10
        assert ctx.state == "spin_situation"
        assert ctx.turn_number == 3
        assert ctx.is_stuck is True
        assert ctx.has_breakthrough is True

    def test_negative_turn_number_raises(self):
        """Test that negative turn number raises ValueError."""
        with pytest.raises(ValueError, match="turn_number cannot be negative"):
            PolicyContext(turn_number=-1)

    def test_negative_frustration_raises(self):
        """Test that negative frustration raises ValueError."""
        with pytest.raises(ValueError, match="frustration_level cannot be negative"):
            PolicyContext(frustration_level=-1)

    def test_create_test_context(self):
        """Test create_test_context factory method."""
        ctx = PolicyContext.create_test_context(
            collected_data={"test": "data"},
            state="presentation",
            turn_number=10,
            is_stuck=True
        )
        assert ctx.collected_data["test"] == "data"
        assert ctx.state == "presentation"
        assert ctx.turn_number == 10
        assert ctx.is_stuck is True

    def test_is_overlay_allowed(self):
        """Test is_overlay_allowed method."""
        ctx = PolicyContext.create_test_context(state="spin_situation")
        assert ctx.is_overlay_allowed() is True

        ctx_protected = PolicyContext.create_test_context(state="success")
        assert ctx_protected.is_overlay_allowed() is False

    def test_is_protected_state(self):
        """Test is_protected_state method."""
        for state in PROTECTED_STATES:
            ctx = PolicyContext.create_test_context(state=state)
            assert ctx.is_protected_state() is True, f"Failed for {state}"

        ctx_allowed = PolicyContext.create_test_context(state="spin_situation")
        assert ctx_allowed.is_protected_state() is False

    def test_is_aggressive_action(self):
        """Test is_aggressive_action method."""
        for action in AGGRESSIVE_ACTIONS:
            ctx = PolicyContext.create_test_context(current_action=action)
            assert ctx.is_aggressive_action() is True, f"Failed for {action}"

        ctx_safe = PolicyContext.create_test_context(current_action="continue_current_goal")
        assert ctx_safe.is_aggressive_action() is False

    def test_to_dict(self):
        """Test to_dict method."""
        ctx = PolicyContext.create_test_context(
            state="spin_situation",
            turn_number=5,
            is_stuck=True,
            total_objections=2
        )
        d = ctx.to_dict()

        assert d["state"] == "spin_situation"
        assert d["turn_number"] == 5
        assert d["is_stuck"] is True
        assert d["total_objections"] == 2
        assert "momentum_direction" in d
        assert "frustration_level" in d

    def test_repr(self):
        """Test __repr__ method."""
        ctx = PolicyContext.create_test_context(
            state="spin_problem",
            turn_number=3,
            is_stuck=True,
            has_breakthrough=True
        )
        repr_str = repr(ctx)
        assert "spin_problem" in repr_str
        assert "turn=3" in repr_str
        assert "is_stuck=True" in repr_str


class TestPolicyContextFromEnvelope:
    """Tests for creating PolicyContext from ContextEnvelope."""

    def test_from_envelope(self):
        """Test creating context from envelope mock."""
        class MockEnvelope:
            collected_data = {"company_size": 10}
            state = "spin_situation"
            total_turns = 5
            spin_phase = "situation"
            last_action = "ask_question"
            last_intent = "info_provided"
            is_stuck = True
            has_oscillation = False
            repeated_question = None
            confidence_trend = "stable"
            unclear_count = 2
            momentum = 0.5
            momentum_direction = "positive"
            engagement_level = "high"
            engagement_trend = "improving"
            funnel_velocity = 0.3
            is_progressing = True
            is_regressing = False
            total_objections = 1
            repeated_objection_types = []
            has_breakthrough = True
            turns_since_breakthrough = 2
            most_effective_action = "ask_problem"
            least_effective_action = None
            frustration_level = 1
            guard_intervention = None

        envelope = MockEnvelope()
        ctx = PolicyContext.from_envelope(envelope, current_action="continue")

        assert ctx.collected_data["company_size"] == 10
        assert ctx.state == "spin_situation"
        assert ctx.turn_number == 5
        assert ctx.is_stuck is True
        assert ctx.has_breakthrough is True
        assert ctx.turns_since_breakthrough == 2
        assert ctx.current_action == "continue"


class TestConstants:
    """Tests for module constants."""

    def test_overlay_allowed_states(self):
        """Test OVERLAY_ALLOWED_STATES constant."""
        assert "spin_situation" in OVERLAY_ALLOWED_STATES
        assert "spin_problem" in OVERLAY_ALLOWED_STATES
        assert "presentation" in OVERLAY_ALLOWED_STATES
        assert "handle_objection" in OVERLAY_ALLOWED_STATES
        assert "success" not in OVERLAY_ALLOWED_STATES

    def test_protected_states(self):
        """Test PROTECTED_STATES constant."""
        assert "greeting" in PROTECTED_STATES
        assert "success" in PROTECTED_STATES
        assert "soft_close" in PROTECTED_STATES
        assert "close" in PROTECTED_STATES
        assert "spin_situation" not in PROTECTED_STATES

    def test_aggressive_actions(self):
        """Test AGGRESSIVE_ACTIONS constant."""
        assert "transition_to_presentation" in AGGRESSIVE_ACTIONS
        assert "transition_to_close" in AGGRESSIVE_ACTIONS
        assert "ask_for_demo" in AGGRESSIVE_ACTIONS
        assert "ask_for_contact" in AGGRESSIVE_ACTIONS
        assert "continue_current_goal" not in AGGRESSIVE_ACTIONS


# =============================================================================
# REGISTRY TESTS
# =============================================================================

class TestPolicyRegistry:
    """Tests for Policy registry."""

    def test_registry_exists(self):
        """Test that policy_registry is properly created."""
        assert policy_registry is not None
        assert policy_registry.name == "policy"
        assert len(policy_registry) > 0

    def test_get_policy_registry(self):
        """Test get_policy_registry function."""
        reg = get_policy_registry()
        assert reg is policy_registry

    def test_registry_has_expected_conditions(self):
        """Test that registry has all expected conditions."""
        expected = [
            "is_stuck",
            "has_oscillation",
            "needs_repair",
            "has_breakthrough",
            "in_breakthrough_window",
            "should_be_conservative",
            "has_guard_intervention",
            "is_overlay_allowed",
        ]
        for name in expected:
            assert policy_registry.has(name), f"Missing condition: {name}"

    def test_registry_categories(self):
        """Test that registry has expected categories."""
        categories = policy_registry.get_categories()
        assert "repair" in categories
        assert "objection" in categories
        assert "breakthrough" in categories
        assert "momentum" in categories
        assert "guard" in categories
        assert "state" in categories
        assert "combined" in categories

    def test_evaluate_through_registry(self):
        """Test evaluating conditions through registry."""
        ctx = PolicyContext.create_test_context(is_stuck=True)
        assert policy_registry.evaluate("is_stuck", ctx) is True

        ctx_not_stuck = PolicyContext.create_test_context(is_stuck=False)
        assert policy_registry.evaluate("is_stuck", ctx_not_stuck) is False

    def test_evaluate_with_trace(self):
        """Test evaluating with trace."""
        ctx = PolicyContext.create_test_context(is_stuck=True)
        trace = EvaluationTrace(rule_name="repair_check")

        result = policy_registry.evaluate("is_stuck", ctx, trace)

        assert result is True
        assert len(trace.entries) == 1
        assert trace.entries[0].condition_name == "is_stuck"
        assert trace.entries[0].result is True

    def test_registry_in_condition_registries(self):
        """Test that Policy registry is in ConditionRegistries."""
        # Policy-specific conditions should be findable
        assert ConditionRegistries.has_condition("in_breakthrough_window")
        assert ConditionRegistries.find_condition("in_breakthrough_window") == "policy"

        # Policy registry should be registered
        assert ConditionRegistries.get("policy") is policy_registry

    def test_validate_all(self):
        """Test validate_all method."""
        result = policy_registry.validate_all(
            lambda: PolicyContext.create_test_context()
        )
        assert result.is_valid
        assert len(result.passed) == len(policy_registry)
        assert len(result.failed) == 0
        assert len(result.errors) == 0


# =============================================================================
# REPAIR CONDITIONS TESTS
# =============================================================================

class TestRepairConditions:
    """Tests for repair-related conditions."""

    def test_is_stuck(self):
        """Test is_stuck condition."""
        ctx = PolicyContext.create_test_context(is_stuck=True)
        assert is_stuck(ctx) is True

        ctx_not_stuck = PolicyContext.create_test_context(is_stuck=False)
        assert is_stuck(ctx_not_stuck) is False

    def test_has_oscillation(self):
        """Test has_oscillation condition."""
        ctx = PolicyContext.create_test_context(has_oscillation=True)
        assert has_oscillation(ctx) is True

        ctx_no_osc = PolicyContext.create_test_context(has_oscillation=False)
        assert has_oscillation(ctx_no_osc) is False

    def test_has_repeated_question(self):
        """Test has_repeated_question condition."""
        ctx = PolicyContext.create_test_context(repeated_question="price_question")
        assert has_repeated_question(ctx) is True

        ctx_no_repeat = PolicyContext.create_test_context(repeated_question=None)
        assert has_repeated_question(ctx_no_repeat) is False

    def test_needs_repair_stuck(self):
        """Test needs_repair with stuck."""
        ctx = PolicyContext.create_test_context(is_stuck=True)
        assert needs_repair(ctx) is True

    def test_needs_repair_oscillation(self):
        """Test needs_repair with oscillation."""
        ctx = PolicyContext.create_test_context(has_oscillation=True)
        assert needs_repair(ctx) is True

    def test_needs_repair_repeated_question(self):
        """Test needs_repair with repeated question."""
        ctx = PolicyContext.create_test_context(repeated_question="question")
        assert needs_repair(ctx) is True

    def test_needs_repair_none(self):
        """Test needs_repair when no repair needed."""
        ctx = PolicyContext.create_test_context()
        assert needs_repair(ctx) is False

    def test_confidence_decreasing(self):
        """Test confidence_decreasing condition."""
        ctx = PolicyContext.create_test_context(confidence_trend="decreasing")
        assert confidence_decreasing(ctx) is True

        ctx_stable = PolicyContext.create_test_context(confidence_trend="stable")
        assert confidence_decreasing(ctx_stable) is False

    def test_high_unclear_count(self):
        """Test high_unclear_count condition."""
        ctx = PolicyContext.create_test_context(unclear_count=3)
        assert high_unclear_count(ctx) is True

        ctx_low = PolicyContext.create_test_context(unclear_count=2)
        assert high_unclear_count(ctx_low) is False


# =============================================================================
# OBJECTION CONDITIONS TESTS
# =============================================================================

class TestObjectionConditions:
    """Tests for objection-related conditions."""

    def test_has_repeated_objections(self):
        """Test has_repeated_objections condition."""
        ctx = PolicyContext.create_test_context(
            repeated_objection_types=["price", "competitor"]
        )
        assert has_repeated_objections(ctx) is True

        ctx_none = PolicyContext.create_test_context(repeated_objection_types=[])
        assert has_repeated_objections(ctx_none) is False

    def test_total_objections_3_plus(self):
        """Test total_objections_3_plus condition."""
        ctx = PolicyContext.create_test_context(total_objections=3)
        assert total_objections_3_plus(ctx) is True

        ctx_low = PolicyContext.create_test_context(total_objections=2)
        assert total_objections_3_plus(ctx_low) is False

    def test_total_objections_5_plus(self):
        """Test total_objections_5_plus condition."""
        ctx = PolicyContext.create_test_context(total_objections=5)
        assert total_objections_5_plus(ctx) is True

        ctx_low = PolicyContext.create_test_context(total_objections=4)
        assert total_objections_5_plus(ctx_low) is False

    def test_should_escalate_objection_by_count(self):
        """Test should_escalate_objection by total count."""
        ctx = PolicyContext.create_test_context(total_objections=3)
        assert should_escalate_objection(ctx) is True

    def test_should_escalate_objection_by_repeat(self):
        """Test should_escalate_objection by repeated types."""
        ctx = PolicyContext.create_test_context(
            total_objections=1,
            repeated_objection_types=["price"]
        )
        assert should_escalate_objection(ctx) is True

    def test_should_escalate_objection_no(self):
        """Test should_escalate_objection when not needed."""
        ctx = PolicyContext.create_test_context(
            total_objections=1,
            repeated_objection_types=[]
        )
        assert should_escalate_objection(ctx) is False

    def test_has_price_objection_repeat(self):
        """Test has_price_objection_repeat condition."""
        ctx = PolicyContext.create_test_context(
            repeated_objection_types=["price", "competitor"]
        )
        assert has_price_objection_repeat(ctx) is True

        ctx_no_price = PolicyContext.create_test_context(
            repeated_objection_types=["competitor"]
        )
        assert has_price_objection_repeat(ctx_no_price) is False

    def test_has_competitor_objection_repeat(self):
        """Test has_competitor_objection_repeat condition."""
        ctx = PolicyContext.create_test_context(
            repeated_objection_types=["competitor"]
        )
        assert has_competitor_objection_repeat(ctx) is True

        ctx_no_comp = PolicyContext.create_test_context(
            repeated_objection_types=["price"]
        )
        assert has_competitor_objection_repeat(ctx_no_comp) is False


# =============================================================================
# BREAKTHROUGH CONDITIONS TESTS
# =============================================================================

class TestBreakthroughConditions:
    """Tests for breakthrough-related conditions."""

    def test_has_breakthrough(self):
        """Test has_breakthrough condition."""
        ctx = PolicyContext.create_test_context(has_breakthrough=True)
        assert has_breakthrough(ctx) is True

        ctx_no = PolicyContext.create_test_context(has_breakthrough=False)
        assert has_breakthrough(ctx_no) is False

    def test_in_breakthrough_window(self):
        """Test in_breakthrough_window condition."""
        # In window (turn 1)
        ctx_1 = PolicyContext.create_test_context(
            has_breakthrough=True,
            turns_since_breakthrough=1
        )
        assert in_breakthrough_window(ctx_1) is True

        # In window (turn 3)
        ctx_3 = PolicyContext.create_test_context(
            has_breakthrough=True,
            turns_since_breakthrough=3
        )
        assert in_breakthrough_window(ctx_3) is True

        # Outside window (turn 4)
        ctx_4 = PolicyContext.create_test_context(
            has_breakthrough=True,
            turns_since_breakthrough=4
        )
        assert in_breakthrough_window(ctx_4) is False

        # No breakthrough
        ctx_no = PolicyContext.create_test_context(
            has_breakthrough=False,
            turns_since_breakthrough=2
        )
        assert in_breakthrough_window(ctx_no) is False

        # None turns_since
        ctx_none = PolicyContext.create_test_context(
            has_breakthrough=True,
            turns_since_breakthrough=None
        )
        assert in_breakthrough_window(ctx_none) is False

    def test_breakthrough_just_happened(self):
        """Test breakthrough_just_happened condition."""
        ctx = PolicyContext.create_test_context(
            has_breakthrough=True,
            turns_since_breakthrough=0
        )
        assert breakthrough_just_happened(ctx) is True

        ctx_1 = PolicyContext.create_test_context(
            has_breakthrough=True,
            turns_since_breakthrough=1
        )
        assert breakthrough_just_happened(ctx_1) is True

        ctx_2 = PolicyContext.create_test_context(
            has_breakthrough=True,
            turns_since_breakthrough=2
        )
        assert breakthrough_just_happened(ctx_2) is False

    def test_should_add_soft_cta(self):
        """Test should_add_soft_cta condition."""
        # In window with positive momentum
        ctx_yes = PolicyContext.create_test_context(
            has_breakthrough=True,
            turns_since_breakthrough=2,
            momentum_direction="positive"
        )
        assert should_add_soft_cta(ctx_yes) is True

        # In window with neutral momentum
        ctx_neutral = PolicyContext.create_test_context(
            has_breakthrough=True,
            turns_since_breakthrough=2,
            momentum_direction="neutral"
        )
        assert should_add_soft_cta(ctx_neutral) is True

        # In window but negative momentum
        ctx_negative = PolicyContext.create_test_context(
            has_breakthrough=True,
            turns_since_breakthrough=2,
            momentum_direction="negative"
        )
        assert should_add_soft_cta(ctx_negative) is False

        # Outside window
        ctx_outside = PolicyContext.create_test_context(
            has_breakthrough=True,
            turns_since_breakthrough=5
        )
        assert should_add_soft_cta(ctx_outside) is False


# =============================================================================
# MOMENTUM CONDITIONS TESTS
# =============================================================================

class TestMomentumConditions:
    """Tests for momentum-related conditions."""

    def test_momentum_positive(self):
        """Test momentum_positive condition."""
        ctx = PolicyContext.create_test_context(momentum_direction="positive")
        assert momentum_positive(ctx) is True

        ctx_neg = PolicyContext.create_test_context(momentum_direction="negative")
        assert momentum_positive(ctx_neg) is False

    def test_momentum_negative(self):
        """Test momentum_negative condition."""
        ctx = PolicyContext.create_test_context(momentum_direction="negative")
        assert momentum_negative(ctx) is True

        ctx_pos = PolicyContext.create_test_context(momentum_direction="positive")
        assert momentum_negative(ctx_pos) is False

    def test_momentum_neutral(self):
        """Test momentum_neutral condition."""
        ctx = PolicyContext.create_test_context(momentum_direction="neutral")
        assert momentum_neutral(ctx) is True

        ctx_pos = PolicyContext.create_test_context(momentum_direction="positive")
        assert momentum_neutral(ctx_pos) is False

    def test_engagement_high(self):
        """Test engagement_high condition."""
        ctx = PolicyContext.create_test_context(engagement_level="high")
        assert engagement_high(ctx) is True

        ctx_med = PolicyContext.create_test_context(engagement_level="medium")
        assert engagement_high(ctx_med) is False

    def test_engagement_low(self):
        """Test engagement_low condition."""
        ctx_low = PolicyContext.create_test_context(engagement_level="low")
        assert engagement_low(ctx_low) is True

        ctx_dis = PolicyContext.create_test_context(engagement_level="disengaged")
        assert engagement_low(ctx_dis) is True

        ctx_high = PolicyContext.create_test_context(engagement_level="high")
        assert engagement_low(ctx_high) is False

    def test_engagement_declining(self):
        """Test engagement_declining condition."""
        ctx = PolicyContext.create_test_context(engagement_trend="declining")
        assert engagement_declining(ctx) is True

        ctx_stable = PolicyContext.create_test_context(engagement_trend="stable")
        assert engagement_declining(ctx_stable) is False

    def test_is_progressing(self):
        """Test is_progressing condition."""
        ctx = PolicyContext.create_test_context(is_progressing=True)
        assert is_progressing(ctx) is True

        ctx_no = PolicyContext.create_test_context(is_progressing=False)
        assert is_progressing(ctx_no) is False

    def test_is_regressing(self):
        """Test is_regressing condition."""
        ctx = PolicyContext.create_test_context(is_regressing=True)
        assert is_regressing(ctx) is True

        ctx_no = PolicyContext.create_test_context(is_regressing=False)
        assert is_regressing(ctx_no) is False

    def test_should_be_conservative_confidence(self):
        """Test should_be_conservative with decreasing confidence."""
        ctx = PolicyContext.create_test_context(confidence_trend="decreasing")
        assert should_be_conservative(ctx) is True

    def test_should_be_conservative_momentum(self):
        """Test should_be_conservative with negative momentum."""
        ctx = PolicyContext.create_test_context(momentum_direction="negative")
        assert should_be_conservative(ctx) is True

    def test_should_be_conservative_no(self):
        """Test should_be_conservative when not needed."""
        ctx = PolicyContext.create_test_context(
            confidence_trend="stable",
            momentum_direction="positive"
        )
        assert should_be_conservative(ctx) is False

    def test_can_accelerate(self):
        """Test can_accelerate condition."""
        ctx = PolicyContext.create_test_context(
            momentum_direction="positive",
            is_progressing=True
        )
        assert can_accelerate(ctx) is True

        ctx_no_progress = PolicyContext.create_test_context(
            momentum_direction="positive",
            is_progressing=False
        )
        assert can_accelerate(ctx_no_progress) is False

        ctx_no_momentum = PolicyContext.create_test_context(
            momentum_direction="neutral",
            is_progressing=True
        )
        assert can_accelerate(ctx_no_momentum) is False


# =============================================================================
# GUARD CONDITIONS TESTS
# =============================================================================

class TestGuardConditions:
    """Tests for guard-related conditions."""

    def test_has_guard_intervention(self):
        """Test has_guard_intervention condition."""
        ctx = PolicyContext.create_test_context(guard_intervention="frustration")
        assert has_guard_intervention(ctx) is True

        ctx_no = PolicyContext.create_test_context(guard_intervention=None)
        assert has_guard_intervention(ctx_no) is False

    def test_frustration_high(self):
        """Test frustration_high condition."""
        ctx = PolicyContext.create_test_context(frustration_level=3)
        assert frustration_high(ctx) is True

        ctx_low = PolicyContext.create_test_context(frustration_level=2)
        assert frustration_high(ctx_low) is False

    def test_frustration_critical(self):
        """Test frustration_critical condition."""
        ctx = PolicyContext.create_test_context(frustration_level=4)
        assert frustration_critical(ctx) is True

        ctx_low = PolicyContext.create_test_context(frustration_level=3)
        assert frustration_critical(ctx_low) is False

    def test_needs_empathy_frustration(self):
        """Test needs_empathy with high frustration."""
        ctx = PolicyContext.create_test_context(frustration_level=2)
        assert needs_empathy(ctx) is True

    def test_needs_empathy_repeated_objections(self):
        """Test needs_empathy with repeated objections."""
        ctx = PolicyContext.create_test_context(
            frustration_level=0,
            repeated_objection_types=["price"]
        )
        assert needs_empathy(ctx) is True

    def test_needs_empathy_no(self):
        """Test needs_empathy when not needed."""
        ctx = PolicyContext.create_test_context(
            frustration_level=1,
            repeated_objection_types=[]
        )
        assert needs_empathy(ctx) is False


# =============================================================================
# STATE CONDITIONS TESTS
# =============================================================================

class TestStateConditions:
    """Tests for state-related conditions."""

    def test_is_overlay_allowed(self):
        """Test is_overlay_allowed condition."""
        for state in OVERLAY_ALLOWED_STATES:
            ctx = PolicyContext.create_test_context(state=state)
            assert is_overlay_allowed(ctx) is True, f"Failed for {state}"

        ctx_not = PolicyContext.create_test_context(state="success")
        assert is_overlay_allowed(ctx_not) is False

    def test_is_protected_state(self):
        """Test is_protected_state condition."""
        for state in PROTECTED_STATES:
            ctx = PolicyContext.create_test_context(state=state)
            assert is_protected_state(ctx) is True, f"Failed for {state}"

        ctx_not = PolicyContext.create_test_context(state="spin_situation")
        assert is_protected_state(ctx_not) is False

    def test_is_aggressive_action(self):
        """Test is_aggressive_action condition."""
        for action in AGGRESSIVE_ACTIONS:
            ctx = PolicyContext.create_test_context(current_action=action)
            assert is_aggressive_action(ctx) is True, f"Failed for {action}"

        ctx_safe = PolicyContext.create_test_context(current_action="ask_question")
        assert is_aggressive_action(ctx_safe) is False

    def test_should_soften_action(self):
        """Test should_soften_action condition."""
        # Aggressive + conservative
        ctx = PolicyContext.create_test_context(
            current_action="transition_to_presentation",
            confidence_trend="decreasing"
        )
        assert should_soften_action(ctx) is True

        # Aggressive + low engagement
        ctx_low = PolicyContext.create_test_context(
            current_action="transition_to_presentation",
            engagement_level="low"
        )
        assert should_soften_action(ctx_low) is True

        # Not aggressive
        ctx_safe = PolicyContext.create_test_context(
            current_action="ask_question",
            confidence_trend="decreasing"
        )
        assert should_soften_action(ctx_safe) is False

        # Aggressive but good signals
        ctx_good = PolicyContext.create_test_context(
            current_action="transition_to_presentation",
            confidence_trend="stable",
            momentum_direction="positive",
            engagement_level="high"
        )
        assert should_soften_action(ctx_good) is False

    def test_is_spin_state(self):
        """Test is_spin_state condition."""
        ctx = PolicyContext.create_test_context(state="spin_situation")
        assert is_spin_state(ctx) is True

        ctx_no = PolicyContext.create_test_context(state="presentation")
        assert is_spin_state(ctx_no) is False

    def test_is_presentation_state(self):
        """Test is_presentation_state condition."""
        ctx = PolicyContext.create_test_context(state="presentation")
        assert is_presentation_state(ctx) is True

        ctx_no = PolicyContext.create_test_context(state="spin_situation")
        assert is_presentation_state(ctx_no) is False

    def test_is_handle_objection_state(self):
        """Test is_handle_objection_state condition."""
        ctx = PolicyContext.create_test_context(state="handle_objection")
        assert is_handle_objection_state(ctx) is True

        ctx_no = PolicyContext.create_test_context(state="presentation")
        assert is_handle_objection_state(ctx_no) is False


# =============================================================================
# COMBINED CONDITIONS TESTS
# =============================================================================

class TestCombinedConditions:
    """Tests for combined conditions."""

    def test_should_apply_repair_overlay(self):
        """Test should_apply_repair_overlay condition."""
        # Allowed state + needs repair
        ctx = PolicyContext.create_test_context(
            state="spin_situation",
            is_stuck=True
        )
        assert should_apply_repair_overlay(ctx) is True

        # Protected state + needs repair
        ctx_protected = PolicyContext.create_test_context(
            state="success",
            is_stuck=True
        )
        assert should_apply_repair_overlay(ctx_protected) is False

        # Allowed state + no repair
        ctx_no_repair = PolicyContext.create_test_context(
            state="spin_situation",
            is_stuck=False,
            has_oscillation=False,
            repeated_question=None
        )
        assert should_apply_repair_overlay(ctx_no_repair) is False

    def test_should_apply_objection_overlay(self):
        """Test should_apply_objection_overlay condition."""
        ctx = PolicyContext.create_test_context(
            state="handle_objection",
            repeated_objection_types=["price"]
        )
        assert should_apply_objection_overlay(ctx) is True

        ctx_no = PolicyContext.create_test_context(
            state="handle_objection",
            repeated_objection_types=[]
        )
        assert should_apply_objection_overlay(ctx_no) is False

    def test_should_apply_breakthrough_overlay(self):
        """Test should_apply_breakthrough_overlay condition."""
        ctx = PolicyContext.create_test_context(
            state="spin_problem",
            has_breakthrough=True,
            turns_since_breakthrough=2
        )
        assert should_apply_breakthrough_overlay(ctx) is True

        ctx_outside = PolicyContext.create_test_context(
            state="spin_problem",
            has_breakthrough=True,
            turns_since_breakthrough=5
        )
        assert should_apply_breakthrough_overlay(ctx_outside) is False

    def test_should_apply_conservative_overlay(self):
        """Test should_apply_conservative_overlay condition."""
        ctx = PolicyContext.create_test_context(
            state="spin_situation",
            current_action="transition_to_presentation",
            confidence_trend="decreasing"
        )
        assert should_apply_conservative_overlay(ctx) is True

        # Not aggressive action
        ctx_safe = PolicyContext.create_test_context(
            state="spin_situation",
            current_action="ask_question",
            confidence_trend="decreasing"
        )
        assert should_apply_conservative_overlay(ctx_safe) is False

    def test_has_effective_action_history(self):
        """Test has_effective_action_history condition."""
        ctx_most = PolicyContext.create_test_context(
            most_effective_action="ask_problem"
        )
        assert has_effective_action_history(ctx_most) is True

        ctx_least = PolicyContext.create_test_context(
            least_effective_action="deflect"
        )
        assert has_effective_action_history(ctx_least) is True

        ctx_none = PolicyContext.create_test_context()
        assert has_effective_action_history(ctx_none) is False

    def test_should_avoid_least_effective(self):
        """Test should_avoid_least_effective condition."""
        ctx = PolicyContext.create_test_context(
            current_action="deflect",
            least_effective_action="deflect"
        )
        assert should_avoid_least_effective(ctx) is True

        ctx_different = PolicyContext.create_test_context(
            current_action="ask_question",
            least_effective_action="deflect"
        )
        assert should_avoid_least_effective(ctx_different) is False

        ctx_no_least = PolicyContext.create_test_context(
            current_action="ask_question",
            least_effective_action=None
        )
        assert should_avoid_least_effective(ctx_no_least) is False


# =============================================================================
# INTEGRATION TESTS
# =============================================================================

class TestIntegration:
    """Integration tests for Policy conditions."""

    def test_repair_scenario(self):
        """Test repair scenario with all signals."""
        ctx = PolicyContext.create_test_context(
            state="spin_situation",
            is_stuck=True,
            unclear_count=3,
            confidence_trend="decreasing"
        )

        assert is_stuck(ctx) is True
        assert needs_repair(ctx) is True
        assert should_apply_repair_overlay(ctx) is True
        assert high_unclear_count(ctx) is True

    def test_breakthrough_scenario(self):
        """Test breakthrough scenario with CTA."""
        ctx = PolicyContext.create_test_context(
            state="spin_problem",
            has_breakthrough=True,
            turns_since_breakthrough=2,
            momentum_direction="positive",
            is_progressing=True
        )

        assert has_breakthrough(ctx) is True
        assert in_breakthrough_window(ctx) is True
        assert should_add_soft_cta(ctx) is True
        assert should_apply_breakthrough_overlay(ctx) is True
        assert can_accelerate(ctx) is True

    def test_objection_escalation_scenario(self):
        """Test objection escalation scenario."""
        ctx = PolicyContext.create_test_context(
            state="handle_objection",
            total_objections=3,
            repeated_objection_types=["price", "competitor"],
            frustration_level=3
        )

        assert total_objections_3_plus(ctx) is True
        assert has_repeated_objections(ctx) is True
        assert should_escalate_objection(ctx) is True
        assert has_price_objection_repeat(ctx) is True
        assert has_competitor_objection_repeat(ctx) is True
        assert frustration_high(ctx) is True
        assert needs_empathy(ctx) is True

    def test_conservative_mode_scenario(self):
        """Test conservative mode scenario."""
        ctx = PolicyContext.create_test_context(
            state="spin_problem",
            current_action="transition_to_presentation",
            confidence_trend="decreasing",
            momentum_direction="negative",
            engagement_level="low"
        )

        assert should_be_conservative(ctx) is True
        assert is_aggressive_action(ctx) is True
        assert should_soften_action(ctx) is True
        assert should_apply_conservative_overlay(ctx) is True
        assert engagement_low(ctx) is True

    def test_guard_intervention_scenario(self):
        """Test guard intervention scenario."""
        ctx = PolicyContext.create_test_context(
            state="spin_situation",
            guard_intervention="frustration_high",
            frustration_level=4
        )

        assert has_guard_intervention(ctx) is True
        assert frustration_critical(ctx) is True
        assert needs_empathy(ctx) is True

    def test_protected_state_scenario(self):
        """Test that protected states block overlays."""
        for state in PROTECTED_STATES:
            ctx = PolicyContext.create_test_context(
                state=state,
                is_stuck=True,
                has_breakthrough=True,
                turns_since_breakthrough=2
            )

            assert is_protected_state(ctx) is True
            assert should_apply_repair_overlay(ctx) is False
            assert should_apply_breakthrough_overlay(ctx) is False


# =============================================================================
# DOCUMENTATION TESTS
# =============================================================================

class TestDocumentation:
    """Tests for documentation generation."""

    def test_registry_documentation(self):
        """Test that registry can generate documentation."""
        docs = policy_registry.get_documentation()

        assert "Policy Conditions" in docs
        assert "PolicyContext" in docs
        assert "is_stuck" in docs
        assert "repair" in docs.lower()
        assert "breakthrough" in docs.lower()
        assert "objection" in docs.lower()

    def test_registry_stats(self):
        """Test registry statistics."""
        stats = policy_registry.get_stats()

        assert stats["name"] == "policy"
        assert stats["total_conditions"] > 0
        assert stats["total_categories"] >= 7
        assert "repair" in stats["conditions_by_category"]
        assert "breakthrough" in stats["conditions_by_category"]
        assert "objection" in stats["conditions_by_category"]


# =============================================================================
# EDGE CASES TESTS
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_empty_repeated_objection_types(self):
        """Test with empty repeated_objection_types."""
        ctx = PolicyContext.create_test_context(repeated_objection_types=[])

        assert has_repeated_objections(ctx) is False
        assert has_price_objection_repeat(ctx) is False
        assert has_competitor_objection_repeat(ctx) is False

    def test_boundary_frustration_levels(self):
        """Test boundary frustration levels."""
        ctx_2 = PolicyContext.create_test_context(frustration_level=2)
        assert frustration_high(ctx_2) is False
        assert needs_empathy(ctx_2) is True

        ctx_3 = PolicyContext.create_test_context(frustration_level=3)
        assert frustration_high(ctx_3) is True
        assert frustration_critical(ctx_3) is False

        ctx_4 = PolicyContext.create_test_context(frustration_level=4)
        assert frustration_critical(ctx_4) is True

    def test_boundary_turns_since_breakthrough(self):
        """Test boundary values for turns_since_breakthrough."""
        # Turn 0 (just happened)
        ctx_0 = PolicyContext.create_test_context(
            has_breakthrough=True,
            turns_since_breakthrough=0
        )
        assert in_breakthrough_window(ctx_0) is False  # 0 not in [1, 3]
        assert breakthrough_just_happened(ctx_0) is True

        # Turn 1 (start of window)
        ctx_1 = PolicyContext.create_test_context(
            has_breakthrough=True,
            turns_since_breakthrough=1
        )
        assert in_breakthrough_window(ctx_1) is True

        # Turn 3 (end of window)
        ctx_3 = PolicyContext.create_test_context(
            has_breakthrough=True,
            turns_since_breakthrough=3
        )
        assert in_breakthrough_window(ctx_3) is True

        # Turn 4 (outside window)
        ctx_4 = PolicyContext.create_test_context(
            has_breakthrough=True,
            turns_since_breakthrough=4
        )
        assert in_breakthrough_window(ctx_4) is False

    def test_boundary_objection_counts(self):
        """Test boundary objection counts."""
        ctx_2 = PolicyContext.create_test_context(total_objections=2)
        assert total_objections_3_plus(ctx_2) is False

        ctx_3 = PolicyContext.create_test_context(total_objections=3)
        assert total_objections_3_plus(ctx_3) is True

        ctx_4 = PolicyContext.create_test_context(total_objections=4)
        assert total_objections_5_plus(ctx_4) is False

        ctx_5 = PolicyContext.create_test_context(total_objections=5)
        assert total_objections_5_plus(ctx_5) is True

    def test_case_insensitive_objection_types(self):
        """Test case insensitive objection type matching."""
        ctx_lower = PolicyContext.create_test_context(
            repeated_objection_types=["price"]
        )
        assert has_price_objection_repeat(ctx_lower) is True

        ctx_upper = PolicyContext.create_test_context(
            repeated_objection_types=["PRICE"]
        )
        assert has_price_objection_repeat(ctx_upper) is True

        ctx_mixed = PolicyContext.create_test_context(
            repeated_objection_types=["Price_high"]
        )
        assert has_price_objection_repeat(ctx_mixed) is True

    def test_none_values_handling(self):
        """Test handling of None values."""
        ctx = PolicyContext.create_test_context(
            turns_since_breakthrough=None,
            guard_intervention=None,
            most_effective_action=None,
            least_effective_action=None
        )

        assert in_breakthrough_window(ctx) is False
        assert has_guard_intervention(ctx) is False
        assert has_effective_action_history(ctx) is False
        assert should_avoid_least_effective(ctx) is False
