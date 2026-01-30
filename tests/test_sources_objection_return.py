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
from src.yaml_config.constants import POSITIVE_INTENTS, PRICE_RELATED_INTENTS, OBJECTION_RETURN_TRIGGERS


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

    def __init__(
        self,
        states: Optional[Dict[str, Dict[str, Any]]] = None,
        variables: Optional[Dict[str, Any]] = None
    ):
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
        # Default entry_state for testing fallback behavior
        self.variables = variables if variables is not None else {
            "entry_state": "bant_budget"
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
    variables: Optional[Dict[str, Any]] = None,
):
    """Helper to create a blackboard with turn started."""
    sm = MockStateMachine(
        state=state,
        collected_data=collected_data or {},
        state_before_objection=state_before_objection
    )
    flow_config = MockFlowConfig(states=states, variables=variables)
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

    def test_default_return_intents_match_ssot(self):
        """Test that default return intents match OBJECTION_RETURN_TRIGGERS from SSOT."""
        source = ObjectionReturnSource()
        expected = set(OBJECTION_RETURN_TRIGGERS)
        assert source.return_intents == expected
        # Verify key intents are included
        assert "agreement" in source.return_intents        # from positive
        assert "price_question" in source.return_intents   # from price_related
        assert "pricing_details" in source.return_intents  # from price_related
        assert "question_features" in source.return_intents # from positive
        assert "question_implementation" in source.return_intents  # from objection_return_questions
        assert "question_demo" in source.return_intents    # from objection_return_questions
        # Verify typos are gone
        assert "question_pricing" not in source.return_intents
        assert "question_integration" not in source.return_intents


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


# =============================================================================
# Tests for Non-Phase State Handling (37% Zero Coverage Fix)
# =============================================================================

