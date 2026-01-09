"""
StateMachine Conditions.

This module provides all condition functions for the StateMachine domain.
Conditions are organized by category:
- data: Check collected_data fields
- intent: Check intent history and counters
- state: Check dialogue state

Part of Phase 2: StateMachine Domain (ARCHITECTURE_UNIFIED_PLAN.md)
"""

from src.conditions.state_machine.context import (
    EvaluatorContext,
    SPIN_PHASES,
    SPIN_STATES,
)
from src.conditions.state_machine.registry import sm_condition


# =============================================================================
# DATA CONDITIONS - Check collected_data fields
# =============================================================================

@sm_condition(
    "has_pricing_data",
    description="Check if company_size or users_count has been collected (needed for pricing)",
    requires_fields={"company_size", "users_count"},
    category="data"
)
def has_pricing_data(ctx: EvaluatorContext) -> bool:
    """
    Returns True if either company_size or users_count is available.

    This is the key condition for the price_question fix:
    if pricing data exists, we should answer with facts instead of deflecting.
    """
    return bool(
        ctx.collected_data.get("company_size") or
        ctx.collected_data.get("users_count")
    )


@sm_condition(
    "has_contact_info",
    description="Check if contact information has been collected",
    requires_fields={"email", "phone", "contact"},
    category="data"
)
def has_contact_info(ctx: EvaluatorContext) -> bool:
    """
    Returns True if email, phone, or contact is available.

    Used for demo_request transition to success state.
    """
    return bool(
        ctx.collected_data.get("email") or
        ctx.collected_data.get("phone") or
        ctx.collected_data.get("contact")
    )


@sm_condition(
    "has_company_size",
    description="Check if company_size has been collected",
    requires_fields={"company_size"},
    category="data"
)
def has_company_size(ctx: EvaluatorContext) -> bool:
    """Returns True if company_size is in collected_data."""
    return bool(ctx.collected_data.get("company_size"))


@sm_condition(
    "has_pain_point",
    description="Check if a pain point has been identified",
    requires_fields={"pain_point", "pain_category"},
    category="data"
)
def has_pain_point(ctx: EvaluatorContext) -> bool:
    """Returns True if a pain point has been identified."""
    return bool(
        ctx.collected_data.get("pain_point") or
        ctx.collected_data.get("pain_category")
    )


@sm_condition(
    "has_pain_and_company_size",
    description="Check if both pain point and company size are known",
    requires_fields={"pain_point", "pain_category", "company_size"},
    category="data"
)
def has_pain_and_company_size(ctx: EvaluatorContext) -> bool:
    """
    Returns True if we have both pain point and company size.

    Used for smart objection handling with ROI calculations.
    """
    has_pain = bool(
        ctx.collected_data.get("pain_point") or
        ctx.collected_data.get("pain_category")
    )
    has_size = bool(ctx.collected_data.get("company_size"))
    return has_pain and has_size


@sm_condition(
    "has_competitor_mention",
    description="Check if a competitor has been mentioned",
    requires_fields={"competitor", "current_crm"},
    category="data"
)
def has_competitor_mention(ctx: EvaluatorContext) -> bool:
    """Returns True if a competitor or current CRM has been mentioned."""
    return bool(
        ctx.collected_data.get("competitor") or
        ctx.collected_data.get("current_crm")
    )


@sm_condition(
    "missing_required_data",
    description="Check if there is any required data missing for current state",
    category="data"
)
def missing_required_data(ctx: EvaluatorContext) -> bool:
    """
    Returns True if there are missing required fields.

    Computed from state configuration's required_data.
    """
    return len(ctx.missing_required_data) > 0


@sm_condition(
    "has_all_required_data",
    description="Check if all required data for current state is collected",
    category="data"
)
def has_all_required_data(ctx: EvaluatorContext) -> bool:
    """Returns True if no required data is missing."""
    return len(ctx.missing_required_data) == 0


@sm_condition(
    "has_high_interest",
    description="Check if client has shown high interest",
    requires_fields={"high_interest"},
    category="data"
)
def has_high_interest(ctx: EvaluatorContext) -> bool:
    """Returns True if high_interest flag is set."""
    return bool(ctx.collected_data.get("high_interest"))


