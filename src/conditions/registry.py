"""
Condition Registry for conditional rules system.

This module provides a type-safe registry for registering, validating,
and evaluating conditions. Each domain (StateMachine, Policy, Fallback,
Personalization) has its own registry with its own context type.

Part of Phase 1: Foundation (ARCHITECTURE_UNIFIED_PLAN.md)
"""

from typing import (
    Generic, TypeVar, Callable, Dict, Optional,
    List, Set, Any, Type, TYPE_CHECKING
)
from dataclasses import dataclass, field
from functools import wraps
import inspect
import time

from src.conditions.base import BaseContext

if TYPE_CHECKING:
    from src.conditions.trace import EvaluationTrace


# Type variable bound to BaseContext for generic registry
TContext = TypeVar("TContext", bound=BaseContext)


class ConditionNotFoundError(Exception):
    """Raised when a condition is not found in the registry."""

    def __init__(self, condition_name: str, registry_name: str = ""):
        self.condition_name = condition_name
        self.registry_name = registry_name
        message = f"Condition '{condition_name}' not found"
        if registry_name:
            message += f" in registry '{registry_name}'"
        super().__init__(message)


class ConditionEvaluationError(Exception):
    """Raised when an error occurs during condition evaluation."""

    def __init__(
        self,
        condition_name: str,
        original_error: Exception,
        registry_name: str = ""
    ):
        self.condition_name = condition_name
        self.original_error = original_error
        self.registry_name = registry_name
        message = f"Error evaluating condition '{condition_name}'"
        if registry_name:
            message += f" in registry '{registry_name}'"
        message += f": {original_error}"
        super().__init__(message)


class ConditionAlreadyRegisteredError(Exception):
    """Raised when trying to register a condition that already exists."""

    def __init__(self, condition_name: str, registry_name: str = ""):
        self.condition_name = condition_name
        self.registry_name = registry_name
        message = f"Condition '{condition_name}' already registered"
        if registry_name:
            message += f" in registry '{registry_name}'"
        super().__init__(message)


class InvalidConditionSignatureError(Exception):
    """Raised when a condition function has an invalid signature."""

    def __init__(self, condition_name: str, reason: str):
        self.condition_name = condition_name
        self.reason = reason
        message = f"Invalid signature for condition '{condition_name}': {reason}"
        super().__init__(message)


@dataclass
class ConditionMetadata(Generic[TContext]):
    """
    Metadata for a registered condition.

    Attributes:
        name: Unique name of the condition
        description: Human-readable description
        func: The condition function
        context_type: Expected context type
        requires_fields: Set of collected_data fields this condition requires
        category: Category for grouping related conditions
    """
    name: str
    description: str
    func: Callable[[TContext], bool]
    context_type: Type[TContext]
    requires_fields: Set[str] = field(default_factory=set)
    category: str = "general"


@dataclass
class ValidationResult:
    """
    Result of validating conditions in a registry.

    Attributes:
        passed: List of condition names that passed validation
        failed: List of dicts with name and reason for conditions that failed
        errors: List of dicts with name and error for conditions that raised exceptions
    """
    passed: List[str] = field(default_factory=list)
    failed: List[Dict[str, str]] = field(default_factory=list)
    errors: List[Dict[str, str]] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        """Check if all conditions passed validation."""
        return len(self.failed) == 0 and len(self.errors) == 0

    @property
    def total_count(self) -> int:
        """Total number of conditions validated."""
        return len(self.passed) + len(self.failed) + len(self.errors)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "passed": self.passed,
            "failed": self.failed,
            "errors": self.errors,
            "is_valid": self.is_valid,
            "total_count": self.total_count
        }


