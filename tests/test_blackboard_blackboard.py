# tests/test_blackboard_blackboard.py

"""
Tests for Blackboard Stage 3: DialogueBlackboard.

These tests verify:
1. DialogueBlackboard initialization
2. Context Layer (begin_turn, get_context)
3. Proposal Layer (propose_action, propose_transition, propose_data_update, propose_flag_set)
4. Decision Layer (commit_decision, get_decision)
5. Utility methods (get_turn_summary)
6. Integration with protocols (IStateMachine, IIntentTracker, IFlowConfig)
7. Multi-tenancy support
8. Objection skip logic
"""

import pytest
from datetime import datetime
from typing import Dict, Any, Optional
from unittest.mock import Mock, MagicMock, patch
from dataclasses import dataclass, field


# =============================================================================
# Mock Implementations for Testing
# =============================================================================

class MockStateMachine:
    """Mock StateMachine implementing IStateMachine protocol."""

    def __init__(self, state: str = "greeting", collected_data: Optional[Dict[str, Any]] = None):
        self._state = state
        self._collected_data = collected_data or {}
        self._current_phase = None
        self._last_action = None
        self._intent_tracker = None

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


class MockIntentTracker:
    """Mock IntentTracker implementing IIntentTracker protocol."""

    def __init__(self, turn_number: int = 0):
        self._turn_number = turn_number
        self._prev_intent = None
        self._intents = []
        self._objection_consecutive = 0
        self._objection_total = 0
        self._category_totals = {}

    @property
    def turn_number(self) -> int:
        return self._turn_number

    @property
    def prev_intent(self) -> Optional[str]:
        return self._prev_intent

    def record(self, intent: str, state: str) -> None:
        if self._intents:
            self._prev_intent = self._intents[-1][0]
        self._intents.append((intent, state))
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
        return sum(1 for i, _ in self._intents if i == intent)

    def category_total(self, category: str) -> int:
        return self._category_totals.get(category, 0)


class MockFlowConfig:
    """Mock FlowConfig implementing IFlowConfig protocol."""

    def __init__(self, states: Optional[Dict[str, Dict[str, Any]]] = None):
        self._states = states or {
            "greeting": {"goal": "Greet user", "phase": None},
            "spin_situation": {"goal": "Gather situation", "phase": "situation"},
            "spin_problem": {"goal": "Identify problems", "phase": "problem"},
            "_limits": {"max_consecutive_objections": 3, "max_total_objections": 5},
        }

    @property
    def states(self) -> Dict[str, Dict[str, Any]]:
        return self._states

    def to_dict(self) -> Dict[str, Any]:
        return {"states": self._states}

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


# =============================================================================
# Test DialogueBlackboard Initialization
# =============================================================================

class TestDialogueBlackboardInit:
    """Test DialogueBlackboard initialization."""

    def test_init_basic(self):
        """Test basic initialization with required arguments."""
        from src.blackboard.blackboard import DialogueBlackboard

        sm = MockStateMachine()
        flow_config = MockFlowConfig()

        bb = DialogueBlackboard(state_machine=sm, flow_config=flow_config)

        assert bb._state_machine is sm
        assert bb._flow_config is flow_config
        assert bb.tenant_id == "default"
        assert bb._context is None
        assert bb._decision is None
        assert bb._action_proposals == []
        assert bb._transition_proposals == []

    def test_init_with_intent_tracker(self):
        """Test initialization with custom intent tracker."""
        from src.blackboard.blackboard import DialogueBlackboard

        sm = MockStateMachine()
        flow_config = MockFlowConfig()
        tracker = MockIntentTracker(turn_number=5)

        bb = DialogueBlackboard(
            state_machine=sm,
            flow_config=flow_config,
            intent_tracker=tracker,
        )

        assert bb._intent_tracker is tracker
        assert bb._intent_tracker.turn_number == 5

    def test_init_with_tenant_config(self):
        """Test initialization with tenant config."""
        from src.blackboard.blackboard import DialogueBlackboard
        from src.blackboard.protocols import TenantConfig

        sm = MockStateMachine()
        flow_config = MockFlowConfig()
        tenant = TenantConfig(
            tenant_id="acme_corp",
            bot_name="ACME Bot",
            tone="friendly",
        )

        bb = DialogueBlackboard(
            state_machine=sm,
            flow_config=flow_config,
            tenant_config=tenant,
        )

        assert bb.tenant_id == "acme_corp"
        assert bb.tenant_config.bot_name == "ACME Bot"
        assert bb.tenant_config.tone == "friendly"


