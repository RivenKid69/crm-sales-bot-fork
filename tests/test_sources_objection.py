# tests/test_sources_objection.py

"""
Tests for ObjectionGuardSource - Stage 12.

These tests verify:
1. ObjectionGuardSource - monitors objection limits per persona
2. _objection_limit_final flag for is_final override
3. Persona-specific limits

Section: 17.3
"""

import pytest
from typing import Dict, Any, Optional
from unittest.mock import Mock

from src.blackboard.sources.objection_guard import ObjectionGuardSource
from src.blackboard.blackboard import DialogueBlackboard
from src.blackboard.enums import Priority, ProposalType


# =============================================================================
# Mock Implementations for Testing
# =============================================================================

class MockStateMachine:
    """Mock StateMachine implementing IStateMachine protocol."""

    def __init__(self, state: str = "greeting", collected_data: Optional[Dict[str, Any]] = None):
        self._state = state
        self._collected_data = collected_data or {}
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
            "spin_situation": {
                "goal": "Gather situation",
                "phase": "situation",
            },
            "soft_close": {"goal": "Soft close", "is_final": True},
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



def create_blackboard(
    state: str = "greeting",
    collected_data: Optional[Dict[str, Any]] = None,
    states: Optional[Dict[str, Dict[str, Any]]] = None,
    intent: str = "greeting",
    extracted_data: Optional[Dict[str, Any]] = None,
    objection_consecutive: int = 0,
    objection_total: int = 0,
):
    """Helper to create a blackboard with turn started."""
    sm = MockStateMachine(state=state, collected_data=collected_data or {})
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
# Tests for ObjectionGuardSource (Section 17.3)
# =============================================================================

class TestObjectionGuardSource:
    """Test suite for ObjectionGuardSource."""

    @pytest.fixture
    def source(self):
        """Create an ObjectionGuardSource with test limits."""
        return ObjectionGuardSource(
            persona_limits={
                "aggressive": {"consecutive": 5, "total": 8},
                "busy": {"consecutive": 2, "total": 4},
                "default": {"consecutive": 3, "total": 5},
            }
        )

    @pytest.fixture
    def mock_blackboard(self):
        """Create a mock blackboard."""
        bb = Mock(spec=DialogueBlackboard)
        bb.current_intent = "objection_price"

        ctx = Mock()
        ctx.current_intent = "objection_price"
        ctx.persona = "default"
        ctx.objection_consecutive = 1
        ctx.objection_total = 2

        bb.get_context.return_value = ctx

        return bb

    def test_should_contribute_true_for_objection(self, source, mock_blackboard):
        """should_contribute returns True for objection intents."""
        assert source.should_contribute(mock_blackboard) is True

    def test_should_contribute_false_for_non_objection(self, source, mock_blackboard):
        """should_contribute returns False for non-objection intents."""
        mock_blackboard.current_intent = "greeting"

        assert source.should_contribute(mock_blackboard) is False

    def test_contribute_no_proposal_when_within_limits(self, source):
        """contribute should not propose if within limits."""
        bb = create_blackboard(
            intent="objection_price",
            objection_consecutive=1,
            objection_total=2,
            collected_data={"persona": "default"}
        )
        # Default limits: consecutive=3, total=5

        source.contribute(bb)

        assert len(bb.get_action_proposals()) == 0
        assert len(bb.get_transition_proposals()) == 0

    def test_contribute_proposes_when_consecutive_exceeded(self, source):
        """contribute should propose soft_close when consecutive limit exceeded."""
        bb = create_blackboard(
            intent="objection_price",
            objection_consecutive=3,  # Equals default limit
            objection_total=3,
            collected_data={"persona": "default"}
        )

        source.contribute(bb)

        # Should propose BLOCKING action
        action_proposals = bb.get_action_proposals()
        assert len(action_proposals) == 1
        assert action_proposals[0].value == "objection_limit_reached"
        assert action_proposals[0].combinable is False  # BLOCKING!

        # Should propose transition
        transition_proposals = bb.get_transition_proposals()
        assert len(transition_proposals) == 1
        assert transition_proposals[0].value == "soft_close"

    def test_contribute_proposes_when_total_exceeded(self, source):
        """contribute should propose soft_close when total limit exceeded."""
        bb = create_blackboard(
            intent="objection_price",
            objection_consecutive=1,
            objection_total=5,  # Equals default limit
            collected_data={"persona": "default"}
        )

        source.contribute(bb)

        assert len(bb.get_action_proposals()) == 1
        assert len(bb.get_transition_proposals()) == 1

    def test_contribute_uses_persona_limits(self, source):
        """contribute should use persona-specific limits."""
        bb = create_blackboard(
            intent="objection_price",
            objection_consecutive=2,  # Equals busy limit
            objection_total=2,
            collected_data={"persona": "busy"}  # Stricter limits: consecutive=2, total=4
        )

        source.contribute(bb)

        # Should trigger because busy limit is 2
        assert len(bb.get_action_proposals()) == 1

    def test_contribute_uses_default_for_unknown_persona(self, source):
        """contribute should use default limits for unknown persona."""
        bb = create_blackboard(
            intent="objection_price",
            objection_consecutive=3,  # Default limit
            objection_total=3,
            collected_data={"persona": "unknown_persona"}
        )

        source.contribute(bb)

        assert len(bb.get_action_proposals()) == 1

    def test_contribute_sets_objection_limit_final_flag(self, source):
        """
        CRITICAL: contribute should propose _objection_limit_final data update.

        This flag is required for is_final override in _fill_compatibility_fields().
        Without it, soft_close triggered by objection limit won't be marked as final.
        """
        bb = create_blackboard(
            intent="objection_price",
            objection_consecutive=3,  # Trigger limit
            objection_total=3,
            collected_data={"persona": "default"}
        )

        source.contribute(bb)

        # Should propose data update for _objection_limit_final
        data_updates = bb.get_data_updates()
        assert "_objection_limit_final" in data_updates
        assert data_updates["_objection_limit_final"] is True


