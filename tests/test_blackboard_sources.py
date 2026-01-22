# tests/test_blackboard_sources.py

"""
Tests for Blackboard Stage 6: Knowledge Sources (Part 1).

These tests verify:
1. PriceQuestionSource - handles price-related questions with combinable=True
2. DataCollectorSource - tracks data completeness and proposes transitions
"""

import pytest
from typing import Dict, Any, Optional, List
from unittest.mock import Mock, MagicMock


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
):
    """Helper to create a blackboard with turn started."""
    from src.blackboard.blackboard import DialogueBlackboard

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
# Tests for PriceQuestionSource
# =============================================================================

class TestPriceQuestionSourceInit:
    """Test PriceQuestionSource initialization."""

    def test_init_default(self):
        """Test default initialization."""
        from src.blackboard.sources import PriceQuestionSource

        source = PriceQuestionSource()

        assert source.name == "PriceQuestionSource"
        assert source.enabled is True
        assert "price_question" in source.price_intents
        assert "discount_request" in source.price_intents

    def test_init_with_custom_name(self):
        """Test initialization with custom name."""
        from src.blackboard.sources import PriceQuestionSource

        source = PriceQuestionSource(name="CustomPriceSource")

        assert source.name == "CustomPriceSource"

    def test_init_with_custom_intents(self):
        """Test initialization with custom price intents."""
        from src.blackboard.sources import PriceQuestionSource

        custom_intents = {"custom_price", "my_pricing"}
        source = PriceQuestionSource(price_intents=custom_intents)

        assert source.price_intents == custom_intents
        assert "price_question" not in source.price_intents

    def test_default_price_intents(self):
        """Test that default price intents are correct."""
        from src.blackboard.sources import PriceQuestionSource

        source = PriceQuestionSource()

        expected_intents = {
            "price_question",
            "pricing_details",
            "cost_inquiry",
            "discount_request",
            "payment_terms",
            "pricing_comparison",
            "budget_question",
        }
        assert source.price_intents == expected_intents


class TestPriceQuestionSourceIntentManagement:
    """Test PriceQuestionSource intent management."""

    def test_add_price_intent(self):
        """Test adding a price intent."""
        from src.blackboard.sources import PriceQuestionSource

        source = PriceQuestionSource()
        source.add_price_intent("new_intent")

        assert "new_intent" in source.price_intents

    def test_remove_price_intent(self):
        """Test removing a price intent."""
        from src.blackboard.sources import PriceQuestionSource

        source = PriceQuestionSource()
        source.remove_price_intent("price_question")

        assert "price_question" not in source.price_intents

    def test_remove_nonexistent_intent(self):
        """Test removing a non-existent intent doesn't raise."""
        from src.blackboard.sources import PriceQuestionSource

        source = PriceQuestionSource()
        # Should not raise
        source.remove_price_intent("nonexistent")


class TestPriceQuestionSourceShouldContribute:
    """Test PriceQuestionSource.should_contribute()."""

    def test_should_contribute_price_question(self):
        """Test should_contribute returns True for price_question."""
        from src.blackboard.sources import PriceQuestionSource

        bb = create_blackboard(intent="price_question")
        source = PriceQuestionSource()

        assert source.should_contribute(bb) is True

    def test_should_contribute_discount_request(self):
        """Test should_contribute returns True for discount_request."""
        from src.blackboard.sources import PriceQuestionSource

        bb = create_blackboard(intent="discount_request")
        source = PriceQuestionSource()

        assert source.should_contribute(bb) is True

    def test_should_contribute_payment_terms(self):
        """Test should_contribute returns True for payment_terms."""
        from src.blackboard.sources import PriceQuestionSource

        bb = create_blackboard(intent="payment_terms")
        source = PriceQuestionSource()

        assert source.should_contribute(bb) is True

    def test_should_not_contribute_non_price_intent(self):
        """Test should_contribute returns False for non-price intents."""
        from src.blackboard.sources import PriceQuestionSource

        bb = create_blackboard(intent="agreement")
        source = PriceQuestionSource()

        assert source.should_contribute(bb) is False

    def test_should_not_contribute_when_disabled(self):
        """Test should_contribute returns False when source is disabled."""
        from src.blackboard.sources import PriceQuestionSource

        bb = create_blackboard(intent="price_question")
        source = PriceQuestionSource()
        source.disable()

        assert source.should_contribute(bb) is False

    def test_should_contribute_custom_intents(self):
        """Test should_contribute with custom intents."""
        from src.blackboard.sources import PriceQuestionSource

        bb = create_blackboard(intent="my_custom_price")
        source = PriceQuestionSource(price_intents={"my_custom_price"})

        assert source.should_contribute(bb) is True


