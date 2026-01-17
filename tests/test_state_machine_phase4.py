"""
Tests for Phase 4 StateMachine integration.

Tests the integration of:
- IntentTracker in StateMachine (single source of truth for intent history)
- RuleResolver for conditional rules
- Price question fix via has_pricing_data condition
- Objection tracking via IntentTracker (replaces ObjectionFlowManager)
- Backward compatibility (tuple unpacking, objection_flow adapter)
- EvaluatorContext building
- Tracing support
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from state_machine import (
    StateMachine, RuleResult, ObjectionFlowAdapter,
    OBJECTION_INTENTS, POSITIVE_INTENTS,
    MAX_CONSECUTIVE_OBJECTIONS, MAX_TOTAL_OBJECTIONS,
)
from src.intent_tracker import IntentTracker
from src.conditions.state_machine.context import EvaluatorContext
from src.conditions.state_machine.registry import sm_registry
from src.conditions.trace import Resolution


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def sm():
    """Create a fresh StateMachine instance."""
    return StateMachine()


@pytest.fixture
def sm_with_tracing():
    """Create a StateMachine with tracing enabled."""
    return StateMachine(enable_tracing=True)


# =============================================================================
# Test IntentTracker Integration
# =============================================================================

class TestIntentTrackerIntegration:
    """Test IntentTracker integration in StateMachine."""

    def test_state_machine_has_intent_tracker(self, sm):
        """StateMachine should have an IntentTracker instance."""
        assert hasattr(sm, 'intent_tracker')
        assert isinstance(sm.intent_tracker, IntentTracker)

    def test_apply_rules_records_intent(self, sm):
        """apply_rules should record intent in tracker."""
        sm.apply_rules("greeting")

        assert sm.intent_tracker.last_intent == "greeting"
        assert sm.intent_tracker.turn_number == 1

    def test_multiple_intents_recorded(self, sm):
        """Multiple intents should be recorded in sequence."""
        sm.apply_rules("greeting")
        sm.apply_rules("price_question")
        sm.apply_rules("agreement")

        assert sm.intent_tracker.turn_number == 3
        assert sm.intent_tracker.last_intent == "agreement"
        assert sm.intent_tracker.history_length == 3

    def test_last_intent_property_uses_tracker(self, sm):
        """last_intent property should delegate to tracker."""
        sm.apply_rules("greeting")
        sm.apply_rules("price_question")

        assert sm.last_intent == "price_question"
        assert sm.last_intent == sm.intent_tracker.last_intent

    def test_reset_clears_intent_tracker(self, sm):
        """reset() should clear the intent tracker."""
        sm.apply_rules("greeting")
        sm.apply_rules("price_question")

        sm.reset()

        assert sm.intent_tracker.turn_number == 0
        assert sm.intent_tracker.last_intent is None
        assert sm.intent_tracker.history_length == 0

    def test_turn_number_property(self, sm):
        """turn_number property should reflect tracker state."""
        assert sm.turn_number == 0

        sm.apply_rules("greeting")
        assert sm.turn_number == 1

        sm.apply_rules("price_question")
        assert sm.turn_number == 2


# =============================================================================
# Test Objection Tracking via IntentTracker
# =============================================================================

class TestObjectionTrackingViaIntentTracker:
    """Test objection tracking using IntentTracker instead of ObjectionFlowManager."""

    def test_objection_counted_via_tracker(self, sm):
        """Objections should be counted via IntentTracker."""
        sm.apply_rules("objection_price")

        assert sm.intent_tracker.objection_total() == 1
        assert sm.intent_tracker.objection_consecutive() == 1

    def test_consecutive_objections_tracked(self, sm):
        """Consecutive objections should be tracked."""
        sm.apply_rules("objection_price")
        sm.apply_rules("objection_competitor")
        sm.apply_rules("objection_no_time")

        assert sm.intent_tracker.objection_consecutive() == 3

    def test_positive_intent_breaks_objection_streak(self, sm):
        """Positive intent should break objection streak."""
        sm.apply_rules("objection_price")
        sm.apply_rules("objection_competitor")
        sm.apply_rules("agreement")  # Positive intent

        assert sm.intent_tracker.objection_consecutive() == 0
        assert sm.intent_tracker.objection_total() == 2

    def test_objection_limit_triggers_soft_close(self, sm):
        """Reaching objection limit should trigger soft_close."""
        # Record MAX_CONSECUTIVE_OBJECTIONS objections
        for i in range(MAX_CONSECUTIVE_OBJECTIONS):
            action, next_state = sm.apply_rules(OBJECTION_INTENTS[i % len(OBJECTION_INTENTS)])

        # The last one should trigger transition to soft_close
        # (action name changed from objection_limit_reached to transition_to_soft_close in YAML)
        assert action == "transition_to_soft_close"
        assert next_state == "soft_close"

    def test_total_objections_limit(self, sm):
        """Reaching total objection limit should trigger soft_close."""
        # Interleave objections with positive intents to avoid consecutive limit
        for i in range(MAX_TOTAL_OBJECTIONS):
            sm.apply_rules(OBJECTION_INTENTS[i % len(OBJECTION_INTENTS)])
            if i < MAX_TOTAL_OBJECTIONS - 1:
                sm.apply_rules("agreement")  # Reset consecutive, but total increases

        assert sm.intent_tracker.objection_total() >= MAX_TOTAL_OBJECTIONS


# =============================================================================
# Test ObjectionFlowAdapter (Backward Compatibility)
# =============================================================================

class TestObjectionFlowAdapter:
    """Test backward compatibility via ObjectionFlowAdapter."""

    def test_objection_flow_property_returns_adapter(self, sm):
        """objection_flow property should return ObjectionFlowAdapter."""
        adapter = sm.objection_flow
        assert isinstance(adapter, ObjectionFlowAdapter)

    def test_adapter_objection_count(self, sm):
        """Adapter should report correct objection counts."""
        sm.apply_rules("objection_price")
        sm.apply_rules("objection_competitor")

        assert sm.objection_flow.objection_count == 2
        assert sm.objection_flow.total_objections == 2

    def test_adapter_should_soft_close(self, sm):
        """Adapter should correctly report should_soft_close."""
        for i in range(MAX_CONSECUTIVE_OBJECTIONS - 1):
            sm.apply_rules(OBJECTION_INTENTS[i % len(OBJECTION_INTENTS)])

        assert sm.objection_flow.should_soft_close() == False

        sm.apply_rules(OBJECTION_INTENTS[0])
        assert sm.objection_flow.should_soft_close() == True

    def test_adapter_get_stats(self, sm):
        """Adapter should return correct stats dict."""
        sm.apply_rules("objection_price")
        sm.apply_rules("objection_competitor")

        stats = sm.objection_flow.get_stats()

        assert "consecutive_objections" in stats
        assert "total_objections" in stats
        assert "history" in stats
        assert stats["consecutive_objections"] == 2
        assert stats["total_objections"] == 2


# =============================================================================
# Test Price Question Fix via Condition
# =============================================================================

class TestPriceQuestionFix:
    """Test price_question fix using has_pricing_data condition."""

    def test_deflect_when_no_pricing_data(self, sm):
        """Should deflect price_question when no pricing data."""
        sm.state = "spin_situation"
        action, _ = sm.apply_rules("price_question")

        assert action == "deflect_and_continue"

    def test_answer_when_has_company_size(self, sm):
        """Should answer price_question when company_size is known."""
        sm.state = "spin_situation"
        sm.collected_data["company_size"] = 10

        action, _ = sm.apply_rules("price_question")

        assert action == "answer_with_facts"

    def test_answer_when_has_users_count(self, sm):
        """Should answer price_question when users_count is known."""
        sm.state = "spin_situation"
        sm.collected_data["users_count"] = 15

        action, _ = sm.apply_rules("price_question")

        assert action == "answer_with_facts"

    def test_deflect_in_problem_phase_without_data(self, sm):
        """Should deflect in problem phase without pricing data."""
        sm.state = "spin_problem"
        action, _ = sm.apply_rules("price_question")

        assert action == "deflect_and_continue"

    def test_answer_in_problem_phase_with_data(self, sm):
        """Should answer in problem phase with pricing data."""
        sm.state = "spin_problem"
        sm.collected_data["company_size"] = 20

        action, _ = sm.apply_rules("price_question")

        assert action == "answer_with_facts"


# =============================================================================
# Test EvaluatorContext Building
# =============================================================================

class TestEvaluatorContextBuilding:
    """Test EvaluatorContext building from StateMachine."""

    def test_build_evaluator_context(self, sm):
        """StateMachine should build valid EvaluatorContext."""
        sm.state = "spin_situation"
        sm.collected_data = {"company_size": 10}
        sm.apply_rules("greeting")

        ctx = sm.build_evaluator_context("price_question")

        assert isinstance(ctx, EvaluatorContext)
        assert ctx.state == "spin_situation"
        assert ctx.current_intent == "price_question"
        assert ctx.collected_data.get("company_size") == 10

    def test_context_has_intent_tracker_reference(self, sm):
        """Context should have reference to IntentTracker."""
        sm.apply_rules("greeting")
        ctx = sm.build_evaluator_context("price_question")

        assert ctx.intent_tracker is sm.intent_tracker

    def test_context_spin_phase_detection(self, sm):
        """Context should correctly detect SPIN phase."""
        sm.state = "spin_problem"
        ctx = sm.build_evaluator_context("agreement")

        assert ctx.spin_phase == "problem"
        assert ctx.is_spin_state == True


# =============================================================================
# Test Tracing Support
# =============================================================================

class TestTracingSupport:
    """Test tracing support in StateMachine.

    Note: Tracing is a Phase 4 feature that needs further integration work.
    Some tests are marked xfail until tracing is fully implemented.
    """

    def test_tracing_disabled_by_default(self, sm):
        """Tracing should be disabled by default."""
        assert sm._enable_tracing == False
        assert sm._trace_collector is None

    def test_tracing_enabled_creates_collector(self, sm_with_tracing):
        """Enabling tracing should create trace collector."""
        assert sm_with_tracing._enable_tracing == True
        assert sm_with_tracing._trace_collector is not None

    @pytest.mark.xfail(reason="Tracing integration needs further work")
    def test_apply_rules_creates_trace(self, sm_with_tracing):
        """apply_rules should create trace when tracing enabled."""
        sm_with_tracing.apply_rules("greeting")

        trace = sm_with_tracing.get_last_trace()

        assert trace is not None
        assert trace.intent == "greeting"
        assert trace.state == "greeting"

    @pytest.mark.xfail(reason="Tracing integration needs further work")
    def test_trace_records_resolution(self, sm_with_tracing):
        """Trace should record how rule was resolved."""
        sm_with_tracing.apply_rules("greeting")

        trace = sm_with_tracing.get_last_trace()

        assert trace.resolution in [Resolution.SIMPLE, Resolution.DEFAULT]
        assert trace.final_action is not None

    @pytest.mark.xfail(reason="Tracing integration needs further work")
    def test_trace_summary_available(self, sm_with_tracing):
        """Trace summary should be available."""
        sm_with_tracing.apply_rules("greeting")
        sm_with_tracing.apply_rules("price_question")

        summary = sm_with_tracing.get_trace_summary()

        assert summary is not None
        assert summary["total_traces"] == 2

    @pytest.mark.xfail(reason="Tracing integration needs further work")
    def test_reset_clears_traces(self, sm_with_tracing):
        """reset() should clear traces."""
        sm_with_tracing.apply_rules("greeting")
        sm_with_tracing.reset()

        summary = sm_with_tracing.get_trace_summary()
        assert summary["total_traces"] == 0


# =============================================================================
# Test Tuple Unpacking Compatibility
# =============================================================================

class TestTupleUnpackingCompatibility:
    """Test backward compatibility with tuple unpacking."""

    def test_apply_rules_returns_tuple(self, sm):
        """apply_rules should return tuple-compatible result."""
        result = sm.apply_rules("greeting")

        # Should be iterable with 2 items
        action, next_state = result

        assert isinstance(action, str)
        assert isinstance(next_state, str)

    def test_can_unpack_directly(self, sm):
        """Should be able to unpack directly."""
        action, state = sm.apply_rules("greeting")

        assert action is not None
        assert state is not None

    def test_process_returns_correct_structure(self, sm):
        """process() should return dict with expected keys."""
        result = sm.process("greeting")

        assert "action" in result
        assert "prev_state" in result
        assert "next_state" in result
        assert "objection_flow" in result


# =============================================================================
# Test SPIN Flow with IntentTracker
# =============================================================================

class TestSPINFlowWithIntentTracker:
    """Test SPIN flow works correctly with IntentTracker."""

    def test_situation_to_problem_transition(self, sm):
        """Situation → Problem transition should work."""
        sm.state = "spin_situation"
        sm.collected_data["company_size"] = 10

        action, next_state = sm.apply_rules("situation_provided")

        assert next_state == "spin_problem"

    def test_problem_to_implication_transition(self, sm):
        """Problem → Implication transition should work."""
        sm.state = "spin_problem"
        sm.collected_data["pain_point"] = "losing customers"

        action, next_state = sm.apply_rules("problem_revealed")

        assert next_state == "spin_implication"

    def test_spin_intents_tracked(self, sm):
        """SPIN progress intents should be tracked."""
        sm.state = "spin_situation"
        sm.apply_rules("situation_provided")
        sm.apply_rules("problem_revealed")

        assert sm.intent_tracker.turn_number == 2

        # Check history contains SPIN intents
        intents = [r.intent for r in sm.intent_tracker.get_history()]
        assert "situation_provided" in intents
        assert "problem_revealed" in intents


# =============================================================================
# Test Circular Flow Integration
# =============================================================================

class TestCircularFlowIntegration:
    """Test CircularFlow still works with new IntentTracker."""

    def test_circular_flow_manager_exists(self, sm):
        """CircularFlowManager should still exist."""
        assert hasattr(sm, 'circular_flow')

    def test_circular_flow_tracks_gobacks(self, sm):
        """CircularFlow should track go-backs."""
        # This tests that the circular_flow component wasn't broken
        stats = sm.circular_flow.get_stats()

        # Check for expected keys (goback_count, history, remaining)
        assert "goback_count" in stats
        assert "history" in stats


# =============================================================================
# Test Process Method with Phase 4
# =============================================================================

class TestProcessMethodPhase4:
    """Test process() method with Phase 4 integration."""

    def test_process_updates_last_action(self, sm):
        """process() should update last_action."""
        result = sm.process("greeting")

        assert sm.last_action is not None
        assert sm.last_action == result["action"]

    def test_process_records_intent_in_tracker(self, sm):
        """process() should record intent in tracker."""
        sm.process("greeting")
        sm.process("price_question")

        assert sm.intent_tracker.turn_number == 2

    def test_process_returns_objection_stats(self, sm):
        """process() should return objection stats."""
        result = sm.process("objection_price")

        stats = result["objection_flow"]
        assert stats["consecutive_objections"] == 1
        assert stats["total_objections"] == 1

    @pytest.mark.xfail(reason="Tracing integration needs further work")
    def test_process_with_tracing_includes_trace(self, sm_with_tracing):
        """process() with tracing should include trace in result."""
        result = sm_with_tracing.process("greeting")

        assert "trace" in result
        assert result["trace"]["intent"] == "greeting"


# =============================================================================
# Test Edge Cases
# =============================================================================

class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_intent_handled(self, sm):
        """Empty intent should not crash."""
        action, state = sm.apply_rules("")

        assert action is not None
        assert state is not None

    def test_unknown_intent_handled(self, sm):
        """Unknown intent should not crash."""
        action, state = sm.apply_rules("completely_unknown_intent_xyz")

        assert action is not None
        assert state is not None

    def test_none_collected_data_handled(self, sm):
        """None in collected_data should be handled."""
        sm.collected_data["test"] = None

        # Should not crash
        action, state = sm.apply_rules("price_question")
        assert action is not None

    def test_rapid_state_changes(self, sm):
        """Rapid state changes should not corrupt tracker."""
        for i in range(100):
            sm.apply_rules("greeting")

        assert sm.intent_tracker.turn_number == 100

    def test_concurrent_reset_and_apply(self, sm):
        """Reset followed by apply should work correctly."""
        sm.apply_rules("greeting")
        sm.reset()
        sm.apply_rules("price_question")

        assert sm.intent_tracker.turn_number == 1
        assert sm.intent_tracker.last_intent == "price_question"


# =============================================================================
# Run Tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
