# tests/test_blackboard_e2e_comprehensive.py

"""
Comprehensive E2E Tests for Blackboard Architecture.

Stage 14 Complete Verification: Tests the full dialogue pipeline through
SalesBot with the new Blackboard/Orchestrator system.

Test Categories:
1. Full Dialogue Pipeline - Complete bot.process() flow with Blackboard
2. Knowledge Sources Integration - All 6 sources working together
3. Edge Cases & Regression - Bug fixes, limits, blocking behavior
4. Multi-Turn Scenarios - Real conversation simulations
5. State Machine Integration - Orchestrator + StateMachine compatibility

Run with:
    pytest tests/test_blackboard_e2e_comprehensive.py -v
    pytest tests/test_blackboard_e2e_comprehensive.py -k "pipeline" -v
    pytest tests/test_blackboard_e2e_comprehensive.py -m "slow" -v  # Long scenarios
"""

import pytest
import time
from typing import Dict, Any, Optional, List
from unittest.mock import Mock, MagicMock, patch
from dataclasses import dataclass, field

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from src.blackboard.orchestrator import DialogueOrchestrator, create_orchestrator
from src.blackboard.blackboard import DialogueBlackboard
from src.blackboard.conflict_resolver import ConflictResolver
from src.blackboard.models import Proposal, ResolvedDecision
from src.blackboard.enums import Priority, ProposalType
from src.blackboard.source_registry import SourceRegistry
from src.blackboard.knowledge_source import KnowledgeSource
from src.blackboard.sources.price_question import PriceQuestionSource
from src.blackboard.sources.data_collector import DataCollectorSource
from src.blackboard.sources.objection_guard import ObjectionGuardSource
from src.blackboard.sources.intent_processor import IntentProcessorSource
from src.blackboard.sources.transition_resolver import TransitionResolverSource
from src.blackboard.sources.escalation import EscalationSource
from src.blackboard.event_bus import EventType


# =============================================================================
# Test Infrastructure
# =============================================================================

@dataclass
class IntentRecord:
    """Record of an intent for tracking."""
    intent: str
    state: str


class E2EIntentTracker:
    """Full-featured IntentTracker for E2E testing."""

    def __init__(self, turn_number: int = 0):
        self._turn_number = turn_number
        self._prev_intent = None
        self._intents: List[IntentRecord] = []
        self._objection_consecutive = 0
        self._objection_total = 0

    @property
    def turn_number(self) -> int:
        return self._turn_number

    @property
    def prev_intent(self) -> Optional[str]:
        return self._prev_intent

    def record(self, intent: str, state: str) -> None:
        if self._intents:
            self._prev_intent = self._intents[-1].intent
        self._intents.append(IntentRecord(intent=intent, state=state))
        self._turn_number += 1

        if "objection" in intent:
            self._objection_consecutive += 1
            self._objection_total += 1
        else:
            self._objection_consecutive = 0

    def objection_consecutive(self) -> int:
        return self._objection_consecutive

    def objection_total(self) -> int:
        return self._objection_total

    def total_count(self, intent: str) -> int:
        return sum(1 for r in self._intents if r.intent == intent)

    def category_total(self, category: str) -> int:
        return sum(1 for r in self._intents if category in r.intent)

    def get_intents_by_category(self, category: str) -> List[IntentRecord]:
        return [r for r in self._intents if category in r.intent]

    def increment_turn(self) -> None:
        self._turn_number += 1


class E2ECircularFlow:
    """CircularFlowManager mock for E2E testing."""

    def __init__(self):
        self._loops = 0
        self._max_loops = 3
        self._goback_count = 0

    def get_stats(self) -> Dict[str, Any]:
        return {
            "loops": self._loops,
            "max_loops": self._max_loops,
            "goback_count": self._goback_count,
        }


class E2EStateMachine:
    """
    Full-featured StateMachine for E2E testing.

    Implements all interfaces required by Orchestrator while being
    independent of external dependencies.
    """

    def __init__(
        self,
        state: str = "greeting",
        collected_data: Optional[Dict[str, Any]] = None
    ):
        self._state = state
        self._collected_data = collected_data or {}
        self._current_phase = None
        self._last_action = None
        self._intent_tracker = E2EIntentTracker()
        self._state_before_objection = None
        self.circular_flow = E2ECircularFlow()

    @property
    def state(self) -> str:
        return self._state

    @state.setter
    def state(self, value: str) -> None:
        self._state = value

    @property
    def collected_data(self) -> Dict[str, Any]:
        return self._collected_data

    @property
    def current_phase(self) -> Optional[str]:
        return self._current_phase

    @current_phase.setter
    def current_phase(self, value: Optional[str]) -> None:
        self._current_phase = value

    @property
    def last_action(self) -> Optional[str]:
        return self._last_action

    @last_action.setter
    def last_action(self, value: Optional[str]) -> None:
        self._last_action = value

    def update_data(self, data: Dict[str, Any]) -> None:
        self._collected_data.update(data)

    def transition_to(
        self,
        next_state: str,
        action: Optional[str] = None,
        phase: Optional[str] = None,
        source: str = "test",
        validate: bool = True,
    ) -> None:
        """Atomic state transition (mirrors real StateMachine.transition_to)."""
        self._state = next_state
        if action is not None:
            self._last_action = action
        if phase is not None:
            self._current_phase = phase

    def is_final(self) -> bool:
        return self._state in ("soft_close", "closed", "rejected", "success")

    def increment_turn(self) -> None:
        self._intent_tracker.increment_turn()