class TestPriceQuestionSourceContribute:
    """Test PriceQuestionSource.contribute()."""

    def test_contribute_price_question_proposes_action(self):
        """Test that price_question intent proposes answer_with_pricing action."""
        from src.blackboard.sources import PriceQuestionSource
        from src.blackboard.enums import Priority, ProposalType

        bb = create_blackboard(intent="price_question")
        source = PriceQuestionSource()

        source.contribute(bb)

        proposals = bb.get_action_proposals()
        assert len(proposals) == 1
        assert proposals[0].type == ProposalType.ACTION
        assert proposals[0].value == "answer_with_pricing"
        assert proposals[0].priority == Priority.HIGH
        assert proposals[0].combinable is True  # KEY: Must be True!
        assert proposals[0].source_name == "PriceQuestionSource"
        assert proposals[0].reason_code == "price_question_priority"

    def test_contribute_discount_request_proposes_specific_action(self):
        """Test that discount_request intent proposes handle_discount_request action."""
        from src.blackboard.sources import PriceQuestionSource

        bb = create_blackboard(intent="discount_request")
        source = PriceQuestionSource()

        source.contribute(bb)

        proposals = bb.get_action_proposals()
        assert len(proposals) == 1
        assert proposals[0].value == "handle_discount_request"

    def test_contribute_payment_terms_proposes_specific_action(self):
        """Test that payment_terms intent proposes explain_payment_terms action."""
        from src.blackboard.sources import PriceQuestionSource

        bb = create_blackboard(intent="payment_terms")
        source = PriceQuestionSource()

        source.contribute(bb)

        proposals = bb.get_action_proposals()
        assert len(proposals) == 1
        assert proposals[0].value == "explain_payment_terms"

    def test_contribute_pricing_comparison_proposes_specific_action(self):
        """Test that pricing_comparison intent proposes compare_pricing action."""
        from src.blackboard.sources import PriceQuestionSource

        bb = create_blackboard(intent="pricing_comparison")
        source = PriceQuestionSource()

        source.contribute(bb)

        proposals = bb.get_action_proposals()
        assert len(proposals) == 1
        assert proposals[0].value == "compare_pricing"

    def test_contribute_budget_question_proposes_specific_action(self):
        """Test that budget_question intent proposes discuss_budget action."""
        from src.blackboard.sources import PriceQuestionSource

        bb = create_blackboard(intent="budget_question")
        source = PriceQuestionSource()

        source.contribute(bb)

        proposals = bb.get_action_proposals()
        assert len(proposals) == 1
        assert proposals[0].value == "discuss_budget"

    def test_contribute_non_price_intent_no_proposals(self):
        """Test that non-price intent doesn't propose anything."""
        from src.blackboard.sources import PriceQuestionSource

        bb = create_blackboard(intent="agreement")
        source = PriceQuestionSource()

        source.contribute(bb)

        assert len(bb.get_action_proposals()) == 0

    def test_contribute_metadata_includes_original_intent(self):
        """Test that metadata includes original intent."""
        from src.blackboard.sources import PriceQuestionSource

        bb = create_blackboard(intent="cost_inquiry")
        source = PriceQuestionSource()

        source.contribute(bb)

        proposals = bb.get_action_proposals()
        assert proposals[0].metadata["original_intent"] == "cost_inquiry"

    def test_contribute_metadata_includes_pricing_data_status(self):
        """Test that metadata includes pricing data availability status."""
        from src.blackboard.sources import PriceQuestionSource

        # Without pricing data
        bb1 = create_blackboard(intent="price_question")
        source = PriceQuestionSource()
        source.contribute(bb1)
        assert bb1.get_action_proposals()[0].metadata["has_pricing_data"] is False

        # With pricing data
        bb2 = create_blackboard(
            intent="price_question",
            collected_data={"pricing_tier": "enterprise"}
        )
        source.contribute(bb2)
        assert bb2.get_action_proposals()[0].metadata["has_pricing_data"] is True

    def test_contribute_combinable_is_always_true(self):
        """Test that combinable is always True for all price intents."""
        from src.blackboard.sources import PriceQuestionSource

        source = PriceQuestionSource()

        for intent in source.price_intents:
            bb = create_blackboard(intent=intent)
            source.contribute(bb)
            proposals = bb.get_action_proposals()
            if proposals:
                assert proposals[0].combinable is True, f"Intent {intent} should be combinable"


