"""
E2E integration tests for Style/Semantic Separation.

Tests the full pipeline: classification → routing → style application.

Feature flag: separate_style_modifiers
"""

import pytest
from unittest.mock import MagicMock, patch

from src.feature_flags import flags
from src.classifier.refinement_pipeline import (
    RefinementContext,
    RefinementDecision,
)
from src.classifier.style_modifier_detection import StyleModifierDetectionLayer
from src.personalization.result import PersonalizationResult, StyleParameters


class TestStyleSeparationE2E:
    """E2E tests for style/semantic separation."""

    @pytest.fixture(autouse=True)
    def setup_flag(self):
        """Enable the feature flag for tests."""
        flags.set_override("separate_style_modifiers", True)
        yield
        flags.clear_override("separate_style_modifiers")

    @pytest.fixture
    def layer(self):
        return StyleModifierDetectionLayer()

    # =========================================================================
    # E2E: Classification → Style Modifier Metadata
    # =========================================================================

    def test_e2e_brevity_with_action_context(self, layer):
        """E2E: '5 человек, быстрее' + ask_about_company → info_provided + brevity."""
        ctx = RefinementContext(
            message="5 человек, быстрее",
            intent="request_brevity",
            confidence=0.85,
            last_action="ask_about_company",
            extracted_data={"company_size": 5},
        )
        result_dict = {
            "intent": "request_brevity",
            "confidence": 0.85,
            "alternatives": [],
            "extracted_data": {"company_size": 5},
        }
        layer_result = layer.refine("5 человек, быстрее", result_dict, ctx)

        assert layer_result.intent == "info_provided"
        assert layer_result.metadata.get("style_modifiers") == ["request_brevity"]
        assert layer_result.metadata.get("style_separation_applied") is True

    def test_e2e_brevity_with_question_alternative(self, layer):
        """E2E: brevity with question_pricing alternative → question_pricing + brevity."""
        ctx = RefinementContext(
            message="быстрее, сколько стоит?",
            intent="request_brevity",
            confidence=0.7,
        )
        result_dict = {
            "intent": "request_brevity",
            "confidence": 0.7,
            "alternatives": [{"intent": "question_pricing", "confidence": 0.6}],
        }
        layer_result = layer.refine("быстрее, сколько стоит?", result_dict, ctx)

        assert layer_result.intent == "question_pricing"
        assert "request_brevity" in layer_result.metadata.get("style_modifiers", [])

    # =========================================================================
    # Context Propagation
    # =========================================================================

    def test_context_propagation_style_modifiers(self, layer):
        """Style modifiers should be accessible via to_dict() for propagation."""
        ctx = RefinementContext(
            message="быстрее",
            intent="request_brevity",
            confidence=0.8,
            last_action="ask_about_company",
        )
        result_dict = {"intent": "request_brevity", "confidence": 0.8, "alternatives": []}
        layer_result = layer.refine("быстрее", result_dict, ctx)

        result_dict_out = layer_result.to_dict()
        # Style modifiers are in refinement_metadata
        meta = result_dict_out.get("refinement_metadata", {})
        assert "style_modifiers" in meta
        assert meta["style_modifiers"] == ["request_brevity"]
        assert meta["style_separation_applied"] is True

    # =========================================================================
    # _apply_style_modifiers Integration
    # =========================================================================

    def test_apply_style_modifiers_brevity(self):
        """_apply_style_modifiers applies brevity to PersonalizationResult."""
        from src.generator import ResponseGenerator

        # Create minimal generator (no LLM needed for this test)
        gen = ResponseGenerator.__new__(ResponseGenerator)
        gen._style_intents_cache = None

        p_result = PersonalizationResult()
        context = {"style_modifiers": ["request_brevity"]}

        result = gen._apply_style_modifiers(context, p_result)
        assert result.style.verbosity == "concise"
        assert "brevity" in result.style.applied_modifiers
        assert "Будь краток" in result.style.tactical_instruction

    def test_apply_style_modifiers_examples(self):
        """_apply_style_modifiers applies examples modifier."""
        from src.generator import ResponseGenerator

        gen = ResponseGenerator.__new__(ResponseGenerator)
        gen._style_intents_cache = None

        p_result = PersonalizationResult()
        context = {"style_modifiers": ["request_examples"]}

        result = gen._apply_style_modifiers(context, p_result)
        assert result.style.verbosity == "detailed"
        assert "examples" in result.style.applied_modifiers

    def test_apply_style_modifiers_summary(self):
        """_apply_style_modifiers applies summary modifier."""
        from src.generator import ResponseGenerator

        gen = ResponseGenerator.__new__(ResponseGenerator)
        gen._style_intents_cache = None

        p_result = PersonalizationResult()
        context = {"style_modifiers": ["request_summary"]}

        result = gen._apply_style_modifiers(context, p_result)
        assert "summary" in result.style.applied_modifiers
        assert "Суммируй" in result.style.tactical_instruction

    def test_apply_style_modifiers_brevity_wins_over_examples(self):
        """When brevity + examples conflict, brevity wins."""
        from src.generator import ResponseGenerator

        gen = ResponseGenerator.__new__(ResponseGenerator)
        gen._style_intents_cache = None

        p_result = PersonalizationResult()
        context = {"style_modifiers": ["request_brevity", "request_examples"]}

        result = gen._apply_style_modifiers(context, p_result)
        assert result.style.verbosity == "concise"
        assert "brevity" in result.style.applied_modifiers
        # examples should be removed by brevity priority
        assert "examples" not in result.style.applied_modifiers

    def test_apply_style_modifiers_from_secondary_signals(self):
        """Style from secondary_signals should also be applied."""
        from src.generator import ResponseGenerator

        gen = ResponseGenerator.__new__(ResponseGenerator)
        gen._style_intents_cache = {"request_brevity"}

        p_result = PersonalizationResult()
        context = {
            "style_modifiers": [],
            "secondary_signals": ["request_brevity"],
        }

        result = gen._apply_style_modifiers(context, p_result)
        assert result.style.verbosity == "concise"
        assert result.style.modifier_source == "secondary"

    def test_apply_style_modifiers_mixed_sources(self):
        """Merging style_modifiers + secondary_signals from style intents."""
        from src.generator import ResponseGenerator

        gen = ResponseGenerator.__new__(ResponseGenerator)
        gen._style_intents_cache = {"request_brevity", "summary_request"}

        p_result = PersonalizationResult()
        context = {
            "style_modifiers": ["request_brevity"],
            "secondary_signals": ["summary_request"],
        }

        result = gen._apply_style_modifiers(context, p_result)
        assert result.style.modifier_source == "mixed"
        assert "brevity" in result.style.applied_modifiers
        assert "summary" in result.style.applied_modifiers

    def test_apply_style_modifiers_no_modifiers_noop(self):
        """No style modifiers → PersonalizationResult unchanged."""
        from src.generator import ResponseGenerator

        gen = ResponseGenerator.__new__(ResponseGenerator)
        gen._style_intents_cache = None

        p_result = PersonalizationResult()
        context = {"style_modifiers": []}

        result = gen._apply_style_modifiers(context, p_result)
        assert result.style.verbosity == "normal"
        assert result.style.applied_modifiers == []

    def test_apply_style_modifiers_flag_off_noop(self):
        """With flag OFF, _apply_style_modifiers should be a no-op."""
        flags.set_override("separate_style_modifiers", False)
        from src.generator import ResponseGenerator

        gen = ResponseGenerator.__new__(ResponseGenerator)
        gen._style_intents_cache = None

        p_result = PersonalizationResult()
        context = {"style_modifiers": ["request_brevity"]}

        result = gen._apply_style_modifiers(context, p_result)
        assert result.style.verbosity == "normal"  # Unchanged

    # =========================================================================
    # PersonalizationResult: to_prompt_variables
    # =========================================================================

    def test_personalization_result_includes_applied_modifiers(self):
        """to_prompt_variables includes applied_style_modifiers."""
        p = PersonalizationResult()
        p.style.applied_modifiers = ["brevity", "summary"]

        variables = p.to_prompt_variables()
        assert variables.get("applied_style_modifiers") == "brevity, summary"

    def test_personalization_result_no_modifiers_no_key(self):
        """to_prompt_variables omits applied_style_modifiers when empty."""
        p = PersonalizationResult()
        variables = p.to_prompt_variables()
        assert "applied_style_modifiers" not in variables

    # =========================================================================
    # RefinementResult to_dict: refinement_metadata propagation
    # =========================================================================

    def test_refinement_result_to_dict_has_metadata(self, layer):
        """to_dict() includes refinement_metadata with style fields."""
        ctx = RefinementContext(
            message="быстрее",
            intent="request_brevity",
            confidence=0.8,
            last_action="ask_about_company",
        )
        result_dict = {"intent": "request_brevity", "confidence": 0.8, "alternatives": []}
        layer_result = layer.refine("быстрее", result_dict, ctx)

        out = layer_result.to_dict()
        assert out["intent"] == "info_provided"
        assert out["refined"] is True
        assert out["refinement_metadata"]["style_modifiers"] == ["request_brevity"]
        assert out["refinement_metadata"]["skip_secondary_detection"] == ["request_brevity"]
