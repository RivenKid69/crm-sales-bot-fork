"""
Unit tests for ClassificationRefinementLayer.

Tests the State Loop Fix: context-aware refinement of LLM classification
for short messages that are incorrectly classified as "greeting".
"""

import pytest
from src.classifier.refinement import (
    ClassificationRefinementLayer,
    RefinementContext,
    create_refinement_context
)

class TestClassificationRefinementLayer:
    """Tests for ClassificationRefinementLayer."""

    @pytest.fixture
    def layer(self):
        """Create refinement layer instance."""
        return ClassificationRefinementLayer()

    @pytest.fixture
    def situation_context(self):
        """Context for situation phase (most common State Loop scenario)."""
        return RefinementContext(
            message="1",
            spin_phase="situation",
            state="greeting",
            last_action="ask_about_company",
            last_intent=None
        )

    @pytest.fixture
    def problem_context(self):
        """Context for problem phase."""
        return RefinementContext(
            message="да",
            spin_phase="problem",
            state="spin_problem",
            last_action="ask_about_problem",
            last_intent=None
        )

    @pytest.fixture
    def no_context(self):
        """Context without SPIN phase (refinement should NOT apply)."""
        return RefinementContext(
            message="привет",
            spin_phase=None,
            state=None,
            last_action=None,
            last_intent=None
        )

    # =========================================================================
    # should_refine() tests
    # =========================================================================

    def test_should_refine_short_greeting_in_situation(self, layer, situation_context):
        """Short message + greeting intent + situation phase → should refine."""
        assert layer.should_refine("1", "greeting", situation_context)

    def test_should_refine_short_unclear_in_situation(self, layer, situation_context):
        """Short message + unclear intent + situation phase → should refine."""
        assert layer.should_refine("да", "unclear", situation_context)

    def test_should_refine_short_small_talk_in_situation(self, layer, situation_context):
        """Short message + small_talk intent + situation phase → should refine."""
        assert layer.should_refine("5", "small_talk", situation_context)

    def test_should_not_refine_long_message(self, layer, situation_context):
        """Long message → should NOT refine."""
        long_msg = "У нас в компании работает около 10 человек в отделе продаж"
        assert not layer.should_refine(long_msg, "greeting", situation_context)

    def test_should_not_refine_specific_intent(self, layer, situation_context):
        """Specific intent (not greeting/unclear) → should NOT refine."""
        assert not layer.should_refine("1", "objection_price", situation_context)
        assert not layer.should_refine("1", "info_provided", situation_context)
        assert not layer.should_refine("1", "situation_provided", situation_context)

    def test_should_not_refine_no_context(self, layer, no_context):
        """No SPIN phase and no greeting state → should NOT refine."""
        assert not layer.should_refine("1", "greeting", no_context)

    def test_should_refine_greeting_state_even_without_phase(self, layer):
        """In greeting state without phase → should still refine."""
        ctx = RefinementContext(
            message="1",
            spin_phase=None,  # No phase
            state="greeting",  # But in greeting state
            last_action=None,
            last_intent=None
        )
        assert layer.should_refine("1", "greeting", ctx)

    def test_should_refine_with_awaiting_data_action(self, layer):
        """With awaiting_data action → should refine."""
        ctx = RefinementContext(
            message="да",
            spin_phase=None,
            state="spin_situation",
            last_action="ask_situation",  # Awaiting data action
            last_intent=None
        )
        assert layer.should_refine("да", "greeting", ctx)

    # =========================================================================
    # refine() tests - situation phase
    # =========================================================================

    def test_refine_number_to_situation_provided(self, layer, situation_context):
        """'1' classified as greeting in situation phase → situation_provided."""
        llm_result = {"intent": "greeting", "confidence": 0.95}

        refined = layer.refine("1", llm_result, situation_context)

        assert refined["intent"] == "situation_provided"
        assert refined["refined"] is True
        assert refined["original_intent"] == "greeting"
        assert 0 < refined["confidence"] <= 1

    def test_refine_yes_to_situation_provided(self, layer, situation_context):
        """'да' classified as greeting in situation phase → situation_provided."""
        llm_result = {"intent": "greeting", "confidence": 0.9}

        refined = layer.refine("да", llm_result, situation_context)

        assert refined["intent"] == "situation_provided"
        assert refined["refined"] is True

    def test_refine_number_word_to_situation_provided(self, layer, situation_context):
        """'первое' classified as unclear → situation_provided."""
        llm_result = {"intent": "unclear", "confidence": 0.7}

        refined = layer.refine("первое", llm_result, situation_context)

        assert refined["intent"] == "situation_provided"
        assert refined["refined"] is True

    # =========================================================================
    # refine() tests - problem phase
    # =========================================================================

    def test_refine_yes_to_problem_revealed(self, layer, problem_context):
        """'да' in problem phase → problem_revealed."""
        llm_result = {"intent": "greeting", "confidence": 0.8}

        refined = layer.refine("да", llm_result, problem_context)

        assert refined["intent"] == "problem_revealed"
        assert refined["refined"] is True

    def test_refine_no_to_no_problem(self, layer):
        """'нет' in problem phase → no_problem."""
        ctx = RefinementContext(
            message="нет",
            spin_phase="problem",
            state="spin_problem",
            last_action="ask_about_problem",
            last_intent=None
        )
        llm_result = {"intent": "greeting", "confidence": 0.8}

        refined = layer.refine("нет", llm_result, ctx)

        assert refined["intent"] == "no_problem"
        assert refined["refined"] is True

    # =========================================================================
    # refine() tests - preserve fields
    # =========================================================================

    def test_refine_preserves_other_fields(self, layer, situation_context):
        """Refinement preserves extracted_data and other fields."""
        llm_result = {
            "intent": "greeting",
            "confidence": 0.95,
            "extracted_data": {"company_size": 1},
            "method": "llm",
            "alternatives": [{"intent": "unclear", "confidence": 0.3}]
        }

        refined = layer.refine("1", llm_result, situation_context)

        assert refined["extracted_data"] == {"company_size": 1}
        assert refined["method"] == "llm"
        assert refined["alternatives"] == [{"intent": "unclear", "confidence": 0.3}]

    def test_refine_adds_refinement_metadata(self, layer, situation_context):
        """Refinement adds metadata fields."""
        llm_result = {"intent": "greeting", "confidence": 0.95}

        refined = layer.refine("1", llm_result, situation_context)

        assert "refined" in refined
        assert "original_intent" in refined
        assert "original_confidence" in refined
        assert "refinement_reason" in refined

    # =========================================================================
    # refine() tests - no refinement cases
    # =========================================================================

    def test_no_refine_for_long_message(self, layer, situation_context):
        """Long message returns original result unchanged."""
        llm_result = {"intent": "greeting", "confidence": 0.95}
        long_msg = "У нас большая компания с множеством отделов"

        refined = layer.refine(long_msg, llm_result, situation_context)

        assert refined["intent"] == "greeting"
        assert "refined" not in refined or refined.get("refined") is False

    def test_no_refine_for_specific_intent(self, layer, situation_context):
        """Specific intent returns original result unchanged."""
        llm_result = {"intent": "objection_price", "confidence": 0.9}

        refined = layer.refine("дорого", llm_result, situation_context)

        assert refined["intent"] == "objection_price"
        assert "refined" not in refined or refined.get("refined") is False

    # =========================================================================
    # Sentiment detection tests
    # =========================================================================

    def test_detect_positive_number(self, layer):
        """Numbers are detected as positive."""
        assert layer._detect_sentiment("5") == "positive"
        assert layer._detect_sentiment("10") == "positive"
        assert layer._detect_sentiment("100 человек") == "positive"

    def test_detect_positive_confirmation(self, layer):
        """Confirmations are detected as positive."""
        assert layer._detect_sentiment("да") == "positive"
        assert layer._detect_sentiment("хорошо") == "positive"
        assert layer._detect_sentiment("ок") == "positive"
        assert layer._detect_sentiment("конечно") == "positive"

    def test_detect_negative(self, layer):
        """Negations are detected as negative."""
        assert layer._detect_sentiment("нет") == "negative"
        assert layer._detect_sentiment("не надо") == "negative"
        assert layer._detect_sentiment("не нужно") == "negative"

    def test_detect_neutral(self, layer):
        """Unclear/neutral messages are detected as neutral."""
        assert layer._detect_sentiment("может") == "neutral"
        assert layer._detect_sentiment("хм") == "neutral"

    # =========================================================================
    # Short message detection tests
    # =========================================================================

    def test_is_short_message_number(self, layer):
        """Numbers are short messages."""
        assert layer._is_short_message("1")
        assert layer._is_short_message("10")
        assert layer._is_short_message("100")

    def test_is_short_message_single_word(self, layer):
        """Single words are short messages."""
        assert layer._is_short_message("да")
        assert layer._is_short_message("нет")
        assert layer._is_short_message("первое")

    def test_is_short_message_few_words(self, layer):
        """Few words are short messages."""
        assert layer._is_short_message("да хорошо")
        assert layer._is_short_message("5 человек")
        assert layer._is_short_message("нет спасибо")

    def test_is_not_short_message_long(self, layer):
        """Long messages are not short."""
        long_msg = "У нас в компании работает около 10 человек в отделе продаж"
        assert not layer._is_short_message(long_msg)

    # =========================================================================
    # Helper function tests
    # =========================================================================

    def test_create_refinement_context_full(self):
        """create_refinement_context creates context from dict."""
        ctx = create_refinement_context("test", {
            "spin_phase": "situation",
            "state": "greeting",
            "last_action": "ask_about_company",
            "last_intent": "greeting"
        })

        assert ctx.message == "test"
        assert ctx.spin_phase == "situation"
        assert ctx.state == "greeting"
        assert ctx.last_action == "ask_about_company"
        assert ctx.last_intent == "greeting"

    def test_create_refinement_context_empty(self):
        """create_refinement_context handles empty dict."""
        ctx = create_refinement_context("test", {})

        assert ctx.message == "test"
        assert ctx.spin_phase is None
        assert ctx.state is None
        assert ctx.last_action is None
        assert ctx.last_intent is None

    def test_create_refinement_context_none(self):
        """create_refinement_context handles None."""
        ctx = create_refinement_context("test", None)

        assert ctx.message == "test"
        assert ctx.spin_phase is None