class TestObjectionGuardSourcePersonaLimits:
    """Test ObjectionGuardSource persona-specific limits."""

    @pytest.fixture
    def source(self):
        """Create an ObjectionGuardSource instance."""
        return ObjectionGuardSource()

    def test_aggressive_persona_higher_limits(self, source):
        """Aggressive persona has higher limits (consecutive=5, total=8)."""
        bb = create_blackboard(
            intent="objection_price",
            objection_consecutive=4,  # Would exceed default (3) but not aggressive (5)
            objection_total=7,        # Would exceed default (5) but not aggressive (8)
            collected_data={"persona": "aggressive"}
        )

        source.contribute(bb)

        # Should NOT propose - within aggressive limits
        assert len(bb.get_action_proposals()) == 0
        assert len(bb.get_transition_proposals()) == 0

    def test_busy_persona_lower_limits(self, source):
        """Busy persona has lower limits (consecutive=2, total=4)."""
        bb = create_blackboard(
            intent="objection_price",
            objection_consecutive=2,  # Equals busy limit
            objection_total=2,
            collected_data={"persona": "busy"}
        )

        source.contribute(bb)

        # Should trigger - busy limit reached
        assert len(bb.get_action_proposals()) == 1

    def test_no_persona_uses_default(self, source):
        """No persona in collected_data uses default limits."""
        bb = create_blackboard(
            intent="objection_price",
            objection_consecutive=3,
            objection_total=3,
            collected_data={}  # No persona
        )

        source.contribute(bb)

        assert len(bb.get_action_proposals()) == 1


class TestObjectionGuardSourceMetadata:
    """Test ObjectionGuardSource metadata in proposals."""

    @pytest.fixture
    def source(self):
        """Create an ObjectionGuardSource instance."""
        return ObjectionGuardSource()

    def test_metadata_includes_counters(self, source):
        """Metadata should include objection counters and limits."""
        bb = create_blackboard(
            intent="objection_price",
            objection_consecutive=3,
            objection_total=4,
            collected_data={"persona": "default"}
        )

        source.contribute(bb)

        action_proposals = bb.get_action_proposals()
        metadata = action_proposals[0].metadata

        assert metadata["persona"] == "default"
        assert metadata["consecutive"] == 3
        assert metadata["total"] == 4
        assert metadata["max_consecutive"] == 3
        assert metadata["max_total"] == 5

    def test_metadata_includes_exceeded_info(self, source):
        """Metadata should indicate which limit was exceeded."""
        bb = create_blackboard(
            intent="objection_price",
            objection_consecutive=3,
            objection_total=3,
            collected_data={"persona": "default"}
        )

        source.contribute(bb)

        action_proposals = bb.get_action_proposals()
        metadata = action_proposals[0].metadata

        assert "consecutive=3>=3" in metadata["exceeded"]


