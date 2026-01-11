"""
Tests for Personalization Domain Conditions.

This module provides comprehensive tests for:
- PersonalizationContext (context.py)
- personalization_registry (registry.py)
- All condition functions (conditions.py)
- CTAGenerator integration

Part of Phase 7: Personalization Domain (ARCHITECTURE_UNIFIED_PLAN.md)
"""

import pytest
from typing import Dict, Any

from src.conditions.personalization import (
    # Context
    PersonalizationContext,
    CTA_TYPES,
    CTA_ELIGIBLE_STATES,
    SOFT_CTA_STATES,
    DIRECT_CTA_STATES,
    INDUSTRIES,
    ROLES,
    PAIN_CATEGORIES,
    SMALL_COMPANY_THRESHOLD,
    MEDIUM_COMPANY_THRESHOLD,
    LARGE_COMPANY_THRESHOLD,
    SOFT_CTA_FRUSTRATION_THRESHOLD,
    NO_CTA_FRUSTRATION_THRESHOLD,
    MIN_TURNS_FOR_CTA,
    # Registry
    personalization_registry,
    personalization_condition,
    get_personalization_registry,
    # CTA conditions
    should_add_cta,
    should_use_soft_cta,
    should_use_direct_cta,
    cta_eligible_state,
    enough_turns_for_cta,
    should_skip_cta,
    cta_after_breakthrough,
    demo_cta_appropriate,
    contact_cta_appropriate,
    trial_cta_appropriate,
    info_cta_appropriate,
    # Company conditions
    has_company_size,
    is_small_company,
    is_medium_company,
    is_large_company,
    is_enterprise_company,
    has_role,
    is_decision_maker,
    is_manager,
    has_industry,
    has_company_context,
    # Pain conditions
    has_pain_category,
    has_pain_point,
    has_pain_context,
    pain_losing_clients,
    pain_no_control,
    pain_manual_work,
    pain_no_analytics,
    pain_team_chaos,
    has_current_crm,
    competitor_mentioned,
    # Engagement conditions
    engagement_high,
    engagement_medium,
    engagement_low,
    momentum_positive,
    momentum_negative,
    momentum_neutral,
    has_breakthrough,
    # Tone conditions
    frustration_none,
    frustration_low,
    frustration_moderate,
    frustration_high,
    needs_soft_approach,
    # Objection conditions
    has_objections,
    has_multiple_objections,
    has_repeated_objections,
    objection_is_price,
    objection_is_competitor,
    objection_is_time,
    # State conditions
    is_spin_state,
    is_early_state,
    is_mid_state,
    is_late_state,
    is_presentation_state,
    is_close_state,
    is_objection_state,
    # Combined conditions
    ready_for_strong_cta,
    has_rich_context,
    can_personalize_by_company,
    can_personalize_by_pain,
    should_be_conservative,
    should_accelerate,
    needs_roi_messaging,
    needs_comparison_messaging,
    can_use_case_study,
    optimal_for_demo_offer,
    needs_urgency_reduction,
)
from src.conditions import ConditionRegistries
from src.conditions.trace import EvaluationTrace


# =============================================================================
# TEST FIXTURES
# =============================================================================

@pytest.fixture
def empty_context():
    """Create an empty context for testing."""
    return PersonalizationContext.create_test_context()


@pytest.fixture
def presentation_context():
    """Create a context in presentation state."""
    return PersonalizationContext.create_test_context(
        state="presentation",
        turn_number=5,
        company_size=10,
        engagement_level="high"
    )


@pytest.fixture
def early_state_context():
    """Create a context in early state."""
    return PersonalizationContext.create_test_context(
        state="spin_situation",
        turn_number=2,
        engagement_level="medium"
    )


@pytest.fixture
def high_frustration_context():
    """Create a context with high frustration."""
    return PersonalizationContext.create_test_context(
        state="presentation",
        turn_number=5,
        frustration_level=5,
        engagement_level="low",
        momentum_direction="negative"
    )


@pytest.fixture
def breakthrough_context():
    """Create a context with breakthrough."""
    return PersonalizationContext.create_test_context(
        state="presentation",
        turn_number=6,
        has_breakthrough=True,
        engagement_level="high",
        momentum_direction="positive",
        pain_category="losing_clients",
        company_size=15
    )


@pytest.fixture
def objection_context():
    """Create a context with objection."""
    return PersonalizationContext.create_test_context(
        state="handle_objection",
        turn_number=5,
        objection_type="objection_price",
        total_objections=2,
        company_size=10
    )


# =============================================================================
# CONTEXT TESTS
# =============================================================================