class TestNonPhaseStateHandling:
    """
    Test that ObjectionReturnSource does NOT return to non-phase states.

    Root Cause (commit 293109e):
        ObjectionReturnSource was proposing HIGH priority transitions back to
        saved states like "greeting" which have NO phase. This won over
        TransitionResolver's NORMAL priority (e.g., agreement → close).

    Result of bug:
        greeting ↔ handle_objection loop → phases_reached = [] → 37% zero coverage

    Affected personas: skeptic, tire_kicker, competitor_user, aggressive
        (all express objections BEFORE entering a phase, so _state_before_objection
        gets saved as "greeting" which has no phase)

    Solution:
        Only propose return transitions to states that have a SPIN phase.
        For non-phase states, let TransitionResolver handle the transition.
    """

    @pytest.fixture
    def source(self):
        """Create an ObjectionReturnSource instance."""
        return ObjectionReturnSource()

    def test_no_return_to_greeting_state_fallback_to_entry(self, source):
        """
        CRITICAL FIX: Do NOT return to 'greeting' which has no phase.
        Instead, propose entry_state as LOW priority fallback.

        Scenario (skeptic persona):
            1. greeting + "не уверен" → objection_think
            2. _state_before_objection = "greeting"
            3. handle_objection + "ладно" → agreement
            4. ObjectionReturnSource proposes entry_state (LOW priority fallback)
            5. TransitionResolver proposes close (NORMAL priority) - WINS
            6. If no explicit transition, entry_state fallback is used

        This prevents:
        - greeting ↔ handle_objection loop (bot can progress)
        - Allows explicit transitions (agreement → close) to win
        """
        bb = create_blackboard(
            state="handle_objection",
            intent="agreement",
            state_before_objection="greeting"  # Non-phase state!
        )

        source.contribute(bb)

        # Should propose entry_state (bant_budget) as fallback, NOT greeting
        proposals = bb.get_transition_proposals()
        assert len(proposals) == 1, \
            "ObjectionReturnSource should propose entry_state fallback for non-phase state"
        assert proposals[0].value == "bant_budget", \
            "Should propose entry_state (bant_budget) not greeting"
        assert proposals[0].priority == Priority.NORMAL, \
            "Fallback should be NORMAL priority to win over TransitionResolver"

    def test_no_return_to_handle_objection_state_fallback(self, source):
        """
        Edge case: _state_before_objection is handle_objection itself.
        Should fallback to entry_state.
        """
        bb = create_blackboard(
            state="handle_objection",
            intent="agreement",
            state_before_objection="handle_objection"  # Non-phase state!
        )

        source.contribute(bb)

        proposals = bb.get_transition_proposals()
        assert len(proposals) == 1
        assert proposals[0].value == "bant_budget"  # entry_state fallback
        assert proposals[0].priority == Priority.NORMAL  # FIX: NORMAL to win over TransitionResolver

    def test_no_return_to_soft_close_state_fallback(self, source):
        """
        Edge case: _state_before_objection is soft_close (final, no phase).
        Should fallback to entry_state.
        """
        bb = create_blackboard(
            state="handle_objection",
            intent="agreement",
            state_before_objection="soft_close"  # Non-phase state!
        )

        source.contribute(bb)

        proposals = bb.get_transition_proposals()
        assert len(proposals) == 1
        assert proposals[0].value == "bant_budget"  # entry_state fallback
        assert proposals[0].priority == Priority.NORMAL  # FIX: NORMAL to win over TransitionResolver

    def test_no_return_to_close_state_fallback(self, source):
        """
        Edge case: _state_before_objection is close (final, no phase).
        Should fallback to entry_state.
        """
        bb = create_blackboard(
            state="handle_objection",
            intent="agreement",
            state_before_objection="close"  # Non-phase state!
        )

        source.contribute(bb)

        proposals = bb.get_transition_proposals()
        assert len(proposals) == 1
        assert proposals[0].value == "bant_budget"  # entry_state fallback
        assert proposals[0].priority == Priority.NORMAL  # FIX: NORMAL to win over TransitionResolver

    def test_no_fallback_without_entry_state(self, source):
        """
        Edge case: No entry_state defined in flow_config.
        Should not propose any transition (delegate to TransitionResolver).
        """
        bb = create_blackboard(
            state="handle_objection",
            intent="agreement",
            state_before_objection="greeting",
            variables={}  # No entry_state
        )

        source.contribute(bb)

        proposals = bb.get_transition_proposals()
        assert len(proposals) == 0, \
            "Without entry_state, should delegate to TransitionResolver"

    def test_returns_to_phase_state_bant_budget(self, source):
        """
        Verify: Still returns to phase states like bant_budget.

        bant_budget has phase="budget", so it should work.
        """
        bb = create_blackboard(
            state="handle_objection",
            intent="agreement",
            state_before_objection="bant_budget"  # Has phase!
        )

        source.contribute(bb)

        proposals = bb.get_transition_proposals()
        assert len(proposals) == 1
        assert proposals[0].value == "bant_budget"

    def test_returns_to_phase_state_bant_authority(self, source):
        """
        Verify: Still returns to phase states like bant_authority.

        bant_authority has phase="authority", so it should work.
        """
        bb = create_blackboard(
            state="handle_objection",
            intent="agreement",
            state_before_objection="bant_authority"  # Has phase!
        )

        source.contribute(bb)

        proposals = bb.get_transition_proposals()
        assert len(proposals) == 1
        assert proposals[0].value == "bant_authority"

    def test_skeptic_persona_scenario(self, source):
        """
        Full skeptic persona scenario that caused 0% phase coverage.

        Flow without fix:
            1. greeting → "не уверен" → objection_think
            2. greeting → handle_objection (save greeting)
            3. handle_objection → "ладно" → agreement
            4. ObjectionReturnSource: handle_objection → greeting (HIGH)
            5. TransitionResolver: handle_objection → close (NORMAL)
            6. HIGH wins → greeting (WRONG!)
            7. Loop repeats, never enters SPIN phases

        Flow with fix:
            1-3. Same
            4. ObjectionReturnSource: entry_state fallback (NORMAL)
            5. TransitionResolver: handle_objection → close (NORMAL)
            6. ObjectionReturnSource runs first (priority_order 35 < 50) → entry_state wins
            7. Conversation continues to phase states → proper phase coverage
        """
        bb = create_blackboard(
            state="handle_objection",
            intent="agreement",
            state_before_objection="greeting"
        )

        source.contribute(bb)

        # ObjectionReturnSource proposes entry_state fallback (NORMAL priority)
        proposals = bb.get_transition_proposals()
        assert len(proposals) == 1
        assert proposals[0].value == "bant_budget"  # entry_state fallback
        assert proposals[0].priority == Priority.NORMAL  # Will win (runs before TransitionResolver)

        # ObjectionReturnSource runs before TransitionResolver → entry_state wins

    def test_tire_kicker_persona_scenario(self, source):
        """
        tire_kicker: "Просто смотрю" → objection_no_need before entering phase.
        Proposes entry_state fallback with NORMAL priority to win over TransitionResolver.
        """
        bb = create_blackboard(
            state="handle_objection",
            intent="agreement",
            state_before_objection="greeting"
        )

        source.contribute(bb)

        proposals = bb.get_transition_proposals()
        assert len(proposals) == 1
        assert proposals[0].value == "bant_budget"
        assert proposals[0].priority == Priority.NORMAL  # FIX: NORMAL to win

    def test_competitor_user_persona_scenario(self, source):
        """
        competitor_user: "У нас уже есть решение" → objection_competitor before phase.
        Proposes entry_state fallback with NORMAL priority to win over TransitionResolver.
        """
        bb = create_blackboard(
            state="handle_objection",
            intent="info_provided",  # Shows positive signal after objection handling
            state_before_objection="greeting"
        )

        source.contribute(bb)

        proposals = bb.get_transition_proposals()
        assert len(proposals) == 1
        assert proposals[0].value == "bant_budget"
        assert proposals[0].priority == Priority.NORMAL  # FIX: NORMAL to win

    def test_aggressive_persona_scenario(self, source):
        """
        aggressive: Negative message → objection_* before entering phase.
        Proposes entry_state fallback with NORMAL priority to win over TransitionResolver.
        """
        bb = create_blackboard(
            state="handle_objection",
            intent="info_provided",  # Provides info after calming down
            state_before_objection="greeting"
        )

        source.contribute(bb)

        proposals = bb.get_transition_proposals()
        assert len(proposals) == 1
        assert proposals[0].value == "bant_budget"
        assert proposals[0].priority == Priority.NORMAL  # FIX: NORMAL to win


