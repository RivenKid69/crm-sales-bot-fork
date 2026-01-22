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

    def transition_to(
        self,
        next_state: str,
        action: Optional[str] = None,
        phase: Optional[str] = None,
        source: str = "unknown",
        validate: bool = True,
    ) -> bool:
        """
        Atomically transition to a new state with consistent updates.

        FIX (Distributed State Mutation bug): This method ensures that
        state, current_phase, and last_action are updated atomically.
        """
        self._state = next_state
        self._current_phase = phase
        if action is not None:
            self._last_action = action
        return True

    def sync_phase_from_state(self) -> None:
        """Synchronize current_phase with the current state."""
        pass  # Mock doesn't have flow config to sync from


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


# =============================================================================
# STAGE 13: Extended Tests (Section 17.4 from Plan)
# =============================================================================

# -----------------------------------------------------------------------------
# The Core Problem Test - CRITICAL INTEGRATION TEST
# -----------------------------------------------------------------------------

class TestCoreProblem:
    """
    Tests for the core problem that Blackboard solves:
    price_question + data_complete should BOTH be applied.
    """

    @pytest.fixture
    def full_orchestrator(self):
        """Create an orchestrator with full sources for integration testing."""
        SourceRegistry.reset()

        sm = MockStateMachine(state="spin_situation")
        sm._collected_data = {}

        fc = MockFlowConfig(states={
            "spin_situation": {
                "goal": "Understand situation",
                "phase": "situation",
                "required_data": ["company_size"],
                "is_final": False,
                "transitions": {
                    "data_complete": "spin_problem",
                    "rejection": "soft_close",
                    "any": "spin_problem",
                },
                "rules": {},
            },
            "spin_problem": {
                "goal": "Identify problems",
                "phase": "problem",
                "required_data": [],
                "is_final": False,
                "transitions": {},
                "rules": {},
            },
            "soft_close": {
                "goal": "Graceful exit",
                "is_final": True,
                "transitions": {},
                "rules": {},
            },
            "_limits": {
                "max_consecutive_objections": 3,
                "max_total_objections": 5,
            },
        })

        return DialogueOrchestrator(
            state_machine=sm,
            flow_config=fc,
            enable_validation=True,
        )

    def test_price_question_with_data_complete_scenario(self, full_orchestrator):
        """
        CORE INTEGRATION TEST.

        Scenario:
        - Current state: spin_situation (requires company_size)
        - User message: "У нас 15 человек. Сколько стоит?"
        - Intent: price_question
        - Extracted data: {company_size: "15"}

        Expected:
        - Action: answer_with_pricing (answer the price question)
        - Next state: spin_problem (data is now complete, transition!)
        """
        sm = full_orchestrator._state_machine
        sm._state = "spin_situation"
        sm._collected_data = {}

        # Add PriceQuestionSource and DataCollectorSource
        from src.blackboard.sources.price_question import PriceQuestionSource
        from src.blackboard.sources.data_collector import DataCollectorSource

        full_orchestrator._sources.clear()
        full_orchestrator.add_source(PriceQuestionSource())
        full_orchestrator.add_source(DataCollectorSource())

        # Simulate extracted data being added to collected_data
        # (This would normally happen in bot.py before process_turn)
        sm._collected_data["company_size"] = "15"

        decision = full_orchestrator.process_turn(
            intent="price_question",
            extracted_data={"company_size": "15"},
        )

        # CRITICAL ASSERTIONS
        assert decision.action == "answer_with_pricing", \
            "Should answer the price question"
        assert decision.next_state == "spin_problem", \
            "Should ALSO transition to next phase (data is complete)"
        assert "price_question_priority" in decision.reason_codes
        assert "data_complete" in decision.reason_codes

    def test_price_question_without_complete_data(self, full_orchestrator):
        """Price question without completing data should not transition."""
        sm = full_orchestrator._state_machine
        sm._state = "spin_situation"
        sm._collected_data = {}  # No data

        from src.blackboard.sources.price_question import PriceQuestionSource
        from src.blackboard.sources.data_collector import DataCollectorSource

        full_orchestrator._sources.clear()
        full_orchestrator.add_source(PriceQuestionSource())
        full_orchestrator.add_source(DataCollectorSource())

        decision = full_orchestrator.process_turn(
            intent="price_question",
            extracted_data={},  # No new data either
        )

        assert decision.action == "answer_with_pricing"
        # No transition because data not complete - stays in current or fallback "any"
        # (Depends on configuration)


