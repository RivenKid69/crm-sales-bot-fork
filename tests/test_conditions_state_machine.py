"""
Tests for StateMachine Domain Conditions.

This module provides comprehensive tests for:
- EvaluatorContext (context.py)
- sm_registry (registry.py)
- All condition functions (conditions.py)

Part of Phase 2: StateMachine Domain (ARCHITECTURE_UNIFIED_PLAN.md)
"""

import pytest
from typing import Dict, Any

from src.conditions.state_machine import (
    # Context
    EvaluatorContext,
    SimpleIntentTracker,
    IntentTrackerProtocol,
    create_test_context,
    SPIN_PHASES,
    SPIN_STATE_TO_PHASE,
    SPIN_STATES,
    INTENT_CATEGORIES,
    # Registry
    sm_registry,
    sm_condition,
    get_sm_registry,
    # Data conditions
    has_pricing_data,
    has_contact_info,
    has_company_size,
    has_pain_point,
    has_pain_and_company_size,
    has_competitor_mention,
    missing_required_data,
    has_all_required_data,
    has_high_interest,
    has_desired_outcome,
    # Intent conditions
    price_repeated_3x,
    price_repeated_2x,
    technical_question_repeated_2x,
    objection_limit_reached,
    objection_consecutive_3x,
    objection_total_5x,
    is_current_intent_objection,
    is_current_intent_positive,
    is_current_intent_question,
    is_spin_progress_intent,
    # State conditions
    is_spin_state,
    in_spin_phase,
    in_situation_phase,
    in_problem_phase,
    in_implication_phase,
    in_need_payoff_phase,
    is_presentation_state,
    is_close_state,
    is_greeting_state,
    is_handle_objection_state,
    is_soft_close_state,
    is_success_state,
    is_terminal_state,
    post_spin_phase,
    # Turn conditions
    is_first_turn,
    is_early_conversation,
    is_late_conversation,
    is_extended_conversation,
    # Combined conditions
    can_answer_price,
    should_deflect_price,
    ready_for_presentation,
    ready_for_close,
    can_handle_with_roi,
)
from src.conditions import ConditionRegistries
from src.conditions.trace import EvaluationTrace, Resolution


# =============================================================================
# TEST FIXTURES
# =============================================================================

@pytest.fixture
def empty_context():
    """Create an empty context for testing."""
    return create_test_context()


@pytest.fixture
def pricing_context():
    """Create a context with pricing data."""
    return create_test_context(
        collected_data={"company_size": 10},
        state="spin_situation"
    )


@pytest.fixture
def full_context():
    """Create a context with lots of data."""
    return create_test_context(
        collected_data={
            "company_size": 50,
            "users_count": 20,
            "pain_point": "losing customers",
            "pain_category": "retention",
            "email": "test@example.com",
            "phone": "+7900123456",
            "competitor": "Bitrix",
            "current_crm": "Excel",
            "high_interest": True,
            "desired_outcome": "automate sales",
        },
        state="presentation",
        turn_number=8
    )


@pytest.fixture
def spin_context():
    """Create a context in SPIN state."""
    return create_test_context(
        state="spin_problem",
        turn_number=5,
        current_intent="problem_revealed"
    )


# =============================================================================
# CONTEXT TESTS
# =============================================================================

class TestEvaluatorContext:
    """Tests for EvaluatorContext class."""

    def test_create_empty_context(self):
        """Test creating empty context."""
        ctx = EvaluatorContext()
        assert ctx.collected_data == {}
        assert ctx.state == ""
        assert ctx.turn_number == 0
        assert ctx.spin_phase is None
        assert ctx.is_spin_state is False

    def test_create_context_with_data(self):
        """Test creating context with collected data."""
        ctx = EvaluatorContext(
            collected_data={"company_size": 10},
            state="spin_situation",
            turn_number=3
        )
        assert ctx.collected_data["company_size"] == 10
        assert ctx.state == "spin_situation"
        assert ctx.turn_number == 3
        assert ctx.spin_phase == "situation"
        assert ctx.is_spin_state is True

    def test_negative_turn_number_raises(self):
        """Test that negative turn number raises ValueError."""
        with pytest.raises(ValueError, match="turn_number cannot be negative"):
            EvaluatorContext(turn_number=-1)

    def test_auto_compute_spin_phase(self):
        """Test automatic computation of spin_phase."""
        for state, phase in SPIN_STATE_TO_PHASE.items():
            ctx = EvaluatorContext(state=state)
            assert ctx.spin_phase == phase
            assert ctx.is_spin_state is True

    def test_non_spin_state(self):
        """Test non-SPIN state."""
        ctx = EvaluatorContext(state="presentation")
        assert ctx.spin_phase is None
        assert ctx.is_spin_state is False

    def test_create_test_context(self):
        """Test create_test_context factory method."""
        ctx = EvaluatorContext.create_test_context(
            collected_data={"test": "data"},
            state="close",
            turn_number=10
        )
        assert ctx.collected_data["test"] == "data"
        assert ctx.state == "close"
        assert ctx.turn_number == 10
        assert ctx.intent_tracker is not None

    def test_from_state_machine(self):
        """Test creating context from state machine."""
        class MockStateMachine:
            state = "spin_problem"
            collected_data = {"company_size": 15}
            spin_phase = "problem"
            turn_number = 7
            last_intent = "info_provided"
            intent_tracker = None

        config = {"required_data": ["pain_point"]}
        ctx = EvaluatorContext.from_state_machine(
            MockStateMachine(),
            "problem_revealed",
            config
        )

        assert ctx.state == "spin_problem"
        assert ctx.collected_data["company_size"] == 15
        assert ctx.spin_phase == "problem"
        assert ctx.turn_number == 7
        assert ctx.current_intent == "problem_revealed"
        assert ctx.prev_intent == "info_provided"
        assert "pain_point" in ctx.missing_required_data

    def test_has_field(self):
        """Test has_field method."""
        ctx = create_test_context(
            collected_data={"company_size": 10, "empty": None, "zero": 0}
        )
        assert ctx.has_field("company_size") is True
        assert ctx.has_field("empty") is False
        assert ctx.has_field("zero") is False
        assert ctx.has_field("nonexistent") is False

    def test_has_any_field(self):
        """Test has_any_field method."""
        ctx = create_test_context(collected_data={"company_size": 10})
        assert ctx.has_any_field(["company_size", "users_count"]) is True
        assert ctx.has_any_field(["users_count", "pain_point"]) is False

    def test_has_all_fields(self):
        """Test has_all_fields method."""
        ctx = create_test_context(
            collected_data={"company_size": 10, "pain_point": "losing"}
        )
        assert ctx.has_all_fields(["company_size", "pain_point"]) is True
        assert ctx.has_all_fields(["company_size", "email"]) is False

    def test_get_field(self):
        """Test get_field method."""
        ctx = create_test_context(collected_data={"company_size": 10})
        assert ctx.get_field("company_size") == 10
        assert ctx.get_field("nonexistent") is None
        assert ctx.get_field("nonexistent", "default") == "default"

    def test_intent_streak_methods(self):
        """Test intent tracking methods."""
        tracker = SimpleIntentTracker()
        tracker.set_intent_streak("price_question", 3)
        tracker.set_intent_total("price_question", 5)
        tracker.set_category_streak("objection", 2)
        tracker.set_category_total("objection", 4)

        ctx = create_test_context(intent_tracker=tracker)

        assert ctx.get_intent_streak("price_question") == 3
        assert ctx.get_intent_total("price_question") == 5
        assert ctx.get_category_streak("objection") == 2
        assert ctx.get_category_total("objection") == 4

    def test_intent_streak_without_tracker(self):
        """Test intent methods when no tracker is set."""
        ctx = EvaluatorContext()
        ctx.intent_tracker = None

        assert ctx.get_intent_streak("any") == 0
        assert ctx.get_intent_total("any") == 0
        assert ctx.get_category_streak("any") == 0
        assert ctx.get_category_total("any") == 0

    def test_to_dict(self):
        """Test to_dict method."""
        ctx = create_test_context(
            collected_data={"test": "data"},
            state="greeting",
            turn_number=5,
            current_intent="price_question"
        )
        d = ctx.to_dict()

        assert d["collected_data"]["test"] == "data"
        assert d["state"] == "greeting"
        assert d["turn_number"] == 5
        assert d["current_intent"] == "price_question"
        assert "spin_phase" in d
        assert "is_spin_state" in d

    def test_repr(self):
        """Test __repr__ method."""
        ctx = create_test_context(
            state="spin_problem",
            current_intent="price_question",
            turn_number=3
        )
        repr_str = repr(ctx)
        assert "spin_problem" in repr_str
        assert "price_question" in repr_str
        assert "turn=3" in repr_str


