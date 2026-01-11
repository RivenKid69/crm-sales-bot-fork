"""
Personalization Conditions.

This module provides all condition functions for the Personalization domain.
Conditions are organized by category:
- cta: CTA eligibility and selection conditions
- company: Company context conditions
- pain: Pain point conditions
- engagement: Engagement and momentum conditions
- tone: Tone and frustration conditions
- state: State-related conditions
- combined: Complex multi-factor conditions

Part of Phase 7: Personalization Domain (ARCHITECTURE_UNIFIED_PLAN.md)
"""

from src.conditions.personalization.context import (
    PersonalizationContext,
    CTA_ELIGIBLE_STATES,
    SOFT_CTA_STATES,
    DIRECT_CTA_STATES,
    PAIN_CATEGORIES,
    SMALL_COMPANY_THRESHOLD,
    MEDIUM_COMPANY_THRESHOLD,
    LARGE_COMPANY_THRESHOLD,
    SOFT_CTA_FRUSTRATION_THRESHOLD,
    NO_CTA_FRUSTRATION_THRESHOLD,
    MIN_TURNS_FOR_CTA,
)
from src.conditions.personalization.registry import personalization_condition


# =============================================================================
# CTA CONDITIONS - CTA eligibility and selection
# =============================================================================

@personalization_condition(
    "should_add_cta",
    description="Check if CTA should be added to response",
    category="cta"
)
def should_add_cta(ctx: PersonalizationContext) -> bool:
    """
    Returns True if CTA should be added to response.

    Conditions: eligible state AND enough turns AND not high frustration.
    """
    if not ctx.is_cta_eligible_state():
        return False
    if not ctx.is_enough_turns_for_cta():
        return False
    if ctx.should_skip_cta():
        return False
    return True


@personalization_condition(
    "should_use_soft_cta",
    description="Check if soft CTA should be used instead of direct",
    category="cta"
)
def should_use_soft_cta(ctx: PersonalizationContext) -> bool:
    """
    Returns True if soft CTA should be used.

    Soft CTA when: frustration >= 3 OR soft CTA state OR negative momentum.
    """
    if ctx.frustration_level >= SOFT_CTA_FRUSTRATION_THRESHOLD:
        return True
    if ctx.is_soft_cta_state():
        return True
    if ctx.momentum_direction == "negative":
        return True
    return False


@personalization_condition(
    "should_use_direct_cta",
    description="Check if direct CTA should be used",
    category="cta"
)
def should_use_direct_cta(ctx: PersonalizationContext) -> bool:
    """
    Returns True if direct CTA should be used.

    Direct CTA when: direct state AND positive momentum AND low frustration.
    """
    if not ctx.is_direct_cta_state():
        return False
    if ctx.frustration_level >= SOFT_CTA_FRUSTRATION_THRESHOLD:
        return False
    return True


@personalization_condition(
    "cta_eligible_state",
    description="Check if current state is eligible for CTA",
    category="cta"
)
def cta_eligible_state(ctx: PersonalizationContext) -> bool:
    """Returns True if current state is eligible for CTA."""
    return ctx.is_cta_eligible_state()


@personalization_condition(
    "enough_turns_for_cta",
    description="Check if enough turns have passed for CTA",
    category="cta"
)
def enough_turns_for_cta(ctx: PersonalizationContext) -> bool:
    """Returns True if minimum turns for CTA have passed."""
    return ctx.is_enough_turns_for_cta()


@personalization_condition(
    "should_skip_cta",
    description="Check if CTA should be skipped due to high frustration",
    category="cta"
)
def should_skip_cta(ctx: PersonalizationContext) -> bool:
    """Returns True if CTA should be skipped."""
    return ctx.should_skip_cta()