class TestPersonalizationContext:
    """Tests for PersonalizationContext class."""

    def test_create_empty_context(self):
        """Test creating empty context."""
        ctx = PersonalizationContext()
        assert ctx.collected_data == {}
        assert ctx.state == ""
        assert ctx.turn_number == 0
        assert ctx.company_size is None
        assert ctx.frustration_level == 0

    def test_create_context_with_data(self):
        """Test creating context with data."""
        ctx = PersonalizationContext(
            collected_data={"company_size": 10},
            state="presentation",
            turn_number=5,
            company_size=10,
            role="owner",
            industry="retail",
            pain_category="losing_clients",
            frustration_level=2,
            has_breakthrough=True
        )
        assert ctx.collected_data["company_size"] == 10
        assert ctx.state == "presentation"
        assert ctx.turn_number == 5
        assert ctx.company_size == 10
        assert ctx.role == "owner"
        assert ctx.industry == "retail"
        assert ctx.pain_category == "losing_clients"
        assert ctx.has_breakthrough is True

    def test_negative_turn_number_raises(self):
        """Test that negative turn number raises ValueError."""
        with pytest.raises(ValueError, match="turn_number cannot be negative"):
            PersonalizationContext(turn_number=-1)

    def test_negative_frustration_raises(self):
        """Test that negative frustration raises ValueError."""
        with pytest.raises(ValueError, match="frustration_level cannot be negative"):
            PersonalizationContext(frustration_level=-1)

    def test_negative_total_objections_raises(self):
        """Test that negative total_objections raises ValueError."""
        with pytest.raises(ValueError, match="total_objections cannot be negative"):
            PersonalizationContext(total_objections=-1)

    def test_negative_cta_count_raises(self):
        """Test that negative cta_count raises ValueError."""
        with pytest.raises(ValueError, match="cta_count cannot be negative"):
            PersonalizationContext(cta_count=-1)

    def test_create_test_context(self):
        """Test create_test_context factory method."""
        ctx = PersonalizationContext.create_test_context(
            collected_data={"test": "data"},
            state="presentation",
            turn_number=10,
            company_size=20,
            pain_category="no_control"
        )
        assert ctx.collected_data["test"] == "data"
        assert ctx.state == "presentation"
        assert ctx.turn_number == 10
        assert ctx.company_size == 20
        assert ctx.pain_category == "no_control"

    def test_is_small_company(self):
        """Test is_small_company method."""
        ctx_small = PersonalizationContext.create_test_context(company_size=3)
        assert ctx_small.is_small_company() is True

        ctx_boundary = PersonalizationContext.create_test_context(company_size=5)
        assert ctx_boundary.is_small_company() is True

        ctx_medium = PersonalizationContext.create_test_context(company_size=10)
        assert ctx_medium.is_small_company() is False

        ctx_none = PersonalizationContext.create_test_context(company_size=None)
        assert ctx_none.is_small_company() is False

    def test_is_medium_company(self):
        """Test is_medium_company method."""
        ctx_medium = PersonalizationContext.create_test_context(company_size=10)
        assert ctx_medium.is_medium_company() is True

        ctx_boundary_low = PersonalizationContext.create_test_context(company_size=6)
        assert ctx_boundary_low.is_medium_company() is True

        ctx_boundary_high = PersonalizationContext.create_test_context(company_size=20)
        assert ctx_boundary_high.is_medium_company() is True

        ctx_small = PersonalizationContext.create_test_context(company_size=5)
        assert ctx_small.is_medium_company() is False

        ctx_large = PersonalizationContext.create_test_context(company_size=25)
        assert ctx_large.is_medium_company() is False

    def test_is_large_company(self):
        """Test is_large_company method."""
        ctx_large = PersonalizationContext.create_test_context(company_size=25)
        assert ctx_large.is_large_company() is True

        ctx_boundary = PersonalizationContext.create_test_context(company_size=20)
        assert ctx_boundary.is_large_company() is False

        ctx_none = PersonalizationContext.create_test_context(company_size=None)
        assert ctx_none.is_large_company() is False

    def test_is_enterprise_company(self):
        """Test is_enterprise_company method."""
        ctx_enterprise = PersonalizationContext.create_test_context(company_size=100)
        assert ctx_enterprise.is_enterprise_company() is True

        ctx_boundary = PersonalizationContext.create_test_context(company_size=50)
        assert ctx_boundary.is_enterprise_company() is False

        ctx_large = PersonalizationContext.create_test_context(company_size=51)
        assert ctx_large.is_enterprise_company() is True

    def test_has_company_context(self):
        """Test has_company_context method."""
        ctx_size = PersonalizationContext.create_test_context(company_size=10)
        assert ctx_size.has_company_context() is True

        ctx_role = PersonalizationContext.create_test_context(role="owner")
        assert ctx_role.has_company_context() is True

        ctx_industry = PersonalizationContext.create_test_context(industry="retail")
        assert ctx_industry.has_company_context() is True

        ctx_none = PersonalizationContext.create_test_context()
        assert ctx_none.has_company_context() is False

    def test_has_pain_context(self):
        """Test has_pain_context method."""
        ctx_category = PersonalizationContext.create_test_context(pain_category="losing_clients")
        assert ctx_category.has_pain_context() is True

        ctx_point = PersonalizationContext.create_test_context(pain_point="Sales tracking")
        assert ctx_point.has_pain_context() is True

        ctx_none = PersonalizationContext.create_test_context()
        assert ctx_none.has_pain_context() is False

    def test_is_cta_eligible_state(self):
        """Test is_cta_eligible_state method."""
        for state in CTA_ELIGIBLE_STATES:
            ctx = PersonalizationContext.create_test_context(state=state)
            assert ctx.is_cta_eligible_state() is True, f"Failed for {state}"

        ctx_greeting = PersonalizationContext.create_test_context(state="greeting")
        assert ctx_greeting.is_cta_eligible_state() is False

    def test_is_soft_cta_state(self):
        """Test is_soft_cta_state method."""
        for state in SOFT_CTA_STATES:
            ctx = PersonalizationContext.create_test_context(state=state)
            assert ctx.is_soft_cta_state() is True, f"Failed for {state}"

        ctx_presentation = PersonalizationContext.create_test_context(state="presentation")
        assert ctx_presentation.is_soft_cta_state() is False

    def test_is_direct_cta_state(self):
        """Test is_direct_cta_state method."""
        for state in DIRECT_CTA_STATES:
            ctx = PersonalizationContext.create_test_context(state=state)
            assert ctx.is_direct_cta_state() is True, f"Failed for {state}"

        ctx_early = PersonalizationContext.create_test_context(state="spin_implication")
        assert ctx_early.is_direct_cta_state() is False

    def test_should_use_soft_cta(self):
        """Test should_use_soft_cta method."""
        ctx_frustrated = PersonalizationContext.create_test_context(frustration_level=3)
        assert ctx_frustrated.should_use_soft_cta() is True

        ctx_low = PersonalizationContext.create_test_context(frustration_level=2)
        assert ctx_low.should_use_soft_cta() is False

    def test_should_skip_cta(self):
        """Test should_skip_cta method."""
        ctx_high = PersonalizationContext.create_test_context(frustration_level=5)
        assert ctx_high.should_skip_cta() is True

        ctx_moderate = PersonalizationContext.create_test_context(frustration_level=4)
        assert ctx_moderate.should_skip_cta() is False

    def test_is_enough_turns_for_cta(self):
        """Test is_enough_turns_for_cta method."""
        ctx_enough = PersonalizationContext.create_test_context(turn_number=3)
        assert ctx_enough.is_enough_turns_for_cta() is True

        ctx_early = PersonalizationContext.create_test_context(turn_number=2)
        assert ctx_early.is_enough_turns_for_cta() is False

    def test_has_rich_context(self):
        """Test has_rich_context method."""
        ctx_2 = PersonalizationContext.create_test_context(
            company_size=10,
            role="owner"
        )
        assert ctx_2.has_rich_context() is True

        ctx_1 = PersonalizationContext.create_test_context(company_size=10)
        assert ctx_1.has_rich_context() is False

        ctx_5 = PersonalizationContext.create_test_context(
            company_size=10,
            role="owner",
            industry="retail",
            pain_category="losing_clients",
            competitor_mentioned=True
        )
        assert ctx_5.has_rich_context() is True

    def test_to_dict(self):
        """Test to_dict method."""
        ctx = PersonalizationContext.create_test_context(
            state="presentation",
            turn_number=5,
            company_size=10,
            pain_category="losing_clients",
            frustration_level=2
        )
        d = ctx.to_dict()

        assert d["state"] == "presentation"
        assert d["turn_number"] == 5
        assert d["company_size"] == 10
        assert d["pain_category"] == "losing_clients"
        assert d["frustration_level"] == 2
        assert "engagement_level" in d
        assert "momentum_direction" in d

    def test_repr(self):
        """Test __repr__ method."""
        ctx = PersonalizationContext.create_test_context(
            state="presentation",
            company_size=10,
            pain_category="losing_clients",
            engagement_level="high",
            frustration_level=2
        )
        repr_str = repr(ctx)
        assert "presentation" in repr_str
        assert "company_size=10" in repr_str