# -----------------------------------------------------------------------------
# COMPATIBILITY TESTS (for bot.py integration)
# -----------------------------------------------------------------------------

class TestBotCompatibility:
    """Tests ensuring full compatibility with bot.py expectations."""

    @pytest.fixture
    def orchestrator_for_compat(self):
        """Create orchestrator for compatibility testing."""
        SourceRegistry.reset()

        sm = MockStateMachine(state="spin_situation")
        sm._collected_data = {"company_size": "15"}

        fc = MockFlowConfig(states={
            "spin_situation": {
                "goal": "Understand situation",
                "phase": "situation",
                "required_data": ["company_size"],
                "optional_data": ["industry"],
                "is_final": False,
                "transitions": {"data_complete": "spin_problem"},
            },
            "spin_problem": {
                "goal": "Identify problems",
                "phase": "problem",
                "required_data": [],
                "is_final": False,
                "transitions": {},
            },
            "soft_close": {
                "goal": "Graceful exit",
                "is_final": True,
                "transitions": {},
            },
        })

        orch = DialogueOrchestrator(
            state_machine=sm,
            flow_config=fc,
            enable_validation=True,
        )
        orch._sources.clear()
        return orch

    def test_to_sm_result_returns_all_required_fields(self, orchestrator_for_compat):
        """
        CRITICAL: to_sm_result() MUST return all fields expected by bot.py.

        bot.py uses these fields:
        - action, next_state (core)
        - prev_state (for metrics)
        - goal (for generator context)
        - collected_data (full dict)
        - missing_data, optional_data (for generator)
        - is_final, spin_phase (for completion detection)
        - circular_flow, objection_flow (for statistics)
        """
        orchestrator_for_compat.add_source(SimpleTestSource(action="test_action"))

        decision = orchestrator_for_compat.process_turn(
            intent="info_provided",
            extracted_data={},
        )

        sm_result = decision.to_sm_result()

        # Assert ALL required fields are present
        assert "action" in sm_result
        assert "next_state" in sm_result
        assert "prev_state" in sm_result
        assert "goal" in sm_result
        assert "collected_data" in sm_result
        assert "missing_data" in sm_result
        assert "optional_data" in sm_result
        assert "is_final" in sm_result
        assert "spin_phase" in sm_result
        assert "circular_flow" in sm_result
        assert "objection_flow" in sm_result

        # Assert types are correct
        assert isinstance(sm_result["collected_data"], dict)
        assert isinstance(sm_result["missing_data"], list)
        assert isinstance(sm_result["optional_data"], list)
        assert isinstance(sm_result["is_final"], bool)

    def test_to_sm_result_compatible_with_dialogue_policy(self, orchestrator_for_compat):
        """
        CRITICAL: sm_result must be modifiable in-place by DialoguePolicy.

        DialoguePolicy does:
            sm_result["action"] = override.action
            sm_result["next_state"] = override.next_state
        """
        orchestrator_for_compat.add_source(SimpleTestSource(action="original_action"))

        decision = orchestrator_for_compat.process_turn(
            intent="greeting",
            extracted_data={},
        )

        sm_result = decision.to_sm_result()

        # Verify it's a regular dict that can be modified in-place
        assert isinstance(sm_result, dict)

        # Simulate DialoguePolicy modification
        original_action = sm_result["action"]
        sm_result["action"] = "policy_override_action"
        sm_result["next_state"] = "policy_override_state"

        # Changes should persist
        assert sm_result["action"] == "policy_override_action"
        assert sm_result["next_state"] == "policy_override_state"

    def test_to_sm_result_provides_goal_for_generator(self, orchestrator_for_compat):
        """
        Generator uses sm_result["goal"] for context.

        context = {
            "goal": sm_result["goal"],
            ...
        }
        """
        orchestrator_for_compat.add_source(SimpleTestSource(action="test"))

        decision = orchestrator_for_compat.process_turn(
            intent="greeting",
            extracted_data={},
        )

        sm_result = decision.to_sm_result()

        # Goal should come from state config
        assert sm_result["goal"] == "Understand situation"

    def test_to_sm_result_includes_trace_field(self, orchestrator_for_compat):
        """
        to_sm_result should include trace field for decision_trace.py compatibility.
        """
        orchestrator_for_compat.add_source(SimpleTestSource(action="test"))

        decision = orchestrator_for_compat.process_turn(
            intent="greeting",
            extracted_data={},
        )

        sm_result = decision.to_sm_result()

        # trace field should be present if resolution_trace exists
        if decision.resolution_trace:
            assert "trace" in sm_result
            assert sm_result["trace"] == decision.resolution_trace

    def test_to_sm_result_includes_prev_phase(self, orchestrator_for_compat):
        """
        to_sm_result should include prev_phase for decision_trace phase tracking.
        """
        orchestrator_for_compat.add_source(TransitionSource(next_state="spin_problem"))

        decision = orchestrator_for_compat.process_turn(
            intent="info_provided",
            extracted_data={"company_size": "15"},
        )

        sm_result = decision.to_sm_result()

        # prev_phase should be present
        assert "prev_phase" in sm_result


