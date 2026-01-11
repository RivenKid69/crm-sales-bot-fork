"""
Personalization Condition Registry.

This module provides the domain-specific registry for Personalization conditions.
All conditions that operate on PersonalizationContext should be registered here.

Part of Phase 7: Personalization Domain (ARCHITECTURE_UNIFIED_PLAN.md)
"""

from typing import Callable, Set

from src.conditions.registry import ConditionRegistry
from src.conditions.personalization.context import PersonalizationContext


# Create the Personalization domain registry
personalization_registry = ConditionRegistry("personalization", PersonalizationContext)


def personalization_condition(
    name: str,
    description: str = "",
    requires_fields: Set[str] = None,
    category: str = "general"
) -> Callable[[Callable[[PersonalizationContext], bool]], Callable[[PersonalizationContext], bool]]:
    """
    Decorator for registering a Personalization condition.

    This is a convenience wrapper around personalization_registry.condition()
    that provides cleaner syntax for condition registration.

    Args:
        name: Unique name of the condition
        description: Human-readable description (falls back to docstring)
        requires_fields: Set of context fields this condition requires
        category: Category for grouping related conditions

    Returns:
        Decorator function

    Example:
        @personalization_condition("should_add_cta", category="cta")
        def should_add_cta(ctx: PersonalizationContext) -> bool:
            '''Check if CTA should be added to response.'''
            return ctx.is_cta_eligible_state() and not ctx.should_skip_cta()
    """
    return personalization_registry.condition(
        name=name,
        description=description,
        requires_fields=requires_fields,
        category=category
    )


def get_personalization_registry() -> ConditionRegistry:
    """
    Get the Personalization registry.

    Returns:
        The Personalization condition registry
    """
    return personalization_registry


# Export all public components
__all__ = [
    "personalization_registry",
    "personalization_condition",
    "get_personalization_registry",
]