class TestPriceQuestionSourceEnableDisable:
    """Test PriceQuestionSource enable/disable functionality."""

    def test_enable_source(self):
        """Test enabling source."""
        from src.blackboard.sources import PriceQuestionSource

        source = PriceQuestionSource()
        source.disable()
        source.enable()

        assert source.enabled is True

    def test_disable_source(self):
        """Test disabling source."""
        from src.blackboard.sources import PriceQuestionSource

        source = PriceQuestionSource()
        source.disable()

        assert source.enabled is False

    def test_disabled_source_no_contribution(self):
        """Test that disabled source doesn't contribute."""
        from src.blackboard.sources import PriceQuestionSource

        bb = create_blackboard(intent="price_question")
        source = PriceQuestionSource()
        source.disable()

        source.contribute(bb)

        assert len(bb.get_action_proposals()) == 0


# =============================================================================
# Tests for DataCollectorSource
# =============================================================================

class TestDataCollectorSourceInit:
    """Test DataCollectorSource initialization."""

    def test_init_default(self):
        """Test default initialization."""
        from src.blackboard.sources import DataCollectorSource

        source = DataCollectorSource()

        assert source.name == "DataCollectorSource"
        assert source.enabled is True

    def test_init_with_custom_name(self):
        """Test initialization with custom name."""
        from src.blackboard.sources import DataCollectorSource

        source = DataCollectorSource(name="CustomDataCollector")

        assert source.name == "CustomDataCollector"


class TestDataCollectorSourceShouldContribute:
    """Test DataCollectorSource.should_contribute()."""

    def test_should_contribute_with_required_data(self):
        """Test should_contribute returns True when state has required_data."""
        from src.blackboard.sources import DataCollectorSource

        states = {
            "spin_situation": {
                "required_data": ["company_name", "industry"],
                "transitions": {"data_complete": "spin_problem"},
            }
        }
        bb = create_blackboard(state="spin_situation", states=states, intent="provide_info")
        source = DataCollectorSource()

        assert source.should_contribute(bb) is True

    def test_should_not_contribute_without_required_data(self):
        """Test should_contribute returns False when state has no required_data."""
        from src.blackboard.sources import DataCollectorSource

        states = {
            "greeting": {"goal": "Greet user"}  # No required_data
        }
        bb = create_blackboard(state="greeting", states=states, intent="greeting")
        source = DataCollectorSource()

        assert source.should_contribute(bb) is False

    def test_should_not_contribute_when_final_state(self):
        """Test should_contribute returns False for final state."""
        from src.blackboard.sources import DataCollectorSource

        states = {
            "closed": {
                "is_final": True,
                "required_data": ["company_name"],
            }
        }
        bb = create_blackboard(state="closed", states=states, intent="greeting")
        source = DataCollectorSource()

        assert source.should_contribute(bb) is False

    def test_should_not_contribute_when_disabled(self):
        """Test should_contribute returns False when source is disabled."""
        from src.blackboard.sources import DataCollectorSource

        states = {
            "spin_situation": {
                "required_data": ["company_name"],
            }
        }
        bb = create_blackboard(state="spin_situation", states=states, intent="provide_info")
        source = DataCollectorSource()
        source.disable()

        assert source.should_contribute(bb) is False

    def test_should_contribute_empty_required_data(self):
        """Test should_contribute returns False for empty required_data list."""
        from src.blackboard.sources import DataCollectorSource

        states = {
            "spin_situation": {
                "required_data": [],  # Empty list
            }
        }
        bb = create_blackboard(state="spin_situation", states=states, intent="provide_info")
        source = DataCollectorSource()

        assert source.should_contribute(bb) is False