# =============================================================================
# Test Context Layer
# =============================================================================

class TestContextLayer:
    """Test Context Layer (begin_turn, get_context)."""

    @pytest.fixture
    def blackboard(self):
        """Create a basic blackboard for testing."""
        from src.blackboard.blackboard import DialogueBlackboard

        sm = MockStateMachine(state="greeting")
        flow_config = MockFlowConfig()
        tracker = MockIntentTracker()

        return DialogueBlackboard(
            state_machine=sm,
            flow_config=flow_config,
            intent_tracker=tracker,
        )

    def test_begin_turn_basic(self, blackboard):
        """Test basic begin_turn functionality."""
        blackboard.begin_turn(
            intent="greeting",
            extracted_data={"company_name": "ACME"},
        )

        assert blackboard._current_intent == "greeting"
        assert blackboard._context is not None
        assert blackboard._context.current_intent == "greeting"
        assert blackboard._context.state == "greeting"
        assert blackboard._turn_start_time is not None

    def test_begin_turn_records_intent(self, blackboard):
        """Test that begin_turn records intent in tracker."""
        blackboard.begin_turn(
            intent="agreement",
            extracted_data={},
        )

        assert blackboard._intent_tracker.turn_number == 1

    def test_begin_turn_updates_collected_data(self, blackboard):
        """Test that begin_turn updates collected_data."""
        blackboard._state_machine._collected_data = {"existing": "data"}

        blackboard.begin_turn(
            intent="provide_info",
            extracted_data={"company_size": "large", "industry": "IT"},
        )

        ctx = blackboard.get_context()
        assert ctx.collected_data["existing"] == "data"
        assert ctx.collected_data["company_size"] == "large"
        assert ctx.collected_data["industry"] == "IT"

    def test_begin_turn_ignores_empty_values(self, blackboard):
        """Test that begin_turn ignores empty values in extracted_data."""
        blackboard._state_machine._collected_data = {"existing": "data"}

        blackboard.begin_turn(
            intent="test",
            extracted_data={"new_field": "value", "empty": "", "none_field": None},
        )

        ctx = blackboard.get_context()
        assert ctx.collected_data["new_field"] == "value"
        assert "empty" not in ctx.collected_data or ctx.collected_data.get("empty") == ""
        assert "none_field" not in ctx.collected_data

    def test_begin_turn_clears_proposals(self, blackboard):
        """Test that begin_turn clears previous proposals."""
        from src.blackboard.enums import Priority

        # Add some proposals
        blackboard.begin_turn(intent="first", extracted_data={})
        blackboard.propose_action("action1", Priority.NORMAL)
        blackboard.propose_transition("state1", Priority.NORMAL)
        blackboard.propose_data_update("field1", "value1")
        blackboard.propose_flag_set("flag1", True)

        # Start new turn
        blackboard.begin_turn(intent="second", extracted_data={})

        assert blackboard.get_action_proposals() == []
        assert blackboard.get_transition_proposals() == []
        assert blackboard.get_data_updates() == {}
        assert blackboard.get_flags_to_set() == {}

    def test_begin_turn_clears_decision(self, blackboard):
        """Test that begin_turn clears previous decision."""
        from src.blackboard.models import ResolvedDecision

        blackboard.begin_turn(intent="first", extracted_data={})
        blackboard.commit_decision(ResolvedDecision(action="test", next_state="test"))

        # Start new turn
        blackboard.begin_turn(intent="second", extracted_data={})

        assert blackboard.get_decision() is None

    def test_begin_turn_with_context_envelope(self, blackboard):
        """Test begin_turn with context envelope."""
        from src.context_envelope import ContextEnvelope

        envelope = ContextEnvelope(state="greeting")

        blackboard.begin_turn(
            intent="greeting",
            extracted_data={},
            context_envelope=envelope,
        )

        ctx = blackboard.get_context()
        assert ctx.context_envelope is envelope

    def test_get_context_before_begin_turn_raises(self, blackboard):
        """Test that get_context raises error before begin_turn."""
        with pytest.raises(RuntimeError) as exc_info:
            blackboard.get_context()

        assert "called before begin_turn" in str(exc_info.value)

    def test_get_context_returns_snapshot(self, blackboard):
        """Test that get_context returns ContextSnapshot."""
        from src.blackboard.models import ContextSnapshot

        blackboard.begin_turn(intent="test", extracted_data={})

        ctx = blackboard.get_context()
        assert isinstance(ctx, ContextSnapshot)

    def test_current_intent_property(self, blackboard):
        """Test current_intent property."""
        blackboard.begin_turn(intent="agreement", extracted_data={})

        assert blackboard.current_intent == "agreement"

    def test_current_intent_before_begin_turn_raises(self, blackboard):
        """Test current_intent raises before begin_turn."""
        with pytest.raises(RuntimeError) as exc_info:
            _ = blackboard.current_intent

        assert "before begin_turn" in str(exc_info.value)

    def test_current_state_property(self, blackboard):
        """Test current_state property."""
        assert blackboard.current_state == "greeting"

        blackboard._state_machine.state = "spin_situation"
        assert blackboard.current_state == "spin_situation"

    def test_collected_data_property(self, blackboard):
        """Test collected_data property."""
        blackboard.begin_turn(
            intent="test",
            extracted_data={"key": "value"},
        )

        assert blackboard.collected_data == {"key": "value"}

    def test_collected_data_before_begin_turn_returns_empty(self, blackboard):
        """Test collected_data returns empty dict before begin_turn."""
        assert blackboard.collected_data == {}


