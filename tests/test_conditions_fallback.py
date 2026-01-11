"""
Tests for Fallback Domain Conditions.

This module provides comprehensive tests for:
- FallbackContext (context.py)
- fallback_registry (registry.py)
- All condition functions (conditions.py)
- FallbackHandler integration

Part of Phase 6: Fallback Domain (ARCHITECTURE_UNIFIED_PLAN.md)
"""

import pytest
from typing import Dict, Any

from src.conditions.fallback import (
    # Context
    FallbackContext,
    FALLBACK_TIERS,
    DYNAMIC_CTA_STATES,
    PAIN_CATEGORIES,
    SMALL_COMPANY_THRESHOLD,
    LARGE_COMPANY_THRESHOLD,
    # Registry
    fallback_registry,
    fallback_condition,
    get_fallback_registry,
    # Tier conditions
    should_escalate_tier,
    is_tier_1,
    is_tier_2,
    is_tier_3,
    is_soft_close,
    is_max_tier,
    too_many_fallbacks,
    many_fallbacks_in_state,
    consecutive_fallbacks_2_plus,
    first_fallback_in_state,
    # Dynamic CTA conditions
    should_use_dynamic_cta,
    has_competitor_context,
    has_pain_context,
    has_pain_losing_clients,
    has_pain_no_control,
    has_pain_manual_work,
    last_intent_price_related,
    last_intent_feature_related,
    # Context conditions
    is_small_company,
    is_large_company,
    has_company_size,
    has_contextual_data,
    has_rich_context,
    # Frustration conditions
    frustration_high,
    frustration_critical,
    frustration_low,
    engagement_low,
    engagement_high,
    momentum_negative,
    momentum_positive,
    should_offer_graceful_exit,
    # State conditions
    is_spin_state,
    is_dynamic_cta_state,
    is_presentation_state,
    is_close_state,
    is_handle_objection_state,
    is_greeting_state,
    # Combined conditions
    should_skip_to_next_state,
    can_try_rephrase,
    should_show_options,
    needs_immediate_escalation,
    can_recover,
    should_personalize_response,
)
from src.conditions import ConditionRegistries
from src.conditions.trace import EvaluationTrace


# =============================================================================
# TEST FIXTURES
# =============================================================================

@pytest.fixture
def empty_context():
    """Create an empty context for testing."""
    return FallbackContext.create_test_context()


@pytest.fixture
def tier_1_context():
    """Create a context in tier 1."""
    return FallbackContext.create_test_context(
        state="spin_situation",
        current_tier="fallback_tier_1",
        total_fallbacks=1,
        consecutive_fallbacks=1
    )


@pytest.fixture
def tier_2_context():
    """Create a context in tier 2."""
    return FallbackContext.create_test_context(
        state="spin_problem",
        current_tier="fallback_tier_2",
        total_fallbacks=3,
        consecutive_fallbacks=2
    )


@pytest.fixture
def high_frustration_context():
    """Create a context with high frustration."""
    return FallbackContext.create_test_context(
        state="spin_situation",
        current_tier="fallback_tier_2",
        total_fallbacks=5,
        frustration_level=4,
        engagement_level="low",
        momentum_direction="negative"
    )


@pytest.fixture
def competitor_context():
    """Create a context with competitor mentioned."""
    return FallbackContext.create_test_context(
        state="spin_situation",
        current_tier="fallback_tier_2",
        competitor_mentioned=True,
        company_size=10
    )


@pytest.fixture
def pain_context():
    """Create a context with pain category."""
    return FallbackContext.create_test_context(
        state="spin_problem",
        current_tier="fallback_tier_2",
        pain_category="losing_clients",
        company_size=15
    )


# =============================================================================
# CONTEXT TESTS
# =============================================================================

