# tests/test_blackboard_orchestrator.py

"""
Tests for Blackboard Stage 10: DialogueOrchestrator.

These tests verify:
1. DialogueOrchestrator initialization
2. process_turn() pipeline coordination
3. _apply_side_effects() for bot.py compatibility
4. add_source(), remove_source(), get_source() methods
5. create_orchestrator() factory function
6. Event emission during pipeline
7. Error handling and fallback decisions
8. Integration with Knowledge Sources
9. Compatibility with bot.py expected output format
"""

import pytest
from typing import Dict, Any, Optional, List
from unittest.mock import Mock, MagicMock, patch
from dataclasses import dataclass, field

from src.blackboard.orchestrator import DialogueOrchestrator, create_orchestrator
from src.blackboard.blackboard import DialogueBlackboard
from src.blackboard.knowledge_source import KnowledgeSource
from src.blackboard.models import Proposal, ResolvedDecision
from src.blackboard.enums import Priority, ProposalType
from src.blackboard.event_bus import (
    DialogueEventBus,
    EventType,
    TurnStartedEvent,
    DecisionCommittedEvent,
)
from src.blackboard.protocols import TenantConfig, DEFAULT_TENANT
from src.blackboard.source_registry import SourceRegistry


# =============================================================================
# Mock Implementations for Testing
# =============================================================================

class MockStateMachine:
    """Mock StateMachine implementing IStateMachine protocol."""

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

    def is_final(self) -> bool:
        return self._state in ("closed", "rejected")


class MockCircularFlow:
    """Mock CircularFlowManager."""

    def get_stats(self) -> Dict[str, Any]:
        return {"loops": 0, "max_loops": 3}


@dataclass
class IntentRecord:
    """Record of an intent."""
    intent: str
    state: str


class MockIntentTracker:
    """Mock IntentTracker implementing IIntentTracker protocol."""

    def __init__(self, turn_number: int = 0):
        self._turn_number = turn_number
        self._prev_intent = None
        self._intents: List[IntentRecord] = []
        self._objection_consecutive = 0
        self._objection_total = 0
        self._category_totals: Dict[str, int] = {}

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

        # Track objections
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
        return self._category_totals.get(category, 0)

    def get_intents_by_category(self, category: str) -> List[IntentRecord]:
        return [r for r in self._intents if category in r.intent]


class MockFlowConfig:
    """Mock FlowConfig implementing IFlowConfig protocol."""

    def __init__(
        self,
        states: Optional[Dict[str, Dict[str, Any]]] = None,
        constants: Optional[Dict[str, Any]] = None
    ):
        self._states = states or {
            "greeting": {
                "goal": "Greet user",
                "phase": None,
                "transitions": {"any": "spin_situation"},
            },
            "spin_situation": {
                "goal": "Gather situation",
                "phase": "situation",
                "required_data": ["company_name"],
                "transitions": {"data_complete": "spin_problem"},
            },
            "spin_problem": {
                "goal": "Identify problems",
                "phase": "problem",
                "required_data": ["problem"],
            },
            "soft_close": {
                "goal": "Close conversation",
                "is_final": True,
            },
            "_limits": {
                "max_consecutive_objections": 3,
                "max_total_objections": 5
            },
        }
        self._constants = constants or {}

    @property
    def states(self) -> Dict[str, Dict[str, Any]]:
        return self._states

    @property
    def constants(self) -> Dict[str, Any]:
        return self._constants

    def to_dict(self) -> Dict[str, Any]:
        return {"states": self._states}

    def get_state_on_enter_flags(self, state_name: str) -> Dict[str, Any]:
        """Get on_enter flags for a state."""
        state_config = self._states.get(state_name, {})
        on_enter = state_config.get("on_enter", {})
        if isinstance(on_enter, dict):
            return on_enter.get("set_flags", {})
        return {}


class SimpleTestSource(KnowledgeSource):
    """Simple test source that proposes a specific action."""

    def __init__(self, name: str = "SimpleTestSource", action: str = "test_action"):
        super().__init__(name=name)
        self._action = action

    def should_contribute(self, blackboard: DialogueBlackboard) -> bool:
        return True

    def contribute(self, blackboard: DialogueBlackboard) -> None:
        blackboard.propose_action(
            action=self._action,
            priority=Priority.NORMAL,
            source_name=self.name,
            reason_code=f"test_{self._action}",
        )


