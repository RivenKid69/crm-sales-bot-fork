"""
Policy Conditions.

This module provides all condition functions for the Policy domain.
Conditions are organized by category:
- repair: Repair mode conditions (stuck, oscillation, repeated question)
- objection: Objection-related conditions
- breakthrough: Breakthrough detection and window
- momentum: Momentum and engagement conditions
- guard: Guard intervention conditions
- state: State-related conditions

Part of Phase 5: DialoguePolicy Domain (ARCHITECTURE_UNIFIED_PLAN.md)
"""

from src.conditions.policy.context import (
    PolicyContext,
    PROTECTED_STATES,
    AGGRESSIVE_ACTIONS,
)
from src.conditions.policy.registry import policy_condition
from src.yaml_config.constants import OBJECTION_INTENTS

# Import from Single Source of Truth for frustration thresholds
from src.frustration_thresholds import (
    FRUSTRATION_ELEVATED,
    FRUSTRATION_MODERATE,
    FRUSTRATION_WARNING,
    is_frustration_elevated,
    is_frustration_moderate,
    is_frustration_warning,
)


# =============================================================================
# REPAIR CONDITIONS - Stuck, oscillation, repeated question
# =============================================================================

@policy_condition(
    "is_stuck",
    description="Check if client is stuck in the conversation",
    category="repair"
)
def is_stuck(ctx: PolicyContext) -> bool:
    """
    Returns True if client is stuck.

    Stuck pattern detected by ContextWindow when client
    shows confusion or lack of progress.
    """
    return ctx.is_stuck


@policy_condition(
    "has_oscillation",
    description="Check if oscillation pattern detected (back and forth)",
    category="repair"
)
def has_oscillation(ctx: PolicyContext) -> bool:
    """
    Returns True if oscillation pattern detected.

    Oscillation occurs when client goes back and forth
    between states or intents.
    """
    return ctx.has_oscillation


@policy_condition(
    "has_repeated_question",
    description="Check if client repeated a question",
    category="repair"
)
def has_repeated_question(ctx: PolicyContext) -> bool:
    """
    Returns True if client repeated a question.

    The specific question type is in ctx.repeated_question.
    """
    return ctx.repeated_question is not None


@policy_condition(
    "needs_repair",
    description="Check if any repair condition is triggered",
    category="repair"
)
def needs_repair(ctx: PolicyContext) -> bool:
    """
    Returns True if any repair condition is triggered.

    Combines: is_stuck OR has_oscillation OR has_repeated_question.
    Suppressed during stall_guard cooldown (turn after StallGuard action).
    """
    if ctx.stall_guard_cooldown:
        return False
    return ctx.is_stuck or ctx.has_oscillation or ctx.repeated_question is not None


@policy_condition(
    "can_apply_repair",
    description="Gate: repair overlay is allowed to run (not suppressed by cooldown)",
    category="repair"
)
def can_apply_repair(ctx: PolicyContext) -> bool:
    """
    Thin gate for the repair cascade overlay.

    Only checks suppression (cooldown). Does NOT enumerate individual
    repair signals — that's the overlay's job. This prevents gate/overlay
    signal desync when new repair conditions are added.
    """
    return not ctx.stall_guard_cooldown


@policy_condition(
    "confidence_decreasing",
    description="Check if confidence trend is decreasing",
    category="repair"
)
def confidence_decreasing(ctx: PolicyContext) -> bool:
    """Returns True if confidence is decreasing."""
    return ctx.confidence_trend == "decreasing"


@policy_condition(
    "high_unclear_count",
    description="Check if unclear count is high (3+)",
    category="repair"
)
def high_unclear_count(ctx: PolicyContext) -> bool:
    """Returns True if unclear count is 3 or more."""
    return ctx.unclear_count >= 3


# =============================================================================
# OBJECTION CONDITIONS - Repeated objections, escalation
# =============================================================================

@policy_condition(
    "has_repeated_objections",
    description="Check if there are repeated objection types",
    category="objection"
)
def has_repeated_objections(ctx: PolicyContext) -> bool:
    """
    Returns True if there are repeated objection types.

    This indicates client is bringing up same objections multiple times.
    """
    return len(ctx.repeated_objection_types) > 0