class TestStateLoopScenarios:
    """
    Test scenarios that caused State Loop bug.

    These are regression tests based on actual logs from the simulation.
    """

    @pytest.fixture
    def layer(self):
        return ClassificationRefinementLayer()

    def test_scenario_number_one_in_greeting(self, layer):
        """
        Scenario: Bot asks "How many employees?" Client answers "1"
        LLM incorrectly classifies as greeting.
        """
        ctx = RefinementContext(
            message="1",
            spin_phase="situation",
            state="greeting",
            last_action="ask_about_company",
            last_intent=None
        )
        llm_result = {"intent": "greeting", "confidence": 0.95}

        refined = layer.refine("1", llm_result, ctx)

        # Should be refined to situation_provided
        assert refined["intent"] == "situation_provided"
        assert refined["refined"] is True

    def test_scenario_pervoe_in_greeting(self, layer):
        """
        Scenario: Bot offers options, Client answers "первое"
        LLM incorrectly classifies as greeting.
        """
        ctx = RefinementContext(
            message="первое",
            spin_phase="situation",
            state="greeting",
            last_action="ask_for_clarification",
            last_intent=None
        )
        llm_result = {"intent": "greeting", "confidence": 0.95}

        refined = layer.refine("первое", llm_result, ctx)

        assert refined["intent"] == "situation_provided"
        assert refined["refined"] is True

    def test_scenario_da_in_problem_phase(self, layer):
        """
        Scenario: Bot asks about problems, Client says "да"
        LLM incorrectly classifies as greeting.
        """
        ctx = RefinementContext(
            message="да",
            spin_phase="problem",
            state="spin_problem",
            last_action="ask_about_problem",
            last_intent=None
        )
        llm_result = {"intent": "greeting", "confidence": 0.9}

        refined = layer.refine("да", llm_result, ctx)

        assert refined["intent"] == "problem_revealed"
        assert refined["refined"] is True

    def test_scenario_real_greeting_not_refined(self, layer):
        """
        Scenario: Actual greeting at start of conversation.
        Should NOT be refined.
        """
        ctx = RefinementContext(
            message="привет",
            spin_phase=None,
            state=None,
            last_action=None,
            last_intent=None
        )
        llm_result = {"intent": "greeting", "confidence": 0.99}

        refined = layer.refine("привет", llm_result, ctx)

        # Real greeting should NOT be refined
        assert refined["intent"] == "greeting"
        assert "refined" not in refined or refined.get("refined") is False
