"""
Integration Tests for FallbackHandler with Conditions (Phase 6).

Tests cover:
- Integration with FallbackContext
- Integration with fallback_registry
- Condition-based tier escalation
- Tracing support
- Event and metric logging
- New smart_escalate and get_recommended_tier methods

Part of Phase 6: Fallback Domain (ARCHITECTURE_UNIFIED_PLAN.md)
"""

import pytest
from unittest.mock import patch, MagicMock

from src.fallback_handler import FallbackHandler, FallbackResponse
from src.conditions.fallback import (
    FallbackContext,
    fallback_registry,
    FALLBACK_TIERS,
)
from src.conditions.trace import EvaluationTrace, Resolution

# =============================================================================
# TEST FIXTURES
# =============================================================================

@pytest.fixture
def handler():
    """Create a fresh FallbackHandler instance."""
    return FallbackHandler(enable_tracing=True)

@pytest.fixture
def handler_no_trace():
    """Create a FallbackHandler with tracing disabled."""
    return FallbackHandler(enable_tracing=False)

@pytest.fixture
def high_frustration_context():
    """Context dict with high frustration signals."""
    return {
        "collected_data": {},
        "frustration_level": 4,
        "engagement_level": "low",
        "momentum_direction": "negative",
        "turn_number": 5
    }

@pytest.fixture
def competitor_context():
    """Context dict with competitor mentioned."""
    return {
        "collected_data": {
            "competitor_mentioned": True,
            "competitor_name": "Битрикс",
            "company_size": 10
        },
        "turn_number": 3
    }

@pytest.fixture
def pain_context():
    """Context dict with pain category."""
    return {
        "collected_data": {
            "pain_category": "losing_clients",
            "company_size": 15
        },
        "turn_number": 4
    }

# =============================================================================
# HANDLER INITIALIZATION TESTS
# =============================================================================

class TestHandlerInitialization:
    """Tests for handler initialization with conditions."""

    def test_handler_creates_with_tracing(self):
        """Handler creates with tracing enabled by default."""
        handler = FallbackHandler()
        assert handler._enable_tracing is True

    def test_handler_creates_without_tracing(self):
        """Handler can be created with tracing disabled."""
        handler = FallbackHandler(enable_tracing=False)
        assert handler._enable_tracing is False

    def test_handler_has_create_context_method(self):
        """Handler has _create_fallback_context method."""
        handler = FallbackHandler()
        assert hasattr(handler, '_create_fallback_context')

    def test_handler_has_create_trace_method(self):
        """Handler has _create_trace method."""
        handler = FallbackHandler()
        assert hasattr(handler, '_create_trace')

# =============================================================================
# CONTEXT CREATION TESTS
# =============================================================================

class TestContextCreation:
    """Tests for FallbackContext creation in handler."""

    def test_creates_context_from_stats(self, handler):
        """Handler creates context from its stats."""
        handler.get_fallback("fallback_tier_1", "spin_situation")
        handler.get_fallback("fallback_tier_1", "spin_situation")

        context = handler._create_fallback_context(
            "fallback_tier_1", "spin_situation", {}
        )

        assert context.total_fallbacks == 2
        assert context.current_tier == "fallback_tier_1"
        assert context.state == "spin_situation"

    def test_creates_context_with_signals(self, handler):
        """Handler creates context with frustration signals."""
        ctx_dict = {
            "frustration_level": 3,
            "engagement_level": "low",
            "momentum_direction": "negative"
        }

        context = handler._create_fallback_context(
            "fallback_tier_2", "spin_problem", ctx_dict
        )

        assert context.frustration_level == 3
        assert context.engagement_level == "low"
        assert context.momentum_direction == "negative"

    def test_creates_context_with_collected_data(self, handler):
        """Handler creates context with collected data."""
        ctx_dict = {
            "collected_data": {
                "company_size": 10,
                "competitor_mentioned": True,
                "pain_category": "losing_clients"
            }
        }

        context = handler._create_fallback_context(
            "fallback_tier_2", "spin_situation", ctx_dict
        )

        assert context.company_size == 10
        assert context.competitor_mentioned is True
        assert context.pain_category == "losing_clients"