@policy_condition(
    "is_current_intent_objection",
    description="Check if current primary intent is objection",
    category="objection"
)
def is_current_intent_objection(ctx: PolicyContext) -> bool:
    """
    Returns True only when current turn intent is objection intent.

    Strict intent-aware gate: historical objections alone are not enough.
    """
    return bool(ctx.current_intent and ctx.current_intent in OBJECTION_INTENTS)


@policy_condition(
    "total_objections_3_plus",
    description="Check if total objections is 3 or more",
    category="objection"
)
def total_objections_3_plus(ctx: PolicyContext) -> bool:
    """
    Returns True if total objections >= max_consecutive_objections.

    At this point, escalation tactics should be considered.
    Uses configurable limit from constants.yaml.
    """
    return ctx.total_objections >= ctx.max_consecutive_objections


@policy_condition(
    "total_objections_5_plus",
    description="Check if total objections >= max_total_objections (configurable)",
    category="objection"
)
def total_objections_5_plus(ctx: PolicyContext) -> bool:
    """Returns True if total objections >= max_total_objections (from constants.yaml)."""
    return ctx.total_objections >= ctx.max_total_objections


@policy_condition(
    "should_escalate_objection",
    description="Check if objection handling should escalate (configurable)",
    category="objection"
)
def should_escalate_objection(ctx: PolicyContext) -> bool:
    """
    Returns True if we should escalate objection handling.

    Escalate when: total >= max_consecutive_objections OR repeated objection types.
    Uses configurable limit from constants.yaml.
    """
    return ctx.total_objections >= ctx.max_consecutive_objections or len(ctx.repeated_objection_types) > 0


@policy_condition(
    "has_price_objection_repeat",
    description="Check if price objection was repeated",
    category="objection"
)
def has_price_objection_repeat(ctx: PolicyContext) -> bool:
    """Returns True if price objection was repeated."""
    return any("price" in obj.lower() for obj in ctx.repeated_objection_types)


@policy_condition(
    "has_competitor_objection_repeat",
    description="Check if competitor objection was repeated",
    category="objection"
)
def has_competitor_objection_repeat(ctx: PolicyContext) -> bool:
    """Returns True if competitor objection was repeated."""
    return any("competitor" in obj.lower() for obj in ctx.repeated_objection_types)


# =============================================================================
# BREAKTHROUGH CONDITIONS - Breakthrough detection and window
# =============================================================================

@policy_condition(
    "has_breakthrough",
    description="Check if breakthrough was detected",
    category="breakthrough"
)
def has_breakthrough(ctx: PolicyContext) -> bool:
    """
    Returns True if a breakthrough was detected.

    Breakthrough is a positive shift in client engagement/interest.
    """
    return ctx.has_breakthrough


@policy_condition(
    "in_breakthrough_window",
    description="Check if within breakthrough window (1-3 turns after)",
    category="breakthrough"
)
def in_breakthrough_window(ctx: PolicyContext) -> bool:
    """
    Returns True if within the breakthrough CTA window.

    The window is 1-3 turns after breakthrough detection.
    This is the optimal time for a soft CTA.
    """
    if not ctx.has_breakthrough:
        return False
    if ctx.turns_since_breakthrough is None:
        return False
    return 1 <= ctx.turns_since_breakthrough <= 3


@policy_condition(
    "breakthrough_just_happened",
    description="Check if breakthrough just happened (this turn or last)",
    category="breakthrough"
)
def breakthrough_just_happened(ctx: PolicyContext) -> bool:
    """Returns True if breakthrough happened very recently."""
    if not ctx.has_breakthrough:
        return False
    if ctx.turns_since_breakthrough is None:
        return False
    return ctx.turns_since_breakthrough <= 1


@policy_condition(
    "should_add_soft_cta",
    description="Check if a soft CTA should be added",
    category="breakthrough"
)
def should_add_soft_cta(ctx: PolicyContext) -> bool:
    """
    Returns True if a soft CTA should be added.

    Conditions: in breakthrough window AND momentum is positive or neutral.
    """
    if not in_breakthrough_window(ctx):
        return False
    return ctx.momentum_direction != "negative"


# =============================================================================
# MOMENTUM CONDITIONS - Momentum and engagement
# =============================================================================

@policy_condition(
    "momentum_positive",
    description="Check if momentum is positive",
    category="momentum"
)
def momentum_positive(ctx: PolicyContext) -> bool:
    """Returns True if momentum direction is positive."""
    return ctx.momentum_direction == "positive"


