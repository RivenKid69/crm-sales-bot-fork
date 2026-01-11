"""
Fallback Conditions.

This module provides all condition functions for the Fallback domain.
Conditions are organized by category:
- tier: Tier escalation conditions
- dynamic_cta: Dynamic CTA selection conditions
- context: Context-based conditions (pain, competitor, company size)
- frustration: Frustration and engagement conditions
- state: State-related conditions

Part of Phase 6: Fallback Domain (ARCHITECTURE_UNIFIED_PLAN.md)
"""

from src.conditions.fallback.context import (
    FallbackContext,
    DYNAMIC_CTA_STATES,
)
from src.conditions.fallback.registry import fallback_condition


# =============================================================================
# TIER CONDITIONS - Fallback tier escalation
# =============================================================================

@fallback_condition(
    "should_escalate_tier",
    description="Check if fallback should escalate to next tier",
    category="tier"
)
def should_escalate_tier(ctx: FallbackContext) -> bool:
    """
    Returns True if fallback should escalate to next tier.

    Escalate when: 2+ consecutive fallbacks at same tier
    or high frustration level.
    """
    return ctx.consecutive_fallbacks >= 2 or ctx.frustration_level >= 3


@fallback_condition(
    "is_tier_1",
    description="Check if current tier is tier 1 (rephrase)",
    category="tier"
)
def is_tier_1(ctx: FallbackContext) -> bool:
    """Returns True if current tier is tier 1."""
    return ctx.current_tier == "fallback_tier_1"


@fallback_condition(
    "is_tier_2",
    description="Check if current tier is tier 2 (options)",
    category="tier"
)
def is_tier_2(ctx: FallbackContext) -> bool:
    """Returns True if current tier is tier 2."""
    return ctx.current_tier == "fallback_tier_2"


@fallback_condition(
    "is_tier_3",
    description="Check if current tier is tier 3 (skip)",
    category="tier"
)
def is_tier_3(ctx: FallbackContext) -> bool:
    """Returns True if current tier is tier 3."""
    return ctx.current_tier == "fallback_tier_3"


@fallback_condition(
    "is_soft_close",
    description="Check if current tier is soft_close (exit)",
    category="tier"
)
def is_soft_close(ctx: FallbackContext) -> bool:
    """Returns True if current tier is soft_close."""
    return ctx.current_tier == "soft_close"


@fallback_condition(
    "is_max_tier",
    description="Check if at maximum tier (soft_close)",
    category="tier"
)
def is_max_tier(ctx: FallbackContext) -> bool:
    """Returns True if at maximum tier."""
    return ctx.is_max_tier()


@fallback_condition(
    "too_many_fallbacks",
    description="Check if too many fallbacks in conversation (5+)",
    category="tier"
)
def too_many_fallbacks(ctx: FallbackContext) -> bool:
    """Returns True if 5 or more fallbacks in conversation."""
    return ctx.total_fallbacks >= 5


@fallback_condition(
    "many_fallbacks_in_state",
    description="Check if many fallbacks in current state (3+)",
    category="tier"
)
def many_fallbacks_in_state(ctx: FallbackContext) -> bool:
    """Returns True if 3 or more fallbacks in current state."""
    return ctx.fallbacks_in_state >= 3


@fallback_condition(
    "consecutive_fallbacks_2_plus",
    description="Check if 2 or more consecutive fallbacks",
    category="tier"
)
def consecutive_fallbacks_2_plus(ctx: FallbackContext) -> bool:
    """Returns True if 2 or more consecutive fallbacks."""
    return ctx.consecutive_fallbacks >= 2


@fallback_condition(
    "first_fallback_in_state",
    description="Check if this is first fallback in current state",
    category="tier"
)
def first_fallback_in_state(ctx: FallbackContext) -> bool:
    """Returns True if this is the first fallback in current state."""
    return ctx.fallbacks_in_state == 0


# =============================================================================
# DYNAMIC CTA CONDITIONS - Context-aware option selection
# =============================================================================