class TestSimpleIntentTracker:
    """Tests for SimpleIntentTracker class."""

    def test_initial_state(self):
        """Test initial tracker state."""
        tracker = SimpleIntentTracker()
        assert tracker.last_intent is None
        assert tracker.prev_intent is None
        assert tracker.streak_count("any") == 0
        assert tracker.total_count("any") == 0

    def test_record_intent(self):
        """Test recording an intent."""
        tracker = SimpleIntentTracker()
        tracker.record("price_question")

        assert tracker.last_intent == "price_question"
        assert tracker.prev_intent is None
        assert tracker.streak_count("price_question") == 1
        assert tracker.total_count("price_question") == 1

    def test_record_multiple_same_intent(self):
        """Test recording same intent multiple times."""
        tracker = SimpleIntentTracker()
        tracker.record("price_question")
        tracker.record("price_question")
        tracker.record("price_question")

        assert tracker.streak_count("price_question") == 3
        assert tracker.total_count("price_question") == 3
        assert tracker.last_intent == "price_question"
        assert tracker.prev_intent == "price_question"

    def test_streak_reset_on_different_intent(self):
        """Test that streak resets when different intent."""
        tracker = SimpleIntentTracker()
        tracker.record("price_question")
        tracker.record("price_question")
        tracker.record("agreement")

        assert tracker.streak_count("price_question") == 0
        assert tracker.total_count("price_question") == 2
        assert tracker.streak_count("agreement") == 1
        assert tracker.last_intent == "agreement"
        assert tracker.prev_intent == "price_question"

    def test_category_tracking(self):
        """Test category streak and total tracking."""
        tracker = SimpleIntentTracker()
        tracker.record("objection_price")
        tracker.record("objection_competitor")

        assert tracker.category_total("objection") == 2
        # Streak should be 2 because both intents are in same category
        # (category streak continues even with different specific intents)
        assert tracker.category_streak("objection") == 2

    def test_set_methods(self):
        """Test manual set methods for testing."""
        tracker = SimpleIntentTracker()
        tracker.set_intent_streak("test", 5)
        tracker.set_intent_total("test", 10)
        tracker.set_category_streak("cat", 3)
        tracker.set_category_total("cat", 7)

        assert tracker.streak_count("test") == 5
        assert tracker.total_count("test") == 10
        assert tracker.category_streak("cat") == 3
        assert tracker.category_total("cat") == 7


class TestConstants:
    """Tests for module constants."""

    def test_spin_phases(self):
        """Test SPIN_PHASES constant."""
        assert SPIN_PHASES == ["situation", "problem", "implication", "need_payoff"]

    def test_spin_state_to_phase(self):
        """Test SPIN_STATE_TO_PHASE mapping."""
        assert SPIN_STATE_TO_PHASE["spin_situation"] == "situation"
        assert SPIN_STATE_TO_PHASE["spin_problem"] == "problem"
        assert SPIN_STATE_TO_PHASE["spin_implication"] == "implication"
        assert SPIN_STATE_TO_PHASE["spin_need_payoff"] == "need_payoff"

    def test_spin_states_set(self):
        """Test SPIN_STATES dict (phase -> state mapping)."""
        # SPIN_STATES is a dict: phase_name -> state_name
        assert "situation" in SPIN_STATES
        assert "problem" in SPIN_STATES
        assert SPIN_STATES["situation"] == "spin_situation"
        assert SPIN_STATES["problem"] == "spin_problem"
        # presentation is not a phase
        assert "presentation" not in SPIN_STATES

    def test_intent_categories(self):
        """Test INTENT_CATEGORIES dict."""
        assert "objection" in INTENT_CATEGORIES
        assert "positive" in INTENT_CATEGORIES
        assert "question" in INTENT_CATEGORIES
        assert "spin_progress" in INTENT_CATEGORIES

        assert "objection_price" in INTENT_CATEGORIES["objection"]
        assert "agreement" in INTENT_CATEGORIES["positive"]
        assert "price_question" in INTENT_CATEGORIES["question"]


# =============================================================================
# REGISTRY TESTS
# =============================================================================

class TestSMRegistry:
    """Tests for StateMachine registry."""

    def test_registry_exists(self):
        """Test that sm_registry is properly created."""
        assert sm_registry is not None
        assert sm_registry.name == "state_machine"
        assert len(sm_registry) > 0

    def test_get_sm_registry(self):
        """Test get_sm_registry function."""
        reg = get_sm_registry()
        assert reg is sm_registry

    def test_registry_has_expected_conditions(self):
        """Test that registry has all expected conditions."""
        expected = [
            "has_pricing_data",
            "has_contact_info",
            "price_repeated_3x",
            "is_spin_state",
            "objection_limit_reached",
        ]
        for name in expected:
            assert sm_registry.has(name), f"Missing condition: {name}"

    def test_registry_categories(self):
        """Test that registry has expected categories."""
        categories = sm_registry.get_categories()
        assert "data" in categories
        assert "intent" in categories
        assert "state" in categories
        assert "turn" in categories
        assert "combined" in categories

    def test_evaluate_through_registry(self):
        """Test evaluating conditions through registry."""
        ctx = create_test_context(collected_data={"company_size": 10})
        assert sm_registry.evaluate("has_pricing_data", ctx) is True

        ctx_empty = create_test_context()
        assert sm_registry.evaluate("has_pricing_data", ctx_empty) is False

    def test_evaluate_with_trace(self):
        """Test evaluating with trace."""
        ctx = create_test_context(collected_data={"company_size": 10})
        trace = EvaluationTrace(rule_name="price_question")

        result = sm_registry.evaluate("has_pricing_data", ctx, trace)

        assert result is True
        assert len(trace.entries) == 1
        assert trace.entries[0].condition_name == "has_pricing_data"
        assert trace.entries[0].result is True

    def test_registry_in_condition_registries(self):
        """Test that SM registry is in ConditionRegistries."""
        # SM-specific conditions should be findable
        assert ConditionRegistries.has_condition("price_repeated_3x")
        assert ConditionRegistries.find_condition("price_repeated_3x") == "state_machine"

        # SM registry should be registered
        assert ConditionRegistries.get("state_machine") is sm_registry

    def test_validate_all(self):
        """Test validate_all method."""
        result = sm_registry.validate_all(
            lambda: create_test_context()
        )
        assert result.is_valid
        assert len(result.passed) == len(sm_registry)
        assert len(result.failed) == 0
        assert len(result.errors) == 0