class TestPersonalizationContextFromEnvelope:
    """Tests for creating PersonalizationContext from ContextEnvelope."""

    def test_from_envelope(self):
        """Test creating context from envelope mock."""
        class MockEnvelope:
            collected_data = {
                "company_size": 10,
                "pain_category": "losing_clients",
                "role": "owner"
            }
            state = "presentation"
            total_turns = 5
            has_breakthrough = True
            engagement_level = "high"
            momentum_direction = "positive"
            frustration_level = 1
            first_objection_type = None
            total_objections = 0
            repeated_objection_types = []
            last_action = "show_benefits"

        envelope = MockEnvelope()
        cta_stats = {"last_cta_turn": 3, "cta_count": 1}

        ctx = PersonalizationContext.from_envelope(envelope, cta_stats)

        assert ctx.collected_data["company_size"] == 10
        assert ctx.state == "presentation"
        assert ctx.turn_number == 5
        assert ctx.company_size == 10
        assert ctx.role == "owner"
        assert ctx.pain_category == "losing_clients"
        assert ctx.has_breakthrough is True
        assert ctx.engagement_level == "high"
        assert ctx.last_cta_turn == 3
        assert ctx.cta_count == 1

    def test_from_envelope_string_company_size(self):
        """Test from_envelope converts string company_size to int."""
        class MockEnvelope:
            collected_data = {"company_size": "15"}
            state = "presentation"
            total_turns = 1
            has_breakthrough = False
            engagement_level = "medium"
            momentum_direction = "neutral"
            frustration_level = 0
            first_objection_type = None
            total_objections = 0
            repeated_objection_types = []
            last_action = None

        ctx = PersonalizationContext.from_envelope(MockEnvelope())
        assert ctx.company_size == 15

    def test_from_envelope_invalid_company_size_string(self):
        """Test from_envelope handles invalid company_size string."""
        class MockEnvelope:
            collected_data = {"company_size": "large"}
            state = "presentation"
            total_turns = 1
            has_breakthrough = False
            engagement_level = "medium"
            momentum_direction = "neutral"
            frustration_level = 0
            first_objection_type = None
            total_objections = 0
            repeated_objection_types = []
            last_action = None

        ctx = PersonalizationContext.from_envelope(MockEnvelope())
        assert ctx.company_size is None


class TestPersonalizationContextFromContextDict:
    """Tests for creating PersonalizationContext from context dict."""

    def test_from_context_dict(self):
        """Test creating context from dictionary."""
        context = {
            "collected_data": {
                "company_size": 10,
                "pain_category": "losing_clients"
            },
            "turn_number": 5,
            "has_breakthrough": True,
            "engagement_level": "high",
            "momentum_direction": "positive",
            "frustration_level": 1,
            "total_objections": 0
        }

        ctx = PersonalizationContext.from_context_dict(
            context=context,
            state="presentation",
            cta_stats={"last_cta_turn": 3, "cta_count": 1}
        )

        assert ctx.state == "presentation"
        assert ctx.turn_number == 5
        assert ctx.company_size == 10
        assert ctx.pain_category == "losing_clients"
        assert ctx.has_breakthrough is True
        assert ctx.last_cta_turn == 3
        assert ctx.cta_count == 1

    def test_from_context_dict_minimal(self):
        """Test creating context with minimal data."""
        ctx = PersonalizationContext.from_context_dict(
            context={},
            state="greeting"
        )

        assert ctx.state == "greeting"
        assert ctx.turn_number == 0
        assert ctx.company_size is None
        assert ctx.frustration_level == 0


class TestConstants:
    """Tests for module constants."""

    def test_cta_types(self):
        """Test CTA_TYPES constant."""
        assert "demo" in CTA_TYPES
        assert "contact" in CTA_TYPES
        assert "trial" in CTA_TYPES
        assert "info" in CTA_TYPES

    def test_cta_eligible_states(self):
        """Test CTA_ELIGIBLE_STATES constant."""
        assert "presentation" in CTA_ELIGIBLE_STATES
        assert "close" in CTA_ELIGIBLE_STATES
        assert "spin_implication" in CTA_ELIGIBLE_STATES
        assert "greeting" not in CTA_ELIGIBLE_STATES

    def test_soft_cta_states(self):
        """Test SOFT_CTA_STATES constant."""
        assert "spin_implication" in SOFT_CTA_STATES
        assert "spin_need_payoff" in SOFT_CTA_STATES
        assert "presentation" not in SOFT_CTA_STATES

    def test_direct_cta_states(self):
        """Test DIRECT_CTA_STATES constant."""
        assert "presentation" in DIRECT_CTA_STATES
        assert "close" in DIRECT_CTA_STATES
        assert "spin_implication" not in DIRECT_CTA_STATES

    def test_pain_categories(self):
        """Test PAIN_CATEGORIES constant."""
        assert "losing_clients" in PAIN_CATEGORIES
        assert "no_control" in PAIN_CATEGORIES
        assert "manual_work" in PAIN_CATEGORIES
        assert "no_analytics" in PAIN_CATEGORIES
        assert "team_chaos" in PAIN_CATEGORIES

    def test_company_size_thresholds(self):
        """Test company size thresholds."""
        assert SMALL_COMPANY_THRESHOLD == 5
        assert MEDIUM_COMPANY_THRESHOLD == 20
        assert LARGE_COMPANY_THRESHOLD == 50

    def test_frustration_thresholds(self):
        """Test frustration thresholds."""
        assert SOFT_CTA_FRUSTRATION_THRESHOLD == 3
        assert NO_CTA_FRUSTRATION_THRESHOLD == 5

    def test_min_turns_for_cta(self):
        """Test MIN_TURNS_FOR_CTA constant."""
        assert MIN_TURNS_FOR_CTA == 3


# =============================================================================
# REGISTRY TESTS
# =============================================================================

class TestPersonalizationRegistry:
    """Tests for Personalization registry."""

    def test_registry_exists(self):
        """Test that personalization_registry is properly created."""
        assert personalization_registry is not None
        assert personalization_registry.name == "personalization"
        assert len(personalization_registry) > 0

    def test_get_personalization_registry(self):
        """Test get_personalization_registry function."""
        reg = get_personalization_registry()
        assert reg is personalization_registry

    def test_registry_has_expected_conditions(self):
        """Test that registry has all expected conditions."""
        expected = [
            "should_add_cta",
            "should_use_soft_cta",
            "has_company_size",
            "has_pain_category",
            "engagement_high",
            "frustration_high",
            "ready_for_strong_cta",
            "can_personalize_by_company",
        ]
        for name in expected:
            assert personalization_registry.has(name), f"Missing condition: {name}"

    def test_registry_categories(self):
        """Test that registry has expected categories."""
        categories = personalization_registry.get_categories()
        assert "cta" in categories
        assert "company" in categories
        assert "pain" in categories
        assert "engagement" in categories
        assert "tone" in categories
        assert "state" in categories
        assert "combined" in categories

    def test_evaluate_through_registry(self):
        """Test evaluating conditions through registry."""
        ctx = PersonalizationContext.create_test_context(
            state="presentation",
            turn_number=5,
            frustration_level=0
        )
        assert personalization_registry.evaluate("cta_eligible_state", ctx) is True
        assert personalization_registry.evaluate("enough_turns_for_cta", ctx) is True

    def test_evaluate_with_trace(self):
        """Test evaluating with trace."""
        ctx = PersonalizationContext.create_test_context(
            state="presentation",
            turn_number=5
        )
        trace = EvaluationTrace(rule_name="cta_check")

        result = personalization_registry.evaluate("cta_eligible_state", ctx, trace)

        assert result is True
        assert len(trace.entries) == 1
        assert trace.entries[0].condition_name == "cta_eligible_state"
        assert trace.entries[0].result is True

    def test_registry_in_condition_registries(self):
        """Test that Personalization registry is in ConditionRegistries."""
        assert ConditionRegistries.has_condition("should_add_cta")
        assert ConditionRegistries.find_condition("should_add_cta") == "personalization"
        assert ConditionRegistries.get("personalization") is personalization_registry

    def test_validate_all(self):
        """Test validate_all method."""
        result = personalization_registry.validate_all(
            lambda: PersonalizationContext.create_test_context()
        )
        assert result.is_valid
        assert len(result.passed) == len(personalization_registry)
        assert len(result.failed) == 0
        assert len(result.errors) == 0


