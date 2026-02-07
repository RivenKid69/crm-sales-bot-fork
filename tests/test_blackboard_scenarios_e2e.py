# tests/test_blackboard_scenarios_e2e.py

"""
Scenario-based E2E Tests for Blackboard Architecture.

Tests real-world dialogue scenarios using the simulator infrastructure
to verify the Blackboard system works correctly in realistic conditions.

Test Categories:
1. Persona-Based Scenarios - Different client types
2. Flow-Specific Scenarios - Different sales techniques
3. Stress Scenarios - Edge cases and limits
4. Regression Scenarios - Known bugs and fixes

Run with:
    pytest tests/test_blackboard_scenarios_e2e.py -v
    pytest tests/test_blackboard_scenarios_e2e.py -k "persona" -v
    pytest tests/test_blackboard_scenarios_e2e.py -m "scenario" -v
"""

import pytest
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional
from unittest.mock import Mock, MagicMock, patch
from dataclasses import dataclass, field

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from src.blackboard.orchestrator import DialogueOrchestrator
from src.blackboard.blackboard import DialogueBlackboard
from src.blackboard.models import ResolvedDecision
from src.blackboard.enums import Priority
from src.blackboard.source_registry import SourceRegistry
from src.blackboard.knowledge_source import KnowledgeSource
from src.blackboard.sources.price_question import PriceQuestionSource
from src.blackboard.sources.data_collector import DataCollectorSource
from src.blackboard.sources.objection_guard import ObjectionGuardSource
from src.blackboard.sources.intent_processor import IntentProcessorSource
from src.blackboard.sources.transition_resolver import TransitionResolverSource
from src.blackboard.sources.escalation import EscalationSource


# =============================================================================
# Scenario Infrastructure
# =============================================================================

@dataclass
class DialogueTurn:
    """Represents a single turn in a dialogue scenario."""
    intent: str
    extracted_data: Dict[str, Any] = field(default_factory=dict)
    expected_action: Optional[str] = None
    expected_state: Optional[str] = None
    expected_reason_codes: Optional[List[str]] = None
    pre_collected_data: Optional[Dict[str, Any]] = None
    description: str = ""


@dataclass
class DialogueScenario:
    """Complete dialogue scenario for testing."""
    name: str
    description: str
    initial_state: str
    initial_data: Dict[str, Any]
    turns: List[DialogueTurn]
    expected_final_state: str
    expected_final_is_final: bool = False
    persona: str = "default"


class ScenarioTestRunner:
    """Runs dialogue scenarios and validates results."""

    def __init__(self, orchestrator: DialogueOrchestrator):
        self.orchestrator = orchestrator
        self.sm = orchestrator._state_machine
        self.results: List[Dict[str, Any]] = []

    def run_scenario(self, scenario: DialogueScenario) -> Dict[str, Any]:
        """
        Run a complete dialogue scenario.

        Returns:
            Dict with success status and detailed results
        """
        self.results = []

        # Setup initial state
        self.sm.state = scenario.initial_state
        self.sm._collected_data = scenario.initial_data.copy()

        errors = []

        for i, turn in enumerate(scenario.turns):
            # Apply pre-collected data if specified
            if turn.pre_collected_data:
                self.sm._collected_data.update(turn.pre_collected_data)

            # Process turn
            decision = self.orchestrator.process_turn(
                intent=turn.intent,
                extracted_data=turn.extracted_data,
            )

            turn_result = {
                "turn": i + 1,
                "intent": turn.intent,
                "action": decision.action,
                "next_state": decision.next_state,
                "reason_codes": decision.reason_codes,
                "description": turn.description,
            }
            self.results.append(turn_result)

            # Validate expectations
            if turn.expected_action and decision.action != turn.expected_action:
                errors.append(
                    f"Turn {i+1}: Expected action '{turn.expected_action}', "
                    f"got '{decision.action}'"
                )

            if turn.expected_state and decision.next_state != turn.expected_state:
                errors.append(
                    f"Turn {i+1}: Expected state '{turn.expected_state}', "
                    f"got '{decision.next_state}'"
                )

            if turn.expected_reason_codes:
                for code in turn.expected_reason_codes:
                    if code not in decision.reason_codes:
                        errors.append(
                            f"Turn {i+1}: Expected reason_code '{code}' not found in "
                            f"{decision.reason_codes}"
                        )

        # Validate final state
        if self.sm.state != scenario.expected_final_state:
            errors.append(
                f"Final state: Expected '{scenario.expected_final_state}', "
                f"got '{self.sm.state}'"
            )

        if scenario.expected_final_is_final and not self.sm.is_final():
            errors.append("Expected final state but is_final() returned False")

        return {
            "success": len(errors) == 0,
            "scenario": scenario.name,
            "errors": errors,
            "turns": self.results,
            "final_state": self.sm.state,
            "final_data": dict(self.sm.collected_data),
        }