class TestFallbackContext:
    """Tests for FallbackContext class."""

    def test_create_empty_context(self):
        """Test creating empty context."""
        ctx = FallbackContext()
        assert ctx.collected_data == {}
        assert ctx.state == ""
        assert ctx.turn_number == 0
        assert ctx.total_fallbacks == 0
        assert ctx.current_tier == "fallback_tier_1"

    def test_create_context_with_data(self):
        """Test creating context with data."""
        ctx = FallbackContext(
            collected_data={"company_size": 10},
            state="spin_situation",
            turn_number=3,
            total_fallbacks=2,
            consecutive_fallbacks=1,
            current_tier="fallback_tier_2",
            frustration_level=2,
            competitor_mentioned=True
        )
        assert ctx.collected_data["company_size"] == 10
        assert ctx.state == "spin_situation"
        assert ctx.turn_number == 3
        assert ctx.total_fallbacks == 2
        assert ctx.current_tier == "fallback_tier_2"
        assert ctx.competitor_mentioned is True

    def test_negative_turn_number_raises(self):
        """Test that negative turn number raises ValueError."""
        with pytest.raises(ValueError, match="turn_number cannot be negative"):
            FallbackContext(turn_number=-1)

    def test_negative_total_fallbacks_raises(self):
        """Test that negative total_fallbacks raises ValueError."""
        with pytest.raises(ValueError, match="total_fallbacks cannot be negative"):
            FallbackContext(total_fallbacks=-1)

    def test_negative_consecutive_fallbacks_raises(self):
        """Test that negative consecutive_fallbacks raises ValueError."""
        with pytest.raises(ValueError, match="consecutive_fallbacks cannot be negative"):
            FallbackContext(consecutive_fallbacks=-1)

    def test_negative_frustration_raises(self):
        """Test that negative frustration raises ValueError."""
        with pytest.raises(ValueError, match="frustration_level cannot be negative"):
            FallbackContext(frustration_level=-1)

    def test_invalid_tier_raises(self):
        """Test that invalid tier raises ValueError."""
        with pytest.raises(ValueError, match="current_tier must be one of"):
            FallbackContext(current_tier="invalid_tier")

    def test_create_test_context(self):
        """Test create_test_context factory method."""
        ctx = FallbackContext.create_test_context(
            collected_data={"test": "data"},
            state="presentation",
            turn_number=10,
            total_fallbacks=3,
            current_tier="fallback_tier_2"
        )
        assert ctx.collected_data["test"] == "data"
        assert ctx.state == "presentation"
        assert ctx.turn_number == 10
        assert ctx.total_fallbacks == 3
        assert ctx.current_tier == "fallback_tier_2"

    def test_get_tier_index(self):
        """Test get_tier_index method."""
        ctx_1 = FallbackContext.create_test_context(current_tier="fallback_tier_1")
        assert ctx_1.get_tier_index() == 0

        ctx_2 = FallbackContext.create_test_context(current_tier="fallback_tier_2")
        assert ctx_2.get_tier_index() == 1

        ctx_3 = FallbackContext.create_test_context(current_tier="fallback_tier_3")
        assert ctx_3.get_tier_index() == 2

        ctx_close = FallbackContext.create_test_context(current_tier="soft_close")
        assert ctx_close.get_tier_index() == 3

    def test_is_max_tier(self):
        """Test is_max_tier method."""
        ctx_1 = FallbackContext.create_test_context(current_tier="fallback_tier_1")
        assert ctx_1.is_max_tier() is False

        ctx_close = FallbackContext.create_test_context(current_tier="soft_close")
        assert ctx_close.is_max_tier() is True

    def test_is_dynamic_cta_state(self):
        """Test is_dynamic_cta_state method."""
        for state in DYNAMIC_CTA_STATES:
            ctx = FallbackContext.create_test_context(state=state)
            assert ctx.is_dynamic_cta_state() is True, f"Failed for {state}"

        ctx_other = FallbackContext.create_test_context(state="greeting")
        assert ctx_other.is_dynamic_cta_state() is False

    def test_is_small_company(self):
        """Test is_small_company method."""
        ctx_small = FallbackContext.create_test_context(company_size=3)
        assert ctx_small.is_small_company() is True

        ctx_boundary = FallbackContext.create_test_context(company_size=5)
        assert ctx_boundary.is_small_company() is True

        ctx_medium = FallbackContext.create_test_context(company_size=10)
        assert ctx_medium.is_small_company() is False

        ctx_none = FallbackContext.create_test_context(company_size=None)
        assert ctx_none.is_small_company() is False

    def test_is_large_company(self):
        """Test is_large_company method."""
        ctx_large = FallbackContext.create_test_context(company_size=30)
        assert ctx_large.is_large_company() is True

        ctx_boundary = FallbackContext.create_test_context(company_size=20)
        assert ctx_boundary.is_large_company() is False  # Not > 20

        ctx_small = FallbackContext.create_test_context(company_size=10)
        assert ctx_small.is_large_company() is False

        ctx_none = FallbackContext.create_test_context(company_size=None)
        assert ctx_none.is_large_company() is False

    def test_has_pain_category(self):
        """Test has_pain_category method."""
        for category in PAIN_CATEGORIES:
            ctx = FallbackContext.create_test_context(pain_category=category)
            assert ctx.has_pain_category() is True, f"Failed for {category}"

        ctx_invalid = FallbackContext.create_test_context(pain_category="invalid")
        assert ctx_invalid.has_pain_category() is False

        ctx_none = FallbackContext.create_test_context(pain_category=None)
        assert ctx_none.has_pain_category() is False

    def test_to_dict(self):
        """Test to_dict method."""
        ctx = FallbackContext.create_test_context(
            state="spin_situation",
            turn_number=5,
            total_fallbacks=3,
            frustration_level=2,
            competitor_mentioned=True
        )
        d = ctx.to_dict()

        assert d["state"] == "spin_situation"
        assert d["turn_number"] == 5
        assert d["total_fallbacks"] == 3
        assert d["frustration_level"] == 2
        assert d["competitor_mentioned"] is True
        assert "momentum_direction" in d
        assert "engagement_level" in d

    def test_repr(self):
        """Test __repr__ method."""
        ctx = FallbackContext.create_test_context(
            state="spin_problem",
            current_tier="fallback_tier_2",
            total_fallbacks=3,
            consecutive_fallbacks=2,
            frustration_level=2
        )
        repr_str = repr(ctx)
        assert "spin_problem" in repr_str
        assert "fallback_tier_2" in repr_str
        assert "total_fallbacks=3" in repr_str