@personalization_condition(
    "cta_after_breakthrough",
    description="Check if CTA should be added after breakthrough",
    category="cta"
)
def cta_after_breakthrough(ctx: PersonalizationContext) -> bool:
    """
    Returns True if this is a good moment for CTA after breakthrough.

    Breakthrough creates opportunity for stronger CTA.
    """
    return ctx.has_breakthrough and not ctx.should_skip_cta()


@personalization_condition(
    "demo_cta_appropriate",
    description="Check if demo CTA is appropriate",
    category="cta"
)
def demo_cta_appropriate(ctx: PersonalizationContext) -> bool:
    """
    Returns True if demo CTA is appropriate.

    Demo CTA works best in presentation state with engaged client.
    Hesitant clients (with objections) should get trial CTA instead.
    """
    if ctx.state not in ("presentation", "spin_need_payoff"):
        return False
    if ctx.engagement_level in ("low", "disengaged"):
        return False
    if ctx.frustration_level >= SOFT_CTA_FRUSTRATION_THRESHOLD:
        return False
    # Hesitant clients with objections should prefer trial CTA
    if ctx.total_objections >= 2:
        return False
    return True


@personalization_condition(
    "contact_cta_appropriate",
    description="Check if contact CTA is appropriate",
    category="cta"
)
def contact_cta_appropriate(ctx: PersonalizationContext) -> bool:
    """
    Returns True if contact CTA is appropriate.

    Contact CTA works best in close state or after breakthrough.
    """
    if ctx.state == "close":
        return True
    if ctx.has_breakthrough and ctx.state == "presentation":
        return True
    return False


@personalization_condition(
    "trial_cta_appropriate",
    description="Check if trial CTA is appropriate",
    category="cta"
)
def trial_cta_appropriate(ctx: PersonalizationContext) -> bool:
    """
    Returns True if trial CTA is appropriate.

    Trial CTA for hesitant clients in presentation.
    """
    if ctx.state != "presentation":
        return False
    if ctx.total_objections >= 2:
        return True
    if ctx.engagement_level == "medium" and ctx.momentum_direction == "neutral":
        return True
    return False


@personalization_condition(
    "info_cta_appropriate",
    description="Check if info CTA is appropriate",
    category="cta"
)
def info_cta_appropriate(ctx: PersonalizationContext) -> bool:
    """
    Returns True if info CTA is appropriate.

    Info CTA for earlier stages or lower engagement.
    """
    if ctx.state in ("spin_implication", "spin_need_payoff"):
        return True
    if ctx.engagement_level in ("low", "disengaged"):
        return True
    return False


# =============================================================================
# COMPANY CONDITIONS - Company context for personalization
# =============================================================================

@personalization_condition(
    "has_company_size",
    description="Check if company size is known",
    requires_fields={"company_size"},
    category="company"
)
def has_company_size(ctx: PersonalizationContext) -> bool:
    """Returns True if company size is known."""
    return ctx.company_size is not None


@personalization_condition(
    "is_small_company",
    description="Check if company is small (1-5 people)",
    requires_fields={"company_size"},
    category="company"
)
def is_small_company(ctx: PersonalizationContext) -> bool:
    """Returns True if company is small (1-5 people)."""
    return ctx.is_small_company()


@personalization_condition(
    "is_medium_company",
    description="Check if company is medium (6-20 people)",
    requires_fields={"company_size"},
    category="company"
)
def is_medium_company(ctx: PersonalizationContext) -> bool:
    """Returns True if company is medium (6-20 people)."""
    return ctx.is_medium_company()


@personalization_condition(
    "is_large_company",
    description="Check if company is large (20+ people)",
    requires_fields={"company_size"},
    category="company"
)
def is_large_company(ctx: PersonalizationContext) -> bool:
    """Returns True if company is large (20+ people)."""
    return ctx.is_large_company()


@personalization_condition(
    "is_enterprise_company",
    description="Check if company is enterprise (50+ people)",
    requires_fields={"company_size"},
    category="company"
)
def is_enterprise_company(ctx: PersonalizationContext) -> bool:
    """Returns True if company is enterprise (50+ people)."""
    return ctx.is_enterprise_company()