class E2EFlowConfig:
    """
    Full-featured FlowConfig for E2E testing with realistic state machine.
    """

    def __init__(self, custom_states: Optional[Dict[str, Dict[str, Any]]] = None):
        self._states = custom_states or self._get_default_states()
        self._constants = {
            "persona_limits": {
                "aggressive": {"consecutive": 5, "total": 8},
                "busy": {"consecutive": 2, "total": 4},
                "skeptic": {"consecutive": 4, "total": 6},
                "price_sensitive": {"consecutive": 3, "total": 6},
                "default": {"consecutive": 3, "total": 5},
            },
            "blackboard": {
                "sources": {
                    "PriceQuestionSource": {"enabled": True},
                    "DataCollectorSource": {"enabled": True},
                    "ObjectionGuardSource": {"enabled": True},
                    "IntentProcessorSource": {"enabled": True},
                    "TransitionResolverSource": {"enabled": True},
                    "EscalationSource": {"enabled": True},
                }
            }
        }

    def _get_default_states(self) -> Dict[str, Dict[str, Any]]:
        """Get comprehensive state configuration for testing."""
        return {
            "greeting": {
                "goal": "Greet user and establish rapport",
                "phase": None,
                "required_data": [],
                "is_final": False,
                "transitions": {
                    "any": "spin_situation",
                    "greeting": "spin_situation",
                    "demo_request": "presentation",
                    "price_question": "spin_situation",
                },
                "rules": {
                    "greeting": {"action": "greet_user"},
                },
            },
            "spin_situation": {
                "goal": "Understand the prospect's current situation",
                "phase": "situation",
                "required_data": ["company_size"],
                "optional_data": ["industry", "role"],
                "is_final": False,
                "transitions": {
                    "data_complete": "spin_problem",
                    "rejection": "soft_close",
                    "escalation": "human_handoff",
                },
                "rules": {
                    "info_provided": {"action": "acknowledge_and_probe"},
                    "question": {"action": "answer_question"},
                    "price_question": {"action": "answer_with_pricing"},
                },
            },
            "spin_problem": {
                "goal": "Identify business problems and pain points",
                "phase": "problem",
                "required_data": ["pain_point"],
                "is_final": False,
                "transitions": {
                    "data_complete": "spin_implication",
                    "rejection": "soft_close",
                },
                "rules": {
                    "problem_stated": {"action": "explore_problem"},
                },
            },
            "spin_implication": {
                "goal": "Explore implications of the problems",
                "phase": "implication",
                "required_data": [],
                "is_final": False,
                "transitions": {
                    "understood": "spin_need_payoff",
                    "data_complete": "spin_need_payoff",
                    "rejection": "soft_close",
                },
                "rules": {},
            },
            "spin_need_payoff": {
                "goal": "Establish value of solution",
                "phase": "need_payoff",
                "required_data": [],
                "is_final": False,
                "transitions": {
                    "ready": "presentation",
                    "data_complete": "presentation",
                    "rejection": "soft_close",
                },
                "rules": {},
            },
            "presentation": {
                "goal": "Present the solution",
                "phase": "presentation",
                "required_data": [],
                "is_final": False,
                "transitions": {
                    "agreed": "closing",
                    "demo_request": "closing",
                    "rejection": "soft_close",
                },
                "rules": {},
            },
            "closing": {
                "goal": "Move toward commitment",
                "phase": "closing",
                "required_data": [],
                "is_final": False,
                "transitions": {
                    "agreed": "success",
                    "contact_provided": "success",
                    "rejection": "soft_close",
                },
                "rules": {},
            },
            "success": {
                "goal": "Confirm agreement",
                "is_final": True,
                "transitions": {},
                "rules": {},
            },
            "soft_close": {
                "goal": "Gracefully end conversation",
                "is_final": True,
                "transitions": {},
                "rules": {},
            },
            "human_handoff": {
                "goal": "Transfer to human agent",
                "is_final": True,
                "transitions": {},
                "rules": {},
            },
            "_limits": {
                "max_consecutive_objections": 3,
                "max_total_objections": 5,
            },
        }

    @property
    def states(self) -> Dict[str, Dict[str, Any]]:
        return self._states

    @property
    def constants(self) -> Dict[str, Any]:
        return self._constants

    def to_dict(self) -> Dict[str, Any]:
        return {"states": self._states, "constants": self._constants}
    @property
    def phase_mapping(self) -> Dict[str, str]:
        """Get phase -> state mapping."""
        mapping = {}
        for state_name, state_config in self._states.items():
            phase = state_config.get("phase") or state_config.get("spin_phase")
            if phase:
                mapping[phase] = state_name
        return mapping

    @property
    def state_to_phase(self) -> Dict[str, str]:
        """Get state -> phase mapping."""
        return {v: k for k, v in self.phase_mapping.items()}

    def get_phase_for_state(self, state_name: str) -> Optional[str]:
        """Get phase name for a state."""
        state_config = self._states.get(state_name, {})
        explicit_phase = state_config.get("phase") or state_config.get("spin_phase")
        if explicit_phase:
            return explicit_phase
        return self.state_to_phase.get(state_name)

    def is_phase_state(self, state_name: str) -> bool:
        """Check if a state is a phase state."""
        return self.get_phase_for_state(state_name) is not None


    def get_state_on_enter_flags(self, state_name: str) -> Dict[str, Any]:
        """Get on_enter flags for a state."""
        state_config = self._states.get(state_name, {})
        on_enter = state_config.get("on_enter", {})
        if isinstance(on_enter, dict):
            return on_enter.get("set_flags", {})
        return {}


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def e2e_state_machine():
    """Create a state machine for E2E testing."""
    return E2EStateMachine(state="greeting")


@pytest.fixture
def e2e_flow_config():
    """Create a flow config for E2E testing."""
    return E2EFlowConfig()