# =============================================================================
# DATA CONDITIONS TESTS
# =============================================================================

class TestDataConditions:
    """Tests for data-related conditions."""

    def test_has_pricing_data_with_company_size(self):
        """Test has_pricing_data with company_size."""
        ctx = create_test_context(collected_data={"company_size": 10})
        assert has_pricing_data(ctx) is True

    def test_has_pricing_data_with_users_count(self):
        """Test has_pricing_data with users_count."""
        ctx = create_test_context(collected_data={"users_count": 20})
        assert has_pricing_data(ctx) is True

    def test_has_pricing_data_with_both(self):
        """Test has_pricing_data with both fields."""
        ctx = create_test_context(
            collected_data={"company_size": 10, "users_count": 20}
        )
        assert has_pricing_data(ctx) is True

    def test_has_pricing_data_empty(self):
        """Test has_pricing_data without data."""
        ctx = create_test_context()
        assert has_pricing_data(ctx) is False

    def test_has_contact_info_with_email(self):
        """Test has_contact_info with email."""
        ctx = create_test_context(collected_data={"email": "test@example.com"})
        assert has_contact_info(ctx) is True

    def test_has_contact_info_with_phone(self):
        """Test has_contact_info with phone."""
        ctx = create_test_context(collected_data={"phone": "+7900123456"})
        assert has_contact_info(ctx) is True

    def test_has_contact_info_with_contact(self):
        """Test has_contact_info with contact field."""
        ctx = create_test_context(collected_data={"contact": "telegram: @user"})
        assert has_contact_info(ctx) is True

    def test_has_contact_info_empty(self):
        """Test has_contact_info without data."""
        ctx = create_test_context()
        assert has_contact_info(ctx) is False

    def test_has_company_size(self):
        """Test has_company_size."""
        ctx = create_test_context(collected_data={"company_size": 10})
        assert has_company_size(ctx) is True

        ctx_empty = create_test_context()
        assert has_company_size(ctx_empty) is False

    def test_has_pain_point_with_pain_point(self):
        """Test has_pain_point with pain_point field."""
        ctx = create_test_context(collected_data={"pain_point": "losing customers"})
        assert has_pain_point(ctx) is True

    def test_has_pain_point_with_pain_category(self):
        """Test has_pain_point with pain_category field."""
        ctx = create_test_context(collected_data={"pain_category": "retention"})
        assert has_pain_point(ctx) is True

    def test_has_pain_point_empty(self):
        """Test has_pain_point without data."""
        ctx = create_test_context()
        assert has_pain_point(ctx) is False

    def test_has_pain_and_company_size(self):
        """Test has_pain_and_company_size."""
        ctx = create_test_context(
            collected_data={"pain_point": "losing", "company_size": 10}
        )
        assert has_pain_and_company_size(ctx) is True

        ctx_only_pain = create_test_context(collected_data={"pain_point": "losing"})
        assert has_pain_and_company_size(ctx_only_pain) is False

        ctx_only_size = create_test_context(collected_data={"company_size": 10})
        assert has_pain_and_company_size(ctx_only_size) is False

    def test_has_competitor_mention_with_competitor(self):
        """Test has_competitor_mention with competitor."""
        ctx = create_test_context(collected_data={"competitor": "Bitrix"})
        assert has_competitor_mention(ctx) is True

    def test_has_competitor_mention_with_current_crm(self):
        """Test has_competitor_mention with current_crm."""
        ctx = create_test_context(collected_data={"current_crm": "Excel"})
        assert has_competitor_mention(ctx) is True

    def test_has_competitor_mention_empty(self):
        """Test has_competitor_mention without data."""
        ctx = create_test_context()
        assert has_competitor_mention(ctx) is False

    def test_missing_required_data(self):
        """Test missing_required_data."""
        ctx = create_test_context(missing_required_data=["pain_point", "company_size"])
        assert missing_required_data(ctx) is True

        ctx_complete = create_test_context(missing_required_data=[])
        assert missing_required_data(ctx_complete) is False

    def test_has_all_required_data(self):
        """Test has_all_required_data."""
        ctx = create_test_context(missing_required_data=[])
        assert has_all_required_data(ctx) is True

        ctx_missing = create_test_context(missing_required_data=["pain_point"])
        assert has_all_required_data(ctx_missing) is False

    def test_has_high_interest(self):
        """Test has_high_interest."""
        ctx = create_test_context(collected_data={"high_interest": True})
        assert has_high_interest(ctx) is True

        ctx_false = create_test_context(collected_data={"high_interest": False})
        assert has_high_interest(ctx_false) is False

        ctx_empty = create_test_context()
        assert has_high_interest(ctx_empty) is False

    def test_has_desired_outcome(self):
        """Test has_desired_outcome."""
        ctx = create_test_context(collected_data={"desired_outcome": "automate"})
        assert has_desired_outcome(ctx) is True

        ctx_empty = create_test_context()
        assert has_desired_outcome(ctx_empty) is False


# =============================================================================
# INTENT CONDITIONS TESTS
# =============================================================================

class TestIntentConditions:
    """Tests for intent-related conditions."""

    def test_price_repeated_3x(self):
        """Test price_repeated_3x."""
        tracker = SimpleIntentTracker()
        tracker.set_intent_streak("price_question", 3)
        ctx = create_test_context(intent_tracker=tracker)
        assert price_repeated_3x(ctx) is True

        tracker2 = SimpleIntentTracker()
        tracker2.set_intent_streak("price_question", 2)
        ctx2 = create_test_context(intent_tracker=tracker2)
        assert price_repeated_3x(ctx2) is False

    def test_price_repeated_2x(self):
        """Test price_repeated_2x."""
        tracker = SimpleIntentTracker()
        tracker.set_intent_streak("price_question", 2)
        ctx = create_test_context(intent_tracker=tracker)
        assert price_repeated_2x(ctx) is True

        tracker2 = SimpleIntentTracker()
        tracker2.set_intent_streak("price_question", 1)
        ctx2 = create_test_context(intent_tracker=tracker2)
        assert price_repeated_2x(ctx2) is False

    def test_technical_question_repeated_2x(self):
        """Test technical_question_repeated_2x."""
        tracker = SimpleIntentTracker()
        tracker.set_intent_streak("question_technical", 2)
        ctx = create_test_context(intent_tracker=tracker)
        assert technical_question_repeated_2x(ctx) is True

        tracker2 = SimpleIntentTracker()
        tracker2.set_intent_streak("question_technical", 1)
        ctx2 = create_test_context(intent_tracker=tracker2)
        assert technical_question_repeated_2x(ctx2) is False

    def test_objection_limit_reached_consecutive(self):
        """Test objection_limit_reached with consecutive limit."""
        tracker = SimpleIntentTracker()
        tracker.set_category_streak("objection", 3)
        ctx = create_test_context(intent_tracker=tracker)
        assert objection_limit_reached(ctx) is True

    def test_objection_limit_reached_total(self):
        """Test objection_limit_reached with total limit."""
        tracker = SimpleIntentTracker()
        tracker.set_category_total("objection", 5)
        ctx = create_test_context(intent_tracker=tracker)
        assert objection_limit_reached(ctx) is True

    def test_objection_limit_not_reached(self):
        """Test objection_limit_reached when not reached."""
        tracker = SimpleIntentTracker()
        tracker.set_category_streak("objection", 2)
        tracker.set_category_total("objection", 3)
        ctx = create_test_context(intent_tracker=tracker)
        assert objection_limit_reached(ctx) is False

    def test_objection_consecutive_3x(self):
        """Test objection_consecutive_3x."""
        tracker = SimpleIntentTracker()
        tracker.set_category_streak("objection", 3)
        ctx = create_test_context(intent_tracker=tracker)
        assert objection_consecutive_3x(ctx) is True

    def test_objection_total_5x(self):
        """Test objection_total_5x."""
        tracker = SimpleIntentTracker()
        tracker.set_category_total("objection", 5)
        ctx = create_test_context(intent_tracker=tracker)
        assert objection_total_5x(ctx) is True

    def test_is_current_intent_objection(self):
        """Test is_current_intent_objection."""
        ctx = create_test_context(current_intent="objection_price")
        assert is_current_intent_objection(ctx) is True

        ctx2 = create_test_context(current_intent="agreement")
        assert is_current_intent_objection(ctx2) is False

    def test_is_current_intent_positive(self):
        """Test is_current_intent_positive."""
        ctx = create_test_context(current_intent="agreement")
        assert is_current_intent_positive(ctx) is True

        ctx2 = create_test_context(current_intent="objection_price")
        assert is_current_intent_positive(ctx2) is False

    def test_is_current_intent_question(self):
        """Test is_current_intent_question."""
        ctx = create_test_context(current_intent="price_question")
        assert is_current_intent_question(ctx) is True

        ctx2 = create_test_context(current_intent="agreement")
        assert is_current_intent_question(ctx2) is False

    def test_is_spin_progress_intent(self):
        """Test is_spin_progress_intent."""
        ctx = create_test_context(current_intent="situation_provided")
        assert is_spin_progress_intent(ctx) is True

        ctx2 = create_test_context(current_intent="problem_revealed")
        assert is_spin_progress_intent(ctx2) is True

        ctx3 = create_test_context(current_intent="agreement")
        assert is_spin_progress_intent(ctx3) is False


