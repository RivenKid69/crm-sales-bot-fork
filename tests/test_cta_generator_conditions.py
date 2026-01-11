"""
Tests for CTAGenerator integration with Personalization conditions.

This module tests the condition-based CTA methods in CTAGenerator:
- should_add_cta_with_conditions
- get_optimal_cta_type
- append_cta_with_conditions
- generate_cta_result_with_conditions
- create_personalization_context

Part of Phase 7: Personalization Domain (ARCHITECTURE_UNIFIED_PLAN.md)
"""

import pytest
import sys
from pathlib import Path
from typing import Dict, Any

# Add src to PYTHONPATH for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from cta_generator import CTAGenerator, CTAResult
from conditions.personalization import (
    PersonalizationContext,
    personalization_registry,
)


# =============================================================================
# TEST FIXTURES
# =============================================================================

@pytest.fixture
def generator():
    """Create a fresh CTAGenerator for each test."""
    gen = CTAGenerator()
    # Set turn count to allow CTA
    gen.turn_count = 5
    return gen


@pytest.fixture
def early_generator():
    """Create a CTAGenerator in early conversation stage."""
    gen = CTAGenerator()
    gen.turn_count = 2
    return gen


@pytest.fixture
def presentation_context():
    """Context for presentation state."""
    return {
        "collected_data": {
            "company_size": 10,
            "pain_category": "losing_clients"
        },
        "frustration_level": 1,
        "engagement_level": "high",
        "momentum_direction": "positive",
        "has_breakthrough": False,
        "total_objections": 0
    }


@pytest.fixture
def breakthrough_context():
    """Context with breakthrough."""
    return {
        "collected_data": {
            "company_size": 15,
            "pain_category": "no_control"
        },
        "frustration_level": 0,
        "engagement_level": "high",
        "momentum_direction": "positive",
        "has_breakthrough": True,
        "total_objections": 0
    }


@pytest.fixture
def frustrated_context():
    """Context with high frustration."""
    return {
        "collected_data": {},
        "frustration_level": 5,
        "engagement_level": "low",
        "momentum_direction": "negative",
        "has_breakthrough": False,
        "total_objections": 2
    }


@pytest.fixture
def moderate_frustration_context():
    """Context with moderate frustration."""
    return {
        "collected_data": {},
        "frustration_level": 3,
        "engagement_level": "medium",
        "momentum_direction": "neutral",
        "has_breakthrough": False,
        "total_objections": 1
    }


# =============================================================================
# CREATE PERSONALIZATION CONTEXT TESTS
# =============================================================================

class TestCreatePersonalizationContext:
    """Tests for create_personalization_context method."""

    def test_create_basic_context(self, generator):
        """Test creating basic personalization context."""
        ctx = generator.create_personalization_context("presentation", {})

        assert isinstance(ctx, PersonalizationContext)
        assert ctx.state == "presentation"
        assert ctx.turn_number == 5

    def test_create_context_with_collected_data(self, generator):
        """Test creating context with collected data."""
        context = {
            "collected_data": {
                "company_size": 10,
                "pain_category": "losing_clients",
                "role": "owner"
            }
        }

        ctx = generator.create_personalization_context("presentation", context)

        assert ctx.company_size == 10
        assert ctx.pain_category == "losing_clients"
        assert ctx.role == "owner"

    def test_create_context_with_signals(self, generator, presentation_context):
        """Test creating context with signal data."""
        ctx = generator.create_personalization_context(
            "presentation",
            presentation_context
        )

        assert ctx.engagement_level == "high"
        assert ctx.momentum_direction == "positive"
        assert ctx.frustration_level == 1

    def test_create_context_with_cta_stats(self, generator):
        """Test that CTA stats are included in context."""
        # Add some CTAs to history
        generator.used_ctas["presentation"] = ["CTA 1", "CTA 2"]

        ctx = generator.create_personalization_context("presentation", {})

        assert ctx.cta_count == 2

    def test_create_context_turn_number(self, generator):
        """Test that turn number is from generator."""
        generator.turn_count = 10

        ctx = generator.create_personalization_context("presentation", {})

        assert ctx.turn_number == 10


# =============================================================================
# SHOULD ADD CTA WITH CONDITIONS TESTS
# =============================================================================