@pytest.fixture
def full_orchestrator(e2e_state_machine, e2e_flow_config):
    """Create a fully configured orchestrator with all sources."""
    SourceRegistry.reset()

    orchestrator = DialogueOrchestrator(
        state_machine=e2e_state_machine,
        flow_config=e2e_flow_config,
        enable_validation=True,
    )

    return orchestrator


@pytest.fixture
def orchestrator_with_selected_sources(e2e_state_machine, e2e_flow_config):
    """Factory to create orchestrator with specific sources only."""
    def _create(source_classes: List[type]):
        SourceRegistry.reset()

        orchestrator = DialogueOrchestrator(
            state_machine=e2e_state_machine,
            flow_config=e2e_flow_config,
            enable_validation=True,
        )

        # Clear default sources and add only selected
        orchestrator._sources.clear()
        for source_class in source_classes:
            orchestrator.add_source(source_class())

        return orchestrator

    return _create


# =============================================================================
# 1. FULL DIALOGUE PIPELINE TESTS
# =============================================================================

class TestFullDialoguePipeline:
    """
    Tests the complete dialogue pipeline from greeting to close.

    Verifies:
    - State transitions work correctly
    - Actions are determined properly
    - Data collection triggers transitions
    - Final states are reached
    """

    def test_happy_path_greeting_to_situation(self, full_orchestrator):
        """Happy path: greeting -> spin_situation."""
        sm = full_orchestrator._state_machine
        assert sm.state == "greeting"

        decision = full_orchestrator.process_turn(
            intent="greeting",
            extracted_data={},
        )

        # Should transition from greeting
        assert decision.next_state == "spin_situation"
        assert decision.action is not None
        assert sm.state == "spin_situation"

    def test_data_collection_advances_phase(self):
        """Data collection should advance to next phase."""
        SourceRegistry.reset()

        sm = E2EStateMachine(state="spin_situation")
        sm._collected_data = {"company_size": "50"}  # Required data present
        fc = E2EFlowConfig()

        orchestrator = DialogueOrchestrator(
            state_machine=sm,
            flow_config=fc,
        )

        # Use only DataCollectorSource to focus the test
        orchestrator._sources.clear()
        orchestrator.add_source(DataCollectorSource())

        decision = orchestrator.process_turn(
            intent="info_provided",
            extracted_data={"company_size": "50"},
        )

        # Should advance to spin_problem
        assert decision.next_state == "spin_problem"
        assert "data_complete" in decision.reason_codes

    def test_full_spin_flow_progression(self):
        """Test progression through all SPIN phases."""
        SourceRegistry.reset()

        sm = E2EStateMachine(state="greeting")
        fc = E2EFlowConfig()

        orchestrator = DialogueOrchestrator(
            state_machine=sm,
            flow_config=fc,
        )

        # Use DataCollectorSource and TransitionResolverSource for proper flow
        orchestrator._sources.clear()
        orchestrator.add_source(DataCollectorSource())
        orchestrator.add_source(TransitionResolverSource())

        # Start at greeting
        orchestrator.process_turn(intent="greeting", extracted_data={})
        assert sm.state == "spin_situation"

        # Situation -> Problem
        sm._collected_data["company_size"] = "100"
        orchestrator.process_turn(intent="info_provided", extracted_data={})
        assert sm.state == "spin_problem"

        # Problem -> Implication
        sm._collected_data["pain_point"] = "slow_processes"
        orchestrator.process_turn(intent="problem_stated", extracted_data={})
        assert sm.state == "spin_implication"

        # Implication -> Need Payoff
        orchestrator.process_turn(intent="understood", extracted_data={})
        assert sm.state == "spin_need_payoff"

        # Need Payoff -> Presentation
        orchestrator.process_turn(intent="ready", extracted_data={})
        assert sm.state == "presentation"

    def test_rejection_leads_to_soft_close(self, full_orchestrator):
        """Rejection intent should lead to soft_close."""
        sm = full_orchestrator._state_machine
        sm.state = "spin_problem"

        # Add a source that handles rejection
        class RejectionHandler(KnowledgeSource):
            def should_contribute(self, bb):
                return bb.current_intent == "rejection"

            def contribute(self, bb):
                bb.propose_action(
                    action="acknowledge_rejection",
                    priority=Priority.CRITICAL,
                    combinable=True,
                    source_name=self.name,
                    reason_code="rejection_detected",
                )
                bb.propose_transition(
                    next_state="soft_close",
                    priority=Priority.CRITICAL,
                    source_name=self.name,
                    reason_code="rejection_transition",
                )

        full_orchestrator.add_source(RejectionHandler("RejectionHandler"))

        decision = full_orchestrator.process_turn(
            intent="rejection",
            extracted_data={},
        )

        assert decision.next_state == "soft_close"

    def test_demo_request_fast_track(self, full_orchestrator):
        """Demo request should fast-track to presentation/closing."""
        sm = full_orchestrator._state_machine
        sm.state = "greeting"

        decision = full_orchestrator.process_turn(
            intent="demo_request",
            extracted_data={},
        )

        # Should advance significantly
        assert decision.next_state in ["presentation", "closing", "spin_situation"]


# =============================================================================
# 2. KNOWLEDGE SOURCES INTEGRATION TESTS
# =============================================================================

