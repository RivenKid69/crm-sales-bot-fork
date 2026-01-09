"""
Integration Tests for Conditional Rules System - Phase 3.

This test suite provides integration coverage for:
- IntentTracker + EvaluatorContext integration
- RuleResolver + StateMachine registry integration
- End-to-end scenarios from ARCHITECTURE_UNIFIED_PLAN.md
- Price question handling with conditional rules
- Objection limit scenarios
- Demo request transition scenarios

Run with: pytest tests/test_conditions_phase3.py -v
"""

import pytest
from typing import Dict, Any

from src.intent_tracker import IntentTracker, INTENT_CATEGORIES
from src.conditions.state_machine.context import (
    EvaluatorContext,
    SimpleIntentTracker,
    SPIN_PHASES,
    SPIN_STATES
)
from src.conditions.state_machine.registry import sm_registry
from src.conditions.state_machine.conditions import (
    has_pricing_data,
    has_contact_info,
    has_company_size,
    price_repeated_3x,
    objection_limit_reached,
    is_spin_state,
    in_spin_phase
)
from src.conditions.trace import EvaluationTrace, Resolution, TraceCollector
from src.rules.resolver import RuleResolver, RuleResult, create_resolver


# =============================================================================
# TEST FIXTURES
# =============================================================================

@pytest.fixture
def intent_tracker():
    """Create a fresh IntentTracker."""
    return IntentTracker()


@pytest.fixture
def resolver():
    """Create RuleResolver with StateMachine registry."""
    return create_resolver(sm_registry)


@pytest.fixture
def trace_collector():
    """Create a TraceCollector for test tracing."""
    return TraceCollector()


# =============================================================================
# INTENT TRACKER + CONTEXT INTEGRATION
# =============================================================================

class TestIntentTrackerContextIntegration:
    """Tests for IntentTracker + EvaluatorContext integration."""

    def test_context_uses_intent_tracker(self):
        """Test EvaluatorContext can use IntentTracker."""
        tracker = IntentTracker()
        tracker.record("price_question", "spin_situation")
        tracker.record("price_question", "spin_situation")

        ctx = EvaluatorContext(
            collected_data={"company_size": 50},
            state="spin_situation",
            turn_number=2,
            current_intent="price_question",
            intent_tracker=tracker
        )

        # Context should access tracker methods
        assert ctx.get_intent_streak("price_question") == 2
        assert ctx.get_intent_total("price_question") == 2

    def test_context_category_access(self):
        """Test EvaluatorContext can access category counts."""
        tracker = IntentTracker()
        tracker.record("objection_price", "handle_objection")
        tracker.record("objection_competitor", "handle_objection")

        ctx = EvaluatorContext(
            collected_data={},
            state="handle_objection",
            turn_number=2,
            current_intent="objection_competitor",
            intent_tracker=tracker
        )

        assert ctx.get_category_streak("objection") == 2
        assert ctx.get_category_total("objection") == 2

    def test_context_from_state_machine_stub(self):
        """Test EvaluatorContext.from_state_machine with stub object."""
        # Create a stub that mimics StateMachine
        class StateMachineStub:
            state = "spin_situation"
            collected_data = {"company_size": 50}
            spin_phase = "situation"
            turn_number = 5
            last_intent = "price_question"
            intent_tracker = None

        ctx = EvaluatorContext.from_state_machine(
            StateMachineStub(),
            current_intent="question_features"
        )

        assert ctx.state == "spin_situation"
        assert ctx.collected_data["company_size"] == 50
        assert ctx.spin_phase == "situation"
        assert ctx.current_intent == "question_features"
        assert ctx.prev_intent == "price_question"

    def test_simple_intent_tracker_compatibility(self):
        """Test SimpleIntentTracker works with EvaluatorContext."""
        tracker = SimpleIntentTracker()
        tracker.record("price_question")
        tracker.record("price_question")
        tracker.record("price_question")

        ctx = EvaluatorContext.create_test_context(
            collected_data={},
            state="spin_situation",
            intent_tracker=tracker
        )

        assert ctx.get_intent_streak("price_question") == 3


# =============================================================================
# RESOLVER + REGISTRY INTEGRATION
# =============================================================================