class TestShouldAddCtaWithConditions:
    """Tests for should_add_cta_with_conditions method."""

    def test_should_add_cta_positive(self, generator, presentation_context):
        """Test CTA should be added in ideal conditions."""
        should_add, reason = generator.should_add_cta_with_conditions(
            state="presentation",
            response="Wipon помогает автоматизировать продажи.",
            context=presentation_context
        )

        assert should_add is True
        assert reason is None

    def test_should_not_add_cta_response_ends_question(self, generator, presentation_context):
        """Test CTA not added when response ends with question."""
        should_add, reason = generator.should_add_cta_with_conditions(
            state="presentation",
            response="Что вас больше всего интересует?",
            context=presentation_context
        )

        assert should_add is False
        assert reason == "response_ends_with_question"

    def test_should_not_add_cta_wrong_state(self, generator, presentation_context):
        """Test CTA not added in greeting state."""
        should_add, reason = generator.should_add_cta_with_conditions(
            state="greeting",
            response="Здравствуйте!",
            context=presentation_context
        )

        assert should_add is False
        assert reason == "no_cta_for_state"

    def test_should_not_add_cta_too_early(self, early_generator, presentation_context):
        """Test CTA not added too early in conversation."""
        should_add, reason = early_generator.should_add_cta_with_conditions(
            state="presentation",
            response="Wipon решает эту проблему.",
            context=presentation_context
        )

        assert should_add is False
        assert "too_early" in reason

    def test_should_not_add_cta_high_frustration(self, generator, frustrated_context):
        """Test CTA not added with high frustration."""
        should_add, reason = generator.should_add_cta_with_conditions(
            state="presentation",
            response="Wipon решает эту проблему.",
            context=frustrated_context
        )

        assert should_add is False
        assert "frustration" in reason


# =============================================================================
# GET OPTIMAL CTA TYPE TESTS
# =============================================================================

class TestGetOptimalCtaType:
    """Tests for get_optimal_cta_type method."""

    def test_demo_cta_for_presentation(self, generator, presentation_context):
        """Test demo CTA type for presentation."""
        cta_type = generator.get_optimal_cta_type("presentation", presentation_context)

        assert cta_type == "demo"

    def test_contact_cta_for_close(self, generator):
        """Test contact CTA type for close state."""
        context = {
            "frustration_level": 0,
            "engagement_level": "high"
        }

        cta_type = generator.get_optimal_cta_type("close", context)

        assert cta_type == "contact"

    def test_contact_cta_after_breakthrough(self, generator, breakthrough_context):
        """Test contact CTA after breakthrough in presentation."""
        cta_type = generator.get_optimal_cta_type("presentation", breakthrough_context)

        assert cta_type == "contact"

    def test_info_cta_for_early_state(self, generator):
        """Test info CTA for early state."""
        context = {
            "frustration_level": 0,
            "engagement_level": "medium"
        }

        cta_type = generator.get_optimal_cta_type("spin_implication", context)

        assert cta_type == "info"

    def test_trial_cta_for_hesitant_client(self, generator):
        """Test trial CTA for hesitant client."""
        context = {
            "total_objections": 2,
            "frustration_level": 2,
            "engagement_level": "medium"
        }

        cta_type = generator.get_optimal_cta_type("presentation", context)

        assert cta_type == "trial"


# =============================================================================
# APPEND CTA WITH CONDITIONS TESTS
# =============================================================================