# =============================================================================
# CTA CONDITIONS TESTS
# =============================================================================

class TestCtaConditions:
    """Tests for CTA-related conditions."""

    def test_should_add_cta(self):
        """Test should_add_cta condition."""
        ctx = PersonalizationContext.create_test_context(
            state="presentation",
            turn_number=5,
            frustration_level=0
        )
        assert should_add_cta(ctx) is True

    def test_should_add_cta_wrong_state(self):
        """Test should_add_cta with wrong state."""
        ctx = PersonalizationContext.create_test_context(
            state="greeting",
            turn_number=5
        )
        assert should_add_cta(ctx) is False

    def test_should_add_cta_too_early(self):
        """Test should_add_cta too early in conversation."""
        ctx = PersonalizationContext.create_test_context(
            state="presentation",
            turn_number=2
        )
        assert should_add_cta(ctx) is False

    def test_should_add_cta_high_frustration(self):
        """Test should_add_cta with high frustration."""
        ctx = PersonalizationContext.create_test_context(
            state="presentation",
            turn_number=5,
            frustration_level=5
        )
        assert should_add_cta(ctx) is False

    def test_should_use_soft_cta(self):
        """Test should_use_soft_cta condition."""
        # Moderate frustration
        ctx_frustration = PersonalizationContext.create_test_context(frustration_level=3)
        assert should_use_soft_cta(ctx_frustration) is True

        # Soft CTA state
        ctx_state = PersonalizationContext.create_test_context(
            state="spin_implication",
            frustration_level=0
        )
        assert should_use_soft_cta(ctx_state) is True

        # Negative momentum
        ctx_momentum = PersonalizationContext.create_test_context(
            state="presentation",
            momentum_direction="negative"
        )
        assert should_use_soft_cta(ctx_momentum) is True

        # All good - no soft CTA needed
        ctx_good = PersonalizationContext.create_test_context(
            state="presentation",
            frustration_level=1,
            momentum_direction="positive"
        )
        assert should_use_soft_cta(ctx_good) is False

    def test_should_use_direct_cta(self):
        """Test should_use_direct_cta condition."""
        ctx = PersonalizationContext.create_test_context(
            state="presentation",
            frustration_level=1
        )
        assert should_use_direct_cta(ctx) is True

        # Wrong state
        ctx_wrong = PersonalizationContext.create_test_context(
            state="spin_implication"
        )
        assert should_use_direct_cta(ctx_wrong) is False

        # High frustration
        ctx_frustrated = PersonalizationContext.create_test_context(
            state="presentation",
            frustration_level=3
        )
        assert should_use_direct_cta(ctx_frustrated) is False

    def test_cta_eligible_state(self):
        """Test cta_eligible_state condition."""
        for state in CTA_ELIGIBLE_STATES:
            ctx = PersonalizationContext.create_test_context(state=state)
            assert cta_eligible_state(ctx) is True, f"Failed for {state}"

        ctx_no = PersonalizationContext.create_test_context(state="greeting")
        assert cta_eligible_state(ctx_no) is False

    def test_enough_turns_for_cta(self):
        """Test enough_turns_for_cta condition."""
        ctx_3 = PersonalizationContext.create_test_context(turn_number=3)
        assert enough_turns_for_cta(ctx_3) is True

        ctx_5 = PersonalizationContext.create_test_context(turn_number=5)
        assert enough_turns_for_cta(ctx_5) is True

        ctx_2 = PersonalizationContext.create_test_context(turn_number=2)
        assert enough_turns_for_cta(ctx_2) is False

    def test_should_skip_cta(self):
        """Test should_skip_cta condition."""
        ctx_high = PersonalizationContext.create_test_context(frustration_level=5)
        assert should_skip_cta(ctx_high) is True

        ctx_low = PersonalizationContext.create_test_context(frustration_level=4)
        assert should_skip_cta(ctx_low) is False

    def test_cta_after_breakthrough(self):
        """Test cta_after_breakthrough condition."""
        ctx = PersonalizationContext.create_test_context(
            has_breakthrough=True,
            frustration_level=2
        )
        assert cta_after_breakthrough(ctx) is True

        ctx_no_breakthrough = PersonalizationContext.create_test_context(
            has_breakthrough=False
        )
        assert cta_after_breakthrough(ctx_no_breakthrough) is False

        ctx_frustrated = PersonalizationContext.create_test_context(
            has_breakthrough=True,
            frustration_level=5
        )
        assert cta_after_breakthrough(ctx_frustrated) is False

    def test_demo_cta_appropriate(self):
        """Test demo_cta_appropriate condition."""
        ctx = PersonalizationContext.create_test_context(
            state="presentation",
            engagement_level="high",
            frustration_level=1
        )
        assert demo_cta_appropriate(ctx) is True

        ctx_wrong_state = PersonalizationContext.create_test_context(state="greeting")
        assert demo_cta_appropriate(ctx_wrong_state) is False

        ctx_low_engagement = PersonalizationContext.create_test_context(
            state="presentation",
            engagement_level="low"
        )
        assert demo_cta_appropriate(ctx_low_engagement) is False

    def test_contact_cta_appropriate(self):
        """Test contact_cta_appropriate condition."""
        ctx_close = PersonalizationContext.create_test_context(state="close")
        assert contact_cta_appropriate(ctx_close) is True

        ctx_breakthrough = PersonalizationContext.create_test_context(
            state="presentation",
            has_breakthrough=True
        )
        assert contact_cta_appropriate(ctx_breakthrough) is True

        ctx_no = PersonalizationContext.create_test_context(state="spin_situation")
        assert contact_cta_appropriate(ctx_no) is False

    def test_trial_cta_appropriate(self):
        """Test trial_cta_appropriate condition."""
        ctx = PersonalizationContext.create_test_context(
            state="presentation",
            total_objections=2
        )
        assert trial_cta_appropriate(ctx) is True

        ctx_hesitant = PersonalizationContext.create_test_context(
            state="presentation",
            engagement_level="medium",
            momentum_direction="neutral"
        )
        assert trial_cta_appropriate(ctx_hesitant) is True

        ctx_wrong_state = PersonalizationContext.create_test_context(state="close")
        assert trial_cta_appropriate(ctx_wrong_state) is False

    def test_info_cta_appropriate(self):
        """Test info_cta_appropriate condition."""
        ctx_early = PersonalizationContext.create_test_context(state="spin_implication")
        assert info_cta_appropriate(ctx_early) is True

        ctx_low = PersonalizationContext.create_test_context(
            state="presentation",
            engagement_level="low"
        )
        assert info_cta_appropriate(ctx_low) is True

        ctx_engaged = PersonalizationContext.create_test_context(
            state="presentation",
            engagement_level="high"
        )
        assert info_cta_appropriate(ctx_engaged) is False


# =============================================================================
# COMPANY CONDITIONS TESTS
# =============================================================================