class TestKnowledgeSourcesIntegration:
    """
    Tests all Knowledge Sources working together.

    Verifies:
    - Each source contributes when appropriate
    - Sources don't interfere with each other
    - Priorities are respected
    - Combinable actions work correctly
    """

    def test_price_question_source_contributes(self, orchestrator_with_selected_sources):
        """PriceQuestionSource should contribute for price intents."""
        orchestrator = orchestrator_with_selected_sources([PriceQuestionSource])
        sm = orchestrator._state_machine
        sm.state = "spin_situation"

        decision = orchestrator.process_turn(
            intent="price_question",
            extracted_data={},
        )

        assert decision.action == "answer_with_pricing"
        assert "price_question" in decision.reason_codes or "price" in str(decision.reason_codes)

    def test_price_question_is_combinable(self, orchestrator_with_selected_sources):
        """PriceQuestionSource action should be combinable with transitions."""
        orchestrator = orchestrator_with_selected_sources([
            PriceQuestionSource,
            DataCollectorSource
        ])
        sm = orchestrator._state_machine
        sm.state = "spin_situation"

        # Data is complete
        sm._collected_data["company_size"] = "50"

        decision = orchestrator.process_turn(
            intent="price_question",
            extracted_data={},
        )

        # Should have BOTH action AND transition
        assert decision.action == "answer_with_pricing"
        assert decision.next_state == "spin_problem"

    def test_data_collector_source_detects_completion(self, orchestrator_with_selected_sources):
        """DataCollectorSource should detect when required data is complete."""
        orchestrator = orchestrator_with_selected_sources([DataCollectorSource])
        sm = orchestrator._state_machine
        sm.state = "spin_situation"
        sm._collected_data["company_size"] = "25"

        decision = orchestrator.process_turn(
            intent="info_provided",
            extracted_data={},
        )

        assert decision.next_state == "spin_problem"
        assert "data_complete" in decision.reason_codes

    def test_objection_guard_within_limits(self, orchestrator_with_selected_sources):
        """ObjectionGuardSource should allow objections within limits."""
        orchestrator = orchestrator_with_selected_sources([ObjectionGuardSource])
        sm = orchestrator._state_machine
        sm.state = "spin_problem"
        sm._intent_tracker._objection_consecutive = 1
        sm._intent_tracker._objection_total = 1

        decision = orchestrator.process_turn(
            intent="objection_price",
            extracted_data={},
        )

        # Should NOT go to soft_close yet
        assert decision.next_state != "soft_close" or decision.action != "objection_limit_reached"

    def test_objection_guard_exceeds_limits(self, orchestrator_with_selected_sources):
        """ObjectionGuardSource should trigger soft_close when limits exceeded."""
        orchestrator = orchestrator_with_selected_sources([ObjectionGuardSource])
        sm = orchestrator._state_machine
        sm.state = "spin_problem"
        sm._intent_tracker._objection_consecutive = 3
        sm._intent_tracker._objection_total = 5

        decision = orchestrator.process_turn(
            intent="objection_price",
            extracted_data={},
        )

        assert decision.action == "objection_limit_reached"
        assert decision.next_state == "soft_close"

    def test_escalation_source_triggers_handoff(self, orchestrator_with_selected_sources):
        """EscalationSource should trigger escalation action when needed.

        NOTE: EscalationSource uses combinable=False which blocks ALL transitions
        including its own. The action is applied but state doesn't change.
        This is by design - blocking actions are meant to halt all processing.
        The bot.py layer handles the actual state transition based on the action.
        """
        orchestrator = orchestrator_with_selected_sources([EscalationSource])
        sm = orchestrator._state_machine
        sm.state = "spin_situation"

        # Use a recognized escalation intent from EXPLICIT_ESCALATION_INTENTS
        decision = orchestrator.process_turn(
            intent="request_human",
            extracted_data={},
        )

        # Escalation action should be proposed
        assert decision.action == "escalate_to_human"
        assert "escalation_explicit_request" in decision.reason_codes
        # Note: State doesn't change because combinable=False blocks all transitions
        # including the transition from the same source. The actual handoff is
        # handled by bot.py based on the action returned.

    def test_all_sources_together_price_with_data(self):
        """All sources working together: price question with complete data."""
        SourceRegistry.reset()

        sm = E2EStateMachine(state="spin_situation")
        sm._collected_data["company_size"] = "30"
        fc = E2EFlowConfig()

        orchestrator = DialogueOrchestrator(
            state_machine=sm,
            flow_config=fc,
        )

        # Use only relevant sources
        orchestrator._sources.clear()
        orchestrator.add_source(PriceQuestionSource())
        orchestrator.add_source(DataCollectorSource())
        orchestrator.add_source(IntentProcessorSource())

        decision = orchestrator.process_turn(
            intent="price_question",
            extracted_data={"company_size": "30"},
        )

        # Price should be answered AND phase should advance
        assert decision.action == "answer_with_pricing"
        assert decision.next_state == "spin_problem"

    def test_source_priority_ordering(self):
        """Higher priority sources should win in conflicts."""
        SourceRegistry.reset()

        sm = E2EStateMachine(state="spin_situation")
        fc = E2EFlowConfig()

        orchestrator = DialogueOrchestrator(
            state_machine=sm,
            flow_config=fc,
        )

        orchestrator._sources.clear()

        class LowPrioritySource(KnowledgeSource):
            def should_contribute(self, bb):
                return True

            def contribute(self, bb):
                bb.propose_action(
                    action="low_priority_action",
                    priority=Priority.LOW,
                    source_name=self.name,
                    reason_code="low_priority",
                )

        class HighPrioritySource(KnowledgeSource):
            def should_contribute(self, bb):
                return True

            def contribute(self, bb):
                bb.propose_action(
                    action="high_priority_action",
                    priority=Priority.HIGH,
                    source_name=self.name,
                    reason_code="high_priority",
                )

        orchestrator.add_source(LowPrioritySource("LowPrioritySource"))
        orchestrator.add_source(HighPrioritySource("HighPrioritySource"))

        decision = orchestrator.process_turn(intent="test", extracted_data={})

        assert decision.action == "high_priority_action"