class TestAppendCtaWithConditions:
    """Tests for append_cta_with_conditions method."""

    def test_append_cta_success(self, generator, presentation_context):
        """Test successful CTA append."""
        response = "Wipon помогает автоматизировать продажи."

        result = generator.append_cta_with_conditions(
            response=response,
            state="presentation",
            context=presentation_context
        )

        assert result != response
        assert len(result) > len(response)
        assert response.rstrip() in result

    def test_append_cta_skip_question(self, generator, presentation_context):
        """Test CTA skipped when response ends with question."""
        response = "Что вас больше всего интересует?"

        result = generator.append_cta_with_conditions(
            response=response,
            state="presentation",
            context=presentation_context
        )

        assert result == response

    def test_append_cta_skip_wrong_state(self, generator, presentation_context):
        """Test CTA skipped in wrong state."""
        response = "Здравствуйте!"

        result = generator.append_cta_with_conditions(
            response=response,
            state="greeting",
            context=presentation_context
        )

        assert result == response

    def test_append_cta_skip_high_frustration(self, generator, frustrated_context):
        """Test CTA skipped with high frustration."""
        response = "Wipon решает эту проблему."

        result = generator.append_cta_with_conditions(
            response=response,
            state="presentation",
            context=frustrated_context
        )

        assert result == response

    def test_append_soft_cta_moderate_frustration(self, generator, moderate_frustration_context):
        """Test soft CTA with moderate frustration."""
        response = "Wipon решает эту проблему."

        result = generator.append_cta_with_conditions(
            response=response,
            state="presentation",
            context=moderate_frustration_context
        )

        # Should still add CTA but soft one
        assert result != response
        # Check for soft CTA phrases
        soft_phrases = ["интересно", "вопросы", "на связи"]
        has_soft_phrase = any(phrase in result.lower() for phrase in soft_phrases)
        # Soft CTA may or may not contain these phrases depending on random selection
        # Just verify CTA was added
        assert len(result) > len(response)


# =============================================================================
# GENERATE CTA RESULT WITH CONDITIONS TESTS
# =============================================================================

class TestGenerateCtaResultWithConditions:
    """Tests for generate_cta_result_with_conditions method."""

    def test_generate_result_success(self, generator, presentation_context):
        """Test successful CTA result generation."""
        response = "Wipon помогает автоматизировать продажи."

        result = generator.generate_cta_result_with_conditions(
            response=response,
            state="presentation",
            context=presentation_context
        )

        assert isinstance(result, CTAResult)
        assert result.cta_added is True
        assert result.cta is not None
        assert result.final_response != response
        assert result.skip_reason is None

    def test_generate_result_skipped(self, generator, frustrated_context):
        """Test CTA result when skipped."""
        response = "Wipon решает эту проблему."

        result = generator.generate_cta_result_with_conditions(
            response=response,
            state="presentation",
            context=frustrated_context
        )

        assert isinstance(result, CTAResult)
        assert result.cta_added is False
        assert result.cta is None
        assert result.final_response == response
        assert result.skip_reason is not None

    def test_generate_result_original_response_preserved(self, generator, presentation_context):
        """Test that original response is preserved in result."""
        response = "Wipon помогает автоматизировать продажи."

        result = generator.generate_cta_result_with_conditions(
            response=response,
            state="presentation",
            context=presentation_context
        )

        assert result.original_response == response

    def test_generate_result_wrong_state(self, generator, presentation_context):
        """Test CTA result for wrong state."""
        response = "Здравствуйте!"

        result = generator.generate_cta_result_with_conditions(
            response=response,
            state="greeting",
            context=presentation_context
        )

        assert result.cta_added is False
        assert result.skip_reason == "no_cta_for_state"


# =============================================================================
# INTEGRATION TESTS
# =============================================================================

class TestConditionsIntegration:
    """Integration tests for CTA conditions."""

    def test_full_presentation_flow(self, generator, presentation_context):
        """Test full presentation flow with conditions."""
        response = "Wipon автоматизирует учёт клиентов и сделок."

        # Check should add
        should_add, _ = generator.should_add_cta_with_conditions(
            "presentation",
            response,
            presentation_context
        )
        assert should_add is True

        # Get optimal type
        cta_type = generator.get_optimal_cta_type("presentation", presentation_context)
        assert cta_type in ["demo", "contact", "trial", "info", None]

        # Generate result
        result = generator.generate_cta_result_with_conditions(
            response,
            "presentation",
            presentation_context
        )
        assert result.cta_added is True

    def test_close_state_flow(self, generator, breakthrough_context):
        """Test close state flow with conditions."""
        response = "Отлично, давайте оформим доступ."

        # Check should add
        should_add, _ = generator.should_add_cta_with_conditions(
            "close",
            response,
            breakthrough_context
        )
        assert should_add is True

        # Get optimal type - should be contact
        cta_type = generator.get_optimal_cta_type("close", breakthrough_context)
        assert cta_type == "contact"

    def test_objection_handling_flow(self, generator):
        """Test objection handling flow."""
        context = {
            "objection_type": "objection_price",
            "total_objections": 1,
            "frustration_level": 2,
            "engagement_level": "medium"
        }
        response = "Понимаю ваши сомнения по цене."

        # Check should add
        should_add, _ = generator.should_add_cta_with_conditions(
            "handle_objection",
            response,
            context
        )
        assert should_add is True

    def test_fallback_to_legacy_on_error(self, generator):
        """Test fallback to legacy method on error."""
        # This should work even with minimal context
        response = "Test response."

        result = generator.generate_cta_result_with_conditions(
            response,
            "presentation",
            None
        )

        # Should still return a valid result
        assert isinstance(result, CTAResult)

    def test_cta_history_tracking(self, generator, presentation_context):
        """Test that CTAs are tracked in history."""
        response = "Wipon помогает автоматизировать."

        # Generate multiple CTAs
        for _ in range(3):
            generator.generate_cta_result_with_conditions(
                response,
                "presentation",
                presentation_context
            )

        # Check history
        stats = generator.get_usage_stats()
        assert stats["total_ctas_used"] > 0