@policy_condition(
    "momentum_negative",
    description="Check if momentum is negative",
    category="momentum"
)
def momentum_negative(ctx: PolicyContext) -> bool:
    """Returns True if momentum direction is negative."""
    return ctx.momentum_direction == "negative"


@policy_condition(
    "momentum_neutral",
    description="Check if momentum is neutral",
    category="momentum"
)
def momentum_neutral(ctx: PolicyContext) -> bool:
    """Returns True if momentum direction is neutral."""
    return ctx.momentum_direction == "neutral"


@policy_condition(
    "engagement_high",
    description="Check if engagement level is high",
    category="momentum"
)
def engagement_high(ctx: PolicyContext) -> bool:
    """Returns True if engagement level is high."""
    return ctx.engagement_level == "high"


@policy_condition(
    "engagement_low",
    description="Check if engagement level is low or disengaged",
    category="momentum"
)
def engagement_low(ctx: PolicyContext) -> bool:
    """Returns True if engagement level is low or disengaged."""
    return ctx.engagement_level in ("low", "disengaged")


@policy_condition(
    "engagement_declining",
    description="Check if engagement trend is declining",
    category="momentum"
)
def engagement_declining(ctx: PolicyContext) -> bool:
    """Returns True if engagement trend is declining."""
    return ctx.engagement_trend == "declining"


@policy_condition(
    "is_progressing",
    description="Check if conversation is progressing through funnel",
    category="momentum"
)
def is_progressing(ctx: PolicyContext) -> bool:
    """Returns True if conversation is progressing."""
    return ctx.is_progressing


@policy_condition(
    "is_regressing",
    description="Check if conversation is regressing",
    category="momentum"
)
def is_regressing(ctx: PolicyContext) -> bool:
    """Returns True if conversation is regressing."""
    return ctx.is_regressing


@policy_condition(
    "should_be_conservative",
    description="Check if conservative mode should be applied",
    category="momentum"
)
def should_be_conservative(ctx: PolicyContext) -> bool:
    """
    Returns True if conservative mode should be applied.

    Conservative when: confidence decreasing OR momentum negative.
    """
    return ctx.confidence_trend == "decreasing" or ctx.momentum_direction == "negative"


@policy_condition(
    "can_accelerate",
    description="Check if we can accelerate towards close",
    category="momentum"
)
def can_accelerate(ctx: PolicyContext) -> bool:
    """
    Returns True if we can accelerate.

    Accelerate when: positive momentum AND progressing.
    """
    return ctx.momentum_direction == "positive" and ctx.is_progressing


# =============================================================================
# GUARD CONDITIONS - Frustration and intervention
# =============================================================================

@policy_condition(
    "has_guard_intervention",
    description="Check if guard intervention or pre-intervention is active",
    category="guard"
)
def has_guard_intervention(ctx: PolicyContext) -> bool:
    """
    Returns True if guard intervention OR pre-intervention is active.

    Pre-intervention is triggered at WARNING frustration level (5-6) with
    certain conditions (RUSHED tone, multiple signals), before full guard
    intervention at HIGH level (7+).
    """
    return ctx.guard_intervention is not None or ctx.pre_intervention_triggered


@policy_condition(
    "has_pre_intervention",
    description="Check if pre-intervention is triggered (WARNING level frustration)",
    category="guard"
)
def has_pre_intervention(ctx: PolicyContext) -> bool:
    """
    Returns True if pre-intervention is triggered.

    Pre-intervention occurs at WARNING frustration level (5-6) when certain
    conditions are met (RUSHED tone, multiple frustration signals).
    This is an early warning before full guard intervention at HIGH level (7+).
    """
    return ctx.pre_intervention_triggered


@policy_condition(
    "frustration_high",
    description=f"Check if frustration level is moderate+ ({FRUSTRATION_MODERATE}+)",
    category="guard"
)
def frustration_high(ctx: PolicyContext) -> bool:
    """Returns True if frustration level is moderate or higher."""
    return is_frustration_moderate(ctx.frustration_level)


@policy_condition(
    "frustration_critical",
    description=f"Check if frustration level is warning+ ({FRUSTRATION_WARNING}+)",
    category="guard"
)
def frustration_critical(ctx: PolicyContext) -> bool:
    """Returns True if frustration level is warning or higher."""
    return is_frustration_warning(ctx.frustration_level)