# =============================================================================
# Tests for Phase Transition with Custom FlowConfig
# =============================================================================

class TestPhaseTransitionWithCustomFlowConfig:
    """
    Test ObjectionReturnSource with various FlowConfig configurations.

    These tests verify that the phase detection works correctly with
    different state-to-phase mappings.
    """

    @pytest.fixture
    def source(self):
        """Create an ObjectionReturnSource instance."""
        return ObjectionReturnSource()

    def test_spin_phases_return_works(self, source):
        """Test that SPIN phase states (situation, problem, etc.) allow return."""
        spin_states = {
            "greeting": {"goal": "Greet"},
            "spin_situation": {"goal": "Qualify situation", "phase": "situation"},
            "spin_problem": {"goal": "Qualify problem", "phase": "problem"},
            "spin_implication": {"goal": "Qualify implication", "phase": "implication"},
            "spin_need_payoff": {"goal": "Qualify need", "phase": "need_payoff"},
            "handle_objection": {"goal": "Handle objection"},
        }
        spin_variables = {"entry_state": "spin_situation"}

        for state_name, state_config in spin_states.items():
            if state_config.get("phase") is None:
                continue  # Skip non-phase states

            bb = create_blackboard(
                state="handle_objection",
                intent="agreement",
                state_before_objection=state_name,
                states=spin_states,
                variables=spin_variables
            )

            source.contribute(bb)

            proposals = bb.get_transition_proposals()
            assert len(proposals) == 1, f"Should return to {state_name}"
            assert proposals[0].value == state_name

    def test_only_phase_states_get_return_with_fallback(self, source):
        """Test that states WITH phase get HIGH priority return, without get NORMAL fallback."""
        mixed_states = {
            "greeting": {"goal": "Greet"},  # No phase
            "qualification": {"goal": "Qualify", "phase": "qualify"},  # Has phase
            "handle_objection": {"goal": "Handle objection"},  # No phase
            "presentation": {"goal": "Present", "phase": "present"},  # Has phase
            "close": {"goal": "Close"},  # No phase
        }
        # entry_state is qualification (has phase)
        mixed_variables = {"entry_state": "qualification"}

        # States with phase should get HIGH priority return to SAME state
        for state_with_phase in ["qualification", "presentation"]:
            bb = create_blackboard(
                state="handle_objection",
                intent="agreement",
                state_before_objection=state_with_phase,
                states=mixed_states,
                variables=mixed_variables
            )
            source.contribute(bb)
            proposals = bb.get_transition_proposals()
            assert len(proposals) == 1
            assert proposals[0].value == state_with_phase  # Return to saved state
            assert proposals[0].priority == Priority.HIGH  # HIGH priority

        # States without phase should get NORMAL priority fallback to entry_state
        # FIX: Changed from LOW to NORMAL so that entry_state wins over TransitionResolver
        for state_without_phase in ["greeting", "close"]:
            bb = create_blackboard(
                state="handle_objection",
                intent="agreement",
                state_before_objection=state_without_phase,
                states=mixed_states,
                variables=mixed_variables
            )
            source.contribute(bb)
            proposals = bb.get_transition_proposals()
            assert len(proposals) == 1
            assert proposals[0].value == "qualification"  # Fallback to entry_state
            assert proposals[0].priority == Priority.NORMAL  # NORMAL priority (FIX: was LOW)