@personalization_condition(
    "has_role",
    description="Check if client role is known",
    requires_fields={"role"},
    category="company"
)
def has_role(ctx: PersonalizationContext) -> bool:
    """Returns True if client role is known."""
    return ctx.role is not None


@personalization_condition(
    "is_decision_maker",
    description="Check if client is a decision maker (owner/director)",
    requires_fields={"role"},
    category="company"
)
def is_decision_maker(ctx: PersonalizationContext) -> bool:
    """Returns True if client is owner or director."""
    if ctx.role is None:
        return False
    return ctx.role in ("owner", "director")


@personalization_condition(
    "is_manager",
    description="Check if client is a manager",
    requires_fields={"role"},
    category="company"
)
def is_manager(ctx: PersonalizationContext) -> bool:
    """Returns True if client is a manager."""
    return ctx.role == "manager"


@personalization_condition(
    "has_industry",
    description="Check if company industry is known",
    requires_fields={"industry"},
    category="company"
)
def has_industry(ctx: PersonalizationContext) -> bool:
    """Returns True if company industry is known."""
    return ctx.industry is not None


@personalization_condition(
    "has_company_context",
    description="Check if any company context is available",
    category="company"
)
def has_company_context(ctx: PersonalizationContext) -> bool:
    """Returns True if any company context is available."""
    return ctx.has_company_context()


# =============================================================================
# PAIN CONDITIONS - Pain point conditions
# =============================================================================

@personalization_condition(
    "has_pain_category",
    description="Check if pain category is known",
    requires_fields={"pain_category"},
    category="pain"
)
def has_pain_category(ctx: PersonalizationContext) -> bool:
    """Returns True if pain category is known."""
    return ctx.pain_category is not None


@personalization_condition(
    "has_pain_point",
    description="Check if specific pain point is known",
    requires_fields={"pain_point"},
    category="pain"
)
def has_pain_point(ctx: PersonalizationContext) -> bool:
    """Returns True if specific pain point is known."""
    return ctx.pain_point is not None


@personalization_condition(
    "has_pain_context",
    description="Check if any pain context is available",
    category="pain"
)
def has_pain_context(ctx: PersonalizationContext) -> bool:
    """Returns True if any pain context is available."""
    return ctx.has_pain_context()


@personalization_condition(
    "pain_losing_clients",
    description="Check if pain is about losing clients",
    requires_fields={"pain_category"},
    category="pain"
)
def pain_losing_clients(ctx: PersonalizationContext) -> bool:
    """Returns True if pain category is losing_clients."""
    return ctx.pain_category == "losing_clients"


@personalization_condition(
    "pain_no_control",
    description="Check if pain is about lack of control",
    requires_fields={"pain_category"},
    category="pain"
)
def pain_no_control(ctx: PersonalizationContext) -> bool:
    """Returns True if pain category is no_control."""
    return ctx.pain_category == "no_control"


@personalization_condition(
    "pain_manual_work",
    description="Check if pain is about manual work",
    requires_fields={"pain_category"},
    category="pain"
)
def pain_manual_work(ctx: PersonalizationContext) -> bool:
    """Returns True if pain category is manual_work."""
    return ctx.pain_category == "manual_work"


@personalization_condition(
    "pain_no_analytics",
    description="Check if pain is about lack of analytics",
    requires_fields={"pain_category"},
    category="pain"
)
def pain_no_analytics(ctx: PersonalizationContext) -> bool:
    """Returns True if pain category is no_analytics."""
    return ctx.pain_category == "no_analytics"


@personalization_condition(
    "pain_team_chaos",
    description="Check if pain is about team chaos",
    requires_fields={"pain_category"},
    category="pain"
)
def pain_team_chaos(ctx: PersonalizationContext) -> bool:
    """Returns True if pain category is team_chaos."""
    return ctx.pain_category == "team_chaos"