class TestFallbackContextFromEnvelope:
    """Tests for creating FallbackContext from ContextEnvelope."""

    def test_from_envelope(self):
        """Test creating context from envelope mock."""
        class MockEnvelope:
            collected_data = {"company_size": 10, "pain_category": "losing_clients"}
            state = "spin_situation"
            total_turns = 5
            frustration_level = 2
            momentum_direction = "positive"
            engagement_level = "high"
            last_intent = "info_provided"

        envelope = MockEnvelope()
        stats = {
            "total_count": 3,
            "tier_counts": {"fallback_tier_2": 2},
            "state_counts": {"spin_situation": 2}
        }

        ctx = FallbackContext.from_envelope(envelope, stats, "fallback_tier_2")

        assert ctx.collected_data["company_size"] == 10
        assert ctx.state == "spin_situation"
        assert ctx.turn_number == 5
        assert ctx.total_fallbacks == 3
        assert ctx.consecutive_fallbacks == 2
        assert ctx.frustration_level == 2
        assert ctx.momentum_direction == "positive"
        assert ctx.engagement_level == "high"
        assert ctx.pain_category == "losing_clients"
        assert ctx.company_size == 10

    def test_from_envelope_with_last_successful_intent(self):
        """Test from_envelope with last_successful_intent attribute."""
        class MockEnvelope:
            collected_data = {}
            state = "spin_problem"
            total_turns = 3
            frustration_level = 0
            momentum_direction = "neutral"
            engagement_level = "medium"
            last_intent = "answer"
            last_successful_intent = "question_features"

        envelope = MockEnvelope()
        stats = {"total_count": 1, "tier_counts": {}, "state_counts": {}}

        ctx = FallbackContext.from_envelope(envelope, stats)

        assert ctx.last_successful_intent == "question_features"

    def test_from_envelope_string_company_size(self):
        """Test from_envelope converts string company_size to int."""
        class MockEnvelope:
            collected_data = {"company_size": "15"}
            state = "spin_situation"
            total_turns = 1
            frustration_level = 0
            momentum_direction = "neutral"
            engagement_level = "medium"
            last_intent = None

        envelope = MockEnvelope()
        stats = {"total_count": 1, "tier_counts": {}, "state_counts": {}}

        ctx = FallbackContext.from_envelope(envelope, stats)

        assert ctx.company_size == 15

    def test_from_envelope_invalid_string_company_size(self):
        """Test from_envelope handles invalid string company_size."""
        class MockEnvelope:
            collected_data = {"company_size": "large"}
            state = "spin_situation"
            total_turns = 1
            frustration_level = 0
            momentum_direction = "neutral"
            engagement_level = "medium"
            last_intent = None

        envelope = MockEnvelope()
        stats = {"total_count": 1, "tier_counts": {}, "state_counts": {}}

        ctx = FallbackContext.from_envelope(envelope, stats)

        assert ctx.company_size is None


class TestFallbackContextFromHandlerStats:
    """Tests for creating FallbackContext from handler stats."""

    def test_from_handler_stats(self):
        """Test creating context from handler stats."""
        stats = {
            "total_count": 5,
            "tier_counts": {"fallback_tier_2": 2},
            "state_counts": {"spin_situation": 3}
        }
        context = {
            "collected_data": {"company_size": 10, "pain_category": "losing_clients"},
            "turn_number": 5,
            "frustration_level": 2,
            "momentum_direction": "negative",
            "engagement_level": "low",
            "last_intent": "price_question"
        }

        ctx = FallbackContext.from_handler_stats(
            stats=stats,
            state="spin_situation",
            context=context,
            current_tier="fallback_tier_2"
        )

        assert ctx.total_fallbacks == 5
        assert ctx.consecutive_fallbacks == 2
        assert ctx.fallbacks_in_state == 3
        assert ctx.company_size == 10
        assert ctx.pain_category == "losing_clients"
        assert ctx.frustration_level == 2
        assert ctx.last_intent == "price_question"

    def test_from_handler_stats_company_size_string(self):
        """Test that company_size string is converted to int."""
        stats = {"total_count": 1, "tier_counts": {}, "state_counts": {}}
        context = {
            "collected_data": {"company_size": "15"}
        }

        ctx = FallbackContext.from_handler_stats(
            stats=stats,
            state="spin_situation",
            context=context,
            current_tier="fallback_tier_1"
        )

        assert ctx.company_size == 15

    def test_from_handler_stats_invalid_company_size_string(self):
        """Test that invalid company_size string becomes None."""
        stats = {"total_count": 1, "tier_counts": {}, "state_counts": {}}
        context = {
            "collected_data": {"company_size": "large"}
        }

        ctx = FallbackContext.from_handler_stats(
            stats=stats,
            state="spin_situation",
            context=context,
            current_tier="fallback_tier_1"
        )

        assert ctx.company_size is None


class TestConstants:
    """Tests for module constants."""

    def test_fallback_tiers(self):
        """Test FALLBACK_TIERS constant."""
        assert len(FALLBACK_TIERS) == 4
        assert FALLBACK_TIERS[0] == "fallback_tier_1"
        assert FALLBACK_TIERS[1] == "fallback_tier_2"
        assert FALLBACK_TIERS[2] == "fallback_tier_3"
        assert FALLBACK_TIERS[3] == "soft_close"

    def test_dynamic_cta_states(self):
        """Test DYNAMIC_CTA_STATES constant."""
        assert "spin_situation" in DYNAMIC_CTA_STATES
        assert "spin_problem" in DYNAMIC_CTA_STATES
        assert "presentation" in DYNAMIC_CTA_STATES
        assert "greeting" not in DYNAMIC_CTA_STATES

    def test_pain_categories(self):
        """Test PAIN_CATEGORIES constant."""
        assert "losing_clients" in PAIN_CATEGORIES
        assert "no_control" in PAIN_CATEGORIES
        assert "manual_work" in PAIN_CATEGORIES

    def test_thresholds(self):
        """Test company size thresholds."""
        assert SMALL_COMPANY_THRESHOLD == 5
        assert LARGE_COMPANY_THRESHOLD == 20


# =============================================================================
# REGISTRY TESTS
# =============================================================================