# =============================================================================
# Tests for Objection Loop Escape (Zero Phase Coverage Fix)
# =============================================================================

class TestObjectionLoopEscape:
    """
    Test that ObjectionReturnSource escapes from objection loop.

    Root Cause (zero phase coverage for tire_kicker/aggressive):
        1. Persona starts with objection in greeting state
        2. _state_before_objection = "greeting" (no phase)
        3. ObjectionReturnSource only triggered on POSITIVE intent
        4. tire_kicker (90% objection prob) / aggressive (70%) NEVER give positive intent
        5. Stuck in handle_objection → handle_objection loop
        6. Eventually objection_limit_reached → soft_close with 0% coverage

    Solution:
        When stuck in objection loop (3+ consecutive objections from non-phase state),
        force exit to entry_state even without positive intent.
        This allows client to enter sales phases instead of going to soft_close.

    Affected personas: tire_kicker, aggressive, price_sensitive
        (all have high objection probability and may never give positive response)
    """

    @pytest.fixture
    def source(self):
        """Create an ObjectionReturnSource instance."""
        return ObjectionReturnSource()

    def test_should_contribute_true_for_objection_loop_escape(self, source):
        """
        should_contribute returns True when stuck in objection loop.

        Conditions:
        1. Current state is handle_objection
        2. _state_before_objection is set (non-phase state like greeting)
        3. Current intent is objection (NOT positive)
        4. 3+ consecutive objections
        """
        bb = create_blackboard(
            state="handle_objection",
            intent="objection_think",  # NOT positive intent!
            state_before_objection="greeting",  # Non-phase state
            objection_consecutive=3  # 3+ consecutive objections
        )

        # should_contribute should return True for objection loop escape
        assert source.should_contribute(bb) is True

    def test_should_contribute_false_below_threshold(self, source):
        """
        should_contribute returns False when below escape threshold.

        Note: begin_turn() calls tracker.record() which increments consecutive
        for objection intents. So if we start with consecutive=1, after record()
        it becomes 2, which is still below threshold (3).
        """
        bb = create_blackboard(
            state="handle_objection",
            intent="objection_price",
            state_before_objection="greeting",
            objection_consecutive=1  # After record() it will be 2, below threshold (3)
        )

        assert source.should_contribute(bb) is False

    def test_should_contribute_false_for_phase_state(self, source):
        """
        should_contribute returns False for objection when came from phase state.

        If we came from a phase state (like bant_budget), we should wait for
        positive intent to return there, not force exit.
        """
        bb = create_blackboard(
            state="handle_objection",
            intent="objection_price",
            state_before_objection="bant_budget",  # HAS phase
            objection_consecutive=3
        )

        assert source.should_contribute(bb) is False

    def test_contribute_proposes_entry_state_on_objection_escape(self, source):
        """
        contribute proposes entry_state when objection loop escape triggered.
        """
        bb = create_blackboard(
            state="handle_objection",
            intent="objection_no_time",  # Objection intent
            state_before_objection="greeting",  # Non-phase state
            objection_consecutive=3  # Triggers escape
        )

        source.contribute(bb)

        proposals = bb.get_transition_proposals()
        assert len(proposals) == 1
        assert proposals[0].value == "bant_budget"  # entry_state
        assert proposals[0].priority == Priority.NORMAL
        assert proposals[0].reason_code == "objection_loop_escape_to_entry_state"

    def test_contribute_metadata_includes_escape_info(self, source):
        """
        contribute metadata includes objection loop escape information.
        """
        bb = create_blackboard(
            state="handle_objection",
            intent="objection_think",
            state_before_objection="greeting",
            objection_consecutive=4
        )

        source.contribute(bb)

        proposals = bb.get_transition_proposals()
        metadata = proposals[0].metadata

        assert metadata["is_objection_loop_escape"] is True
        assert metadata["consecutive_objections"] == 4
        assert metadata["mechanism"] == "objection_loop_escape"

    def test_tire_kicker_scenario_objection_escape(self, source):
        """
        Full tire_kicker scenario: always objects, never positive.

        tire_kicker: 90% objection probability, max_turns=6
        Typical flow without fix:
            Turn 1: greeting + "потом посмотрю" → objection_think
            Turn 2: handle_objection + "не грузите" → objection_no_time
            Turn 3: handle_objection + "неинтересно" → objection_no_need
            Turn 4: handle_objection + "перезвоню" → objection_think
            Turn 5: handle_objection + "хватит" → objection_no_time
            Turn 6: handle_objection → max_turns reached → 0% coverage

        With fix (objection_loop_escape at turn 3):
            Turn 1-2: Same
            Turn 3: objection_consecutive >= 3, non-phase state
                    → objection_loop_escape → entry_state
            Turn 4+: Client is in phase state, can progress
        """
        bb = create_blackboard(
            state="handle_objection",
            intent="objection_no_need",  # 3rd consecutive objection
            state_before_objection="greeting",
            objection_consecutive=3
        )

        source.contribute(bb)

        proposals = bb.get_transition_proposals()
        assert len(proposals) == 1
        assert proposals[0].value == "bant_budget"  # Forces exit to phase
        assert "objection_loop_escape" in proposals[0].reason_code

    def test_aggressive_scenario_objection_escape(self, source):
        """
        aggressive: 70% objection probability, rude and impatient.

        Without fix: high chance of 0% coverage (stuck in objection loop).
        With fix: escape to entry_state after 3 consecutive objections.
        """
        bb = create_blackboard(
            state="handle_objection",
            intent="objection_no_time",  # "Не грузите меня"
            state_before_objection="greeting",
            objection_consecutive=3
        )

        source.contribute(bb)

        proposals = bb.get_transition_proposals()
        assert len(proposals) == 1
        assert proposals[0].value == "bant_budget"

    def test_positive_intent_still_works_normally(self, source):
        """
        Verify: Positive intent still triggers normal return (not escape).

        When client gives positive intent, use normal return mechanism,
        not objection loop escape.
        """
        bb = create_blackboard(
            state="handle_objection",
            intent="agreement",  # POSITIVE intent
            state_before_objection="greeting",
            objection_consecutive=0  # Streak reset by positive intent
        )

        source.contribute(bb)

        proposals = bb.get_transition_proposals()
        assert len(proposals) == 1
        assert proposals[0].value == "bant_budget"  # entry_state fallback
        # Should be normal fallback, not escape
        assert proposals[0].reason_code == "objection_return_to_entry_state"

    def test_escape_threshold_is_configurable(self):
        """
        Verify: Escape threshold can be configured.
        """
        from src.blackboard.sources.objection_return import OBJECTION_LOOP_ESCAPE_THRESHOLD

        # Default is 3
        assert OBJECTION_LOOP_ESCAPE_THRESHOLD == 3