class TestCompanyConditions:
    """Tests for company-related conditions."""

    def test_has_company_size(self):
        """Test has_company_size condition."""
        ctx = PersonalizationContext.create_test_context(company_size=10)
        assert has_company_size(ctx) is True

        ctx_none = PersonalizationContext.create_test_context(company_size=None)
        assert has_company_size(ctx_none) is False

    def test_is_small_company(self):
        """Test is_small_company condition."""
        ctx_small = PersonalizationContext.create_test_context(company_size=3)
        assert is_small_company(ctx_small) is True

        ctx_boundary = PersonalizationContext.create_test_context(company_size=5)
        assert is_small_company(ctx_boundary) is True

        ctx_medium = PersonalizationContext.create_test_context(company_size=6)
        assert is_small_company(ctx_medium) is False

    def test_is_medium_company(self):
        """Test is_medium_company condition."""
        ctx = PersonalizationContext.create_test_context(company_size=10)
        assert is_medium_company(ctx) is True

        ctx_low = PersonalizationContext.create_test_context(company_size=5)
        assert is_medium_company(ctx_low) is False

        ctx_high = PersonalizationContext.create_test_context(company_size=21)
        assert is_medium_company(ctx_high) is False

    def test_is_large_company(self):
        """Test is_large_company condition."""
        ctx = PersonalizationContext.create_test_context(company_size=25)
        assert is_large_company(ctx) is True

        ctx_boundary = PersonalizationContext.create_test_context(company_size=20)
        assert is_large_company(ctx_boundary) is False

    def test_is_enterprise_company(self):
        """Test is_enterprise_company condition."""
        ctx = PersonalizationContext.create_test_context(company_size=100)
        assert is_enterprise_company(ctx) is True

        ctx_large = PersonalizationContext.create_test_context(company_size=50)
        assert is_enterprise_company(ctx_large) is False

    def test_has_role(self):
        """Test has_role condition."""
        ctx = PersonalizationContext.create_test_context(role="owner")
        assert has_role(ctx) is True

        ctx_none = PersonalizationContext.create_test_context(role=None)
        assert has_role(ctx_none) is False

    def test_is_decision_maker(self):
        """Test is_decision_maker condition."""
        ctx_owner = PersonalizationContext.create_test_context(role="owner")
        assert is_decision_maker(ctx_owner) is True

        ctx_director = PersonalizationContext.create_test_context(role="director")
        assert is_decision_maker(ctx_director) is True

        ctx_manager = PersonalizationContext.create_test_context(role="manager")
        assert is_decision_maker(ctx_manager) is False

    def test_is_manager(self):
        """Test is_manager condition."""
        ctx = PersonalizationContext.create_test_context(role="manager")
        assert is_manager(ctx) is True

        ctx_owner = PersonalizationContext.create_test_context(role="owner")
        assert is_manager(ctx_owner) is False

    def test_has_industry(self):
        """Test has_industry condition."""
        ctx = PersonalizationContext.create_test_context(industry="retail")
        assert has_industry(ctx) is True

        ctx_none = PersonalizationContext.create_test_context(industry=None)
        assert has_industry(ctx_none) is False

    def test_has_company_context(self):
        """Test has_company_context condition."""
        ctx_size = PersonalizationContext.create_test_context(company_size=10)
        assert has_company_context(ctx_size) is True

        ctx_role = PersonalizationContext.create_test_context(role="owner")
        assert has_company_context(ctx_role) is True

        ctx_none = PersonalizationContext.create_test_context()
        assert has_company_context(ctx_none) is False


# =============================================================================
# PAIN CONDITIONS TESTS
# =============================================================================

class TestPainConditions:
    """Tests for pain-related conditions."""

    def test_has_pain_category(self):
        """Test has_pain_category condition."""
        ctx = PersonalizationContext.create_test_context(pain_category="losing_clients")
        assert has_pain_category(ctx) is True

        ctx_none = PersonalizationContext.create_test_context(pain_category=None)
        assert has_pain_category(ctx_none) is False

    def test_has_pain_point(self):
        """Test has_pain_point condition."""
        ctx = PersonalizationContext.create_test_context(pain_point="Sales tracking")
        assert has_pain_point(ctx) is True

        ctx_none = PersonalizationContext.create_test_context(pain_point=None)
        assert has_pain_point(ctx_none) is False

    def test_has_pain_context(self):
        """Test has_pain_context condition."""
        ctx_category = PersonalizationContext.create_test_context(pain_category="no_control")
        assert has_pain_context(ctx_category) is True

        ctx_point = PersonalizationContext.create_test_context(pain_point="Manual work")
        assert has_pain_context(ctx_point) is True

        ctx_none = PersonalizationContext.create_test_context()
        assert has_pain_context(ctx_none) is False

    def test_pain_losing_clients(self):
        """Test pain_losing_clients condition."""
        ctx = PersonalizationContext.create_test_context(pain_category="losing_clients")
        assert pain_losing_clients(ctx) is True

        ctx_other = PersonalizationContext.create_test_context(pain_category="no_control")
        assert pain_losing_clients(ctx_other) is False

    def test_pain_no_control(self):
        """Test pain_no_control condition."""
        ctx = PersonalizationContext.create_test_context(pain_category="no_control")
        assert pain_no_control(ctx) is True

    def test_pain_manual_work(self):
        """Test pain_manual_work condition."""
        ctx = PersonalizationContext.create_test_context(pain_category="manual_work")
        assert pain_manual_work(ctx) is True

    def test_pain_no_analytics(self):
        """Test pain_no_analytics condition."""
        ctx = PersonalizationContext.create_test_context(pain_category="no_analytics")
        assert pain_no_analytics(ctx) is True

    def test_pain_team_chaos(self):
        """Test pain_team_chaos condition."""
        ctx = PersonalizationContext.create_test_context(pain_category="team_chaos")
        assert pain_team_chaos(ctx) is True

    def test_has_current_crm(self):
        """Test has_current_crm condition."""
        ctx = PersonalizationContext.create_test_context(current_crm="Bitrix24")
        assert has_current_crm(ctx) is True

        ctx_none = PersonalizationContext.create_test_context(current_crm=None)
        assert has_current_crm(ctx_none) is False

    def test_competitor_mentioned(self):
        """Test competitor_mentioned condition."""
        ctx = PersonalizationContext.create_test_context(competitor_mentioned=True)
        assert competitor_mentioned(ctx) is True

        ctx_no = PersonalizationContext.create_test_context(competitor_mentioned=False)
        assert competitor_mentioned(ctx_no) is False


# =============================================================================
# ENGAGEMENT CONDITIONS TESTS
# =============================================================================