class TestFallbackRegistry:
    """Tests for Fallback registry."""

    def test_registry_exists(self):
        """Test that fallback_registry is properly created."""
        assert fallback_registry is not None
        assert fallback_registry.name == "fallback"
        assert len(fallback_registry) > 0

    def test_get_fallback_registry(self):
        """Test get_fallback_registry function."""
        reg = get_fallback_registry()
        assert reg is fallback_registry

    def test_registry_has_expected_conditions(self):
        """Test that registry has all expected conditions."""
        expected = [
            "should_escalate_tier",
            "is_tier_1",
            "is_tier_2",
            "should_use_dynamic_cta",
            "has_competitor_context",
            "frustration_high",
            "needs_immediate_escalation",
            "can_recover",
        ]
        for name in expected:
            assert fallback_registry.has(name), f"Missing condition: {name}"

    def test_registry_categories(self):
        """Test that registry has expected categories."""
        categories = fallback_registry.get_categories()
        assert "tier" in categories
        assert "dynamic_cta" in categories
        assert "context" in categories
        assert "frustration" in categories
        assert "state" in categories
        assert "combined" in categories

    def test_evaluate_through_registry(self):
        """Test evaluating conditions through registry."""
        ctx = FallbackContext.create_test_context(current_tier="fallback_tier_1")
        assert fallback_registry.evaluate("is_tier_1", ctx) is True

        ctx_2 = FallbackContext.create_test_context(current_tier="fallback_tier_2")
        assert fallback_registry.evaluate("is_tier_1", ctx_2) is False

    def test_evaluate_with_trace(self):
        """Test evaluating with trace."""
        ctx = FallbackContext.create_test_context(
            current_tier="fallback_tier_1",
            total_fallbacks=1
        )
        trace = EvaluationTrace(rule_name="tier_check")

        result = fallback_registry.evaluate("is_tier_1", ctx, trace)

        assert result is True
        assert len(trace.entries) == 1
        assert trace.entries[0].condition_name == "is_tier_1"
        assert trace.entries[0].result is True

    def test_registry_in_condition_registries(self):
        """Test that Fallback registry is in ConditionRegistries."""
        assert ConditionRegistries.has_condition("should_escalate_tier")
        assert ConditionRegistries.find_condition("should_escalate_tier") == "fallback"
        assert ConditionRegistries.get("fallback") is fallback_registry

    def test_validate_all(self):
        """Test validate_all method."""
        result = fallback_registry.validate_all(
            lambda: FallbackContext.create_test_context()
        )
        assert result.is_valid
        assert len(result.passed) == len(fallback_registry)
        assert len(result.failed) == 0
        assert len(result.errors) == 0


# =============================================================================
# TIER CONDITIONS TESTS
# =============================================================================

class TestTierConditions:
    """Tests for tier-related conditions."""

    def test_should_escalate_tier_consecutive(self):
        """Test should_escalate_tier with consecutive fallbacks."""
        ctx = FallbackContext.create_test_context(consecutive_fallbacks=2)
        assert should_escalate_tier(ctx) is True

        ctx_low = FallbackContext.create_test_context(consecutive_fallbacks=1)
        assert should_escalate_tier(ctx_low) is False

    def test_should_escalate_tier_frustration(self):
        """Test should_escalate_tier with high frustration."""
        ctx = FallbackContext.create_test_context(
            consecutive_fallbacks=1,
            frustration_level=3
        )
        assert should_escalate_tier(ctx) is True

    def test_is_tier_1(self):
        """Test is_tier_1 condition."""
        ctx = FallbackContext.create_test_context(current_tier="fallback_tier_1")
        assert is_tier_1(ctx) is True

        ctx_2 = FallbackContext.create_test_context(current_tier="fallback_tier_2")
        assert is_tier_1(ctx_2) is False

    def test_is_tier_2(self):
        """Test is_tier_2 condition."""
        ctx = FallbackContext.create_test_context(current_tier="fallback_tier_2")
        assert is_tier_2(ctx) is True

        ctx_1 = FallbackContext.create_test_context(current_tier="fallback_tier_1")
        assert is_tier_2(ctx_1) is False

    def test_is_tier_3(self):
        """Test is_tier_3 condition."""
        ctx = FallbackContext.create_test_context(current_tier="fallback_tier_3")
        assert is_tier_3(ctx) is True

    def test_is_soft_close(self):
        """Test is_soft_close condition."""
        ctx = FallbackContext.create_test_context(current_tier="soft_close")
        assert is_soft_close(ctx) is True

    def test_is_max_tier(self):
        """Test is_max_tier condition."""
        ctx = FallbackContext.create_test_context(current_tier="soft_close")
        assert is_max_tier(ctx) is True

        ctx_3 = FallbackContext.create_test_context(current_tier="fallback_tier_3")
        assert is_max_tier(ctx_3) is False

    def test_too_many_fallbacks(self):
        """Test too_many_fallbacks condition."""
        ctx = FallbackContext.create_test_context(total_fallbacks=5)
        assert too_many_fallbacks(ctx) is True

        ctx_low = FallbackContext.create_test_context(total_fallbacks=4)
        assert too_many_fallbacks(ctx_low) is False

    def test_many_fallbacks_in_state(self):
        """Test many_fallbacks_in_state condition."""
        ctx = FallbackContext.create_test_context(fallbacks_in_state=3)
        assert many_fallbacks_in_state(ctx) is True

        ctx_low = FallbackContext.create_test_context(fallbacks_in_state=2)
        assert many_fallbacks_in_state(ctx_low) is False

    def test_consecutive_fallbacks_2_plus(self):
        """Test consecutive_fallbacks_2_plus condition."""
        ctx = FallbackContext.create_test_context(consecutive_fallbacks=2)
        assert consecutive_fallbacks_2_plus(ctx) is True

        ctx_low = FallbackContext.create_test_context(consecutive_fallbacks=1)
        assert consecutive_fallbacks_2_plus(ctx_low) is False

    def test_first_fallback_in_state(self):
        """Test first_fallback_in_state condition."""
        ctx = FallbackContext.create_test_context(fallbacks_in_state=0)
        assert first_fallback_in_state(ctx) is True

        ctx_not_first = FallbackContext.create_test_context(fallbacks_in_state=1)
        assert first_fallback_in_state(ctx_not_first) is False


# =============================================================================
# DYNAMIC CTA CONDITIONS TESTS
# =============================================================================

