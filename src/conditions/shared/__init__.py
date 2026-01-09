"""
Shared conditions that work with BaseContext.

These conditions use only the common fields defined in BaseContext
and can be used across all domains.

Part of Phase 1: Foundation (ARCHITECTURE_UNIFIED_PLAN.md)
"""

from typing import Any, List

from src.conditions.base import BaseContext, SimpleContext
from src.conditions.registry import ConditionRegistry


# Create shared registry that works with any BaseContext-compatible context
shared_registry = ConditionRegistry("shared", SimpleContext)


# =============================================================================
# DATA CONDITIONS - Check collected_data fields
# =============================================================================

@shared_registry.condition(
    "has_collected_data",
    description="Check if any data has been collected",
    category="data"
)
def has_collected_data(ctx: BaseContext) -> bool:
    """Returns True if collected_data is not empty."""
    return bool(ctx.collected_data)


@shared_registry.condition(
    "has_company_size",
    description="Check if company_size has been collected",
    requires_fields={"company_size"},
    category="data"
)
def has_company_size(ctx: BaseContext) -> bool:
    """Returns True if company_size is in collected_data."""
    return bool(ctx.collected_data.get("company_size"))


@shared_registry.condition(
    "has_users_count",
    description="Check if users_count has been collected",
    requires_fields={"users_count"},
    category="data"
)
def has_users_count(ctx: BaseContext) -> bool:
    """Returns True if users_count is in collected_data."""
    return bool(ctx.collected_data.get("users_count"))


@shared_registry.condition(
    "has_pricing_data",
    description="Check if company_size or users_count has been collected",
    requires_fields={"company_size", "users_count"},
    category="data"
)
def has_pricing_data(ctx: BaseContext) -> bool:
    """Returns True if either company_size or users_count is available."""
    return bool(
        ctx.collected_data.get("company_size") or
        ctx.collected_data.get("users_count")
    )


@shared_registry.condition(
    "has_contact_info",
    description="Check if contact information has been collected",
    requires_fields={"email", "phone", "contact"},
    category="data"
)
def has_contact_info(ctx: BaseContext) -> bool:
    """Returns True if email, phone, or contact is available."""
    return bool(
        ctx.collected_data.get("email") or
        ctx.collected_data.get("phone") or
        ctx.collected_data.get("contact")
    )


@shared_registry.condition(
    "has_pain_point",
    description="Check if a pain point has been identified",
    requires_fields={"pain_point", "pain_category"},
    category="data"
)
def has_pain_point(ctx: BaseContext) -> bool:
    """Returns True if a pain point has been identified."""
    return bool(
        ctx.collected_data.get("pain_point") or
        ctx.collected_data.get("pain_category")
    )


@shared_registry.condition(
    "has_competitor_mention",
    description="Check if a competitor has been mentioned",
    requires_fields={"competitor", "current_crm"},
    category="data"
)
def has_competitor_mention(ctx: BaseContext) -> bool:
    """Returns True if a competitor or current CRM has been mentioned."""
    return bool(
        ctx.collected_data.get("competitor") or
        ctx.collected_data.get("current_crm")
    )


@shared_registry.condition(
    "has_role",
    description="Check if user role has been identified",
    requires_fields={"role"},
    category="data"
)
def has_role(ctx: BaseContext) -> bool:
    """Returns True if role is in collected_data."""
    return bool(ctx.collected_data.get("role"))


@shared_registry.condition(
    "has_industry",
    description="Check if industry has been identified",
    requires_fields={"industry"},
    category="data"
)
def has_industry(ctx: BaseContext) -> bool:
    """Returns True if industry is in collected_data."""
    return bool(ctx.collected_data.get("industry"))


# =============================================================================
# STATE CONDITIONS - Check dialogue state
# =============================================================================

@shared_registry.condition(
    "is_initial_state",
    description="Check if in initial state",
    category="state"
)
def is_initial_state(ctx: BaseContext) -> bool:
    """Returns True if state is 'initial'."""
    return ctx.state == "initial"