# =============================================================================
# Test Proposal Layer
# =============================================================================

class TestProposalLayer:
    """Test Proposal Layer (propose_action, propose_transition, etc.)."""

    @pytest.fixture
    def blackboard(self):
        """Create a blackboard with turn started."""
        from src.blackboard.blackboard import DialogueBlackboard

        sm = MockStateMachine()
        flow_config = MockFlowConfig()
        tracker = MockIntentTracker()

        bb = DialogueBlackboard(
            state_machine=sm,
            flow_config=flow_config,
            intent_tracker=tracker,
        )
        bb.begin_turn(intent="test", extracted_data={})
        return bb

    def test_propose_action_basic(self, blackboard):
        """Test basic propose_action."""
        from src.blackboard.enums import Priority, ProposalType

        blackboard.propose_action(
            action="answer_question",
            priority=Priority.HIGH,
            source_name="TestSource",
            reason_code="TEST_001",
        )

        proposals = blackboard.get_action_proposals()
        assert len(proposals) == 1
        assert proposals[0].type == ProposalType.ACTION
        assert proposals[0].value == "answer_question"
        assert proposals[0].priority == Priority.HIGH
        assert proposals[0].source_name == "TestSource"
        assert proposals[0].reason_code == "TEST_001"
        assert proposals[0].combinable is True  # Default

    def test_propose_action_non_combinable(self, blackboard):
        """Test propose_action with combinable=False."""
        from src.blackboard.enums import Priority

        blackboard.propose_action(
            action="reject",
            priority=Priority.CRITICAL,
            combinable=False,
            source_name="ObjectionGuard",
            reason_code="OBJ_LIMIT",
        )

        proposals = blackboard.get_action_proposals()
        assert proposals[0].combinable is False

    def test_propose_action_with_metadata(self, blackboard):
        """Test propose_action with metadata."""
        from src.blackboard.enums import Priority

        blackboard.propose_action(
            action="handle_objection",
            priority=Priority.HIGH,
            source_name="ObjectionHandler",
            reason_code="OBJ_HANDLE",
            metadata={"objection_type": "price", "consecutive": 2},
        )

        proposals = blackboard.get_action_proposals()
        assert proposals[0].metadata == {"objection_type": "price", "consecutive": 2}

    def test_propose_action_default_reason_code(self, blackboard):
        """Test propose_action generates default reason_code."""
        from src.blackboard.enums import Priority

        blackboard.propose_action(
            action="my_action",
            priority=Priority.NORMAL,
            source_name="TestSource",
        )

        proposals = blackboard.get_action_proposals()
        assert proposals[0].reason_code == "action_my_action"

    def test_propose_transition_basic(self, blackboard):
        """Test basic propose_transition."""
        from src.blackboard.enums import Priority, ProposalType

        blackboard.propose_transition(
            next_state="spin_problem",
            priority=Priority.NORMAL,
            source_name="TransitionHandler",
            reason_code="DATA_COMPLETE",
        )

        proposals = blackboard.get_transition_proposals()
        assert len(proposals) == 1
        assert proposals[0].type == ProposalType.TRANSITION
        assert proposals[0].value == "spin_problem"
        assert proposals[0].priority == Priority.NORMAL
        assert proposals[0].source_name == "TransitionHandler"
        assert proposals[0].reason_code == "DATA_COMPLETE"
        assert proposals[0].combinable is True  # Always true for transitions

    def test_propose_transition_default_reason_code(self, blackboard):
        """Test propose_transition generates default reason_code."""
        from src.blackboard.enums import Priority

        blackboard.propose_transition(
            next_state="spin_situation",
            priority=Priority.NORMAL,
            source_name="TestSource",
        )

        proposals = blackboard.get_transition_proposals()
        assert proposals[0].reason_code == "transition_to_spin_situation"

    def test_propose_data_update(self, blackboard):
        """Test propose_data_update."""
        blackboard.propose_data_update(
            field="company_size",
            value="large",
            source_name="DataExtractor",
            reason_code="EXTRACTED",
        )

        updates = blackboard.get_data_updates()
        assert updates == {"company_size": "large"}

    def test_propose_data_update_multiple(self, blackboard):
        """Test multiple data updates."""
        blackboard.propose_data_update("field1", "value1", "Source1")
        blackboard.propose_data_update("field2", "value2", "Source2")
        blackboard.propose_data_update("field1", "overwritten", "Source3")  # Overwrite

        updates = blackboard.get_data_updates()
        assert updates == {"field1": "overwritten", "field2": "value2"}

    def test_propose_flag_set(self, blackboard):
        """Test propose_flag_set."""
        blackboard.propose_flag_set(
            flag="_objection_handled",
            value=True,
            source_name="ObjectionHandler",
            reason_code="OBJ_RESOLVED",
        )

        flags = blackboard.get_flags_to_set()
        assert flags == {"_objection_handled": True}

    def test_propose_flag_set_multiple(self, blackboard):
        """Test multiple flag sets."""
        blackboard.propose_flag_set("flag1", True, "Source1")
        blackboard.propose_flag_set("flag2", "value", "Source2")

        flags = blackboard.get_flags_to_set()
        assert flags == {"flag1": True, "flag2": "value"}

    def test_get_proposals_returns_all(self, blackboard):
        """Test get_proposals returns all proposals."""
        from src.blackboard.enums import Priority

        blackboard.propose_action("action1", Priority.HIGH, source_name="S1")
        blackboard.propose_action("action2", Priority.NORMAL, source_name="S2")
        blackboard.propose_transition("state1", Priority.LOW, source_name="S3")

        all_proposals = blackboard.get_proposals()
        assert len(all_proposals) == 3

        # Actions first, then transitions
        assert all_proposals[0].value == "action1"
        assert all_proposals[1].value == "action2"
        assert all_proposals[2].value == "state1"

    def test_get_action_proposals_returns_copy(self, blackboard):
        """Test get_action_proposals returns a copy."""
        from src.blackboard.enums import Priority

        blackboard.propose_action("action1", Priority.NORMAL, source_name="S1")

        proposals1 = blackboard.get_action_proposals()
        proposals2 = blackboard.get_action_proposals()

        assert proposals1 is not proposals2
        assert proposals1 == proposals2

    def test_get_transition_proposals_returns_copy(self, blackboard):
        """Test get_transition_proposals returns a copy."""
        from src.blackboard.enums import Priority

        blackboard.propose_transition("state1", Priority.NORMAL, source_name="S1")

        proposals1 = blackboard.get_transition_proposals()
        proposals2 = blackboard.get_transition_proposals()

        assert proposals1 is not proposals2