class TestDynamicCtaConditions:
    """Tests for dynamic CTA conditions."""

    def test_should_use_dynamic_cta(self):
        """Test should_use_dynamic_cta condition."""
        ctx = FallbackContext.create_test_context(
            current_tier="fallback_tier_2",
            state="spin_situation",
            competitor_mentioned=True
        )
        assert should_use_dynamic_cta(ctx) is True

    def test_should_use_dynamic_cta_wrong_tier(self):
        """Test should_use_dynamic_cta with wrong tier."""
        ctx = FallbackContext.create_test_context(
            current_tier="fallback_tier_1",
            state="spin_situation",
            competitor_mentioned=True
        )
        assert should_use_dynamic_cta(ctx) is False

    def test_should_use_dynamic_cta_wrong_state(self):
        """Test should_use_dynamic_cta with wrong state."""
        ctx = FallbackContext.create_test_context(
            current_tier="fallback_tier_2",
            state="greeting",
            competitor_mentioned=True
        )
        assert should_use_dynamic_cta(ctx) is False

    def test_should_use_dynamic_cta_no_context(self):
        """Test should_use_dynamic_cta with no context."""
        ctx = FallbackContext.create_test_context(
            current_tier="fallback_tier_2",
            state="spin_situation",
            competitor_mentioned=False,
            pain_category=None,
            company_size=None,
            last_intent=None
        )
        assert should_use_dynamic_cta(ctx) is False

    def test_has_competitor_context(self):
        """Test has_competitor_context condition."""
        ctx = FallbackContext.create_test_context(competitor_mentioned=True)
        assert has_competitor_context(ctx) is True

        ctx_no = FallbackContext.create_test_context(competitor_mentioned=False)
        assert has_competitor_context(ctx_no) is False

    def test_has_pain_context(self):
        """Test has_pain_context condition."""
        ctx = FallbackContext.create_test_context(pain_category="losing_clients")
        assert has_pain_context(ctx) is True

        ctx_no = FallbackContext.create_test_context(pain_category=None)
        assert has_pain_context(ctx_no) is False

        ctx_invalid = FallbackContext.create_test_context(pain_category="invalid")
        assert has_pain_context(ctx_invalid) is False

    def test_has_pain_losing_clients(self):
        """Test has_pain_losing_clients condition."""
        ctx = FallbackContext.create_test_context(pain_category="losing_clients")
        assert has_pain_losing_clients(ctx) is True

        ctx_other = FallbackContext.create_test_context(pain_category="no_control")
        assert has_pain_losing_clients(ctx_other) is False

    def test_has_pain_no_control(self):
        """Test has_pain_no_control condition."""
        ctx = FallbackContext.create_test_context(pain_category="no_control")
        assert has_pain_no_control(ctx) is True

    def test_has_pain_manual_work(self):
        """Test has_pain_manual_work condition."""
        ctx = FallbackContext.create_test_context(pain_category="manual_work")
        assert has_pain_manual_work(ctx) is True

    def test_last_intent_price_related(self):
        """Test last_intent_price_related condition."""
        for intent in ["price_question", "pricing_details", "objection_price"]:
            ctx = FallbackContext.create_test_context(last_intent=intent)
            assert last_intent_price_related(ctx) is True, f"Failed for {intent}"

        ctx_other = FallbackContext.create_test_context(last_intent="greeting")
        assert last_intent_price_related(ctx_other) is False

        ctx_none = FallbackContext.create_test_context(last_intent=None)
        assert last_intent_price_related(ctx_none) is False

    def test_last_intent_feature_related(self):
        """Test last_intent_feature_related condition."""
        for intent in ["question_features", "question_integrations", "question_how_works"]:
            ctx = FallbackContext.create_test_context(last_intent=intent)
            assert last_intent_feature_related(ctx) is True, f"Failed for {intent}"

        ctx_other = FallbackContext.create_test_context(last_intent="greeting")
        assert last_intent_feature_related(ctx_other) is False


# =============================================================================
# CONTEXT CONDITIONS TESTS
# =============================================================================

class TestContextConditions:
    """Tests for context-related conditions."""

    def test_is_small_company(self):
        """Test is_small_company condition."""
        ctx = FallbackContext.create_test_context(company_size=3)
        assert is_small_company(ctx) is True

        ctx_boundary = FallbackContext.create_test_context(company_size=5)
        assert is_small_company(ctx_boundary) is True

        ctx_large = FallbackContext.create_test_context(company_size=10)
        assert is_small_company(ctx_large) is False

    def test_is_large_company(self):
        """Test is_large_company condition."""
        ctx = FallbackContext.create_test_context(company_size=25)
        assert is_large_company(ctx) is True

        ctx_boundary = FallbackContext.create_test_context(company_size=20)
        assert is_large_company(ctx_boundary) is False

    def test_has_company_size(self):
        """Test has_company_size condition."""
        ctx = FallbackContext.create_test_context(company_size=10)
        assert has_company_size(ctx) is True

        ctx_none = FallbackContext.create_test_context(company_size=None)
        assert has_company_size(ctx_none) is False

    def test_has_contextual_data(self):
        """Test has_contextual_data condition."""
        ctx_size = FallbackContext.create_test_context(company_size=10)
        assert has_contextual_data(ctx_size) is True

        ctx_comp = FallbackContext.create_test_context(competitor_mentioned=True)
        assert has_contextual_data(ctx_comp) is True

        ctx_pain = FallbackContext.create_test_context(pain_category="losing_clients")
        assert has_contextual_data(ctx_pain) is True

        ctx_none = FallbackContext.create_test_context()
        assert has_contextual_data(ctx_none) is False

    def test_has_rich_context(self):
        """Test has_rich_context condition."""
        # 2 data points
        ctx_2 = FallbackContext.create_test_context(
            company_size=10,
            competitor_mentioned=True
        )
        assert has_rich_context(ctx_2) is True

        # 3 data points
        ctx_3 = FallbackContext.create_test_context(
            company_size=10,
            competitor_mentioned=True,
            pain_category="losing_clients"
        )
        assert has_rich_context(ctx_3) is True

        # 1 data point
        ctx_1 = FallbackContext.create_test_context(company_size=10)
        assert has_rich_context(ctx_1) is False


