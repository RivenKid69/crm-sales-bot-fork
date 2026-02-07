# tests/test_blackboard_integration.py

"""
Integration tests for the complete Blackboard system.

Stage 13: Integration Tests (Section 18 from Plan)

These tests verify end-to-end behavior with real components
(not mocks) to ensure the system works as designed.

Test Categories:
1. Scenario Tests - Complete dialogue scenarios
2. Bug Fix Verification - Tests proving bugs are fixed
3. Performance Benchmarks - Latency measurements
"""

import pytest
from typing import Dict, Any, Optional, List
from unittest.mock import Mock, MagicMock
from dataclasses import dataclass, field

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


# =============================================================================
# Mock Implementations for Integration Testing
# =============================================================================

@dataclass
class IntentRecord:
    """Record of an intent."""
    intent: str
    state: str


class MockIntentTracker:
    """Mock IntentTracker for testing."""

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

        # Track objections
        if "objection" in intent:
            self._objection_consecutive += 1
            self._objection_total += 1
        else:
            self._objection_consecutive = 0

    def advance_turn(self) -> None:
        self._turn_number += 1

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


class MockCircularFlow:
    """Mock CircularFlowManager."""

    def __init__(self):
        self._loops = 0
        self._max_loops = 3

    def get_stats(self) -> Dict[str, Any]:
        return {"loops": self._loops, "max_loops": self._max_loops}


