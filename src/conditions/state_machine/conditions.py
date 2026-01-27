"""
StateMachine Conditions.

This module provides all condition functions for the StateMachine domain.
Conditions are organized by category:
- data: Check collected_data fields
- intent: Check intent history and counters
- state: Check dialogue state

Part of Phase 2: StateMachine Domain (ARCHITECTURE_UNIFIED_PLAN.md)
"""

from src.conditions.state_machine.context import EvaluatorContext
from src.conditions.state_machine.registry import sm_condition

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
    description="Check if contact information has been collected (any format, no strict validation)",
    requires_fields={"email", "phone", "contact", "contact_info"},
    category="data"
)
def has_contact_info(ctx: EvaluatorContext) -> bool:
    """
    Returns True if email, phone, or contact is available in any format.

    NOTE: This is a lenient check that only verifies presence, not validity.
    For strict validation, use `has_validated_contact`.

    Used for backward compatibility and cases where presence is sufficient.
    Checks both top-level fields and nested contact_info dict.
    """
    # Check top-level fields
    if ctx.collected_data.get("email") or ctx.collected_data.get("phone") or ctx.collected_data.get("contact"):
        return True

    # Check contact_info field
    contact_info = ctx.collected_data.get("contact_info")

    # contact_info can be a string (direct phone/email from DataExtractor)
    if isinstance(contact_info, str) and contact_info.strip():
        return True

    # Or a dict with nested fields
    if isinstance(contact_info, dict):
        return bool(contact_info.get("email") or contact_info.get("phone") or contact_info.get("name"))

    return False


@sm_condition(
    "has_validated_contact",
    description="Check if contact information has been collected AND validated",
    requires_fields={"email", "phone", "contact", "contact_info"},
    category="data"
)
def has_validated_contact(ctx: EvaluatorContext) -> bool:
    """
    Returns True only if valid email or phone is present.

    Unlike `has_contact_info`, this condition performs strict validation:
    - Email must match standard RFC pattern
    - Phone must be a valid Russian number (+7/8 format with valid prefix)
    - Filters out false positives like sequential digits (1234567890)

    Use this condition for:
    - ready_for_close decisions
    - Success state transitions
    - Any case where contact quality matters

    Example:
        "demo_request: [when: has_validated_contact, then: success]"
    """
    from src.conditions.state_machine.contact_validator import has_valid_contact
    return has_valid_contact(ctx.collected_data)


@sm_condition(
    "has_valid_email",
    description="Check if a valid email address has been collected",
    requires_fields={"email", "contact_info"},
    category="data"
)
def has_valid_email(ctx: EvaluatorContext) -> bool:
    """
    Returns True if a valid email address is present.

    Validation includes:
    - Standard email format (user@domain.tld)
    - Reasonable length constraints
    - Normalization to lowercase

    Checks both top-level email and contact_info fields.
    """
    from src.conditions.state_machine.contact_validator import ContactValidator
    validator = ContactValidator()

    # Check top-level email
    email = ctx.collected_data.get("email")
    if email and validator.validate_email(email).is_valid:
        return True

    # Check contact_info
    contact_info = ctx.collected_data.get("contact_info")
    if isinstance(contact_info, str) and '@' in contact_info:
        return validator.validate_email(contact_info).is_valid
    if isinstance(contact_info, dict):
        email = contact_info.get("email")
        if email and validator.validate_email(email).is_valid:
            return True

    return False


@sm_condition(
    "has_valid_phone",
    description="Check if a valid Russian phone number has been collected",
    requires_fields={"phone", "contact_info"},
    category="data"
)
def has_valid_phone(ctx: EvaluatorContext) -> bool:
    """
    Returns True if a valid Russian phone number is present.

    Validation includes:
    - Format: +7/8 with valid structure, or 10-digit local
    - Valid mobile prefix (900-999) or city code (495, 812, etc.)
    - Filters out invalid patterns (sequential, repeated digits)

    Checks both top-level phone and contact_info fields.
    """
    from src.conditions.state_machine.contact_validator import ContactValidator
    validator = ContactValidator()

    # Check top-level phone
    phone = ctx.collected_data.get("phone")
    if phone and validator.validate_phone(phone).is_valid:
        return True

    # Check contact_info
    contact_info = ctx.collected_data.get("contact_info")
    if isinstance(contact_info, str) and '@' not in contact_info:
        return validator.validate_phone(contact_info).is_valid
    if isinstance(contact_info, dict):
        phone = contact_info.get("phone")
        if phone and validator.validate_phone(phone).is_valid:
            return True

    return False


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
    description="Check if price-related intents repeated 3+ times consecutively",
    category="intent"
)
def price_repeated_3x(ctx: EvaluatorContext) -> bool:
    """
    Returns True if price-related intents have been asked 3+ times in a row.

    This triggers escalation to answer_with_price_range.

    FIX: Now uses category_streak("price_related") instead of intent_streak("price_question").
    This correctly tracks ALL price-related intents:
    - price_question, pricing_details, cost_inquiry, discount_request,
    - payment_terms, pricing_comparison, budget_question

    Bug fixed: Previously streak was reset when client asked "и скидка есть?"
    (discount_request) after "а какая цена?" (price_question), causing infinite
    deflect loop because streak never reached 3.
    """
    return ctx.get_category_streak("price_related") >= 3