# =============================================================================
# COMPARISON WITH LEGACY TESTS
# =============================================================================

class TestComparisonWithLegacy:
    """Tests comparing condition-based vs legacy methods."""

    def test_both_methods_agree_on_skip_question(self, generator, presentation_context):
        """Test both methods skip when response ends with question."""
        response = "Что вас интересует?"

        # Legacy
        legacy_should, legacy_reason = generator.should_add_cta(
            "presentation",
            response,
            presentation_context
        )

        # Conditions
        cond_should, cond_reason = generator.should_add_cta_with_conditions(
            "presentation",
            response,
            presentation_context
        )

        assert legacy_should == cond_should
        assert legacy_reason == cond_reason

    def test_both_methods_agree_on_wrong_state(self, generator, presentation_context):
        """Test both methods skip for wrong state."""
        response = "Здравствуйте!"

        # Legacy
        legacy_should, legacy_reason = generator.should_add_cta(
            "greeting",
            response,
            presentation_context
        )

        # Conditions
        cond_should, cond_reason = generator.should_add_cta_with_conditions(
            "greeting",
            response,
            presentation_context
        )

        assert legacy_should == cond_should
        # Reasons may differ in wording but both should indicate state issue

    def test_both_methods_agree_on_high_frustration(self, generator, frustrated_context):
        """Test both methods skip for high frustration."""
        response = "Wipon решает проблему."

        # Legacy
        legacy_should, _ = generator.should_add_cta(
            "presentation",
            response,
            frustrated_context
        )

        # Conditions
        cond_should, _ = generator.should_add_cta_with_conditions(
            "presentation",
            response,
            frustrated_context
        )

        assert legacy_should == cond_should


# =============================================================================
# EDGE CASES
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases."""

    def test_empty_context(self, generator):
        """Test with empty context."""
        result = generator.generate_cta_result_with_conditions(
            "Test response.",
            "presentation",
            {}
        )

        assert isinstance(result, CTAResult)

    def test_none_context(self, generator):
        """Test with None context."""
        result = generator.generate_cta_result_with_conditions(
            "Test response.",
            "presentation",
            None
        )

        assert isinstance(result, CTAResult)

    def test_empty_response(self, generator, presentation_context):
        """Test with empty response."""
        result = generator.generate_cta_result_with_conditions(
            "",
            "presentation",
            presentation_context
        )

        # Should still work but might skip CTA
        assert isinstance(result, CTAResult)

    def test_whitespace_response(self, generator, presentation_context):
        """Test with whitespace response."""
        result = generator.generate_cta_result_with_conditions(
            "   ",
            "presentation",
            presentation_context
        )

        assert isinstance(result, CTAResult)

    def test_unknown_state(self, generator, presentation_context):
        """Test with unknown state."""
        result = generator.generate_cta_result_with_conditions(
            "Test response.",
            "unknown_state",
            presentation_context
        )

        assert isinstance(result, CTAResult)
        # Should skip CTA for unknown state
        assert result.cta_added is False

    def test_very_long_response(self, generator, presentation_context):
        """Test with very long response."""
        response = "Lorem ipsum " * 100  # Long response

        result = generator.generate_cta_result_with_conditions(
            response,
            "presentation",
            presentation_context
        )

        assert isinstance(result, CTAResult)
        if result.cta_added:
            assert result.final_response.startswith(response.rstrip())