class TestEngagementConditions:
    """Tests for engagement-related conditions."""

    def test_engagement_high(self):
        """Test engagement_high condition."""
        ctx = PersonalizationContext.create_test_context(engagement_level="high")
        assert engagement_high(ctx) is True

        ctx_medium = PersonalizationContext.create_test_context(engagement_level="medium")
        assert engagement_high(ctx_medium) is False

    def test_engagement_medium(self):
        """Test engagement_medium condition."""
        ctx = PersonalizationContext.create_test_context(engagement_level="medium")
        assert engagement_medium(ctx) is True

        ctx_high = PersonalizationContext.create_test_context(engagement_level="high")
        assert engagement_medium(ctx_high) is False

    def test_engagement_low(self):
        """Test engagement_low condition."""
        ctx_low = PersonalizationContext.create_test_context(engagement_level="low")
        assert engagement_low(ctx_low) is True

        ctx_dis = PersonalizationContext.create_test_context(engagement_level="disengaged")
        assert engagement_low(ctx_dis) is True

        ctx_med = PersonalizationContext.create_test_context(engagement_level="medium")
        assert engagement_low(ctx_med) is False

    def test_momentum_positive(self):
        """Test momentum_positive condition."""
        ctx = PersonalizationContext.create_test_context(momentum_direction="positive")
        assert momentum_positive(ctx) is True

        ctx_neg = PersonalizationContext.create_test_context(momentum_direction="negative")
        assert momentum_positive(ctx_neg) is False

    def test_momentum_negative(self):
        """Test momentum_negative condition."""
        ctx = PersonalizationContext.create_test_context(momentum_direction="negative")
        assert momentum_negative(ctx) is True

    def test_momentum_neutral(self):
        """Test momentum_neutral condition."""
        ctx = PersonalizationContext.create_test_context(momentum_direction="neutral")
        assert momentum_neutral(ctx) is True

    def test_has_breakthrough(self):
        """Test has_breakthrough condition."""
        ctx = PersonalizationContext.create_test_context(has_breakthrough=True)
        assert has_breakthrough(ctx) is True

        ctx_no = PersonalizationContext.create_test_context(has_breakthrough=False)
        assert has_breakthrough(ctx_no) is False


# =============================================================================
# TONE CONDITIONS TESTS
# =============================================================================

class TestToneConditions:
    """Tests for tone-related conditions."""

    def test_frustration_none(self):
        """Test frustration_none condition."""
        ctx = PersonalizationContext.create_test_context(frustration_level=0)
        assert frustration_none(ctx) is True

        ctx_1 = PersonalizationContext.create_test_context(frustration_level=1)
        assert frustration_none(ctx_1) is False

    def test_frustration_low(self):
        """Test frustration_low condition."""
        ctx_1 = PersonalizationContext.create_test_context(frustration_level=1)
        assert frustration_low(ctx_1) is True

        ctx_2 = PersonalizationContext.create_test_context(frustration_level=2)
        assert frustration_low(ctx_2) is True

        ctx_0 = PersonalizationContext.create_test_context(frustration_level=0)
        assert frustration_low(ctx_0) is False

        ctx_3 = PersonalizationContext.create_test_context(frustration_level=3)
        assert frustration_low(ctx_3) is False

    def test_frustration_moderate(self):
        """Test frustration_moderate condition."""
        ctx_3 = PersonalizationContext.create_test_context(frustration_level=3)
        assert frustration_moderate(ctx_3) is True

        ctx_4 = PersonalizationContext.create_test_context(frustration_level=4)
        assert frustration_moderate(ctx_4) is True

        ctx_2 = PersonalizationContext.create_test_context(frustration_level=2)
        assert frustration_moderate(ctx_2) is False

        ctx_5 = PersonalizationContext.create_test_context(frustration_level=5)
        assert frustration_moderate(ctx_5) is False

    def test_frustration_high(self):
        """Test frustration_high condition."""
        ctx_5 = PersonalizationContext.create_test_context(frustration_level=5)
        assert frustration_high(ctx_5) is True

        ctx_6 = PersonalizationContext.create_test_context(frustration_level=6)
        assert frustration_high(ctx_6) is True

        ctx_4 = PersonalizationContext.create_test_context(frustration_level=4)
        assert frustration_high(ctx_4) is False

    def test_needs_soft_approach(self):
        """Test needs_soft_approach condition."""
        ctx_frustrated = PersonalizationContext.create_test_context(frustration_level=3)
        assert needs_soft_approach(ctx_frustrated) is True

        ctx_negative = PersonalizationContext.create_test_context(
            momentum_direction="negative"
        )
        assert needs_soft_approach(ctx_negative) is True

        ctx_low_engagement = PersonalizationContext.create_test_context(
            engagement_level="low"
        )
        assert needs_soft_approach(ctx_low_engagement) is True

        ctx_good = PersonalizationContext.create_test_context(
            frustration_level=1,
            momentum_direction="positive",
            engagement_level="high"
        )
        assert needs_soft_approach(ctx_good) is False


# =============================================================================
# OBJECTION CONDITIONS TESTS
# =============================================================================

class TestObjectionConditions:
    """Tests for objection-related conditions."""

    def test_has_objections(self):
        """Test has_objections condition."""
        ctx = PersonalizationContext.create_test_context(total_objections=1)
        assert has_objections(ctx) is True

        ctx_none = PersonalizationContext.create_test_context(total_objections=0)
        assert has_objections(ctx_none) is False

    def test_has_multiple_objections(self):
        """Test has_multiple_objections condition."""
        ctx = PersonalizationContext.create_test_context(total_objections=2)
        assert has_multiple_objections(ctx) is True

        ctx_1 = PersonalizationContext.create_test_context(total_objections=1)
        assert has_multiple_objections(ctx_1) is False

    def test_has_repeated_objections(self):
        """Test has_repeated_objections condition."""
        ctx = PersonalizationContext.create_test_context(
            repeated_objection_types=["price", "price"]
        )
        assert has_repeated_objections(ctx) is True

        ctx_none = PersonalizationContext.create_test_context(
            repeated_objection_types=[]
        )
        assert has_repeated_objections(ctx_none) is False

    def test_objection_is_price(self):
        """Test objection_is_price condition."""
        ctx = PersonalizationContext.create_test_context(objection_type="objection_price")
        assert objection_is_price(ctx) is True

        ctx_other = PersonalizationContext.create_test_context(objection_type="objection_competitor")
        assert objection_is_price(ctx_other) is False

        ctx_none = PersonalizationContext.create_test_context(objection_type=None)
        assert objection_is_price(ctx_none) is False

    def test_objection_is_competitor(self):
        """Test objection_is_competitor condition."""
        ctx = PersonalizationContext.create_test_context(objection_type="objection_competitor")
        assert objection_is_competitor(ctx) is True

    def test_objection_is_time(self):
        """Test objection_is_time condition."""
        ctx = PersonalizationContext.create_test_context(objection_type="objection_time")
        assert objection_is_time(ctx) is True

        ctx_later = PersonalizationContext.create_test_context(objection_type="call_later")
        assert objection_is_time(ctx_later) is True


# =============================================================================
# STATE CONDITIONS TESTS
# =============================================================================

