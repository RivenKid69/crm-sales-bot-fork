"""
Fallback Conditions Domain.

This package provides the condition infrastructure for FallbackHandler,
including context, registry, and condition functions.

Part of Phase 6: Fallback Domain (ARCHITECTURE_UNIFIED_PLAN.md)

Usage:
    from src.conditions.fallback import (
        FallbackContext,
        fallback_registry,
        fallback_condition,
        # Conditions
        should_escalate_tier,
        should_use_dynamic_cta,
        has_competitor_context,
    )

    # Create context from handler stats
    ctx = FallbackContext.from_handler_stats(stats, state, context)

    # Evaluate a condition
    if fallback_registry.evaluate("should_escalate_tier", ctx):
        # Escalate to next tier
        pass
"""

from src.conditions.fallback.context import (
    FallbackContext,
    FALLBACK_TIERS,
    DYNAMIC_CTA_STATES,
    PAIN_CATEGORIES,
    SMALL_COMPANY_THRESHOLD,
    LARGE_COMPANY_THRESHOLD,
)
from src.conditions.fallback.registry import (
    fallback_registry,
    fallback_condition,
    get_fallback_registry,
)

# Import all conditions to register them
from src.conditions.fallback.conditions import (
    # Tier conditions
    should_escalate_tier,
    is_tier_1,
    is_tier_2,
    is_tier_3,
    is_soft_close,
    is_max_tier,
    too_many_fallbacks,
    many_fallbacks_in_state,
    consecutive_fallbacks_2_plus,
    first_fallback_in_state,
    # Dynamic CTA conditions
    should_use_dynamic_cta,
    has_competitor_context,
    has_pain_context,
    has_pain_losing_clients,
    has_pain_no_control,
    has_pain_manual_work,
    last_intent_price_related,
    last_intent_feature_related,
    # Context conditions
    is_small_company,
    is_large_company,
    has_company_size,
    has_contextual_data,
    has_rich_context,
    # Frustration conditions
    frustration_high,
    frustration_critical,
    frustration_low,
    engagement_low,
    engagement_high,
    momentum_negative,
    momentum_positive,
    should_offer_graceful_exit,
    # State conditions
    is_spin_state,
    is_dynamic_cta_state,
    is_presentation_state,
    is_close_state,
    is_handle_objection_state,
    is_greeting_state,
    # Combined conditions
    should_skip_to_next_state,
    can_try_rephrase,
    should_show_options,
    needs_immediate_escalation,
    can_recover,
    should_personalize_response,
)


# Export all public components
__all__ = [
    # Context
    "FallbackContext",
    "FALLBACK_TIERS",
    "DYNAMIC_CTA_STATES",
    "PAIN_CATEGORIES",
    "SMALL_COMPANY_THRESHOLD",
    "LARGE_COMPANY_THRESHOLD",
    # Registry
    "fallback_registry",
    "fallback_condition",
    "get_fallback_registry",
    # Tier conditions
    "should_escalate_tier",
    "is_tier_1",
    "is_tier_2",
    "is_tier_3",
    "is_soft_close",
    "is_max_tier",
    "too_many_fallbacks",
    "many_fallbacks_in_state",
    "consecutive_fallbacks_2_plus",
    "first_fallback_in_state",
    # Dynamic CTA conditions
    "should_use_dynamic_cta",
    "has_competitor_context",
    "has_pain_context",
    "has_pain_losing_clients",
    "has_pain_no_control",
    "has_pain_manual_work",
    "last_intent_price_related",
    "last_intent_feature_related",
    # Context conditions
    "is_small_company",
    "is_large_company",
    "has_company_size",
    "has_contextual_data",
    "has_rich_context",
    # Frustration conditions
    "frustration_high",
    "frustration_critical",
    "frustration_low",
    "engagement_low",
    "engagement_high",
    "momentum_negative",
    "momentum_positive",
    "should_offer_graceful_exit",
    # State conditions
    "is_spin_state",
    "is_dynamic_cta_state",
    "is_presentation_state",
    "is_close_state",
    "is_handle_objection_state",
    "is_greeting_state",
    # Combined conditions
    "should_skip_to_next_state",
    "can_try_rephrase",
    "should_show_options",
    "needs_immediate_escalation",
    "can_recover",
    "should_personalize_response",
]