# =============================================================================
# Tests for Total-Based Objection Escape (Meta-Intent Streak Breaking Fix)
# =============================================================================

class TestTotalBasedObjectionEscape:
    """
    Test that ObjectionReturnSource escapes when total objections approach limit,
    even when consecutive streak is broken by meta-intents.

    Root Cause (secondary zero phase coverage bug):
        1. Persona starts with objection in greeting state
        2. _state_before_objection = "greeting" (no phase)
        3. Meta-intents like request_brevity break consecutive objection streak
        4. Consecutive never reaches 3 (OBJECTION_LOOP_ESCAPE_THRESHOLD)
        5. But total keeps accumulating
        6. When total reaches max_total_objections (5), objection_limit_reached fires
        7. objection_limit_reached → soft_close → 0% coverage

    Solution:
        Fire escape when total objections approach limit (max_total - 1 = 4).
        This ensures escape fires BEFORE objection_limit_reached,
        routing to entry_state instead of soft_close.

    Affected scenario:
        Turn 1: objection_price   → consecutive=1, total=1
        Turn 2: objection_think   → consecutive=2, total=2
        Turn 3: request_brevity   → consecutive=0 (RESET!), total=2
        Turn 4: objection_trust   → consecutive=1, total=3
        Turn 5: objection_price   → consecutive=2, total=4
                → total >= 4 (OBJECTION_TOTAL_ESCAPE_THRESHOLD)
                → Total escape fires → entry_state ✓
    """

    @pytest.fixture
    def source(self):
        """Create an ObjectionReturnSource instance."""
        return ObjectionReturnSource()

    def test_total_escape_threshold_is_correct(self):
        """
        Verify: Total escape threshold = max_total_objections - 1.
        """
        from src.blackboard.sources.objection_return import (
            OBJECTION_TOTAL_ESCAPE_THRESHOLD,
        )
        from src.yaml_config.constants import MAX_TOTAL_OBJECTIONS

        assert OBJECTION_TOTAL_ESCAPE_THRESHOLD == MAX_TOTAL_OBJECTIONS - 1
        # With default max_total=5, threshold should be 4
        assert OBJECTION_TOTAL_ESCAPE_THRESHOLD == 4

    def test_should_contribute_true_for_total_escape(self, source):
        """
        should_contribute returns True when total objections reach threshold.

        Note: MockIntentTracker.record() is called during begin_turn(),
        incrementing consecutive+1 and total+1 for objection intents.
        Initial values are set to (desired_after_record - 1).

        After record: consecutive=2 (below 3), total=4 (at threshold)
        """
        bb = create_blackboard(
            state="handle_objection",
            intent="objection_price",  # Objection intent → record +1
            state_before_objection="greeting",  # Non-phase state
            objection_consecutive=1,  # After record: 2 (below threshold 3)
            objection_total=3,  # After record: 4 (at total escape threshold)
        )

        assert source.should_contribute(bb) is True

    def test_should_contribute_false_below_total_threshold(self, source):
        """
        should_contribute returns False when total is below threshold
        and consecutive is also below threshold.

        After record: consecutive=1, total=3 (both below thresholds)
        """
        bb = create_blackboard(
            state="handle_objection",
            intent="objection_price",  # record +1
            state_before_objection="greeting",
            objection_consecutive=0,  # After record: 1 (below 3)
            objection_total=2,  # After record: 3 (below 4)
        )

        assert source.should_contribute(bb) is False

    def test_should_contribute_false_for_phase_state_total_escape(self, source):
        """
        should_contribute returns False for total escape when saved state has phase.

        Total escape only triggers for non-phase states (like greeting).
        For phase states, we wait for positive intent to return.

        After record: consecutive=2, total=4 (at threshold but phase state)
        """
        bb = create_blackboard(
            state="handle_objection",
            intent="objection_price",  # record +1
            state_before_objection="bant_budget",  # HAS phase
            objection_consecutive=1,  # After record: 2
            objection_total=3,  # After record: 4 (at threshold)
        )

        assert source.should_contribute(bb) is False

    def test_contribute_proposes_entry_state_on_total_escape(self, source):
        """
        contribute proposes entry_state when total escape triggered.

        After record: consecutive=1 (below 3), total=4 (at threshold)
        """
        bb = create_blackboard(
            state="handle_objection",
            intent="objection_trust",  # Objection intent → record +1
            state_before_objection="greeting",  # Non-phase state
            objection_consecutive=0,  # After record: 1 (below 3)
            objection_total=3,  # After record: 4 (at threshold)
        )

        source.contribute(bb)

        proposals = bb.get_transition_proposals()
        assert len(proposals) == 1
        assert proposals[0].value == "bant_budget"  # entry_state
        assert proposals[0].priority == Priority.NORMAL
        assert proposals[0].reason_code == "objection_total_escape_to_entry_state"

    def test_contribute_metadata_includes_total_escape_info(self, source):
        """
        contribute metadata includes total escape information.

        After record: consecutive=1 (below 3), total=4 (at threshold)
        """
        bb = create_blackboard(
            state="handle_objection",
            intent="objection_price",  # record +1
            state_before_objection="greeting",
            objection_consecutive=0,  # After record: 1 (below 3)
            objection_total=3,  # After record: 4 (at threshold)
        )

        source.contribute(bb)

        proposals = bb.get_transition_proposals()
        metadata = proposals[0].metadata

        assert metadata["is_objection_loop_escape"] is True
        assert metadata["escape_trigger"] == "total"
        assert metadata["total_objections"] == 4
        assert metadata["mechanism"] == "objection_total_escape"

    def test_consecutive_escape_still_has_priority_over_total(self, source):
        """
        When both consecutive and total thresholds are met,
        consecutive escape triggers first (it's checked first).

        After record: consecutive=3 (at threshold), total=5 (above threshold)
        """
        bb = create_blackboard(
            state="handle_objection",
            intent="objection_price",  # record +1
            state_before_objection="greeting",
            objection_consecutive=2,  # After record: 3 (at consecutive threshold)
            objection_total=4,  # After record: 5 (above total threshold)
        )

        source.contribute(bb)

        proposals = bb.get_transition_proposals()
        assert len(proposals) == 1
        # Consecutive escape triggers first (checked before total)
        assert proposals[0].reason_code == "objection_loop_escape_to_entry_state"
        metadata = proposals[0].metadata
        assert metadata["escape_trigger"] == "consecutive"

    def test_meta_intent_streak_breaking_full_scenario(self, source):
        """
        Full scenario: meta-intents break consecutive streak, total triggers escape.

        Simulates the exact bug:
        - tire_kicker in greeting → objection → handle_objection (save greeting)
        - obj(c=1,t=1), obj(c=2,t=2), brevity(c=0,t=2), obj(c=1,t=3)
        - Now 4th objection intent arrives → record: c=1+1=2, t=3+1=4
        - Total escape fires (4 >= 4) while consecutive doesn't (2 < 3)
        """
        # State before this turn: c=1, t=3 (broken by request_brevity)
        bb = create_blackboard(
            state="handle_objection",
            intent="objection_price",  # 4th objection → record: c=2, t=4
            state_before_objection="greeting",
            objection_consecutive=1,  # After record: 2 (broken by brevity)
            objection_total=3,  # After record: 4 (keeps accumulating)
        )

        source.contribute(bb)

        proposals = bb.get_transition_proposals()
        assert len(proposals) == 1
        assert proposals[0].value == "bant_budget"  # entry_state
        assert proposals[0].reason_code == "objection_total_escape_to_entry_state"

    def test_total_escape_above_threshold(self, source):
        """
        Total escape should also fire when total exceeds threshold.

        After record: consecutive=1, total=5 (above threshold 4)
        """
        bb = create_blackboard(
            state="handle_objection",
            intent="objection_no_need",  # record +1
            state_before_objection="greeting",
            objection_consecutive=0,  # After record: 1
            objection_total=4,  # After record: 5 (above threshold)
        )

        assert source.should_contribute(bb) is True

        source.contribute(bb)

        proposals = bb.get_transition_proposals()
        assert len(proposals) == 1
        assert proposals[0].value == "bant_budget"
        assert proposals[0].reason_code == "objection_total_escape_to_entry_state"

    def test_no_total_escape_for_positive_intent(self, source):
        """
        Positive intent should use normal return path, not total escape.
        """
        bb = create_blackboard(
            state="handle_objection",
            intent="agreement",  # POSITIVE intent
            state_before_objection="greeting",
            objection_consecutive=0,
            objection_total=4,  # At total threshold, but positive intent
        )

        source.contribute(bb)

        proposals = bb.get_transition_proposals()
        assert len(proposals) == 1
        assert proposals[0].value == "bant_budget"  # entry_state fallback
        # Should be normal return, not total escape
        assert proposals[0].reason_code == "objection_return_to_entry_state"

    def test_no_total_escape_without_entry_state(self, source):
        """
        No total escape when flow has no entry_state defined.
        """
        bb = create_blackboard(
            state="handle_objection",
            intent="objection_price",
            state_before_objection="greeting",
            objection_consecutive=1,
            objection_total=4,
            variables={},  # No entry_state
        )

        source.contribute(bb)

        proposals = bb.get_transition_proposals()
        assert len(proposals) == 0  # No fallback available