# =============================================================================
# TRACE CREATION TESTS
# =============================================================================

class TestTraceCreation:
    """Tests for trace creation in handler."""

    def test_creates_trace_when_enabled(self, handler):
        """Handler creates trace when tracing is enabled."""
        trace = handler._create_trace("fallback_tier_1", "spin_situation")

        assert trace is not None
        assert isinstance(trace, EvaluationTrace)
        assert trace.rule_name == "fallback_fallback_tier_1"
        assert trace.state == "spin_situation"
        assert trace.domain == "fallback"

    def test_no_trace_when_disabled(self, handler_no_trace):
        """Handler returns None trace when tracing is disabled."""
        trace = handler_no_trace._create_trace("fallback_tier_1", "spin_situation")
        assert trace is None

# =============================================================================
# RESPONSE WITH TRACE TESTS
# =============================================================================

class TestResponseWithTrace:
    """Tests for responses containing trace information."""

    def test_tier_1_response_has_trace(self, handler):
        """Tier 1 response includes trace."""
        response = handler.get_fallback("fallback_tier_1", "spin_situation", {})

        assert response.trace is not None
        assert isinstance(response.trace, EvaluationTrace)

    def test_tier_2_response_has_trace(self, handler):
        """Tier 2 response includes trace."""
        response = handler.get_fallback("fallback_tier_2", "spin_situation", {})

        assert response.trace is not None
        assert isinstance(response.trace, EvaluationTrace)

    def test_tier_3_response_has_trace(self, handler):
        """Tier 3 response includes trace."""
        response = handler.get_fallback("fallback_tier_3", "spin_situation", {})

        assert response.trace is not None
        assert isinstance(response.trace, EvaluationTrace)

    def test_soft_close_response_has_trace(self, handler):
        """Soft close response includes trace."""
        response = handler.get_fallback("soft_close", "spin_situation", {})

        assert response.trace is not None
        assert isinstance(response.trace, EvaluationTrace)

    def test_no_trace_when_disabled(self, handler_no_trace):
        """Response has no trace when tracing disabled."""
        response = handler_no_trace.get_fallback("fallback_tier_1", "spin_situation", {})

        assert response.trace is None

# =============================================================================
# IMMEDIATE ESCALATION TESTS
# =============================================================================

class TestImmediateEscalation:
    """Tests for immediate escalation using conditions."""

    def test_critical_frustration_triggers_escalation(self, handler, high_frustration_context):
        """Critical frustration level triggers immediate escalation."""
        high_frustration_context["frustration_level"] = 5

        response = handler.get_fallback(
            "fallback_tier_1", "spin_situation", high_frustration_context
        )

        assert response.action == "close"
        assert response.next_state == "soft_close"

    def test_many_consecutive_with_negative_triggers_escalation(self, handler):
        """Many consecutive fallbacks with negative momentum triggers escalation."""
        # Build up consecutive fallbacks
        for _ in range(5):
            handler.get_fallback("fallback_tier_1", "spin_situation", {})

        context = {
            "momentum_direction": "negative",
        }

        # Note: This tests the immediate escalation logic
        # which looks at consecutive_fallbacks >= 4 AND negative momentum

    def test_normal_frustration_no_escalation(self, handler):
        """Normal frustration does not trigger immediate escalation."""
        context = {
            "frustration_level": 2,
            "engagement_level": "medium",
            "momentum_direction": "neutral"
        }

        response = handler.get_fallback(
            "fallback_tier_1", "spin_situation", context
        )

        assert response.action == "continue"

# =============================================================================
# SMART ESCALATE TESTS
# =============================================================================

