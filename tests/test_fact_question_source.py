# tests/test_fact_question_source.py

"""
Tests for FactQuestionSource.

These tests verify the Knowledge Source that handles fact-based questions,
working in conjunction with SecondaryIntentDetectionLayer to respond
to questions that might be lost in composite message classification.
"""

import pytest
from typing import Dict, Any, List, Optional
from unittest.mock import Mock, MagicMock, patch
from dataclasses import dataclass, field

from src.blackboard.sources.fact_question import FactQuestionSource
from src.blackboard.enums import Priority


# =============================================================================
# MOCK CLASSES
# =============================================================================

@dataclass
class MockContextEnvelope:
    """Mock context envelope with secondary intents support."""
    frustration_level: int = 0
    is_stuck: bool = False
    has_oscillation: bool = False
    momentum: float = 0.0
    engagement_level: str = "medium"
    repeated_question: Optional[str] = None
    tone: Optional[str] = None
    secondary_intents: List[str] = field(default_factory=list)
    classification_result: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MockContextSnapshot:
    """Mock context snapshot for blackboard."""
    state: str = "bant_budget"
    current_intent: str = "info_provided"
    last_intent: str = "greeting"
    collected_data: Dict[str, Any] = field(default_factory=dict)
    state_config: Dict[str, Any] = field(default_factory=dict)
    turn_number: int = 1
    current_phase: str = "budget"
    context_envelope: MockContextEnvelope = field(default_factory=MockContextEnvelope)

    def get_missing_required_data(self) -> List[str]:
        return []


class MockBlackboard:
    """Mock blackboard for testing."""

    def __init__(
        self,
        current_intent: str = "info_provided",
        state: str = "bant_budget",
        secondary_intents: List[str] = None,
        state_config: Dict[str, Any] = None,
    ):
        self.current_intent = current_intent
        self._state = state
        self._secondary_intents = secondary_intents or []
        self._state_config = state_config or {}
        self._proposals = []

        # Create context envelope with secondary intents
        envelope = MockContextEnvelope(
            secondary_intents=self._secondary_intents,
            classification_result={"secondary_signals": self._secondary_intents}
        )

        # Create context snapshot
        self._context = MockContextSnapshot(
            state=state,
            current_intent=current_intent,
            state_config=self._state_config,
            context_envelope=envelope,
        )

    def get_context(self) -> MockContextSnapshot:
        return self._context

    def propose_action(
        self,
        action: str,
        priority: Priority,
        combinable: bool,
        reason_code: str,
        source_name: str,
        metadata: Dict[str, Any] = None,
    ):
        self._proposals.append({
            "action": action,
            "priority": priority,
            "combinable": combinable,
            "reason_code": reason_code,
            "source_name": source_name,
            "metadata": metadata or {},
        })


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def source():
    """Create a FactQuestionSource instance."""
    return FactQuestionSource()


@pytest.fixture
def make_blackboard():
    """Factory for creating mock blackboards."""
    def _make(
        current_intent: str = "info_provided",
        state: str = "bant_budget",
        secondary_intents: List[str] = None,
        rules: Dict[str, Any] = None,
    ) -> MockBlackboard:
        state_config = {}
        if rules:
            state_config["rules"] = rules
        return MockBlackboard(
            current_intent=current_intent,
            state=state,
            secondary_intents=secondary_intents,
            state_config=state_config,
        )
    return _make


# =============================================================================
# BASIC FUNCTIONALITY TESTS
# =============================================================================

class TestFactQuestionSourceBasics:
    """Test basic functionality of FactQuestionSource."""

    def test_source_initialization(self, source):
        """Test source initializes correctly."""
        assert source.name == "FactQuestionSource"
        assert source._enabled is True
        assert len(source._fact_intents) > 0

    def test_default_fact_intents(self, source):
        """Test default fact intents are loaded."""
        expected_intents = [
            "question_features",
            "question_integrations",
            "question_technical",
            "question_equipment_general",
            "comparison",
        ]
        for intent in expected_intents:
            assert intent in source._fact_intents, f"Missing fact intent: {intent}"

    def test_price_intents_excluded(self, source):
        """Test that price intents are excluded (handled by PriceQuestionSource)."""
        price_intents = [
            "price_question",
            "pricing_details",
            "cost_inquiry",
        ]
        for intent in price_intents:
            assert intent not in source._fact_intents, f"Price intent should be excluded: {intent}"