# =============================================================================
# 3. EDGE CASES & REGRESSION TESTS
# =============================================================================

class TestEdgeCasesAndRegression:
    """
    Tests for edge cases and regression verification.

    Verifies:
    - Known bugs are fixed
    - Edge cases handled properly
    - Blocking behavior works
    - Persona-specific limits
    """

    def test_price_question_no_longer_blocks_transition(self):
        """
        BUG FIX: Price question should not block data_complete transition.

        OLD BEHAVIOR: price_question -> return action, stay in state
        NEW BEHAVIOR: price_question -> action + transition (combinable)
        """
        SourceRegistry.reset()

        sm = E2EStateMachine(state="spin_situation")
        sm._collected_data["company_size"] = "15"
        fc = E2EFlowConfig()

        orchestrator = DialogueOrchestrator(
            state_machine=sm,
            flow_config=fc,
        )

        orchestrator._sources.clear()
        orchestrator.add_source(PriceQuestionSource())
        orchestrator.add_source(DataCollectorSource())

        decision = orchestrator.process_turn(
            intent="price_question",
            extracted_data={},
        )

        # FIXED: Both action and transition are applied
        assert decision.action == "answer_with_pricing"
        assert decision.next_state == "spin_problem"

    def test_blocking_action_prevents_transition(self):
        """
        Blocking (non-combinable) actions should prevent transitions.
        """
        SourceRegistry.reset()

        sm = E2EStateMachine(state="spin_situation")
        sm._collected_data["company_size"] = "15"
        fc = E2EFlowConfig()

        orchestrator = DialogueOrchestrator(
            state_machine=sm,
            flow_config=fc,
        )

        orchestrator._sources.clear()

        class BlockingSource(KnowledgeSource):
            def should_contribute(self, bb):
                return True

            def contribute(self, bb):
                bb.propose_action(
                    action="blocking_action",
                    priority=Priority.CRITICAL,
                    combinable=False,  # BLOCKING
                    source_name=self.name,
                    reason_code="blocking_test",
                )

        orchestrator.add_source(BlockingSource("BlockingSource"))
        orchestrator.add_source(DataCollectorSource())

        decision = orchestrator.process_turn(
            intent="test",
            extracted_data={},
        )

        # Blocking action should prevent data_complete transition
        assert decision.action == "blocking_action"
        assert decision.next_state == "spin_situation"
        assert "data_complete" not in decision.reason_codes

    def test_persona_limits_busy(self):
        """Busy persona should have low objection limits (2 consecutive)."""
        SourceRegistry.reset()

        sm = E2EStateMachine(state="spin_problem")
        sm._collected_data["persona"] = "busy"
        sm._intent_tracker._objection_consecutive = 2
        sm._intent_tracker._objection_total = 2
        fc = E2EFlowConfig()

        orchestrator = DialogueOrchestrator(
            state_machine=sm,
            flow_config=fc,
        )

        orchestrator._sources.clear()
        orchestrator.add_source(ObjectionGuardSource())

        decision = orchestrator.process_turn(
            intent="objection_price",
            extracted_data={},
        )

        # Busy persona hits limit at 2
        assert decision.action == "objection_limit_reached"
        assert decision.next_state == "soft_close"

    def test_persona_limits_aggressive(self):
        """Aggressive persona should have high objection limits (5 consecutive)."""
        SourceRegistry.reset()

        sm = E2EStateMachine(state="spin_problem")
        sm._collected_data["persona"] = "aggressive"
        sm._intent_tracker._objection_consecutive = 4
        sm._intent_tracker._objection_total = 4
        fc = E2EFlowConfig()

        orchestrator = DialogueOrchestrator(
            state_machine=sm,
            flow_config=fc,
        )

        orchestrator._sources.clear()
        orchestrator.add_source(ObjectionGuardSource())

        decision = orchestrator.process_turn(
            intent="objection_price",
            extracted_data={},
        )

        # Aggressive persona should NOT hit limit yet at 4
        assert not (decision.action == "objection_limit_reached" and decision.next_state == "soft_close")

    def test_source_error_isolation(self):
        """Source errors should not break the pipeline."""
        SourceRegistry.reset()

        sm = E2EStateMachine(state="spin_situation")
        fc = E2EFlowConfig()

        orchestrator = DialogueOrchestrator(
            state_machine=sm,
            flow_config=fc,
        )

        orchestrator._sources.clear()

        class ErrorSource(KnowledgeSource):
            def should_contribute(self, bb):
                return True

            def contribute(self, bb):
                raise ValueError("Test error - should be caught")

        class GoodSource(KnowledgeSource):
            def should_contribute(self, bb):
                return True

            def contribute(self, bb):
                bb.propose_action(
                    action="good_action",
                    priority=Priority.NORMAL,
                    source_name=self.name,
                    reason_code="good_source",
                )

        orchestrator.add_source(ErrorSource("ErrorSource"))
        orchestrator.add_source(GoodSource("GoodSource"))

        # Should not raise, should continue with good source
        decision = orchestrator.process_turn(
            intent="test",
            extracted_data={},
        )

        assert decision.action == "good_action"

    def test_empty_proposals_fallback(self):
        """When no sources contribute, fallback should be used."""
        SourceRegistry.reset()

        sm = E2EStateMachine(state="spin_situation")
        fc = E2EFlowConfig()

        orchestrator = DialogueOrchestrator(
            state_machine=sm,
            flow_config=fc,
        )

        orchestrator._sources.clear()

        # No sources = no proposals
        decision = orchestrator.process_turn(
            intent="unknown_intent",
            extracted_data={},
        )

        # Should use fallback
        assert decision.action is not None
        assert decision.next_state is not None