# =============================================================================
# STATE CONDITIONS TESTS
# =============================================================================

class TestStateConditions:
    """Tests for state-related conditions."""

    def test_is_spin_state(self):
        """Test is_spin_state."""
        # SPIN_STATES is a dict: phase -> state_name
        # Use values (state names) for testing
        for state_name in SPIN_STATES.values():
            ctx = create_test_context(state=state_name)
            assert is_spin_state(ctx) is True, f"Failed for {state_name}"

        ctx_non_spin = create_test_context(state="presentation")
        assert is_spin_state(ctx_non_spin) is False

    def test_in_spin_phase(self):
        """Test in_spin_phase."""
        ctx = create_test_context(state="spin_situation")
        assert in_spin_phase(ctx) is True

        ctx_non = create_test_context(state="presentation")
        assert in_spin_phase(ctx_non) is False

    def test_in_situation_phase(self):
        """Test in_situation_phase."""
        ctx = create_test_context(state="spin_situation")
        assert in_situation_phase(ctx) is True

        ctx_other = create_test_context(state="spin_problem")
        assert in_situation_phase(ctx_other) is False

    def test_in_problem_phase(self):
        """Test in_problem_phase."""
        ctx = create_test_context(state="spin_problem")
        assert in_problem_phase(ctx) is True

        ctx_other = create_test_context(state="spin_situation")
        assert in_problem_phase(ctx_other) is False

    def test_in_implication_phase(self):
        """Test in_implication_phase."""
        ctx = create_test_context(state="spin_implication")
        assert in_implication_phase(ctx) is True

        ctx_other = create_test_context(state="spin_problem")
        assert in_implication_phase(ctx_other) is False

    def test_in_need_payoff_phase(self):
        """Test in_need_payoff_phase."""
        ctx = create_test_context(state="spin_need_payoff")
        assert in_need_payoff_phase(ctx) is True

        ctx_other = create_test_context(state="spin_implication")
        assert in_need_payoff_phase(ctx_other) is False

    def test_is_presentation_state(self):
        """Test is_presentation_state."""
        ctx = create_test_context(state="presentation")
        assert is_presentation_state(ctx) is True

        ctx_other = create_test_context(state="close")
        assert is_presentation_state(ctx_other) is False

    def test_is_close_state(self):
        """Test is_close_state."""
        ctx = create_test_context(state="close")
        assert is_close_state(ctx) is True

        ctx_other = create_test_context(state="presentation")
        assert is_close_state(ctx_other) is False

    def test_is_greeting_state(self):
        """Test is_greeting_state."""
        ctx = create_test_context(state="greeting")
        assert is_greeting_state(ctx) is True

        ctx_other = create_test_context(state="spin_situation")
        assert is_greeting_state(ctx_other) is False

    def test_is_handle_objection_state(self):
        """Test is_handle_objection_state."""
        ctx = create_test_context(state="handle_objection")
        assert is_handle_objection_state(ctx) is True

        ctx_other = create_test_context(state="presentation")
        assert is_handle_objection_state(ctx_other) is False

    def test_is_soft_close_state(self):
        """Test is_soft_close_state."""
        ctx = create_test_context(state="soft_close")
        assert is_soft_close_state(ctx) is True

        ctx_other = create_test_context(state="close")
        assert is_soft_close_state(ctx_other) is False

    def test_is_success_state(self):
        """Test is_success_state."""
        ctx = create_test_context(state="success")
        assert is_success_state(ctx) is True

        ctx_other = create_test_context(state="close")
        assert is_success_state(ctx_other) is False

    def test_is_terminal_state(self):
        """Test is_terminal_state."""
        for state in ["success", "soft_close", "failed"]:
            ctx = create_test_context(state=state)
            assert is_terminal_state(ctx) is True, f"Failed for {state}"

        ctx_non_terminal = create_test_context(state="close")
        assert is_terminal_state(ctx_non_terminal) is False

    def test_post_spin_phase(self):
        """Test post_spin_phase."""
        for state in ["presentation", "close", "handle_objection", "soft_close", "success", "failed"]:
            ctx = create_test_context(state=state)
            assert post_spin_phase(ctx) is True, f"Failed for {state}"

        # SPIN_STATES is a dict: phase -> state_name
        # Use values (state names) for testing
        for state_name in SPIN_STATES.values():
            ctx = create_test_context(state=state_name)
            assert post_spin_phase(ctx) is False, f"Should be False for {state_name}"


# =============================================================================
# TURN CONDITIONS TESTS
# =============================================================================

class TestTurnConditions:
    """Tests for turn-related conditions."""

    def test_is_first_turn(self):
        """Test is_first_turn."""
        ctx = create_test_context(turn_number=0)
        assert is_first_turn(ctx) is True

        ctx_not_first = create_test_context(turn_number=1)
        assert is_first_turn(ctx_not_first) is False

    def test_is_early_conversation(self):
        """Test is_early_conversation."""
        for turn in [0, 1, 2]:
            ctx = create_test_context(turn_number=turn)
            assert is_early_conversation(ctx) is True, f"Failed for turn {turn}"

        ctx_late = create_test_context(turn_number=3)
        assert is_early_conversation(ctx_late) is False

    def test_is_late_conversation(self):
        """Test is_late_conversation."""
        ctx = create_test_context(turn_number=10)
        assert is_late_conversation(ctx) is True

        ctx_early = create_test_context(turn_number=9)
        assert is_late_conversation(ctx_early) is False

    def test_is_extended_conversation(self):
        """Test is_extended_conversation."""
        ctx = create_test_context(turn_number=20)
        assert is_extended_conversation(ctx) is True

        ctx_not_extended = create_test_context(turn_number=19)
        assert is_extended_conversation(ctx_not_extended) is False