class ConditionRegistry(Generic[TContext]):
    """
    Type-safe registry for conditions of a specific domain.

    Each domain (StateMachine, Policy, Fallback, Personalization)
    has its own registry with its own context type.

    Benefits:
    - Type safety: mypy checks context type compatibility
    - Isolation: conditions from one domain are not visible in another
    - Open-Closed: new domain = new registry without modifying existing

    Example:
        # Create registry for StateMachine domain
        sm_registry = ConditionRegistry("state_machine", EvaluatorContext)

        # Register a condition
        @sm_registry.condition("has_pricing_data", category="data")
        def has_pricing_data(ctx: EvaluatorContext) -> bool:
            return bool(ctx.collected_data.get("company_size"))

        # Evaluate condition
        result = sm_registry.evaluate("has_pricing_data", context)
    """

    def __init__(
        self,
        name: str,
        context_type: Type[TContext],
        allow_overwrite: bool = False
    ):
        """
        Initialize a new condition registry.

        Args:
            name: Name of this registry (e.g., "state_machine", "policy")
            context_type: Type of context this registry accepts
            allow_overwrite: Whether to allow overwriting existing conditions
        """
        self.name = name
        self.context_type = context_type
        self.allow_overwrite = allow_overwrite
        self._conditions: Dict[str, ConditionMetadata[TContext]] = {}
        self._categories: Dict[str, List[str]] = {}

    def condition(
        self,
        name: str,
        description: str = "",
        requires_fields: Set[str] = None,
        category: str = "general"
    ) -> Callable[[Callable[[TContext], bool]], Callable[[TContext], bool]]:
        """
        Decorator for registering a condition.

        Args:
            name: Unique name of the condition
            description: Human-readable description (falls back to docstring)
            requires_fields: Set of collected_data fields this condition requires
            category: Category for grouping related conditions

        Returns:
            Decorator function

        Raises:
            ConditionAlreadyRegisteredError: If condition already exists
            InvalidConditionSignatureError: If function signature is invalid

        Example:
            @registry.condition("has_pricing_data", category="data")
            def has_pricing_data(ctx: EvaluatorContext) -> bool:
                return bool(ctx.collected_data.get("company_size"))
        """
        def decorator(
            func: Callable[[TContext], bool]
        ) -> Callable[[TContext], bool]:
            # Validate signature
            self._validate_signature(name, func)

            # Check for duplicate registration
            if name in self._conditions and not self.allow_overwrite:
                raise ConditionAlreadyRegisteredError(name, self.name)

            # Create metadata
            metadata = ConditionMetadata(
                name=name,
                description=description or func.__doc__ or "",
                func=func,
                context_type=self.context_type,
                requires_fields=requires_fields or set(),
                category=category
            )

            # Register condition
            self._conditions[name] = metadata

            # Update category index
            if category not in self._categories:
                self._categories[category] = []
            if name not in self._categories[category]:
                self._categories[category].append(name)

            # Wrap function to preserve metadata
            @wraps(func)
            def wrapper(ctx: TContext) -> bool:
                return func(ctx)

            # Attach metadata to wrapper for introspection
            wrapper._condition_name = name  # type: ignore
            wrapper._registry = self.name  # type: ignore
            wrapper._metadata = metadata  # type: ignore

            return wrapper

        return decorator

    def _validate_signature(
        self,
        name: str,
        func: Callable[[TContext], bool]
    ) -> None:
        """
        Validate that a function has the correct signature for a condition.

        Args:
            name: Name of the condition (for error messages)
            func: Function to validate

        Raises:
            InvalidConditionSignatureError: If signature is invalid
        """
        sig = inspect.signature(func)
        params = list(sig.parameters.values())

        # Check parameter count
        if len(params) != 1:
            raise InvalidConditionSignatureError(
                name,
                f"must accept exactly one parameter, got {len(params)}"
            )

        # Check parameter annotation if provided
        param = params[0]
        if param.annotation != inspect.Parameter.empty:
            # Allow BaseContext or the specific context type
            if not (
                param.annotation == self.context_type or
                param.annotation == BaseContext or
                (hasattr(param.annotation, '__name__') and
                 param.annotation.__name__ == self.context_type.__name__)
            ):
                raise InvalidConditionSignatureError(
                    name,
                    f"parameter type {param.annotation.__name__} is not "
                    f"compatible with {self.context_type.__name__}"
                )

    def register(
        self,
        name: str,
        func: Callable[[TContext], bool],
        description: str = "",
        requires_fields: Set[str] = None,
        category: str = "general"
    ) -> None:
        """
        Register a condition programmatically (non-decorator style).

        Args:
            name: Unique name of the condition
            func: The condition function
            description: Human-readable description
            requires_fields: Set of collected_data fields required
            category: Category for grouping

        Raises:
            ConditionAlreadyRegisteredError: If condition already exists
            InvalidConditionSignatureError: If function signature is invalid
        """
        # Use decorator internally to maintain consistency
        decorated = self.condition(name, description, requires_fields, category)
        decorated(func)

    def unregister(self, name: str) -> bool:
        """
        Remove a condition from the registry.

        Args:
            name: Name of the condition to remove

        Returns:
            True if condition was removed, False if it didn't exist
        """
        if name not in self._conditions:
            return False

        metadata = self._conditions.pop(name)

        # Remove from category index
        category = metadata.category
        if category in self._categories and name in self._categories[category]:
            self._categories[category].remove(name)
            if not self._categories[category]:
                del self._categories[category]

        return True

    def evaluate(
        self,
        name: str,
        ctx: TContext,
        trace: Optional["EvaluationTrace"] = None
    ) -> bool:
        """
        Evaluate a condition.

        Args:
            name: Name of the condition
            ctx: Context to evaluate against
            trace: Optional trace for debugging

        Returns:
            Result of the condition evaluation

        Raises:
            ConditionNotFoundError: If condition doesn't exist
            ConditionEvaluationError: If evaluation fails
        """
        metadata = self._conditions.get(name)
        if metadata is None:
            raise ConditionNotFoundError(name, self.name)

        try:
            start_time = time.perf_counter()
            result = metadata.func(ctx)
            elapsed_ms = (time.perf_counter() - start_time) * 1000

            if trace is not None:
                trace.record(
                    condition_name=name,
                    result=result,
                    ctx=ctx,
                    relevant_fields=metadata.requires_fields,
                    elapsed_ms=elapsed_ms
                )

            return result

        except Exception as e:
            raise ConditionEvaluationError(name, e, self.name) from e

    def get(self, name: str) -> Optional[ConditionMetadata[TContext]]:
        """Get metadata for a condition."""
        return self._conditions.get(name)

    def has(self, name: str) -> bool:
        """Check if a condition exists."""
        return name in self._conditions

    def list_all(self) -> List[str]:
        """List all condition names."""
        return list(self._conditions.keys())

    def list_by_category(self, category: str) -> List[str]:
        """List condition names in a category."""
        return list(self._categories.get(category, []))

    def get_categories(self) -> List[str]:
        """List all categories."""
        return list(self._categories.keys())

    def validate_all(
        self,
        ctx_factory: Callable[[], TContext]
    ) -> ValidationResult:
        """
        Validate all conditions against a test context.

        Args:
            ctx_factory: Factory function to create test context

        Returns:
            ValidationResult with passed/failed/errors
        """
        result = ValidationResult()
        test_ctx = ctx_factory()

        for name, metadata in self._conditions.items():
            try:
                output = metadata.func(test_ctx)
                if not isinstance(output, bool):
                    result.failed.append({
                        "name": name,
                        "reason": f"returned {type(output).__name__}, expected bool"
                    })
                else:
                    result.passed.append(name)
            except Exception as e:
                result.errors.append({
                    "name": name,
                    "error": str(e)
                })

        return result

    def get_documentation(self) -> str:
        """
        Generate documentation for all conditions in the registry.

        Returns:
            Markdown-formatted documentation string
        """
        lines = [f"# {self.name.replace('_', ' ').title()} Conditions\n"]
        lines.append(f"Context: `{self.context_type.__name__}`\n")
        lines.append(f"Total conditions: {len(self._conditions)}\n")

        for category in sorted(self._categories.keys()):
            lines.append(f"\n## {category.title()}\n")
            for name in sorted(self._categories[category]):
                meta = self._conditions[name]
                lines.append(f"### `{name}`")
                if meta.description:
                    lines.append(f"\n{meta.description}")
                if meta.requires_fields:
                    fields = ", ".join(sorted(meta.requires_fields))
                    lines.append(f"\n**Requires:** {fields}")
                lines.append("")

        return "\n".join(lines)

    def get_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the registry.

        Returns:
            Dictionary with condition and category counts
        """
        return {
            "name": self.name,
            "context_type": self.context_type.__name__,
            "total_conditions": len(self._conditions),
            "total_categories": len(self._categories),
            "conditions_by_category": {
                cat: len(names) for cat, names in self._categories.items()
            }
        }

    def __len__(self) -> int:
        """Return number of registered conditions."""
        return len(self._conditions)

    def __contains__(self, name: str) -> bool:
        """Check if a condition is registered."""
        return name in self._conditions

    def __repr__(self) -> str:
        return (
            f"ConditionRegistry(name={self.name!r}, "
            f"context_type={self.context_type.__name__}, "
            f"conditions={len(self._conditions)})"
        )