@sm_condition(
    "price_repeated_2x",
    description="Check if price-related intents repeated 2+ times consecutively",
    category="intent"
)
def price_repeated_2x(ctx: EvaluatorContext) -> bool:
    """
    Returns True if price-related intents have been asked 2+ times in a row.

    FIX: Now uses category_streak("price_related") instead of intent_streak("price_question").
    See price_repeated_3x docstring for detailed bug description.
    """
    return ctx.get_category_streak("price_related") >= 2


@sm_condition(
    "technical_question_repeated_2x",
    description="Check if technical questions repeated 2+ times consecutively",
    category="intent"
)
def technical_question_repeated_2x(ctx: EvaluatorContext) -> bool:
    """
    Returns True if technical questions have been asked 2+ times in a row.

    This triggers offer_documentation_link action.

    FIX: Now uses category_streak("technical_question") instead of intent_streak("question_technical").
    This correctly tracks ALL technical question intents:
    - question_technical, question_security, question_support, question_implementation,
    - question_training, question_updates, question_mobile, question_offline,
    - question_data_migration, question_customization, question_reports, question_automation,
    - question_scalability

    Bug fixed: Previously streak was reset when client asked about different technical topics
    (e.g., question_security after question_technical), preventing the documentation link offer.
    """
    return ctx.get_category_streak("technical_question") >= 2


@sm_condition(
    "objection_limit_reached",
    description="Check if objection limit has been reached (configurable via constants.yaml)",
    category="intent"
)
def objection_limit_reached(ctx: EvaluatorContext) -> bool:
    """
    Returns True if objection limit has been reached.

    Limits are configurable via constants.yaml:
    - max_consecutive_objections (default: 3)
    - max_total_objections (default: 5)

    Triggers transition to soft_close.
    """
    consecutive = ctx.get_category_streak("objection")
    total = ctx.get_category_total("objection")

    # Use limits from context (populated from YAML config)
    return (
        consecutive >= ctx.max_consecutive_objections
        or total >= ctx.max_total_objections
    )


@sm_condition(
    "objection_consecutive_3x",
    description="Check if consecutive objection limit reached (configurable via constants.yaml)",
    category="intent"
)
def objection_consecutive_3x(ctx: EvaluatorContext) -> bool:
    """Returns True if consecutive objections >= max_consecutive_objections."""
    return ctx.get_category_streak("objection") >= ctx.max_consecutive_objections


@sm_condition(
    "objection_total_5x",
    description="Check if total objection limit reached (configurable via constants.yaml)",
    category="intent"
)
def objection_total_5x(ctx: EvaluatorContext) -> bool:
    """Returns True if total objections >= max_total_objections."""
    return ctx.get_category_total("objection") >= ctx.max_total_objections


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


@sm_condition(
    "unclear_consecutive_3x",
    description="Check if unclear intent repeated 3+ times consecutively",
    category="intent"
)
def unclear_consecutive_3x(ctx: EvaluatorContext) -> bool:
    """
    Returns True if unclear has been returned 3+ times in a row.

    This triggers escape from handle_objection to presentation,
    preventing infinite stuck loops when classifier can't determine intent.

    Part of Objection Stuck Fix (OBJECTION_STUCK_FIX_PLAN.md)
    """
    return ctx.get_intent_streak("unclear") >= 3


@sm_condition(
    "objection_repeated",
    description="Check if same objection type repeated 2+ times consecutively",
    category="intent"
)
def objection_repeated(ctx: EvaluatorContext) -> bool:
    """
    Returns True if same objection intent has been repeated 2+ times.

    If user repeats the exact same objection, they're not convinced by
    our handling and we should escalate to soft_close rather than
    continue pushing.

    Part of Objection Stuck Fix (OBJECTION_STUCK_FIX_PLAN.md)
    """
    if not ctx.current_intent:
        return False

    # Get streak for current specific intent (not category)
    return ctx.get_intent_streak(ctx.current_intent) >= 2