# =============================================================================
# Test Decision Layer
# =============================================================================

class TestDecisionLayer:
    """Test Decision Layer (commit_decision, get_decision)."""

    @pytest.fixture
    def blackboard(self):
        """Create a blackboard with turn started."""
        from src.blackboard.blackboard import DialogueBlackboard

        sm = MockStateMachine()
        flow_config = MockFlowConfig()
        tracker = MockIntentTracker()

        bb = DialogueBlackboard(
            state_machine=sm,
            flow_config=flow_config,
            intent_tracker=tracker,
        )
        bb.begin_turn(intent="test", extracted_data={})
        return bb

    def test_commit_decision_stores_decision(self, blackboard):
        """Test that commit_decision stores the decision."""
        from src.blackboard.models import ResolvedDecision

        decision = ResolvedDecision(
            action="answer_question",
            next_state="spin_problem",
            reason_codes=["QUESTION_ANSWERED"],
        )

        blackboard.commit_decision(decision)

        stored = blackboard.get_decision()
        assert stored is decision
        assert stored.action == "answer_question"
        assert stored.next_state == "spin_problem"

    def test_commit_decision_applies_data_updates(self, blackboard):
        """Test that commit_decision applies data_updates to state machine."""
        from src.blackboard.models import ResolvedDecision

        decision = ResolvedDecision(
            action="collect_data",
            next_state="current",
            data_updates={"collected_field": "collected_value"},
        )

        blackboard.commit_decision(decision)

        assert blackboard._state_machine.collected_data["collected_field"] == "collected_value"

    def test_commit_decision_applies_proposal_data_updates(self, blackboard):
        """Test that commit_decision applies proposed data updates."""
        from src.blackboard.models import ResolvedDecision

        blackboard.propose_data_update("proposed_field", "proposed_value", "TestSource")

        decision = ResolvedDecision(
            action="test",
            next_state="current",
        )

        blackboard.commit_decision(decision)

        assert blackboard._state_machine.collected_data["proposed_field"] == "proposed_value"

    def test_commit_decision_applies_flags(self, blackboard):
        """Test that commit_decision applies flags_to_set."""
        from src.blackboard.models import ResolvedDecision

        decision = ResolvedDecision(
            action="handle_objection",
            next_state="current",
            flags_to_set={"_objection_handled": True},
        )

        blackboard.commit_decision(decision)

        assert blackboard.get_flags_to_set()["_objection_handled"] is True

    def test_get_decision_returns_none_before_commit(self, blackboard):
        """Test that get_decision returns None before commit."""
        assert blackboard.get_decision() is None