@sm_condition(
    "has_desired_outcome",
    description="Check if desired outcome has been identified",
    requires_fields={"desired_outcome"},
    category="data"
)
def has_desired_outcome(ctx: EvaluatorContext) -> bool:
    """Returns True if desired_outcome is in collected_data."""
    return bool(ctx.collected_data.get("desired_outcome"))


# =============================================================================
# INTENT CONDITIONS - Check intent history and counters
# =============================================================================

@sm_condition(
    "price_repeated_3x",
    description="Check if price_question intent repeated 3+ times consecutively",
    category="intent"
)
def price_repeated_3x(ctx: EvaluatorContext) -> bool:
    """
    Returns True if price_question has been asked 3+ times in a row.

    This triggers escalation to answer_with_price_range.
    """
    return ctx.get_intent_streak("price_question") >= 3


@sm_condition(
    "price_repeated_2x",
    description="Check if price_question intent repeated 2+ times consecutively",
    category="intent"
)
def price_repeated_2x(ctx: EvaluatorContext) -> bool:
    """Returns True if price_question has been asked 2+ times in a row."""
    return ctx.get_intent_streak("price_question") >= 2


@sm_condition(
    "technical_question_repeated_2x",
    description="Check if question_technical intent repeated 2+ times",
    category="intent"
)
def technical_question_repeated_2x(ctx: EvaluatorContext) -> bool:
    """
    Returns True if technical question has been asked 2+ times.

    This triggers offer_documentation_link action.
    """
    return ctx.get_intent_streak("question_technical") >= 2


@sm_condition(
    "objection_limit_reached",
    description="Check if objection limit (3 consecutive or 5 total) has been reached",
    category="intent"
)
def objection_limit_reached(ctx: EvaluatorContext) -> bool:
    """
    Returns True if objection limit has been reached.

    Limits:
    - 3 consecutive objections
    - 5 total objections in conversation

    Triggers transition to soft_close.
    """
    consecutive = ctx.get_category_streak("objection")
    total = ctx.get_category_total("objection")

    return consecutive >= 3 or total >= 5


@sm_condition(
    "objection_consecutive_3x",
    description="Check if 3+ consecutive objections",
    category="intent"
)
def objection_consecutive_3x(ctx: EvaluatorContext) -> bool:
    """Returns True if 3+ objections in a row."""
    return ctx.get_category_streak("objection") >= 3


@sm_condition(
    "objection_total_5x",
    description="Check if 5+ total objections in conversation",
    category="intent"
)
def objection_total_5x(ctx: EvaluatorContext) -> bool:
    """Returns True if 5+ total objections."""
    return ctx.get_category_total("objection") >= 5


@sm_condition(
    "is_current_intent_objection",
    description="Check if current intent is an objection",
    category="intent"
)
def is_current_intent_objection(ctx: EvaluatorContext) -> bool:
    """Returns True if current intent is in objection category."""
    from src.conditions.state_machine.context import INTENT_CATEGORIES
    return ctx.current_intent in INTENT_CATEGORIES.get("objection", [])


@sm_condition(
    "is_current_intent_positive",
    description="Check if current intent is positive (agreement, progress, etc.)",
    category="intent"
)
def is_current_intent_positive(ctx: EvaluatorContext) -> bool:
    """Returns True if current intent is in positive category."""
    from src.conditions.state_machine.context import INTENT_CATEGORIES
    return ctx.current_intent in INTENT_CATEGORIES.get("positive", [])


@sm_condition(
    "is_current_intent_question",
    description="Check if current intent is a question",
    category="intent"
)
def is_current_intent_question(ctx: EvaluatorContext) -> bool:
    """Returns True if current intent is in question category."""
    from src.conditions.state_machine.context import INTENT_CATEGORIES
    return ctx.current_intent in INTENT_CATEGORIES.get("question", [])


@sm_condition(
    "is_spin_progress_intent",
    description="Check if current intent indicates SPIN progress",
    category="intent"
)
def is_spin_progress_intent(ctx: EvaluatorContext) -> bool:
    """Returns True if current intent is a SPIN progress intent."""
    from src.conditions.state_machine.context import INTENT_CATEGORIES
    return ctx.current_intent in INTENT_CATEGORIES.get("spin_progress", [])


# =============================================================================
# STATE CONDITIONS - Check dialogue state and phase
# =============================================================================