@sm_condition(
    "objection_loop_escape",
    description="Check if stuck in objection loop (3+ consecutive OR total approaching limit)",
    category="intent"
)
def objection_loop_escape(ctx: EvaluatorContext) -> bool:
    """
    Returns True if client is stuck in objection loop and should escape to entry_state.

    This condition is designed for the zero phase coverage bug fix:
    - tire_kicker (90% objection probability) and aggressive (70%) personas
    - Express objections BEFORE entering any phase
    - _state_before_objection = "greeting" (no phase)
    - Never give positive intents → stuck in handle_objection loop
    - Need to force exit to entry_state to start sales phases

    Triggers when:
    1. Current state is handle_objection
    2. Current intent is an objection
    3. EITHER:
       a) 3+ consecutive objections without positive response (original)
       b) Total objections approaching limit (max_total - 1) (FIX)

    Case 3b fixes the meta-intent streak breaking bug:
    - Meta-intents (request_brevity, etc.) reset consecutive streak to 0
    - But total objections keep accumulating
    - Without this fix, objection_limit_reached fires at total=max_total
      → soft_close with 0% coverage
    - With this fix, escape fires at total=max_total-1, one step before limit
      → entry_state, giving client a chance to enter sales phases

    In YAML transition order, objection_loop_escape is checked BEFORE
    objection_limit_reached, so escape wins when both would be true.

    Part of Zero Phase Coverage Fix (OBJECTION_STUCK_FIX_PLAN.md)
    """
    # Check current state
    if ctx.state != "handle_objection":
        return False

    # Check if current intent is objection
    from src.conditions.state_machine.context import INTENT_CATEGORIES
    if ctx.current_intent not in INTENT_CATEGORIES.get("objection", []):
        return False

    consecutive = ctx.get_category_streak("objection")
    total = ctx.get_category_total("objection")

    # CASE A: Consecutive-based escape (original)
    # 3+ consecutive objections without positive response
    if consecutive >= 3:
        return True

    # CASE B: Total-based escape (FIX for meta-intent streak breaking)
    # Meta-intents like request_brevity break consecutive streak but don't
    # reduce total. Fire escape when total reaches max_total - 1 to ensure
    # escape fires BEFORE objection_limit_reached (which fires at max_total).
    # This prevents the scenario where consecutive never reaches 3 but
    # total reaches 5 → objection_limit_reached → soft_close → 0% coverage.
    if total >= ctx.max_total_objections - 1:
        return True

    return False


# =============================================================================
# COUNT-BASED CONDITIONS (Lost Question Fix)
# =============================================================================
# FIX: Streak-based условия сбрасываются при чередовании интентов.
# Count-based условия считают ОБЩЕЕ количество, не последовательное.
#
# Пример проблемы:
#   Turn 1: "100 человек. Сколько стоит?" → info_provided (streak=0 для price)
#   Turn 2: "Бюджет 500к. Не тяни, давай по делу" → info_provided (streak=0)
#   Turn 3: "Цену скажи!" → price_question (streak=1, не 3!)
#
# Count-based условие поймает, что price_question был 3 раза в истории.
# =============================================================================

@sm_condition(
    "price_total_count_3x",
    description="Check if price-related intents occurred 3+ times TOTAL in conversation",
    category="intent"
)
def price_total_count_3x(ctx: EvaluatorContext) -> bool:
    """
    Returns True if price-related intents have been asked 3+ times TOTAL.

    FIX: Now uses get_category_total("price_related") instead of get_intent_count.
    This ensures consistency with:
    - price_repeated_3x (uses category_streak)
    - constants.yaml price_related category (Single Source of Truth)

    This is more reliable than streak-based conditions because:
    - Streak resets when ANY other intent occurs
    - In composite messages, price_question might not be primary
    - Count tracks ALL occurrences regardless of order

    Use this for triggering answer_with_price_range.
    """
    return ctx.get_category_total("price_related") >= 3


@sm_condition(
    "price_total_count_2x",
    description="Check if price-related intents occurred 2+ times TOTAL in conversation",
    category="intent"
)
def price_total_count_2x(ctx: EvaluatorContext) -> bool:
    """
    Returns True if price-related intents have been asked 2+ times TOTAL.

    FIX: Now uses get_category_total("price_related") instead of get_intent_count.
    This ensures consistency with:
    - price_repeated_2x (uses category_streak)
    - constants.yaml price_related category (Single Source of Truth)

    Softer trigger than 3x - useful for showing willingness to discuss price
    while still trying to gather qualifying info.
    """
    return ctx.get_category_total("price_related") >= 2