# =============================================================================
# SHOULD_CONTRIBUTE TESTS
# =============================================================================

class TestShouldContribute:
    """Test should_contribute() method."""

    def test_contribute_on_primary_fact_intent(self, source, make_blackboard):
        """Test contribution when primary intent is fact-requiring."""
        blackboard = make_blackboard(current_intent="question_features")

        assert source.should_contribute(blackboard) is True

    def test_contribute_on_secondary_fact_intent(self, source, make_blackboard):
        """Test contribution when secondary intent is fact-requiring."""
        blackboard = make_blackboard(
            current_intent="info_provided",
            secondary_intents=["question_features"]
        )

        assert source.should_contribute(blackboard) is True

    def test_no_contribute_on_non_fact_intent(self, source, make_blackboard):
        """Test no contribution when no fact intent present."""
        blackboard = make_blackboard(
            current_intent="agreement",
            secondary_intents=["gratitude"]
        )

        assert source.should_contribute(blackboard) is False

    def test_no_contribute_on_price_intent(self, source, make_blackboard):
        """Test no contribution for price intents (handled by PriceQuestionSource)."""
        blackboard = make_blackboard(current_intent="price_question")

        assert source.should_contribute(blackboard) is False

    def test_disabled_source_no_contribute(self, source, make_blackboard):
        """Test disabled source doesn't contribute."""
        source._enabled = False
        blackboard = make_blackboard(current_intent="question_features")

        assert source.should_contribute(blackboard) is False

        source._enabled = True  # Re-enable for other tests


# =============================================================================
# CONTRIBUTE TESTS - PRIMARY INTENT
# =============================================================================

class TestContributePrimaryIntent:
    """Test contribute() with primary fact intent."""

    def test_propose_action_for_features(self, source, make_blackboard):
        """Test action proposed for question_features."""
        blackboard = make_blackboard(current_intent="question_features")

        source.contribute(blackboard)

        assert len(blackboard._proposals) == 1
        proposal = blackboard._proposals[0]
        assert proposal["action"] == "answer_with_facts"
        assert proposal["priority"] == Priority.HIGH
        assert proposal["combinable"] is True
        assert proposal["metadata"]["fact_intent"] == "question_features"
        assert proposal["metadata"]["detection_source"] == "primary"

    def test_propose_action_for_technical(self, source, make_blackboard):
        """Test custom action for question_technical."""
        blackboard = make_blackboard(current_intent="question_technical")

        source.contribute(blackboard)

        assert len(blackboard._proposals) == 1
        proposal = blackboard._proposals[0]
        # question_technical has custom action
        assert proposal["action"] == "answer_technical_question"

    def test_propose_action_for_comparison(self, source, make_blackboard):
        """Test custom action for comparison intent."""
        blackboard = make_blackboard(current_intent="comparison")

        source.contribute(blackboard)

        assert len(blackboard._proposals) == 1
        proposal = blackboard._proposals[0]
        assert proposal["action"] == "compare_with_competitor"


# =============================================================================
# CONTRIBUTE TESTS - SECONDARY INTENT
# =============================================================================

