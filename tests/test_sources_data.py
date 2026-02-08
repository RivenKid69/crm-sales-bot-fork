# tests/test_sources_data.py

"""
Tests for DataCollectorSource - Stage 12.

These tests verify:
1. DataCollectorSource - tracks data completeness and proposes transitions
2. data_complete transition when all required data is collected

Section: 17.3
"""

import pytest
from typing import Dict, Any, Optional
from unittest.mock import Mock

from src.blackboard.sources.data_collector import DataCollectorSource
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
        self._state_before_objection = None

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
    def state_before_objection(self) -> Optional[str]:
        return self._state_before_objection

    @state_before_objection.setter
    def state_before_objection(self, value: Optional[str]) -> None:
        self._state_before_objection = value

    def sync_phase_from_state(self) -> None:
        pass


class MockIntentTracker:
    """Mock IntentTracker implementing IIntentTracker protocol."""

    def __init__(self, turn_number: int = 0):
        self._turn_number = turn_number
        self._prev_intent = None
        self._intents = []

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

    def advance_turn(self) -> None:
        self._turn_number += 1

    def objection_consecutive(self) -> int:
        return 0

    def objection_total(self) -> int:
        return 0

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
                "required_data": ["company_name", "industry"],
                "transitions": {"data_complete": "spin_problem"},
            },
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



def create_blackboard(
    state: str = "greeting",
    collected_data: Optional[Dict[str, Any]] = None,
    states: Optional[Dict[str, Dict[str, Any]]] = None,
    intent: str = "greeting",
    extracted_data: Optional[Dict[str, Any]] = None,
):
    """Helper to create a blackboard with turn started."""
    sm = MockStateMachine(state=state, collected_data=collected_data or {})
    flow_config = MockFlowConfig(states=states)
    tracker = MockIntentTracker()

    bb = DialogueBlackboard(
        state_machine=sm,
        flow_config=flow_config,
        intent_tracker=tracker,
    )
    bb.begin_turn(intent=intent, extracted_data=extracted_data or {})
    return bb


# =============================================================================
# Tests for DataCollectorSource (Section 17.3)
# =============================================================================