# =============================================================================
# Test Utility Methods
# =============================================================================

class TestUtilityMethods:
    """Test utility methods (get_turn_summary)."""

    @pytest.fixture
    def blackboard(self):
        """Create a blackboard with turn started."""
        from src.blackboard.blackboard import DialogueBlackboard

        sm = MockStateMachine(state="spin_situation")
        flow_config = MockFlowConfig()
        tracker = MockIntentTracker(turn_number=3)

        bb = DialogueBlackboard(
            state_machine=sm,
            flow_config=flow_config,
            intent_tracker=tracker,
        )
        bb.begin_turn(intent="agreement", extracted_data={})
        return bb

    def test_get_turn_summary_basic(self, blackboard):
        """Test get_turn_summary returns correct structure."""
        summary = blackboard.get_turn_summary()

        assert "turn_number" in summary
        assert "intent" in summary
        assert "state" in summary
        assert "action_proposals_count" in summary
        assert "transition_proposals_count" in summary
        assert "action_proposals" in summary
        assert "transition_proposals" in summary
        assert "data_updates" in summary
        assert "decision" in summary
        assert "turn_duration_ms" in summary

    def test_get_turn_summary_values(self, blackboard):
        """Test get_turn_summary returns correct values."""
        from src.blackboard.enums import Priority
        from src.blackboard.models import ResolvedDecision

        blackboard.propose_action("action1", Priority.HIGH, source_name="S1")
        blackboard.propose_transition("state1", Priority.NORMAL, source_name="S2")
        blackboard.propose_data_update("field1", "value1", "S3")

        decision = ResolvedDecision(action="action1", next_state="state1")
        blackboard.commit_decision(decision)

        summary = blackboard.get_turn_summary()

        assert summary["turn_number"] == 4  # 3 + 1 from begin_turn
        assert summary["intent"] == "agreement"
        assert summary["state"] == "spin_situation"
        assert summary["action_proposals_count"] == 1
        assert summary["transition_proposals_count"] == 1
        assert summary["data_updates"] == {"field1": "value1"}
        assert summary["decision"] is not None
        assert summary["turn_duration_ms"] is not None