class TestContributeSecondaryIntent:
    """Test contribute() with secondary fact intent."""

    def test_propose_action_for_secondary_features(self, source, make_blackboard):
        """Test action proposed when question_features is secondary."""
        blackboard = make_blackboard(
            current_intent="info_provided",
            secondary_intents=["question_features"]
        )

        source.contribute(blackboard)

        assert len(blackboard._proposals) == 1
        proposal = blackboard._proposals[0]
        assert proposal["action"] == "answer_with_facts"
        assert proposal["metadata"]["fact_intent"] == "question_features"
        assert proposal["metadata"]["detection_source"] == "secondary"
        assert proposal["metadata"]["primary_intent"] == "info_provided"

    def test_propose_action_for_secondary_integrations(self, source, make_blackboard):
        """Test action proposed when question_integrations is secondary."""
        blackboard = make_blackboard(
            current_intent="situation_provided",
            secondary_intents=["question_integrations"]
        )

        source.contribute(blackboard)

        assert len(blackboard._proposals) == 1
        proposal = blackboard._proposals[0]
        assert proposal["action"] == "answer_with_facts"
        assert proposal["metadata"]["fact_intent"] == "question_integrations"
        assert proposal["metadata"]["detection_source"] == "secondary"

    def test_primary_takes_precedence_over_secondary(self, source, make_blackboard):
        """Test that primary fact intent takes precedence over secondary."""
        blackboard = make_blackboard(
            current_intent="question_technical",  # Primary fact intent
            secondary_intents=["question_features"]  # Secondary fact intent
        )

        source.contribute(blackboard)

        assert len(blackboard._proposals) == 1
        proposal = blackboard._proposals[0]
        # Should use primary intent
        assert proposal["metadata"]["fact_intent"] == "question_technical"
        assert proposal["metadata"]["detection_source"] == "primary"


# =============================================================================
# YAML RULES TESTS
# =============================================================================

class TestYamlRules:
    """Test that YAML rules are respected."""

    def test_yaml_rule_override(self, source, make_blackboard):
        """Test that YAML rule overrides default action."""
        blackboard = make_blackboard(
            current_intent="question_features",
            rules={
                "question_features": "custom_features_response"
            }
        )

        source.contribute(blackboard)

        assert len(blackboard._proposals) == 1
        proposal = blackboard._proposals[0]
        assert proposal["action"] == "custom_features_response"
        assert proposal["metadata"]["rule_source"] == "yaml_rule"

    def test_fallback_when_no_yaml_rule(self, source, make_blackboard):
        """Test fallback action when no YAML rule defined."""
        blackboard = make_blackboard(
            current_intent="question_features",
            rules={}  # No rules
        )

        source.contribute(blackboard)

        assert len(blackboard._proposals) == 1
        proposal = blackboard._proposals[0]
        assert proposal["action"] == "answer_with_facts"
        assert proposal["metadata"]["rule_source"] == "fallback"


# =============================================================================
# COMBINABLE TESTS
# =============================================================================

class TestCombinableActions:
    """Test that actions are combinable with transitions."""

    def test_action_is_combinable(self, source, make_blackboard):
        """Test that fact question actions are combinable."""
        blackboard = make_blackboard(current_intent="question_features")

        source.contribute(blackboard)

        assert len(blackboard._proposals) == 1
        proposal = blackboard._proposals[0]
        assert proposal["combinable"] is True

    def test_action_has_high_priority(self, source, make_blackboard):
        """Test that fact question actions have HIGH priority."""
        blackboard = make_blackboard(current_intent="question_features")

        source.contribute(blackboard)

        assert len(blackboard._proposals) == 1
        proposal = blackboard._proposals[0]
        assert proposal["priority"] == Priority.HIGH


# =============================================================================
# STATISTICS TESTS
# =============================================================================

class TestStatistics:
    """Test statistics tracking."""

    def test_primary_detection_stats(self, source, make_blackboard):
        """Test that primary detections are tracked."""
        # Reset stats
        source._primary_detections = 0
        source._secondary_detections = 0

        blackboard = make_blackboard(current_intent="question_features")
        source.contribute(blackboard)

        assert source._primary_detections == 1
        assert source._secondary_detections == 0

    def test_secondary_detection_stats(self, source, make_blackboard):
        """Test that secondary detections are tracked."""
        # Reset stats
        source._primary_detections = 0
        source._secondary_detections = 0

        blackboard = make_blackboard(
            current_intent="info_provided",
            secondary_intents=["question_features"]
        )
        source.contribute(blackboard)

        assert source._primary_detections == 0
        assert source._secondary_detections == 1

    def test_get_stats(self, source):
        """Test get_stats returns expected structure."""
        stats = source.get_stats()

        assert "name" in stats
        assert "enabled" in stats
        assert "fact_intents_count" in stats
        assert "primary_detections" in stats
        assert "secondary_detections" in stats
        assert "total_detections" in stats