# =============================================================================
# COMBINED CONDITIONS TESTS
# =============================================================================

class TestCombinedConditions:
    """Tests for combined conditions."""

    def test_can_answer_price_with_data(self):
        """Test can_answer_price with pricing data."""
        ctx = create_test_context(collected_data={"company_size": 10})
        assert can_answer_price(ctx) is True

    def test_can_answer_price_with_repeated(self):
        """Test can_answer_price with repeated question."""
        tracker = SimpleIntentTracker()
        tracker.set_intent_streak("price_question", 3)
        ctx = create_test_context(intent_tracker=tracker)
        assert can_answer_price(ctx) is True

    def test_can_answer_price_no_data_no_repeat(self):
        """Test can_answer_price without data or repeats."""
        ctx = create_test_context()
        assert can_answer_price(ctx) is False

    def test_should_deflect_price_in_spin(self):
        """Test should_deflect_price in SPIN phase."""
        ctx = create_test_context(state="spin_situation")
        assert should_deflect_price(ctx) is True

    def test_should_deflect_price_with_data(self):
        """Test should_deflect_price with data (should not deflect)."""
        ctx = create_test_context(
            collected_data={"company_size": 10},
            state="spin_situation"
        )
        assert should_deflect_price(ctx) is False

    def test_should_deflect_price_after_repeats(self):
        """Test should_deflect_price after 3 repeats (should not deflect)."""
        tracker = SimpleIntentTracker()
        tracker.set_intent_streak("price_question", 3)
        ctx = create_test_context(
            intent_tracker=tracker,
            state="spin_situation"
        )
        assert should_deflect_price(ctx) is False

    def test_should_deflect_price_not_in_spin(self):
        """Test should_deflect_price not in SPIN (should not deflect)."""
        ctx = create_test_context(state="presentation")
        assert should_deflect_price(ctx) is False

    def test_ready_for_presentation(self):
        """Test ready_for_presentation."""
        ctx = create_test_context(
            collected_data={"company_size": 10, "pain_point": "losing"}
        )
        assert ready_for_presentation(ctx) is True

        ctx_missing = create_test_context(collected_data={"company_size": 10})
        assert ready_for_presentation(ctx_missing) is False

    def test_ready_for_close(self):
        """Test ready_for_close."""
        ctx = create_test_context(collected_data={"email": "test@example.com"})
        assert ready_for_close(ctx) is True

        ctx_no_contact = create_test_context()
        assert ready_for_close(ctx_no_contact) is False

    def test_can_handle_with_roi(self):
        """Test can_handle_with_roi."""
        ctx = create_test_context(
            collected_data={"pain_point": "losing", "company_size": 10}
        )
        assert can_handle_with_roi(ctx) is True

        ctx_missing = create_test_context(collected_data={"company_size": 10})
        assert can_handle_with_roi(ctx_missing) is False


# =============================================================================
# INTEGRATION TESTS
# =============================================================================

class TestIntegration:
    """Integration tests for StateMachine conditions."""

    def test_price_question_scenario_without_data(self):
        """Test price question scenario without pricing data."""
        ctx = create_test_context(
            state="spin_situation",
            current_intent="price_question"
        )

        # Should deflect
        assert should_deflect_price(ctx) is True
        assert can_answer_price(ctx) is False
        assert has_pricing_data(ctx) is False

    def test_price_question_scenario_with_data(self):
        """Test price question scenario with pricing data (BUG FIX)."""
        ctx = create_test_context(
            collected_data={"company_size": 10},
            state="spin_situation",
            current_intent="price_question"
        )

        # Should answer with facts (not deflect)
        assert should_deflect_price(ctx) is False
        assert can_answer_price(ctx) is True
        assert has_pricing_data(ctx) is True

    def test_price_question_scenario_repeated(self):
        """Test price question scenario with repeated asks."""
        tracker = SimpleIntentTracker()
        tracker.set_intent_streak("price_question", 3)

        ctx = create_test_context(
            state="spin_problem",
            current_intent="price_question",
            intent_tracker=tracker
        )

        # Should answer with range (not deflect)
        assert should_deflect_price(ctx) is False
        assert can_answer_price(ctx) is True
        assert price_repeated_3x(ctx) is True

    def test_objection_handling_with_roi_data(self):
        """Test objection handling with ROI data."""
        ctx = create_test_context(
            collected_data={
                "company_size": 10,
                "pain_point": "losing customers",
            },
            state="handle_objection",
            current_intent="objection_price"
        )

        assert is_current_intent_objection(ctx) is True
        assert can_handle_with_roi(ctx) is True

    def test_objection_limit_scenario(self):
        """Test objection limit reached scenario."""
        tracker = SimpleIntentTracker()
        tracker.set_category_streak("objection", 3)

        ctx = create_test_context(
            state="presentation",
            current_intent="objection_no_time",
            intent_tracker=tracker
        )

        assert is_current_intent_objection(ctx) is True
        assert objection_limit_reached(ctx) is True
        # Should transition to soft_close

    def test_demo_request_with_contact(self):
        """Test demo request scenario with contact info."""
        ctx = create_test_context(
            collected_data={"email": "test@example.com"},
            state="close",
            current_intent="demo_request"
        )

        assert is_close_state(ctx) is True
        assert has_contact_info(ctx) is True
        assert ready_for_close(ctx) is True
        # Should transition to success

    def test_demo_request_without_contact(self):
        """Test demo request scenario without contact info."""
        ctx = create_test_context(
            state="close",
            current_intent="demo_request"
        )

        assert is_close_state(ctx) is True
        assert has_contact_info(ctx) is False
        assert ready_for_close(ctx) is False
        # Should stay in current state

    def test_spin_progression(self):
        """Test SPIN phase progression detection."""
        # Situation phase
        ctx_sit = create_test_context(
            state="spin_situation",
            current_intent="situation_provided"
        )
        assert in_situation_phase(ctx_sit) is True
        assert is_spin_progress_intent(ctx_sit) is True

        # Problem phase
        ctx_prob = create_test_context(
            state="spin_problem",
            current_intent="problem_revealed"
        )
        assert in_problem_phase(ctx_prob) is True
        assert is_spin_progress_intent(ctx_prob) is True

        # Implication phase
        ctx_impl = create_test_context(
            state="spin_implication",
            current_intent="implication_acknowledged"
        )
        assert in_implication_phase(ctx_impl) is True
        assert is_spin_progress_intent(ctx_impl) is True

        # Need-Payoff phase
        ctx_need = create_test_context(
            state="spin_need_payoff",
            current_intent="need_expressed"
        )
        assert in_need_payoff_phase(ctx_need) is True
        assert is_spin_progress_intent(ctx_need) is True

    def test_conversation_phases(self):
        """Test conversation phase detection."""
        # First turn
        ctx_first = create_test_context(turn_number=0)
        assert is_first_turn(ctx_first) is True
        assert is_early_conversation(ctx_first) is True
        assert is_late_conversation(ctx_first) is False
        assert is_extended_conversation(ctx_first) is False

        # Early conversation
        ctx_early = create_test_context(turn_number=2)
        assert is_first_turn(ctx_early) is False
        assert is_early_conversation(ctx_early) is True
        assert is_late_conversation(ctx_early) is False

        # Late conversation
        ctx_late = create_test_context(turn_number=15)
        assert is_early_conversation(ctx_late) is False
        assert is_late_conversation(ctx_late) is True
        assert is_extended_conversation(ctx_late) is False

        # Extended conversation
        ctx_extended = create_test_context(turn_number=25)
        assert is_late_conversation(ctx_extended) is True
        assert is_extended_conversation(ctx_extended) is True