class TransitionSource(KnowledgeSource):
    """Test source that proposes a transition."""

    def __init__(self, name: str = "TransitionSource", next_state: str = "spin_problem"):
        super().__init__(name=name)
        self._next_state = next_state

    def should_contribute(self, blackboard: DialogueBlackboard) -> bool:
        return True

    def contribute(self, blackboard: DialogueBlackboard) -> None:
        blackboard.propose_transition(
            next_state=self._next_state,
            priority=Priority.NORMAL,
            source_name=self.name,
            reason_code=f"transition_to_{self._next_state}",
        )


class ErrorSource(KnowledgeSource):
    """Test source that raises an error."""

    def __init__(self, name: str = "ErrorSource"):
        super().__init__(name=name)

    def should_contribute(self, blackboard: DialogueBlackboard) -> bool:
        return True

    def contribute(self, blackboard: DialogueBlackboard) -> None:
        raise RuntimeError("Test error from ErrorSource")


class ConditionalSource(KnowledgeSource):
    """Test source that only contributes based on condition."""

    def __init__(self, name: str = "ConditionalSource", should_contribute_value: bool = False):
        super().__init__(name=name)
        self._should_contribute_value = should_contribute_value

    def should_contribute(self, blackboard: DialogueBlackboard) -> bool:
        return self._should_contribute_value

    def contribute(self, blackboard: DialogueBlackboard) -> None:
        blackboard.propose_action(
            action="conditional_action",
            priority=Priority.HIGH,
            source_name=self.name,
            reason_code="conditional_triggered",
        )


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_state_machine():
    """Create a mock state machine."""
    return MockStateMachine(state="spin_situation")


@pytest.fixture
def mock_flow_config():
    """Create a mock flow config."""
    return MockFlowConfig()


@pytest.fixture
def event_bus():
    """Create an event bus for testing."""
    return DialogueEventBus()


@pytest.fixture
def orchestrator_no_sources(mock_state_machine, mock_flow_config, event_bus):
    """Create an orchestrator with no sources (for isolated testing)."""
    # Clear registry to avoid interference from other sources
    SourceRegistry.reset()

    orch = DialogueOrchestrator(
        state_machine=mock_state_machine,
        flow_config=mock_flow_config,
        event_bus=event_bus,
        enable_validation=True,
    )
    # Remove all sources for isolated testing
    orch._sources.clear()
    return orch


# =============================================================================
# Test DialogueOrchestrator Initialization
# =============================================================================

class TestOrchestratorInit:
    """Test DialogueOrchestrator initialization."""

    def test_init_basic(self, mock_state_machine, mock_flow_config):
        """Test basic initialization."""
        SourceRegistry.reset()

        orch = DialogueOrchestrator(
            state_machine=mock_state_machine,
            flow_config=mock_flow_config,
        )

        assert orch._state_machine is mock_state_machine
        assert orch._flow_config is mock_flow_config
        assert orch._enable_validation is True
        assert isinstance(orch._blackboard, DialogueBlackboard)
        assert isinstance(orch._event_bus, DialogueEventBus)

    def test_init_with_custom_event_bus(self, mock_state_machine, mock_flow_config, event_bus):
        """Test initialization with custom event bus."""
        SourceRegistry.reset()

        orch = DialogueOrchestrator(
            state_machine=mock_state_machine,
            flow_config=mock_flow_config,
            event_bus=event_bus,
        )

        assert orch._event_bus is event_bus

    def test_init_with_tenant_config(self, mock_state_machine, mock_flow_config):
        """Test initialization with tenant configuration."""
        SourceRegistry.reset()

        tenant = TenantConfig(
            tenant_id="test_tenant",
            bot_name="Test Bot",
            tone="friendly",
        )

        orch = DialogueOrchestrator(
            state_machine=mock_state_machine,
            flow_config=mock_flow_config,
            tenant_config=tenant,
        )

        assert orch._tenant_config.tenant_id == "test_tenant"
        assert orch._blackboard.tenant_id == "test_tenant"

    def test_init_default_tenant(self, mock_state_machine, mock_flow_config):
        """Test that DEFAULT_TENANT is used when no tenant provided."""
        SourceRegistry.reset()

        orch = DialogueOrchestrator(
            state_machine=mock_state_machine,
            flow_config=mock_flow_config,
        )

        assert orch._tenant_config.tenant_id == "default"