class TestDataCollectorSourceContribute:
    """Test DataCollectorSource.contribute()."""

    def test_contribute_data_complete_proposes_transition(self):
        """Test that complete data proposes data_complete transition."""
        from src.blackboard.sources import DataCollectorSource
        from src.blackboard.enums import Priority, ProposalType

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
            collected_data={"company_name": "ACME", "industry": "Tech"},
        )
        source = DataCollectorSource()

        source.contribute(bb)

        proposals = bb.get_transition_proposals()
        assert len(proposals) == 1
        assert proposals[0].type == ProposalType.TRANSITION
        assert proposals[0].value == "spin_problem"
        assert proposals[0].priority == Priority.NORMAL
        assert proposals[0].source_name == "DataCollectorSource"
        assert proposals[0].reason_code == "data_complete"

    def test_contribute_missing_data_no_proposal(self):
        """Test that missing data doesn't propose transition."""
        from src.blackboard.sources import DataCollectorSource

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
        source = DataCollectorSource()

        source.contribute(bb)

        assert len(bb.get_transition_proposals()) == 0

    def test_contribute_no_transition_defined(self):
        """Test that no proposal when data_complete transition not defined."""
        from src.blackboard.sources import DataCollectorSource

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
        source = DataCollectorSource()

        source.contribute(bb)

        assert len(bb.get_transition_proposals()) == 0

    def test_contribute_empty_string_treated_as_missing(self):
        """Test that empty string value is treated as missing."""
        from src.blackboard.sources import DataCollectorSource

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
        source = DataCollectorSource()

        source.contribute(bb)

        assert len(bb.get_transition_proposals()) == 0

    def test_contribute_none_treated_as_missing(self):
        """Test that None value is treated as missing."""
        from src.blackboard.sources import DataCollectorSource

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
            collected_data={"company_name": None},  # None value
        )
        source = DataCollectorSource()

        source.contribute(bb)

        assert len(bb.get_transition_proposals()) == 0

    def test_contribute_empty_list_treated_as_missing(self):
        """Test that empty list value is treated as missing."""
        from src.blackboard.sources import DataCollectorSource

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
            collected_data={"contacts": []},  # Empty list
        )
        source = DataCollectorSource()

        source.contribute(bb)

        assert len(bb.get_transition_proposals()) == 0

    def test_contribute_empty_dict_treated_as_missing(self):
        """Test that empty dict value is treated as missing."""
        from src.blackboard.sources import DataCollectorSource

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
            collected_data={"metadata": {}},  # Empty dict
        )
        source = DataCollectorSource()

        source.contribute(bb)

        assert len(bb.get_transition_proposals()) == 0

    def test_contribute_metadata_includes_fields(self):
        """Test that metadata includes required and collected fields."""
        from src.blackboard.sources import DataCollectorSource

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
        source = DataCollectorSource()

        source.contribute(bb)

        proposals = bb.get_transition_proposals()
        assert proposals[0].metadata["required_fields"] == ["company_name", "industry"]
        assert "company_name" in proposals[0].metadata["collected_fields"]
        assert "industry" in proposals[0].metadata["collected_fields"]


class TestDataCollectorSourceGetDataStatus:
    """Test DataCollectorSource.get_data_status() utility method."""

    def test_get_data_status_complete(self):
        """Test get_data_status when data is complete."""
        from src.blackboard.sources import DataCollectorSource

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
        source = DataCollectorSource()

        status = source.get_data_status(bb)

        assert status["required_fields"] == ["company_name", "industry"]
        assert status["optional_fields"] == ["company_size"]
        assert status["missing_required"] == []
        assert status["missing_optional"] == ["company_size"]
        assert status["is_complete"] is True
        assert status["completion_percentage"] == 100.0

    def test_get_data_status_incomplete(self):
        """Test get_data_status when data is incomplete."""
        from src.blackboard.sources import DataCollectorSource

        states = {
            "spin_situation": {
                "required_data": ["company_name", "industry"],
            }
        }
        bb = create_blackboard(
            state="spin_situation",
            states=states,
            intent="provide_info",
            collected_data={"company_name": "ACME"},  # Missing industry
        )
        source = DataCollectorSource()

        status = source.get_data_status(bb)

        assert status["missing_required"] == ["industry"]
        assert status["is_complete"] is False
        assert status["completion_percentage"] == 50.0

    def test_get_data_status_no_required_data(self):
        """Test get_data_status when no required data defined."""
        from src.blackboard.sources import DataCollectorSource

        states = {
            "greeting": {}  # No required_data
        }
        bb = create_blackboard(state="greeting", states=states, intent="greeting")
        source = DataCollectorSource()

        status = source.get_data_status(bb)

        assert status["required_fields"] == []
        assert status["is_complete"] is True
        assert status["completion_percentage"] == 100.0