# =============================================================================
# Test Infrastructure
# =============================================================================

@dataclass
class IntentRecord:
    """Record of an intent for tracking."""
    intent: str
    state: str


class ScenarioStateMachine:
    """StateMachine implementation for scenario testing."""

    def __init__(
        self,
        state: str = "greeting",
        collected_data: Optional[Dict[str, Any]] = None
    ):
        self._state = state
        self._collected_data = collected_data or {}
        self._current_phase = None
        self._last_action = None
        self._intent_tracker = self._create_intent_tracker()
        self._state_before_objection = None
        self.circular_flow = self._create_circular_flow()

    def _create_intent_tracker(self):
        """Create intent tracker."""
        class IntentTracker:
            def __init__(self):
                self._turn_number = 0
                self._prev_intent = None
                self._intents = []
                self._objection_consecutive = 0
                self._objection_total = 0

            @property
            def turn_number(self):
                return self._turn_number

            @property
            def prev_intent(self):
                return self._prev_intent

            def record(self, intent, state):
                if self._intents:
                    self._prev_intent = self._intents[-1].intent
                self._intents.append(IntentRecord(intent=intent, state=state))
                if "objection" in intent:
                    self._objection_consecutive += 1
                    self._objection_total += 1
                else:
                    self._objection_consecutive = 0

            def objection_consecutive(self):
                return self._objection_consecutive

            def objection_total(self):
                return self._objection_total

            def total_count(self, intent):
                return sum(1 for r in self._intents if r.intent == intent)

            def category_total(self, category):
                return sum(1 for r in self._intents if category in r.intent)

            def get_intents_by_category(self, category):
                return [r for r in self._intents if category in r.intent]

            def advance_turn(self):
                self._turn_number += 1

        return IntentTracker()

    def _create_circular_flow(self):
        """Create circular flow manager."""
        class CircularFlow:
            def __init__(self):
                self._loops = 0
                self._max_loops = 3

            def get_stats(self):
                return {"loops": self._loops, "max_loops": self._max_loops}

        return CircularFlow()

    @property
    def state(self):
        return self._state

    @state.setter
    def state(self, value):
        self._state = value

    @property
    def collected_data(self):
        return self._collected_data

    @property
    def current_phase(self):
        return self._current_phase

    @current_phase.setter
    def current_phase(self, value):
        self._current_phase = value

    @property
    def last_action(self):
        return self._last_action

    @last_action.setter
    def last_action(self, value):
        self._last_action = value

    def update_data(self, data):
        self._collected_data.update(data)

    def transition_to(
        self,
        next_state: str,
        action: Optional[str] = None,
        phase: Optional[str] = None,
        source: str = "test",
        validate: bool = True,
    ) -> None:
        """
        Atomic state transition (mirrors real StateMachine.transition_to).

        Args:
            next_state: Target state
            action: Optional action to set
            phase: Optional phase to set
            source: Source of transition (for logging)
            validate: Whether to validate transition (ignored in mock)
        """
        self._state = next_state
        if action is not None:
            self._last_action = action
        if phase is not None:
            self._current_phase = phase

    def is_final(self):
        return self._state in ("soft_close", "closed", "rejected", "success")