@fallback_condition(
    "should_use_dynamic_cta",
    description="Check if dynamic CTA should be used",
    category="dynamic_cta"
)
def should_use_dynamic_cta(ctx: FallbackContext) -> bool:
    """
    Returns True if dynamic CTA should be used.

    Conditions: tier 2 AND state supports dynamic CTA AND
    there's contextual data to personalize.
    """
    if ctx.current_tier != "fallback_tier_2":
        return False
    if not ctx.is_dynamic_cta_state():
        return False
    # Need at least some context to personalize
    return (
        ctx.competitor_mentioned or
        ctx.has_pain_category() or
        ctx.company_size is not None or
        ctx.last_intent is not None
    )


@fallback_condition(
    "has_competitor_context",
    description="Check if competitor was mentioned for personalization",
    requires_fields={"competitor_mentioned"},
    category="dynamic_cta"
)
def has_competitor_context(ctx: FallbackContext) -> bool:
    """
    Returns True if competitor was mentioned.

    Highest priority for dynamic CTA selection.
    """
    return ctx.competitor_mentioned


@fallback_condition(
    "has_pain_context",
    description="Check if pain category is available for personalization",
    requires_fields={"pain_category"},
    category="dynamic_cta"
)
def has_pain_context(ctx: FallbackContext) -> bool:
    """Returns True if pain category is available."""
    return ctx.has_pain_category()


@fallback_condition(
    "has_pain_losing_clients",
    description="Check if pain is about losing clients",
    requires_fields={"pain_category"},
    category="dynamic_cta"
)
def has_pain_losing_clients(ctx: FallbackContext) -> bool:
    """Returns True if pain category is losing_clients."""
    return ctx.pain_category == "losing_clients"


@fallback_condition(
    "has_pain_no_control",
    description="Check if pain is about lack of control",
    requires_fields={"pain_category"},
    category="dynamic_cta"
)
def has_pain_no_control(ctx: FallbackContext) -> bool:
    """Returns True if pain category is no_control."""
    return ctx.pain_category == "no_control"


@fallback_condition(
    "has_pain_manual_work",
    description="Check if pain is about manual work",
    requires_fields={"pain_category"},
    category="dynamic_cta"
)
def has_pain_manual_work(ctx: FallbackContext) -> bool:
    """Returns True if pain category is manual_work."""
    return ctx.pain_category == "manual_work"


@fallback_condition(
    "last_intent_price_related",
    description="Check if last intent was price-related",
    category="dynamic_cta"
)
def last_intent_price_related(ctx: FallbackContext) -> bool:
    """Returns True if last intent was price-related."""
    if ctx.last_intent is None:
        return False
    price_intents = {"price_question", "pricing_details", "objection_price"}
    return ctx.last_intent in price_intents


@fallback_condition(
    "last_intent_feature_related",
    description="Check if last intent was feature-related",
    category="dynamic_cta"
)
def last_intent_feature_related(ctx: FallbackContext) -> bool:
    """Returns True if last intent was feature-related."""
    if ctx.last_intent is None:
        return False
    feature_intents = {"question_features", "question_integrations", "question_how_works"}
    return ctx.last_intent in feature_intents


# =============================================================================
# CONTEXT CONDITIONS - Company size and data availability
# =============================================================================

@fallback_condition(
    "is_small_company",
    description="Check if company is small (1-5 people)",
    requires_fields={"company_size"},
    category="context"
)
def is_small_company(ctx: FallbackContext) -> bool:
    """Returns True if company is small (1-5 people)."""
    return ctx.is_small_company()


@fallback_condition(
    "is_large_company",
    description="Check if company is large (20+ people)",
    requires_fields={"company_size"},
    category="context"
)
def is_large_company(ctx: FallbackContext) -> bool:
    """Returns True if company is large (20+ people)."""
    return ctx.is_large_company()


@fallback_condition(
    "has_company_size",
    description="Check if company size is known",
    requires_fields={"company_size"},
    category="context"
)
def has_company_size(ctx: FallbackContext) -> bool:
    """Returns True if company size is known."""
    return ctx.company_size is not None