# =============================================================================
# Test Objection Skip Logic
# =============================================================================

class TestObjectionSkipLogic:
    """Test _should_skip_objection_recording logic."""

    @pytest.fixture
    def blackboard_with_objections(self):
        """Create a blackboard with objection tracking."""
        from src.blackboard.blackboard import DialogueBlackboard

        sm = MockStateMachine()
        flow_config = MockFlowConfig(states={
            "greeting": {},
            "_limits": {"max_consecutive_objections": 3, "max_total_objections": 5},
        })
        tracker = MockIntentTracker()

        return DialogueBlackboard(
            state_machine=sm,
            flow_config=flow_config,
            intent_tracker=tracker,
        )

    def test_skip_objection_when_consecutive_limit_reached(self, blackboard_with_objections):
        """Test skipping objection recording when consecutive limit reached."""
        bb = blackboard_with_objections

        # Simulate reaching the consecutive limit
        bb._intent_tracker._objection_consecutive = 3
        bb._intent_tracker._objection_total = 3

        # Should skip recording
        with patch('src.yaml_config.constants.OBJECTION_INTENTS', ['objection_price']):
            result = bb._should_skip_objection_recording("objection_price")

        assert result is True

    def test_skip_objection_when_total_limit_reached(self, blackboard_with_objections):
        """Test skipping objection recording when total limit reached."""
        bb = blackboard_with_objections

        # Simulate reaching the total limit
        bb._intent_tracker._objection_consecutive = 1
        bb._intent_tracker._objection_total = 5

        # Should skip recording
        with patch('src.yaml_config.constants.OBJECTION_INTENTS', ['objection_price']):
            result = bb._should_skip_objection_recording("objection_price")

        assert result is True

    def test_no_skip_objection_below_limit(self, blackboard_with_objections):
        """Test not skipping objection recording below limits."""
        bb = blackboard_with_objections

        # Below limits
        bb._intent_tracker._objection_consecutive = 1
        bb._intent_tracker._objection_total = 2

        # Should not skip
        with patch('src.yaml_config.constants.OBJECTION_INTENTS', ['objection_price']):
            result = bb._should_skip_objection_recording("objection_price")

        assert result is False

    def test_no_skip_non_objection_intent(self, blackboard_with_objections):
        """Test not skipping non-objection intents."""
        bb = blackboard_with_objections

        # Even with high counts
        bb._intent_tracker._objection_consecutive = 10
        bb._intent_tracker._objection_total = 20

        # Non-objection should not be skipped
        with patch('src.yaml_config.constants.OBJECTION_INTENTS', ['objection_price']):
            result = bb._should_skip_objection_recording("agreement")

        assert result is False


# =============================================================================
# Test Multi-Tenancy Support
# =============================================================================