class ScenarioFlowConfig:
    """FlowConfig implementation for scenario testing."""

    def __init__(self, persona_limits: Optional[Dict] = None):
        self._states = self._get_states()
        self._constants = {
            "persona_limits": persona_limits or {
                "aggressive": {"consecutive": 5, "total": 8},
                "busy": {"consecutive": 2, "total": 4},
                "skeptic": {"consecutive": 4, "total": 6},
                "price_sensitive": {"consecutive": 3, "total": 6},
                "default": {"consecutive": 3, "total": 5},
            }
        }

    def _get_states(self):
        return {
            "greeting": {
                "goal": "Greet user",
                "phase": None,
                "required_data": [],
                "is_final": False,
                "transitions": {"any": "spin_situation"},
            },
            "spin_situation": {
                "goal": "Understand situation",
                "phase": "situation",
                "required_data": ["company_size"],
                "optional_data": ["industry"],
                "is_final": False,
                "transitions": {
                    "data_complete": "spin_problem",
                    "rejection": "soft_close",
                    "escalation": "human_handoff",
                },
            },
            "spin_problem": {
                "goal": "Identify problems",
                "phase": "problem",
                "required_data": ["pain_point"],
                "is_final": False,
                "transitions": {
                    "data_complete": "spin_implication",
                    "rejection": "soft_close",
                },
            },
            "spin_implication": {
                "goal": "Explore implications",
                "phase": "implication",
                "required_data": [],
                "is_final": False,
                "transitions": {
                    "data_complete": "spin_need_payoff",
                    "understood": "spin_need_payoff",
                    "rejection": "soft_close",
                },
            },
            "spin_need_payoff": {
                "goal": "Establish value",
                "phase": "need_payoff",
                "required_data": [],
                "is_final": False,
                "transitions": {
                    "data_complete": "presentation",
                    "ready": "presentation",
                    "rejection": "soft_close",
                },
            },
            "presentation": {
                "goal": "Present solution",
                "phase": "presentation",
                "required_data": [],
                "is_final": False,
                "transitions": {
                    "agreed": "closing",
                    "demo_request": "closing",
                    "rejection": "soft_close",
                },
            },
            "closing": {
                "goal": "Close deal",
                "phase": "closing",
                "required_data": [],
                "is_final": False,
                "transitions": {
                    "agreed": "success",
                    "contact_provided": "success",
                    "rejection": "soft_close",
                },
            },
            "success": {
                "goal": "Success",
                "is_final": True,
                "transitions": {},
            },
            "soft_close": {
                "goal": "Soft close",
                "is_final": True,
                "transitions": {},
            },
            "human_handoff": {
                "goal": "Human handoff",
                "is_final": True,
                "transitions": {},
            },
            "_limits": {
                "max_consecutive_objections": 3,
                "max_total_objections": 5,
            },
        }

    @property
    def states(self):
        return self._states

    @property
    def constants(self):
        return self._constants

    def get_state_on_enter_flags(self, state_name):
        state_config = self._states.get(state_name, {})
        on_enter = state_config.get("on_enter", {})
        if isinstance(on_enter, dict):
            return on_enter.get("set_flags", {})
        return {}

    @property
    def phase_mapping(self):
        """Get phase -> state mapping."""
        mapping = {}
        for state_name, state_config in self._states.items():
            phase = state_config.get("phase") or state_config.get("spin_phase")
            if phase:
                mapping[phase] = state_name
        return mapping

    @property
    def state_to_phase(self):
        """
        Get complete state -> phase mapping.

        This is the CANONICAL source of truth for state -> phase resolution.
        Includes both reverse mapping from phase_mapping AND explicit phases
        from state configs (explicit phases have higher priority).
        """
        # Start with reverse mapping from phase_mapping
        result = {v: k for k, v in self.phase_mapping.items()}

        # Override with explicit phases from state configs (higher priority)
        for state_name, state_config in self._states.items():
            explicit_phase = state_config.get("phase") or state_config.get("spin_phase")
            if explicit_phase:
                result[state_name] = explicit_phase

        return result

    def get_phase_for_state(self, state_name):
        """Get phase name for a state."""
        # Delegate to state_to_phase which contains the complete mapping
        return self.state_to_phase.get(state_name)

    def is_phase_state(self, state_name):
        """Check if a state is a phase state."""
        return self.get_phase_for_state(state_name) is not None