# =============================================================================
# DOCUMENTATION TESTS
# =============================================================================

class TestDocumentation:
    """Tests for documentation generation."""

    def test_registry_documentation(self):
        """Test that registry can generate documentation."""
        docs = sm_registry.get_documentation()

        assert "State Machine Conditions" in docs
        assert "EvaluatorContext" in docs
        assert "has_pricing_data" in docs
        assert "data" in docs.lower()
        assert "intent" in docs.lower()
        assert "state" in docs.lower()

    def test_registry_stats(self):
        """Test registry statistics."""
        stats = sm_registry.get_stats()

        assert stats["name"] == "state_machine"
        assert stats["total_conditions"] > 0
        assert stats["total_categories"] >= 5
        assert "data" in stats["conditions_by_category"]
        assert "intent" in stats["conditions_by_category"]


# =============================================================================
# EDGE CASES TESTS
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_empty_collected_data(self):
        """Test with completely empty collected_data."""
        ctx = create_test_context(collected_data={})

        assert has_pricing_data(ctx) is False
        assert has_contact_info(ctx) is False
        assert has_company_size(ctx) is False
        assert has_pain_point(ctx) is False
        assert has_competitor_mention(ctx) is False

    def test_falsy_values_in_collected_data(self):
        """Test with falsy values in collected_data."""
        ctx = create_test_context(
            collected_data={
                "company_size": 0,
                "email": "",
                "pain_point": None,
            }
        )

        # All should be False because values are falsy
        assert has_company_size(ctx) is False
        assert has_contact_info(ctx) is False
        assert has_pain_point(ctx) is False

    def test_none_intent_tracker(self):
        """Test with None intent tracker."""
        ctx = EvaluatorContext(
            state="greeting",
            turn_number=0,
            intent_tracker=None
        )

        # Should handle gracefully
        assert ctx.get_intent_streak("any") == 0
        assert ctx.get_intent_total("any") == 0
        assert ctx.get_category_streak("any") == 0
        assert ctx.get_category_total("any") == 0

    def test_unknown_state(self):
        """Test with unknown state."""
        ctx = create_test_context(state="unknown_state")

        assert is_spin_state(ctx) is False
        assert in_spin_phase(ctx) is False
        assert is_terminal_state(ctx) is False
        assert post_spin_phase(ctx) is False

    def test_boundary_turn_numbers(self):
        """Test boundary turn numbers."""
        # Exactly at boundaries
        ctx_3 = create_test_context(turn_number=3)
        assert is_early_conversation(ctx_3) is False

        ctx_10 = create_test_context(turn_number=10)
        assert is_late_conversation(ctx_10) is True

        ctx_20 = create_test_context(turn_number=20)
        assert is_extended_conversation(ctx_20) is True

    def test_boundary_streak_counts(self):
        """Test boundary streak counts."""
        tracker = SimpleIntentTracker()

        # Exactly at boundaries
        tracker.set_intent_streak("price_question", 2)
        ctx_2 = create_test_context(intent_tracker=tracker)
        assert price_repeated_2x(ctx_2) is True
        assert price_repeated_3x(ctx_2) is False

        tracker.set_intent_streak("price_question", 3)
        ctx_3 = create_test_context(intent_tracker=tracker)
        assert price_repeated_3x(ctx_3) is True

    def test_context_immutability(self):
        """Test that collected_data is copied in from_state_machine."""
        class MockSM:
            state = "greeting"
            collected_data = {"key": "value"}
            spin_phase = None
            turn_number = 0
            last_intent = None
            intent_tracker = None

        sm = MockSM()
        ctx = EvaluatorContext.from_state_machine(sm, "test", None)

        # Modify original
        sm.collected_data["key"] = "modified"

        # Context should have original value
        assert ctx.collected_data["key"] == "value"


# =============================================================================
# CONTEXT-AWARE CONDITIONS TESTS (Phase 5)
# =============================================================================

# Import new conditions
from src.conditions.state_machine import (
    client_frustrated,
    client_very_frustrated,
    client_stuck,
    client_oscillating,
    momentum_positive,
    momentum_negative,
    momentum_strong_positive,
    momentum_strong_negative,
    engagement_high,
    engagement_low,
    has_repeated_question,
    repeated_price_question,
    confidence_declining,
    many_objections,
    breakthrough_detected,
    in_breakthrough_window,
    guard_intervened,
    needs_repair,
    should_be_careful,
    can_accelerate,
    should_answer_directly,
)


