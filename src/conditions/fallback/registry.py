"""
Fallback Condition Registry.

This module provides the domain-specific registry for Fallback conditions.
All conditions that operate on FallbackContext should be registered here.

Part of Phase 6: Fallback Domain (ARCHITECTURE_UNIFIED_PLAN.md)
"""

from typing import Callable, Set

from src.conditions.registry import ConditionRegistry
from src.conditions.fallback.context import FallbackContext


# Create the Fallback domain registry
fallback_registry = ConditionRegistry("fallback", FallbackContext)


def fallback_condition(
    name: str,
    description: str = "",
    requires_fields: Set[str] = None,
    category: str = "general"
) -> Callable[[Callable[[FallbackContext], bool]], Callable[[FallbackContext], bool]]:
    """
    Decorator for registering a Fallback condition.

    This is a convenience wrapper around fallback_registry.condition()
    that provides cleaner syntax for condition registration.

    Args:
        name: Unique name of the condition
        description: Human-readable description (falls back to docstring)
        requires_fields: Set of context fields this condition requires
        category: Category for grouping related conditions

    Returns:
        Decorator function

    Example:
        @fallback_condition("should_escalate", category="tier")
        def should_escalate(ctx: FallbackContext) -> bool:
            '''Check if fallback should escalate to next tier.'''
            return ctx.consecutive_fallbacks >= 2
    """
    return fallback_registry.condition(
        name=name,
        description=description,
        requires_fields=requires_fields,
        category=category
    )


def get_fallback_registry() -> ConditionRegistry:
    """
    Get the Fallback registry.

    Returns:
        The Fallback condition registry
    """
    return fallback_registry


# Export all public components
__all__ = [
    "fallback_registry",
    "fallback_condition",
    "get_fallback_registry",
]