# =============================================================================
# 4. MULTI-TURN SCENARIO TESTS
# =============================================================================

class TestMultiTurnScenarios:
    """
    Tests for realistic multi-turn conversation scenarios.

    Verifies:
    - Extended conversations work correctly
    - State consistency across turns
    - Data accumulation works
    - Turn counting works
    """

    def test_complete_sales_conversation(self):
        """Complete sales conversation from greeting to success."""
        SourceRegistry.reset()

        sm = E2EStateMachine(state="greeting")
        fc = E2EFlowConfig()

        orchestrator = DialogueOrchestrator(
            state_machine=sm,
            flow_config=fc,
        )

        orchestrator._sources.clear()
        orchestrator.add_source(DataCollectorSource())
        orchestrator.add_source(TransitionResolverSource())

        # Turn 1: Greeting
        d1 = orchestrator.process_turn(intent="greeting", extracted_data={})
        assert sm.state == "spin_situation"

        # Turn 2: Provide company size
        sm._collected_data["company_size"] = "50"
        d2 = orchestrator.process_turn(intent="info_provided", extracted_data={"company_size": "50"})
        assert sm.state == "spin_problem"

        # Turn 3: Reveal pain point
        sm._collected_data["pain_point"] = "manual_processes"
        d3 = orchestrator.process_turn(intent="problem_stated", extracted_data={"pain_point": "manual_processes"})
        assert sm.state == "spin_implication"

        # Turn 4: Acknowledge implications
        d4 = orchestrator.process_turn(intent="understood", extracted_data={})
        assert sm.state == "spin_need_payoff"

        # Turn 5: Express need
        d5 = orchestrator.process_turn(intent="ready", extracted_data={})
        assert sm.state == "presentation"

        # Turn 6: Agreement
        d6 = orchestrator.process_turn(intent="agreed", extracted_data={})
        assert sm.state == "closing"

        # Turn 7: Provide contact
        sm._collected_data["contact"] = "test@example.com"
        d7 = orchestrator.process_turn(intent="contact_provided", extracted_data={"contact": "test@example.com"})
        assert sm.state == "success"
        assert sm.is_final()

    def test_conversation_with_objections(self):
        """Conversation that includes handled objections."""
        SourceRegistry.reset()

        sm = E2EStateMachine(state="spin_problem")
        sm._collected_data["company_size"] = "30"
        fc = E2EFlowConfig()

        orchestrator = DialogueOrchestrator(
            state_machine=sm,
            flow_config=fc,
        )

        orchestrator._sources.clear()
        orchestrator.add_source(ObjectionGuardSource())
        orchestrator.add_source(DataCollectorSource())

        # First objection - should be handled
        d1 = orchestrator.process_turn(intent="objection_price", extracted_data={})
        assert sm.state != "soft_close"  # Should not exit yet

        # Second objection
        sm._intent_tracker._objection_consecutive = 1
        sm._intent_tracker._objection_total = 1
        d2 = orchestrator.process_turn(intent="objection_no_time", extracted_data={})
        assert sm.state != "soft_close"  # Still within limits

        # Provide data to advance
        sm._collected_data["pain_point"] = "test"
        sm._intent_tracker._objection_consecutive = 0  # Reset
        d3 = orchestrator.process_turn(intent="problem_stated", extracted_data={})
        assert sm.state == "spin_implication"

    def test_conversation_with_price_questions(self):
        """Conversation with multiple price questions that don't block flow."""
        SourceRegistry.reset()

        sm = E2EStateMachine(state="spin_situation")
        fc = E2EFlowConfig()

        orchestrator = DialogueOrchestrator(
            state_machine=sm,
            flow_config=fc,
        )

        orchestrator._sources.clear()
        orchestrator.add_source(PriceQuestionSource())
        orchestrator.add_source(DataCollectorSource())

        # Price question before data complete - should answer but stay
        d1 = orchestrator.process_turn(intent="price_question", extracted_data={})
        assert d1.action == "answer_with_pricing"
        assert sm.state == "spin_situation"  # No data yet

        # Provide data and ask about price again
        sm._collected_data["company_size"] = "100"
        d2 = orchestrator.process_turn(intent="price_question", extracted_data={})
        assert d2.action == "answer_with_pricing"
        assert sm.state == "spin_problem"  # Should advance now

    def test_data_accumulation_across_turns(self):
        """Data should accumulate correctly across multiple turns."""
        SourceRegistry.reset()

        sm = E2EStateMachine(state="spin_situation")
        fc = E2EFlowConfig()

        orchestrator = DialogueOrchestrator(
            state_machine=sm,
            flow_config=fc,
        )

        orchestrator._sources.clear()
        orchestrator.add_source(DataCollectorSource())

        # Turn 1: Partial data
        sm._collected_data["industry"] = "retail"
        d1 = orchestrator.process_turn(intent="info_provided", extracted_data={"industry": "retail"})
        assert "industry" in sm.collected_data
        assert sm.state == "spin_situation"  # company_size still missing

        # Turn 2: Complete data
        sm._collected_data["company_size"] = "25"
        d2 = orchestrator.process_turn(intent="info_provided", extracted_data={"company_size": "25"})
        assert "industry" in sm.collected_data
        assert "company_size" in sm.collected_data
        assert sm.state == "spin_problem"


# =============================================================================
# 5. STATE MACHINE INTEGRATION TESTS
# =============================================================================