class TestContextAwareConditions:
    """Tests for context-aware conditions based on ContextEnvelope signals."""

    # =========================================================================
    # Frustration conditions
    # =========================================================================

    def test_client_frustrated_true(self):
        """Test client_frustrated returns True for frustration >= 3."""
        ctx = create_test_context(frustration_level=3)
        assert client_frustrated(ctx) is True

        ctx_high = create_test_context(frustration_level=5)
        assert client_frustrated(ctx_high) is True

    def test_client_frustrated_false(self):
        """Test client_frustrated returns False for frustration < 3."""
        ctx = create_test_context(frustration_level=0)
        assert client_frustrated(ctx) is False

        ctx_low = create_test_context(frustration_level=2)
        assert client_frustrated(ctx_low) is False

    def test_client_very_frustrated(self):
        """Test client_very_frustrated for frustration >= 4."""
        ctx_3 = create_test_context(frustration_level=3)
        assert client_very_frustrated(ctx_3) is False

        ctx_4 = create_test_context(frustration_level=4)
        assert client_very_frustrated(ctx_4) is True

        ctx_5 = create_test_context(frustration_level=5)
        assert client_very_frustrated(ctx_5) is True

    # =========================================================================
    # Stuck and oscillation conditions
    # =========================================================================

    def test_client_stuck(self):
        """Test client_stuck condition."""
        ctx_stuck = create_test_context(is_stuck=True)
        assert client_stuck(ctx_stuck) is True

        ctx_not_stuck = create_test_context(is_stuck=False)
        assert client_stuck(ctx_not_stuck) is False

    def test_client_oscillating(self):
        """Test client_oscillating condition."""
        ctx_osc = create_test_context(has_oscillation=True)
        assert client_oscillating(ctx_osc) is True

        ctx_no_osc = create_test_context(has_oscillation=False)
        assert client_oscillating(ctx_no_osc) is False

    # =========================================================================
    # Momentum conditions
    # =========================================================================

    def test_momentum_positive(self):
        """Test momentum_positive condition."""
        ctx_pos = create_test_context(momentum_direction="positive")
        assert momentum_positive(ctx_pos) is True

        ctx_neg = create_test_context(momentum_direction="negative")
        assert momentum_positive(ctx_neg) is False

        ctx_neutral = create_test_context(momentum_direction="neutral")
        assert momentum_positive(ctx_neutral) is False

    def test_momentum_negative(self):
        """Test momentum_negative condition."""
        ctx_neg = create_test_context(momentum_direction="negative")
        assert momentum_negative(ctx_neg) is True

        ctx_pos = create_test_context(momentum_direction="positive")
        assert momentum_negative(ctx_pos) is False

    def test_momentum_strong_positive(self):
        """Test momentum_strong_positive for score > 0.5."""
        ctx_strong = create_test_context(momentum=0.7)
        assert momentum_strong_positive(ctx_strong) is True

        ctx_weak = create_test_context(momentum=0.3)
        assert momentum_strong_positive(ctx_weak) is False

        ctx_boundary = create_test_context(momentum=0.5)
        assert momentum_strong_positive(ctx_boundary) is False

    def test_momentum_strong_negative(self):
        """Test momentum_strong_negative for score < -0.5."""
        ctx_strong = create_test_context(momentum=-0.7)
        assert momentum_strong_negative(ctx_strong) is True

        ctx_weak = create_test_context(momentum=-0.3)
        assert momentum_strong_negative(ctx_weak) is False

    # =========================================================================
    # Engagement conditions
    # =========================================================================

    def test_engagement_high(self):
        """Test engagement_high condition."""
        ctx_high = create_test_context(engagement_level="high")
        assert engagement_high(ctx_high) is True

        ctx_medium = create_test_context(engagement_level="medium")
        assert engagement_high(ctx_medium) is False

    def test_engagement_low(self):
        """Test engagement_low condition."""
        ctx_low = create_test_context(engagement_level="low")
        assert engagement_low(ctx_low) is True

        ctx_disengaged = create_test_context(engagement_level="disengaged")
        assert engagement_low(ctx_disengaged) is True

        ctx_medium = create_test_context(engagement_level="medium")
        assert engagement_low(ctx_medium) is False

    # =========================================================================
    # Repeated question conditions
    # =========================================================================

    def test_has_repeated_question(self):
        """Test has_repeated_question condition."""
        ctx_repeated = create_test_context(repeated_question="price_question")
        assert has_repeated_question(ctx_repeated) is True

        ctx_no_repeat = create_test_context(repeated_question=None)
        assert has_repeated_question(ctx_no_repeat) is False

    def test_repeated_price_question(self):
        """Test repeated_price_question condition."""
        ctx_price = create_test_context(repeated_question="price_question")
        assert repeated_price_question(ctx_price) is True

        ctx_pricing = create_test_context(repeated_question="pricing_details")
        assert repeated_price_question(ctx_pricing) is True

        ctx_other = create_test_context(repeated_question="question_features")
        assert repeated_price_question(ctx_other) is False

        ctx_none = create_test_context(repeated_question=None)
        assert repeated_price_question(ctx_none) is False

    # =========================================================================
    # Confidence conditions
    # =========================================================================

    def test_confidence_declining(self):
        """Test confidence_declining condition."""
        ctx_declining = create_test_context(confidence_trend="decreasing")
        assert confidence_declining(ctx_declining) is True

        ctx_stable = create_test_context(confidence_trend="stable")
        assert confidence_declining(ctx_stable) is False

        ctx_increasing = create_test_context(confidence_trend="increasing")
        assert confidence_declining(ctx_increasing) is False

    # =========================================================================
    # Objection conditions
    # =========================================================================

    def test_many_objections(self):
        """Test many_objections for total >= 3."""
        ctx_many = create_test_context(total_objections=3)
        assert many_objections(ctx_many) is True

        ctx_more = create_test_context(total_objections=5)
        assert many_objections(ctx_more) is True

        ctx_few = create_test_context(total_objections=2)
        assert many_objections(ctx_few) is False

    # =========================================================================
    # Breakthrough conditions
    # =========================================================================

    def test_breakthrough_detected(self):
        """Test breakthrough_detected condition."""
        ctx_bt = create_test_context(has_breakthrough=True)
        assert breakthrough_detected(ctx_bt) is True

        ctx_no_bt = create_test_context(has_breakthrough=False)
        assert breakthrough_detected(ctx_no_bt) is False

    def test_in_breakthrough_window(self):
        """Test in_breakthrough_window for 1-3 turns after breakthrough."""
        # In window (1-3 turns)
        ctx_1 = create_test_context(has_breakthrough=True, turns_since_breakthrough=1)
        assert in_breakthrough_window(ctx_1) is True

        ctx_2 = create_test_context(has_breakthrough=True, turns_since_breakthrough=2)
        assert in_breakthrough_window(ctx_2) is True

        ctx_3 = create_test_context(has_breakthrough=True, turns_since_breakthrough=3)
        assert in_breakthrough_window(ctx_3) is True

        # Outside window
        ctx_0 = create_test_context(has_breakthrough=True, turns_since_breakthrough=0)
        assert in_breakthrough_window(ctx_0) is False

        ctx_4 = create_test_context(has_breakthrough=True, turns_since_breakthrough=4)
        assert in_breakthrough_window(ctx_4) is False

        # No breakthrough
        ctx_no_bt = create_test_context(has_breakthrough=False, turns_since_breakthrough=2)
        assert in_breakthrough_window(ctx_no_bt) is False

        # None turns_since
        ctx_none = create_test_context(has_breakthrough=True, turns_since_breakthrough=None)
        assert in_breakthrough_window(ctx_none) is False

    # =========================================================================
    # Guard conditions
    # =========================================================================

    def test_guard_intervened(self):
        """Test guard_intervened condition."""
        ctx_guard = create_test_context(guard_intervention="empathize")
        assert guard_intervened(ctx_guard) is True

        ctx_no_guard = create_test_context(guard_intervention=None)
        assert guard_intervened(ctx_no_guard) is False

    # =========================================================================
    # Combined conditions
    # =========================================================================

    def test_needs_repair(self):
        """Test needs_repair combined condition."""
        # Stuck
        ctx_stuck = create_test_context(is_stuck=True)
        assert needs_repair(ctx_stuck) is True

        # Oscillating
        ctx_osc = create_test_context(has_oscillation=True)
        assert needs_repair(ctx_osc) is True

        # Repeated question
        ctx_repeat = create_test_context(repeated_question="price_question")
        assert needs_repair(ctx_repeat) is True

        # None of the above
        ctx_ok = create_test_context(
            is_stuck=False, has_oscillation=False, repeated_question=None
        )
        assert needs_repair(ctx_ok) is False

    def test_should_be_careful(self):
        """Test should_be_careful combined condition."""
        # Frustrated (level >= 2)
        ctx_frust = create_test_context(frustration_level=2)
        assert should_be_careful(ctx_frust) is True

        # Negative momentum
        ctx_neg = create_test_context(momentum_direction="negative")
        assert should_be_careful(ctx_neg) is True

        # Both ok
        ctx_ok = create_test_context(
            frustration_level=1, momentum_direction="neutral"
        )
        assert should_be_careful(ctx_ok) is False

    def test_can_accelerate(self):
        """Test can_accelerate combined condition."""
        # All conditions met
        ctx_ok = create_test_context(
            momentum_direction="positive",
            engagement_level="high",
            frustration_level=0
        )
        assert can_accelerate(ctx_ok) is True

        # Missing positive momentum
        ctx_no_mom = create_test_context(
            momentum_direction="neutral",
            engagement_level="high",
            frustration_level=0
        )
        assert can_accelerate(ctx_no_mom) is False

        # Missing high engagement
        ctx_no_eng = create_test_context(
            momentum_direction="positive",
            engagement_level="medium",
            frustration_level=0
        )
        assert can_accelerate(ctx_no_eng) is False

        # Has frustration
        ctx_frust = create_test_context(
            momentum_direction="positive",
            engagement_level="high",
            frustration_level=1
        )
        assert can_accelerate(ctx_frust) is False

    def test_should_answer_directly(self):
        """Test should_answer_directly combined condition."""
        # Frustrated
        ctx_frust = create_test_context(frustration_level=2)
        assert should_answer_directly(ctx_frust) is True

        # Repeated question
        ctx_repeat = create_test_context(repeated_question="price_question")
        assert should_answer_directly(ctx_repeat) is True

        # Declining confidence
        ctx_conf = create_test_context(confidence_trend="decreasing")
        assert should_answer_directly(ctx_conf) is True

        # None of the above
        ctx_ok = create_test_context(
            frustration_level=0,
            repeated_question=None,
            confidence_trend="stable"
        )
        assert should_answer_directly(ctx_ok) is False