@policy_condition(
    "needs_empathy",
    description="Check if response should include empathy",
    category="guard"
)
def needs_empathy(ctx: PolicyContext) -> bool:
    """
    Returns True if response should include empathy.

    When frustration is elevated+ or there are repeated objections.
    """
    return is_frustration_elevated(ctx.frustration_level) or len(ctx.repeated_objection_types) > 0


# =============================================================================
# STATE CONDITIONS - State and action checks
# =============================================================================

@policy_condition(
    "is_overlay_allowed",
    description="Check if overlay is allowed for current state",
    category="state"
)
def is_overlay_allowed(ctx: PolicyContext) -> bool:
    """Returns True if overlay is allowed for current state."""
    return ctx.state not in PROTECTED_STATES


@policy_condition(
    "is_protected_state",
    description="Check if current state is protected from overlays",
    category="state"
)
def is_protected_state(ctx: PolicyContext) -> bool:
    """Returns True if current state is protected."""
    return ctx.state in PROTECTED_STATES


@policy_condition(
    "is_aggressive_action",
    description="Check if current action is aggressive",
    category="state"
)
def is_aggressive_action(ctx: PolicyContext) -> bool:
    """
    Returns True if current action is aggressive.

    Aggressive actions push towards close/demo.
    """
    return ctx.current_action in AGGRESSIVE_ACTIONS


@policy_condition(
    "should_soften_action",
    description="Check if current action should be softened",
    category="state"
)
def should_soften_action(ctx: PolicyContext) -> bool:
    """
    Returns True if current action should be softened.

    Soften when: aggressive action AND (conservative mode OR low engagement).
    """
    if ctx.current_action not in AGGRESSIVE_ACTIONS:
        return False
    return should_be_conservative(ctx) or engagement_low(ctx)


@policy_condition(
    "is_spin_state",
    description="Check if current state is a SPIN state",
    category="state"
)
def is_spin_state(ctx: PolicyContext) -> bool:
    """Returns True if in a SPIN state."""
    return ctx.state.startswith("spin_")


@policy_condition(
    "is_presentation_state",
    description="Check if in presentation state",
    category="state"
)
def is_presentation_state(ctx: PolicyContext) -> bool:
    """Returns True if in presentation state."""
    return ctx.state == "presentation"


@policy_condition(
    "is_handle_objection_state",
    description="Check if in handle_objection state",
    category="state"
)
def is_handle_objection_state(ctx: PolicyContext) -> bool:
    """Returns True if in handle_objection state."""
    return ctx.state == "handle_objection"


# =============================================================================
# COMBINED CONDITIONS - Complex conditions for policy decisions
# =============================================================================

@policy_condition(
    "should_apply_repair_overlay",
    description="Check if repair overlay should be applied",
    category="combined"
)
def should_apply_repair_overlay(ctx: PolicyContext) -> bool:
    """
    Returns True if repair overlay should be applied.

    Requires: overlay allowed AND needs repair.
    """
    return is_overlay_allowed(ctx) and needs_repair(ctx)


@policy_condition(
    "should_apply_objection_overlay",
    description="Check if objection overlay should be applied",
    category="combined"
)
def should_apply_objection_overlay(ctx: PolicyContext) -> bool:
    """
    Returns True if objection overlay should be applied.

    Requires ALL:
    - overlay allowed
    - repeated objection signal exists
    - current primary intent is objection
    """
    return (
        is_overlay_allowed(ctx)
        and has_repeated_objections(ctx)
        and is_current_intent_objection(ctx)
    )


@policy_condition(
    "should_apply_breakthrough_overlay",
    description="Check if breakthrough overlay should be applied",
    category="combined"
)
def should_apply_breakthrough_overlay(ctx: PolicyContext) -> bool:
    """
    Returns True if breakthrough overlay should be applied.

    Requires: overlay allowed AND in breakthrough window.
    """
    return is_overlay_allowed(ctx) and in_breakthrough_window(ctx)


@policy_condition(
    "should_apply_conservative_overlay",
    description="Check if conservative overlay should be applied",
    category="combined"
)
def should_apply_conservative_overlay(ctx: PolicyContext) -> bool:
    """
    Returns True if conservative overlay should be applied.

    Requires: overlay allowed AND aggressive action AND conservative mode.
    """
    return (
        is_overlay_allowed(ctx) and
        is_aggressive_action(ctx) and
        should_be_conservative(ctx)
    )


