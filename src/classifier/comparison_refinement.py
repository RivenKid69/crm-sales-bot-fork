"""
ComparisonRefinementLayer - Refines comparison-like intents to objection_competitor
when the message contains competitive objection signals.

Bug #31a fix: "конкурент дешевле" classified as comparison → should be objection_competitor.

Architecture:
- Registered via @register_refinement_layer decorator (Principle 3.3)
- Uses keyword detection for competitive objection signals
- Feature-flagged (comparison_refinement: False by default)
- Fail-safe: passes through on error
"""

from typing import Any, ClassVar, Dict, List, Optional, Set
import re
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


# Comparison intents that can be refined to objection_competitor
COMPARISON_INTENTS: Set[str] = {
    "comparison",
    "question_product_comparison",
    "question_tariff_comparison",
    "question_snr_comparison",
}

# Competitive objection signal patterns (Russian)
COMPETITOR_OBJECTION_PATTERNS: List[re.Pattern] = [
    re.compile(r"(дешевл|дороже|стоит\s+меньше|цена\s+ниже)", re.IGNORECASE),
    re.compile(r"(конкурент|альтернатив)\w*\s+(лучш|дешевл|быстр|удобн)", re.IGNORECASE),
    re.compile(r"(у\s+них|у\s+другие?х?)\s+(лучш|дешевл|есть)", re.IGNORECASE),
    re.compile(r"(зачем\s+вы|чем\s+вы)\s+(лучш|отличаетесь)", re.IGNORECASE),
    re.compile(r"(bitrix|битрикс|amo|амо|salesforce|hubspot|pipedrive|мегаплан)", re.IGNORECASE),
    re.compile(r"(перейти|переход|уход)\s+(от|с|из)\s+\w+\s+(на|в|к)", re.IGNORECASE),
]


@register_refinement_layer("comparison")
class ComparisonRefinementLayer(BaseRefinementLayer):
    """
    Refines comparison intents to objection_competitor when competitive
    objection signals are detected.

    Trigger: intent in COMPARISON_INTENTS AND message matches competitor patterns
    Result: intent → objection_competitor, confidence boosted

    This catches cases like:
    - "У Битрикс дешевле" (comparison → objection_competitor)
    - "Конкурент лучше по функционалу" (comparison → objection_competitor)
    - "Зачем вы если есть AmoCRM?" (comparison → objection_competitor)
    """

    LAYER_NAME: ClassVar[str] = "comparison"
    LAYER_PRIORITY: ClassVar[LayerPriority] = LayerPriority.NORMAL
    FEATURE_FLAG: ClassVar[Optional[str]] = "comparison_refinement"

    def _should_apply(self, ctx: RefinementContext) -> bool:
        """Check if current intent is a comparison-type intent."""
        return ctx.intent in COMPARISON_INTENTS

    def _do_refine(
        self,
        message: str,
        result: Dict[str, Any],
        ctx: RefinementContext
    ) -> RefinementResult:
        """
        Check if message contains competitive objection signals.
        If yes, refine to objection_competitor.
        """
        message_lower = message.lower()

        for pattern in COMPETITOR_OBJECTION_PATTERNS:
            if pattern.search(message_lower):
                logger.info(
                    f"ComparisonRefinement: '{ctx.intent}' → 'objection_competitor' "
                    f"(pattern: {pattern.pattern})",
                    extra={
                        "layer": self.name,
                        "original_intent": ctx.intent,
                        "refined_intent": "objection_competitor",
                        "message_preview": message[:60],
                    }
                )

                return RefinementResult(
                    decision=RefinementDecision.REFINED,
                    intent="objection_competitor",
                    confidence=max(ctx.confidence, 0.75),
                    original_intent=ctx.intent,
                    refinement_reason="competitor_objection_signal",
                    metadata={
                        "matched_pattern": pattern.pattern,
                        "source_intent": ctx.intent,
                    },
                )

        # No competitive signals - pass through
        return RefinementResult(
            decision=RefinementDecision.PASS_THROUGH,
            intent=ctx.intent,
            confidence=ctx.confidence,
        )