@personalization_condition(
    "has_current_crm",
    description="Check if current CRM is known",
    requires_fields={"current_crm"},
    category="pain"
)
def has_current_crm(ctx: PersonalizationContext) -> bool:
    """Returns True if current CRM is known."""
    return ctx.current_crm is not None


@personalization_condition(
    "competitor_mentioned",
    description="Check if a competitor was mentioned",
    requires_fields={"competitor_mentioned"},
    category="pain"
)
def competitor_mentioned(ctx: PersonalizationContext) -> bool:
    """Returns True if competitor was mentioned."""
    return ctx.competitor_mentioned


# =============================================================================
# ENGAGEMENT CONDITIONS - Engagement and momentum
# =============================================================================

@personalization_condition(
    "engagement_high",
    description="Check if engagement level is high",
    category="engagement"
)
def engagement_high(ctx: PersonalizationContext) -> bool:
    """Returns True if engagement level is high."""
    return ctx.engagement_level == "high"


@personalization_condition(
    "engagement_medium",
    description="Check if engagement level is medium",
    category="engagement"
)
def engagement_medium(ctx: PersonalizationContext) -> bool:
    """Returns True if engagement level is medium."""
    return ctx.engagement_level == "medium"


@personalization_condition(
    "engagement_low",
    description="Check if engagement level is low or disengaged",
    category="engagement"
)
def engagement_low(ctx: PersonalizationContext) -> bool:
    """Returns True if engagement level is low or disengaged."""
    return ctx.engagement_level in ("low", "disengaged")


@personalization_condition(
    "momentum_positive",
    description="Check if momentum is positive",
    category="engagement"
)
def momentum_positive(ctx: PersonalizationContext) -> bool:
    """Returns True if momentum direction is positive."""
    return ctx.momentum_direction == "positive"


@personalization_condition(
    "momentum_negative",
    description="Check if momentum is negative",
    category="engagement"
)
def momentum_negative(ctx: PersonalizationContext) -> bool:
    """Returns True if momentum direction is negative."""
    return ctx.momentum_direction == "negative"


@personalization_condition(
    "momentum_neutral",
    description="Check if momentum is neutral",
    category="engagement"
)
def momentum_neutral(ctx: PersonalizationContext) -> bool:
    """Returns True if momentum direction is neutral."""
    return ctx.momentum_direction == "neutral"


@personalization_condition(
    "has_breakthrough",
    description="Check if a breakthrough moment occurred",
    category="engagement"
)
def has_breakthrough(ctx: PersonalizationContext) -> bool:
    """Returns True if a breakthrough moment occurred."""
    return ctx.has_breakthrough


# =============================================================================
# TONE CONDITIONS - Tone and frustration
# =============================================================================

@personalization_condition(
    "frustration_none",
    description="Check if frustration level is zero",
    category="tone"
)
def frustration_none(ctx: PersonalizationContext) -> bool:
    """Returns True if frustration level is zero."""
    return ctx.frustration_level == 0


@personalization_condition(
    "frustration_low",
    description="Check if frustration level is low (1-2)",
    category="tone"
)
def frustration_low(ctx: PersonalizationContext) -> bool:
    """Returns True if frustration level is 1 or 2."""
    return 1 <= ctx.frustration_level <= 2


@personalization_condition(
    "frustration_moderate",
    description="Check if frustration level is moderate (3-4)",
    category="tone"
)
def frustration_moderate(ctx: PersonalizationContext) -> bool:
    """Returns True if frustration level is 3 or 4."""
    return 3 <= ctx.frustration_level <= 4


@personalization_condition(
    "frustration_high",
    description="Check if frustration level is high (5+)",
    category="tone"
)
def frustration_high(ctx: PersonalizationContext) -> bool:
    """Returns True if frustration level is 5 or higher."""
    return ctx.frustration_level >= 5


