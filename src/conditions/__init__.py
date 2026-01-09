"""
Conditional Rules System - Foundation Layer.

This package provides the infrastructure for conditional rules evaluation
across different domains (StateMachine, Policy, Fallback, Personalization).

Main components:
- BaseContext: Protocol defining common context interface
- SimpleContext: Concrete implementation for testing/simple use
- ConditionRegistry: Type-safe registry for domain conditions
- EvaluationTrace: Trace of condition evaluations for debugging
- TraceCollector: Collector for aggregating traces
- ConditionRegistries: Aggregator for all domain registries

Part of Phase 1: Foundation (ARCHITECTURE_UNIFIED_PLAN.md)
"""

from typing import Dict, List, Any, Callable, Optional

from src.conditions.base import (
    BaseContext,
    SimpleContext,
    is_valid_context
)
from src.conditions.registry import (
    ConditionRegistry,
    ConditionMetadata,
    ValidationResult,
    ConditionNotFoundError,
    ConditionEvaluationError,
    ConditionAlreadyRegisteredError,
    InvalidConditionSignatureError,
    TContext
)
from src.conditions.trace import (
    EvaluationTrace,
    TraceCollector,
    TraceSummary,
    ConditionEntry,
    Resolution
)
from src.conditions.shared import shared_registry


class ConditionRegistries:
    """
    Aggregator for all condition registries.

    Provides unified interface for:
    - Registering domain registries
    - Validating all conditions across domains
    - Generating documentation
    - Collecting statistics

    Example:
        # Register domain registries
        ConditionRegistries.register("state_machine", sm_registry)
        ConditionRegistries.register("policy", policy_registry)

        # Validate all conditions
        result = ConditionRegistries.validate_all({
            "state_machine": lambda: EvaluatorContext(...),
            "policy": lambda: PolicyContext(...)
        })

        # Generate documentation
        docs = ConditionRegistries.generate_documentation()
    """

    _registries: Dict[str, ConditionRegistry] = {}

    @classmethod
    def register(cls, name: str, registry: ConditionRegistry) -> None:
        """
        Register a domain registry.

        Args:
            name: Name of the domain (e.g., "state_machine")
            registry: The registry instance

        Raises:
            ValueError: If registry already registered with this name
        """
        if name in cls._registries:
            raise ValueError(f"Registry '{name}' already registered")
        cls._registries[name] = registry

    @classmethod
    def unregister(cls, name: str) -> bool:
        """
        Remove a domain registry.

        Args:
            name: Name of the registry to remove

        Returns:
            True if removed, False if not found
        """
        if name in cls._registries:
            del cls._registries[name]
            return True
        return False

    @classmethod
    def get(cls, name: str) -> Optional[ConditionRegistry]:
        """
        Get a registry by name.

        Args:
            name: Name of the registry

        Returns:
            Registry instance or None if not found
        """
        return cls._registries.get(name)

    @classmethod
    def list_registries(cls) -> List[str]:
        """List all registered registry names."""
        return list(cls._registries.keys())

    @classmethod
    def validate_all(
        cls,
        ctx_factories: Dict[str, Callable]
    ) -> Dict[str, ValidationResult]:
        """
        Validate all conditions across all registries.

        Args:
            ctx_factories: Dict mapping registry name to context factory

        Returns:
            Dict mapping registry name to ValidationResult
        """
        results = {}
        for name, registry in cls._registries.items():
            if name in ctx_factories:
                results[name] = registry.validate_all(ctx_factories[name])
            else:
                # Create a minimal result indicating no factory provided
                results[name] = ValidationResult(
                    errors=[{
                        "name": "__registry__",
                        "error": f"No context factory provided for '{name}'"
                    }]
                )
        return results

    @classmethod
    def get_stats(cls) -> Dict[str, Any]:
        """
        Get statistics for all registries.

        Returns:
            Dict with aggregate statistics
        """
        stats = {
            "total_registries": len(cls._registries),
            "total_conditions": 0,
            "registries": {}
        }

        for name, registry in cls._registries.items():
            reg_stats = registry.get_stats()
            stats["registries"][name] = reg_stats
            stats["total_conditions"] += reg_stats["total_conditions"]

        return stats

    @classmethod
    def generate_documentation(cls) -> str:
        """
        Generate documentation for all registries.

        Returns:
            Markdown-formatted documentation string
        """
        lines = ["# Condition Registries Documentation\n"]
        lines.append(f"Total registries: {len(cls._registries)}\n")

        stats = cls.get_stats()
        lines.append(f"Total conditions: {stats['total_conditions']}\n")

        for name in sorted(cls._registries.keys()):
            registry = cls._registries[name]
            lines.append(f"\n---\n\n{registry.get_documentation()}")

        return "\n".join(lines)

    @classmethod
    def clear(cls) -> None:
        """Clear all registered registries."""
        cls._registries.clear()

    @classmethod
    def has_condition(cls, condition_name: str) -> bool:
        """
        Check if a condition exists in any registry.

        Args:
            condition_name: Name of the condition to find

        Returns:
            True if condition exists in any registry
        """
        return any(
            registry.has(condition_name)
            for registry in cls._registries.values()
        )

    @classmethod
    def find_condition(cls, condition_name: str) -> Optional[str]:
        """
        Find which registry contains a condition.

        Args:
            condition_name: Name of the condition to find

        Returns:
            Registry name or None if not found
        """
        for name, registry in cls._registries.items():
            if registry.has(condition_name):
                return name
        return None


# Register shared registry by default
ConditionRegistries.register("shared", shared_registry)


# Export all public components
__all__ = [
    # Base
    "BaseContext",
    "SimpleContext",
    "is_valid_context",
    # Registry
    "ConditionRegistry",
    "ConditionMetadata",
    "ValidationResult",
    "TContext",
    # Errors
    "ConditionNotFoundError",
    "ConditionEvaluationError",
    "ConditionAlreadyRegisteredError",
    "InvalidConditionSignatureError",
    # Trace
    "EvaluationTrace",
    "TraceCollector",
    "TraceSummary",
    "ConditionEntry",
    "Resolution",
    # Aggregator
    "ConditionRegistries",
    # Shared
    "shared_registry",
]
