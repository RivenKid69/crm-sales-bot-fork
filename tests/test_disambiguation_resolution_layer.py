# tests/test_disambiguation_resolution_layer.py

"""
Unit tests for DisambiguationResolutionLayer.

Covers:
- Path A: Critical intent override (contact_provided, rejection, demo_request)
- Path B: Option selection (1, 2, first, second, keyword match)
- Path C: Custom input / unrecognized answer
- Not in disambiguation: layer skips
- Metadata signals (exit_disambiguation, resolved_intent)
"""

import pytest
from typing import Dict, Any

from src.classifier.refinement_pipeline import (
    RefinementContext,
    RefinementResult,
    RefinementDecision,
    LayerPriority,
)
from src.classifier.disambiguation_resolution_layer import DisambiguationResolutionLayer

# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def layer():
    return DisambiguationResolutionLayer()

@pytest.fixture
def sample_options():
    return [
        {"intent": "price_question", "label": "Узнать цены"},
        {"intent": "demo_request", "label": "Записаться на демо"},
        {"intent": "feature_question", "label": "Узнать о функциях"},
    ]

def make_ctx(
    in_disambiguation: bool = False,
    options: list = None,
    intent: str = "unclear",
    message: str = "test",
) -> RefinementContext:
    return RefinementContext(
        message=message,
        state="spin_situation",
        in_disambiguation=in_disambiguation,
        disambiguation_options=options or [],
        intent=intent,
        confidence=0.5,
        metadata={},
    )

def make_result(intent: str = "unclear", confidence: float = 0.5) -> Dict[str, Any]:
    return {
        "intent": intent,
        "confidence": confidence,
        "extracted_data": {},
    }

# =============================================================================
# Test: Layer metadata
# =============================================================================

class TestLayerMetadata:

    def test_layer_name(self, layer):
        assert layer.name == "disambiguation_resolution"

    def test_layer_priority_is_critical(self, layer):
        assert layer.priority == LayerPriority.CRITICAL

    def test_feature_flag(self, layer):
        assert layer.FEATURE_FLAG == "unified_disambiguation"

# =============================================================================
# Test: _should_apply
# =============================================================================

class TestShouldApply:

    def test_applies_when_in_disambiguation(self, layer):
        ctx = make_ctx(in_disambiguation=True)
        assert layer._should_apply(ctx) is True

    def test_skips_when_not_in_disambiguation(self, layer):
        ctx = make_ctx(in_disambiguation=False)
        assert layer._should_apply(ctx) is False

# =============================================================================
# Test: Path A — Critical intent override
# =============================================================================

class TestPathACriticalIntents:

    @pytest.mark.parametrize("critical_intent", [
        "contact_provided",
        "rejection",
        "demo_request",
    ])
    def test_critical_intent_passes_through(self, layer, critical_intent, sample_options):
        ctx = make_ctx(
            in_disambiguation=True,
            options=sample_options,
            intent=critical_intent,
            message="хочу связаться с менеджером",
        )
        result = make_result(intent=critical_intent, confidence=0.85)

        refinement = layer._do_refine("хочу связаться с менеджером", result, ctx)

        assert refinement.decision == RefinementDecision.PASS_THROUGH
        assert refinement.intent == critical_intent
        assert ctx.metadata.get("exit_disambiguation") is True

    def test_critical_intent_does_not_refine(self, layer, sample_options):
        ctx = make_ctx(
            in_disambiguation=True,
            options=sample_options,
            intent="contact_provided",
        )
        result = make_result(intent="contact_provided", confidence=0.9)

        refinement = layer._do_refine("вот мой номер 89001234567", result, ctx)

        assert refinement.decision != RefinementDecision.REFINED

# =============================================================================
# Test: Path B — Option selection
# =============================================================================

class TestPathBOptionSelection:

    def test_numeric_selection_1(self, layer, sample_options):
        ctx = make_ctx(
            in_disambiguation=True,
            options=sample_options,
            intent="unclear",
            message="1",
        )
        result = make_result(intent="unclear")

        refinement = layer._do_refine("1", result, ctx)

        assert refinement.decision == RefinementDecision.REFINED
        assert refinement.intent == "price_question"
        assert refinement.confidence == 0.9
        assert ctx.metadata["exit_disambiguation"] is True
        assert ctx.metadata["disambiguation_resolved_intent"] == "price_question"

    def test_numeric_selection_2(self, layer, sample_options):
        ctx = make_ctx(
            in_disambiguation=True,
            options=sample_options,
            intent="unclear",
            message="2",
        )
        result = make_result(intent="unclear")

        refinement = layer._do_refine("2", result, ctx)

        assert refinement.decision == RefinementDecision.REFINED
        assert refinement.intent == "demo_request"

    def test_word_selection_first(self, layer, sample_options):
        ctx = make_ctx(
            in_disambiguation=True,
            options=sample_options,
            intent="unclear",
            message="первое",
        )
        result = make_result(intent="unclear")

        refinement = layer._do_refine("первое", result, ctx)

        assert refinement.decision == RefinementDecision.REFINED
        assert refinement.intent == "price_question"

    def test_word_selection_second(self, layer, sample_options):
        ctx = make_ctx(
            in_disambiguation=True,
            options=sample_options,
            intent="unclear",
            message="второе",
        )
        result = make_result(intent="unclear")

        refinement = layer._do_refine("второе", result, ctx)

        assert refinement.decision == RefinementDecision.REFINED
        assert refinement.intent == "demo_request"

    def test_refined_result_has_correct_metadata(self, layer, sample_options):
        ctx = make_ctx(
            in_disambiguation=True,
            options=sample_options,
            intent="unclear",
            message="1",
        )
        result = make_result(intent="unclear")

        refinement = layer._do_refine("1", result, ctx)

        assert refinement.metadata["method"] == "disambiguation_resolved"
        assert refinement.metadata["selected_option"] == "price_question"
        assert refinement.original_intent == "unclear"
        assert refinement.refinement_reason == "disambiguation_resolved"

