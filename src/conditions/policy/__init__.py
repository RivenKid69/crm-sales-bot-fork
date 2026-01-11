"""
Policy Conditions Domain.

This package provides the condition infrastructure for DialoguePolicy,
including context, registry, and condition functions.

Part of Phase 5: DialoguePolicy Domain (ARCHITECTURE_UNIFIED_PLAN.md)

Usage:
    from src.conditions.policy import (
        PolicyContext,
        policy_registry,
        policy_condition,
        # Conditions
        is_stuck,
        has_breakthrough,
        in_breakthrough_window,
    )

    # Create context from envelope
    ctx = PolicyContext.from_envelope(envelope, current_action="ask_for_demo")

    # Evaluate a condition
    if policy_registry.evaluate("should_be_conservative", ctx):
        # Apply conservative overlay
        pass
"""

from src.conditions.policy.context import (
    PolicyContext,
    OVERLAY_ALLOWED_STATES,
    PROTECTED_STATES,
    AGGRESSIVE_ACTIONS,
)
from src.conditions.policy.registry import (
    policy_registry,
    policy_condition,
    get_policy_registry,
)

# Import all conditions to register them
from src.conditions.policy.conditions import (
    # Repair conditions
    is_stuck,
    has_oscillation,
    has_repeated_question,
    needs_repair,
    confidence_decreasing,
    high_unclear_count,
    # Objection conditions
    has_repeated_objections,
    total_objections_3_plus,
    total_objections_5_plus,
    should_escalate_objection,
    has_price_objection_repeat,
    has_competitor_objection_repeat,
    # Breakthrough conditions
    has_breakthrough,
    in_breakthrough_window,
    breakthrough_just_happened,
    should_add_soft_cta,
    # Momentum conditions
    momentum_positive,
    momentum_negative,
    momentum_neutral,
    engagement_high,
    engagement_low,
    engagement_declining,
    is_progressing,
    is_regressing,
    should_be_conservative,
    can_accelerate,
    # Guard conditions
    has_guard_intervention,
    frustration_high,
    frustration_critical,
    needs_empathy,
    # State conditions
    is_overlay_allowed,
    is_protected_state,
    is_aggressive_action,
    should_soften_action,
    is_spin_state,
    is_presentation_state,
    is_handle_objection_state,
    # Combined conditions
    should_apply_repair_overlay,
    should_apply_objection_overlay,
    should_apply_breakthrough_overlay,
    should_apply_conservative_overlay,
    has_effective_action_history,
    should_avoid_least_effective,
)


# Export all public components
__all__ = [
    # Context
    "PolicyContext",
    "OVERLAY_ALLOWED_STATES",
    "PROTECTED_STATES",
    "AGGRESSIVE_ACTIONS",
    # Registry
    "policy_registry",
    "policy_condition",
    "get_policy_registry",
    # Repair conditions
    "is_stuck",
    "has_oscillation",
    "has_repeated_question",
    "needs_repair",
    "confidence_decreasing",
    "high_unclear_count",
    # Objection conditions
    "has_repeated_objections",
    "total_objections_3_plus",
    "total_objections_5_plus",
    "should_escalate_objection",
    "has_price_objection_repeat",
    "has_competitor_objection_repeat",
    # Breakthrough conditions
    "has_breakthrough",
    "in_breakthrough_window",
    "breakthrough_just_happened",
    "should_add_soft_cta",
    # Momentum conditions
    "momentum_positive",
    "momentum_negative",
    "momentum_neutral",
    "engagement_high",
    "engagement_low",
    "engagement_declining",
    "is_progressing",
    "is_regressing",
    "should_be_conservative",
    "can_accelerate",
    # Guard conditions
    "has_guard_intervention",
    "frustration_high",
    "frustration_critical",
    "needs_empathy",
    # State conditions
    "is_overlay_allowed",
    "is_protected_state",
    "is_aggressive_action",
    "should_soften_action",
    "is_spin_state",
    "is_presentation_state",
    "is_handle_objection_state",
    # Combined conditions
    "should_apply_repair_overlay",
    "should_apply_objection_overlay",
    "should_apply_breakthrough_overlay",
    "should_apply_conservative_overlay",
    "has_effective_action_history",
    "should_avoid_least_effective",
]