@sm_condition(
    "question_total_count_2x",
    description="Check if any question intent occurred 2+ times TOTAL",
    category="intent"
)
def question_total_count_2x(ctx: EvaluatorContext) -> bool:
    """
    Returns True if current question intent has been asked 2+ times TOTAL.

    FIX: Now uses get_intent_total instead of get_intent_count.

    Works for any question_* intent. Useful for triggering detailed answers
    when user shows persistent interest in a topic.
    """
    if not ctx.current_intent or not ctx.current_intent.startswith("question_"):
        return False
    return ctx.get_intent_total(ctx.current_intent) >= 2


@sm_condition(
    "unclear_total_count_3x",
    description="Check if unclear occurred 3+ times TOTAL in conversation",
    category="intent"
)
def unclear_total_count_3x(ctx: EvaluatorContext) -> bool:
    """
    Returns True if unclear has been returned 3+ times TOTAL.

    FIX: Now uses get_intent_total instead of get_intent_count.

    Total count is more reliable for detecting communication issues
    than streak-based which resets on any clear classification.
    """
    return ctx.get_intent_total("unclear") >= 3


@sm_condition(
    "has_secondary_price_question",
    description="Check if secondary_intents contains price_question",
    category="intent"
)
def has_secondary_price_question(ctx: EvaluatorContext) -> bool:
    """
    Returns True if secondary_intents contains price_question.

    This enables detection of price questions even when they were
    lost in composite message classification.

    Works with SecondaryIntentDetectionLayer.
    Now uses ctx.secondary_intents field directly (wired through ContextEnvelope).
    """
    return bool(ctx.secondary_intents and "price_question" in ctx.secondary_intents)


@sm_condition(
    "has_secondary_question_intent",
    description="Check if secondary_intents contains any question_* intent",
    category="intent"
)
def has_secondary_question_intent(ctx: EvaluatorContext) -> bool:
    """
    Returns True if secondary_intents contains any question intent.

    This is the general check for detecting any lost question
    in composite messages.

    Works with SecondaryIntentDetectionLayer.
    Now uses ctx.secondary_intents field directly (wired through ContextEnvelope).
    """
    if not ctx.secondary_intents:
        return False
    for intent in ctx.secondary_intents:
        if intent.startswith("question_") or intent in {
            "price_question", "demo_request", "callback_request"
        }:
            return True
    return False


@sm_condition(
    "should_answer_question_now",
    description="Check if question should be answered immediately (frustrated or repeated)",
    category="composite"
)
def should_answer_question_now(ctx: EvaluatorContext) -> bool:
    """
    Returns True if we should answer the question immediately.

    FIX: Now uses get_category_total("price_related") instead of get_intent_count.
    This ensures consistency with price_total_count_2x and SSOT principle.

    Combines multiple signals:
    - Elevated frustration (4+)
    - Price-related intents asked 2+ times total
    - Rushed tone ("давай по делу")
    - Secondary question detected

    This is the "should_answer_directly" logic but with total counts.
    """
    # Check frustration
    if ctx.frustration_level >= 4:
        return True

    # Check price-related intent count (uses category for SSOT consistency)
    if ctx.get_category_total("price_related") >= 2:
        return True

    # Check tone
    tone = getattr(ctx, "tone", None)
    if tone and tone.lower() == "rushed":
        return True

    # Check for secondary price question
    if has_secondary_price_question(ctx):
        return True

    return False


# =============================================================================
# STATE CONDITIONS - Check dialogue state and phase
# =============================================================================

@sm_condition(
    "is_phase_state",
    description="Check if current state is a phase state (any flow)",
    category="state"
)
def is_phase_state(ctx: EvaluatorContext) -> bool:
    """Returns True if currently in a phase state."""
    return ctx.is_phase_state


# Legacy alias for backward compatibility
@sm_condition(
    "is_spin_state",
    description="Legacy alias for is_phase_state",
    category="state"
)
def is_spin_state(ctx: EvaluatorContext) -> bool:
    """Legacy alias - returns True if currently in a phase state."""
    return ctx.is_phase_state


@sm_condition(
    "in_phase",
    description="Check if currently in any phase",
    category="state"
)
def in_phase(ctx: EvaluatorContext) -> bool:
    """Returns True if currently in any phase."""
    return ctx.current_phase is not None


# Legacy alias for backward compatibility
@sm_condition(
    "in_spin_phase",
    description="Legacy alias for in_phase",
    category="state"
)
def in_spin_phase(ctx: EvaluatorContext) -> bool:
    """Legacy alias - returns True if currently in any phase."""
    return ctx.current_phase is not None