class TestResolverRegistryIntegration:
    """Tests for RuleResolver + sm_registry integration."""

    def test_resolver_uses_sm_registry(self, resolver):
        """Test resolver can evaluate conditions from sm_registry."""
        ctx = EvaluatorContext.create_test_context(
            collected_data={"company_size": 50},
            state="spin_situation"
        )

        state_rules = {
            "price_question": {"when": "has_pricing_data", "then": "answer_with_facts"}
        }

        action = resolver.resolve_action(
            intent="price_question",
            state_rules=state_rules,
            global_rules={},
            ctx=ctx
        )

        assert action == "answer_with_facts"

    def test_resolver_with_registered_conditions(self, resolver):
        """Test resolver works with all registered sm_registry conditions."""
        # Verify conditions are registered
        assert sm_registry.has("has_pricing_data")
        assert sm_registry.has("has_contact_info")
        assert sm_registry.has("price_repeated_3x")
        assert sm_registry.has("objection_limit_reached")

    def test_resolver_tracing_with_registry(self, resolver, trace_collector):
        """Test tracing works with registry conditions."""
        ctx = EvaluatorContext.create_test_context(
            collected_data={"company_size": 50},
            state="spin_situation"
        )

        trace = trace_collector.create_trace(
            rule_name="price_question",
            intent="price_question",
            state="spin_situation",
            domain="state_machine"
        )

        state_rules = {
            "price_question": [
                {"when": "has_pricing_data", "then": "answer_with_facts"},
                "deflect"
            ]
        }

        action = resolver.resolve_action(
            intent="price_question",
            state_rules=state_rules,
            global_rules={},
            ctx=ctx,
            trace=trace
        )

        assert trace.resolution == Resolution.CONDITION_MATCHED
        assert trace.matched_condition == "has_pricing_data"
        assert trace.conditions_checked >= 1


# =============================================================================
# PRICE QUESTION SCENARIOS (Plan Section 5.1-5.2)
# =============================================================================

class TestPriceQuestionScenarios:
    """Tests for price question scenarios from plan."""

    def test_price_question_with_data_answers(self, resolver):
        """Test: price_question + has_pricing_data = answer_with_facts."""
        ctx = EvaluatorContext.create_test_context(
            collected_data={"company_size": 50},
            state="spin_situation"
        )

        rules = {
            "price_question": [
                {"when": "has_pricing_data", "then": "answer_with_facts"},
                {"when": "price_repeated_3x", "then": "answer_with_price_range"},
                "deflect_and_continue"
            ]
        }

        action = resolver.resolve_action("price_question", rules, {}, ctx)
        assert action == "answer_with_facts"

    def test_price_question_without_data_deflects(self, resolver):
        """Test: price_question + no_data = deflect_and_continue."""
        ctx = EvaluatorContext.create_test_context(
            collected_data={},
            state="spin_situation"
        )

        rules = {
            "price_question": [
                {"when": "has_pricing_data", "then": "answer_with_facts"},
                {"when": "price_repeated_3x", "then": "answer_with_price_range"},
                "deflect_and_continue"
            ]
        }

        action = resolver.resolve_action("price_question", rules, {}, ctx)
        assert action == "deflect_and_continue"

    def test_price_question_repeated_3x_escalates(self, resolver):
        """Test: price_question repeated 3x = answer_with_price_range."""
        tracker = SimpleIntentTracker()
        tracker.set_intent_streak("price_question", 3)

        ctx = EvaluatorContext.create_test_context(
            collected_data={},
            state="spin_situation",
            intent_tracker=tracker
        )

        rules = {
            "price_question": [
                {"when": "has_pricing_data", "then": "answer_with_facts"},
                {"when": "price_repeated_3x", "then": "answer_with_price_range"},
                "deflect_and_continue"
            ]
        }

        action = resolver.resolve_action("price_question", rules, {}, ctx)
        assert action == "answer_with_price_range"

    def test_price_question_data_takes_priority_over_repetition(self, resolver):
        """Test: has_pricing_data takes priority over price_repeated_3x."""
        tracker = SimpleIntentTracker()
        tracker.set_intent_streak("price_question", 5)

        ctx = EvaluatorContext.create_test_context(
            collected_data={"company_size": 50},
            state="spin_situation",
            intent_tracker=tracker
        )

        rules = {
            "price_question": [
                {"when": "has_pricing_data", "then": "answer_with_facts"},
                {"when": "price_repeated_3x", "then": "answer_with_price_range"},
                "deflect_and_continue"
            ]
        }

        action = resolver.resolve_action("price_question", rules, {}, ctx)
        # First condition wins due to order
        assert action == "answer_with_facts"