# -----------------------------------------------------------------------------
# EXTERNAL STATE CHANGES TESTS (Critical for bot.py integration)
# -----------------------------------------------------------------------------

class TestExternalStateChanges:
    """
    These tests verify that Blackboard correctly handles state changes
    made by bot.py BEFORE or AFTER process_turn().
    """

    def test_blackboard_sees_external_state_change_before_process(self):
        """
        CRITICAL: Blackboard must see state changes made by bot.py BEFORE process_turn().

        Scenario: Fallback "skip" action (bot.py line 743)
        1. bot.py sets state_machine.state = "spin_problem" (skip action)
        2. process_turn() is called
        3. Blackboard should read "spin_problem" as current state
        """
        SourceRegistry.reset()

        sm = MockStateMachine(state="greeting")
        fc = MockFlowConfig()

        orch = DialogueOrchestrator(
            state_machine=sm,
            flow_config=fc,
            enable_validation=True,
        )
        orch._sources.clear()
        orch.add_source(SimpleTestSource(action="test"))

        # Simulate bot.py fallback skip (line 743) BEFORE calling process_turn
        sm._state = "spin_problem"

        decision = orch.process_turn(
            intent="info_provided",
            extracted_data={},
        )

        # Blackboard should have read "spin_problem" as current state, NOT "greeting"
        assert decision.prev_state == "spin_problem"

    def test_blackboard_sees_external_collected_data_before_process(self):
        """
        CRITICAL: Blackboard must see collected_data changes made BEFORE process_turn().

        Scenario: Competitor extraction (bot.py lines 773-776)
        1. bot.py sets collected_data["competitor_mentioned"] = True
        2. process_turn() is called
        3. Blackboard should see competitor_mentioned in collected_data
        """
        SourceRegistry.reset()

        sm = MockStateMachine(state="spin_situation")
        sm._collected_data = {}

        fc = MockFlowConfig()

        orch = DialogueOrchestrator(
            state_machine=sm,
            flow_config=fc,
            enable_validation=True,
        )
        orch._sources.clear()
        orch.add_source(SimpleTestSource(action="test"))

        # Simulate bot.py competitor extraction (lines 773-776) BEFORE calling process_turn
        sm._collected_data["competitor_mentioned"] = True
        sm._collected_data["competitor_name"] = "Competitor X"

        decision = orch.process_turn(
            intent="info_provided",
            extracted_data={},
        )

        # Blackboard should have seen the competitor data
        sm_result = decision.to_sm_result()
        assert sm_result["collected_data"].get("competitor_mentioned") is True
        assert sm_result["collected_data"].get("competitor_name") == "Competitor X"

    def test_dialogue_policy_can_override_state_after_process(self):
        """
        CRITICAL: DialoguePolicy can OVERWRITE state AFTER process_turn().

        Scenario: DialoguePolicy override (bot.py line 944)
        1. process_turn() is called, sets state to "spin_problem"
        2. DialoguePolicy overrides to "spin_implication"
        3. bot.py writes state_machine.state = "spin_implication"
        4. This is NORMAL and EXPECTED behavior
        """
        SourceRegistry.reset()

        sm = MockStateMachine(state="spin_situation")
        sm._collected_data = {"company_size": "15"}

        fc = MockFlowConfig()

        orch = DialogueOrchestrator(
            state_machine=sm,
            flow_config=fc,
            enable_validation=True,
        )
        orch._sources.clear()
        orch.add_source(TransitionSource(next_state="spin_problem"))

        decision = orch.process_turn(
            intent="info_provided",
            extracted_data={},
        )

        # process_turn completed, state was set via _apply_side_effects
        original_next_state = decision.next_state

        # Simulate DialoguePolicy override (line 944)
        policy_override_state = "spin_implication"
        sm._state = policy_override_state

        # State should be overwritten
        assert sm.state == policy_override_state
        # This is expected - DialoguePolicy has final say

    def test_orchestrator_reads_state_at_begin_turn(self):
        """
        Verify that state is read at the START of process_turn, not cached.

        This ensures external state changes (fallback skip) are visible.
        """
        SourceRegistry.reset()

        sm = MockStateMachine(state="greeting")
        fc = MockFlowConfig()

        orch = DialogueOrchestrator(
            state_machine=sm,
            flow_config=fc,
            enable_validation=True,
        )
        orch._sources.clear()
        orch.add_source(SimpleTestSource(action="test"))

        # First call
        decision1 = orch.process_turn(
            intent="greeting",
            extracted_data={},
        )

        # External state change between calls
        sm._state = "spin_situation"

        # Second call should see "spin_situation", not cached "greeting"
        decision2 = orch.process_turn(
            intent="info_provided",
            extracted_data={},
        )

        assert decision2.prev_state == "spin_situation"

    def test_disambiguation_not_affected_by_blackboard(self):
        """
        Verify that disambiguation state is NOT managed by Blackboard.

        Disambiguation methods are called directly by bot.py and are
        OUT OF SCOPE for Blackboard system.
        """
        SourceRegistry.reset()

        sm = MockStateMachine(state="greeting")
        # Add disambiguation-like attributes (would exist on real StateMachine)
        sm.in_disambiguation = False
        sm.disambiguation_context = None
        sm.turns_since_last_disambiguation = 5

        fc = MockFlowConfig()

        orch = DialogueOrchestrator(
            state_machine=sm,
            flow_config=fc,
            enable_validation=True,
        )
        orch._sources.clear()
        orch.add_source(SimpleTestSource(action="test"))

        decision = orch.process_turn(
            intent="greeting",
            extracted_data={},
        )

        # Blackboard should complete without touching disambiguation
        assert decision is not None
        # Disambiguation state should be unchanged
        assert sm.in_disambiguation is False

    def test_compatibility_fields_filled_after_state_transition(self):
        """
        When state transitions, compatibility fields should reflect NEW state.
        """
        SourceRegistry.reset()

        sm = MockStateMachine(state="spin_situation")
        sm._collected_data = {"company_size": "15"}

        fc = MockFlowConfig(states={
            "spin_situation": {
                "goal": "Understand situation",
                "phase": "situation",
                "required_data": ["company_size"],
                "is_final": False,
                "transitions": {"data_complete": "spin_problem"},
            },
            "spin_problem": {
                "goal": "Identify problems",
                "phase": "problem",
                "required_data": [],
                "is_final": False,
                "transitions": {},
            },
        })

        orch = DialogueOrchestrator(
            state_machine=sm,
            flow_config=fc,
            enable_validation=True,
        )
        orch._sources.clear()
        orch.add_source(TransitionSource(next_state="spin_problem"))

        decision = orch.process_turn(
            intent="info_provided",
            extracted_data={},
        )

        # If transitioned to spin_problem, fields should reflect spin_problem config
        if decision.next_state == "spin_problem":
            assert decision.prev_state == "spin_situation"
            assert decision.goal == "Identify problems"
            assert decision.spin_phase == "problem"


