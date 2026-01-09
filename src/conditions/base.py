"""
Base context protocol for conditional rules system.

This module defines the BaseContext protocol that all domain-specific
contexts must implement. It provides a common interface for condition
functions that need to work across multiple domains.

Part of Phase 1: Foundation (ARCHITECTURE_UNIFIED_PLAN.md)
"""

from typing import Protocol, Dict, Any, runtime_checkable
from dataclasses import dataclass, field


@runtime_checkable
class BaseContext(Protocol):
    """
    Base protocol for all evaluation contexts.

    Defines common fields available in all domains.
    Conditions typed against BaseContext can be used anywhere.

    Attributes:
        collected_data: Data collected about the client during conversation
        state: Current dialogue state name
        turn_number: Current turn number in the dialogue (0-indexed)
    """

    @property
    def collected_data(self) -> Dict[str, Any]:
        """Collected data about the client."""
        ...

    @property
    def state(self) -> str:
        """Current dialogue state."""
        ...

    @property
    def turn_number(self) -> int:
        """Turn number in the dialogue."""
        ...


@dataclass
class SimpleContext:
    """
    Simple concrete implementation of BaseContext for testing and basic use.

    This class provides a straightforward implementation that can be used
    for unit tests, shared conditions, and simple evaluation scenarios.

    Example:
        ctx = SimpleContext(
            collected_data={"company_size": 10},
            state="spin_situation",
            turn_number=5
        )
        result = some_condition(ctx)
    """
    collected_data: Dict[str, Any] = field(default_factory=dict)
    state: str = ""
    turn_number: int = 0

    def __post_init__(self):
        """Validate context fields after initialization."""
        if self.turn_number < 0:
            raise ValueError("turn_number cannot be negative")

    @classmethod
    def create_test_context(
        cls,
        collected_data: Dict[str, Any] = None,
        state: str = "initial",
        turn_number: int = 0
    ) -> "SimpleContext":
        """
        Factory method to create a test context with defaults.

        Args:
            collected_data: Optional data to include
            state: Optional state name
            turn_number: Optional turn number

        Returns:
            A new SimpleContext instance
        """
        return cls(
            collected_data=collected_data or {},
            state=state,
            turn_number=turn_number
        )


def is_valid_context(obj: Any) -> bool:
    """
    Check if an object implements the BaseContext protocol.

    Args:
        obj: Object to check

    Returns:
        True if object implements BaseContext, False otherwise
    """
    return isinstance(obj, BaseContext)