# =============================================================================
# Test Properties
# =============================================================================

class TestOrchestratorProperties:
    """Test DialogueOrchestrator properties."""

    def test_blackboard_property(self, orchestrator_no_sources):
        """Test blackboard property returns blackboard instance."""
        assert isinstance(orchestrator_no_sources.blackboard, DialogueBlackboard)

    def test_event_bus_property(self, orchestrator_no_sources):
        """Test event_bus property returns event bus instance."""
        assert isinstance(orchestrator_no_sources.event_bus, DialogueEventBus)

    def test_sources_property(self, orchestrator_no_sources):
        """Test sources property returns list of sources."""
        assert isinstance(orchestrator_no_sources.sources, list)
        # Initially empty after clearing
        assert len(orchestrator_no_sources.sources) == 0


# =============================================================================
# Test Source Management
# =============================================================================

class TestSourceManagement:
    """Test add_source, remove_source, get_source methods."""

    def test_add_source(self, orchestrator_no_sources):
        """Test adding a knowledge source."""
        source = SimpleTestSource(name="TestSource")
        orchestrator_no_sources.add_source(source)

        assert len(orchestrator_no_sources.sources) == 1
        assert orchestrator_no_sources.sources[0].name == "TestSource"

    def test_remove_source(self, orchestrator_no_sources):
        """Test removing a knowledge source."""
        source = SimpleTestSource(name="TestSource")
        orchestrator_no_sources.add_source(source)

        result = orchestrator_no_sources.remove_source("TestSource")
        assert result is True
        assert len(orchestrator_no_sources.sources) == 0

    def test_remove_source_not_found(self, orchestrator_no_sources):
        """Test removing a non-existent source."""
        result = orchestrator_no_sources.remove_source("NonExistent")
        assert result is False

    def test_get_source(self, orchestrator_no_sources):
        """Test getting a source by name."""
        source = SimpleTestSource(name="TestSource")
        orchestrator_no_sources.add_source(source)

        found = orchestrator_no_sources.get_source("TestSource")
        assert found is source

    def test_get_source_not_found(self, orchestrator_no_sources):
        """Test getting a non-existent source."""
        found = orchestrator_no_sources.get_source("NonExistent")
        assert found is None

    def test_add_multiple_sources(self, orchestrator_no_sources):
        """Test adding multiple sources."""
        source1 = SimpleTestSource(name="Source1")
        source2 = SimpleTestSource(name="Source2")

        orchestrator_no_sources.add_source(source1)
        orchestrator_no_sources.add_source(source2)

        assert len(orchestrator_no_sources.sources) == 2


# =============================================================================
# Test process_turn()
# =============================================================================