class TestObjectionGuardSourceProposalProperties:
    """Test ObjectionGuardSource proposal properties."""

    @pytest.fixture
    def source(self):
        """Create an ObjectionGuardSource instance."""
        return ObjectionGuardSource()

    def test_action_proposal_is_blocking(self, source):
        """Action proposal must have combinable=False (BLOCKING)."""
        bb = create_blackboard(
            intent="objection_price",
            objection_consecutive=3,
            objection_total=3,
        )

        source.contribute(bb)

        action_proposals = bb.get_action_proposals()
        assert len(action_proposals) == 1
        assert action_proposals[0].combinable is False

    def test_action_proposal_is_high_priority(self, source):
        """Action proposal must have HIGH priority."""
        bb = create_blackboard(
            intent="objection_price",
            objection_consecutive=3,
            objection_total=3,
        )

        source.contribute(bb)

        action_proposals = bb.get_action_proposals()
        assert action_proposals[0].priority == Priority.HIGH

    def test_transition_proposal_to_soft_close(self, source):
        """Transition proposal must target soft_close."""
        bb = create_blackboard(
            intent="objection_price",
            objection_consecutive=3,
            objection_total=3,
        )

        source.contribute(bb)

        transition_proposals = bb.get_transition_proposals()
        assert len(transition_proposals) == 1
        assert transition_proposals[0].value == "soft_close"
        assert transition_proposals[0].priority == Priority.HIGH


class TestObjectionGuardSourceEnableDisable:
    """Test ObjectionGuardSource enable/disable functionality."""

    def test_enable_source(self):
        """Test enabling source."""
        source = ObjectionGuardSource()
        source.disable()
        source.enable()

        assert source.enabled is True

    def test_disable_source(self):
        """Test disabling source."""
        source = ObjectionGuardSource()
        source.disable()

        assert source.enabled is False

    def test_disabled_source_no_contribution(self):
        """Disabled source should not contribute even when limit exceeded."""
        bb = create_blackboard(
            intent="objection_price",
            objection_consecutive=10,
            objection_total=10,
        )
        source = ObjectionGuardSource()
        source.disable()

        source.contribute(bb)

        assert len(bb.get_action_proposals()) == 0
        assert len(bb.get_transition_proposals()) == 0


class TestObjectionGuardSourceInit:
    """Test ObjectionGuardSource initialization."""

    def test_init_default(self):
        """Test default initialization."""
        source = ObjectionGuardSource()

        assert source.name == "ObjectionGuardSource"
        assert source.enabled is True
        assert "objection_price" in source.objection_intents
        assert "objection_competitor" in source.objection_intents

    def test_init_with_custom_name(self):
        """Test initialization with custom name."""
        source = ObjectionGuardSource(name="CustomObjectionGuard")

        assert source.name == "CustomObjectionGuard"

    def test_init_with_custom_persona_limits(self):
        """Test initialization with custom persona limits."""
        custom_limits = {
            "aggressive": {"consecutive": 10, "total": 15},
            "default": {"consecutive": 5, "total": 10},
        }
        source = ObjectionGuardSource(persona_limits=custom_limits)

        assert source.persona_limits == custom_limits

    def test_init_with_custom_objection_intents(self):
        """Test initialization with custom objection intents."""
        custom_intents = {"my_objection", "custom_objection"}
        source = ObjectionGuardSource(objection_intents=custom_intents)

        assert source.objection_intents == custom_intents
        assert "objection_price" not in source.objection_intents

    def test_default_persona_limits(self):
        """Test that default persona limits are correct."""
        source = ObjectionGuardSource()

        assert source.persona_limits["aggressive"]["consecutive"] == 5
        assert source.persona_limits["aggressive"]["total"] == 8
        assert source.persona_limits["busy"]["consecutive"] == 2
        assert source.persona_limits["busy"]["total"] == 4
        assert source.persona_limits["default"]["consecutive"] == 3
        assert source.persona_limits["default"]["total"] == 5

    def test_default_objection_intents(self):
        """Test that default objection intents are comprehensive."""
        source = ObjectionGuardSource()

        expected_intents = {
            "objection_price",
            "objection_competitor",
            "objection_timing",
            "objection_authority",
            "objection_need",
            "objection_trust",
            "objection_budget",
            "objection_features",
            "objection_complexity",
            "objection_support",
            "objection_integration",
            "objection_security",
            "objection_scalability",
            "objection_contract",
            "objection_implementation",
            "objection_training",
            "objection_roi",
            "objection_change",
            "objection_generic",
        }
        assert source.objection_intents == expected_intents


class TestIsFinalWhenObjectionLimitReached:
    """
    Integration test: is_final should be True when soft_close is triggered by objection limit.

    Flow:
    1. ObjectionGuardSource proposes soft_close + _objection_limit_final
    2. _fill_compatibility_fields checks for this flag
    3. is_final is set to True even if soft_close config has is_final=False
    """

    def test_objection_limit_final_flag_is_set(self):
        """Verify _objection_limit_final flag is proposed."""
        source = ObjectionGuardSource()
        bb = create_blackboard(
            intent="objection_price",
            objection_consecutive=3,
            objection_total=3,
            collected_data={"persona": "default"}
        )

        source.contribute(bb)

        data_updates = bb.get_data_updates()
        assert "_objection_limit_final" in data_updates
        assert data_updates["_objection_limit_final"] is True