# =============================================================================
# FRUSTRATION CONDITIONS TESTS
# =============================================================================

class TestFrustrationConditions:
    """Tests for frustration-related conditions."""

    def test_frustration_high(self):
        """Test frustration_high condition."""
        ctx = FallbackContext.create_test_context(frustration_level=3)
        assert frustration_high(ctx) is True

        ctx_low = FallbackContext.create_test_context(frustration_level=2)
        assert frustration_high(ctx_low) is False

    def test_frustration_critical(self):
        """Test frustration_critical condition."""
        ctx = FallbackContext.create_test_context(frustration_level=4)
        assert frustration_critical(ctx) is True

        ctx_low = FallbackContext.create_test_context(frustration_level=3)
        assert frustration_critical(ctx_low) is False

    def test_frustration_low(self):
        """Test frustration_low condition."""
        ctx_0 = FallbackContext.create_test_context(frustration_level=0)
        assert frustration_low(ctx_0) is True

        ctx_1 = FallbackContext.create_test_context(frustration_level=1)
        assert frustration_low(ctx_1) is True

        ctx_2 = FallbackContext.create_test_context(frustration_level=2)
        assert frustration_low(ctx_2) is False

    def test_engagement_low(self):
        """Test engagement_low condition."""
        ctx_low = FallbackContext.create_test_context(engagement_level="low")
        assert engagement_low(ctx_low) is True

        ctx_dis = FallbackContext.create_test_context(engagement_level="disengaged")
        assert engagement_low(ctx_dis) is True

        ctx_high = FallbackContext.create_test_context(engagement_level="high")
        assert engagement_low(ctx_high) is False

    def test_engagement_high(self):
        """Test engagement_high condition."""
        ctx = FallbackContext.create_test_context(engagement_level="high")
        assert engagement_high(ctx) is True

        ctx_med = FallbackContext.create_test_context(engagement_level="medium")
        assert engagement_high(ctx_med) is False

    def test_momentum_negative(self):
        """Test momentum_negative condition."""
        ctx = FallbackContext.create_test_context(momentum_direction="negative")
        assert momentum_negative(ctx) is True

        ctx_pos = FallbackContext.create_test_context(momentum_direction="positive")
        assert momentum_negative(ctx_pos) is False

    def test_momentum_positive(self):
        """Test momentum_positive condition."""
        ctx = FallbackContext.create_test_context(momentum_direction="positive")
        assert momentum_positive(ctx) is True

    def test_should_offer_graceful_exit_critical_frustration(self):
        """Test should_offer_graceful_exit with critical frustration."""
        ctx = FallbackContext.create_test_context(frustration_level=4)
        assert should_offer_graceful_exit(ctx) is True

    def test_should_offer_graceful_exit_many_fallbacks_low_engagement(self):
        """Test should_offer_graceful_exit with many fallbacks and low engagement."""
        ctx = FallbackContext.create_test_context(
            total_fallbacks=5,
            engagement_level="low"
        )
        assert should_offer_graceful_exit(ctx) is True

    def test_should_offer_graceful_exit_negative_momentum(self):
        """Test should_offer_graceful_exit with negative momentum."""
        ctx = FallbackContext.create_test_context(
            total_fallbacks=4,
            momentum_direction="negative"
        )
        assert should_offer_graceful_exit(ctx) is True

    def test_should_offer_graceful_exit_no(self):
        """Test should_offer_graceful_exit when not needed."""
        ctx = FallbackContext.create_test_context(
            frustration_level=2,
            total_fallbacks=3,
            engagement_level="medium",
            momentum_direction="neutral"
        )
        assert should_offer_graceful_exit(ctx) is False


# =============================================================================
# STATE CONDITIONS TESTS
# =============================================================================

class TestStateConditions:
    """Tests for state-related conditions."""

    def test_is_spin_state(self):
        """Test is_spin_state condition."""
        for state in ["spin_situation", "spin_problem", "spin_implication", "spin_need_payoff"]:
            ctx = FallbackContext.create_test_context(state=state)
            assert is_spin_state(ctx) is True, f"Failed for {state}"

        ctx_no = FallbackContext.create_test_context(state="presentation")
        assert is_spin_state(ctx_no) is False

    def test_is_dynamic_cta_state(self):
        """Test is_dynamic_cta_state condition."""
        for state in DYNAMIC_CTA_STATES:
            ctx = FallbackContext.create_test_context(state=state)
            assert is_dynamic_cta_state(ctx) is True, f"Failed for {state}"

        ctx_no = FallbackContext.create_test_context(state="greeting")
        assert is_dynamic_cta_state(ctx_no) is False

    def test_is_presentation_state(self):
        """Test is_presentation_state condition."""
        ctx = FallbackContext.create_test_context(state="presentation")
        assert is_presentation_state(ctx) is True

        ctx_no = FallbackContext.create_test_context(state="spin_situation")
        assert is_presentation_state(ctx_no) is False

    def test_is_close_state(self):
        """Test is_close_state condition."""
        ctx_close = FallbackContext.create_test_context(state="close")
        assert is_close_state(ctx_close) is True

        ctx_soft = FallbackContext.create_test_context(state="soft_close")
        assert is_close_state(ctx_soft) is True

        ctx_no = FallbackContext.create_test_context(state="presentation")
        assert is_close_state(ctx_no) is False

    def test_is_handle_objection_state(self):
        """Test is_handle_objection_state condition."""
        ctx = FallbackContext.create_test_context(state="handle_objection")
        assert is_handle_objection_state(ctx) is True

    def test_is_greeting_state(self):
        """Test is_greeting_state condition."""
        ctx = FallbackContext.create_test_context(state="greeting")
        assert is_greeting_state(ctx) is True


# =============================================================================
# COMBINED CONDITIONS TESTS
# =============================================================================