# Generic phase checker - use with phase name from config
def _in_specific_phase(ctx: EvaluatorContext, phase_name: str) -> bool:
    """Check if in a specific phase by name."""
    return ctx.current_phase == phase_name


# Legacy SPIN phase conditions for backward compatibility
@sm_condition(
    "in_situation_phase",
    description="Check if in situation phase",
    category="state"
)
def in_situation_phase(ctx: EvaluatorContext) -> bool:
    """Returns True if in situation phase."""
    return ctx.current_phase == "situation"


@sm_condition(
    "in_problem_phase",
    description="Check if in problem phase",
    category="state"
)
def in_problem_phase(ctx: EvaluatorContext) -> bool:
    """Returns True if in problem phase."""
    return ctx.current_phase == "problem"


@sm_condition(
    "in_implication_phase",
    description="Check if in implication phase",
    category="state"
)
def in_implication_phase(ctx: EvaluatorContext) -> bool:
    """Returns True if in implication phase."""
    return ctx.current_phase == "implication"


@sm_condition(
    "in_need_payoff_phase",
    description="Check if in need_payoff phase",
    category="state"
)
def in_need_payoff_phase(ctx: EvaluatorContext) -> bool:
    """Returns True if in need_payoff phase."""
    return ctx.current_phase == "need_payoff"


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
    "post_phase",
    description="Check if past all phases (in final states)",
    category="state"
)
def post_phase(ctx: EvaluatorContext) -> bool:
    """Returns True if past all phases (in a known post-phase state)."""
    # Known post-phase states (after all phases are complete)
    POST_PHASE_STATES = {
        "presentation", "close", "handle_objection",
        "soft_close", "success", "failed"
    }
    # Only return True for known post-phase states
    return ctx.state in POST_PHASE_STATES and not ctx.is_phase_state


# Legacy alias
@sm_condition(
    "post_spin_phase",
    description="Legacy alias for post_phase",
    category="state"
)
def post_spin_phase(ctx: EvaluatorContext) -> bool:
    """Legacy alias - returns True if past phases."""
    return post_phase(ctx)


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


@sm_condition(
    "turn_number_gte_3",
    description="Check if turn number is 3 or more (State Loop Fix fallback)",
    category="turn"
)
def turn_number_gte_3(ctx: EvaluatorContext) -> bool:
    """
    Returns True if turn_number >= 3.

    Used as fallback condition for greeting state to prevent
    State Loop bug where bot gets stuck in greeting.
    """
    return ctx.turn_number >= 3


@sm_condition(
    "greeting_too_long",
    description="Check if stuck in greeting state too long (3+ turns)",
    category="turn"
)
def greeting_too_long(ctx: EvaluatorContext) -> bool:
    """
    Returns True if in greeting state for 3+ turns.

    This is a combined condition specifically for State Loop Fix:
    - Current state is greeting
    - Turn number >= 3

    Triggers fallback transition to entry_state.
    """
    return ctx.state == "greeting" and ctx.turn_number >= 3


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
    description="Check if ready to close deal (has VALIDATED contact info)",
    requires_fields={"email", "phone", "contact", "contact_info"},
    category="combined"
)
def ready_for_close(ctx: EvaluatorContext) -> bool:
    """
    Returns True if we have VALIDATED contact info and can close.

    EXPLICIT LOGIC:
    This condition now uses strict validation to ensure contact quality.
    A deal is ready to close only when:
    1. Email is valid (RFC-compliant format), OR
    2. Phone is valid (Russian format with valid prefix)

    Invalid contact patterns are filtered out:
    - Sequential numbers (1234567890)
    - Repeated digits (1111111111)
    - Invalid phone prefixes
    - Malformed email addresses

    Use cases:
    - close state: agreement → success transition
    - close state: demo_request → success transition
    - Any transition requiring verified contact before success

    Note: For backward compatibility or lenient checks, use `has_contact_info`.
    """
    return has_validated_contact(ctx)


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


# =============================================================================
# CONTEXT-AWARE CONDITIONS - Based on ContextEnvelope signals
# =============================================================================

@sm_condition(
    "client_frustrated",
    description=f"Check if client frustration level is moderate+ (>= {FRUSTRATION_MODERATE})",
    category="context"
)
def client_frustrated(ctx: EvaluatorContext) -> bool:
    """
    Returns True if client frustration level is moderate or higher.

    When frustrated, avoid deflecting and be more direct.
    """
    return is_frustration_moderate(ctx.frustration_level)


@sm_condition(
    "client_very_frustrated",
    description=f"Check if client frustration level is warning+ (>= {FRUSTRATION_WARNING})",
    category="context"
)
def client_very_frustrated(ctx: EvaluatorContext) -> bool:
    """
    Returns True if client frustration level is warning or higher.

    Consider offering exit or immediate help.
    """
    return is_frustration_warning(ctx.frustration_level)