# =============================================================================
# OBJECTION LIMIT SCENARIOS (Plan Section 5.3)
# =============================================================================

class TestObjectionLimitScenarios:
    """Tests for objection limit scenarios from plan."""

    def test_objection_3_consecutive_triggers_soft_close(self, resolver):
        """Test: 3 consecutive objections triggers transition to soft_close."""
        tracker = SimpleIntentTracker()
        tracker.set_category_streak("objection", 3)

        ctx = EvaluatorContext.create_test_context(
            collected_data={},
            state="handle_objection",
            intent_tracker=tracker
        )

        transitions = {
            "objection_price": [
                {"when": "objection_limit_reached", "then": "soft_close"},
                None
            ]
        }

        result = resolver.resolve_transition(
            "objection_price", transitions, ctx
        )
        assert result == "soft_close"

    def test_objection_5_total_triggers_soft_close(self, resolver):
        """Test: 5 total objections triggers transition to soft_close."""
        tracker = SimpleIntentTracker()
        tracker.set_category_total("objection", 5)
        tracker.set_category_streak("objection", 1)

        ctx = EvaluatorContext.create_test_context(
            collected_data={},
            state="handle_objection",
            intent_tracker=tracker
        )

        transitions = {
            "objection_price": [
                {"when": "objection_limit_reached", "then": "soft_close"},
                None
            ]
        }

        result = resolver.resolve_transition(
            "objection_price", transitions, ctx
        )
        assert result == "soft_close"

    def test_objection_below_limit_stays(self, resolver):
        """Test: objections below limit stays in state."""
        tracker = SimpleIntentTracker()
        tracker.set_category_streak("objection", 2)
        tracker.set_category_total("objection", 3)

        ctx = EvaluatorContext.create_test_context(
            collected_data={},
            state="handle_objection",
            intent_tracker=tracker
        )

        transitions = {
            "objection_price": [
                {"when": "objection_limit_reached", "then": "soft_close"},
                None
            ]
        }

        result = resolver.resolve_transition(
            "objection_price", transitions, ctx
        )
        assert result is None  # Stay in handle_objection


# =============================================================================
# DEMO REQUEST TRANSITION (Plan Section 5.5)
# =============================================================================

class TestDemoRequestTransition:
    """Tests for demo_request transition scenarios from plan."""

    def test_demo_request_with_contact_to_success(self, resolver):
        """Test: demo_request + has_contact_info = success."""
        ctx = EvaluatorContext.create_test_context(
            collected_data={"email": "test@example.com"},
            state="close"
        )

        transitions = {
            "demo_request": [
                {"when": "has_contact_info", "then": "success"},
                None
            ]
        }

        result = resolver.resolve_transition(
            "demo_request", transitions, ctx
        )
        assert result == "success"

    def test_demo_request_without_contact_stays(self, resolver):
        """Test: demo_request + no_contact = stay in close."""
        ctx = EvaluatorContext.create_test_context(
            collected_data={},
            state="close"
        )

        transitions = {
            "demo_request": [
                {"when": "has_contact_info", "then": "success"},
                None
            ]
        }

        result = resolver.resolve_transition(
            "demo_request", transitions, ctx
        )
        assert result is None


# =============================================================================
# TECHNICAL QUESTION ESCALATION (Plan Section 5.4)
# =============================================================================

class TestTechnicalQuestionEscalation:
    """Tests for technical question escalation scenarios."""

    def test_technical_question_repeated_2x_offers_docs(self, resolver):
        """Test: question_technical repeated 2x = offer_documentation_link."""
        tracker = SimpleIntentTracker()
        tracker.set_intent_streak("question_technical", 2)

        ctx = EvaluatorContext.create_test_context(
            collected_data={},
            state="spin_situation",
            intent_tracker=tracker
        )

        rules = {
            "question_technical": [
                {"when": "technical_question_repeated_2x", "then": "offer_documentation_link"},
                "answer_technical"
            ]
        }

        action = resolver.resolve_action("question_technical", rules, {}, ctx)
        assert action == "offer_documentation_link"

    def test_technical_question_first_time_answers(self, resolver):
        """Test: question_technical first time = answer_technical."""
        tracker = SimpleIntentTracker()
        tracker.set_intent_streak("question_technical", 1)

        ctx = EvaluatorContext.create_test_context(
            collected_data={},
            state="spin_situation",
            intent_tracker=tracker
        )

        rules = {
            "question_technical": [
                {"when": "technical_question_repeated_2x", "then": "offer_documentation_link"},
                "answer_technical"
            ]
        }

        action = resolver.resolve_action("question_technical", rules, {}, ctx)
        assert action == "answer_technical"