class TestCombinedConditions:
    """Tests for combined conditions."""

    def test_should_skip_to_next_state(self):
        """Test should_skip_to_next_state condition."""
        ctx = FallbackContext.create_test_context(
            current_tier="fallback_tier_3",
            fallbacks_in_state=2
        )
        assert should_skip_to_next_state(ctx) is True

        # Wrong tier
        ctx_wrong = FallbackContext.create_test_context(
            current_tier="fallback_tier_2",
            fallbacks_in_state=2
        )
        assert should_skip_to_next_state(ctx_wrong) is False

    def test_should_skip_to_next_state_frustration(self):
        """Test should_skip_to_next_state with frustration."""
        ctx = FallbackContext.create_test_context(
            current_tier="fallback_tier_3",
            fallbacks_in_state=1,
            frustration_level=2
        )
        assert should_skip_to_next_state(ctx) is True

    def test_can_try_rephrase(self):
        """Test can_try_rephrase condition."""
        ctx = FallbackContext.create_test_context(
            current_tier="fallback_tier_1",
            total_fallbacks=2,
            frustration_level=2
        )
        assert can_try_rephrase(ctx) is True

    def test_can_try_rephrase_too_many_fallbacks(self):
        """Test can_try_rephrase with too many fallbacks."""
        ctx = FallbackContext.create_test_context(
            current_tier="fallback_tier_1",
            total_fallbacks=3,
            frustration_level=1
        )
        assert can_try_rephrase(ctx) is False

    def test_can_try_rephrase_high_frustration(self):
        """Test can_try_rephrase with high frustration."""
        ctx = FallbackContext.create_test_context(
            current_tier="fallback_tier_1",
            total_fallbacks=1,
            frustration_level=3
        )
        assert can_try_rephrase(ctx) is False

    def test_should_show_options(self):
        """Test should_show_options condition."""
        ctx = FallbackContext.create_test_context(
            current_tier="fallback_tier_2",
            state="spin_situation"
        )
        assert should_show_options(ctx) is True

        ctx_objection = FallbackContext.create_test_context(
            current_tier="fallback_tier_2",
            state="handle_objection"
        )
        assert should_show_options(ctx_objection) is True

        # Wrong tier
        ctx_wrong = FallbackContext.create_test_context(
            current_tier="fallback_tier_1",
            state="spin_situation"
        )
        assert should_show_options(ctx_wrong) is False

        # Wrong state (not in DYNAMIC_CTA_STATES and not handle_objection)
        ctx_wrong_state = FallbackContext.create_test_context(
            current_tier="fallback_tier_2",
            state="greeting"
        )
        assert should_show_options(ctx_wrong_state) is False

    def test_needs_immediate_escalation_critical_frustration(self):
        """Test needs_immediate_escalation with critical frustration."""
        ctx = FallbackContext.create_test_context(frustration_level=5)
        assert needs_immediate_escalation(ctx) is True

    def test_needs_immediate_escalation_consecutive_negative(self):
        """Test needs_immediate_escalation with consecutive fallbacks and negative momentum."""
        ctx = FallbackContext.create_test_context(
            consecutive_fallbacks=4,
            momentum_direction="negative"
        )
        assert needs_immediate_escalation(ctx) is True

    def test_needs_immediate_escalation_total_disengaged(self):
        """Test needs_immediate_escalation with many fallbacks and disengaged."""
        ctx = FallbackContext.create_test_context(
            total_fallbacks=7,
            engagement_level="disengaged"
        )
        assert needs_immediate_escalation(ctx) is True

    def test_needs_immediate_escalation_no(self):
        """Test needs_immediate_escalation when not needed."""
        ctx = FallbackContext.create_test_context(
            frustration_level=3,
            consecutive_fallbacks=2,
            total_fallbacks=4,
            engagement_level="medium"
        )
        assert needs_immediate_escalation(ctx) is False

    def test_can_recover(self):
        """Test can_recover condition."""
        ctx = FallbackContext.create_test_context(
            frustration_level=2,
            total_fallbacks=4,
            engagement_level="medium"
        )
        assert can_recover(ctx) is True

    def test_can_recover_high_frustration(self):
        """Test can_recover with high frustration."""
        ctx = FallbackContext.create_test_context(frustration_level=4)
        assert can_recover(ctx) is False

    def test_can_recover_too_many_fallbacks(self):
        """Test can_recover with too many fallbacks."""
        ctx = FallbackContext.create_test_context(total_fallbacks=6)
        assert can_recover(ctx) is False

    def test_can_recover_disengaged(self):
        """Test can_recover with disengaged user."""
        ctx = FallbackContext.create_test_context(engagement_level="disengaged")
        assert can_recover(ctx) is False

    def test_should_personalize_response(self):
        """Test should_personalize_response condition."""
        ctx = FallbackContext.create_test_context(
            frustration_level=2,
            company_size=10
        )
        assert should_personalize_response(ctx) is True

    def test_should_personalize_response_critical_frustration(self):
        """Test should_personalize_response with critical frustration."""
        ctx = FallbackContext.create_test_context(
            frustration_level=4,
            company_size=10
        )
        assert should_personalize_response(ctx) is False

    def test_should_personalize_response_no_context(self):
        """Test should_personalize_response with no context."""
        ctx = FallbackContext.create_test_context(frustration_level=2)
        assert should_personalize_response(ctx) is False


# =============================================================================
# INTEGRATION TESTS
# =============================================================================