@policy_condition(
    "has_effective_action_history",
    description="Check if we have action effectiveness data",
    category="combined"
)
def has_effective_action_history(ctx: PolicyContext) -> bool:
    """Returns True if we have action effectiveness data."""
    return ctx.most_effective_action is not None or ctx.least_effective_action is not None


@policy_condition(
    "should_avoid_least_effective",
    description="Check if current action matches least effective",
    category="combined"
)
def should_avoid_least_effective(ctx: PolicyContext) -> bool:
    """
    Returns True if current action matches least effective action.

    When true, we should consider using a different action.
    """
    if ctx.least_effective_action is None:
        return False
    return ctx.current_action == ctx.least_effective_action


# =============================================================================
# PRICE QUESTION CONDITION (НОВОЕ) - Вопросы о цене
# =============================================================================

@policy_condition(
    "is_price_question",
    description="Check if client is asking about price",
    category="price"
)
def is_price_question(ctx: PolicyContext) -> bool:
    """
    Checks THREE sources:
    1. Primary intent (current turn)
    2. Secondary intents (compound message detection)
    3. Repeated question (historical — catches classifier misses)

    Uses INTENT_CATEGORIES from constants.yaml as Single Source of Truth.
    """
    from src.yaml_config.constants import INTENT_CATEGORIES
    price_intents = set(INTENT_CATEGORIES.get("price_related", []))
    if ctx.current_intent and ctx.current_intent in price_intents:
        return True
    if ctx.secondary_intents:
        if price_intents & set(ctx.secondary_intents):
            return True
    # repeated_question fallback — require current-turn price signal
    if ctx.repeated_question and ctx.repeated_question in price_intents:
        from src.yaml_config.constants import PRICE_KEYWORDS_STRICT
        msg = (ctx.last_user_message or '').lower()
        keywords = PRICE_KEYWORDS_STRICT or ["цена", "тариф", "стоимость", "сколько стоит"]
        if msg and any(kw in msg for kw in keywords):
            return True
    return False


# =============================================================================
# ANSWERABLE QUESTION CONDITION - Any known question type
# =============================================================================

@policy_condition(
    "is_answerable_question",
    description="Check if client asks any known answerable question",
    category="question"
)
def is_answerable_question(ctx: PolicyContext) -> bool:
    """Universal version of is_price_question for ALL question types."""
    from src.yaml_config.constants import INTENT_CATEGORIES
    answerable = (
        set(INTENT_CATEGORIES.get("question", []))
        | set(INTENT_CATEGORIES.get("price_related", []))
    )
    if ctx.current_intent and ctx.current_intent in answerable:
        return True
    if ctx.secondary_intents:
        if answerable & set(ctx.secondary_intents):
            return True
    if ctx.repeated_question and ctx.repeated_question in answerable:
        return True
    return False


# =============================================================================
# STALL DETECTION - Same state N turns without progress
# =============================================================================

@policy_condition(
    "is_stalled",
    description="Detect flow state stall: same state N turns without data progress",
    category="repair"
)
def is_stalled(ctx: PolicyContext) -> bool:
    """
    Detect flow state stall: same state N turns without data progress.

    Different from is_stuck (which detects repeated unclear intents).
    Stall means the dialog is running but not progressing — user asks
    off-topic questions (price_question, request_brevity) that get handled
    by rules but don't cause state transitions.

    Uses consecutive_same_state from ContextWindow.
    """
    from src.yaml_config.constants import _constants
    config = _constants.get("stall_detection", {})
    if not config.get("enabled", True):
        return False
    threshold = config.get("stall_threshold", 3)
    exempt = set(config.get("exempt_states", []))
    if ctx.state in exempt:
        return False
    return (ctx.consecutive_same_state >= threshold
            and not ctx.is_progressing
            and not ctx.has_extracted_data)


# Export all condition functions for testing
__all__ = [
    # Repair conditions
    "is_stuck",
    "has_oscillation",
    "has_repeated_question",
    "needs_repair",
    "can_apply_repair",
    "confidence_decreasing",
    "high_unclear_count",
    "is_stalled",
    # Objection conditions
    "has_repeated_objections",
    "is_current_intent_objection",
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
    "has_pre_intervention",
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
    # Price question condition (НОВОЕ)
    "is_price_question",
    # Answerable question condition
    "is_answerable_question",
]