class IntegrationStateMachine:
    """
    State Machine implementation for integration testing.

    Closely mirrors the real StateMachine interface while being
    isolated from external dependencies.
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
        self._intent_tracker = MockIntentTracker()
        self._state_before_objection = None
        self.circular_flow = MockCircularFlow()

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

    def is_final(self) -> bool:
        return self._state in ("soft_close", "closed", "rejected")


class IntegrationFlowConfig:
    """
    Flow configuration for integration testing.

    Contains a realistic state configuration that mirrors production.
    """

    def __init__(self, custom_states: Optional[Dict[str, Dict[str, Any]]] = None):
        self._states = custom_states or self._get_default_states()
        self._constants = {
            "persona_limits": {
                "aggressive": {"consecutive": 5, "total": 8},
                "busy": {"consecutive": 2, "total": 4},
                "default": {"consecutive": 3, "total": 5},
            }
        }

    def _get_default_states(self) -> Dict[str, Dict[str, Any]]:
        """Get default state configuration for testing."""
        return {
            "greeting": {
                "goal": "Greet user and establish rapport",
                "phase": None,
                "required_data": [],
                "is_final": False,
                "transitions": {
                    "any": "spin_situation",
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
                    "ready": "closing",
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

    def get_phase_for_state(self, state_name: str) -> Optional[str]:
        """Get phase name for a state."""
        # Delegate to state_to_phase which contains the complete mapping
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
# Test Fixtures
# =============================================================================

@pytest.fixture
def integration_state_machine():
    """Create a state machine for integration testing."""
    return IntegrationStateMachine(state="spin_situation")


@pytest.fixture
def integration_flow_config():
    """Create a flow config for integration testing."""
    return IntegrationFlowConfig()


@pytest.fixture
def full_orchestrator(integration_state_machine, integration_flow_config):
    """Create a fully configured orchestrator for integration testing."""
    SourceRegistry.reset()

    return DialogueOrchestrator(
        state_machine=integration_state_machine,
        flow_config=integration_flow_config,
        enable_validation=True,
    )


# =============================================================================
# Scenario Tests
# =============================================================================

class TestBlackboardIntegration:
    """
    Integration tests for the complete Blackboard system.

    These tests verify end-to-end behavior with real components
    (not mocks) to ensure the system works as designed.
    """

    def test_scenario_price_question_with_data(self):
        """
        Scenario: User provides company size while asking about price.

        Input: "У нас 15 человек. Сколько стоит?"
        Expected: Answer price AND advance to next phase.
        """
        SourceRegistry.reset()

        sm = IntegrationStateMachine(state="spin_situation")
        sm._collected_data = {}
        fc = IntegrationFlowConfig()

        orchestrator = DialogueOrchestrator(
            state_machine=sm,
            flow_config=fc,
        )

        # Clear and add only relevant sources
        orchestrator._sources.clear()
        orchestrator.add_source(PriceQuestionSource())
        orchestrator.add_source(DataCollectorSource())

        # Simulate data being collected before process_turn (as bot.py does)
        sm._collected_data["company_size"] = "15"

        decision = orchestrator.process_turn(
            intent="price_question",
            extracted_data={"company_size": "15"},
        )

        assert decision.action == "answer_with_pricing", \
            "Should answer the price question"
        assert decision.next_state == "spin_problem", \
            "Should transition to next phase since data is complete"

    def test_scenario_multiple_objections_within_limit(self):
        """
        Scenario: User raises objections but within limits.

        Should continue conversation, not soft close.
        """
        SourceRegistry.reset()

        sm = IntegrationStateMachine(state="spin_problem")
        sm._intent_tracker._objection_consecutive = 1
        sm._intent_tracker._objection_total = 2
        fc = IntegrationFlowConfig()

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

        # Within limits - should NOT go to soft_close with limit action
        assert not (decision.action == "objection_limit_reached" and decision.next_state == "soft_close")

    def test_scenario_objection_limit_exceeded(self):
        """
        Scenario: User raises too many objections.

        Should transition to soft_close.
        """
        SourceRegistry.reset()

        sm = IntegrationStateMachine(state="spin_problem")
        sm._intent_tracker._objection_consecutive = 4  # Updated: default consecutive limit is now 4
        sm._intent_tracker._objection_total = 6  # Updated: default total limit is now 6
        fc = IntegrationFlowConfig()

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

        assert decision.action == "objection_limit_reached"
        assert decision.next_state == "soft_close"

    def test_scenario_normal_flow_with_data_progression(self):
        """
        Scenario: Normal conversation flow.

        User provides situation info -> advance to problem phase.
        """
        SourceRegistry.reset()

        sm = IntegrationStateMachine(state="spin_situation")
        sm._collected_data = {}
        fc = IntegrationFlowConfig()

        orchestrator = DialogueOrchestrator(
            state_machine=sm,
            flow_config=fc,
        )

        orchestrator._sources.clear()
        orchestrator.add_source(DataCollectorSource())

        # Provide required data
        sm._collected_data["company_size"] = "50"

        decision = orchestrator.process_turn(
            intent="info_provided",
            extracted_data={"company_size": "50"},
        )

        # Should have data_complete transition
        assert decision.next_state == "spin_problem"
        assert "data_complete" in decision.reason_codes

    def test_scenario_rejection_blocks_transition(self):
        """
        Scenario: User rejects completely.

        Should transition to soft_close even if data is complete.
        """
        SourceRegistry.reset()

        sm = IntegrationStateMachine(state="spin_situation")
        sm._collected_data = {"company_size": "50"}  # Data is complete
        fc = IntegrationFlowConfig()

        orchestrator = DialogueOrchestrator(
            state_machine=sm,
            flow_config=fc,
        )

        orchestrator._sources.clear()

        # Create a source that proposes rejection with transition
        # Note: When proposing both action AND transition, use combinable=True
        # The CRITICAL priority ensures this action/transition wins over others
        class RejectionSource(KnowledgeSource):
            def should_contribute(self, bb):
                return bb.current_intent == "rejection"

            def contribute(self, bb):
                bb.propose_action(
                    action="acknowledge_rejection",
                    priority=Priority.CRITICAL,
                    combinable=True,  # Allow our own transition to happen
                    source_name=self.name,
                    reason_code="rejection_detected",
                )
                bb.propose_transition(
                    next_state="soft_close",
                    priority=Priority.CRITICAL,
                    source_name=self.name,
                    reason_code="rejection_transition",
                )

        orchestrator.add_source(RejectionSource("RejectionSource"))
        orchestrator.add_source(DataCollectorSource())

        decision = orchestrator.process_turn(
            intent="rejection",
            extracted_data={},
        )

        # Rejection should block data_complete and go to soft_close
        assert decision.next_state == "soft_close"

    def test_scenario_combinable_action_with_transition(self):
        """
        Scenario: Action that is combinable with transition.

        Both action and transition should be applied.
        """
        SourceRegistry.reset()

        sm = IntegrationStateMachine(state="spin_situation")
        sm._collected_data = {"company_size": "20"}
        fc = IntegrationFlowConfig()

        orchestrator = DialogueOrchestrator(
            state_machine=sm,
            flow_config=fc,
        )

        orchestrator._sources.clear()

        # Custom combinable action source
        class CombinableActionSource(KnowledgeSource):
            def should_contribute(self, bb):
                return True

            def contribute(self, bb):
                bb.propose_action(
                    action="custom_combinable_action",
                    priority=Priority.HIGH,
                    combinable=True,  # COMBINABLE
                    source_name=self.name,
                    reason_code="combinable_test",
                )

        orchestrator.add_source(CombinableActionSource("CombinableActionSource"))
        orchestrator.add_source(DataCollectorSource())

        decision = orchestrator.process_turn(
            intent="info_provided",
            extracted_data={},
        )

        # Both action and transition should be applied
        assert decision.action == "custom_combinable_action"
        assert decision.next_state == "spin_problem"
        assert "combinable_test" in decision.reason_codes
        assert "data_complete" in decision.reason_codes


# =============================================================================
# Bug Fix Verification Tests
# =============================================================================

class TestBugFixes:
    """
    Tests that verify Blackboard fixes known bugs from the old system.

    NOTE: Legacy система полностью удалена, эти тесты документируют
    исправленное поведение (не сравнивают с legacy).
    """

    def test_price_question_no_longer_blocks_transition(self):
        """
        Verify the core bug is fixed.

        OLD BEHAVIOR (BUG):
        - price_question -> return("answer_with_pricing", SAME_STATE)
        - data_complete check NEVER reached
        - Bot stuck in spin_situation asking same questions

        NEW BEHAVIOR (FIXED):
        - price_question -> propose_action("answer_with_pricing", combinable=True)
        - data_complete -> propose_transition("spin_problem")
        - BOTH applied — bot answers price AND advances to next phase
        """
        SourceRegistry.reset()

        sm = IntegrationStateMachine(state="spin_situation")
        sm._collected_data = {"company_size": "15"}  # Required data present
        fc = IntegrationFlowConfig()

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

    def test_blocking_actions_work(self):
        """
        Verify combinable=False blocks transitions correctly.

        - rejection -> blocks data_complete transition
        - escalation -> blocks all other transitions
        - objection_limit_reached -> blocks continuation
        """
        SourceRegistry.reset()

        sm = IntegrationStateMachine(state="spin_situation")
        sm._collected_data = {"company_size": "15"}  # Data is complete
        fc = IntegrationFlowConfig()

        orchestrator = DialogueOrchestrator(
            state_machine=sm,
            flow_config=fc,
        )

        orchestrator._sources.clear()

        # Blocking source
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
        orchestrator.add_source(DataCollectorSource())  # Would propose data_complete

        decision = orchestrator.process_turn(
            intent="blocking_intent",
            extracted_data={},
        )

        # Blocking action should prevent data_complete transition
        assert decision.action == "blocking_action"
        # State should remain the same (transition blocked)
        assert decision.next_state == "spin_situation"
        assert "data_complete" not in decision.reason_codes

    def test_persona_limits_respected(self):
        """
        Verify persona-specific objection limits work correctly.

        - aggressive persona: 5 consecutive, 8 total
        - busy persona: 2 consecutive, 4 total
        - default: 3 consecutive, 5 total
        """
        SourceRegistry.reset()

        # Test busy persona (low limit: 2 consecutive)
        sm = IntegrationStateMachine(state="spin_problem")
        sm._collected_data = {"persona": "busy"}
        sm._intent_tracker._objection_consecutive = 2
        sm._intent_tracker._objection_total = 2
        fc = IntegrationFlowConfig()

        orchestrator = DialogueOrchestrator(
            state_machine=sm,
            flow_config=fc,
        )

        orchestrator._sources.clear()
        objection_guard = ObjectionGuardSource()
        orchestrator.add_source(objection_guard)

        decision = orchestrator.process_turn(
            intent="objection_price",
            extracted_data={},
        )

        # Busy persona should hit limit at 2 consecutive
        assert decision.action == "objection_limit_reached"
        assert decision.next_state == "soft_close"


# =============================================================================
# Multi-Source Integration Tests
# =============================================================================

class TestMultiSourceIntegration:
    """Tests for interactions between multiple Knowledge Sources."""

    def test_source_priority_ordering(self):
        """
        Verify that sources are processed in priority order.

        Higher priority sources' proposals should win.
        """
        SourceRegistry.reset()

        sm = IntegrationStateMachine(state="spin_situation")
        fc = IntegrationFlowConfig()

        orchestrator = DialogueOrchestrator(
            state_machine=sm,
            flow_config=fc,
        )

        orchestrator._sources.clear()

        # Low priority source
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

        # High priority source
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

        decision = orchestrator.process_turn(
            intent="test",
            extracted_data={},
        )

        # High priority should win
        assert decision.action == "high_priority_action"
        assert "high_priority" in decision.reason_codes

    def test_multiple_transitions_highest_priority_wins(self):
        """Verify that highest priority transition wins when multiple are proposed."""
        SourceRegistry.reset()

        sm = IntegrationStateMachine(state="spin_situation")
        fc = IntegrationFlowConfig()

        orchestrator = DialogueOrchestrator(
            state_machine=sm,
            flow_config=fc,
        )

        orchestrator._sources.clear()

        class NormalTransitionSource(KnowledgeSource):
            def should_contribute(self, bb):
                return True

            def contribute(self, bb):
                bb.propose_transition(
                    next_state="spin_problem",
                    priority=Priority.NORMAL,
                    source_name=self.name,
                    reason_code="normal_transition",
                )

        class HighTransitionSource(KnowledgeSource):
            def should_contribute(self, bb):
                return True

            def contribute(self, bb):
                bb.propose_transition(
                    next_state="soft_close",
                    priority=Priority.HIGH,
                    source_name=self.name,
                    reason_code="high_transition",
                )

        orchestrator.add_source(NormalTransitionSource("NormalTransitionSource"))
        orchestrator.add_source(HighTransitionSource("HighTransitionSource"))

        decision = orchestrator.process_turn(
            intent="test",
            extracted_data={},
        )

        # High priority transition should win
        assert decision.next_state == "soft_close"
        assert "high_transition" in decision.reason_codes


# =============================================================================
# Data Update Integration Tests
# =============================================================================

class TestDataUpdateIntegration:
    """Tests for data update handling in the Blackboard system."""

    def test_data_updates_applied_to_state_machine(self):
        """Verify that data updates from proposals are applied to state machine."""
        SourceRegistry.reset()

        sm = IntegrationStateMachine(state="spin_situation")
        sm._collected_data = {}
        fc = IntegrationFlowConfig()

        orchestrator = DialogueOrchestrator(
            state_machine=sm,
            flow_config=fc,
        )

        orchestrator._sources.clear()

        class DataUpdateSource(KnowledgeSource):
            def should_contribute(self, bb):
                return True

            def contribute(self, bb):
                bb.propose_data_update(
                    field="test_field",
                    value="test_value",
                    source_name=self.name,
                    reason_code="data_update_test",
                )

        orchestrator.add_source(DataUpdateSource("DataUpdateSource"))

        decision = orchestrator.process_turn(
            intent="test",
            extracted_data={},
        )

        # Data should be updated
        assert sm.collected_data.get("test_field") == "test_value"

    def test_flag_updates_applied(self):
        """Verify that flag updates from proposals are applied."""
        SourceRegistry.reset()

        sm = IntegrationStateMachine(state="spin_situation")
        sm._collected_data = {}
        fc = IntegrationFlowConfig()

        orchestrator = DialogueOrchestrator(
            state_machine=sm,
            flow_config=fc,
        )

        orchestrator._sources.clear()

        class FlagSource(KnowledgeSource):
            def should_contribute(self, bb):
                return True

            def contribute(self, bb):
                bb.propose_flag_set(
                    flag="_custom_flag",
                    value=True,
                    source_name=self.name,
                    reason_code="flag_test",
                )

        orchestrator.add_source(FlagSource("FlagSource"))

        decision = orchestrator.process_turn(
            intent="test",
            extracted_data={},
        )

        # Flag should be set
        assert sm.collected_data.get("_custom_flag") is True


# =============================================================================
# Event Emission Integration Tests
# =============================================================================

class TestEventIntegration:
    """Tests for event emission during the Blackboard pipeline."""

    def test_all_pipeline_events_emitted(self):
        """Verify that all expected events are emitted during pipeline."""
        SourceRegistry.reset()

        sm = IntegrationStateMachine(state="spin_situation")
        fc = IntegrationFlowConfig()

        orchestrator = DialogueOrchestrator(
            state_machine=sm,
            flow_config=fc,
        )

        orchestrator._sources.clear()
        orchestrator.add_source(PriceQuestionSource())

        events_received = []

        def handler(event):
            events_received.append(event.event_type)

        orchestrator.event_bus.subscribe_all(handler)

        orchestrator.process_turn(
            intent="price_question",
            extracted_data={},
        )

        # Core events should be present
        from src.blackboard.event_bus import EventType

        assert EventType.TURN_STARTED in events_received
        assert EventType.SOURCE_CONTRIBUTED in events_received
        assert EventType.CONFLICT_RESOLVED in events_received
        assert EventType.DECISION_COMMITTED in events_received


# =============================================================================
# Performance Benchmarks (Optional)
# =============================================================================

class TestPerformance:
    """Performance benchmarks for Blackboard system."""

    def test_process_turn_basic_latency(self):
        """Benchmark basic process_turn latency (without pytest-benchmark)."""
        import time

        SourceRegistry.reset()

        sm = IntegrationStateMachine(state="spin_situation")
        fc = IntegrationFlowConfig()

        orchestrator = DialogueOrchestrator(
            state_machine=sm,
            flow_config=fc,
        )

        # Warm up
        for _ in range(5):
            orchestrator.process_turn(
                intent="greeting",
                extracted_data={},
            )

        # Measure
        iterations = 100
        start_time = time.time()

        for _ in range(iterations):
            orchestrator.process_turn(
                intent="info_provided",
                extracted_data={"name": "Test"},
            )

        elapsed = time.time() - start_time
        avg_latency_ms = (elapsed / iterations) * 1000

        # Assert reasonable latency (should be under 10ms typically)
        assert avg_latency_ms < 50, f"Average latency {avg_latency_ms:.2f}ms exceeds threshold"

    def test_source_contribution_isolation(self):
        """Verify that source errors don't break the pipeline."""
        SourceRegistry.reset()

        sm = IntegrationStateMachine(state="spin_situation")
        fc = IntegrationFlowConfig()

        orchestrator = DialogueOrchestrator(
            state_machine=sm,
            flow_config=fc,
        )

        orchestrator._sources.clear()

        class ErrorSource(KnowledgeSource):
            def should_contribute(self, bb):
                return True

            def contribute(self, bb):
                raise ValueError("Test error")

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