class TestMultiTenancy:
    """Test multi-tenancy support."""

    def test_tenant_id_property(self):
        """Test tenant_id property."""
        from src.blackboard.blackboard import DialogueBlackboard
        from src.blackboard.protocols import TenantConfig

        sm = MockStateMachine()
        flow_config = MockFlowConfig()
        tenant = TenantConfig(tenant_id="custom_tenant")

        bb = DialogueBlackboard(
            state_machine=sm,
            flow_config=flow_config,
            tenant_config=tenant,
        )

        assert bb.tenant_id == "custom_tenant"

    def test_tenant_config_property(self):
        """Test tenant_config property."""
        from src.blackboard.blackboard import DialogueBlackboard
        from src.blackboard.protocols import TenantConfig

        sm = MockStateMachine()
        flow_config = MockFlowConfig()
        tenant = TenantConfig(
            tenant_id="test",
            bot_name="TestBot",
            features={"feature1": True},
        )

        bb = DialogueBlackboard(
            state_machine=sm,
            flow_config=flow_config,
            tenant_config=tenant,
        )

        assert bb.tenant_config.bot_name == "TestBot"
        assert bb.tenant_config.features["feature1"] is True

    def test_context_snapshot_includes_tenant_info(self):
        """Test that context snapshot includes tenant info."""
        from src.blackboard.blackboard import DialogueBlackboard
        from src.blackboard.protocols import TenantConfig

        sm = MockStateMachine()
        flow_config = MockFlowConfig()
        tracker = MockIntentTracker()
        tenant = TenantConfig(tenant_id="tenant_abc")

        bb = DialogueBlackboard(
            state_machine=sm,
            flow_config=flow_config,
            intent_tracker=tracker,
            tenant_config=tenant,
        )

        bb.begin_turn(intent="test", extracted_data={})

        ctx = bb.get_context()
        assert ctx.tenant_id == "tenant_abc"
        assert ctx.tenant_config is tenant


# =============================================================================
# Test Package Imports
# =============================================================================

class TestPackageImports:
    """Test that DialogueBlackboard can be imported from package."""

    def test_import_from_package(self):
        """Test importing DialogueBlackboard from src.blackboard."""
        from src.blackboard import DialogueBlackboard

        assert DialogueBlackboard is not None

    def test_in_dunder_all(self):
        """Test that DialogueBlackboard is in __all__."""
        import src.blackboard as bb

        assert "DialogueBlackboard" in bb.__all__


# =============================================================================
# Test Integration with Real Classes
# =============================================================================

class TestRealIntegration:
    """Integration tests with real StateMachine and IntentTracker."""

    def test_with_real_intent_tracker(self):
        """Test DialogueBlackboard with real IntentTracker."""
        from src.blackboard.blackboard import DialogueBlackboard
        from src.intent_tracker import IntentTracker

        sm = MockStateMachine()
        flow_config = MockFlowConfig()
        tracker = IntentTracker()

        bb = DialogueBlackboard(
            state_machine=sm,
            flow_config=flow_config,
            intent_tracker=tracker,
        )

        bb.begin_turn(intent="greeting", extracted_data={})

        assert tracker.turn_number == 1
        assert tracker.last_intent == "greeting"

    def test_with_real_flow_config(self):
        """Test DialogueBlackboard with real FlowConfig."""
        from src.blackboard.blackboard import DialogueBlackboard
        from src.config_loader import FlowConfig

        sm = MockStateMachine()
        flow_config = FlowConfig(
            name="test_flow",
            states={
                "greeting": {"goal": "Greet user"},
                "spin_situation": {"goal": "Gather info", "phase": "situation"},
            },
        )
        tracker = MockIntentTracker()

        bb = DialogueBlackboard(
            state_machine=sm,
            flow_config=flow_config,
            intent_tracker=tracker,
        )

        bb.begin_turn(intent="test", extracted_data={})

        ctx = bb.get_context()
        assert ctx.state_config == {"goal": "Greet user"}


# =============================================================================
# Criteria Verification (from Architectural Plan)
# =============================================================================

