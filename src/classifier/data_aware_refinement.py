"""
DataAwareRefinementLayer: promotes 'unclear' → 'info_provided'
when DataExtractor found meaningful data in the same message.

Architecture:
- Registered via @register_refinement_layer decorator (Principle 3.3)
- Uses existing extracted_data from RefinementContext (no duplicate extraction)
- Defense-in-depth Layer 1 for stall prevention (Principle 3.4)
"""
from src.classifier.refinement_pipeline import (
    BaseRefinementLayer,
    RefinementContext,
    RefinementResult,
    LayerPriority,
    register_refinement_layer,
)


# Fields that indicate meaningful business data (not trivial extractions)
# Verified against actual DataExtractor.extract() output fields
_MEANINGFUL_FIELDS = frozenset({
    # Direct matches from DataExtractor
    "company_size", "pain_point", "pain_category", "role",
    "timeline", "contact_info", "budget_range",
    "current_tools", "business_type", "users_count",
    "pain_impact", "financial_impact", "desired_outcome",
    "urgency", "client_name",
})

# Trivial fields excluded (don't indicate info_provided intent):
# option_index, high_interest, value_acknowledged, preferred_channel, contact_type


@register_refinement_layer("data_aware")
class DataAwareRefinementLayer(BaseRefinementLayer):
    """Promote 'unclear' to 'info_provided' when extracted data exists."""

    LAYER_NAME = "data_aware"
    LAYER_PRIORITY = LayerPriority.NORMAL
    FEATURE_FLAG = "data_aware_refinement"

    def _should_apply(self, ctx: RefinementContext) -> bool:
        """Only apply when classifier is uncertain AND data was extracted."""
        return ctx.intent == "unclear" and bool(ctx.extracted_data)

    def _do_refine(
        self,
        message: str,
        result: dict,
        ctx: RefinementContext,
    ) -> RefinementResult:
        # Filter for meaningful non-empty fields
        meaningful = {
            k: v for k, v in ctx.extracted_data.items()
            if v is not None and v != "" and k in _MEANINGFUL_FIELDS
        }

        if not meaningful:
            return self._pass_through(result, ctx)

        return self._create_refined_result(
            new_intent="info_provided",
            new_confidence=0.75,
            original_intent=ctx.intent,
            reason=f"data_aware: extracted {sorted(meaningful.keys())}",
            result=result,
        )