@sm_condition(
    "client_stuck",
    description="Check if dialogue is stuck (repeated unclear/same responses)",
    category="context"
)
def client_stuck(ctx: EvaluatorContext) -> bool:
    """
    Returns True if dialogue is stuck.

    Triggers clarification or change of approach.
    """
    return ctx.is_stuck


@sm_condition(
    "client_oscillating",
    description="Check if dialogue is oscillating (back-and-forth pattern)",
    category="context"
)
def client_oscillating(ctx: EvaluatorContext) -> bool:
    """
    Returns True if dialogue is oscillating.

    Triggers summarization and reset.
    """
    return ctx.has_oscillation


@sm_condition(
    "momentum_positive",
    description="Check if conversation momentum is positive",
    category="context"
)
def momentum_positive(ctx: EvaluatorContext) -> bool:
    """Returns True if momentum direction is positive."""
    return ctx.momentum_direction == "positive"


@sm_condition(
    "momentum_negative",
    description="Check if conversation momentum is negative",
    category="context"
)
def momentum_negative(ctx: EvaluatorContext) -> bool:
    """Returns True if momentum direction is negative."""
    return ctx.momentum_direction == "negative"


@sm_condition(
    "momentum_strong_positive",
    description="Check if momentum score is strongly positive (> 0.5)",
    category="context"
)
def momentum_strong_positive(ctx: EvaluatorContext) -> bool:
    """Returns True if momentum score > 0.5."""
    return ctx.momentum > 0.5


@sm_condition(
    "momentum_strong_negative",
    description="Check if momentum score is strongly negative (< -0.5)",
    category="context"
)
def momentum_strong_negative(ctx: EvaluatorContext) -> bool:
    """Returns True if momentum score < -0.5."""
    return ctx.momentum < -0.5


@sm_condition(
    "engagement_high",
    description="Check if client engagement level is high",
    category="context"
)
def engagement_high(ctx: EvaluatorContext) -> bool:
    """Returns True if engagement level is high."""
    return ctx.engagement_level == "high"


@sm_condition(
    "engagement_low",
    description="Check if client engagement level is low",
    category="context"
)
def engagement_low(ctx: EvaluatorContext) -> bool:
    """Returns True if engagement level is low or disengaged."""
    return ctx.engagement_level in ("low", "disengaged")


@sm_condition(
    "has_repeated_question",
    description="Check if there is a repeated question",
    category="context"
)
def has_repeated_question(ctx: EvaluatorContext) -> bool:
    """Returns True if a repeated question was detected."""
    return ctx.repeated_question is not None


@sm_condition(
    "repeated_price_question",
    description="Check if price question is being repeated",
    category="context"
)
def repeated_price_question(ctx: EvaluatorContext) -> bool:
    """Returns True if repeated question is about price."""
    if ctx.repeated_question is None:
        return False
    q = ctx.repeated_question.lower()
    return "price" in q or "pricing" in q


@sm_condition(
    "confidence_declining",
    description="Check if classification confidence is declining",
    category="context"
)
def confidence_declining(ctx: EvaluatorContext) -> bool:
    """Returns True if confidence trend is decreasing."""
    return ctx.confidence_trend == "decreasing"


@sm_condition(
    "many_objections",
    description="Check if there are many objections (3+) in conversation",
    category="context"
)
def many_objections(ctx: EvaluatorContext) -> bool:
    """Returns True if total objections >= 3."""
    return ctx.total_objections >= 3


@sm_condition(
    "breakthrough_detected",
    description="Check if a breakthrough was detected in conversation",
    category="context"
)
def breakthrough_detected(ctx: EvaluatorContext) -> bool:
    """Returns True if breakthrough was detected."""
    return ctx.has_breakthrough


@sm_condition(
    "in_breakthrough_window",
    description="Check if we're in the breakthrough window (1-3 turns after)",
    category="context"
)
def in_breakthrough_window(ctx: EvaluatorContext) -> bool:
    """
    Returns True if in breakthrough window.

    This is the optimal time for soft CTA.
    """
    if not ctx.has_breakthrough:
        return False
    if ctx.turns_since_breakthrough is None:
        return False
    return 1 <= ctx.turns_since_breakthrough <= 3


@sm_condition(
    "guard_intervened",
    description="Check if conversation guard has intervened",
    category="context"
)
def guard_intervened(ctx: EvaluatorContext) -> bool:
    """Returns True if guard intervention is active."""
    return ctx.guard_intervention is not None


