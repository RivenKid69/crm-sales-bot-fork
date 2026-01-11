"""
Personalization Conditions Domain.

This package provides the condition infrastructure for PersonalizationEngine/CTAGenerator,
including context, registry, and condition functions.

Part of Phase 7: Personalization Domain (ARCHITECTURE_UNIFIED_PLAN.md)

Usage:
    from src.conditions.personalization import (
        PersonalizationContext,
        personalization_registry,
        personalization_condition,
        # Conditions
        should_add_cta,
        should_use_soft_cta,
        has_company_context,
    )

    # Create context from envelope
    ctx = PersonalizationContext.from_envelope(envelope)

    # Evaluate a condition
    if personalization_registry.evaluate("should_add_cta", ctx):
        # Add CTA to response
        pass
"""

from src.conditions.personalization.context import (
    PersonalizationContext,
    CTA_TYPES,
    CTA_ELIGIBLE_STATES,
    SOFT_CTA_STATES,
    DIRECT_CTA_STATES,
    INDUSTRIES,
    ROLES,
    PAIN_CATEGORIES,
    SMALL_COMPANY_THRESHOLD,
    MEDIUM_COMPANY_THRESHOLD,
    LARGE_COMPANY_THRESHOLD,
    SOFT_CTA_FRUSTRATION_THRESHOLD,
    NO_CTA_FRUSTRATION_THRESHOLD,
    MIN_TURNS_FOR_CTA,
)
from src.conditions.personalization.registry import (
    personalization_registry,
    personalization_condition,
    get_personalization_registry,
)

# Import all conditions to register them
from src.conditions.personalization.conditions import (
    # CTA conditions
    should_add_cta,
    should_use_soft_cta,
    should_use_direct_cta,
    cta_eligible_state,
    enough_turns_for_cta,
    should_skip_cta,
    cta_after_breakthrough,
    demo_cta_appropriate,
    contact_cta_appropriate,
    trial_cta_appropriate,
    info_cta_appropriate,
    # Company conditions
    has_company_size,
    is_small_company,
    is_medium_company,
    is_large_company,
    is_enterprise_company,
    has_role,
    is_decision_maker,
    is_manager,
    has_industry,
    has_company_context,
    # Pain conditions
    has_pain_category,
    has_pain_point,
    has_pain_context,
    pain_losing_clients,
    pain_no_control,
    pain_manual_work,
    pain_no_analytics,
    pain_team_chaos,
    has_current_crm,
    competitor_mentioned,
    # Engagement conditions
    engagement_high,
    engagement_medium,
    engagement_low,
    momentum_positive,
    momentum_negative,
    momentum_neutral,
    has_breakthrough,
    # Tone conditions
    frustration_none,
    frustration_low,
    frustration_moderate,
    frustration_high,
    needs_soft_approach,
    # Objection conditions
    has_objections,
    has_multiple_objections,
    has_repeated_objections,
    objection_is_price,
    objection_is_competitor,
    objection_is_time,
    # State conditions
    is_spin_state,
    is_early_state,
    is_mid_state,
    is_late_state,
    is_presentation_state,
    is_close_state,
    is_objection_state,
    # Combined conditions
    ready_for_strong_cta,
    has_rich_context,
    can_personalize_by_company,
    can_personalize_by_pain,
    should_be_conservative,
    should_accelerate,
    needs_roi_messaging,
    needs_comparison_messaging,
    can_use_case_study,
    optimal_for_demo_offer,
    needs_urgency_reduction,
)


# Export all public components
__all__ = [
    # Context
    "PersonalizationContext",
    "CTA_TYPES",
    "CTA_ELIGIBLE_STATES",
    "SOFT_CTA_STATES",
    "DIRECT_CTA_STATES",
    "INDUSTRIES",
    "ROLES",
    "PAIN_CATEGORIES",
    "SMALL_COMPANY_THRESHOLD",
    "MEDIUM_COMPANY_THRESHOLD",
    "LARGE_COMPANY_THRESHOLD",
    "SOFT_CTA_FRUSTRATION_THRESHOLD",
    "NO_CTA_FRUSTRATION_THRESHOLD",
    "MIN_TURNS_FOR_CTA",
    # Registry
    "personalization_registry",
    "personalization_condition",
    "get_personalization_registry",
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
