# tests/test_sources_objection_return.py

"""
Tests for ObjectionReturnSource - Phase Preservation after Objection Handling.

These tests verify:
1. ObjectionReturnSource - returns to previous phase after successful objection handling
2. Phase preservation mechanism - _state_before_objection is used correctly
3. Priority-based conflict resolution - HIGH priority wins over YAML transitions
4. Integration with other Knowledge Sources

Root Cause Fixed:
    _state_before_objection was saved but NEVER USED for transitions.
    This caused the bot to get stuck in handle_objection without returning
    to the sales flow phases.

Solution:
    ObjectionReturnSource proposes transitions back to _state_before_objection
    when a positive intent is detected in handle_objection state.
"""

import pytest
from typing import Dict, Any, Optional

from src.blackboard.sources.objection_return import ObjectionReturnSource
from src.blackboard.blackboard import DialogueBlackboard
from src.blackboard.enums import Priority, ProposalType
from src.yaml_config.constants import POSITIVE_INTENTS


# =============================================================================
# Mock Implementations for Testing
# =============================================================================

class MockStateMachine:
    """Mock StateMachine implementing IStateMachine protocol."""

    def __init__(
        self,
        state: str = "greeting",
        collected_data: Optional[Dict[str, Any]] = None,
        state_before_objection: Optional[str] = None
    ):
        self._state = state
        self._collected_data = collected_data or {}
        self._intent_tracker = None
        self._state_before_objection = state_before_objection

    @property
    def state(self) -> str:
        return self._state

    @state.setter
    def state(self, value: str) -> None:
        self._state = value

    @property
    def collected_data(self) -> Dict[str, Any]:
        return self._collected_data


class MockIntentTracker:
    """Mock IntentTracker implementing IIntentTracker protocol."""

    def __init__(
        self,
        turn_number: int = 0,
        objection_consecutive: int = 0,
        objection_total: int = 0
    ):
        self._turn_number = turn_number
        self._prev_intent = None
        self._intents = []
        self._objection_consecutive = objection_consecutive
        self._objection_total = objection_total

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
        return 0