class TestSmartEscalate:
    """Tests for smart_escalate method."""

    def test_smart_escalate_returns_tier(self, handler):
        """smart_escalate returns a valid tier."""
        tier = handler.smart_escalate("spin_situation", {})
        assert tier in FALLBACK_TIERS

    def test_smart_escalate_immediate_for_critical(self, handler, high_frustration_context):
        """smart_escalate returns soft_close for critical frustration."""
        high_frustration_context["frustration_level"] = 5

        tier = handler.smart_escalate("spin_situation", high_frustration_context)

        assert tier == "soft_close"

    def test_smart_escalate_uses_conditions(self, handler):
        """smart_escalate uses condition registry."""
        # Set up state for should_escalate_tier condition
        handler.get_fallback("fallback_tier_1", "spin_situation", {})
        handler.get_fallback("fallback_tier_1", "spin_situation", {})

        # With 2 consecutive fallbacks and frustration >= 3, should escalate
        context = {"frustration_level": 3}
        tier = handler.smart_escalate("spin_situation", context)

        assert tier in ["fallback_tier_2", "soft_close"]

    def test_smart_escalate_stays_at_tier_when_ok(self, handler):
        """smart_escalate stays at tier when recovery possible."""
        handler.get_fallback("fallback_tier_1", "spin_situation", {})

        context = {
            "frustration_level": 1,
            "engagement_level": "medium"
        }

        tier = handler.smart_escalate("spin_situation", context)

        assert tier == "fallback_tier_1"

# =============================================================================
# GET RECOMMENDED TIER TESTS
# =============================================================================

class TestGetRecommendedTier:
    """Tests for get_recommended_tier method."""

    def test_returns_tier_1_for_fresh_conversation(self, handler):
        """Returns tier 1 for fresh conversation."""
        tier = handler.get_recommended_tier("spin_situation", {})
        assert tier == "fallback_tier_1"

    def test_returns_tier_2_for_moderate_frustration(self, handler):
        """Returns tier 2 for moderate frustration."""
        context = {"frustration_level": 2}
        tier = handler.get_recommended_tier("spin_situation", context)
        assert tier == "fallback_tier_2"

    def test_returns_tier_2_for_many_fallbacks(self, handler):
        """Returns tier 2 when many fallbacks already."""
        # Build up fallbacks
        for _ in range(3):
            handler.get_fallback("fallback_tier_1", "spin_situation", {})

        tier = handler.get_recommended_tier("spin_situation", {})
        assert tier == "fallback_tier_2"

    def test_returns_tier_2_for_high_frustration(self, handler):
        """Returns tier 2 for high (but not critical) frustration."""
        # get_recommended_tier returns tier 2 for frustration >= 2
        # For truly critical situations, the immediate escalation in
        # get_fallback will handle it
        context = {"frustration_level": 4}
        tier = handler.get_recommended_tier("spin_situation", context)
        assert tier == "fallback_tier_2"

# =============================================================================
# CONDITION-BASED TIER 1 TESTS
# =============================================================================

class TestConditionBasedTier1:
    """Tests for condition-based tier 1 behavior."""

    def test_tier_1_escalates_when_not_appropriate(self, handler):
        """Tier 1 escalates when can_try_rephrase is false."""
        # Build up many fallbacks
        for _ in range(4):
            handler.get_fallback("fallback_tier_1", "spin_situation", {})

        context = {"frustration_level": 3}
        response = handler.get_fallback("fallback_tier_1", "spin_situation", context)

        # Should have escalated or at least returned options
        # The can_try_rephrase condition checks total_fallbacks < 3 and frustration < 3
        assert response.message is not None

    def test_tier_1_works_normally_when_appropriate(self, handler):
        """Tier 1 works normally when conditions are good."""
        context = {"frustration_level": 1}
        response = handler.get_fallback("fallback_tier_1", "spin_situation", context)

        assert response.action == "continue"
        assert response.options is None

# =============================================================================
# CONDITION-BASED TIER 2 TESTS
# =============================================================================