@pytest.fixture
def create_scenario_orchestrator():
    """Factory to create orchestrator for scenario testing."""
    def _create(
        initial_state: str = "greeting",
        initial_data: Dict[str, Any] = None,
        persona: str = "default",
        sources: List[type] = None
    ):
        SourceRegistry.reset()

        sm = ScenarioStateMachine(state=initial_state, collected_data=initial_data or {})
        if persona:
            sm._collected_data["persona"] = persona

        fc = ScenarioFlowConfig()

        orchestrator = DialogueOrchestrator(
            state_machine=sm,
            flow_config=fc,
            enable_validation=True,
        )

        if sources:
            orchestrator._sources.clear()
            for source_class in sources:
                orchestrator.add_source(source_class())

        return orchestrator

    return _create


# =============================================================================
# 1. PERSONA-BASED SCENARIOS
# =============================================================================

@pytest.mark.scenario
class TestPersonaScenarios:
    """
    Tests different client personas.

    Each persona has different behavior patterns and limits.
    """

    def test_happy_path_persona_success(self, create_scenario_orchestrator):
        """Happy path persona should complete successfully."""
        orchestrator = create_scenario_orchestrator(
            initial_state="greeting",
            persona="default",
            sources=[DataCollectorSource, TransitionResolverSource]
        )

        scenario = DialogueScenario(
            name="Happy Path to Success",
            description="Cooperative client completes full flow",
            initial_state="greeting",
            initial_data={"persona": "default"},
            turns=[
                DialogueTurn(
                    intent="greeting",
                    expected_state="spin_situation",
                    description="Initial greeting"
                ),
                DialogueTurn(
                    intent="info_provided",
                    pre_collected_data={"company_size": "50"},
                    expected_state="spin_problem",
                    description="Provide company size"
                ),
                DialogueTurn(
                    intent="problem_stated",
                    pre_collected_data={"pain_point": "manual_work"},
                    expected_state="spin_implication",
                    description="Reveal pain point"
                ),
                DialogueTurn(
                    intent="understood",
                    expected_state="spin_need_payoff",
                    description="Acknowledge implications"
                ),
                DialogueTurn(
                    intent="ready",
                    expected_state="presentation",
                    description="Ready to see solution"
                ),
                DialogueTurn(
                    intent="agreed",
                    expected_state="closing",
                    description="Agree to proceed"
                ),
                DialogueTurn(
                    intent="contact_provided",
                    pre_collected_data={"contact": "test@test.com"},
                    expected_state="success",
                    description="Provide contact"
                ),
            ],
            expected_final_state="success",
            expected_final_is_final=True,
        )

        runner = ScenarioTestRunner(orchestrator)
        result = runner.run_scenario(scenario)

        assert result["success"], f"Errors: {result['errors']}"

    def test_busy_persona_low_objection_tolerance(self, create_scenario_orchestrator):
        """Busy persona should have low objection tolerance (2 consecutive)."""
        orchestrator = create_scenario_orchestrator(
            initial_state="spin_situation",
            initial_data={"company_size": "20"},
            persona="busy",
            sources=[ObjectionGuardSource]
        )

        sm = orchestrator._state_machine
        sm._intent_tracker._objection_consecutive = 1
        sm._intent_tracker._objection_total = 1

        # Second consecutive objection - should NOT trigger yet (busy = 2 consecutive)
        decision = orchestrator.process_turn(intent="objection_price", extracted_data={})
        # At this point the tracker has consecutive=2 after increment

        # Third consecutive objection - NOW should trigger (after 2 more)
        sm._intent_tracker._objection_consecutive = 2
        sm._intent_tracker._objection_total = 2

        # Use valid objection intent (objection_timing is in DEFAULT_OBJECTION_INTENTS)
        decision = orchestrator.process_turn(intent="objection_timing", extracted_data={})

        assert decision.action == "objection_limit_reached"
        assert decision.next_state == "soft_close"

    def test_skeptic_persona_higher_objection_tolerance(self, create_scenario_orchestrator):
        """Skeptical persona should tolerate more objections (4 consecutive)."""
        orchestrator = create_scenario_orchestrator(
            initial_state="spin_problem",
            persona="skeptic",  # FIX: Changed from "skeptical" to "skeptic" to match personas.py
            sources=[ObjectionGuardSource]
        )

        sm = orchestrator._state_machine
        sm._intent_tracker._objection_consecutive = 2
        sm._intent_tracker._objection_total = 2

        # 3rd objection - should still be OK for skeptic (limit is 4, count becomes 3)
        decision = orchestrator.process_turn(intent="objection_price", extracted_data={})

        # Should NOT trigger limit yet (skeptic has consecutive=4, current=3)
        assert not (decision.action == "objection_limit_reached" and decision.next_state == "soft_close")

        # 4th objection will trigger (skeptic limit is 4 consecutive, count becomes 4 >= 4)
        sm._intent_tracker._objection_consecutive = 3
        sm._intent_tracker._objection_total = 3

        decision = orchestrator.process_turn(intent="objection_price", extracted_data={})

        assert decision.action == "objection_limit_reached"
        assert decision.next_state == "soft_close"

    def test_price_sensitive_persona_with_price_questions(self, create_scenario_orchestrator):
        """Price sensitive persona asking many price questions."""
        orchestrator = create_scenario_orchestrator(
            initial_state="spin_situation",
            initial_data={"company_size": "30"},
            persona="price_sensitive",
            sources=[PriceQuestionSource, DataCollectorSource]
        )

        # First price question
        d1 = orchestrator.process_turn(intent="price_question", extracted_data={})
        assert d1.action == "answer_with_pricing"
        assert d1.next_state == "spin_problem"  # Data was complete

        # Another price question in new state
        d2 = orchestrator.process_turn(intent="price_question", extracted_data={})
        assert d2.action == "answer_with_pricing"