class TestProcessTurn:
    """Test process_turn() pipeline."""

    def test_process_turn_basic(self, orchestrator_no_sources):
        """Test basic turn processing with no sources."""
        decision = orchestrator_no_sources.process_turn(
            intent="greeting",
            extracted_data={"name": "John"},
        )

        assert isinstance(decision, ResolvedDecision)
        # With no proposals, should use default action and stay in current state
        assert decision.action == "continue"
        assert decision.next_state == "spin_situation"

    def test_process_turn_with_source(self, orchestrator_no_sources):
        """Test turn processing with a source."""
        source = SimpleTestSource(action="greet_user")
        orchestrator_no_sources.add_source(source)

        decision = orchestrator_no_sources.process_turn(
            intent="greeting",
            extracted_data={},
        )

        assert decision.action == "greet_user"
        assert "test_greet_user" in decision.reason_codes

    def test_process_turn_with_transition(self, orchestrator_no_sources):
        """Test turn processing with transition proposal."""
        source = TransitionSource(next_state="spin_problem")
        orchestrator_no_sources.add_source(source)

        decision = orchestrator_no_sources.process_turn(
            intent="data_complete",
            extracted_data={},
        )

        assert decision.next_state == "spin_problem"
        assert "transition_to_spin_problem" in decision.reason_codes

    def test_process_turn_updates_state(self, mock_state_machine, mock_flow_config):
        """Test that process_turn updates state machine state."""
        SourceRegistry.reset()

        orch = DialogueOrchestrator(
            state_machine=mock_state_machine,
            flow_config=mock_flow_config,
        )
        orch._sources.clear()

        source = TransitionSource(next_state="spin_problem")
        orch.add_source(source)

        initial_state = mock_state_machine.state
        decision = orch.process_turn(
            intent="data_complete",
            extracted_data={},
        )

        # State should be updated
        assert mock_state_machine.state == "spin_problem"
        assert mock_state_machine.state != initial_state

    def test_process_turn_updates_last_action(self, mock_state_machine, mock_flow_config):
        """Test that process_turn updates last_action."""
        SourceRegistry.reset()

        orch = DialogueOrchestrator(
            state_machine=mock_state_machine,
            flow_config=mock_flow_config,
        )
        orch._sources.clear()

        source = SimpleTestSource(action="custom_action")
        orch.add_source(source)

        orch.process_turn(
            intent="test",
            extracted_data={},
        )

        assert mock_state_machine.last_action == "custom_action"

    def test_process_turn_emits_events(self, orchestrator_no_sources):
        """Test that process_turn emits events."""
        events_received = []

        def handler(event):
            events_received.append(event)

        orchestrator_no_sources.event_bus.subscribe_all(handler)

        orchestrator_no_sources.process_turn(
            intent="greeting",
            extracted_data={},
        )

        # Should have at least TurnStartedEvent and DecisionCommittedEvent
        event_types = [e.event_type for e in events_received]
        assert EventType.TURN_STARTED in event_types
        assert EventType.DECISION_COMMITTED in event_types

    def test_process_turn_handles_source_error(self, orchestrator_no_sources):
        """Test that errors in sources are caught and logged."""
        error_source = ErrorSource()
        good_source = SimpleTestSource(action="fallback_action")

        orchestrator_no_sources.add_source(error_source)
        orchestrator_no_sources.add_source(good_source)

        # Should not raise, should continue with next source
        decision = orchestrator_no_sources.process_turn(
            intent="test",
            extracted_data={},
        )

        # Good source should have contributed
        assert decision.action == "fallback_action"

    def test_process_turn_skips_inactive_sources(self, orchestrator_no_sources):
        """Test that sources with should_contribute=False are skipped."""
        inactive_source = ConditionalSource(should_contribute_value=False)
        active_source = SimpleTestSource(action="active_action")

        orchestrator_no_sources.add_source(inactive_source)
        orchestrator_no_sources.add_source(active_source)

        decision = orchestrator_no_sources.process_turn(
            intent="test",
            extracted_data={},
        )

        # Only active source should have contributed
        assert decision.action == "active_action"
        assert "conditional_triggered" not in decision.reason_codes


# =============================================================================
# Test _apply_side_effects()
# =============================================================================