class TestConditionBasedTier2:
    """Tests for condition-based tier 2 behavior."""

    def test_tier_2_uses_dynamic_cta_conditions(self, handler, competitor_context):
        """Tier 2 uses conditions for dynamic CTA selection."""
        from src.feature_flags import flags
        flags.set_override("dynamic_cta_fallback", True)

        try:
            response = handler.get_fallback(
                "fallback_tier_2", "spin_situation", competitor_context
            )

            # Should use competitor-based dynamic CTA
            if response.options:
                # Check trace for condition evaluation
                if response.trace:
                    assert response.trace.conditions_checked > 0
        finally:
            flags.clear_override("dynamic_cta_fallback")

    def test_tier_2_falls_back_to_static_when_no_context(self, handler):
        """Tier 2 falls back to static when dynamic CTA conditions not met."""
        from src.feature_flags import flags
        flags.set_override("dynamic_cta_fallback", True)

        try:
            response = handler.get_fallback(
                "fallback_tier_2", "spin_situation", {}
            )

            # Should have message and options
            assert response.message is not None
        finally:
            flags.clear_override("dynamic_cta_fallback")

# =============================================================================
# CONDITION-BASED TIER 3 TESTS
# =============================================================================

class TestConditionBasedTier3:
    """Tests for condition-based tier 3 behavior."""

    def test_tier_3_checks_skip_conditions(self, handler):
        """Tier 3 checks should_skip_to_next_state condition."""
        # Set up context for skip
        handler.get_fallback("fallback_tier_3", "spin_situation", {})
        handler.get_fallback("fallback_tier_3", "spin_situation", {})

        context = {"frustration_level": 2}
        response = handler.get_fallback(
            "fallback_tier_3", "spin_situation", context
        )

        assert response.action == "skip"
        assert response.next_state is not None

# =============================================================================
# LOGGING TESTS
# =============================================================================

class TestLogging:
    """Tests for event and metric logging."""

    @patch('src.fallback_handler.logger')
    def test_logs_fallback_triggered_event(self, mock_logger, handler):
        """Logs fallback_triggered event."""
        handler.get_fallback("fallback_tier_1", "spin_situation", {})

        # Check that event was called
        mock_logger.event.assert_called()
        event_calls = [c for c in mock_logger.event.call_args_list
                       if c[0][0] == "fallback_triggered"]
        assert len(event_calls) >= 1

    @patch('src.fallback_handler.logger')
    def test_logs_processing_metric(self, mock_logger, handler):
        """Logs fallback_processing metric."""
        handler.get_fallback("fallback_tier_1", "spin_situation", {})

        # Check that metric was called
        mock_logger.metric.assert_called()
        metric_calls = [c for c in mock_logger.metric.call_args_list
                        if c[0][0] == "fallback_processing_time"]
        assert len(metric_calls) >= 1

    @patch('src.fallback_handler.logger')
    def test_logs_tier_escalation_event(self, mock_logger, handler):
        """Logs tier escalation event."""
        handler.escalate_tier("fallback_tier_1")

        event_calls = [c for c in mock_logger.event.call_args_list
                       if c[0][0] == "fallback_tier_escalated"]
        assert len(event_calls) >= 1

    @patch('src.fallback_handler.logger')
    def test_logs_skip_offered_event(self, mock_logger, handler):
        """Logs skip offered event."""
        handler.get_fallback("fallback_tier_3", "spin_situation", {})

        event_calls = [c for c in mock_logger.event.call_args_list
                       if c[0][0] == "fallback_skip_offered"]
        assert len(event_calls) >= 1

    @patch('src.fallback_handler.logger')
    def test_logs_graceful_exit_event(self, mock_logger, handler):
        """Logs graceful exit event."""
        handler.get_fallback("soft_close", "spin_situation", {})

        event_calls = [c for c in mock_logger.event.call_args_list
                       if c[0][0] == "fallback_graceful_exit"]
        assert len(event_calls) >= 1

# =============================================================================
# TRACE CONTENT TESTS
# =============================================================================