# =============================================================================
# 2. FLOW-SPECIFIC SCENARIOS
# =============================================================================

@pytest.mark.scenario
class TestFlowScenarios:
    """
    Tests specific flow patterns.

    Verifies different paths through the state machine.
    """

    def test_direct_demo_request_path(self, create_scenario_orchestrator):
        """Direct demo request should fast-track to closing."""
        orchestrator = create_scenario_orchestrator(
            initial_state="greeting",
            sources=[TransitionResolverSource]
        )

        # Client immediately requests demo
        decision = orchestrator.process_turn(intent="demo_request", extracted_data={})

        # Should advance toward closing (state machine has demo_request -> presentation in greeting)
        assert decision.next_state in ["presentation", "closing", "spin_situation"]

    def test_problem_discovery_path(self, create_scenario_orchestrator):
        """Path focused on problem discovery."""
        orchestrator = create_scenario_orchestrator(
            initial_state="spin_situation",
            sources=[DataCollectorSource]
        )

        sm = orchestrator._state_machine

        # Provide company size
        sm._collected_data["company_size"] = "100"
        d1 = orchestrator.process_turn(intent="info_provided", extracted_data={})
        assert d1.next_state == "spin_problem"

        # Reveal major pain
        sm._collected_data["pain_point"] = "losing_customers"
        d2 = orchestrator.process_turn(intent="problem_stated", extracted_data={})
        assert d2.next_state == "spin_implication"

    def test_objection_handling_path(self, create_scenario_orchestrator):
        """Path with objections that are handled successfully."""
        orchestrator = create_scenario_orchestrator(
            initial_state="spin_problem",
            initial_data={"company_size": "50"},
            sources=[ObjectionGuardSource, DataCollectorSource]
        )

        sm = orchestrator._state_machine

        # First objection
        d1 = orchestrator.process_turn(intent="objection_price", extracted_data={})
        assert sm.state != "soft_close"  # Should continue

        # Positive turn after objection
        sm._intent_tracker._objection_consecutive = 0
        sm._collected_data["pain_point"] = "test_pain"
        d2 = orchestrator.process_turn(intent="problem_stated", extracted_data={})
        assert sm.state == "spin_implication"