@fallback_condition(
    "has_contextual_data",
    description="Check if any contextual data is available",
    category="context"
)
def has_contextual_data(ctx: FallbackContext) -> bool:
    """
    Returns True if any contextual data is available.

    Contextual data enables better personalization.
    """
    return (
        ctx.company_size is not None or
        ctx.competitor_mentioned or
        ctx.pain_category is not None
    )


@fallback_condition(
    "has_rich_context",
    description="Check if rich contextual data is available (2+ data points)",
    category="context"
)
def has_rich_context(ctx: FallbackContext) -> bool:
    """Returns True if 2 or more contextual data points available."""
    count = 0
    if ctx.company_size is not None:
        count += 1
    if ctx.competitor_mentioned:
        count += 1
    if ctx.pain_category is not None:
        count += 1
    if ctx.last_intent is not None:
        count += 1
    return count >= 2


# =============================================================================
# FRUSTRATION CONDITIONS - Frustration and engagement
# =============================================================================

@fallback_condition(
    "frustration_high",
    description="Check if frustration level is high (3+)",
    category="frustration"
)
def frustration_high(ctx: FallbackContext) -> bool:
    """Returns True if frustration level is 3 or higher."""
    return ctx.frustration_level >= 3


@fallback_condition(
    "frustration_critical",
    description="Check if frustration level is critical (4+)",
    category="frustration"
)
def frustration_critical(ctx: FallbackContext) -> bool:
    """Returns True if frustration level is 4 or higher."""
    return ctx.frustration_level >= 4


@fallback_condition(
    "frustration_low",
    description="Check if frustration level is low (0-1)",
    category="frustration"
)
def frustration_low(ctx: FallbackContext) -> bool:
    """Returns True if frustration level is 0 or 1."""
    return ctx.frustration_level <= 1


@fallback_condition(
    "engagement_low",
    description="Check if engagement level is low or disengaged",
    category="frustration"
)
def engagement_low(ctx: FallbackContext) -> bool:
    """Returns True if engagement level is low or disengaged."""
    return ctx.engagement_level in ("low", "disengaged")


@fallback_condition(
    "engagement_high",
    description="Check if engagement level is high",
    category="frustration"
)
def engagement_high(ctx: FallbackContext) -> bool:
    """Returns True if engagement level is high."""
    return ctx.engagement_level == "high"


@fallback_condition(
    "momentum_negative",
    description="Check if momentum is negative",
    category="frustration"
)
def momentum_negative(ctx: FallbackContext) -> bool:
    """Returns True if momentum direction is negative."""
    return ctx.momentum_direction == "negative"


@fallback_condition(
    "momentum_positive",
    description="Check if momentum is positive",
    category="frustration"
)
def momentum_positive(ctx: FallbackContext) -> bool:
    """Returns True if momentum direction is positive."""
    return ctx.momentum_direction == "positive"


@fallback_condition(
    "should_offer_graceful_exit",
    description="Check if graceful exit should be offered",
    category="frustration"
)
def should_offer_graceful_exit(ctx: FallbackContext) -> bool:
    """
    Returns True if graceful exit should be offered.

    Conditions: critical frustration OR (too many fallbacks AND low engagement)
    OR negative momentum with high fallbacks.
    """
    if ctx.frustration_level >= 4:
        return True
    if ctx.total_fallbacks >= 5 and ctx.engagement_level in ("low", "disengaged"):
        return True
    if ctx.momentum_direction == "negative" and ctx.total_fallbacks >= 4:
        return True
    return False


# =============================================================================
# STATE CONDITIONS - State-related conditions
# =============================================================================

@fallback_condition(
    "is_spin_state",
    description="Check if in a SPIN state",
    category="state"
)
def is_spin_state(ctx: FallbackContext) -> bool:
    """Returns True if in a SPIN state."""
    return ctx.state.startswith("spin_")


@fallback_condition(
    "is_dynamic_cta_state",
    description="Check if state supports dynamic CTA",
    category="state"
)
def is_dynamic_cta_state(ctx: FallbackContext) -> bool:
    """Returns True if current state supports dynamic CTA."""
    return ctx.is_dynamic_cta_state()


@fallback_condition(
    "is_presentation_state",
    description="Check if in presentation state",
    category="state"
)
def is_presentation_state(ctx: FallbackContext) -> bool:
    """Returns True if in presentation state."""
    return ctx.state == "presentation"


