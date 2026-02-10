"""
Unit tests for OptionSelectionRefinementLayer.

Tests the Disambiguation Assist Fix: context-aware refinement of LLM classification
for short numeric/ordinal responses ("1", "2", "первое") that are incorrectly
classified as request_brevity when they're actually option selections.

Problem Scenario:
    Bot: "Что для вас приоритетнее — скорость или функционал?"
    User: "1"
    LLM: request_brevity (0.9) ← WRONG
    Expected: info_provided with option_selection signal

Research basis:
    - Grice's Cooperative Principle: short answers carry implicature
    - Conversational repair: numeric responses to binary questions = selections
"""

import pytest
from typing import Dict, Any

from src.classifier.refinement_layers import OptionSelectionRefinementLayer
from src.classifier.refinement_pipeline import (
    RefinementContext,
    RefinementDecision,
    LayerPriority,
)

class TestOptionSelectionRefinementLayer:
    """Tests for OptionSelectionRefinementLayer."""

    @pytest.fixture
    def layer(self):
        """Create refinement layer instance."""
        return OptionSelectionRefinementLayer()

    @pytest.fixture
    def option_question_context(self) -> RefinementContext:
        """Context where bot asked option question and user replied "1"."""
        return RefinementContext(
            message="1",
            intent="request_brevity",
            confidence=0.9,
            state="spin_situation",
            phase="situation",
            last_action="ask_about_priority",
            last_bot_message="Что для вас приоритетнее — скорость или функционал?",
            metadata={}
        )

    @pytest.fixture
    def option_question_context_ordinal(self) -> RefinementContext:
        """Context where bot asked option question and user replied "первое"."""
        return RefinementContext(
            message="первое",
            intent="request_brevity",
            confidence=0.85,
            state="spin_problem",
            phase="problem",
            last_action="ask_priority",
            last_bot_message="Вам важнее скорость внедрения или гибкость настройки?",
            metadata={}
        )

    @pytest.fixture
    def no_option_context(self) -> RefinementContext:
        """Context where bot did NOT ask option question."""
        return RefinementContext(
            message="1",
            intent="request_brevity",
            confidence=0.9,
            state="spin_situation",
            phase="situation",
            last_action="ask_about_company",
            last_bot_message="Сколько человек работает в вашей компании?",
            metadata={}
        )

    @pytest.fixture
    def non_selection_message_context(self) -> RefinementContext:
        """Context where message is not a selection."""
        return RefinementContext(
            message="да, расскажите подробнее",
            intent="request_brevity",
            confidence=0.85,
            state="spin_situation",
            phase="situation",
            last_action="ask_priority",
            last_bot_message="Что для вас приоритетнее — скорость или функционал?",
            metadata={}
        )

    # =========================================================================
    # Layer Configuration Tests
    # =========================================================================

    def test_layer_name(self, layer):
        """Layer has correct name."""
        assert layer.name == "option_selection"

    def test_layer_priority(self, layer):
        """Layer has HIGH priority."""
        assert layer.priority == LayerPriority.HIGH

    def test_layer_feature_flag(self, layer):
        """Layer has correct feature flag."""
        assert layer.FEATURE_FLAG == "option_selection_refinement"

    # =========================================================================
    # _should_apply() Tests
    # =========================================================================

    def test_should_apply_when_option_question_and_numeric_answer(
        self, layer, option_question_context
    ):
        """Should apply when bot asked option question and user replied "1"."""
        assert layer._should_apply(option_question_context) is True

    def test_should_apply_when_option_question_and_ordinal_answer(
        self, layer, option_question_context_ordinal
    ):
        """Should apply when bot asked option question and user replied "первое"."""
        assert layer._should_apply(option_question_context_ordinal) is True

    def test_should_not_apply_when_no_option_question(
        self, layer, no_option_context
    ):
        """Should NOT apply when bot did not ask option question."""
        assert layer._should_apply(no_option_context) is False

    def test_should_not_apply_when_message_not_selection(
        self, layer, non_selection_message_context
    ):
        """Should NOT apply when message is not a selection pattern."""
        assert layer._should_apply(non_selection_message_context) is False

    def test_should_not_apply_when_intent_not_suspicious(self, layer):
        """Should NOT apply when intent is not in suspicious list."""
        ctx = RefinementContext(
            message="1",
            intent="info_provided",  # Not suspicious
            confidence=0.9,
            last_bot_message="Что для вас приоритетнее — скорость или функционал?",
        )
        assert layer._should_apply(ctx) is False

    def test_should_not_apply_when_no_last_bot_message(self, layer):
        """Should NOT apply when last_bot_message is missing."""
        ctx = RefinementContext(
            message="1",
            intent="request_brevity",
            confidence=0.9,
            last_bot_message=None,
        )
        assert layer._should_apply(ctx) is False

    def test_should_not_apply_when_message_too_long(self, layer):
        """Should NOT apply when message is too long to be selection."""
        ctx = RefinementContext(
            message="ну давайте первый вариант попробуем",  # > 15 chars
            intent="request_brevity",
            confidence=0.9,
            last_bot_message="Что для вас приоритетнее — скорость или функционал?",
        )
        assert layer._should_apply(ctx) is False

    # =========================================================================
    # _is_selection_answer() Tests
    # =========================================================================

    def test_is_selection_answer_numeric_1(self, layer):
        """'1' is selection answer."""
        assert layer._is_selection_answer("1") is True

    def test_is_selection_answer_numeric_2(self, layer):
        """'2' is selection answer."""
        assert layer._is_selection_answer("2") is True

    def test_is_selection_answer_numeric_3(self, layer):
        """'3' is selection answer."""
        assert layer._is_selection_answer("3") is True

    def test_is_selection_answer_ordinal_first(self, layer):
        """'первое' is selection answer."""
        assert layer._is_selection_answer("первое") is True
        assert layer._is_selection_answer("первый") is True

    def test_is_selection_answer_ordinal_second(self, layer):
        """'второе' is selection answer."""
        assert layer._is_selection_answer("второе") is True
        assert layer._is_selection_answer("второй") is True

    def test_is_selection_answer_ordinal_third(self, layer):
        """'третье' is selection answer."""
        assert layer._is_selection_answer("третье") is True

    def test_is_selection_answer_text_number(self, layer):
        """'один', 'два', 'три' are selection answers."""
        assert layer._is_selection_answer("один") is True
        assert layer._is_selection_answer("два") is True
        assert layer._is_selection_answer("три") is True

    def test_is_not_selection_answer_regular_text(self, layer):
        """Regular text is not selection answer."""
        assert layer._is_selection_answer("да") is False
        assert layer._is_selection_answer("нет") is False
        assert layer._is_selection_answer("скорость") is False

    # =========================================================================
    # _is_option_question() Tests
    # =========================================================================

    def test_is_option_question_with_or(self, layer):
        """Question with 'или' is option question."""
        assert layer._is_option_question("Скорость или функционал?") is True
        assert layer._is_option_question(
            "Что для вас приоритетнее — скорость или функционал?"
        ) is True

    def test_is_option_question_priority(self, layer):
        """Priority question is option question."""
        assert layer._is_option_question("Что для вас важнее?") is True
        assert layer._is_option_question("Что приоритетнее для вашей команды?") is True

    def test_is_option_question_important(self, layer):
        """'Вам важнее' question is option question."""
        assert layer._is_option_question("Вам важнее скорость или качество?") is True

    def test_is_not_option_question_regular(self, layer):
        """Regular question is not option question."""
        assert layer._is_option_question("Сколько человек в команде?") is False
        assert layer._is_option_question("Какие инструменты используете?") is False

    # =========================================================================
    # _extract_option_index() Tests
    # =========================================================================

    def test_extract_option_index_numeric(self, layer):
        """Extract index from numeric answers."""
        assert layer._extract_option_index("1") == 0
        assert layer._extract_option_index("2") == 1
        assert layer._extract_option_index("3") == 2

    def test_extract_option_index_ordinal(self, layer):
        """Extract index from ordinal answers."""
        assert layer._extract_option_index("первое") == 0
        assert layer._extract_option_index("первый") == 0
        assert layer._extract_option_index("второе") == 1
        assert layer._extract_option_index("третье") == 2

    def test_extract_option_index_text_number(self, layer):
        """Extract index from text number answers."""
        assert layer._extract_option_index("один") == 0
        assert layer._extract_option_index("два") == 1
        assert layer._extract_option_index("три") == 2

    def test_extract_option_index_unknown(self, layer):
        """Return None for unknown patterns."""
        assert layer._extract_option_index("четыре") is None
        assert layer._extract_option_index("да") is None

    # =========================================================================
    # _extract_options_from_question() Tests
    # =========================================================================

    def test_extract_options_from_question(self, layer):
        """Extract options from 'X или Y?' pattern."""
        options = layer._extract_options_from_question("Скорость или функционал?")
        assert len(options) == 2
        assert "Скорость" in options
        assert "функционал" in options

    def test_extract_options_from_complex_question(self, layer):
        """Extract options from complex question."""
        options = layer._extract_options_from_question(
            "Что для вас приоритетнее — быстро запустить или глубоко настроить?"
        )
        assert len(options) == 2

    def test_extract_options_no_pattern(self, layer):
        """Return empty list when no pattern matches."""
        options = layer._extract_options_from_question("Сколько человек в команде?")
        assert options == []

    # =========================================================================
    # refine() / _do_refine() Tests
    # =========================================================================

    def test_refine_option_selection_to_info_provided(
        self, layer, option_question_context
    ):
        """Refine request_brevity → info_provided when option selection detected."""
        result = {"intent": "request_brevity", "confidence": 0.9}

        refined = layer.refine("1", result, option_question_context)

        assert refined.decision == RefinementDecision.REFINED
        assert refined.intent == "info_provided"
        assert refined.original_intent == "request_brevity"
        assert "option_selection" in refined.refinement_reason

    def test_refine_adds_secondary_signal(self, layer, option_question_context):
        """Refinement adds option_selection secondary signal."""
        result = {"intent": "request_brevity", "confidence": 0.9}

        refined = layer.refine("1", result, option_question_context)

        assert "option_selection" in refined.secondary_signals

    def test_refine_adds_metadata(self, layer, option_question_context):
        """Refinement adds metadata about option selection."""
        result = {"intent": "request_brevity", "confidence": 0.9}

        refined = layer.refine("1", result, option_question_context)

        assert "option_index" in refined.metadata
        assert refined.metadata["option_index"] == 0  # "1" → index 0

    def test_refine_confidence(self, layer, option_question_context):
        """Refined confidence is from config."""
        result = {"intent": "request_brevity", "confidence": 0.9}

        refined = layer.refine("1", result, option_question_context)

        # Default config confidence is 0.75
        assert refined.confidence == 0.75

    def test_no_refine_when_not_applicable(self, layer, no_option_context):
        """No refinement when conditions not met."""
        result = {"intent": "request_brevity", "confidence": 0.9}

        refined = layer.refine("1", result, no_option_context)

        assert refined.decision in [
            RefinementDecision.PASS_THROUGH,
            RefinementDecision.SKIPPED
        ]
        assert refined.intent == "request_brevity"