# =============================================================================
# PRICE OBJECTION WITH ROI (Plan Section 5.3)
# =============================================================================

class TestPriceObjectionWithROI:
    """Tests for smart price objection handling."""

    def test_objection_price_with_pain_and_size_uses_roi(self, resolver):
        """Test: objection_price + pain + size = handle_price_with_roi."""
        ctx = EvaluatorContext.create_test_context(
            collected_data={
                "pain_point": "losing deals",
                "company_size": 50
            },
            state="handle_objection"
        )

        rules = {
            "objection_price": [
                {"when": "has_pain_and_company_size", "then": "handle_price_with_roi"},
                {"when": "has_company_size", "then": "handle_price_with_comparison"},
                "handle_price_objection_generic"
            ]
        }

        action = resolver.resolve_action("objection_price", rules, {}, ctx)
        assert action == "handle_price_with_roi"

    def test_objection_price_with_size_only_uses_comparison(self, resolver):
        """Test: objection_price + size (no pain) = handle_price_with_comparison."""
        ctx = EvaluatorContext.create_test_context(
            collected_data={"company_size": 50},
            state="handle_objection"
        )

        rules = {
            "objection_price": [
                {"when": "has_pain_and_company_size", "then": "handle_price_with_roi"},
                {"when": "has_company_size", "then": "handle_price_with_comparison"},
                "handle_price_objection_generic"
            ]
        }

        action = resolver.resolve_action("objection_price", rules, {}, ctx)
        assert action == "handle_price_with_comparison"

    def test_objection_price_no_data_uses_generic(self, resolver):
        """Test: objection_price + no data = generic handler."""
        ctx = EvaluatorContext.create_test_context(
            collected_data={},
            state="handle_objection"
        )

        rules = {
            "objection_price": [
                {"when": "has_pain_and_company_size", "then": "handle_price_with_roi"},
                {"when": "has_company_size", "then": "handle_price_with_comparison"},
                "handle_price_objection_generic"
            ]
        }

        action = resolver.resolve_action("objection_price", rules, {}, ctx)
        assert action == "handle_price_objection_generic"


# =============================================================================
# FULL CONVERSATION FLOW TEST
# =============================================================================

class TestFullConversationFlow:
    """End-to-end tests simulating conversation flows."""

    def test_happy_path_flow(self, resolver):
        """Test happy path: greeting -> SPIN -> presentation -> close -> success."""
        tracker = IntentTracker()

        # Turn 1: Greeting
        tracker.record("greeting", "greeting")
        ctx1 = EvaluatorContext.create_test_context(
            collected_data={},
            state="greeting",
            current_intent="greeting",
            intent_tracker=tracker
        )

        # Turn 2: Price question (deflect - no data)
        tracker.record("price_question", "spin_situation")
        ctx2 = EvaluatorContext.create_test_context(
            collected_data={},
            state="spin_situation",
            current_intent="price_question",
            intent_tracker=tracker
        )

        rules = {
            "price_question": [
                {"when": "has_pricing_data", "then": "answer_with_facts"},
                "deflect_and_continue"
            ]
        }
        action = resolver.resolve_action("price_question", rules, {}, ctx2)
        assert action == "deflect_and_continue"

        # Turn 3: Info provided (now have data)
        tracker.record("info_provided", "spin_problem")
        ctx3 = EvaluatorContext.create_test_context(
            collected_data={"company_size": 50},
            state="spin_problem",
            current_intent="info_provided",
            intent_tracker=tracker
        )

        # Turn 4: Price question again (now answer)
        tracker.record("price_question", "spin_problem")
        ctx4 = EvaluatorContext.create_test_context(
            collected_data={"company_size": 50, "pain_point": "losing deals"},
            state="spin_problem",
            current_intent="price_question",
            intent_tracker=tracker
        )
        action = resolver.resolve_action("price_question", rules, {}, ctx4)
        assert action == "answer_with_facts"

    def test_objection_flow(self, resolver):
        """Test objection handling flow."""
        tracker = IntentTracker()

        # Simulate objections
        for _ in range(2):
            tracker.record("objection_price", "handle_objection")

        ctx = EvaluatorContext.create_test_context(
            collected_data={},
            state="handle_objection",
            current_intent="objection_price",
            intent_tracker=tracker
        )

        # Not yet at limit
        assert not objection_limit_reached(ctx)

        # Add one more objection
        tracker.record("objection_no_time", "handle_objection")
        ctx2 = EvaluatorContext.create_test_context(
            collected_data={},
            state="handle_objection",
            current_intent="objection_no_time",
            intent_tracker=tracker
        )

        # Now at limit (3 consecutive)
        assert objection_limit_reached(ctx2)