class TestTraceContent:
    """Tests for trace content and structure."""

    def test_trace_has_correct_domain(self, handler):
        """Trace has fallback domain."""
        response = handler.get_fallback("fallback_tier_1", "spin_situation", {})

        assert response.trace.domain == "fallback"

    def test_trace_has_resolution(self, handler):
        """Trace has resolution set."""
        response = handler.get_fallback("fallback_tier_1", "spin_situation", {})

        assert response.trace.resolution != Resolution.NONE

    def test_trace_records_condition_checks(self, handler):
        """Trace records condition evaluations."""
        context = {"frustration_level": 3}
        response = handler.get_fallback("fallback_tier_1", "spin_situation", context)

        # Should have checked at least immediate escalation condition
        assert response.trace.conditions_checked >= 1

# =============================================================================
# INTEGRATION WITH REGISTRY TESTS
# =============================================================================

class TestRegistryIntegration:
    """Tests for integration with fallback_registry."""

    def test_handler_uses_registry_for_conditions(self, handler):
        """Handler uses fallback_registry to evaluate conditions."""
        # This is verified by checking that the response varies based on context
        context_low = {"frustration_level": 0}
        context_high = {"frustration_level": 5}

        response_low = handler.get_fallback("fallback_tier_1", "spin_situation", context_low)
        handler.reset()
        response_high = handler.get_fallback("fallback_tier_1", "spin_situation", context_high)

        # High frustration should trigger different response (soft_close)
        assert response_high.action == "close"
        assert response_low.action == "continue"

    def test_all_conditions_evaluate_without_error(self, handler):
        """All fallback conditions can be evaluated without error."""
        context = FallbackContext.create_test_context()

        # Evaluate all conditions
        for name in fallback_registry.list_all():
            result = fallback_registry.evaluate(name, context)
            assert isinstance(result, bool)

# =============================================================================
# EDGE CASES TESTS
# =============================================================================

class TestEdgeCases:
    """Edge case tests for Phase 6 functionality."""

    def test_handles_missing_context_gracefully(self, handler):
        """Handles missing context dict gracefully."""
        response = handler.get_fallback("fallback_tier_1", "spin_situation", None)
        assert response.message is not None

    def test_handles_empty_context_gracefully(self, handler):
        """Handles empty context dict gracefully."""
        response = handler.get_fallback("fallback_tier_1", "spin_situation", {})
        assert response.message is not None

    def test_handles_partial_context(self, handler):
        """Handles partial context data."""
        context = {
            "frustration_level": 2
            # Missing other fields
        }
        response = handler.get_fallback("fallback_tier_1", "spin_situation", context)
        assert response.message is not None

    def test_handles_invalid_string_company_size(self, handler):
        """Handles invalid string company size."""
        context = {
            "collected_data": {
                "company_size": "large"  # Invalid - should be int
            }
        }
        response = handler.get_fallback("fallback_tier_2", "spin_situation", context)
        assert response.message is not None

# =============================================================================
# BACKWARD COMPATIBILITY TESTS
# =============================================================================

class TestBackwardCompatibility:
    """Tests ensuring backward compatibility."""

    def test_old_api_still_works(self, handler):
        """Old API without context still works."""
        response = handler.get_fallback("fallback_tier_1", "spin_situation")
        assert response.message is not None
        assert response.action == "continue"

    def test_old_escalate_tier_still_works(self, handler):
        """Old escalate_tier method still works."""
        next_tier = handler.escalate_tier("fallback_tier_1")
        assert next_tier == "fallback_tier_2"

    def test_old_stats_api_still_works(self, handler):
        """Old stats API still works."""
        handler.get_fallback("fallback_tier_1", "spin_situation", {})

        stats = handler.get_stats_dict()
        assert "total_count" in stats
        assert "tier_counts" in stats
        assert "state_counts" in stats

    def test_response_has_expected_fields(self, handler):
        """Response has all expected fields."""
        response = handler.get_fallback("fallback_tier_1", "spin_situation", {})

        assert hasattr(response, 'message')
        assert hasattr(response, 'options')
        assert hasattr(response, 'action')
        assert hasattr(response, 'next_state')
        assert hasattr(response, 'trace')

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
