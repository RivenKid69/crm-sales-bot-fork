"""
Policy Condition Registry.

This module provides the domain-specific registry for Policy conditions.
All conditions that operate on PolicyContext should be registered here.

Part of Phase 5: DialoguePolicy Domain (ARCHITECTURE_UNIFIED_PLAN.md)
"""

from typing import Callable, Set

from src.conditions.registry import ConditionRegistry
from src.conditions.policy.context import PolicyContext


# Create the Policy domain registry
policy_registry = ConditionRegistry("policy", PolicyContext)


def policy_condition(
    name: str,
    description: str = "",
    requires_fields: Set[str] = None,
    category: str = "general"
) -> Callable[[Callable[[PolicyContext], bool]], Callable[[PolicyContext], bool]]:
    """
    Decorator for registering a Policy condition.

    This is a convenience wrapper around policy_registry.condition()
    that provides cleaner syntax for condition registration.

    Args:
        name: Unique name of the condition
        description: Human-readable description (falls back to docstring)
        requires_fields: Set of context fields this condition requires
        category: Category for grouping related conditions

    Returns:
        Decorator function

    Example:
        @policy_condition("is_stuck", category="repair")
        def is_stuck(ctx: PolicyContext) -> bool:
            '''Check if client is stuck.'''
            return ctx.is_stuck
    """
    return policy_registry.condition(
        name=name,
        description=description,
        requires_fields=requires_fields,
        category=category
    )


def get_policy_registry() -> ConditionRegistry:
    """
    Get the Policy registry.

    Returns:
        The Policy condition registry
    """
    return policy_registry


# Export all public components
__all__ = [
    "policy_registry",
    "policy_condition",
    "get_policy_registry",
]