class TestDataCollectorSourceEnableDisable:
    """Test DataCollectorSource enable/disable functionality."""

    def test_enable_source(self):
        """Test enabling source."""
        from src.blackboard.sources import DataCollectorSource

        source = DataCollectorSource()
        source.disable()
        source.enable()

        assert source.enabled is True

    def test_disable_source(self):
        """Test disabling source."""
        from src.blackboard.sources import DataCollectorSource

        source = DataCollectorSource()
        source.disable()

        assert source.enabled is False


# =============================================================================
# Integration Tests
# =============================================================================

class TestSourcesIntegration:
    """Integration tests for sources working together."""

    def test_price_question_with_data_complete(self):
        """
        Test that price question and data complete can coexist.

        This is the KEY scenario: user asks about pricing while providing
        the last required data field. Both should be proposed:
        - PriceQuestionSource: answer_with_pricing (combinable=True)
        - DataCollectorSource: transition to next phase

        The ConflictResolver should later combine both.
        """
        from src.blackboard.sources import PriceQuestionSource, DataCollectorSource

        states = {
            "spin_situation": {
                "required_data": ["company_name"],
                "transitions": {"data_complete": "spin_problem"},
            }
        }
        bb = create_blackboard(
            state="spin_situation",
            states=states,
            intent="price_question",
            collected_data={"company_name": "ACME"},  # All data complete
        )

        price_source = PriceQuestionSource()
        data_source = DataCollectorSource()

        # Both sources contribute
        price_source.contribute(bb)
        data_source.contribute(bb)

        # Should have both proposals
        action_proposals = bb.get_action_proposals()
        transition_proposals = bb.get_transition_proposals()

        assert len(action_proposals) == 1
        assert action_proposals[0].value == "answer_with_pricing"
        assert action_proposals[0].combinable is True

        assert len(transition_proposals) == 1
        assert transition_proposals[0].value == "spin_problem"

    def test_multiple_price_sources_same_blackboard(self):
        """Test that only one price source should contribute per turn."""
        from src.blackboard.sources import PriceQuestionSource

        bb = create_blackboard(intent="price_question")
        source1 = PriceQuestionSource(name="Source1")
        source2 = PriceQuestionSource(name="Source2")

        source1.contribute(bb)
        source2.contribute(bb)

        # Both contributed (in real scenario, only one should be registered)
        proposals = bb.get_action_proposals()
        assert len(proposals) == 2


# =============================================================================
# Package Import Tests
# =============================================================================

class TestPackageImports:
    """Test package import functionality."""

    def test_import_from_sources_package(self):
        """Test importing sources from package."""
        from src.blackboard.sources import PriceQuestionSource, DataCollectorSource

        assert PriceQuestionSource is not None
        assert DataCollectorSource is not None

    def test_sources_in_dunder_all(self):
        """Test that sources are in __all__."""
        import src.blackboard.sources as sources

        assert "PriceQuestionSource" in sources.__all__
        assert "DataCollectorSource" in sources.__all__


# =============================================================================
# Criteria Verification (from Architectural Plan)
# =============================================================================

class TestStage6CriteriaVerification:
    """
    Verification tests from the plan's CRITERION OF COMPLETION for Stage 6.
    """

    def test_criterion_import_price_question_source(self):
        """
        Plan criterion: from src.blackboard.sources import PriceQuestionSource
        """
        from src.blackboard.sources import PriceQuestionSource

        assert PriceQuestionSource is not None

    def test_criterion_import_data_collector_source(self):
        """
        Plan criterion: from src.blackboard.sources import DataCollectorSource
        """
        from src.blackboard.sources import DataCollectorSource

        assert DataCollectorSource is not None

    def test_criterion_price_question_combinable_true(self):
        """
        Plan criterion: PriceQuestionSource.combinable = True
        """
        from src.blackboard.sources import PriceQuestionSource

        bb = create_blackboard(intent="price_question")
        source = PriceQuestionSource()
        source.contribute(bb)

        proposals = bb.get_action_proposals()
        assert len(proposals) == 1
        assert proposals[0].combinable is True

    def test_criterion_data_collector_proposes_data_complete(self):
        """
        Plan criterion: DataCollectorSource proposes data_complete transition
        """
        from src.blackboard.sources import DataCollectorSource

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
            collected_data={"company_name": "ACME"},
        )
        source = DataCollectorSource()
        source.contribute(bb)

        proposals = bb.get_transition_proposals()
        assert len(proposals) == 1
        assert proposals[0].reason_code == "data_complete"