class TestIntegration:
    """Integration tests for Fallback conditions."""

    def test_tier_1_scenario(self):
        """Test tier 1 scenario with all signals."""
        ctx = FallbackContext.create_test_context(
            state="spin_situation",
            current_tier="fallback_tier_1",
            total_fallbacks=1,
            frustration_level=1
        )

        assert is_tier_1(ctx) is True
        assert can_try_rephrase(ctx) is True
        assert should_escalate_tier(ctx) is False
        assert can_recover(ctx) is True

    def test_tier_2_dynamic_cta_scenario(self):
        """Test tier 2 with dynamic CTA."""
        ctx = FallbackContext.create_test_context(
            state="spin_problem",
            current_tier="fallback_tier_2",
            total_fallbacks=3,
            competitor_mentioned=True,
            pain_category="losing_clients",
            company_size=15
        )

        assert is_tier_2(ctx) is True
        assert should_use_dynamic_cta(ctx) is True
        assert has_competitor_context(ctx) is True
        assert has_pain_context(ctx) is True
        assert has_rich_context(ctx) is True
        assert should_personalize_response(ctx) is True

    def test_escalation_scenario(self):
        """Test escalation scenario."""
        ctx = FallbackContext.create_test_context(
            state="spin_situation",
            current_tier="fallback_tier_2",
            total_fallbacks=4,
            consecutive_fallbacks=2,
            frustration_level=3
        )

        assert should_escalate_tier(ctx) is True
        assert frustration_high(ctx) is True
        assert consecutive_fallbacks_2_plus(ctx) is True

    def test_graceful_exit_scenario(self):
        """Test graceful exit scenario."""
        ctx = FallbackContext.create_test_context(
            state="spin_situation",
            current_tier="fallback_tier_3",
            total_fallbacks=7,
            frustration_level=4,
            engagement_level="disengaged",
            momentum_direction="negative"
        )

        assert should_offer_graceful_exit(ctx) is True
        assert needs_immediate_escalation(ctx) is True
        assert can_recover(ctx) is False
        assert frustration_critical(ctx) is True

    def test_recovery_possible_scenario(self):
        """Test scenario where recovery is possible."""
        ctx = FallbackContext.create_test_context(
            state="spin_problem",
            current_tier="fallback_tier_2",
            total_fallbacks=3,
            frustration_level=2,
            engagement_level="medium",
            momentum_direction="neutral",
            pain_category="losing_clients"
        )

        assert can_recover(ctx) is True
        assert should_personalize_response(ctx) is True
        assert needs_immediate_escalation(ctx) is False


# =============================================================================
# DOCUMENTATION TESTS
# =============================================================================

class TestDocumentation:
    """Tests for documentation generation."""

    def test_registry_documentation(self):
        """Test that registry can generate documentation."""
        docs = fallback_registry.get_documentation()

        assert "Fallback Conditions" in docs
        assert "FallbackContext" in docs
        assert "should_escalate_tier" in docs
        assert "tier" in docs.lower()
        assert "dynamic_cta" in docs.lower()

    def test_registry_stats(self):
        """Test registry statistics."""
        stats = fallback_registry.get_stats()

        assert stats["name"] == "fallback"
        assert stats["total_conditions"] > 0
        assert stats["total_categories"] >= 6
        assert "tier" in stats["conditions_by_category"]
        assert "dynamic_cta" in stats["conditions_by_category"]


# =============================================================================
# EDGE CASES TESTS
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_boundary_frustration_levels(self):
        """Test boundary frustration levels."""
        ctx_2 = FallbackContext.create_test_context(frustration_level=2)
        assert frustration_high(ctx_2) is False
        assert frustration_low(ctx_2) is False

        ctx_3 = FallbackContext.create_test_context(frustration_level=3)
        assert frustration_high(ctx_3) is True
        assert frustration_critical(ctx_3) is False

        ctx_4 = FallbackContext.create_test_context(frustration_level=4)
        assert frustration_critical(ctx_4) is True

    def test_boundary_fallback_counts(self):
        """Test boundary fallback counts."""
        ctx_4 = FallbackContext.create_test_context(total_fallbacks=4)
        assert too_many_fallbacks(ctx_4) is False

        ctx_5 = FallbackContext.create_test_context(total_fallbacks=5)
        assert too_many_fallbacks(ctx_5) is True

        ctx_2 = FallbackContext.create_test_context(fallbacks_in_state=2)
        assert many_fallbacks_in_state(ctx_2) is False

        ctx_3 = FallbackContext.create_test_context(fallbacks_in_state=3)
        assert many_fallbacks_in_state(ctx_3) is True

    def test_boundary_company_sizes(self):
        """Test boundary company sizes."""
        # Small company boundary
        ctx_5 = FallbackContext.create_test_context(company_size=5)
        assert is_small_company(ctx_5) is True

        ctx_6 = FallbackContext.create_test_context(company_size=6)
        assert is_small_company(ctx_6) is False

        # Large company boundary
        ctx_20 = FallbackContext.create_test_context(company_size=20)
        assert is_large_company(ctx_20) is False

        ctx_21 = FallbackContext.create_test_context(company_size=21)
        assert is_large_company(ctx_21) is True

    def test_none_values_handling(self):
        """Test handling of None values."""
        ctx = FallbackContext.create_test_context(
            company_size=None,
            pain_category=None,
            last_intent=None,
            last_successful_intent=None
        )

        assert has_company_size(ctx) is False
        assert is_small_company(ctx) is False
        assert is_large_company(ctx) is False
        assert has_pain_context(ctx) is False
        assert last_intent_price_related(ctx) is False
        assert last_intent_feature_related(ctx) is False

    def test_all_tiers_valid(self):
        """Test that all tier values are valid."""
        for tier in FALLBACK_TIERS:
            ctx = FallbackContext.create_test_context(current_tier=tier)
            assert ctx.current_tier == tier

    def test_zero_values(self):
        """Test with zero values."""
        ctx = FallbackContext.create_test_context(
            total_fallbacks=0,
            consecutive_fallbacks=0,
            fallbacks_in_state=0,
            frustration_level=0,
            company_size=0
        )

        assert first_fallback_in_state(ctx) is True
        assert frustration_low(ctx) is True
        assert is_small_company(ctx) is False  # 0 is not in range (0, 5]