# =============================================================================
# Tests for Price Question Return (SSOT-based)
# =============================================================================

class TestPriceQuestionReturn:
    """
    Test that all 7 price-related intents trigger return from handle_objection.

    Root Cause Fixed:
        QUESTION_RETURN_INTENTS had "question_pricing" (typo, not a real intent)
        and missed all 6 other price_related intents.
        Now OBJECTION_RETURN_TRIGGERS (SSOT) includes the full price_related category.
    """

    PRICE_INTENTS = [
        "price_question",
        "pricing_details",
        "cost_inquiry",
        "discount_request",
        "payment_terms",
        "pricing_comparison",
        "budget_question",
    ]

    @pytest.fixture
    def source(self):
        """Create an ObjectionReturnSource instance."""
        return ObjectionReturnSource()

    @pytest.mark.parametrize("intent", PRICE_INTENTS)
    def test_should_contribute_true_for_all_price_related_intents(self, source, intent):
        """should_contribute returns True for each of the 7 price-related intents."""
        bb = create_blackboard(
            state="handle_objection",
            intent=intent,
            state_before_objection="bant_budget"
        )
        assert source.should_contribute(bb) is True, f"Failed for price intent: {intent}"

    @pytest.mark.parametrize("intent", PRICE_INTENTS)
    def test_contribute_returns_to_phase_state_on_price_question(self, source, intent):
        """contribute returns to saved phase state for price intents."""
        bb = create_blackboard(
            state="handle_objection",
            intent=intent,
            state_before_objection="bant_budget"
        )

        source.contribute(bb)

        proposals = bb.get_transition_proposals()
        assert len(proposals) == 1
        assert proposals[0].value == "bant_budget"
        assert proposals[0].priority == Priority.HIGH

    @pytest.mark.parametrize("intent", PRICE_INTENTS)
    def test_contribute_returns_to_entry_state_for_non_phase(self, source, intent):
        """contribute falls back to entry_state when saved_state has no phase."""
        bb = create_blackboard(
            state="handle_objection",
            intent=intent,
            state_before_objection="greeting"
        )

        source.contribute(bb)

        proposals = bb.get_transition_proposals()
        assert len(proposals) == 1
        assert proposals[0].value == "bant_budget"  # entry_state fallback
        assert proposals[0].priority == Priority.NORMAL

    def test_price_related_intents_from_ssot(self):
        """Verify that all 7 price intents are in OBJECTION_RETURN_TRIGGERS from SSOT."""
        expected_price_intents = set(self.PRICE_INTENTS)
        triggers_set = set(OBJECTION_RETURN_TRIGGERS)
        assert expected_price_intents <= triggers_set, (
            f"Missing price intents in SSOT: {expected_price_intents - triggers_set}"
        )

    def test_price_related_intents_match_category(self):
        """Verify PRICE_RELATED_INTENTS category matches expected intents."""
        expected = set(self.PRICE_INTENTS)
        actual = set(PRICE_RELATED_INTENTS)
        assert expected == actual, (
            f"PRICE_RELATED_INTENTS mismatch. Missing: {expected - actual}, Extra: {actual - expected}"
        )