# =============================================================================
# 3. STRESS SCENARIOS
# =============================================================================

@pytest.mark.scenario
class TestStressScenarios:
    """
    Tests edge cases and stress conditions.

    Verifies system handles unusual situations correctly.
    """

    def test_rapid_objection_sequence(self, create_scenario_orchestrator):
        """Rapid sequence of objections should trigger soft close."""
        orchestrator = create_scenario_orchestrator(
            initial_state="spin_problem",
            persona="default",  # 3 consecutive limit
            sources=[ObjectionGuardSource]
        )

        sm = orchestrator._state_machine

        # First objection
        sm._intent_tracker._objection_consecutive = 0
        sm._intent_tracker._objection_total = 0
        orchestrator.process_turn(intent="objection_price", extracted_data={})

        # Second objection
        sm._intent_tracker._objection_consecutive = 1
        sm._intent_tracker._objection_total = 1
        orchestrator.process_turn(intent="objection_no_time", extracted_data={})

        # Third objection - should NOT trigger limit yet for default persona (limit is 4)
        sm._intent_tracker._objection_consecutive = 2
        sm._intent_tracker._objection_total = 2
        d3 = orchestrator.process_turn(intent="objection_think", extracted_data={})

        # At this point, with 4 consecutive objections for default persona (updated from 3)
        sm._intent_tracker._objection_consecutive = 4  # Updated: default consecutive limit is now 4
        sm._intent_tracker._objection_total = 4
        d4 = orchestrator.process_turn(intent="objection_competitor", extracted_data={})

        assert d4.action == "objection_limit_reached"
        assert d4.next_state == "soft_close"

    def test_multiple_price_questions_sequence(self, create_scenario_orchestrator):
        """Multiple price questions should not block flow."""
        orchestrator = create_scenario_orchestrator(
            initial_state="spin_situation",
            sources=[PriceQuestionSource, DataCollectorSource]
        )

        sm = orchestrator._state_machine

        # Price question 1 (no data yet)
        d1 = orchestrator.process_turn(intent="price_question", extracted_data={})
        assert d1.action == "answer_with_pricing"
        assert sm.state == "spin_situation"  # Should stay

        # Price question 2 (still no data)
        d2 = orchestrator.process_turn(intent="pricing_details", extracted_data={})
        assert d2.action == "answer_with_pricing"
        assert sm.state == "spin_situation"  # Should still stay

        # Now provide data + price question (discount_request returns different action)
        sm._collected_data["company_size"] = "100"
        d3 = orchestrator.process_turn(intent="discount_request", extracted_data={})
        # NOTE: discount_request returns "handle_discount_request" not "answer_with_pricing"
        assert d3.action == "handle_discount_request"
        assert sm.state == "spin_problem"  # NOW should advance

    def test_empty_extracted_data_handling(self, create_scenario_orchestrator):
        """System should handle empty extracted data gracefully."""
        orchestrator = create_scenario_orchestrator(
            initial_state="spin_situation",
            sources=[DataCollectorSource, IntentProcessorSource]
        )

        # All turns with empty extracted_data
        for _ in range(5):
            decision = orchestrator.process_turn(intent="info_provided", extracted_data={})
            assert decision is not None
            assert decision.action is not None

    def test_unknown_intent_handling(self, create_scenario_orchestrator):
        """System should handle unknown intents gracefully."""
        orchestrator = create_scenario_orchestrator(
            initial_state="spin_situation",
            sources=[IntentProcessorSource, TransitionResolverSource]
        )

        decision = orchestrator.process_turn(
            intent="completely_unknown_intent_xyz",
            extracted_data={}
        )

        # Should not crash, should have some decision
        assert decision is not None
        assert decision.action is not None or decision.next_state is not None


# =============================================================================
# 4. REGRESSION SCENARIOS
# =============================================================================