@fallback_condition(
    "is_close_state",
    description="Check if in close or soft_close state",
    category="state"
)
def is_close_state(ctx: FallbackContext) -> bool:
    """Returns True if in close or soft_close state."""
    return ctx.state in ("close", "soft_close")


@fallback_condition(
    "is_handle_objection_state",
    description="Check if in handle_objection state",
    category="state"
)
def is_handle_objection_state(ctx: FallbackContext) -> bool:
    """Returns True if in handle_objection state."""
    return ctx.state == "handle_objection"


@fallback_condition(
    "is_greeting_state",
    description="Check if in greeting state",
    category="state"
)
def is_greeting_state(ctx: FallbackContext) -> bool:
    """Returns True if in greeting state."""
    return ctx.state == "greeting"


# =============================================================================
# COMBINED CONDITIONS - Complex conditions for fallback decisions
# =============================================================================

@fallback_condition(
    "should_skip_to_next_state",
    description="Check if should offer skip to next state",
    category="combined"
)
def should_skip_to_next_state(ctx: FallbackContext) -> bool:
    """
    Returns True if skip to next state should be offered.

    Conditions: tier 3 AND (many fallbacks in state OR frustration moderate).
    """
    if ctx.current_tier != "fallback_tier_3":
        return False
    return ctx.fallbacks_in_state >= 2 or ctx.frustration_level >= 2


@fallback_condition(
    "can_try_rephrase",
    description="Check if rephrase (tier 1) is appropriate",
    category="combined"
)
def can_try_rephrase(ctx: FallbackContext) -> bool:
    """
    Returns True if rephrase approach is appropriate.

    Conditions: tier 1 AND not too many fallbacks AND frustration not high.
    """
    if ctx.current_tier != "fallback_tier_1":
        return False
    return ctx.total_fallbacks < 3 and ctx.frustration_level < 3


@fallback_condition(
    "should_show_options",
    description="Check if showing options (tier 2) is appropriate",
    category="combined"
)
def should_show_options(ctx: FallbackContext) -> bool:
    """
    Returns True if showing options is appropriate.

    Conditions: tier 2 AND state supports it.
    """
    if ctx.current_tier != "fallback_tier_2":
        return False
    # Options work best in SPIN states and presentation
    return ctx.state in DYNAMIC_CTA_STATES or ctx.state == "handle_objection"


@fallback_condition(
    "needs_immediate_escalation",
    description="Check if immediate escalation to soft_close is needed",
    category="combined"
)
def needs_immediate_escalation(ctx: FallbackContext) -> bool:
    """
    Returns True if immediate escalation to soft_close is needed.

    Emergency escalation when situation is critical.
    """
    # Critical frustration always triggers immediate escalation
    if ctx.frustration_level >= 5:
        return True
    # Too many consecutive fallbacks with negative momentum
    if ctx.consecutive_fallbacks >= 4 and ctx.momentum_direction == "negative":
        return True
    # Many fallbacks overall with low engagement
    if ctx.total_fallbacks >= 7 and ctx.engagement_level in ("low", "disengaged"):
        return True
    return False


@fallback_condition(
    "can_recover",
    description="Check if conversation can still be recovered",
    category="combined"
)
def can_recover(ctx: FallbackContext) -> bool:
    """
    Returns True if conversation can still be recovered.

    Recovery is possible when frustration is not critical
    and we haven't exhausted fallback options.
    """
    if ctx.frustration_level >= 4:
        return False
    if ctx.total_fallbacks >= 6:
        return False
    if ctx.engagement_level == "disengaged":
        return False
    return True


@fallback_condition(
    "should_personalize_response",
    description="Check if fallback response should be personalized",
    category="combined"
)
def should_personalize_response(ctx: FallbackContext) -> bool:
    """
    Returns True if fallback response should be personalized.

    Personalization when: has contextual data AND not critical situation.
    """
    if ctx.frustration_level >= 4:
        return False
    return has_contextual_data(ctx)


# Export all condition functions for testing
__all__ = [
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