@personalization_condition(
    "needs_soft_approach",
    description="Check if soft approach is needed based on frustration/momentum",
    category="tone"
)
def needs_soft_approach(ctx: PersonalizationContext) -> bool:
    """
    Returns True if soft approach is needed.

    Soft approach when: moderate frustration OR negative momentum OR low engagement.
    """
    if ctx.frustration_level >= 3:
        return True
    if ctx.momentum_direction == "negative":
        return True
    if ctx.engagement_level in ("low", "disengaged"):
        return True
    return False


# =============================================================================
# OBJECTION CONDITIONS - Objection handling
# =============================================================================

@personalization_condition(
    "has_objections",
    description="Check if there are any objections",
    category="objection"
)
def has_objections(ctx: PersonalizationContext) -> bool:
    """Returns True if there is at least one objection."""
    return ctx.total_objections > 0


@personalization_condition(
    "has_multiple_objections",
    description="Check if there are multiple objections (2+)",
    category="objection"
)
def has_multiple_objections(ctx: PersonalizationContext) -> bool:
    """Returns True if there are 2 or more objections."""
    return ctx.total_objections >= 2


@personalization_condition(
    "has_repeated_objections",
    description="Check if there are repeated objection types",
    category="objection"
)
def has_repeated_objections(ctx: PersonalizationContext) -> bool:
    """Returns True if there are repeated objection types."""
    return len(ctx.repeated_objection_types) > 0


@personalization_condition(
    "objection_is_price",
    description="Check if current objection is about price",
    requires_fields={"objection_type"},
    category="objection"
)
def objection_is_price(ctx: PersonalizationContext) -> bool:
    """Returns True if current objection is price-related."""
    if ctx.objection_type is None:
        return False
    return "price" in ctx.objection_type.lower()


@personalization_condition(
    "objection_is_competitor",
    description="Check if current objection is about competitor",
    requires_fields={"objection_type"},
    category="objection"
)
def objection_is_competitor(ctx: PersonalizationContext) -> bool:
    """Returns True if current objection is competitor-related."""
    if ctx.objection_type is None:
        return False
    return "competitor" in ctx.objection_type.lower()


@personalization_condition(
    "objection_is_time",
    description="Check if current objection is about time",
    requires_fields={"objection_type"},
    category="objection"
)
def objection_is_time(ctx: PersonalizationContext) -> bool:
    """Returns True if current objection is time-related."""
    if ctx.objection_type is None:
        return False
    return "time" in ctx.objection_type.lower() or "later" in ctx.objection_type.lower()


# =============================================================================
# STATE CONDITIONS - State-related conditions
# =============================================================================

@personalization_condition(
    "is_spin_state",
    description="Check if in a SPIN state",
    category="state"
)
def is_spin_state(ctx: PersonalizationContext) -> bool:
    """Returns True if in a SPIN state."""
    return ctx.state.startswith("spin_")


@personalization_condition(
    "is_early_state",
    description="Check if in early state (greeting/spin_situation)",
    category="state"
)
def is_early_state(ctx: PersonalizationContext) -> bool:
    """Returns True if in early state."""
    return ctx.state in ("greeting", "spin_situation", "spin_problem")


@personalization_condition(
    "is_mid_state",
    description="Check if in mid state (spin_implication/need_payoff)",
    category="state"
)
def is_mid_state(ctx: PersonalizationContext) -> bool:
    """Returns True if in mid state."""
    return ctx.state in ("spin_implication", "spin_need_payoff")


@personalization_condition(
    "is_late_state",
    description="Check if in late state (presentation/close)",
    category="state"
)
def is_late_state(ctx: PersonalizationContext) -> bool:
    """Returns True if in late state."""
    return ctx.state in ("presentation", "close", "handle_objection")


@personalization_condition(
    "is_presentation_state",
    description="Check if in presentation state",
    category="state"
)
def is_presentation_state(ctx: PersonalizationContext) -> bool:
    """Returns True if in presentation state."""
    return ctx.state == "presentation"