class TestStage3CriteriaVerification:
    """
    Verification tests from the plan's CRITERION OF COMPLETION for Stage 3.
    """

    def test_criterion_import_dialogue_blackboard(self):
        """
        Plan criterion: from src.blackboard import DialogueBlackboard
        """
        from src.blackboard import DialogueBlackboard

        assert DialogueBlackboard is not None

    def test_criterion_blackboard_initialization(self):
        """
        Plan criterion: bb = DialogueBlackboard(state_machine, flow_config)
        """
        from src.blackboard import DialogueBlackboard

        sm = MockStateMachine()
        flow_config = MockFlowConfig()

        bb = DialogueBlackboard(state_machine=sm, flow_config=flow_config)

        assert bb._state_machine is sm
        assert bb._flow_config is flow_config

    def test_criterion_begin_turn(self):
        """
        Plan criterion: bb.begin_turn(intent, extracted_data, context_envelope)
        """
        from src.blackboard import DialogueBlackboard

        sm = MockStateMachine()
        flow_config = MockFlowConfig()
        tracker = MockIntentTracker()

        bb = DialogueBlackboard(
            state_machine=sm,
            flow_config=flow_config,
            intent_tracker=tracker,
        )

        bb.begin_turn(
            intent="test_intent",
            extracted_data={"key": "value"},
            context_envelope=None,
        )

        assert bb.current_intent == "test_intent"

    def test_criterion_get_context(self):
        """
        Plan criterion: ctx = bb.get_context()
        """
        from src.blackboard import DialogueBlackboard, ContextSnapshot

        sm = MockStateMachine()
        flow_config = MockFlowConfig()
        tracker = MockIntentTracker()

        bb = DialogueBlackboard(
            state_machine=sm,
            flow_config=flow_config,
            intent_tracker=tracker,
        )
        bb.begin_turn(intent="test", extracted_data={})

        ctx = bb.get_context()

        assert isinstance(ctx, ContextSnapshot)

    def test_criterion_propose_action(self):
        """
        Plan criterion: bb.propose_action("answer_with_pricing", Priority.HIGH, combinable=True)
        """
        from src.blackboard import DialogueBlackboard, Priority

        sm = MockStateMachine()
        flow_config = MockFlowConfig()
        tracker = MockIntentTracker()

        bb = DialogueBlackboard(
            state_machine=sm,
            flow_config=flow_config,
            intent_tracker=tracker,
        )
        bb.begin_turn(intent="test", extracted_data={})

        bb.propose_action("answer_with_pricing", Priority.HIGH, combinable=True)

        proposals = bb.get_action_proposals()
        assert len(proposals) == 1
        assert proposals[0].value == "answer_with_pricing"
        assert proposals[0].priority == Priority.HIGH
        assert proposals[0].combinable is True

    def test_criterion_propose_transition(self):
        """
        Plan criterion: bb.propose_transition("spin_problem", Priority.NORMAL)
        """
        from src.blackboard import DialogueBlackboard, Priority

        sm = MockStateMachine()
        flow_config = MockFlowConfig()
        tracker = MockIntentTracker()

        bb = DialogueBlackboard(
            state_machine=sm,
            flow_config=flow_config,
            intent_tracker=tracker,
        )
        bb.begin_turn(intent="test", extracted_data={})

        bb.propose_transition("spin_problem", Priority.NORMAL)

        proposals = bb.get_transition_proposals()
        assert len(proposals) == 1
        assert proposals[0].value == "spin_problem"
        assert proposals[0].priority == Priority.NORMAL

    def test_criterion_commit_decision(self):
        """
        Plan criterion: bb.commit_decision(decision)
        """
        from src.blackboard import DialogueBlackboard, ResolvedDecision

        sm = MockStateMachine()
        flow_config = MockFlowConfig()
        tracker = MockIntentTracker()

        bb = DialogueBlackboard(
            state_machine=sm,
            flow_config=flow_config,
            intent_tracker=tracker,
        )
        bb.begin_turn(intent="test", extracted_data={})

        decision = ResolvedDecision(action="test_action", next_state="test_state")
        bb.commit_decision(decision)

        stored = bb.get_decision()
        assert stored.action == "test_action"
        assert stored.next_state == "test_state"