class TestDataCollectorSource:
    """Test suite for DataCollectorSource."""

    @pytest.fixture
    def source(self):
        """Create a DataCollectorSource instance."""
        return DataCollectorSource()

    @pytest.fixture
    def mock_blackboard(self):
        """Create a mock blackboard with context."""
        bb = Mock(spec=DialogueBlackboard)

        ctx = Mock()
        ctx.state_config = {
            "required_data": ["company_size", "industry"],
            "is_final": False,
            "transitions": {
                "data_complete": "spin_problem",
            },
        }
        ctx.required_data = ["company_size", "industry"]
        ctx.collected_data = {"company_size": "50"}  # Missing industry
        ctx.get_transition = lambda trigger: ctx.state_config["transitions"].get(trigger)

        bb.get_context.return_value = ctx

        return bb

    def test_should_contribute_true_when_required_data_exists(self, source):
        """should_contribute returns True when state has required_data."""
        states = {
            "spin_situation": {
                "required_data": ["company_name", "industry"],
                "transitions": {"data_complete": "spin_problem"},
            }
        }
        bb = create_blackboard(state="spin_situation", states=states, intent="provide_info")

        assert source.should_contribute(bb) is True

    def test_should_contribute_false_when_no_required_data(self, source):
        """should_contribute returns False when no required_data defined."""
        states = {
            "greeting": {"goal": "Greet user"}  # No required_data
        }
        bb = create_blackboard(state="greeting", states=states, intent="greeting")

        assert source.should_contribute(bb) is False

    def test_should_contribute_false_when_empty_required_data(self, source):
        """should_contribute returns False when required_data is empty list."""
        states = {
            "spin_situation": {
                "required_data": [],  # Empty list
            }
        }
        bb = create_blackboard(state="spin_situation", states=states, intent="provide_info")

        assert source.should_contribute(bb) is False

    def test_should_contribute_false_when_final_state(self, source):
        """should_contribute returns False for final states."""
        states = {
            "closed": {
                "is_final": True,
                "required_data": ["company_name"],
            }
        }
        bb = create_blackboard(state="closed", states=states, intent="greeting")

        assert source.should_contribute(bb) is False

    def test_should_contribute_false_when_disabled(self, source):
        """should_contribute returns False when source is disabled."""
        states = {
            "spin_situation": {
                "required_data": ["company_name"],
            }
        }
        bb = create_blackboard(state="spin_situation", states=states, intent="provide_info")
        source.disable()

        assert source.should_contribute(bb) is False

    def test_contribute_no_proposal_when_data_missing(self, source):
        """contribute should not propose if data is missing."""
        states = {
            "spin_situation": {
                "required_data": ["company_name", "industry"],
                "transitions": {"data_complete": "spin_problem"},
            }
        }
        bb = create_blackboard(
            state="spin_situation",
            states=states,
            intent="provide_info",
            collected_data={"company_name": "ACME"},  # Missing industry
        )

        source.contribute(bb)

        assert len(bb.get_transition_proposals()) == 0

    def test_contribute_proposes_transition_when_data_complete(self, source):
        """contribute should propose transition when all data collected."""
        states = {
            "spin_situation": {
                "required_data": ["company_name", "industry"],
                "transitions": {"data_complete": "spin_problem"},
            }
        }
        bb = create_blackboard(
            state="spin_situation",
            states=states,
            intent="provide_info",
            collected_data={"company_name": "ACME", "industry": "tech"},  # All data!
        )

        source.contribute(bb)

        proposals = bb.get_transition_proposals()
        assert len(proposals) == 1
        assert proposals[0].type == ProposalType.TRANSITION
        assert proposals[0].value == "spin_problem"
        assert proposals[0].reason_code == "data_complete"
        assert proposals[0].priority == Priority.NORMAL

    def test_contribute_no_proposal_when_no_transition_defined(self, source):
        """contribute should not propose if data_complete transition not defined."""
        states = {
            "spin_situation": {
                "required_data": ["company_name"],
                # No transitions defined
            }
        }
        bb = create_blackboard(
            state="spin_situation",
            states=states,
            intent="provide_info",
            collected_data={"company_name": "ACME"},
        )

        source.contribute(bb)

        assert len(bb.get_transition_proposals()) == 0


class TestDataCollectorSourceEmptyValues:
    """Test DataCollectorSource handling of empty values."""

    @pytest.fixture
    def source(self):
        """Create a DataCollectorSource instance."""
        return DataCollectorSource()

    def test_empty_string_treated_as_missing(self, source):
        """Empty string value should be treated as missing."""
        states = {
            "spin_situation": {
                "required_data": ["company_name"],
                "transitions": {"data_complete": "spin_problem"},
            }
        }
        bb = create_blackboard(
            state="spin_situation",
            states=states,
            intent="provide_info",
            collected_data={"company_name": ""},  # Empty string
        )

        source.contribute(bb)

        assert len(bb.get_transition_proposals()) == 0

    def test_none_treated_as_missing(self, source):
        """None value should be treated as missing."""
        states = {
            "spin_situation": {
                "required_data": ["company_name"],
                "transitions": {"data_complete": "spin_problem"},
            }
        }
        bb = create_blackboard(
            state="spin_situation",
            states=states,
            intent="provide_info",
            collected_data={"company_name": None},
        )

        source.contribute(bb)

        assert len(bb.get_transition_proposals()) == 0

    def test_empty_list_treated_as_missing(self, source):
        """Empty list value should be treated as missing."""
        states = {
            "spin_situation": {
                "required_data": ["contacts"],
                "transitions": {"data_complete": "spin_problem"},
            }
        }
        bb = create_blackboard(
            state="spin_situation",
            states=states,
            intent="provide_info",
            collected_data={"contacts": []},
        )

        source.contribute(bb)

        assert len(bb.get_transition_proposals()) == 0

    def test_empty_dict_treated_as_missing(self, source):
        """Empty dict value should be treated as missing."""
        states = {
            "spin_situation": {
                "required_data": ["metadata"],
                "transitions": {"data_complete": "spin_problem"},
            }
        }
        bb = create_blackboard(
            state="spin_situation",
            states=states,
            intent="provide_info",
            collected_data={"metadata": {}},
        )

        source.contribute(bb)

        assert len(bb.get_transition_proposals()) == 0