class TestApplySideEffects:
    """Test _apply_side_effects() for bot.py compatibility."""

    def test_apply_side_effects_updates_state(self, mock_state_machine, mock_flow_config):
        """Test that side effects update state."""
        SourceRegistry.reset()

        orch = DialogueOrchestrator(
            state_machine=mock_state_machine,
            flow_config=mock_flow_config,
        )

        decision = ResolvedDecision(
            action="test_action",
            next_state="spin_problem",
        )

        orch._apply_side_effects(decision, "spin_situation", True)

        assert mock_state_machine.state == "spin_problem"

    def test_apply_side_effects_updates_last_action(self, mock_state_machine, mock_flow_config):
        """Test that side effects update last_action."""
        SourceRegistry.reset()

        orch = DialogueOrchestrator(
            state_machine=mock_state_machine,
            flow_config=mock_flow_config,
        )

        decision = ResolvedDecision(
            action="custom_action",
            next_state="spin_situation",
        )

        orch._apply_side_effects(decision, "spin_situation", False)

        assert mock_state_machine.last_action == "custom_action"

    def test_apply_side_effects_updates_phase(self, mock_state_machine, mock_flow_config):
        """Test that side effects update current_phase."""
        SourceRegistry.reset()

        orch = DialogueOrchestrator(
            state_machine=mock_state_machine,
            flow_config=mock_flow_config,
        )

        decision = ResolvedDecision(
            action="test",
            next_state="spin_problem",
        )

        orch._apply_side_effects(decision, "spin_situation", True)

        assert mock_state_machine.current_phase == "problem"

    def test_apply_side_effects_applies_data_updates(self, mock_state_machine, mock_flow_config):
        """Test that side effects apply data_updates."""
        SourceRegistry.reset()

        orch = DialogueOrchestrator(
            state_machine=mock_state_machine,
            flow_config=mock_flow_config,
        )

        decision = ResolvedDecision(
            action="test",
            next_state="spin_situation",
            data_updates={"company_name": "ACME Corp"},
        )

        orch._apply_side_effects(decision, "spin_situation", False)

        assert mock_state_machine.collected_data.get("company_name") == "ACME Corp"

    def test_apply_side_effects_applies_flags(self, mock_state_machine, mock_flow_config):
        """Test that side effects apply flags_to_set."""
        SourceRegistry.reset()

        orch = DialogueOrchestrator(
            state_machine=mock_state_machine,
            flow_config=mock_flow_config,
        )

        decision = ResolvedDecision(
            action="test",
            next_state="spin_situation",
            flags_to_set={"_custom_flag": True},
        )

        orch._apply_side_effects(decision, "spin_situation", False)

        assert mock_state_machine.collected_data.get("_custom_flag") is True


# =============================================================================
# Test _fill_compatibility_fields()
# =============================================================================

class TestFillCompatibilityFields:
    """Test _fill_compatibility_fields() for bot.py compatibility."""

    def test_fill_prev_state(self, mock_state_machine, mock_flow_config):
        """Test that prev_state is filled."""
        SourceRegistry.reset()

        orch = DialogueOrchestrator(
            state_machine=mock_state_machine,
            flow_config=mock_flow_config,
        )

        decision = ResolvedDecision(action="test", next_state="spin_situation")
        orch._fill_compatibility_fields(decision, "greeting")

        assert decision.prev_state == "greeting"

    def test_fill_goal(self, mock_state_machine, mock_flow_config):
        """Test that goal is filled from state config."""
        SourceRegistry.reset()

        orch = DialogueOrchestrator(
            state_machine=mock_state_machine,
            flow_config=mock_flow_config,
        )

        decision = ResolvedDecision(action="test", next_state="spin_situation")
        orch._fill_compatibility_fields(decision, "greeting")

        assert decision.goal == "Gather situation"

    def test_fill_collected_data(self, mock_state_machine, mock_flow_config):
        """Test that collected_data is filled."""
        mock_state_machine.collected_data["test_field"] = "test_value"

        SourceRegistry.reset()

        orch = DialogueOrchestrator(
            state_machine=mock_state_machine,
            flow_config=mock_flow_config,
        )

        decision = ResolvedDecision(action="test", next_state="spin_situation")
        orch._fill_compatibility_fields(decision, "greeting")

        assert decision.collected_data.get("test_field") == "test_value"

    def test_fill_missing_data(self, mock_state_machine, mock_flow_config):
        """Test that missing_data is correctly identified."""
        SourceRegistry.reset()

        orch = DialogueOrchestrator(
            state_machine=mock_state_machine,
            flow_config=mock_flow_config,
        )

        decision = ResolvedDecision(action="test", next_state="spin_situation")
        orch._fill_compatibility_fields(decision, "greeting")

        # spin_situation requires "company_name" which is not in collected_data
        assert "company_name" in decision.missing_data

    def test_fill_is_final(self, mock_state_machine, mock_flow_config):
        """Test that is_final is filled."""
        SourceRegistry.reset()

        orch = DialogueOrchestrator(
            state_machine=mock_state_machine,
            flow_config=mock_flow_config,
        )

        # Test non-final state
        decision = ResolvedDecision(action="test", next_state="spin_situation")
        orch._fill_compatibility_fields(decision, "greeting")
        assert decision.is_final is False

        # Test final state
        decision = ResolvedDecision(action="test", next_state="soft_close")
        orch._fill_compatibility_fields(decision, "greeting")
        assert decision.is_final is True

    def test_fill_spin_phase(self, mock_state_machine, mock_flow_config):
        """Test that spin_phase is filled."""
        SourceRegistry.reset()

        orch = DialogueOrchestrator(
            state_machine=mock_state_machine,
            flow_config=mock_flow_config,
        )

        decision = ResolvedDecision(action="test", next_state="spin_problem")
        orch._fill_compatibility_fields(decision, "spin_situation")

        assert decision.spin_phase == "problem"