@sm_condition(
    "needs_repair",
    description="Check if dialogue needs repair (stuck, oscillating, or repeated question)",
    category="context"
)
def needs_repair(ctx: EvaluatorContext) -> bool:
    """
    Returns True if dialogue needs repair.

    Combined check for stuck, oscillation, or repeated question.
    """
    return ctx.is_stuck or ctx.has_oscillation or ctx.repeated_question is not None


@sm_condition(
    "should_be_careful",
    description="Check if we should be careful (elevated frustration or negative momentum)",
    category="context"
)
def should_be_careful(ctx: EvaluatorContext) -> bool:
    """
    Returns True if we should be more careful with responses.

    Triggers when client is frustrated (elevated+) or momentum is negative.
    """
    return is_frustration_elevated(ctx.frustration_level) or ctx.momentum_direction == "negative"


@sm_condition(
    "can_accelerate",
    description="Check if we can accelerate the flow (positive signals)",
    category="context"
)
def can_accelerate(ctx: EvaluatorContext) -> bool:
    """
    Returns True if we can accelerate the sales flow.

    Requires positive momentum, high engagement, and no frustration.
    """
    return (
        ctx.momentum_direction == "positive" and
        ctx.engagement_level == "high" and
        ctx.frustration_level == 0
    )


@sm_condition(
    "should_answer_directly",
    description="Check if we should answer question directly (frustrated, rushed, or repeated)",
    category="context"
)
def should_answer_directly(ctx: EvaluatorContext) -> bool:
    """
    Returns True if we should answer directly instead of deflecting.

    Triggers when:
    - Client is frustrated (elevated+)
    - Question is repeated
    - Confidence is declining
    - FIX: Client tone is RUSHED (busy/aggressive personas want immediate answers)
    """
    # FIX: RUSHED tone = client wants direct answer NOW, don't deflect
    # This fixes busy/aggressive personas not being served with price/time
    is_rushed = bool(ctx.tone and ctx.tone.lower() == "rushed")

    return (
        is_frustration_elevated(ctx.frustration_level) or
        ctx.repeated_question is not None or
        ctx.confidence_trend == "decreasing" or
        is_rushed
    )


# =============================================================================
# ADDITIONAL CONDITIONS FOR YAML CUSTOM EXPRESSIONS
# =============================================================================

@sm_condition(
    "has_oscillation",
    description="Alias for client_oscillating - dialogue is oscillating",
    category="context"
)
def has_oscillation(ctx: EvaluatorContext) -> bool:
    """Returns True if dialogue is oscillating (back-and-forth pattern)."""
    return ctx.has_oscillation


@sm_condition(
    "has_breakthrough",
    description="Alias for breakthrough_detected - breakthrough was detected",
    category="context"
)
def has_breakthrough(ctx: EvaluatorContext) -> bool:
    """Returns True if breakthrough was detected."""
    return ctx.has_breakthrough


@sm_condition(
    "turns_since_breakthrough_ok",
    description="Check if we're in optimal window after breakthrough (1-3 turns)",
    category="context"
)
def turns_since_breakthrough_ok(ctx: EvaluatorContext) -> bool:
    """Returns True if in breakthrough window (1-3 turns after)."""
    if not ctx.has_breakthrough:
        return False
    if ctx.turns_since_breakthrough is None:
        return False
    return 1 <= ctx.turns_since_breakthrough <= 3


@sm_condition(
    "in_protected_state",
    description="Check if in a protected state (greeting, success)",
    category="state"
)
def in_protected_state(ctx: EvaluatorContext) -> bool:
    """Returns True if in a protected state where aggressive tactics are not allowed."""
    protected_states = {"greeting", "success", "soft_close", "failed"}
    return ctx.state in protected_states


@sm_condition(
    "has_financial_impact",
    description="Check if financial impact data is available",
    requires_fields={"financial_impact", "revenue", "savings"},
    category="data"
)
def has_financial_impact(ctx: EvaluatorContext) -> bool:
    """Returns True if financial impact data is available for ROI calculation."""
    return bool(
        ctx.collected_data.get("financial_impact") or
        ctx.collected_data.get("revenue") or
        ctx.collected_data.get("savings") or
        ctx.collected_data.get("budget")
    )


@sm_condition(
    "unclear_count_high",
    description="Check if there have been many unclear responses (3+)",
    category="context"
)
def unclear_count_high(ctx: EvaluatorContext) -> bool:
    """Returns True if unclear intent count is 3 or higher."""
    return ctx.unclear_count >= 3