class TestDataCollectorSourceMetadata:
    """Test DataCollectorSource metadata in proposals."""

    @pytest.fixture
    def source(self):
        """Create a DataCollectorSource instance."""
        return DataCollectorSource()

    def test_metadata_includes_fields(self, source):
        """Metadata should include required and collected fields."""
        states = {
            "spin_situation": {
                "required_data": ["company_name", "industry"],
                "transitions": {"data_complete": "spin_problem"},
            }
        }
        bb = create_blackboard(
            state="spin_situation",
            states=states,
            intent="provide_info",
            collected_data={"company_name": "ACME", "industry": "Tech", "extra": "data"},
        )

        source.contribute(bb)

        proposals = bb.get_transition_proposals()
        assert proposals[0].metadata["required_fields"] == ["company_name", "industry"]
        assert "company_name" in proposals[0].metadata["collected_fields"]
        assert "industry" in proposals[0].metadata["collected_fields"]


class TestDataCollectorSourceGetDataStatus:
    """Test DataCollectorSource.get_data_status() utility method."""

    @pytest.fixture
    def source(self):
        """Create a DataCollectorSource instance."""
        return DataCollectorSource()

    def test_get_data_status_complete(self, source):
        """Test get_data_status when data is complete."""
        states = {
            "spin_situation": {
                "required_data": ["company_name", "industry"],
                "optional_data": ["company_size"],
            }
        }
        bb = create_blackboard(
            state="spin_situation",
            states=states,
            intent="provide_info",
            collected_data={"company_name": "ACME", "industry": "Tech"},
        )

        status = source.get_data_status(bb)

        assert status["required_fields"] == ["company_name", "industry"]
        assert status["optional_fields"] == ["company_size"]
        assert status["missing_required"] == []
        assert status["missing_optional"] == ["company_size"]
        assert status["is_complete"] is True
        assert status["completion_percentage"] == 100.0

    def test_get_data_status_incomplete(self, source):
        """Test get_data_status when data is incomplete."""
        states = {
            "spin_situation": {
                "required_data": ["company_name", "industry"],
            }
        }
        bb = create_blackboard(
            state="spin_situation",
            states=states,
            intent="provide_info",
            collected_data={"company_name": "ACME"},
        )

        status = source.get_data_status(bb)

        assert status["missing_required"] == ["industry"]
        assert status["is_complete"] is False
        assert status["completion_percentage"] == 50.0

    def test_get_data_status_no_required_data(self, source):
        """Test get_data_status when no required data defined."""
        states = {
            "greeting": {}  # No required_data
        }
        bb = create_blackboard(state="greeting", states=states, intent="greeting")

        status = source.get_data_status(bb)

        assert status["required_fields"] == []
        assert status["is_complete"] is True
        assert status["completion_percentage"] == 100.0


class TestDataCollectorSourceEnableDisable:
    """Test DataCollectorSource enable/disable functionality."""

    def test_enable_source(self):
        """Test enabling source."""
        source = DataCollectorSource()
        source.disable()
        source.enable()

        assert source.enabled is True

    def test_disable_source(self):
        """Test disabling source."""
        source = DataCollectorSource()
        source.disable()

        assert source.enabled is False


class TestDataCollectorSourceInit:
    """Test DataCollectorSource initialization."""

    def test_init_default(self):
        """Test default initialization."""
        source = DataCollectorSource()

        assert source.name == "DataCollectorSource"
        assert source.enabled is True

    def test_init_with_custom_name(self):
        """Test initialization with custom name."""
        source = DataCollectorSource(name="CustomDataCollector")

        assert source.name == "CustomDataCollector"