# =============================================================================
# Test Fallback Decision
# =============================================================================

class TestFallbackDecision:
    """Test fallback decision creation."""

    def test_create_fallback_decision(self, orchestrator_no_sources):
        """Test fallback decision creation."""
        fallback = orchestrator_no_sources._create_fallback_decision(
            current_state="spin_situation",
            reason="test_error",
            turn_number=5,
        )

        assert fallback.action == "continue_current_goal"
        assert fallback.next_state == "spin_situation"
        assert "fallback_test_error" in fallback.reason_codes
        assert fallback.resolution_trace.get("fallback") is True


# =============================================================================
# Test create_orchestrator() Factory
# =============================================================================

class TestCreateOrchestrator:
    """Test create_orchestrator() factory function."""

    def test_create_orchestrator_basic(self, mock_state_machine, mock_flow_config):
        """Test basic factory usage."""
        SourceRegistry.reset()

        orch = create_orchestrator(
            state_machine=mock_state_machine,
            flow_config=mock_flow_config,
        )

        assert isinstance(orch, DialogueOrchestrator)

    def test_create_orchestrator_with_metrics(self, mock_state_machine, mock_flow_config):
        """Test factory with metrics enabled."""
        SourceRegistry.reset()

        orch = create_orchestrator(
            state_machine=mock_state_machine,
            flow_config=mock_flow_config,
            enable_metrics=True,
        )

        # Should have metrics collector subscribed
        assert len(orch.event_bus._global_handlers) >= 1

    def test_create_orchestrator_with_debug_logging(self, mock_state_machine, mock_flow_config):
        """Test factory with debug logging enabled."""
        SourceRegistry.reset()

        orch = create_orchestrator(
            state_machine=mock_state_machine,
            flow_config=mock_flow_config,
            enable_debug_logging=True,
        )

        # Should have debug logger subscribed
        assert len(orch.event_bus._global_handlers) >= 1

    def test_create_orchestrator_with_tenant_config(self, mock_state_machine, mock_flow_config):
        """Test factory with tenant configuration."""
        SourceRegistry.reset()

        tenant = TenantConfig(
            tenant_id="acme",
            bot_name="ACME Bot",
        )

        orch = create_orchestrator(
            state_machine=mock_state_machine,
            flow_config=mock_flow_config,
            tenant_config=tenant,
        )

        assert orch._tenant_config.tenant_id == "acme"


# =============================================================================
# Test to_sm_result() Compatibility
# =============================================================================

class TestSmResultCompatibility:
    """Test that output is compatible with bot.py expectations."""

    def test_to_sm_result_has_required_fields(self, orchestrator_no_sources):
        """Test that to_sm_result() has all required fields for bot.py."""
        source = SimpleTestSource(action="test_action")
        orchestrator_no_sources.add_source(source)

        decision = orchestrator_no_sources.process_turn(
            intent="greeting",
            extracted_data={"name": "John"},
        )

        sm_result = decision.to_sm_result()

        # Required fields for bot.py
        assert "action" in sm_result
        assert "next_state" in sm_result
        assert "prev_state" in sm_result
        assert "goal" in sm_result
        assert "collected_data" in sm_result
        assert "missing_data" in sm_result
        assert "is_final" in sm_result
        assert "spin_phase" in sm_result
        assert "circular_flow" in sm_result
        assert "objection_flow" in sm_result

    def test_objection_stats_structure(self, orchestrator_no_sources):
        """Test that objection stats have expected structure."""
        decision = orchestrator_no_sources.process_turn(
            intent="greeting",
            extracted_data={},
        )

        objection_flow = decision.objection_flow

        assert "consecutive_objections" in objection_flow
        assert "total_objections" in objection_flow
        assert "history" in objection_flow