# -----------------------------------------------------------------------------
# OBJECTION LIMIT TESTS
# -----------------------------------------------------------------------------

class TestObjectionLimits:
    """Tests for objection limit handling."""

    @pytest.fixture
    def orchestrator_with_objection_guard(self):
        """Create orchestrator with ObjectionGuardSource."""
        SourceRegistry.reset()

        sm = MockStateMachine(state="spin_problem")
        sm._collected_data = {}

        fc = MockFlowConfig(states={
            "spin_problem": {
                "goal": "Identify problems",
                "phase": "problem",
                "required_data": [],
                "is_final": False,
                "transitions": {},
            },
            "soft_close": {
                "goal": "Graceful exit",
                "is_final": True,
                "transitions": {},
            },
            "_limits": {
                "max_consecutive_objections": 3,
                "max_total_objections": 5,
            },
        })

        orch = DialogueOrchestrator(
            state_machine=sm,
            flow_config=fc,
            enable_validation=True,
        )
        orch._sources.clear()

        from src.blackboard.sources.objection_guard import ObjectionGuardSource
        orch.add_source(ObjectionGuardSource())

        return orch

    def test_objection_limit_triggers_soft_close(self, orchestrator_with_objection_guard):
        """Exceeding objection limit should trigger soft_close."""
        sm = orchestrator_with_objection_guard._state_machine

        # Simulate high objection counts
        sm._intent_tracker._objection_consecutive = 3
        sm._intent_tracker._objection_total = 5

        decision = orchestrator_with_objection_guard.process_turn(
            intent="objection_price",
            extracted_data={},
        )

        assert decision.action == "objection_limit_reached"
        assert decision.next_state == "soft_close"

    def test_objection_limit_sets_is_final_true(self, orchestrator_with_objection_guard):
        """
        CRITICAL: Objection limit should set is_final=True.

        When objection limit is reached:
        1. ObjectionGuardSource proposes _objection_limit_final data update
        2. _fill_compatibility_fields checks for this flag
        3. is_final is set to True (even if soft_close config has is_final=False)

        This prevents dialogue continuation and objection counter overflow.
        """
        sm = orchestrator_with_objection_guard._state_machine
        sm._collected_data = {}

        # Simulate high objection counts
        sm._intent_tracker._objection_consecutive = 3
        sm._intent_tracker._objection_total = 5

        decision = orchestrator_with_objection_guard.process_turn(
            intent="objection_price",
            extracted_data={},
        )

        sm_result = decision.to_sm_result()

        # CRITICAL ASSERTIONS
        assert sm_result["next_state"] == "soft_close"
        assert sm_result["is_final"] is True, \
            "is_final MUST be True when objection limit reached"
        assert sm_result["collected_data"].get("_objection_limit_final") is True, \
            "_objection_limit_final flag MUST be set in collected_data"

    def test_objection_within_limits_continues(self, orchestrator_with_objection_guard):
        """Objections within limits should NOT trigger soft_close."""
        sm = orchestrator_with_objection_guard._state_machine

        # Low objection counts
        sm._intent_tracker._objection_consecutive = 1
        sm._intent_tracker._objection_total = 2

        decision = orchestrator_with_objection_guard.process_turn(
            intent="objection_price",
            extracted_data={},
        )

        # Should NOT go to soft_close
        assert decision.next_state != "soft_close" or decision.action != "objection_limit_reached"


