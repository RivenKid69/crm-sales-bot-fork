"""
Style Modifier Detection Layer — separates semantic intent from style modifiers.

When primary intent is a style intent (request_brevity, example_request, summary_request),
this layer infers the true semantic intent (what the user wants) and moves the style
signal to metadata (how the user wants it delivered).

Example:
    Input: "5 человек, быстрее", last_action="ask_about_company"
    Before: intent="request_brevity" → template="respond_briefly"
    After:  intent="info_provided" + style_modifier="request_brevity"
            → template="ask_about_problem" rendered concisely

Architecture:
    - Runs at HIGHEST priority (110) — before all other layers
    - FEATURE_FLAG = None — dynamic check in _should_apply() for runtime toggle
    - Style modifiers go ONLY in metadata (not secondary_signals — pipeline overwrites)
    - Config-driven: style_modifier_detection section in constants.yaml

SSoT: This file is the Single Source of Truth for style/semantic separation logic.
Feature flag: separate_style_modifiers (checked dynamically in _should_apply)
"""

from typing import Any, Dict, List, Optional, Set
import logging

from src.classifier.refinement_pipeline import (
    BaseRefinementLayer,
    LayerPriority,
    RefinementContext,
    RefinementResult,
    RefinementDecision,
    register_refinement_layer,
)

logger = logging.getLogger(__name__)


@register_refinement_layer("style_modifier_detection")
class StyleModifierDetectionLayer(BaseRefinementLayer):
    """
    Detects when primary intent is a style intent and separates semantic + style.

    Style intents (request_brevity, example_request, summary_request) describe
    HOW the user wants the response, not WHAT they want. This layer infers
    the semantic intent for routing and preserves style as a modifier.

    Semantic inference uses 6 strategies by priority:
        1. Action-based (highest) — last_action implies expected data type
        2. Alternatives-based — prefer question/price intents from alternatives
        3. Data-based — extracted_data present → info_provided
        4. Phase-based — dialogue phase implies expected intent
        5. Expects-based — expects_data_type set → info_provided
        6. Fallback — default to "unclear"
    """

    LAYER_NAME = "style_modifier_detection"
    LAYER_PRIORITY = LayerPriority.HIGHEST  # Runs before CRITICAL(100)

    # FEATURE_FLAG = None: dynamic toggle via _should_apply() instead of
    # cached self._enabled from __init__. See docstring in plan.
    FEATURE_FLAG = None

    def __init__(self):
        super().__init__()
        self._init_style_intents()

    def _get_config(self) -> Dict[str, Any]:
        """Load style_modifier_detection config from constants.yaml.

        Follows universal layer pattern: override _get_config(),
        result stored in self._config by BaseRefinementLayer.__init__().
        """
        try:
            from src.yaml_config.constants import get_style_modifier_detection_config
            return get_style_modifier_detection_config()
        except (ImportError, AttributeError):
            return {}

    def _init_style_intents(self):
        """Initialize style intents set and validate config.

        Follows layer pattern: delegate config-dependent init to _init_*() method
        (see FirstContactRefinementLayer._init_patterns(),
         GreetingContextRefinementLayer._init_suspicious_intents()).
        """
        self._style_intents: Set[str] = set(self._config.get("style_intents", [
            "request_brevity", "example_request", "summary_request"
        ]))

        # Validate: action_expects_data must not map to style intents
        action_expects = self._config.get("semantic_inference", {}).get(
            "action_expects_data", {}
        )
        bad_keys = [
            action for action, semantic in action_expects.items()
            if semantic in self._style_intents
        ]
        for action in bad_keys:
            logger.warning(
                "Config error: action_expects_data maps to style intent, removing",
                extra={"action": action, "mapped_to": action_expects[action]},
            )
            del action_expects[action]

    def _should_apply(self, ctx: RefinementContext) -> bool:
        """Check if style separation should apply.

        Dynamic feature flag check (NOT cached at init like FEATURE_FLAG would be).
        Lazy import — consistent with all layer files.
        """
        from src.feature_flags import flags
        if not flags.is_enabled("separate_style_modifiers"):
            return False
        return ctx.intent in self._style_intents

    def _do_refine(
        self,
        message: str,
        result: Dict[str, Any],
        ctx: RefinementContext
    ) -> RefinementResult:
        """Separate style intent into semantic intent + style modifier."""
        semantic_intent = self._infer_semantic_intent(ctx, result)

        # Safety: inference must not return style intent (prevent recursion)
        if semantic_intent in self._style_intents:
            logger.warning(
                "Inference returned style intent, fallback to unclear",
                extra={"inferred": semantic_intent, "original": ctx.intent},
            )
            semantic_intent = "unclear"

        # Map intent name to modifier name via config
        style_modifier = self._map_intent_to_modifier(ctx.intent)

        return self._create_refined_result(
            new_intent=semantic_intent,
            new_confidence=ctx.confidence if ctx.confidence > 0.5 else 0.75,
            original_intent=ctx.intent,
            reason="style_intent_separated",
            result=result,
            metadata={
                "style_modifiers": [style_modifier],
                "style_separation_applied": True,
                "original_intent": ctx.intent,
                "skip_secondary_detection": [ctx.intent],
            },
        )

    def _infer_semantic_intent(
        self, ctx: RefinementContext, result: Dict[str, Any]
    ) -> str:
        """Infer semantic intent using 6 strategies by priority.

        Uses ctx for context fields, result for alternatives.
        """
        inference_config = self._config.get("semantic_inference", {})

        # Strategy 1: Action-based (highest priority)
        action_expects = inference_config.get("action_expects_data", {})
        if ctx.last_action and ctx.last_action in action_expects:
            return action_expects[ctx.last_action]

        # Strategy 2: Alternatives-based (prefer question/price intents)
        alternatives = result.get("alternatives", [])
        if isinstance(alternatives, list):
            for alt in alternatives:
                if not isinstance(alt, dict):
                    continue
                alt_intent = alt.get("intent")
                if not isinstance(alt_intent, str):
                    continue
                if alt_intent.startswith("question_") or alt_intent.startswith("price_"):
                    return alt_intent

        # Strategy 3: Data-based
        if ctx.extracted_data:
            return "info_provided"

        # Strategy 4: Phase-based
        phase_defaults = inference_config.get("phase_defaults", {})
        if ctx.phase and ctx.phase in phase_defaults:
            return phase_defaults[ctx.phase]

        # Strategy 5: Expects-based
        if ctx.expects_data_type:
            return "info_provided"

        # Strategy 6: Fallback
        return inference_config.get("default_semantic", "unclear")

    def _map_intent_to_modifier(self, intent: str) -> str:
        """Map style intent name to modifier name via config."""
        mapping = self._config.get("intent_to_modifier", {})
        return mapping.get(intent, intent)