# =============================================================================
# CONFIGURABLE OBJECTION LIMITS TESTS
# =============================================================================

class TestConfigurableObjectionLimits:
    """
    Tests for configurable objection limits.

    These tests verify that objection limits are properly:
    1. Read from YAML config (constants.yaml)
    2. Passed through EvaluatorContext
    3. Used in condition functions instead of hardcoded values
    """

    def test_default_limits_from_yaml(self):
        """Test that default limits come from YAML config."""
        from src.yaml_config.constants import (
            MAX_CONSECUTIVE_OBJECTIONS,
            MAX_TOTAL_OBJECTIONS,
        )

        ctx = create_test_context()

        # Default limits should match YAML config
        assert ctx.max_consecutive_objections == MAX_CONSECUTIVE_OBJECTIONS
        assert ctx.max_total_objections == MAX_TOTAL_OBJECTIONS

    def test_custom_limits_in_context(self):
        """Test that custom limits can be passed to context."""
        # Create context with custom limits
        ctx = create_test_context(
            max_consecutive_objections=5,
            max_total_objections=10,
        )

        assert ctx.max_consecutive_objections == 5
        assert ctx.max_total_objections == 10

    def test_objection_limit_reached_respects_custom_consecutive(self):
        """Test objection_limit_reached uses custom consecutive limit."""
        tracker = SimpleIntentTracker()
        tracker.set_category_streak("objection", 4)
        tracker.set_category_total("objection", 2)

        # With default limit (3), this should trigger
        ctx_default = create_test_context(intent_tracker=tracker)
        assert objection_limit_reached(ctx_default) is True

        # With higher custom limit (5), this should NOT trigger
        tracker2 = SimpleIntentTracker()
        tracker2.set_category_streak("objection", 4)
        tracker2.set_category_total("objection", 2)
        ctx_custom = create_test_context(
            intent_tracker=tracker2,
            max_consecutive_objections=5,
            max_total_objections=10,
        )
        assert objection_limit_reached(ctx_custom) is False

    def test_objection_limit_reached_respects_custom_total(self):
        """Test objection_limit_reached uses custom total limit."""
        tracker = SimpleIntentTracker()
        tracker.set_category_streak("objection", 1)
        tracker.set_category_total("objection", 6)

        # With default limit (5), this should trigger
        ctx_default = create_test_context(intent_tracker=tracker)
        assert objection_limit_reached(ctx_default) is True

        # With higher custom limit (10), this should NOT trigger
        tracker2 = SimpleIntentTracker()
        tracker2.set_category_streak("objection", 1)
        tracker2.set_category_total("objection", 6)
        ctx_custom = create_test_context(
            intent_tracker=tracker2,
            max_consecutive_objections=5,
            max_total_objections=10,
        )
        assert objection_limit_reached(ctx_custom) is False

    def test_objection_consecutive_3x_respects_custom_limit(self):
        """Test objection_consecutive_3x uses context limit."""
        tracker = SimpleIntentTracker()
        tracker.set_category_streak("objection", 4)

        # With custom limit of 5, should NOT trigger
        ctx = create_test_context(
            intent_tracker=tracker,
            max_consecutive_objections=5,
        )
        assert objection_consecutive_3x(ctx) is False

        # With custom limit of 4, should trigger (exactly at limit)
        tracker2 = SimpleIntentTracker()
        tracker2.set_category_streak("objection", 4)
        ctx2 = create_test_context(
            intent_tracker=tracker2,
            max_consecutive_objections=4,
        )
        assert objection_consecutive_3x(ctx2) is True

    def test_objection_total_5x_respects_custom_limit(self):
        """Test objection_total_5x uses context limit."""
        tracker = SimpleIntentTracker()
        tracker.set_category_total("objection", 7)

        # With custom limit of 10, should NOT trigger
        ctx = create_test_context(
            intent_tracker=tracker,
            max_total_objections=10,
        )
        assert objection_total_5x(ctx) is False

        # With custom limit of 7, should trigger (exactly at limit)
        tracker2 = SimpleIntentTracker()
        tracker2.set_category_total("objection", 7)
        ctx2 = create_test_context(
            intent_tracker=tracker2,
            max_total_objections=7,
        )
        assert objection_total_5x(ctx2) is True

    def test_limits_from_state_machine(self):
        """Test that limits are extracted from state_machine."""

        class MockStateMachine:
            state = "greeting"
            collected_data = {}
            spin_phase = None
            turn_number = 0
            last_intent = None
            intent_tracker = None
            # Custom limits
            max_consecutive_objections = 4
            max_total_objections = 8

        sm = MockStateMachine()
        ctx = EvaluatorContext.from_state_machine(sm, "test", None)

        assert ctx.max_consecutive_objections == 4
        assert ctx.max_total_objections == 8

    def test_limits_fallback_when_not_in_state_machine(self):
        """Test fallback to YAML defaults when state_machine has no limits."""
        from src.yaml_config.constants import (
            MAX_CONSECUTIVE_OBJECTIONS,
            MAX_TOTAL_OBJECTIONS,
        )

        class MockStateMachine:
            state = "greeting"
            collected_data = {}
            spin_phase = None
            turn_number = 0
            last_intent = None
            intent_tracker = None
            # No max_consecutive_objections or max_total_objections

        sm = MockStateMachine()
        ctx = EvaluatorContext.from_state_machine(sm, "test", None)

        # Should fall back to YAML defaults
        assert ctx.max_consecutive_objections == MAX_CONSECUTIVE_OBJECTIONS
        assert ctx.max_total_objections == MAX_TOTAL_OBJECTIONS

    def test_edge_case_zero_limits(self):
        """Test edge case with zero limits (immediate trigger)."""
        tracker = SimpleIntentTracker()
        tracker.set_category_streak("objection", 0)
        tracker.set_category_total("objection", 0)

        # With zero limits, even 0 objections should trigger
        ctx = create_test_context(
            intent_tracker=tracker,
            max_consecutive_objections=0,
            max_total_objections=0,
        )

        assert objection_limit_reached(ctx) is True
        assert objection_consecutive_3x(ctx) is True
        assert objection_total_5x(ctx) is True

    def test_edge_case_very_high_limits(self):
        """Test edge case with very high limits (never trigger)."""
        tracker = SimpleIntentTracker()
        tracker.set_category_streak("objection", 100)
        tracker.set_category_total("objection", 100)

        # With very high limits, even 100 objections should NOT trigger
        ctx = create_test_context(
            intent_tracker=tracker,
            max_consecutive_objections=1000,
            max_total_objections=1000,
        )

        assert objection_limit_reached(ctx) is False
        assert objection_consecutive_3x(ctx) is False
        assert objection_total_5x(ctx) is False