@personalization_condition(
    "is_close_state",
    description="Check if in close state",
    category="state"
)
def is_close_state(ctx: PersonalizationContext) -> bool:
    """Returns True if in close state."""
    return ctx.state == "close"


@personalization_condition(
    "is_objection_state",
    description="Check if in handle_objection state",
    category="state"
)
def is_objection_state(ctx: PersonalizationContext) -> bool:
    """Returns True if in handle_objection state."""
    return ctx.state == "handle_objection"


# =============================================================================
# COMBINED CONDITIONS - Complex multi-factor conditions
# =============================================================================

@personalization_condition(
    "ready_for_strong_cta",
    description="Check if ready for strong CTA (breakthrough + engagement)",
    category="combined"
)
def ready_for_strong_cta(ctx: PersonalizationContext) -> bool:
    """
    Returns True if conditions are ideal for strong CTA.

    Ideal: breakthrough + high/medium engagement + low frustration + late state.
    """
    if not ctx.has_breakthrough:
        return False
    if ctx.engagement_level in ("low", "disengaged"):
        return False
    if ctx.frustration_level >= 3:
        return False
    if not ctx.state in ("presentation", "close"):
        return False
    return True


@personalization_condition(
    "has_rich_context",
    description="Check if rich contextual data is available for personalization",
    category="combined"
)
def has_rich_context(ctx: PersonalizationContext) -> bool:
    """Returns True if 2 or more contextual data points available."""
    return ctx.has_rich_context()


@personalization_condition(
    "can_personalize_by_company",
    description="Check if response can be personalized by company info",
    category="combined"
)
def can_personalize_by_company(ctx: PersonalizationContext) -> bool:
    """
    Returns True if enough company info for personalization.

    Need: company_size OR (role AND industry).
    """
    if ctx.company_size is not None:
        return True
    if ctx.role is not None and ctx.industry is not None:
        return True
    return False


@personalization_condition(
    "can_personalize_by_pain",
    description="Check if response can be personalized by pain point",
    category="combined"
)
def can_personalize_by_pain(ctx: PersonalizationContext) -> bool:
    """
    Returns True if pain context allows personalization.

    Need: pain_category OR pain_point OR competitor context.
    """
    if ctx.pain_category is not None:
        return True
    if ctx.pain_point is not None:
        return True
    if ctx.competitor_mentioned:
        return True
    return False


@personalization_condition(
    "should_be_conservative",
    description="Check if conservative approach is needed",
    category="combined"
)
def should_be_conservative(ctx: PersonalizationContext) -> bool:
    """
    Returns True if conservative approach is needed.

    Conservative when: multiple objections OR frustration OR negative momentum.
    """
    if ctx.total_objections >= 2:
        return True
    if ctx.frustration_level >= 3:
        return True
    if ctx.momentum_direction == "negative":
        return True
    if ctx.engagement_level in ("low", "disengaged"):
        return True
    return False


@personalization_condition(
    "should_accelerate",
    description="Check if acceleration approach is appropriate",
    category="combined"
)
def should_accelerate(ctx: PersonalizationContext) -> bool:
    """
    Returns True if acceleration is appropriate.

    Accelerate when: positive momentum AND high engagement AND breakthrough.
    """
    if ctx.momentum_direction != "positive":
        return False
    if ctx.engagement_level != "high":
        return False
    if not ctx.has_breakthrough:
        return False
    return True


@personalization_condition(
    "needs_roi_messaging",
    description="Check if ROI messaging would be effective",
    category="combined"
)
def needs_roi_messaging(ctx: PersonalizationContext) -> bool:
    """
    Returns True if ROI messaging would be effective.

    ROI messaging for: price objection with company size known.
    """
    if ctx.objection_type is None:
        return False
    if "price" not in ctx.objection_type.lower():
        return False
    if ctx.company_size is None:
        return False
    return True