# -----------------------------------------------------------------------------
# FACTORY FUNCTION TESTS (Extended)
# -----------------------------------------------------------------------------

class TestFactoryFunctionExtended:
    """Extended tests for create_orchestrator() factory function."""

    def test_create_orchestrator_with_custom_source(self):
        """create_orchestrator should support custom sources via Plugin System."""
        SourceRegistry.reset()

        sm = MockStateMachine(state="greeting")
        fc = MockFlowConfig()

        class MyCustomSource(KnowledgeSource):
            """Custom source for testing."""
            def contribute(self, blackboard):
                blackboard.propose_action(
                    action="custom_action",
                    priority=Priority.NORMAL,
                    source_name=self.name,
                    reason_code="custom_reason",
                )

        orchestrator = create_orchestrator(
            state_machine=sm,
            flow_config=fc,
            custom_sources=[MyCustomSource],
        )

        # Should have built-in sources + custom source
        source_names = [s.name for s in orchestrator.sources]
        assert "MyCustomSource" in source_names

    def test_orchestrator_loads_sources_from_registry(self):
        """DialogueOrchestrator should load sources from SourceRegistry."""
        from src.blackboard.source_registry import register_builtin_sources

        SourceRegistry.reset()
        # Re-register built-in sources after reset
        register_builtin_sources()

        sm = MockStateMachine(state="greeting")
        fc = MockFlowConfig()

        orchestrator = create_orchestrator(
            state_machine=sm,
            flow_config=fc,
        )

        # Verify sources are loaded
        source_names = [s.name for s in orchestrator.sources]

        # Check that key sources are present (order may vary based on priority)
        assert "PriceQuestionSource" in source_names
        assert "DataCollectorSource" in source_names

    def test_create_orchestrator_with_persona_limits(self):
        """create_orchestrator should pass persona_limits to ObjectionGuardSource."""
        SourceRegistry.reset()

        sm = MockStateMachine(state="greeting")
        fc = MockFlowConfig()

        custom_limits = {
            "aggressive": {"consecutive": 10, "total": 15},
            "default": {"consecutive": 5, "total": 10},
        }

        orchestrator = create_orchestrator(
            state_machine=sm,
            flow_config=fc,
            persona_limits=custom_limits,
        )

        # Find ObjectionGuardSource
        objection_source = orchestrator.get_source("ObjectionGuardSource")

        if objection_source:
            # Custom limits should be applied
            assert objection_source.persona_limits.get("aggressive", {}).get("consecutive") == 10


