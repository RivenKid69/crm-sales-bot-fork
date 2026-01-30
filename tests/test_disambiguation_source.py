# tests/test_disambiguation_source.py

"""
Unit tests for DisambiguationSource.

Covers:
- should_contribute: True when intent == "disambiguation_needed", False otherwise
- contribute: proposes ask_clarification with HIGH priority, combinable=False
- Metadata flow: disambiguation_options and disambiguation_question passed correctly
"""

import pytest
from unittest.mock import MagicMock, PropertyMock
from typing import Dict, Any, List

from src.blackboard.sources.disambiguation import DisambiguationSource
from src.blackboard.enums import Priority, ProposalType


# =============================================================================
# Helpers
# =============================================================================

class MockBlackboard:
    """Minimal mock of DialogueBlackboard."""

    def __init__(self, intent: str = "greeting", options: list = None, question: str = ""):
        self._intent = intent
        self._proposals = []
        self._options = options or []
        self._question = question

    @property
    def current_intent(self):
        return self._intent

    def get_context(self):
        ctx = MagicMock()
        envelope = MagicMock()
        envelope.classification_result = {
            "disambiguation_options": self._options,
            "disambiguation_question": self._question,
        }
        ctx.context_envelope = envelope
        return ctx

    def propose_action(self, **kwargs):
        self._proposals.append(kwargs)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def source():
    return DisambiguationSource()


@pytest.fixture
def sample_options():
    return [
        {"intent": "price_question", "label": "Узнать цены"},
        {"intent": "demo_request", "label": "Записаться на демо"},
    ]


# =============================================================================
# Test: should_contribute
# =============================================================================

class TestShouldContribute:

    def test_true_when_disambiguation_needed(self, source):
        bb = MockBlackboard(intent="disambiguation_needed")
        assert source.should_contribute(bb) is True

    def test_false_when_other_intent(self, source):
        for intent in ["greeting", "price_question", "unclear", "info_provided", "rejection"]:
            bb = MockBlackboard(intent=intent)
            assert source.should_contribute(bb) is False, f"Should not contribute for {intent}"

    def test_false_when_disabled(self, source):
        source.disable()
        bb = MockBlackboard(intent="disambiguation_needed")
        assert source.should_contribute(bb) is False


# =============================================================================
# Test: contribute
# =============================================================================

class TestContribute:

    def test_proposes_ask_clarification(self, source, sample_options):
        bb = MockBlackboard(
            intent="disambiguation_needed",
            options=sample_options,
            question="Уточните, пожалуйста:",
        )

        source.contribute(bb)

        assert len(bb._proposals) == 1
        proposal = bb._proposals[0]
        assert proposal["action"] == "ask_clarification"

    def test_priority_is_high(self, source, sample_options):
        bb = MockBlackboard(
            intent="disambiguation_needed",
            options=sample_options,
        )

        source.contribute(bb)

        proposal = bb._proposals[0]
        assert proposal["priority"] == Priority.HIGH

    def test_combinable_is_false(self, source, sample_options):
        bb = MockBlackboard(
            intent="disambiguation_needed",
            options=sample_options,
        )

        source.contribute(bb)

        proposal = bb._proposals[0]
        assert proposal["combinable"] is False

    def test_reason_code(self, source, sample_options):
        bb = MockBlackboard(
            intent="disambiguation_needed",
            options=sample_options,
        )

        source.contribute(bb)

        proposal = bb._proposals[0]
        assert proposal["reason_code"] == "disambiguation_needed"

    def test_metadata_contains_options(self, source, sample_options):
        bb = MockBlackboard(
            intent="disambiguation_needed",
            options=sample_options,
            question="Уточните:",
        )

        source.contribute(bb)

        proposal = bb._proposals[0]
        assert proposal["metadata"]["disambiguation_options"] == sample_options
        assert proposal["metadata"]["disambiguation_question"] == "Уточните:"

    def test_no_proposals_when_disabled(self, source, sample_options):
        source.disable()
        bb = MockBlackboard(
            intent="disambiguation_needed",
            options=sample_options,
        )

        source.contribute(bb)

        assert len(bb._proposals) == 0

    def test_empty_options_still_proposes(self, source):
        """Even with empty options, the source proposes (bot.py handles the edge case)."""
        bb = MockBlackboard(
            intent="disambiguation_needed",
            options=[],
            question="",
        )

        source.contribute(bb)

        assert len(bb._proposals) == 1
        proposal = bb._proposals[0]
        assert proposal["metadata"]["disambiguation_options"] == []


# =============================================================================
# Test: Source name
# =============================================================================

class TestSourceName:

    def test_default_name(self, source):
        assert source.name == "DisambiguationSource"

    def test_custom_name(self):
        source = DisambiguationSource(name="CustomDisambig")
        assert source.name == "CustomDisambig"


# =============================================================================
# Test: Context envelope edge cases
# =============================================================================

class TestContextEnvelopeEdgeCases:

    def test_no_context_envelope(self, source):
        """Handle case where context_envelope is None."""
        bb = MockBlackboard(intent="disambiguation_needed")
        # Override get_context to return None envelope
        ctx = MagicMock()
        ctx.context_envelope = None
        bb.get_context = lambda: ctx

        source.contribute(bb)

        assert len(bb._proposals) == 1
        proposal = bb._proposals[0]
        assert proposal["metadata"]["disambiguation_options"] == []
        assert proposal["metadata"]["disambiguation_question"] == ""

    def test_no_classification_result_attribute(self, source):
        """Handle case where classification_result attribute is missing."""
        bb = MockBlackboard(intent="disambiguation_needed")
        ctx = MagicMock()
        ctx.context_envelope = MagicMock(spec=[])  # No attributes
        bb.get_context = lambda: ctx

        source.contribute(bb)

        assert len(bb._proposals) == 1
        proposal = bb._proposals[0]
        assert proposal["metadata"]["disambiguation_options"] == []