@sm_condition(
    "frustration_warning",
    description=f"Check if frustration is elevated (>= {FRUSTRATION_ELEVATED})",
    category="context"
)
def frustration_warning(ctx: EvaluatorContext) -> bool:
    """Returns True if frustration level is elevated or higher."""
    return is_frustration_elevated(ctx.frustration_level)


@sm_condition(
    "has_objection",
    description="Check if current intent is an objection type",
    category="intent"
)
def has_objection(ctx: EvaluatorContext) -> bool:
    """Returns True if current intent is an objection."""
    from src.conditions.state_machine.context import INTENT_CATEGORIES
    return ctx.current_intent in INTENT_CATEGORIES.get("objection", [])


@sm_condition(
    "has_multiple_questions",
    description="Check if client has asked multiple questions (3+ in conversation)",
    category="intent"
)
def has_multiple_questions(ctx: EvaluatorContext) -> bool:
    """Returns True if 3+ question intents in conversation."""
    return ctx.get_category_total("question") >= 3


@sm_condition(
    "engagement_declining",
    description="Check if engagement is declining over time",
    category="context"
)
def engagement_declining(ctx: EvaluatorContext) -> bool:
    """Returns True if engagement trend is declining."""
    # Check momentum as proxy for engagement trend
    return ctx.momentum_direction == "negative" or ctx.momentum < -0.2


@sm_condition(
    "lead_temperature_hot",
    description="Check if lead temperature is HOT",
    category="lead"
)
def lead_temperature_hot(ctx: EvaluatorContext) -> bool:
    """Returns True if lead_temperature is 'hot' or 'HOT'."""
    temp = ctx.collected_data.get("lead_temperature", "").lower()
    return temp == "hot"


@sm_condition(
    "lead_temperature_very_hot",
    description="Check if lead temperature is VERY_HOT",
    category="lead"
)
def lead_temperature_very_hot(ctx: EvaluatorContext) -> bool:
    """Returns True if lead_temperature is 'very_hot' or 'VERY_HOT'."""
    temp = ctx.collected_data.get("lead_temperature", "").lower()
    return temp in ("very_hot", "very hot")


@sm_condition(
    "lead_temperature_cold",
    description="Check if lead temperature is COLD",
    category="lead"
)
def lead_temperature_cold(ctx: EvaluatorContext) -> bool:
    """Returns True if lead_temperature is 'cold' or 'COLD'."""
    temp = ctx.collected_data.get("lead_temperature", "").lower()
    return temp == "cold"


# Export all condition functions for testing
__all__ = [
    # Data conditions
    "has_pricing_data",
    "has_contact_info",
    "has_validated_contact",
    "has_valid_email",
    "has_valid_phone",
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
    "objection_loop_escape",
    "is_current_intent_objection",
    "is_current_intent_positive",
    "is_current_intent_question",
    "is_spin_progress_intent",
    # State conditions (generic)
    "is_phase_state",
    "in_phase",
    "post_phase",
    # State conditions (legacy aliases)
    "is_spin_state",
    "in_spin_phase",
    "post_spin_phase",
    # Phase-specific conditions
    "in_situation_phase",
    "in_problem_phase",
    "in_implication_phase",
    "in_need_payoff_phase",
    # State-specific conditions
    "is_presentation_state",
    "is_close_state",
    "is_greeting_state",
    "is_handle_objection_state",
    "is_soft_close_state",
    "is_success_state",
    "is_terminal_state",
    # Turn conditions
    "is_first_turn",
    "is_early_conversation",
    "is_late_conversation",
    "is_extended_conversation",
    "turn_number_gte_3",
    "greeting_too_long",
    # Combined conditions
    "can_answer_price",
    "should_deflect_price",
    "ready_for_presentation",
    "ready_for_close",
    "can_handle_with_roi",
    # Context-aware conditions
    "client_frustrated",
    "client_very_frustrated",
    "client_stuck",
    "client_oscillating",
    "momentum_positive",
    "momentum_negative",
    "momentum_strong_positive",
    "momentum_strong_negative",
    "engagement_high",
    "engagement_low",
    "has_repeated_question",
    "repeated_price_question",
    "confidence_declining",
    "many_objections",
    "breakthrough_detected",
    "in_breakthrough_window",
    "guard_intervened",
    "needs_repair",
    "should_be_careful",
    "can_accelerate",
    "should_answer_directly",
    # Additional conditions for YAML custom expressions
    "has_oscillation",
    "has_breakthrough",
    "turns_since_breakthrough_ok",
    "in_protected_state",
    "has_financial_impact",
    "unclear_count_high",
    "frustration_warning",
    "has_objection",
    "has_multiple_questions",
    "engagement_declining",
    "lead_temperature_hot",
    "lead_temperature_very_hot",
    "lead_temperature_cold",
]