# =============================================================================
# EDGE CASES TESTS
# =============================================================================

class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_secondary_intents(self, source, make_blackboard):
        """Test handling of empty secondary intents."""
        blackboard = make_blackboard(
            current_intent="agreement",
            secondary_intents=[]
        )

        assert source.should_contribute(blackboard) is False

    def test_none_secondary_intents(self, source, make_blackboard):
        """Test handling of None secondary intents."""
        blackboard = make_blackboard(
            current_intent="agreement",
            secondary_intents=None
        )

        assert source.should_contribute(blackboard) is False

    def test_disabled_source_no_proposals(self, source, make_blackboard):
        """Test that disabled source makes no proposals."""
        source._enabled = False
        blackboard = make_blackboard(current_intent="question_features")

        source.contribute(blackboard)

        assert len(blackboard._proposals) == 0

        source._enabled = True  # Re-enable

    def test_multiple_secondary_fact_intents(self, source, make_blackboard):
        """Test handling of multiple secondary fact intents."""
        blackboard = make_blackboard(
            current_intent="info_provided",
            secondary_intents=["question_features", "question_integrations"]
        )

        source.contribute(blackboard)

        assert len(blackboard._proposals) == 1
        # Should use first matching fact intent
        proposal = blackboard._proposals[0]
        assert proposal["metadata"]["fact_intent"] in [
            "question_features", "question_integrations"
        ]


# =============================================================================
# REAL-WORLD SCENARIO TESTS
# =============================================================================

class TestRealWorldScenarios:
    """Test real-world scenarios from the bug report."""

    def test_composite_message_with_price_secondary(self, source, make_blackboard):
        """
        Scenario: User says "100 человек. Сколько стоит?"
        - Primary: info_provided
        - Secondary: price_question (handled by PriceQuestionSource, not this source)
        """
        blackboard = make_blackboard(
            current_intent="info_provided",
            secondary_intents=["price_question"]  # Price is excluded
        )

        # Should NOT contribute (price handled by PriceQuestionSource)
        assert source.should_contribute(blackboard) is False

    def test_composite_message_with_features_secondary(self, source, make_blackboard):
        """
        Scenario: User says "У нас ресторан. Какие функции есть?"
        - Primary: situation_provided
        - Secondary: question_features
        """
        blackboard = make_blackboard(
            current_intent="situation_provided",
            secondary_intents=["question_features"]
        )

        assert source.should_contribute(blackboard) is True
        source.contribute(blackboard)

        assert len(blackboard._proposals) == 1
        proposal = blackboard._proposals[0]
        assert proposal["action"] == "answer_with_facts"
        assert proposal["metadata"]["fact_intent"] == "question_features"
        assert proposal["metadata"]["detection_source"] == "secondary"

    def test_composite_message_with_integration_secondary(self, source, make_blackboard):
        """
        Scenario: User says "10 касс. Есть интеграция с Каспи?"
        - Primary: info_provided
        - Secondary: question_integrations
        """
        blackboard = make_blackboard(
            current_intent="info_provided",
            secondary_intents=["question_integrations"]
        )

        assert source.should_contribute(blackboard) is True
        source.contribute(blackboard)

        assert len(blackboard._proposals) == 1
        proposal = blackboard._proposals[0]
        assert proposal["action"] == "answer_with_facts"
        assert proposal["metadata"]["fact_intent"] == "question_integrations"

    def test_bant_flow_with_fact_question(self, source, make_blackboard):
        """
        Scenario: In BANT authority phase, user asks about features
        - State: bant_authority
        - Primary: info_provided
        - Secondary: question_features
        """
        blackboard = make_blackboard(
            current_intent="info_provided",
            state="bant_authority",
            secondary_intents=["question_features"]
        )

        assert source.should_contribute(blackboard) is True
        source.contribute(blackboard)

        # Should propose answer even in BANT flow
        assert len(blackboard._proposals) == 1
        proposal = blackboard._proposals[0]
        assert proposal["combinable"] is True  # Allows BANT to continue