@sm_condition(
    "is_spin_state",
    description="Check if current state is part of SPIN flow",
    category="state"
)
def is_spin_state(ctx: EvaluatorContext) -> bool:
    """Returns True if currently in a SPIN state."""
    return ctx.is_spin_state


@sm_condition(
    "in_spin_phase",
    description="Check if currently in any SPIN phase",
    category="state"
)
def in_spin_phase(ctx: EvaluatorContext) -> bool:
    """Returns True if currently in any SPIN phase."""
    return ctx.spin_phase is not None and ctx.spin_phase in SPIN_PHASES


@sm_condition(
    "in_situation_phase",
    description="Check if in SPIN Situation phase",
    category="state"
)
def in_situation_phase(ctx: EvaluatorContext) -> bool:
    """Returns True if in Situation phase."""
    return ctx.spin_phase == "situation"


@sm_condition(
    "in_problem_phase",
    description="Check if in SPIN Problem phase",
    category="state"
)
def in_problem_phase(ctx: EvaluatorContext) -> bool:
    """Returns True if in Problem phase."""
    return ctx.spin_phase == "problem"


@sm_condition(
    "in_implication_phase",
    description="Check if in SPIN Implication phase",
    category="state"
)
def in_implication_phase(ctx: EvaluatorContext) -> bool:
    """Returns True if in Implication phase."""
    return ctx.spin_phase == "implication"


@sm_condition(
    "in_need_payoff_phase",
    description="Check if in SPIN Need-Payoff phase",
    category="state"
)
def in_need_payoff_phase(ctx: EvaluatorContext) -> bool:
    """Returns True if in Need-Payoff phase."""
    return ctx.spin_phase == "need_payoff"


@sm_condition(
    "is_presentation_state",
    description="Check if in presentation state",
    category="state"
)
def is_presentation_state(ctx: EvaluatorContext) -> bool:
    """Returns True if in presentation state."""
    return ctx.state == "presentation"


@sm_condition(
    "is_close_state",
    description="Check if in close state",
    category="state"
)
def is_close_state(ctx: EvaluatorContext) -> bool:
    """Returns True if in close state."""
    return ctx.state == "close"


@sm_condition(
    "is_greeting_state",
    description="Check if in greeting state",
    category="state"
)
def is_greeting_state(ctx: EvaluatorContext) -> bool:
    """Returns True if in greeting state."""
    return ctx.state == "greeting"


@sm_condition(
    "is_handle_objection_state",
    description="Check if in handle_objection state",
    category="state"
)
def is_handle_objection_state(ctx: EvaluatorContext) -> bool:
    """Returns True if in handle_objection state."""
    return ctx.state == "handle_objection"


@sm_condition(
    "is_soft_close_state",
    description="Check if in soft_close state",
    category="state"
)
def is_soft_close_state(ctx: EvaluatorContext) -> bool:
    """Returns True if in soft_close state."""
    return ctx.state == "soft_close"


@sm_condition(
    "is_success_state",
    description="Check if in success state",
    category="state"
)
def is_success_state(ctx: EvaluatorContext) -> bool:
    """Returns True if in success state."""
    return ctx.state == "success"


@sm_condition(
    "is_terminal_state",
    description="Check if in a terminal state (success, soft_close, failed)",
    category="state"
)
def is_terminal_state(ctx: EvaluatorContext) -> bool:
    """Returns True if in a terminal state."""
    return ctx.state in ("success", "soft_close", "failed")


@sm_condition(
    "post_spin_phase",
    description="Check if past all SPIN phases (presentation or later)",
    category="state"
)
def post_spin_phase(ctx: EvaluatorContext) -> bool:
    """Returns True if past SPIN phases (in presentation, close, etc.)."""
    non_spin_states = {"presentation", "close", "handle_objection", "soft_close", "success", "failed"}
    return ctx.state in non_spin_states


# =============================================================================
# TURN CONDITIONS - Check turn number
# =============================================================================

@sm_condition(
    "is_first_turn",
    description="Check if this is the first turn",
    category="turn"
)
def is_first_turn(ctx: EvaluatorContext) -> bool:
    """Returns True if turn_number is 0."""
    return ctx.turn_number == 0


@sm_condition(
    "is_early_conversation",
    description="Check if in early conversation (first 3 turns)",
    category="turn"
)
def is_early_conversation(ctx: EvaluatorContext) -> bool:
    """Returns True if turn_number < 3."""
    return ctx.turn_number < 3