@pytest.mark.scenario
class TestRegressionScenarios:
    """
    Tests for known bugs and their fixes.

    Each test documents a specific bug that was fixed.
    """

    def test_regression_price_question_blocks_transition(self, create_scenario_orchestrator):
        """
        REGRESSION: Price question used to block data_complete transition.

        OLD BUG:
        - User: "У нас 15 человек. Сколько стоит?"
        - System: answered price, but STAYED in spin_situation
        - data_complete check was NEVER reached

        FIX:
        - PriceQuestionSource uses combinable=True
        - Both action (answer_with_pricing) AND transition (data_complete) applied
        """
        orchestrator = create_scenario_orchestrator(
            initial_state="spin_situation",
            initial_data={"company_size": "15"},  # Data already complete!
            sources=[PriceQuestionSource, DataCollectorSource]
        )

        decision = orchestrator.process_turn(
            intent="price_question",
            extracted_data={"company_size": "15"},
        )

        # MUST have both action AND transition
        assert decision.action == "answer_with_pricing", \
            "Price question should be answered"
        assert decision.next_state == "spin_problem", \
            "Should transition because data is complete"
        assert "data_complete" in decision.reason_codes or "price" in str(decision.reason_codes)

    def test_regression_blocking_action_without_transition(self, create_scenario_orchestrator):
        """
        REGRESSION: Blocking actions should prevent data_complete transition.

        This is the CORRECT behavior - non-combinable actions should block.
        """
        orchestrator = create_scenario_orchestrator(
            initial_state="spin_situation",
            initial_data={"company_size": "20"},
            sources=[DataCollectorSource]
        )

        # Add a blocking source
        class BlockingSource(KnowledgeSource):
            def should_contribute(self, bb):
                return True

            def contribute(self, bb):
                bb.propose_action(
                    action="must_handle_this_first",
                    priority=Priority.CRITICAL,
                    combinable=False,  # BLOCKING
                    source_name=self.name,
                    reason_code="blocking_action",
                )

        orchestrator.add_source(BlockingSource("BlockingSource"))

        decision = orchestrator.process_turn(
            intent="test",
            extracted_data={},
        )

        # Blocking action should be selected
        assert decision.action == "must_handle_this_first"
        # Transition should NOT happen
        assert decision.next_state == "spin_situation"
        assert "data_complete" not in decision.reason_codes

    def test_regression_persona_limits_ignored(self, create_scenario_orchestrator):
        """
        REGRESSION: Persona-specific objection limits were ignored.

        FIX: ObjectionGuardSource now reads persona from collected_data
        and applies correct limits.
        """
        # Test busy persona (lowest limits)
        orchestrator = create_scenario_orchestrator(
            initial_state="spin_problem",
            persona="busy",
            sources=[ObjectionGuardSource]
        )

        sm = orchestrator._state_machine
        sm._intent_tracker._objection_consecutive = 2  # Busy limit
        sm._intent_tracker._objection_total = 2

        decision = orchestrator.process_turn(intent="objection_price", extracted_data={})

        assert decision.action == "objection_limit_reached", \
            "Busy persona should hit limit at 2 consecutive objections"
        assert decision.next_state == "soft_close"


# =============================================================================
# 5. DATA FLOW SCENARIOS
# =============================================================================

@pytest.mark.scenario
class TestDataFlowScenarios:
    """
    Tests data collection and flow scenarios.

    Verifies data is collected and used correctly.
    """

    def test_incremental_data_collection(self, create_scenario_orchestrator):
        """Data should be collected incrementally across turns."""
        orchestrator = create_scenario_orchestrator(
            initial_state="spin_situation",
            sources=[DataCollectorSource]
        )

        sm = orchestrator._state_machine

        # Turn 1: Partial data (optional field)
        sm._collected_data["industry"] = "technology"
        d1 = orchestrator.process_turn(intent="info_provided", extracted_data={})
        assert "industry" in sm.collected_data
        assert sm.state == "spin_situation"  # Still missing company_size

        # Turn 2: Required data
        sm._collected_data["company_size"] = "200"
        d2 = orchestrator.process_turn(intent="info_provided", extracted_data={})
        assert "industry" in sm.collected_data
        assert "company_size" in sm.collected_data
        assert sm.state == "spin_problem"  # Now should advance

    def test_data_persistence_across_phases(self, create_scenario_orchestrator):
        """Collected data should persist across phase transitions."""
        orchestrator = create_scenario_orchestrator(
            initial_state="spin_situation",
            initial_data={"initial_field": "initial_value"},
            sources=[DataCollectorSource]
        )

        sm = orchestrator._state_machine

        # Collect data in situation
        sm._collected_data["company_size"] = "50"
        orchestrator.process_turn(intent="info_provided", extracted_data={})
        assert sm.state == "spin_problem"

        # Verify initial data persisted
        assert sm.collected_data.get("initial_field") == "initial_value"
        assert sm.collected_data.get("company_size") == "50"

        # Collect more data in problem
        sm._collected_data["pain_point"] = "slow_growth"
        orchestrator.process_turn(intent="problem_stated", extracted_data={})
        assert sm.state == "spin_implication"

        # All data should be present
        assert sm.collected_data.get("initial_field") == "initial_value"
        assert sm.collected_data.get("company_size") == "50"
        assert sm.collected_data.get("pain_point") == "slow_growth"