@personalization_condition(
    "needs_comparison_messaging",
    description="Check if competitor comparison messaging is needed",
    category="combined"
)
def needs_comparison_messaging(ctx: PersonalizationContext) -> bool:
    """
    Returns True if competitor comparison messaging is appropriate.

    Comparison when: competitor mentioned OR competitor objection.
    """
    if ctx.competitor_mentioned:
        return True
    if ctx.objection_type and "competitor" in ctx.objection_type.lower():
        return True
    return False


@personalization_condition(
    "can_use_case_study",
    description="Check if case study reference would be effective",
    category="combined"
)
def can_use_case_study(ctx: PersonalizationContext) -> bool:
    """
    Returns True if case study reference would be effective.

    Case study effective when: industry known AND company size known.
    """
    if ctx.industry is None:
        return False
    if ctx.company_size is None:
        return False
    return True


@personalization_condition(
    "optimal_for_demo_offer",
    description="Check if this is optimal moment for demo offer",
    category="combined"
)
def optimal_for_demo_offer(ctx: PersonalizationContext) -> bool:
    """
    Returns True if this is optimal moment for demo offer.

    Optimal: presentation state + positive signals + pain identified.
    """
    if ctx.state != "presentation":
        return False
    if ctx.frustration_level >= 3:
        return False
    if ctx.engagement_level in ("low", "disengaged"):
        return False
    if not ctx.has_pain_context():
        return False
    return True


@personalization_condition(
    "needs_urgency_reduction",
    description="Check if urgency should be reduced in messaging",
    category="combined"
)
def needs_urgency_reduction(ctx: PersonalizationContext) -> bool:
    """
    Returns True if urgency should be reduced.

    Reduce urgency when: time objection OR low engagement.
    """
    if ctx.objection_type and "time" in ctx.objection_type.lower():
        return True
    if ctx.engagement_level in ("low", "disengaged"):
        return True
    return False


# Export all condition functions for testing
__all__ = [
    # CTA conditions
    "should_add_cta",
    "should_use_soft_cta",
    "should_use_direct_cta",
    "cta_eligible_state",
    "enough_turns_for_cta",
    "should_skip_cta",
    "cta_after_breakthrough",
    "demo_cta_appropriate",
    "contact_cta_appropriate",
    "trial_cta_appropriate",
    "info_cta_appropriate",
    # Company conditions
    "has_company_size",
    "is_small_company",
    "is_medium_company",
    "is_large_company",
    "is_enterprise_company",
    "has_role",
    "is_decision_maker",
    "is_manager",
    "has_industry",
    "has_company_context",
    # Pain conditions
    "has_pain_category",
    "has_pain_point",
    "has_pain_context",
    "pain_losing_clients",
    "pain_no_control",
    "pain_manual_work",
    "pain_no_analytics",
    "pain_team_chaos",
    "has_current_crm",
    "competitor_mentioned",
    # Engagement conditions
    "engagement_high",
    "engagement_medium",
    "engagement_low",
    "momentum_positive",
    "momentum_negative",
    "momentum_neutral",
    "has_breakthrough",
    # Tone conditions
    "frustration_none",
    "frustration_low",
    "frustration_moderate",
    "frustration_high",
    "needs_soft_approach",
    # Objection conditions
    "has_objections",
    "has_multiple_objections",
    "has_repeated_objections",
    "objection_is_price",
    "objection_is_competitor",
    "objection_is_time",
    # State conditions
    "is_spin_state",
    "is_early_state",
    "is_mid_state",
    "is_late_state",
    "is_presentation_state",
    "is_close_state",
    "is_objection_state",
    # Combined conditions
    "ready_for_strong_cta",
    "has_rich_context",
    "can_personalize_by_company",
    "can_personalize_by_pain",
    "should_be_conservative",
    "should_accelerate",
    "needs_roi_messaging",
    "needs_comparison_messaging",
    "can_use_case_study",
    "optimal_for_demo_offer",
    "needs_urgency_reduction",
]