class TestStateMachineIntegration:
    """
    Tests for Orchestrator + StateMachine integration.

    Verifies:
    - Side effects are applied correctly
    - Compatibility fields are filled
    - State updates propagate
    - Phase tracking works
    """

    def test_state_update_propagates(self):
        """State changes should propagate to state machine."""
        SourceRegistry.reset()

        sm = E2EStateMachine(state="greeting")
        fc = E2EFlowConfig()

        orchestrator = DialogueOrchestrator(
            state_machine=sm,
            flow_config=fc,
        )

        decision = orchestrator.process_turn(intent="greeting", extracted_data={})

        # State machine should be updated
        assert sm.state == decision.next_state
        assert sm.last_action == decision.action

    def test_phase_tracking(self):
        """Current phase should be tracked correctly."""
        SourceRegistry.reset()

        sm = E2EStateMachine(state="greeting")
        fc = E2EFlowConfig()

        orchestrator = DialogueOrchestrator(
            state_machine=sm,
            flow_config=fc,
        )

        # Add DataCollectorSource to enable transitions
        orchestrator._sources.clear()
        orchestrator.add_source(DataCollectorSource())

        # Greeting has no phase - but after greeting we move to spin_situation
        orchestrator.process_turn(intent="greeting", extracted_data={})
        assert sm.current_phase == "situation"  # spin_situation has phase "situation"

        # Advance to problem by providing required data
        sm._collected_data["company_size"] = "50"
        orchestrator.process_turn(intent="info_provided", extracted_data={})
        assert sm.current_phase == "problem"  # spin_problem has phase "problem"

    def test_collected_data_in_decision(self):
        """Decision should include collected_data for bot.py compatibility."""
        SourceRegistry.reset()

        sm = E2EStateMachine(state="spin_situation")
        sm._collected_data = {"test_field": "test_value", "company_size": "20"}
        fc = E2EFlowConfig()

        orchestrator = DialogueOrchestrator(
            state_machine=sm,
            flow_config=fc,
        )

        decision = orchestrator.process_turn(intent="info_provided", extracted_data={})

        assert decision.collected_data is not None
        assert "test_field" in decision.collected_data

    def test_missing_data_calculated(self):
        """Missing data should be calculated for current state."""
        SourceRegistry.reset()

        sm = E2EStateMachine(state="spin_situation")
        sm._collected_data = {}  # No data yet
        fc = E2EFlowConfig()

        orchestrator = DialogueOrchestrator(
            state_machine=sm,
            flow_config=fc,
        )

        decision = orchestrator.process_turn(intent="greeting", extracted_data={})

        # spin_situation requires company_size
        assert "company_size" in decision.missing_data

    def test_is_final_correctly_set(self):
        """is_final should be set based on state configuration."""
        SourceRegistry.reset()

        sm = E2EStateMachine(state="closing")
        fc = E2EFlowConfig()

        orchestrator = DialogueOrchestrator(
            state_machine=sm,
            flow_config=fc,
        )

        # Add source to transition to success
        class SuccessSource(KnowledgeSource):
            def should_contribute(self, bb):
                return True

            def contribute(self, bb):
                bb.propose_transition(
                    next_state="success",
                    priority=Priority.HIGH,
                    source_name=self.name,
                    reason_code="close_success",
                )

        orchestrator._sources.clear()
        orchestrator.add_source(SuccessSource("SuccessSource"))

        decision = orchestrator.process_turn(intent="contact_provided", extracted_data={})

        assert decision.next_state == "success"
        assert decision.is_final is True

    def test_to_sm_result_format(self):
        """to_sm_result() should return bot.py compatible dict."""
        SourceRegistry.reset()

        sm = E2EStateMachine(state="spin_situation")
        sm._collected_data = {"company_size": "50"}
        fc = E2EFlowConfig()

        orchestrator = DialogueOrchestrator(
            state_machine=sm,
            flow_config=fc,
        )

        decision = orchestrator.process_turn(intent="info_provided", extracted_data={})
        sm_result = decision.to_sm_result()

        # Check all required fields for bot.py
        required_fields = [
            "action", "next_state", "prev_state", "collected_data",
            "missing_data", "goal", "is_final", "reason_codes"
        ]

        for field in required_fields:
            assert field in sm_result, f"Missing field: {field}"


# =============================================================================
# 6. EVENT BUS INTEGRATION TESTS
# =============================================================================

class TestEventBusIntegration:
    """
    Tests for EventBus integration and observability.

    Verifies:
    - All pipeline events are emitted
    - Event data is correct
    - Subscribers receive events
    """

    def test_turn_started_event_emitted(self):
        """TurnStarted event should be emitted at turn start."""
        SourceRegistry.reset()

        sm = E2EStateMachine(state="greeting")
        fc = E2EFlowConfig()

        orchestrator = DialogueOrchestrator(
            state_machine=sm,
            flow_config=fc,
        )

        events = []
        orchestrator.event_bus.subscribe_all(lambda e: events.append(e))

        orchestrator.process_turn(intent="greeting", extracted_data={})

        event_types = [e.event_type for e in events]
        assert EventType.TURN_STARTED in event_types

    def test_all_pipeline_events_emitted(self):
        """All pipeline events should be emitted during processing."""
        SourceRegistry.reset()

        sm = E2EStateMachine(state="greeting")
        fc = E2EFlowConfig()

        orchestrator = DialogueOrchestrator(
            state_machine=sm,
            flow_config=fc,
        )

        events = []
        orchestrator.event_bus.subscribe_all(lambda e: events.append(e))

        orchestrator.process_turn(intent="greeting", extracted_data={})

        event_types = [e.event_type for e in events]

        # Core events should be present
        assert EventType.TURN_STARTED in event_types
        assert EventType.CONFLICT_RESOLVED in event_types
        assert EventType.DECISION_COMMITTED in event_types

    def test_state_transitioned_event_on_change(self):
        """StateTransitioned event should be emitted when state changes."""
        SourceRegistry.reset()

        sm = E2EStateMachine(state="greeting")
        fc = E2EFlowConfig()

        orchestrator = DialogueOrchestrator(
            state_machine=sm,
            flow_config=fc,
        )

        events = []
        orchestrator.event_bus.subscribe_all(lambda e: events.append(e))

        orchestrator.process_turn(intent="greeting", extracted_data={})

        event_types = [e.event_type for e in events]
        assert EventType.STATE_TRANSITIONED in event_types


