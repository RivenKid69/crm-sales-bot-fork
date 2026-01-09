"""
StateMachine Condition Registry.

This module provides the domain-specific registry for StateMachine conditions.
All conditions that operate on EvaluatorContext should be registered here.

Part of Phase 2: StateMachine Domain (ARCHITECTURE_UNIFIED_PLAN.md)
"""

from typing import Callable, Set

from src.conditions.registry import ConditionRegistry
from src.conditions.state_machine.context import EvaluatorContext


# Create the StateMachine domain registry
sm_registry = ConditionRegistry("state_machine", EvaluatorContext)


def sm_condition(
    name: str,
    description: str = "",
    requires_fields: Set[str] = None,
    category: str = "general"
) -> Callable[[Callable[[EvaluatorContext], bool]], Callable[[EvaluatorContext], bool]]:
    """
    Decorator for registering a StateMachine condition.

    This is a convenience wrapper around sm_registry.condition()
    that provides cleaner syntax for condition registration.

    Args:
        name: Unique name of the condition
        description: Human-readable description (falls back to docstring)
        requires_fields: Set of collected_data fields this condition requires
        category: Category for grouping related conditions

    Returns:
        Decorator function

    Example:
        @sm_condition("has_pricing_data", category="data")
        def has_pricing_data(ctx: EvaluatorContext) -> bool:
            '''Check if pricing data is available.'''
            return bool(
                ctx.collected_data.get("company_size") or
                ctx.collected_data.get("users_count")
            )
    """
    return sm_registry.condition(
        name=name,
        description=description,
        requires_fields=requires_fields,
        category=category
    )


def get_sm_registry() -> ConditionRegistry:
    """
    Get the StateMachine registry.

    Returns:
        The StateMachine condition registry
    """
    return sm_registry


# Export all public components
__all__ = [
    "sm_registry",
    "sm_condition",
    "get_sm_registry",
]
