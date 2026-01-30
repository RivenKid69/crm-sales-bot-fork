# src/classifier/disambiguation_resolution_layer.py

"""
Disambiguation Resolution Layer for the Refinement Pipeline.

Handles disambiguation responses within the unified Blackboard pipeline,
eliminating the parallel disambiguation pipeline (_handle_disambiguation_response).

Three resolution paths:
  A) Critical intent override — LLM classified a critical intent, exit disambiguation
  B) Option selection — user chose one of the offered options (1, 2, первое, второе)
  C) Custom input — user typed free text, LLM classification is the answer

All paths return a valid RefinementResult. No early returns, no None.
"""

from typing import Any, Dict, List, Set
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


@register_refinement_layer("disambiguation_resolution")
class DisambiguationResolutionLayer(BaseRefinementLayer):
    """
    Resolves disambiguation responses inside the refinement pipeline.

    Priority: CRITICAL (100) — runs first, before other layers.
    Feature flag: unified_disambiguation.

    Only activates when ctx.in_disambiguation is True (the bot is waiting
    for the user to pick an option or provide custom input).
    """

    LAYER_NAME = "disambiguation_resolution"
    LAYER_PRIORITY = LayerPriority.CRITICAL
    FEATURE_FLAG = "unified_disambiguation"

    CRITICAL_INTENTS: Set[str] = {"contact_provided", "rejection", "demo_request"}

    def _should_apply(self, ctx: RefinementContext) -> bool:
        return ctx.in_disambiguation

    def _do_refine(
        self,
        message: str,
        result: Dict[str, Any],
        ctx: RefinementContext,
    ) -> RefinementResult:
        intent = result.get("intent", "unclear")

        # --- Path A: Critical intent override ---
        if intent in self.CRITICAL_INTENTS:
            logger.info(
                "Disambiguation interrupted by critical intent",
                extra={"intent": intent},
            )
            ctx.metadata["exit_disambiguation"] = True
            return self._pass_through(result, ctx)

        # --- Path B: Option selection (1, 2, первое, второе, keyword match) ---
        options = ctx.disambiguation_options
        if options:
            from src.disambiguation_ui import DisambiguationUI

            ui = DisambiguationUI()
            resolved = ui.parse_answer(answer=message, options=options)

            if resolved and resolved != DisambiguationUI.CUSTOM_INPUT_MARKER:
                logger.info(
                    "Disambiguation resolved via option selection",
                    extra={"resolved_intent": resolved},
                )
                ctx.metadata["exit_disambiguation"] = True
                ctx.metadata["disambiguation_resolved_intent"] = resolved
                return self._create_refined_result(
                    new_intent=resolved,
                    new_confidence=0.9,
                    original_intent=intent,
                    reason="disambiguation_resolved",
                    result=result,
                    metadata={
                        "method": "disambiguation_resolved",
                        "selected_option": resolved,
                    },
                )

        # --- Path C: Custom input / unrecognized answer ---
        # The LLM already classified the message — that classification IS the answer.
        logger.info(
            "Disambiguation: custom input, using LLM classification",
            extra={"llm_intent": intent},
        )
        ctx.metadata["exit_disambiguation"] = True
        return self._pass_through(result, ctx)