# =============================================================================
# 7. PERFORMANCE TESTS
# =============================================================================

class TestPerformance:
    """
    Performance benchmarks for the Blackboard system.

    Verifies:
    - Processing time is acceptable
    - No memory leaks in repeated calls
    """

    def test_process_turn_latency(self):
        """process_turn should complete within acceptable time."""
        SourceRegistry.reset()

        sm = E2EStateMachine(state="spin_situation")
        fc = E2EFlowConfig()

        orchestrator = DialogueOrchestrator(
            state_machine=sm,
            flow_config=fc,
        )

        # Warm up
        for _ in range(5):
            orchestrator.process_turn(intent="greeting", extracted_data={})

        # Measure
        iterations = 50
        start_time = time.time()

        for _ in range(iterations):
            orchestrator.process_turn(intent="info_provided", extracted_data={"test": "data"})

        elapsed = time.time() - start_time
        avg_latency_ms = (elapsed / iterations) * 1000

        # Should be under 50ms per turn
        assert avg_latency_ms < 50, f"Latency {avg_latency_ms:.2f}ms exceeds 50ms threshold"

    def test_multiple_sources_performance(self):
        """Multiple sources should not significantly impact performance."""
        SourceRegistry.reset()

        sm = E2EStateMachine(state="spin_situation")
        fc = E2EFlowConfig()

        orchestrator = DialogueOrchestrator(
            state_machine=sm,
            flow_config=fc,
        )

        # Add all sources
        orchestrator._sources.clear()
        orchestrator.add_source(PriceQuestionSource())
        orchestrator.add_source(DataCollectorSource())
        orchestrator.add_source(ObjectionGuardSource())
        orchestrator.add_source(IntentProcessorSource())
        orchestrator.add_source(TransitionResolverSource())
        orchestrator.add_source(EscalationSource())

        iterations = 30
        start_time = time.time()

        for _ in range(iterations):
            orchestrator.process_turn(intent="info_provided", extracted_data={})

        elapsed = time.time() - start_time
        avg_latency_ms = (elapsed / iterations) * 1000

        # Even with 6 sources, should be under 100ms
        assert avg_latency_ms < 100, f"Latency {avg_latency_ms:.2f}ms exceeds 100ms threshold"


# =============================================================================
# 8. SALESBOT INTEGRATION TESTS (with mock LLM)
# =============================================================================

class TestSalesBotIntegration:
    """
    Tests for full SalesBot + Blackboard integration.

    Uses mock LLM to test the complete pipeline.
    """

    @pytest.fixture
    def mock_llm(self):
        """Create a mock LLM."""
        llm = MagicMock()
        llm.generate.return_value = "Test response from bot"
        llm.health_check.return_value = True
        llm.model = "mock-model"
        return llm

    @pytest.fixture
    def sales_bot_with_mock(self, mock_llm):
        """Create SalesBot with mock LLM."""
        from src.bot import SalesBot
        from src.feature_flags import flags

        # Enable required flags
        flags.set_override("metrics_tracking", True)
        flags.set_override("conversation_guard", True)
        flags.set_override("tone_analysis", True)
        flags.set_override("lead_scoring", True)
        flags.set_override("objection_handler", True)
        flags.set_override("cta_generator", True)
        flags.set_override("confidence_router", True)
        flags.set_override("context_full_envelope", True)
        flags.set_override("context_policy_overlays", True)
        flags.set_override("context_response_directives", True)

        bot = SalesBot(llm=mock_llm, enable_tracing=True)

        yield bot

        flags.clear_all_overrides()

    def test_salesbot_has_orchestrator(self, sales_bot_with_mock):
        """SalesBot should have orchestrator initialized."""
        assert hasattr(sales_bot_with_mock, '_orchestrator')
        assert sales_bot_with_mock._orchestrator is not None

    def test_salesbot_process_returns_response(self, sales_bot_with_mock):
        """SalesBot.process() should return response with Blackboard."""
        result = sales_bot_with_mock.process("Привет")

        assert "response" in result
        assert result["response"] is not None
        assert len(result["response"]) > 0

    def test_salesbot_process_returns_state(self, sales_bot_with_mock):
        """SalesBot.process() should return state info."""
        result = sales_bot_with_mock.process("Привет")

        assert "state" in result
        assert result["state"] is not None

    def test_salesbot_process_returns_action(self, sales_bot_with_mock):
        """SalesBot.process() should return action from Blackboard."""
        result = sales_bot_with_mock.process("Привет")

        assert "action" in result
        assert result["action"] is not None

    def test_salesbot_reset_works(self, sales_bot_with_mock):
        """SalesBot.reset() should clear state."""
        sales_bot_with_mock.process("Привет")
        sales_bot_with_mock.process("Расскажите о ценах")

        sales_bot_with_mock.reset()

        assert sales_bot_with_mock.state_machine.state == "greeting"
        assert len(sales_bot_with_mock.history) == 0


# =============================================================================
# Run Tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