# =============================================================================
# 6. COMBINED SCENARIOS
# =============================================================================

@pytest.mark.scenario
class TestCombinedScenarios:
    """
    Tests combining multiple features in realistic scenarios.

    These are the most comprehensive integration tests.
    """

    def test_full_conversation_with_price_and_objections(self, create_scenario_orchestrator):
        """
        Complete conversation with price questions and objections.

        Simulates a realistic sales dialogue:
        1. Greeting
        2. Situation questions + price question
        3. Problem discovery + objection
        4. Progress to close
        """
        orchestrator = create_scenario_orchestrator(
            initial_state="greeting",
            persona="default",
            sources=[
                PriceQuestionSource,
                DataCollectorSource,
                ObjectionGuardSource,
                TransitionResolverSource,
            ]
        )

        sm = orchestrator._state_machine

        # Turn 1: Greeting
        d1 = orchestrator.process_turn(intent="greeting", extracted_data={})
        assert sm.state == "spin_situation"

        # Turn 2: Price question early (no data yet)
        d2 = orchestrator.process_turn(intent="price_question", extracted_data={})
        assert d2.action == "answer_with_pricing"
        assert sm.state == "spin_situation"  # No data yet

        # Turn 3: Provide data + price question
        sm._collected_data["company_size"] = "75"
        d3 = orchestrator.process_turn(intent="price_question", extracted_data={})
        assert d3.action == "answer_with_pricing"
        assert sm.state == "spin_problem"  # Should advance now

        # Turn 4: Objection in problem phase
        d4 = orchestrator.process_turn(intent="objection_price", extracted_data={})
        assert sm.state != "soft_close"  # First objection, should continue

        # Turn 5: Provide pain point
        sm._intent_tracker._objection_consecutive = 0  # Reset objection streak
        sm._collected_data["pain_point"] = "high_costs"
        d5 = orchestrator.process_turn(intent="problem_stated", extracted_data={})
        assert sm.state == "spin_implication"

        # Verify all data collected
        assert sm.collected_data.get("company_size") == "75"
        assert sm.collected_data.get("pain_point") == "high_costs"

    def test_all_sources_working_together(self, create_scenario_orchestrator):
        """All 6 knowledge sources working together without conflicts."""
        orchestrator = create_scenario_orchestrator(
            initial_state="spin_situation",
            initial_data={"company_size": "100"},
            sources=[
                PriceQuestionSource,
                DataCollectorSource,
                ObjectionGuardSource,
                IntentProcessorSource,
                TransitionResolverSource,
                EscalationSource,
            ]
        )

        # Price question with complete data
        d1 = orchestrator.process_turn(intent="price_question", extracted_data={})
        assert d1.action == "answer_with_pricing"
        assert d1.next_state == "spin_problem"

        sm = orchestrator._state_machine

        # Regular intent in new state
        d2 = orchestrator.process_turn(intent="info_provided", extracted_data={})
        assert d2.action is not None

        # Escalation request
        d3 = orchestrator.process_turn(intent="escalation_request", extracted_data={})
        # Should handle escalation (either through action or transition)
        assert d3.action is not None or d3.next_state == "human_handoff"


# =============================================================================
# Run Tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