class TestStateConditions:
    """Tests for state-related conditions."""

    def test_is_spin_state(self):
        """Test is_spin_state condition."""
        for state in ["spin_situation", "spin_problem", "spin_implication", "spin_need_payoff"]:
            ctx = PersonalizationContext.create_test_context(state=state)
            assert is_spin_state(ctx) is True, f"Failed for {state}"

        ctx_no = PersonalizationContext.create_test_context(state="presentation")
        assert is_spin_state(ctx_no) is False

    def test_is_early_state(self):
        """Test is_early_state condition."""
        for state in ["greeting", "spin_situation", "spin_problem"]:
            ctx = PersonalizationContext.create_test_context(state=state)
            assert is_early_state(ctx) is True, f"Failed for {state}"

        ctx_no = PersonalizationContext.create_test_context(state="presentation")
        assert is_early_state(ctx_no) is False

    def test_is_mid_state(self):
        """Test is_mid_state condition."""
        for state in ["spin_implication", "spin_need_payoff"]:
            ctx = PersonalizationContext.create_test_context(state=state)
            assert is_mid_state(ctx) is True, f"Failed for {state}"

        ctx_no = PersonalizationContext.create_test_context(state="presentation")
        assert is_mid_state(ctx_no) is False

    def test_is_late_state(self):
        """Test is_late_state condition."""
        for state in ["presentation", "close", "handle_objection"]:
            ctx = PersonalizationContext.create_test_context(state=state)
            assert is_late_state(ctx) is True, f"Failed for {state}"

        ctx_no = PersonalizationContext.create_test_context(state="spin_situation")
        assert is_late_state(ctx_no) is False

    def test_is_presentation_state(self):
        """Test is_presentation_state condition."""
        ctx = PersonalizationContext.create_test_context(state="presentation")
        assert is_presentation_state(ctx) is True

        ctx_no = PersonalizationContext.create_test_context(state="close")
        assert is_presentation_state(ctx_no) is False

    def test_is_close_state(self):
        """Test is_close_state condition."""
        ctx = PersonalizationContext.create_test_context(state="close")
        assert is_close_state(ctx) is True

    def test_is_objection_state(self):
        """Test is_objection_state condition."""
        ctx = PersonalizationContext.create_test_context(state="handle_objection")
        assert is_objection_state(ctx) is True


# =============================================================================
# COMBINED CONDITIONS TESTS
# =============================================================================

class TestCombinedConditions:
    """Tests for combined conditions."""

    def test_ready_for_strong_cta(self):
        """Test ready_for_strong_cta condition."""
        ctx = PersonalizationContext.create_test_context(
            state="presentation",
            has_breakthrough=True,
            engagement_level="high",
            frustration_level=1
        )
        assert ready_for_strong_cta(ctx) is True

    def test_ready_for_strong_cta_no_breakthrough(self):
        """Test ready_for_strong_cta without breakthrough."""
        ctx = PersonalizationContext.create_test_context(
            state="presentation",
            has_breakthrough=False,
            engagement_level="high"
        )
        assert ready_for_strong_cta(ctx) is False

    def test_ready_for_strong_cta_low_engagement(self):
        """Test ready_for_strong_cta with low engagement."""
        ctx = PersonalizationContext.create_test_context(
            state="presentation",
            has_breakthrough=True,
            engagement_level="low"
        )
        assert ready_for_strong_cta(ctx) is False

    def test_has_rich_context(self):
        """Test has_rich_context condition."""
        ctx_2 = PersonalizationContext.create_test_context(
            company_size=10,
            role="owner"
        )
        assert has_rich_context(ctx_2) is True

        ctx_1 = PersonalizationContext.create_test_context(company_size=10)
        assert has_rich_context(ctx_1) is False

    def test_can_personalize_by_company(self):
        """Test can_personalize_by_company condition."""
        ctx_size = PersonalizationContext.create_test_context(company_size=10)
        assert can_personalize_by_company(ctx_size) is True

        ctx_role_industry = PersonalizationContext.create_test_context(
            role="owner",
            industry="retail"
        )
        assert can_personalize_by_company(ctx_role_industry) is True

        ctx_role_only = PersonalizationContext.create_test_context(role="owner")
        assert can_personalize_by_company(ctx_role_only) is False

    def test_can_personalize_by_pain(self):
        """Test can_personalize_by_pain condition."""
        ctx_category = PersonalizationContext.create_test_context(pain_category="losing_clients")
        assert can_personalize_by_pain(ctx_category) is True

        ctx_point = PersonalizationContext.create_test_context(pain_point="Sales issues")
        assert can_personalize_by_pain(ctx_point) is True

        ctx_competitor = PersonalizationContext.create_test_context(competitor_mentioned=True)
        assert can_personalize_by_pain(ctx_competitor) is True

        ctx_none = PersonalizationContext.create_test_context()
        assert can_personalize_by_pain(ctx_none) is False

    def test_should_be_conservative(self):
        """Test should_be_conservative condition."""
        ctx_objections = PersonalizationContext.create_test_context(total_objections=2)
        assert should_be_conservative(ctx_objections) is True

        ctx_frustrated = PersonalizationContext.create_test_context(frustration_level=3)
        assert should_be_conservative(ctx_frustrated) is True

        ctx_negative = PersonalizationContext.create_test_context(
            momentum_direction="negative"
        )
        assert should_be_conservative(ctx_negative) is True

        ctx_low = PersonalizationContext.create_test_context(engagement_level="low")
        assert should_be_conservative(ctx_low) is True

        ctx_good = PersonalizationContext.create_test_context(
            total_objections=1,
            frustration_level=1,
            momentum_direction="positive",
            engagement_level="high"
        )
        assert should_be_conservative(ctx_good) is False

    def test_should_accelerate(self):
        """Test should_accelerate condition."""
        ctx = PersonalizationContext.create_test_context(
            momentum_direction="positive",
            engagement_level="high",
            has_breakthrough=True
        )
        assert should_accelerate(ctx) is True

        ctx_no_momentum = PersonalizationContext.create_test_context(
            momentum_direction="neutral",
            engagement_level="high",
            has_breakthrough=True
        )
        assert should_accelerate(ctx_no_momentum) is False

    def test_needs_roi_messaging(self):
        """Test needs_roi_messaging condition."""
        ctx = PersonalizationContext.create_test_context(
            objection_type="objection_price",
            company_size=10
        )
        assert needs_roi_messaging(ctx) is True

        ctx_no_size = PersonalizationContext.create_test_context(
            objection_type="objection_price"
        )
        assert needs_roi_messaging(ctx_no_size) is False

        ctx_no_objection = PersonalizationContext.create_test_context(company_size=10)
        assert needs_roi_messaging(ctx_no_objection) is False

    def test_needs_comparison_messaging(self):
        """Test needs_comparison_messaging condition."""
        ctx_mentioned = PersonalizationContext.create_test_context(competitor_mentioned=True)
        assert needs_comparison_messaging(ctx_mentioned) is True

        ctx_objection = PersonalizationContext.create_test_context(
            objection_type="objection_competitor"
        )
        assert needs_comparison_messaging(ctx_objection) is True

        ctx_none = PersonalizationContext.create_test_context()
        assert needs_comparison_messaging(ctx_none) is False

    def test_can_use_case_study(self):
        """Test can_use_case_study condition."""
        ctx = PersonalizationContext.create_test_context(
            industry="retail",
            company_size=10
        )
        assert can_use_case_study(ctx) is True

        ctx_no_industry = PersonalizationContext.create_test_context(company_size=10)
        assert can_use_case_study(ctx_no_industry) is False

        ctx_no_size = PersonalizationContext.create_test_context(industry="retail")
        assert can_use_case_study(ctx_no_size) is False

    def test_optimal_for_demo_offer(self):
        """Test optimal_for_demo_offer condition."""
        ctx = PersonalizationContext.create_test_context(
            state="presentation",
            frustration_level=1,
            engagement_level="high",
            pain_category="losing_clients"
        )
        assert optimal_for_demo_offer(ctx) is True

        ctx_wrong_state = PersonalizationContext.create_test_context(
            state="close",
            pain_category="losing_clients"
        )
        assert optimal_for_demo_offer(ctx_wrong_state) is False

        ctx_no_pain = PersonalizationContext.create_test_context(state="presentation")
        assert optimal_for_demo_offer(ctx_no_pain) is False

    def test_needs_urgency_reduction(self):
        """Test needs_urgency_reduction condition."""
        ctx_time = PersonalizationContext.create_test_context(
            objection_type="objection_time"
        )
        assert needs_urgency_reduction(ctx_time) is True

        ctx_low = PersonalizationContext.create_test_context(engagement_level="low")
        assert needs_urgency_reduction(ctx_low) is True

        ctx_good = PersonalizationContext.create_test_context(
            engagement_level="high"
        )
        assert needs_urgency_reduction(ctx_good) is False


