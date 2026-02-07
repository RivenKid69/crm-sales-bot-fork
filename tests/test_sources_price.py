# tests/test_sources_price.py

"""
Tests for PriceQuestionSource - Stage 12.

These tests verify:
1. PriceQuestionSource - handles price-related questions with combinable=True
2. CRITICAL: combinable flag must be True (allows state transitions to proceed)

Section: 17.3
"""

import pytest
from typing import Dict, Any, Optional
from unittest.mock import Mock, MagicMock

from src.blackboard.sources.price_question import PriceQuestionSource
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
            },
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
# Tests for PriceQuestionSource (Section 17.3)
# =============================================================================

class TestPriceQuestionSource:
    """Test suite for PriceQuestionSource."""

    @pytest.fixture
    def source(self):
        """Create a PriceQuestionSource instance."""
        return PriceQuestionSource()

    @pytest.fixture
    def mock_blackboard(self):
        """Create a mock blackboard."""
        bb = Mock(spec=DialogueBlackboard)
        bb.current_intent = "price_question"

        ctx = Mock()
        ctx.current_intent = "price_question"
        ctx.collected_data = {}
        bb.get_context.return_value = ctx

        return bb

    def test_should_contribute_true_for_price_question(self, source, mock_blackboard):
        """should_contribute returns True for price_question intent."""
        mock_blackboard.current_intent = "price_question"

        assert source.should_contribute(mock_blackboard) is True

    def test_should_contribute_true_for_pricing_details(self, source, mock_blackboard):
        """should_contribute returns True for pricing_details intent."""
        mock_blackboard.current_intent = "pricing_details"

        assert source.should_contribute(mock_blackboard) is True

    def test_should_contribute_true_for_cost_inquiry(self, source, mock_blackboard):
        """should_contribute returns True for cost_inquiry intent."""
        mock_blackboard.current_intent = "cost_inquiry"

        assert source.should_contribute(mock_blackboard) is True

    def test_should_contribute_true_for_discount_request(self, source, mock_blackboard):
        """should_contribute returns True for discount_request intent."""
        mock_blackboard.current_intent = "discount_request"

        assert source.should_contribute(mock_blackboard) is True

    def test_should_contribute_true_for_payment_terms(self, source, mock_blackboard):
        """should_contribute returns True for payment_terms intent."""
        mock_blackboard.current_intent = "payment_terms"

        assert source.should_contribute(mock_blackboard) is True

    def test_should_contribute_true_for_budget_question(self, source, mock_blackboard):
        """should_contribute returns True for budget_question intent."""
        mock_blackboard.current_intent = "budget_question"

        assert source.should_contribute(mock_blackboard) is True

    def test_should_contribute_false_for_other_intents(self, source, mock_blackboard):
        """should_contribute returns False for non-price intents."""
        mock_blackboard.current_intent = "greeting"

        assert source.should_contribute(mock_blackboard) is False

    def test_should_contribute_false_when_disabled(self, source, mock_blackboard):
        """should_contribute returns False when source is disabled."""
        source.disable()
        mock_blackboard.current_intent = "price_question"

        assert source.should_contribute(mock_blackboard) is False

    def test_contribute_proposes_answer_with_pricing(self, source):
        """contribute should propose answer_with_pricing action."""
        bb = create_blackboard(intent="price_question")

        source.contribute(bb)

        proposals = bb.get_action_proposals()
        assert len(proposals) == 1
        assert proposals[0].value == "answer_with_pricing"
        assert proposals[0].priority == Priority.HIGH
        assert proposals[0].combinable is True  # CRITICAL!
        assert proposals[0].reason_code == "price_question_priority"

    def test_contribute_proposes_discount_handler_for_discount_request(self, source):
        """contribute should propose handle_discount_request for discount intent."""
        bb = create_blackboard(intent="discount_request")

        source.contribute(bb)

        proposals = bb.get_action_proposals()
        assert len(proposals) == 1
        assert proposals[0].value == "handle_discount_request"

    def test_contribute_proposes_explain_payment_terms(self, source):
        """contribute should propose explain_payment_terms for payment_terms intent."""
        bb = create_blackboard(intent="payment_terms")

        source.contribute(bb)

        proposals = bb.get_action_proposals()
        assert len(proposals) == 1
        assert proposals[0].value == "explain_payment_terms"

    def test_contribute_proposes_compare_pricing(self, source):
        """contribute should propose compare_pricing for pricing_comparison intent."""
        bb = create_blackboard(intent="pricing_comparison")

        source.contribute(bb)

        proposals = bb.get_action_proposals()
        assert len(proposals) == 1
        assert proposals[0].value == "compare_pricing"

    def test_contribute_proposes_discuss_budget(self, source):
        """contribute should propose discuss_budget for budget_question intent."""
        bb = create_blackboard(intent="budget_question")

        source.contribute(bb)

        proposals = bb.get_action_proposals()
        assert len(proposals) == 1
        assert proposals[0].value == "discuss_budget"

    def test_combinable_flag_is_true(self, source):
        """
        CRITICAL TEST: combinable must be True.

        This ensures price questions don't block data_complete transitions.
        """
        bb = create_blackboard(intent="price_question")

        source.contribute(bb)

        proposals = bb.get_action_proposals()
        assert len(proposals) == 1
        assert proposals[0].combinable is True, \
            "PriceQuestionSource MUST set combinable=True to allow transitions"

    def test_combinable_true_for_all_price_intents(self, source):
        """combinable must be True for ALL price-related intents."""
        price_intents = [
            "price_question",
            "pricing_details",
            "cost_inquiry",
            "discount_request",
            "payment_terms",
            "pricing_comparison",
            "budget_question",
        ]

        for intent in price_intents:
            bb = create_blackboard(intent=intent)
            source.contribute(bb)
            proposals = bb.get_action_proposals()

            assert len(proposals) == 1, f"No proposal for {intent}"
            assert proposals[0].combinable is True, \
                f"Intent {intent} MUST have combinable=True"

    def test_contribute_metadata_includes_original_intent(self, source):
        """Metadata should include original intent."""
        bb = create_blackboard(intent="cost_inquiry")

        source.contribute(bb)

        proposals = bb.get_action_proposals()
        assert proposals[0].metadata["original_intent"] == "cost_inquiry"

    def test_contribute_metadata_includes_pricing_data_status(self, source):
        """Metadata should include has_pricing_data flag."""
        # Without pricing data
        bb1 = create_blackboard(intent="price_question")
        source.contribute(bb1)
        assert bb1.get_action_proposals()[0].metadata["has_pricing_data"] is False

        # With pricing data
        bb2 = create_blackboard(
            intent="price_question",
            collected_data={"pricing_tier": "enterprise"}
        )
        source.contribute(bb2)
        assert bb2.get_action_proposals()[0].metadata["has_pricing_data"] is True