# =============================================================================
# TRACE COLLECTION TEST
# =============================================================================

class TestTraceCollection:
    """Tests for trace collection across conversations."""

    def test_collect_traces_for_simulation(self, resolver, trace_collector):
        """Test collecting traces for simulation analysis."""
        # Simulate multiple turns
        turns = [
            {"intent": "greeting", "state": "greeting", "data": {}},
            {"intent": "price_question", "state": "spin_situation", "data": {}},
            {"intent": "price_question", "state": "spin_situation", "data": {"company_size": 50}},
        ]

        rules = {
            "greeting": "greet_back",
            "price_question": [
                {"when": "has_pricing_data", "then": "answer_with_facts"},
                "deflect_and_continue"
            ]
        }

        for turn in turns:
            trace = trace_collector.create_trace(
                rule_name=turn["intent"],
                intent=turn["intent"],
                state=turn["state"],
                domain="state_machine"
            )

            ctx = EvaluatorContext.create_test_context(
                collected_data=turn["data"],
                state=turn["state"],
                current_intent=turn["intent"]
            )

            resolver.resolve_action(turn["intent"], rules, {}, ctx, trace=trace)

        # Analyze traces
        summary = trace_collector.get_summary()
        assert summary.total_traces == 3
        assert Resolution.SIMPLE.value in summary.by_resolution
        assert Resolution.CONDITION_MATCHED.value in summary.by_resolution or \
               Resolution.DEFAULT.value in summary.by_resolution


# =============================================================================
# BACKWARD COMPATIBILITY TESTS
# =============================================================================

class TestBackwardCompatibility:
    """Tests ensuring backward compatibility with existing config format."""

    def test_simple_string_rules_work(self, resolver):
        """Test simple string rules still work."""
        ctx = EvaluatorContext.create_test_context(
            collected_data={},
            state="greeting"
        )

        rules = {
            "greeting": "greet_back",
            "price_question": "deflect_and_continue"
        }

        action1 = resolver.resolve_action("greeting", rules, {}, ctx)
        action2 = resolver.resolve_action("price_question", rules, {}, ctx)

        assert action1 == "greet_back"
        assert action2 == "deflect_and_continue"

    def test_simple_string_transitions_work(self, resolver):
        """Test simple string transitions still work."""
        ctx = EvaluatorContext.create_test_context(
            collected_data={},
            state="greeting"
        )

        transitions = {
            "agreement": "spin_situation",
            "rejection": "soft_close"
        }

        result1 = resolver.resolve_transition("agreement", transitions, ctx)
        result2 = resolver.resolve_transition("rejection", transitions, ctx)

        assert result1 == "spin_situation"
        assert result2 == "soft_close"

    def test_rule_result_tuple_unpacking(self, resolver):
        """Test RuleResult supports tuple unpacking."""
        ctx = EvaluatorContext.create_test_context(
            collected_data={},
            state="greeting"
        )

        action = resolver.resolve_action(
            "greeting",
            {"greeting": "greet_back"},
            {},
            ctx
        )
        next_state = resolver.resolve_transition(
            "greeting",
            {"greeting": "spin_situation"},
            ctx
        )

        result = RuleResult(action=action, next_state=next_state)

        # Old code pattern: action, state = result
        act, st = result
        assert act == "greet_back"
        assert st == "spin_situation"