# =============================================================================
# INTEGRATION TESTS
# =============================================================================

class TestIntegration:
    """Integration tests for Personalization conditions."""

    def test_presentation_with_breakthrough_scenario(self):
        """Test presentation state with breakthrough."""
        ctx = PersonalizationContext.create_test_context(
            state="presentation",
            turn_number=6,
            has_breakthrough=True,
            engagement_level="high",
            momentum_direction="positive",
            frustration_level=1,
            pain_category="losing_clients",
            company_size=15
        )

        assert should_add_cta(ctx) is True
        assert ready_for_strong_cta(ctx) is True
        assert should_accelerate(ctx) is True
        assert demo_cta_appropriate(ctx) is True
        assert contact_cta_appropriate(ctx) is True
        assert optimal_for_demo_offer(ctx) is True
        assert should_use_direct_cta(ctx) is True

    def test_objection_handling_scenario(self):
        """Test objection handling scenario."""
        ctx = PersonalizationContext.create_test_context(
            state="handle_objection",
            turn_number=5,
            objection_type="objection_price",
            total_objections=2,
            company_size=10,
            frustration_level=2
        )

        assert is_objection_state(ctx) is True
        assert has_multiple_objections(ctx) is True
        assert objection_is_price(ctx) is True
        assert needs_roi_messaging(ctx) is True
        assert should_be_conservative(ctx) is True

    def test_early_conversation_scenario(self):
        """Test early conversation scenario."""
        ctx = PersonalizationContext.create_test_context(
            state="spin_situation",
            turn_number=2,
            engagement_level="medium"
        )

        assert should_add_cta(ctx) is False
        assert is_early_state(ctx) is True
        assert enough_turns_for_cta(ctx) is False

    def test_high_frustration_scenario(self):
        """Test high frustration scenario."""
        ctx = PersonalizationContext.create_test_context(
            state="presentation",
            turn_number=5,
            frustration_level=5,
            engagement_level="low",
            momentum_direction="negative"
        )

        assert should_add_cta(ctx) is False
        assert should_skip_cta(ctx) is True
        assert frustration_high(ctx) is True
        assert needs_soft_approach(ctx) is True
        assert should_be_conservative(ctx) is True

    def test_rich_context_personalization_scenario(self):
        """Test rich context personalization scenario."""
        ctx = PersonalizationContext.create_test_context(
            state="presentation",
            turn_number=5,
            company_size=20,
            role="director",
            industry="retail",
            pain_category="losing_clients",
            competitor_mentioned=True
        )

        assert has_rich_context(ctx) is True
        assert can_personalize_by_company(ctx) is True
        assert can_personalize_by_pain(ctx) is True
        assert needs_comparison_messaging(ctx) is True
        assert can_use_case_study(ctx) is True
        assert is_decision_maker(ctx) is True


# =============================================================================
# DOCUMENTATION TESTS
# =============================================================================

class TestDocumentation:
    """Tests for documentation generation."""

    def test_registry_documentation(self):
        """Test that registry can generate documentation."""
        docs = personalization_registry.get_documentation()

        assert "Personalization Conditions" in docs
        assert "PersonalizationContext" in docs
        assert "should_add_cta" in docs
        assert "cta" in docs.lower()
        assert "company" in docs.lower()

    def test_registry_stats(self):
        """Test registry statistics."""
        stats = personalization_registry.get_stats()

        assert stats["name"] == "personalization"
        assert stats["total_conditions"] > 0
        assert stats["total_categories"] >= 7
        assert "cta" in stats["conditions_by_category"]
        assert "company" in stats["conditions_by_category"]


# =============================================================================
# EDGE CASES TESTS
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_boundary_frustration_levels(self):
        """Test boundary frustration levels."""
        ctx_2 = PersonalizationContext.create_test_context(frustration_level=2)
        assert frustration_low(ctx_2) is True
        assert frustration_moderate(ctx_2) is False

        ctx_3 = PersonalizationContext.create_test_context(frustration_level=3)
        assert frustration_low(ctx_3) is False
        assert frustration_moderate(ctx_3) is True

        ctx_5 = PersonalizationContext.create_test_context(frustration_level=5)
        assert frustration_moderate(ctx_5) is False
        assert frustration_high(ctx_5) is True

    def test_boundary_company_sizes(self):
        """Test boundary company sizes."""
        # Small company boundary
        ctx_5 = PersonalizationContext.create_test_context(company_size=5)
        assert is_small_company(ctx_5) is True

        ctx_6 = PersonalizationContext.create_test_context(company_size=6)
        assert is_small_company(ctx_6) is False
        assert is_medium_company(ctx_6) is True

        # Large company boundary
        ctx_20 = PersonalizationContext.create_test_context(company_size=20)
        assert is_medium_company(ctx_20) is True
        assert is_large_company(ctx_20) is False

        ctx_21 = PersonalizationContext.create_test_context(company_size=21)
        assert is_large_company(ctx_21) is True

        # Enterprise boundary
        ctx_50 = PersonalizationContext.create_test_context(company_size=50)
        assert is_enterprise_company(ctx_50) is False

        ctx_51 = PersonalizationContext.create_test_context(company_size=51)
        assert is_enterprise_company(ctx_51) is True

    def test_boundary_turn_numbers(self):
        """Test boundary turn numbers."""
        ctx_2 = PersonalizationContext.create_test_context(turn_number=2)
        assert enough_turns_for_cta(ctx_2) is False

        ctx_3 = PersonalizationContext.create_test_context(turn_number=3)
        assert enough_turns_for_cta(ctx_3) is True

    def test_none_values_handling(self):
        """Test handling of None values."""
        ctx = PersonalizationContext.create_test_context(
            company_size=None,
            role=None,
            industry=None,
            pain_category=None,
            pain_point=None,
            objection_type=None
        )

        assert has_company_size(ctx) is False
        assert is_small_company(ctx) is False
        assert has_role(ctx) is False
        assert has_industry(ctx) is False
        assert has_pain_category(ctx) is False
        assert has_pain_point(ctx) is False
        assert objection_is_price(ctx) is False

    def test_zero_values(self):
        """Test with zero values."""
        ctx = PersonalizationContext.create_test_context(
            turn_number=0,
            frustration_level=0,
            total_objections=0,
            cta_count=0,
            company_size=0
        )

        assert frustration_none(ctx) is True
        assert has_objections(ctx) is False
        assert is_small_company(ctx) is False  # 0 is not in range (0, 5]

    def test_empty_lists(self):
        """Test with empty lists."""
        ctx = PersonalizationContext.create_test_context(
            repeated_objection_types=[]
        )

        assert has_repeated_objections(ctx) is False