# =============================================================================
# Test: Path C — Custom input / unrecognized
# =============================================================================

class TestPathCCustomInput:

    def test_custom_text_passes_llm_classification(self, layer, sample_options):
        # Use a message that doesn't match any option keyword (avoids Path B match)
        ctx = make_ctx(
            in_disambiguation=True,
            options=sample_options,
            intent="info_provided",
            message="у нас работает 100 человек в офисе",
        )
        result = make_result(intent="info_provided", confidence=0.8)

        refinement = layer._do_refine("у нас работает 100 человек в офисе", result, ctx)

        assert refinement.decision == RefinementDecision.PASS_THROUGH
        assert refinement.intent == "info_provided"
        assert ctx.metadata["exit_disambiguation"] is True

    def test_unrecognized_input_passes_llm_classification(self, layer, sample_options):
        ctx = make_ctx(
            in_disambiguation=True,
            options=sample_options,
            intent="info_provided",
            message="у нас 50 сотрудников",
        )
        result = make_result(intent="info_provided", confidence=0.7)

        refinement = layer._do_refine("у нас 50 сотрудников", result, ctx)

        assert refinement.decision == RefinementDecision.PASS_THROUGH
        assert refinement.intent == "info_provided"
        assert ctx.metadata["exit_disambiguation"] is True

    def test_custom_input_with_no_options(self, layer):
        ctx = make_ctx(
            in_disambiguation=True,
            options=[],
            intent="greeting",
            message="привет",
        )
        result = make_result(intent="greeting", confidence=0.9)

        refinement = layer._do_refine("привет", result, ctx)

        # With no options, goes to Path C (custom input)
        assert refinement.decision == RefinementDecision.PASS_THROUGH
        assert ctx.metadata["exit_disambiguation"] is True

# =============================================================================
# Test: Edge cases
# =============================================================================

class TestEdgeCases:

    def test_critical_intent_takes_priority_over_option_match(self, layer):
        """If LLM says contact_provided, don't try to parse as option."""
        options = [
            {"intent": "price_question", "label": "Цены"},
            {"intent": "feature_question", "label": "Функции"},
        ]
        ctx = make_ctx(
            in_disambiguation=True,
            options=options,
            intent="contact_provided",
            message="1",  # Could be parsed as option 1
        )
        result = make_result(intent="contact_provided", confidence=0.9)

        refinement = layer._do_refine("1", result, ctx)

        # Path A (critical) wins over Path B (option)
        assert refinement.decision == RefinementDecision.PASS_THROUGH
        assert refinement.intent == "contact_provided"

    def test_all_paths_set_exit_disambiguation(self, layer, sample_options):
        """Every path must set exit_disambiguation=True."""
        # Path A
        ctx_a = make_ctx(in_disambiguation=True, options=sample_options, intent="rejection")
        layer._do_refine("не хочу", make_result(intent="rejection"), ctx_a)
        assert ctx_a.metadata["exit_disambiguation"] is True

        # Path B
        ctx_b = make_ctx(in_disambiguation=True, options=sample_options, intent="unclear", message="1")
        layer._do_refine("1", make_result(intent="unclear"), ctx_b)
        assert ctx_b.metadata["exit_disambiguation"] is True

        # Path C
        ctx_c = make_ctx(in_disambiguation=True, options=sample_options, intent="greeting", message="привет")
        layer._do_refine("привет", make_result(intent="greeting"), ctx_c)
        assert ctx_c.metadata["exit_disambiguation"] is True

    def test_all_paths_return_refinement_result(self, layer, sample_options):
        """Every path returns a RefinementResult, never None."""
        messages = [
            ("rejection", "не хочу"),
            ("unclear", "1"),
            ("greeting", "привет"),
        ]
        for intent, msg in messages:
            ctx = make_ctx(in_disambiguation=True, options=sample_options, intent=intent, message=msg)
            result = layer._do_refine(msg, make_result(intent=intent), ctx)
            assert isinstance(result, RefinementResult), f"Path for {intent} returned {type(result)}"
