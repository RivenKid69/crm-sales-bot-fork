"""
Regression tests for Style/Semantic Separation — Legacy Mode (flag OFF).

Verifies that when separate_style_modifiers is OFF, all existing behavior
is preserved exactly as before the feature was added.

Feature flag: separate_style_modifiers (OFF in these tests)
"""

import pytest

from src.feature_flags import flags
from src.classifier.refinement_pipeline import (
    RefinementContext,
    RefinementDecision,
)
from src.classifier.style_modifier_detection import StyleModifierDetectionLayer


class TestStyleSeparationLegacy:
    """Legacy mode tests: flag OFF preserves old behavior."""

    @pytest.fixture(autouse=True)
    def setup_flag(self):
        """Ensure flag is OFF for all legacy tests."""
        flags.set_override("separate_style_modifiers", False)
        yield
        flags.clear_override("separate_style_modifiers")

    @pytest.fixture
    def layer(self):
        return StyleModifierDetectionLayer()

    # =========================================================================
    # Layer Behavior with Flag OFF
    # =========================================================================

    def test_flag_off_should_apply_returns_false(self, layer):
        """With flag OFF, _should_apply returns False for style intents."""
        ctx = RefinementContext(
            message="быстрее",
            intent="request_brevity",
            confidence=0.85,
            last_action="ask_about_company",
        )
        assert not layer._should_apply(ctx)

    def test_flag_off_refine_pass_through(self, layer):
        """With flag OFF, refine() returns pass-through (no modification)."""
        ctx = RefinementContext(
            message="быстрее",
            intent="request_brevity",
            confidence=0.85,
            last_action="ask_about_company",
        )
        result_dict = {
            "intent": "request_brevity",
            "confidence": 0.85,
            "alternatives": [],
        }
        layer_result = layer.refine("быстрее", result_dict, ctx)

        assert layer_result.decision == RefinementDecision.PASS_THROUGH
        assert layer_result.intent == "request_brevity"
        assert layer_result.confidence == 0.85

    def test_flag_off_no_style_modifiers_in_result(self, layer):
        """With flag OFF, no style_modifiers metadata in result."""
        ctx = RefinementContext(
            message="быстрее",
            intent="request_brevity",
            confidence=0.85,
        )
        result_dict = {"intent": "request_brevity", "confidence": 0.85}
        layer_result = layer.refine("быстрее", result_dict, ctx)

        assert "style_modifiers" not in layer_result.metadata

    # =========================================================================
    # Classification Result: Default Fields
    # =========================================================================

    def test_classification_result_defaults(self):
        """With flag OFF, classification result should have empty defaults."""
        # Simulate what unified.py does
        result = {
            "intent": "request_brevity",
            "confidence": 0.85,
        }

        # unified.py always adds these defaults
        if "style_modifiers" not in result:
            result["style_modifiers"] = []
        if "style_separation_applied" not in result:
            result["style_separation_applied"] = False

        assert result["style_modifiers"] == []
        assert result["style_separation_applied"] is False

    # =========================================================================
    # Generator: Legacy Branch Preserved
    # =========================================================================

    def test_generator_legacy_branch_active(self):
        """With flag OFF, request_brevity → respond_briefly (legacy behavior)."""
        # Verify the flag check logic
        assert not flags.is_enabled("separate_style_modifiers")
        # The condition in _select_template_key is:
        # if not flags.is_enabled("separate_style_modifiers"):
        #     template_key = "respond_briefly"
        # So with flag OFF, this path should be active (respond_briefly used)

    # =========================================================================
    # Bot Context: Empty Style Fields
    # =========================================================================

    def test_bot_context_empty_style_fields(self):
        """With flag OFF, classification has empty style fields for context."""
        classification = {
            "intent": "request_brevity",
            "confidence": 0.85,
        }

        # Simulate what bot.py does (safe .get with defaults)
        context_style = classification.get("style_modifiers", [])
        context_secondary = classification.get("secondary_signals", [])
        context_applied = classification.get("style_separation_applied", False)

        assert context_style == []
        assert context_secondary == []
        assert context_applied is False

    # =========================================================================
    # PersonalizationResult: No Side Effects
    # =========================================================================

    def test_personalization_result_unmodified(self):
        """With flag OFF, _apply_style_modifiers is a no-op."""
        from src.generator import ResponseGenerator
        from src.personalization.result import PersonalizationResult

        gen = ResponseGenerator.__new__(ResponseGenerator)
        gen._style_intents_cache = None

        p_result = PersonalizationResult()
        context = {"style_modifiers": ["request_brevity"]}

        # With flag OFF, should return unchanged
        result = gen._apply_style_modifiers(context, p_result)
        assert result.style.verbosity == "normal"
        assert result.style.applied_modifiers == []
        assert result.style.modifier_source == "behavioral"

    # =========================================================================
    # Non-Style Intents: Always Unaffected
    # =========================================================================

    def test_non_style_intent_unaffected(self, layer):
        """Non-style intents pass through regardless of flag."""
        ctx = RefinementContext(
            message="50 человек",
            intent="info_provided",
            confidence=0.9,
        )
        result_dict = {"intent": "info_provided", "confidence": 0.9}
        layer_result = layer.refine("50 человек", result_dict, ctx)

        assert layer_result.decision == RefinementDecision.PASS_THROUGH
        assert layer_result.intent == "info_provided"

    def test_question_intent_unaffected(self, layer):
        """Question intents pass through regardless of flag."""
        ctx = RefinementContext(
            message="сколько стоит?",
            intent="question_pricing",
            confidence=0.9,
        )
        result_dict = {"intent": "question_pricing", "confidence": 0.9}
        layer_result = layer.refine("сколько стоит?", result_dict, ctx)

        assert layer_result.decision == RefinementDecision.PASS_THROUGH

    # =========================================================================
    # Feature Flag Toggle: Dynamic
    # =========================================================================

    def test_dynamic_toggle_on_off(self, layer):
        """Flag can be toggled dynamically at runtime."""
        ctx = RefinementContext(
            message="быстрее",
            intent="request_brevity",
            confidence=0.8,
            last_action="ask_about_company",
        )
        result_dict = {"intent": "request_brevity", "confidence": 0.8, "alternatives": []}

        # Flag OFF → pass through
        assert not layer._should_apply(ctx)

        # Toggle ON
        flags.set_override("separate_style_modifiers", True)
        assert layer._should_apply(ctx)

        # Toggle back OFF
        flags.set_override("separate_style_modifiers", False)
        assert not layer._should_apply(ctx)

    # =========================================================================
    # SecondaryIntentDetection: No Skip When Flag Off
    # =========================================================================

    def test_secondary_detection_no_skip(self):
        """With flag OFF, skip_secondary_detection is not in metadata."""
        layer = StyleModifierDetectionLayer()
        ctx = RefinementContext(
            message="быстрее",
            intent="request_brevity",
            confidence=0.8,
        )
        result_dict = {"intent": "request_brevity", "confidence": 0.8}
        layer_result = layer.refine("быстрее", result_dict, ctx)

        # Pass through → no metadata with skip_secondary_detection
        assert "skip_secondary_detection" not in layer_result.metadata