# =============================================================================
# Test Event Emission
# =============================================================================

class TestEventEmission:
    """Test event emission during pipeline."""

    def test_turn_started_event(self, orchestrator_no_sources):
        """Test TurnStartedEvent is emitted."""
        events = []
        orchestrator_no_sources.event_bus.subscribe(
            EventType.TURN_STARTED,
            lambda e: events.append(e)
        )

        orchestrator_no_sources.process_turn(
            intent="greeting",
            extracted_data={},
        )

        assert len(events) == 1
        assert events[0].data["intent"] == "greeting"
        assert events[0].data["state"] == "spin_situation"

    def test_decision_committed_event(self, orchestrator_no_sources):
        """Test DecisionCommittedEvent is emitted."""
        events = []
        orchestrator_no_sources.event_bus.subscribe(
            EventType.DECISION_COMMITTED,
            lambda e: events.append(e)
        )

        source = SimpleTestSource(action="test_action")
        orchestrator_no_sources.add_source(source)

        orchestrator_no_sources.process_turn(
            intent="greeting",
            extracted_data={},
        )

        assert len(events) == 1
        assert events[0].data["action"] == "test_action"

    def test_state_transitioned_event_on_transition(self, orchestrator_no_sources):
        """Test StateTransitionedEvent is emitted on state change."""
        events = []
        orchestrator_no_sources.event_bus.subscribe(
            EventType.STATE_TRANSITIONED,
            lambda e: events.append(e)
        )

        source = TransitionSource(next_state="spin_problem")
        orchestrator_no_sources.add_source(source)

        orchestrator_no_sources.process_turn(
            intent="data_complete",
            extracted_data={},
        )

        assert len(events) == 1
        assert events[0].data["from_state"] == "spin_situation"
        assert events[0].data["to_state"] == "spin_problem"

    def test_no_state_transitioned_event_without_transition(self, orchestrator_no_sources):
        """Test no StateTransitionedEvent when state doesn't change."""
        events = []
        orchestrator_no_sources.event_bus.subscribe(
            EventType.STATE_TRANSITIONED,
            lambda e: events.append(e)
        )

        source = SimpleTestSource(action="stay_action")
        orchestrator_no_sources.add_source(source)

        orchestrator_no_sources.process_turn(
            intent="greeting",
            extracted_data={},
        )

        # No transition, so no event
        assert len(events) == 0


# =============================================================================
# Test Error Handling
# =============================================================================

class TestErrorHandling:
    """Test error handling in the pipeline."""

    def test_error_event_on_source_error(self, orchestrator_no_sources):
        """Test ErrorOccurredEvent is emitted on source error."""
        events = []
        orchestrator_no_sources.event_bus.subscribe(
            EventType.ERROR_OCCURRED,
            lambda e: events.append(e)
        )

        error_source = ErrorSource()
        orchestrator_no_sources.add_source(error_source)

        orchestrator_no_sources.process_turn(
            intent="test",
            extracted_data={},
        )

        assert len(events) == 1
        assert events[0].data["component"] == "ErrorSource"
        assert "RuntimeError" in events[0].data["error_type"]


# =============================================================================
# Test get_turn_summary()
# =============================================================================

class TestGetTurnSummary:
    """Test get_turn_summary() method."""

    def test_get_turn_summary(self, orchestrator_no_sources):
        """Test that turn summary is returned."""
        source = SimpleTestSource(action="test_action")
        orchestrator_no_sources.add_source(source)

        orchestrator_no_sources.process_turn(
            intent="greeting",
            extracted_data={},
        )

        summary = orchestrator_no_sources.get_turn_summary()

        assert "intent" in summary
        assert "state" in summary
        assert summary["intent"] == "greeting"