class MockFlowConfig:
    """Mock FlowConfig implementing IFlowConfig protocol."""

    def __init__(self, states: Optional[Dict[str, Dict[str, Any]]] = None):
        self._states = states or {
            "greeting": {"goal": "Greet user", "phase": None},
            "bant_budget": {
                "goal": "Qualify budget",
                "phase": "budget",
            },
            "bant_authority": {
                "goal": "Qualify authority",
                "phase": "authority",
            },
            "handle_objection": {
                "goal": "Handle objection",
                "transitions": {
                    "agreement": "close",
                    "objection_price": "handle_objection",
                }
            },
            "soft_close": {"goal": "Soft close", "is_final": True},
            "close": {"goal": "Close", "is_final": True},
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
        """Get complete state -> phase mapping."""
        result = {v: k for k, v in self.phase_mapping.items()}
        for state_name, state_config in self._states.items():
            explicit_phase = state_config.get("phase") or state_config.get("spin_phase")
            if explicit_phase:
                result[state_name] = explicit_phase
        return result

    def get_phase_for_state(self, state_name: str) -> Optional[str]:
        """Get phase name for a state."""
        return self.state_to_phase.get(state_name)

    def is_phase_state(self, state_name: str) -> bool:
        """Check if a state is a phase state."""
        return self.get_phase_for_state(state_name) is not None


def create_blackboard(
    state: str = "greeting",
    collected_data: Optional[Dict[str, Any]] = None,
    states: Optional[Dict[str, Dict[str, Any]]] = None,
    intent: str = "greeting",
    extracted_data: Optional[Dict[str, Any]] = None,
    state_before_objection: Optional[str] = None,
    objection_consecutive: int = 0,
    objection_total: int = 0,
):
    """Helper to create a blackboard with turn started."""
    sm = MockStateMachine(
        state=state,
        collected_data=collected_data or {},
        state_before_objection=state_before_objection
    )
    flow_config = MockFlowConfig(states=states)
    tracker = MockIntentTracker(
        objection_consecutive=objection_consecutive,
        objection_total=objection_total
    )

    bb = DialogueBlackboard(
        state_machine=sm,
        flow_config=flow_config,
        intent_tracker=tracker,
    )
    bb.begin_turn(intent=intent, extracted_data=extracted_data or {})
    return bb


# =============================================================================
# Tests for ObjectionReturnSource Initialization
# =============================================================================

class TestObjectionReturnSourceInit:
    """Test ObjectionReturnSource initialization."""

    def test_init_default(self):
        """Test default initialization."""
        source = ObjectionReturnSource()

        assert source.name == "ObjectionReturnSource"
        assert source.enabled is True
        assert len(source.return_intents) > 0

    def test_init_with_custom_name(self):
        """Test initialization with custom name."""
        source = ObjectionReturnSource(name="CustomReturnSource")

        assert source.name == "CustomReturnSource"

    def test_init_with_custom_return_intents(self):
        """Test initialization with custom return intents."""
        custom_intents = {"agreement", "interest", "custom_positive"}
        source = ObjectionReturnSource(return_intents=custom_intents)

        assert source.return_intents == custom_intents

    def test_init_disabled(self):
        """Test initialization with disabled state."""
        source = ObjectionReturnSource(enabled=False)

        assert source.enabled is False

    def test_default_return_intents_are_positive_intents(self):
        """Test that default return intents match POSITIVE_INTENTS."""
        source = ObjectionReturnSource()

        assert source.return_intents == set(POSITIVE_INTENTS)
        assert "agreement" in source.return_intents
        assert "demo_request" in source.return_intents


# =============================================================================
# Tests for ObjectionReturnSource should_contribute
# =============================================================================

class TestObjectionReturnSourceShouldContribute:
    """Test ObjectionReturnSource should_contribute logic."""

    @pytest.fixture
    def source(self):
        """Create an ObjectionReturnSource instance."""
        return ObjectionReturnSource()

    def test_should_contribute_true_when_all_conditions_met(self, source):
        """should_contribute returns True when all conditions are met."""
        bb = create_blackboard(
            state="handle_objection",
            intent="agreement",
            state_before_objection="bant_budget"
        )

        assert source.should_contribute(bb) is True

    def test_should_contribute_false_when_not_handle_objection_state(self, source):
        """should_contribute returns False when not in handle_objection state."""
        bb = create_blackboard(
            state="bant_budget",
            intent="agreement",
            state_before_objection="bant_budget"
        )

        assert source.should_contribute(bb) is False

    def test_should_contribute_false_when_no_saved_state(self, source):
        """should_contribute returns False when no _state_before_objection."""
        bb = create_blackboard(
            state="handle_objection",
            intent="agreement",
            state_before_objection=None
        )

        assert source.should_contribute(bb) is False

    def test_should_contribute_false_when_not_positive_intent(self, source):
        """should_contribute returns False when intent is not positive."""
        bb = create_blackboard(
            state="handle_objection",
            intent="objection_price",
            state_before_objection="bant_budget"
        )

        assert source.should_contribute(bb) is False

    def test_should_contribute_false_when_disabled(self, source):
        """should_contribute returns False when source is disabled."""
        source.disable()
        bb = create_blackboard(
            state="handle_objection",
            intent="agreement",
            state_before_objection="bant_budget"
        )

        assert source.should_contribute(bb) is False

    def test_should_contribute_for_various_positive_intents(self, source):
        """should_contribute returns True for various positive intents."""
        positive_intents = ["agreement", "info_provided", "demo_request", "callback_request"]

        for intent in positive_intents:
            bb = create_blackboard(
                state="handle_objection",
                intent=intent,
                state_before_objection="bant_budget"
            )
            assert source.should_contribute(bb) is True, f"Failed for intent: {intent}"


# =============================================================================
# Tests for ObjectionReturnSource contribute
# =============================================================================

class TestObjectionReturnSourceContribute:
    """Test ObjectionReturnSource contribute logic."""

    @pytest.fixture
    def source(self):
        """Create an ObjectionReturnSource instance."""
        return ObjectionReturnSource()

    def test_contribute_proposes_transition_to_saved_state(self, source):
        """contribute should propose transition back to saved state."""
        bb = create_blackboard(
            state="handle_objection",
            intent="agreement",
            state_before_objection="bant_budget"
        )

        source.contribute(bb)

        proposals = bb.get_transition_proposals()
        assert len(proposals) == 1
        assert proposals[0].value == "bant_budget"

    def test_contribute_uses_high_priority(self, source):
        """contribute should use HIGH priority to win over YAML transitions."""
        bb = create_blackboard(
            state="handle_objection",
            intent="agreement",
            state_before_objection="bant_budget"
        )

        source.contribute(bb)

        proposals = bb.get_transition_proposals()
        assert proposals[0].priority == Priority.HIGH

    def test_contribute_no_proposal_when_disabled(self, source):
        """contribute should not propose when disabled."""
        source.disable()
        bb = create_blackboard(
            state="handle_objection",
            intent="agreement",
            state_before_objection="bant_budget"
        )

        source.contribute(bb)

        assert len(bb.get_transition_proposals()) == 0

    def test_contribute_no_proposal_when_no_saved_state(self, source):
        """contribute should not propose when no saved state."""
        bb = create_blackboard(
            state="handle_objection",
            intent="agreement",
            state_before_objection=None
        )

        source.contribute(bb)

        assert len(bb.get_transition_proposals()) == 0

    def test_contribute_returns_to_different_phase_states(self, source):
        """contribute should return to various phase states correctly."""
        phase_states = ["bant_budget", "bant_authority"]

        for saved_state in phase_states:
            bb = create_blackboard(
                state="handle_objection",
                intent="agreement",
                state_before_objection=saved_state
            )

            source.contribute(bb)

            proposals = bb.get_transition_proposals()
            assert len(proposals) == 1
            assert proposals[0].value == saved_state, f"Failed for saved_state: {saved_state}"


# =============================================================================
# Tests for ObjectionReturnSource Metadata
# =============================================================================

class TestObjectionReturnSourceMetadata:
    """Test ObjectionReturnSource metadata in proposals."""

    @pytest.fixture
    def source(self):
        """Create an ObjectionReturnSource instance."""
        return ObjectionReturnSource()

    def test_metadata_includes_from_state(self, source):
        """Metadata should include from_state."""
        bb = create_blackboard(
            state="handle_objection",
            intent="agreement",
            state_before_objection="bant_budget"
        )

        source.contribute(bb)

        proposals = bb.get_transition_proposals()
        metadata = proposals[0].metadata

        assert metadata["from_state"] == "handle_objection"

    def test_metadata_includes_to_state(self, source):
        """Metadata should include to_state."""
        bb = create_blackboard(
            state="handle_objection",
            intent="agreement",
            state_before_objection="bant_budget"
        )

        source.contribute(bb)

        proposals = bb.get_transition_proposals()
        metadata = proposals[0].metadata

        assert metadata["to_state"] == "bant_budget"

    def test_metadata_includes_trigger_intent(self, source):
        """Metadata should include trigger_intent."""
        bb = create_blackboard(
            state="handle_objection",
            intent="agreement",
            state_before_objection="bant_budget"
        )

        source.contribute(bb)

        proposals = bb.get_transition_proposals()
        metadata = proposals[0].metadata

        assert metadata["trigger_intent"] == "agreement"

    def test_metadata_includes_target_phase(self, source):
        """Metadata should include target_phase."""
        bb = create_blackboard(
            state="handle_objection",
            intent="agreement",
            state_before_objection="bant_budget"
        )

        source.contribute(bb)

        proposals = bb.get_transition_proposals()
        metadata = proposals[0].metadata

        assert metadata["target_phase"] == "budget"

    def test_metadata_includes_mechanism(self, source):
        """Metadata should include mechanism identifier."""
        bb = create_blackboard(
            state="handle_objection",
            intent="agreement",
            state_before_objection="bant_budget"
        )

        source.contribute(bb)

        proposals = bb.get_transition_proposals()
        metadata = proposals[0].metadata

        assert metadata["mechanism"] == "objection_return"

    def test_reason_code_is_objection_return_to_phase(self, source):
        """Proposal should have correct reason_code."""
        bb = create_blackboard(
            state="handle_objection",
            intent="agreement",
            state_before_objection="bant_budget"
        )

        source.contribute(bb)

        proposals = bb.get_transition_proposals()
        assert proposals[0].reason_code == "objection_return_to_phase"


# =============================================================================
# Tests for ObjectionReturnSource Enable/Disable
# =============================================================================

class TestObjectionReturnSourceEnableDisable:
    """Test ObjectionReturnSource enable/disable functionality."""

    def test_enable_source(self):
        """Test enabling source."""
        source = ObjectionReturnSource(enabled=False)
        source.enable()

        assert source.enabled is True

    def test_disable_source(self):
        """Test disabling source."""
        source = ObjectionReturnSource()
        source.disable()

        assert source.enabled is False

    def test_disabled_source_should_not_contribute(self):
        """Disabled source should return False from should_contribute."""
        bb = create_blackboard(
            state="handle_objection",
            intent="agreement",
            state_before_objection="bant_budget"
        )
        source = ObjectionReturnSource()
        source.disable()

        assert source.should_contribute(bb) is False

    def test_disabled_source_no_contribution(self):
        """Disabled source should not contribute even when conditions met."""
        bb = create_blackboard(
            state="handle_objection",
            intent="agreement",
            state_before_objection="bant_budget"
        )
        source = ObjectionReturnSource()
        source.disable()

        source.contribute(bb)

        assert len(bb.get_transition_proposals()) == 0


# =============================================================================
# Tests for Phase Preservation Scenarios
# =============================================================================

class TestPhasePreservationScenarios:
    """Test real-world phase preservation scenarios."""

    @pytest.fixture
    def source(self):
        """Create an ObjectionReturnSource instance."""
        return ObjectionReturnSource()

    def test_budget_phase_preserved_after_objection(self, source):
        """
        Scenario: Client was in bant_budget, raised objection, then agreed.
        Expected: Return to bant_budget, not to close.
        """
        bb = create_blackboard(
            state="handle_objection",
            intent="agreement",
            state_before_objection="bant_budget"
        )

        source.contribute(bb)

        proposals = bb.get_transition_proposals()
        assert len(proposals) == 1
        assert proposals[0].value == "bant_budget"  # Phase preserved!

    def test_authority_phase_preserved_after_objection(self, source):
        """
        Scenario: Client was in bant_authority, raised objection, showed positive signal.
        Expected: Return to bant_authority.
        """
        bb = create_blackboard(
            state="handle_objection",
            intent="info_provided",
            state_before_objection="bant_authority"
        )

        source.contribute(bb)

        proposals = bb.get_transition_proposals()
        assert len(proposals) == 1
        assert proposals[0].value == "bant_authority"

    def test_no_return_when_objection_continues(self, source):
        """
        Scenario: Client raises another objection (not positive intent).
        Expected: No return transition proposed.
        """
        bb = create_blackboard(
            state="handle_objection",
            intent="objection_competitor",
            state_before_objection="bant_budget"
        )

        source.contribute(bb)

        assert len(bb.get_transition_proposals()) == 0

    def test_demo_request_triggers_return(self, source):
        """
        Scenario: Client requests demo after objection handling.
        Expected: Return to saved state (demo_request is positive intent).
        """
        bb = create_blackboard(
            state="handle_objection",
            intent="demo_request",
            state_before_objection="bant_budget"
        )

        source.contribute(bb)

        proposals = bb.get_transition_proposals()
        assert len(proposals) == 1
        assert proposals[0].value == "bant_budget"


# =============================================================================
# Tests for Priority-Based Conflict Resolution
# =============================================================================

class TestPriorityBasedResolution:
    """Test that ObjectionReturnSource wins over YAML transitions."""

    @pytest.fixture
    def source(self):
        """Create an ObjectionReturnSource instance."""
        return ObjectionReturnSource()

    def test_proposal_has_high_priority(self, source):
        """Proposal should have HIGH priority."""
        bb = create_blackboard(
            state="handle_objection",
            intent="agreement",
            state_before_objection="bant_budget"
        )

        source.contribute(bb)

        proposals = bb.get_transition_proposals()
        assert proposals[0].priority == Priority.HIGH

    def test_high_priority_wins_over_normal(self, source):
        """
        HIGH priority should win over NORMAL (YAML transitions).

        This is validated by checking the priority level - conflict
        resolution is handled by ConflictResolver which gives precedence
        to higher priority (lower enum value).
        """
        bb = create_blackboard(
            state="handle_objection",
            intent="agreement",
            state_before_objection="bant_budget"
        )

        source.contribute(bb)

        proposals = bb.get_transition_proposals()
        # HIGH = 1, NORMAL = 2, so HIGH wins
        assert proposals[0].priority == Priority.HIGH
        assert Priority.HIGH < Priority.NORMAL  # Lower value = higher priority


# =============================================================================
# Tests for Edge Cases
# =============================================================================

class TestEdgeCases:
    """Test edge cases and error handling."""

    @pytest.fixture
    def source(self):
        """Create an ObjectionReturnSource instance."""
        return ObjectionReturnSource()

    def test_saved_state_not_in_flow_config(self, source):
        """
        Edge case: Saved state no longer exists in flow config.
        Expected: No transition proposed (validation fails).
        """
        states = {
            "handle_objection": {"goal": "Handle objection"},
            "greeting": {"goal": "Greet user"},
            # Note: bant_budget is NOT in states
        }
        bb = create_blackboard(
            state="handle_objection",
            intent="agreement",
            state_before_objection="bant_budget",
            states=states
        )

        source.contribute(bb)

        # Should not propose transition to non-existent state
        assert len(bb.get_transition_proposals()) == 0

    def test_empty_return_intents(self):
        """Edge case: Source initialized with empty return intents."""
        source = ObjectionReturnSource(return_intents=set())
        bb = create_blackboard(
            state="handle_objection",
            intent="agreement",
            state_before_objection="bant_budget"
        )

        # should_contribute should return False
        assert source.should_contribute(bb) is False

    def test_multiple_contributes_same_turn(self, source):
        """Multiple contribute calls in same turn should be idempotent-ish."""
        bb = create_blackboard(
            state="handle_objection",
            intent="agreement",
            state_before_objection="bant_budget"
        )

        source.contribute(bb)
        source.contribute(bb)
        source.contribute(bb)

        # Should have 3 proposals (each contribute adds one)
        # This is expected behavior - proposals are additive
        proposals = bb.get_transition_proposals()
        assert len(proposals) == 3
        # All should be the same
        for p in proposals:
            assert p.value == "bant_budget"


# =============================================================================
# Tests for Source Name
# =============================================================================

class TestSourceName:
    """Test ObjectionReturnSource naming."""

    def test_source_name_in_proposal(self):
        """Proposal should include source name."""
        source = ObjectionReturnSource()
        bb = create_blackboard(
            state="handle_objection",
            intent="agreement",
            state_before_objection="bant_budget"
        )

        source.contribute(bb)

        proposals = bb.get_transition_proposals()
        assert proposals[0].source_name == "ObjectionReturnSource"

    def test_custom_source_name_in_proposal(self):
        """Custom source name should appear in proposal."""
        source = ObjectionReturnSource(name="CustomReturn")
        bb = create_blackboard(
            state="handle_objection",
            intent="agreement",
            state_before_objection="bant_budget"
        )

        source.contribute(bb)

        proposals = bb.get_transition_proposals()
        assert proposals[0].source_name == "CustomReturn"