@shared_registry.condition(
    "is_success_state",
    description="Check if in success state",
    category="state"
)
def is_success_state(ctx: BaseContext) -> bool:
    """Returns True if state is 'success'."""
    return ctx.state == "success"


@shared_registry.condition(
    "is_failed_state",
    description="Check if in failed state",
    category="state"
)
def is_failed_state(ctx: BaseContext) -> bool:
    """Returns True if state is 'failed'."""
    return ctx.state == "failed"


@shared_registry.condition(
    "is_terminal_state",
    description="Check if in a terminal state (success or failed)",
    category="state"
)
def is_terminal_state(ctx: BaseContext) -> bool:
    """Returns True if state is 'success' or 'failed'."""
    return ctx.state in ("success", "failed")


# =============================================================================
# TURN CONDITIONS - Check turn number
# =============================================================================

@shared_registry.condition(
    "is_first_turn",
    description="Check if this is the first turn",
    category="turn"
)
def is_first_turn(ctx: BaseContext) -> bool:
    """Returns True if turn_number is 0."""
    return ctx.turn_number == 0


@shared_registry.condition(
    "is_early_conversation",
    description="Check if in early conversation (first 3 turns)",
    category="turn"
)
def is_early_conversation(ctx: BaseContext) -> bool:
    """Returns True if turn_number < 3."""
    return ctx.turn_number < 3


@shared_registry.condition(
    "is_late_conversation",
    description="Check if in late conversation (10+ turns)",
    category="turn"
)
def is_late_conversation(ctx: BaseContext) -> bool:
    """Returns True if turn_number >= 10."""
    return ctx.turn_number >= 10


@shared_registry.condition(
    "is_extended_conversation",
    description="Check if conversation is extended (20+ turns)",
    category="turn"
)
def is_extended_conversation(ctx: BaseContext) -> bool:
    """Returns True if turn_number >= 20."""
    return ctx.turn_number >= 20


# =============================================================================
# HELPER FUNCTIONS - For creating custom conditions
# =============================================================================

def has_field(field_name: str) -> bool:
    """
    Create a condition that checks for a specific field.

    Note: This is a helper for creating condition functions,
    not a condition itself.

    Example:
        @registry.condition("has_budget")
        def has_budget(ctx: BaseContext) -> bool:
            return check_field(ctx, "budget")
    """
    def condition(ctx: BaseContext) -> bool:
        return bool(ctx.collected_data.get(field_name))
    return condition


def check_field(ctx: BaseContext, field_name: str) -> bool:
    """Check if a specific field exists and has a truthy value."""
    return bool(ctx.collected_data.get(field_name))


def has_any_field(ctx: BaseContext, field_names: List[str]) -> bool:
    """Check if any of the specified fields exist."""
    return any(check_field(ctx, name) for name in field_names)


def has_all_fields(ctx: BaseContext, field_names: List[str]) -> bool:
    """Check if all of the specified fields exist."""
    return all(check_field(ctx, name) for name in field_names)


def get_field_value(ctx: BaseContext, field_name: str, default: Any = None) -> Any:
    """Get a field value from collected_data with default."""
    return ctx.collected_data.get(field_name, default)


# Export all public components
__all__ = [
    "shared_registry",
    # Data conditions
    "has_collected_data",
    "has_company_size",
    "has_users_count",
    "has_pricing_data",
    "has_contact_info",
    "has_pain_point",
    "has_competitor_mention",
    "has_role",
    "has_industry",
    # State conditions
    "is_initial_state",
    "is_success_state",
    "is_failed_state",
    "is_terminal_state",
    # Turn conditions
    "is_first_turn",
    "is_early_conversation",
    "is_late_conversation",
    "is_extended_conversation",
    # Helpers
    "has_field",
    "check_field",
    "has_any_field",
    "has_all_fields",
    "get_field_value",
]