class TestPriceQuestionSourceIntentManagement:
    """Test PriceQuestionSource intent management."""

    def test_add_price_intent(self):
        """Test adding a custom price intent."""
        source = PriceQuestionSource()
        source.add_price_intent("custom_price_intent")

        assert "custom_price_intent" in source.price_intents

    def test_remove_price_intent(self):
        """Test removing a price intent."""
        source = PriceQuestionSource()
        source.remove_price_intent("price_question")

        assert "price_question" not in source.price_intents

    def test_custom_intents_at_init(self):
        """Test initialization with custom intents."""
        custom_intents = {"my_price", "my_cost"}
        source = PriceQuestionSource(price_intents=custom_intents)

        assert source.price_intents == custom_intents
        assert "price_question" not in source.price_intents


class TestPriceQuestionSourceEnableDisable:
    """Test PriceQuestionSource enable/disable functionality."""

    def test_enable_source(self):
        """Test enabling source."""
        source = PriceQuestionSource()
        source.disable()
        source.enable()

        assert source.enabled is True

    def test_disable_source(self):
        """Test disabling source."""
        source = PriceQuestionSource()
        source.disable()

        assert source.enabled is False

    def test_disabled_source_no_contribution(self):
        """Disabled source should not contribute."""
        bb = create_blackboard(intent="price_question")
        source = PriceQuestionSource()
        source.disable()

        source.contribute(bb)

        assert len(bb.get_action_proposals()) == 0


class TestPriceQuestionSourceInit:
    """Test PriceQuestionSource initialization."""

    def test_init_default(self):
        """Test default initialization."""
        source = PriceQuestionSource()

        assert source.name == "PriceQuestionSource"
        assert source.enabled is True
        assert "price_question" in source.price_intents
        assert "discount_request" in source.price_intents

    def test_init_with_custom_name(self):
        """Test initialization with custom name."""
        source = PriceQuestionSource(name="CustomPriceSource")

        assert source.name == "CustomPriceSource"

    def test_default_price_intents(self):
        """Test that default price intents are correct."""
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