@sm_condition(
    "is_late_conversation",
    description="Check if in late conversation (10+ turns)",
    category="turn"
)
def is_late_conversation(ctx: EvaluatorContext) -> bool:
    """Returns True if turn_number >= 10."""
    return ctx.turn_number >= 10


@sm_condition(
    "is_extended_conversation",
    description="Check if conversation is extended (20+ turns)",
    category="turn"
)
def is_extended_conversation(ctx: EvaluatorContext) -> bool:
    """Returns True if turn_number >= 20."""
    return ctx.turn_number >= 20


# =============================================================================
# COMBINED CONDITIONS - Complex conditions combining multiple checks
# =============================================================================

@sm_condition(
    "can_answer_price",
    description="Check if we can answer price question (has data or repeated 3x)",
    requires_fields={"company_size", "users_count"},
    category="combined"
)
def can_answer_price(ctx: EvaluatorContext) -> bool:
    """
    Returns True if we should answer price question directly.

    Either:
    - We have pricing data (company_size or users_count)
    - Price question has been repeated 3+ times
    """
    return has_pricing_data(ctx) or price_repeated_3x(ctx)


@sm_condition(
    "should_deflect_price",
    description="Check if we should deflect price question",
    requires_fields={"company_size", "users_count"},
    category="combined"
)
def should_deflect_price(ctx: EvaluatorContext) -> bool:
    """
    Returns True if we should deflect price question.

    We deflect if:
    - No pricing data yet
    - Price not repeated 3+ times
    - Currently in SPIN phase
    """
    if has_pricing_data(ctx):
        return False
    if price_repeated_3x(ctx):
        return False
    return in_spin_phase(ctx)


@sm_condition(
    "ready_for_presentation",
    description="Check if ready to move to presentation",
    requires_fields={"company_size", "pain_point", "pain_category"},
    category="combined"
)
def ready_for_presentation(ctx: EvaluatorContext) -> bool:
    """
    Returns True if we have enough data for presentation.

    Requires:
    - Company size known
    - Pain point identified
    """
    return has_company_size(ctx) and has_pain_point(ctx)


@sm_condition(
    "ready_for_close",
    description="Check if ready to close (has contact info)",
    requires_fields={"email", "phone", "contact"},
    category="combined"
)
def ready_for_close(ctx: EvaluatorContext) -> bool:
    """Returns True if we have contact info and can close."""
    return has_contact_info(ctx)


@sm_condition(
    "can_handle_with_roi",
    description="Check if we can handle price objection with ROI",
    requires_fields={"pain_point", "pain_category", "company_size"},
    category="combined"
)
def can_handle_with_roi(ctx: EvaluatorContext) -> bool:
    """
    Returns True if we can calculate ROI for price objection handling.

    Requires both pain point and company size to be known.
    """
    return has_pain_and_company_size(ctx)


# Export all condition functions for testing
__all__ = [
    # Data conditions
    "has_pricing_data",
    "has_contact_info",
    "has_company_size",
    "has_pain_point",
    "has_pain_and_company_size",
    "has_competitor_mention",
    "missing_required_data",
    "has_all_required_data",
    "has_high_interest",
    "has_desired_outcome",
    # Intent conditions
    "price_repeated_3x",
    "price_repeated_2x",
    "technical_question_repeated_2x",
    "objection_limit_reached",
    "objection_consecutive_3x",
    "objection_total_5x",
    "is_current_intent_objection",
    "is_current_intent_positive",
    "is_current_intent_question",
    "is_spin_progress_intent",
    # State conditions
    "is_spin_state",
    "in_spin_phase",
    "in_situation_phase",
    "in_problem_phase",
    "in_implication_phase",
    "in_need_payoff_phase",
    "is_presentation_state",
    "is_close_state",
    "is_greeting_state",
    "is_handle_objection_state",
    "is_soft_close_state",
    "is_success_state",
    "is_terminal_state",
    "post_spin_phase",
    # Turn conditions
    "is_first_turn",
    "is_early_conversation",
    "is_late_conversation",
    "is_extended_conversation",
    # Combined conditions
    "can_answer_price",
    "should_deflect_price",
    "ready_for_presentation",
    "ready_for_close",
    "can_handle_with_roi",
]