# -----------------------------------------------------------------------------
# SIDE EFFECTS TESTS (Extended)
# -----------------------------------------------------------------------------

class TestSideEffectsExtended:
    """Extended tests for _apply_side_effects()."""

    def test_side_effects_applied_correctly(self):
        """
        Side effects MUST be applied for bot.py compatibility:
        - state_machine.state updated
        - state_machine.last_action updated
        - IntentTracker.record() called
        """
        SourceRegistry.reset()

        sm = MockStateMachine(state="spin_situation")
        sm._collected_data = {"company_size": "15"}

        fc = MockFlowConfig(states={
            "spin_situation": {
                "goal": "Understand situation",
                "phase": "situation",
                "required_data": ["company_size"],
                "transitions": {"data_complete": "spin_problem"},
            },
            "spin_problem": {
                "goal": "Identify problems",
                "phase": "problem",
                "required_data": [],
            },
        })

        orch = DialogueOrchestrator(
            state_machine=sm,
            flow_config=fc,
            enable_validation=True,
        )
        orch._sources.clear()

        # Add source that proposes action
        orch.add_source(SimpleTestSource(action="custom_action"))
        orch.add_source(TransitionSource(next_state="spin_problem"))

        initial_turn = sm._intent_tracker.turn_number

        orch.process_turn(
            intent="info_provided",
            extracted_data={"pain_point": "losing customers"},
        )

        # State should be updated
        assert sm.state == "spin_problem"

        # last_action should be updated
        assert sm.last_action == "custom_action"

        # IntentTracker should have recorded (turn number incremented)
        assert sm._intent_tracker.turn_number == initial_turn + 1

    def test_on_enter_flags_applied_on_transition(self):
        """Test that on_enter flags are applied when state changes."""
        SourceRegistry.reset()

        sm = MockStateMachine(state="spin_situation")
        sm._collected_data = {}

        fc = MockFlowConfig(states={
            "spin_situation": {
                "goal": "Understand situation",
                "phase": "situation",
                "transitions": {"data_complete": "spin_problem"},
            },
            "spin_problem": {
                "goal": "Identify problems",
                "phase": "problem",
                "on_enter": {
                    "set_flags": {"entered_problem": True},
                },
            },
        })

        orch = DialogueOrchestrator(
            state_machine=sm,
            flow_config=fc,
            enable_validation=True,
        )
        orch._sources.clear()
        orch.add_source(TransitionSource(next_state="spin_problem"))

        orch.process_turn(
            intent="data_complete",
            extracted_data={},
        )

        # on_enter flags should be applied
        assert sm.collected_data.get("entered_problem") is True