class TestOptionSelectionWithClientAgent:
    """Integration tests for OptionSelectionRefinementLayer with ClientAgent behavior."""

    @pytest.fixture
    def layer(self):
        """Create refinement layer instance."""
        return OptionSelectionRefinementLayer()

    def test_scenario_spin_priority_question(self, layer):
        """
        Scenario: SPIN priority question answered with "1".

        Bot: "Что для вас приоритетнее — скорость или функционал?"
        User: "1"
        Expected: info_provided (not request_brevity)
        """
        ctx = RefinementContext(
            message="1",
            intent="request_brevity",
            confidence=0.9,
            state="spin_situation",
            phase="situation",
            last_bot_message="Что для вас приоритетнее — скорость или функционал?",
        )
        result = {"intent": "request_brevity", "confidence": 0.9}

        refined = layer.refine("1", result, ctx)

        assert refined.intent == "info_provided"
        assert "option_selection" in refined.secondary_signals

    def test_scenario_challenger_question(self, layer):
        """
        Scenario: Challenger question answered with "первое".

        Bot: "Понял. Что сейчас для вас приоритетнее — быстро запустить или глубоко настроить?"
        User: "первое"
        Expected: info_provided (not request_brevity)
        """
        ctx = RefinementContext(
            message="первое",
            intent="request_brevity",
            confidence=0.85,
            state="challenger",
            phase="align",
            last_bot_message="Понял. Что сейчас для вас приоритетнее — быстро запустить или глубоко настроить?",
        )
        result = {"intent": "request_brevity", "confidence": 0.85}

        refined = layer.refine("первое", result, ctx)

        assert refined.intent == "info_provided"
        assert refined.metadata["option_index"] == 0

    def test_scenario_snap_question(self, layer):
        """
        Scenario: SNAP question answered with "2".

        Bot: "Понял. Что для вас важнее — скорость, контроль или снижение ошибок?"
        User: "2"
        Expected: info_provided (not request_brevity)
        """
        ctx = RefinementContext(
            message="2",
            intent="greeting",  # Another misclassification
            confidence=0.8,
            state="snap",
            phase="align",
            last_bot_message="Понял. Что для вас важнее — скорость, контроль или снижение ошибок?",
        )
        result = {"intent": "greeting", "confidence": 0.8}

        refined = layer.refine("2", result, ctx)

        assert refined.intent == "info_provided"
        assert refined.metadata["option_index"] == 1

    def test_scenario_not_option_question(self, layer):
        """
        Scenario: Regular question (not option), "1" should stay as-is.

        Bot: "Сколько человек в команде?"
        User: "1"
        Expected: request_brevity unchanged (layer should not apply)
        """
        ctx = RefinementContext(
            message="1",
            intent="request_brevity",
            confidence=0.9,
            state="spin_situation",
            phase="situation",
            last_bot_message="Сколько человек в команде?",
        )
        result = {"intent": "request_brevity", "confidence": 0.9}

        refined = layer.refine("1", result, ctx)

        # Should NOT refine - this is not an option question
        assert refined.intent == "request_brevity"

class TestShortAnswerRefinementWithRequestBrevity:
    """
    Tests that ShortAnswerRefinementLayer now handles request_brevity.

    FIX: request_brevity was added to LOW_SIGNAL_INTENTS.
    """

    def test_request_brevity_in_low_signal_intents(self):
        """request_brevity should be in LOW_SIGNAL_INTENTS."""
        from src.classifier.refinement_layers import ShortAnswerRefinementLayer

        layer = ShortAnswerRefinementLayer()
        assert "request_brevity" in layer.LOW_SIGNAL_INTENTS

    def test_should_apply_to_request_brevity(self):
        """ShortAnswerRefinementLayer should apply to request_brevity."""
        from src.classifier.refinement_layers import ShortAnswerRefinementLayer

        layer = ShortAnswerRefinementLayer()
        ctx = RefinementContext(
            message="1",
            intent="request_brevity",
            confidence=0.9,
            state="greeting",
            phase="situation",
            last_action="ask_about_company",
        )

        # Should apply because:
        # 1. Message is short (✓)
        # 2. Intent is in LOW_SIGNAL_INTENTS (✓ after fix)
        # 3. Has phase context (✓)
        assert layer._should_apply(ctx) is True
