"""
Unit tests for StyleModifierDetectionLayer.

Tests the Style/Semantic Separation feature: when primary intent is a style intent
(request_brevity, example_request, summary_request), the layer infers the true
semantic intent and moves the style signal to metadata.

Feature flag: separate_style_modifiers
SSoT: src/classifier/style_modifier_detection.py
"""

import pytest
from typing import Dict, Any

from src.classifier.style_modifier_detection import StyleModifierDetectionLayer
from src.classifier.refinement_pipeline import (
    RefinementContext,
    RefinementDecision,
    LayerPriority,
)
from src.feature_flags import flags


class TestStyleModifierDetectionLayer:
    """Tests for StyleModifierDetectionLayer."""

    @pytest.fixture(autouse=True)
    def setup_flag(self):
        """Enable the feature flag for tests, restore after."""
        flags.set_override("separate_style_modifiers", True)
        yield
        flags.clear_override("separate_style_modifiers")

    @pytest.fixture
    def layer(self):
        """Create layer instance."""
        return StyleModifierDetectionLayer()

    # =========================================================================
    # Priority and Registration
    # =========================================================================

    def test_layer_priority_is_highest(self, layer):
        """Layer must run before all other layers."""
        assert layer.priority == LayerPriority.HIGHEST
        assert layer.priority.value == 110

    def test_layer_name(self, layer):
        """Layer has correct name."""
        assert layer.name == "style_modifier_detection"

    def test_feature_flag_none(self, layer):
        """FEATURE_FLAG is None (dynamic check in _should_apply)."""
        assert layer.FEATURE_FLAG is None

    # =========================================================================
    # _should_apply: Flag gating
    # =========================================================================

    def test_should_apply_flag_off(self, layer):
        """When flag OFF, layer should not apply."""
        flags.set_override("separate_style_modifiers", False)
        ctx = RefinementContext(
            message="быстрее",
            intent="request_brevity",
            confidence=0.85,
        )
        assert not layer._should_apply(ctx)

    def test_should_apply_flag_on_style_intent(self, layer):
        """When flag ON and intent is style, layer should apply."""
        ctx = RefinementContext(
            message="быстрее",
            intent="request_brevity",
            confidence=0.85,
        )
        assert layer._should_apply(ctx)

    def test_should_apply_non_style_intent(self, layer):
        """Non-style intents should not trigger the layer."""
        ctx = RefinementContext(
            message="50 человек",
            intent="info_provided",
            confidence=0.9,
        )
        assert not layer._should_apply(ctx)

    def test_should_apply_question_pricing_skipped(self, layer):
        """question_pricing is not a style intent, should not apply."""
        ctx = RefinementContext(
            message="сколько стоит?",
            intent="question_pricing",
            confidence=0.9,
        )
        assert not layer._should_apply(ctx)

    # =========================================================================
    # Semantic Inference: Strategy 1 (Action-based)
    # =========================================================================

    def test_action_based_inference_ask_about_company(self, layer):
        """last_action=ask_about_company → info_provided."""
        ctx = RefinementContext(
            message="5 человек, быстрее",
            intent="request_brevity",
            confidence=0.8,
            last_action="ask_about_company",
        )
        result_dict = {"alternatives": [], "extracted_data": {"company_size": 5}}
        layer_result = layer._do_refine("5 человек, быстрее", result_dict, ctx)

        assert layer_result.decision == RefinementDecision.REFINED
        assert layer_result.intent == "info_provided"
        assert layer_result.original_intent == "request_brevity"
        assert layer_result.refinement_reason == "style_intent_separated"

    def test_action_based_inference_ask_problem(self, layer):
        """last_action=ask_problem → info_provided."""
        ctx = RefinementContext(
            message="быстрее",
            intent="request_brevity",
            confidence=0.8,
            last_action="ask_problem",
        )
        result = layer._do_refine("быстрее", {"alternatives": []}, ctx)
        assert result.intent == "info_provided"

    def test_action_based_inference_continue_current_goal(self, layer):
        """last_action=continue_current_goal → info_provided."""
        ctx = RefinementContext(
            message="кратко",
            intent="request_brevity",
            confidence=0.85,
            last_action="continue_current_goal",
        )
        result = layer._do_refine("кратко", {"alternatives": []}, ctx)
        assert result.intent == "info_provided"

    # =========================================================================
    # Semantic Inference: Strategy 2 (Alternatives-based)
    # =========================================================================

    def test_alternatives_based_question_intent(self, layer):
        """Prefer question_* intent from alternatives."""
        ctx = RefinementContext(
            message="быстрее, сколько стоит?",
            intent="request_brevity",
            confidence=0.75,
        )
        result_dict = {
            "alternatives": [
                {"intent": "question_pricing", "confidence": 0.6},
            ],
        }
        result = layer._do_refine("быстрее, сколько стоит?", result_dict, ctx)
        assert result.intent == "question_pricing"

    def test_alternatives_based_price_intent(self, layer):
        """Prefer price_* intent from alternatives."""
        ctx = RefinementContext(
            message="кратко, цена?",
            intent="request_brevity",
            confidence=0.75,
        )
        result_dict = {
            "alternatives": [
                {"intent": "price_question", "confidence": 0.5},
            ],
        }
        result = layer._do_refine("кратко, цена?", result_dict, ctx)
        assert result.intent == "price_question"

    def test_alternatives_none_safe(self, layer):
        """alternatives=None should be handled safely."""
        ctx = RefinementContext(
            message="быстрее",
            intent="request_brevity",
            confidence=0.8,
        )
        # No alternatives key at all
        result = layer._do_refine("быстрее", {}, ctx)
        # Should fallback to "unclear" (no action, no alternatives, no data, no phase)
        assert result.intent == "unclear"

    def test_alternatives_invalid_format_safe(self, layer):
        """alternatives with invalid format should be handled safely."""
        ctx = RefinementContext(
            message="быстрее",
            intent="request_brevity",
            confidence=0.8,
        )
        result_dict = {"alternatives": ["not_a_dict", None, 42]}
        result = layer._do_refine("быстрее", result_dict, ctx)
        assert result.intent == "unclear"

    # =========================================================================
    # Semantic Inference: Strategy 3 (Data-based)
    # =========================================================================

    def test_data_based_inference(self, layer):
        """Extracted data present → info_provided."""
        ctx = RefinementContext(
            message="5 человек, быстрее",
            intent="request_brevity",
            confidence=0.8,
            extracted_data={"company_size": 5},
        )
        result = layer._do_refine("5 человек, быстрее", {"alternatives": []}, ctx)
        assert result.intent == "info_provided"

    # =========================================================================
    # Semantic Inference: Strategy 4 (Phase-based)
    # =========================================================================

    def test_phase_based_situation(self, layer):
        """phase=situation → info_provided."""
        ctx = RefinementContext(
            message="быстрее",
            intent="request_brevity",
            confidence=0.8,
            phase="situation",
        )
        result = layer._do_refine("быстрее", {"alternatives": []}, ctx)
        assert result.intent == "info_provided"

    def test_phase_based_problem(self, layer):
        """phase=problem → problem_revealed."""
        ctx = RefinementContext(
            message="быстрее",
            intent="request_brevity",
            confidence=0.8,
            phase="problem",
        )
        result = layer._do_refine("быстрее", {"alternatives": []}, ctx)
        assert result.intent == "problem_revealed"

    def test_phase_based_implication(self, layer):
        """phase=implication → need_expressed."""
        ctx = RefinementContext(
            message="быстрее",
            intent="request_brevity",
            confidence=0.8,
            phase="implication",
        )
        result = layer._do_refine("быстрее", {"alternatives": []}, ctx)
        assert result.intent == "need_expressed"

    # =========================================================================
    # Semantic Inference: Strategy 5 (Expects-based)
    # =========================================================================

    def test_expects_data_type_inference(self, layer):
        """expects_data_type set → info_provided."""
        ctx = RefinementContext(
            message="быстрее",
            intent="request_brevity",
            confidence=0.8,
            expects_data_type="company_size",
        )
        result = layer._do_refine("быстрее", {"alternatives": []}, ctx)
        assert result.intent == "info_provided"

    # =========================================================================
    # Semantic Inference: Strategy 6 (Fallback)
    # =========================================================================

    def test_fallback_to_unclear(self, layer):
        """No context → fallback to 'unclear'."""
        ctx = RefinementContext(
            message="быстрее",
            intent="request_brevity",
            confidence=0.8,
        )
        result = layer._do_refine("быстрее", {"alternatives": []}, ctx)
        assert result.intent == "unclear"

    # =========================================================================
    # Safety: Inference must not return style intent
    # =========================================================================

    def test_inference_safety_prevents_style_intent_return(self, layer):
        """If inference returns a style intent, fallback to 'unclear'."""
        # Force alternatives to contain only style intents
        ctx = RefinementContext(
            message="быстрее",
            intent="request_brevity",
            confidence=0.8,
        )
        result_dict = {
            "alternatives": [
                {"intent": "example_request", "confidence": 0.6},
            ],
        }
        # example_request is a style intent, so inference should NOT return it
        # It should fall through to next strategy or fallback
        result = layer._do_refine("быстрее", result_dict, ctx)
        # Since example_request doesn't start with question_ or price_,
        # Strategy 2 skips it. Fallback should be "unclear".
        assert result.intent == "unclear"

    # =========================================================================
    # Style Modifier Metadata
    # =========================================================================

    def test_style_modifier_in_metadata(self, layer):
        """Style modifier should be in metadata."""
        ctx = RefinementContext(
            message="быстрее",
            intent="request_brevity",
            confidence=0.8,
            last_action="ask_about_company",
        )
        result = layer._do_refine("быстрее", {"alternatives": []}, ctx)
        assert "style_modifiers" in result.metadata
        assert "request_brevity" in result.metadata["style_modifiers"]
        assert result.metadata["style_separation_applied"] is True

    def test_skip_secondary_detection_in_metadata(self, layer):
        """skip_secondary_detection should include the original style intent."""
        ctx = RefinementContext(
            message="быстрее",
            intent="request_brevity",
            confidence=0.8,
            last_action="ask_about_company",
        )
        result = layer._do_refine("быстрее", {"alternatives": []}, ctx)
        assert "skip_secondary_detection" in result.metadata
        assert "request_brevity" in result.metadata["skip_secondary_detection"]

    def test_original_intent_in_metadata(self, layer):
        """Original intent should be preserved in metadata."""
        ctx = RefinementContext(
            message="быстрее",
            intent="request_brevity",
            confidence=0.8,
            last_action="ask_about_company",
        )
        result = layer._do_refine("быстрее", {"alternatives": []}, ctx)
        assert result.metadata["original_intent"] == "request_brevity"
        assert result.original_intent == "request_brevity"

    # =========================================================================
    # Intent-to-Modifier Mapping
    # =========================================================================

    def test_intent_to_modifier_mapping_brevity(self, layer):
        """request_brevity maps to request_brevity modifier."""
        assert layer._map_intent_to_modifier("request_brevity") == "request_brevity"

    def test_intent_to_modifier_mapping_example(self, layer):
        """example_request maps to request_examples modifier."""
        assert layer._map_intent_to_modifier("example_request") == "request_examples"

    def test_intent_to_modifier_mapping_summary(self, layer):
        """summary_request maps to request_summary modifier."""
        assert layer._map_intent_to_modifier("summary_request") == "request_summary"

    def test_intent_to_modifier_mapping_unknown(self, layer):
        """Unknown intent maps to itself (fallback)."""
        assert layer._map_intent_to_modifier("unknown_style") == "unknown_style"

    # =========================================================================
    # Confidence Handling
    # =========================================================================

    def test_confidence_preserved_when_above_threshold(self, layer):
        """Original confidence preserved when > 0.5."""
        ctx = RefinementContext(
            message="быстрее",
            intent="request_brevity",
            confidence=0.85,
            last_action="ask_about_company",
        )
        result = layer._do_refine("быстрее", {"alternatives": []}, ctx)
        assert result.confidence == 0.85

    def test_confidence_boosted_when_below_threshold(self, layer):
        """Confidence boosted to 0.75 when <= 0.5."""
        ctx = RefinementContext(
            message="быстрее",
            intent="request_brevity",
            confidence=0.3,
            last_action="ask_about_company",
        )
        result = layer._do_refine("быстрее", {"alternatives": []}, ctx)
        assert result.confidence == 0.75

    # =========================================================================
    # Config Validation
    # =========================================================================

    def test_style_intents_loaded_from_config(self, layer):
        """Style intents should be loaded from config."""
        assert "request_brevity" in layer._style_intents
        assert "example_request" in layer._style_intents
        assert "summary_request" in layer._style_intents

    # =========================================================================
    # Full Pipeline: refine() Method
    # =========================================================================

    def test_full_refine_with_flag_on(self, layer):
        """Full refine() call with flag ON should produce refined result."""
        ctx = RefinementContext(
            message="5 человек, быстрее",
            intent="request_brevity",
            confidence=0.8,
            last_action="ask_about_company",
        )
        result_dict = {"intent": "request_brevity", "confidence": 0.8, "alternatives": []}
        layer_result = layer.refine("5 человек, быстрее", result_dict, ctx)

        assert layer_result.decision == RefinementDecision.REFINED
        assert layer_result.intent == "info_provided"
        assert layer_result.layer_name == "style_modifier_detection"

    def test_full_refine_with_flag_off(self, layer):
        """Full refine() call with flag OFF should pass through."""
        flags.set_override("separate_style_modifiers", False)
        ctx = RefinementContext(
            message="быстрее",
            intent="request_brevity",
            confidence=0.8,
            last_action="ask_about_company",
        )
        result_dict = {"intent": "request_brevity", "confidence": 0.8}
        layer_result = layer.refine("быстрее", result_dict, ctx)

        assert layer_result.decision == RefinementDecision.PASS_THROUGH
        assert layer_result.intent == "request_brevity"

    def test_full_refine_non_style_intent_pass_through(self, layer):
        """Non-style intent should pass through."""
        ctx = RefinementContext(
            message="50 человек",
            intent="info_provided",
            confidence=0.9,
        )
        result_dict = {"intent": "info_provided", "confidence": 0.9}
        layer_result = layer.refine("50 человек", result_dict, ctx)

        assert layer_result.decision == RefinementDecision.PASS_THROUGH

    # =========================================================================
    # example_request and summary_request
    # =========================================================================

    def test_example_request_separated(self, layer):
        """example_request should be separated like request_brevity."""
        ctx = RefinementContext(
            message="покажи примеры",
            intent="example_request",
            confidence=0.8,
            last_action="ask_about_problem",
        )
        result = layer._do_refine("покажи примеры", {"alternatives": []}, ctx)
        assert result.intent == "info_provided"
        assert "request_examples" in result.metadata["style_modifiers"]

    def test_summary_request_separated(self, layer):
        """summary_request should be separated like request_brevity."""
        ctx = RefinementContext(
            message="суммируй",
            intent="summary_request",
            confidence=0.8,
            phase="need_payoff",
        )
        result = layer._do_refine("суммируй", {"alternatives": []}, ctx)
        assert result.intent == "need_expressed"
        assert "request_summary" in result.metadata["style_modifiers"]
