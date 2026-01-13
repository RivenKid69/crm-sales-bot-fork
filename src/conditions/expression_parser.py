"""
Condition Expression Parser for AND/OR/NOT combinations.

This module provides parsing of composite conditions from YAML configuration.
Supports nested expressions with caching for performance.

Part of Phase 1: State Machine Parameterization

Formats supported:
- Simple: "condition_name"
- AND: {"and": [...]}
- OR: {"or": [...]}
- NOT: {"not": "condition_name"}
- Custom reference: "custom:name"
"""

from typing import (
    Dict, Any, Callable, Optional, List, Union,
    TYPE_CHECKING, Generic, TypeVar
)
from dataclasses import dataclass, field
import logging

if TYPE_CHECKING:
    from src.conditions.registry import ConditionRegistry
    from src.conditions.trace import EvaluationTrace

logger = logging.getLogger(__name__)

# Type for context (generic)
TContext = TypeVar("TContext")

# Type alias for condition expressions from YAML
ConditionExpression = Union[str, Dict[str, Any]]


class ExpressionParseError(Exception):
    """Raised when expression parsing fails."""

    def __init__(self, expression: Any, reason: str):
        self.expression = expression
        self.reason = reason
        message = f"Invalid expression {expression!r}: {reason}"
        super().__init__(message)


class UnknownConditionError(Exception):
    """Raised when a condition is not found."""

    def __init__(self, condition_name: str, source: str = ""):
        self.condition_name = condition_name
        self.source = source
        message = f"Unknown condition '{condition_name}'"
        if source:
            message += f" in {source}"
        super().__init__(message)


class UnknownCustomConditionError(Exception):
    """Raised when a custom condition is not found."""

    def __init__(self, condition_name: str):
        self.condition_name = condition_name
        message = f"Unknown custom condition 'custom:{condition_name}'"
        super().__init__(message)


@dataclass
class ParsedExpression(Generic[TContext]):
    """
    Represents a parsed condition expression.

    Attributes:
        evaluator: Callable that evaluates the expression given a context
        source: Original expression (for debugging)
        is_composite: Whether this is a composite (AND/OR/NOT) expression
        referenced_conditions: Set of simple condition names referenced
    """
    evaluator: Callable[[TContext, Optional["EvaluationTrace"]], bool]
    source: Any
    is_composite: bool = False
    referenced_conditions: set = field(default_factory=set)

    def evaluate(
        self,
        ctx: TContext,
        trace: Optional["EvaluationTrace"] = None
    ) -> bool:
        """Evaluate the expression against context."""
        return self.evaluator(ctx, trace)


class ConditionExpressionParser(Generic[TContext]):
    """
    Parses AND/OR/NOT expressions from YAML.

    Supports:
    - Simple conditions: "condition_name" → registry lookup
    - AND: {"and": [...]} → all must be true
    - OR: {"or": [...]} → at least one must be true
    - NOT: {"not": "condition"} → negation
    - Custom reference: "custom:name" → lookup in custom_conditions

    Example:
        parser = ConditionExpressionParser(registry, custom_conditions)

        # Simple condition
        expr = parser.parse("has_pricing_data")
        result = expr.evaluate(ctx)

        # Composite condition
        expr = parser.parse({
            "and": [
                "has_contact_info",
                {"or": ["has_pain_point", "has_high_interest"]},
                {"not": "client_frustrated"}
            ]
        })
        result = expr.evaluate(ctx)
    """

    def __init__(
        self,
        registry: "ConditionRegistry[TContext]",
        custom_conditions: Optional[Dict[str, Dict[str, Any]]] = None
    ):
        """
        Initialize parser.

        Args:
            registry: ConditionRegistry for evaluating simple conditions
            custom_conditions: Dict of custom condition definitions from YAML
                Format: {"name": {"description": "...", "expression": {...}}}
        """
        self.registry = registry
        self.custom_conditions = custom_conditions or {}
        self._cache: Dict[str, ParsedExpression[TContext]] = {}

    def parse(
        self,
        expression: ConditionExpression,
        source_name: str = ""
    ) -> ParsedExpression[TContext]:
        """
        Parse a condition expression.

        Args:
            expression: The expression to parse (string or dict)
            source_name: Optional name for error messages

        Returns:
            ParsedExpression that can be evaluated

        Raises:
            ExpressionParseError: If expression format is invalid
            UnknownConditionError: If referenced condition doesn't exist
            UnknownCustomConditionError: If custom condition doesn't exist
        """
        # Generate cache key
        cache_key = self._make_cache_key(expression)
        if cache_key in self._cache:
            return self._cache[cache_key]

        # Parse the expression
        parsed = self._parse_internal(expression, source_name)

        # Cache the result
        self._cache[cache_key] = parsed

        return parsed

    def _make_cache_key(self, expression: ConditionExpression) -> str:
        """Create a cache key from expression."""
        if isinstance(expression, str):
            return expression
        # For dicts, use repr for consistent key
        return repr(self._normalize_expression(expression))

    def _normalize_expression(self, expression: Any) -> Any:
        """Normalize expression for consistent caching."""
        if isinstance(expression, dict):
            return {k: self._normalize_expression(v) for k, v in sorted(expression.items())}
        if isinstance(expression, list):
            return [self._normalize_expression(item) for item in expression]
        return expression

    def _parse_internal(
        self,
        expression: ConditionExpression,
        source_name: str = ""
    ) -> ParsedExpression[TContext]:
        """Internal parsing implementation."""
        # String condition
        if isinstance(expression, str):
            # Custom condition reference
            if expression.startswith("custom:"):
                return self._parse_custom(expression[7:], source_name)
            # Simple condition
            return self._parse_simple(expression, source_name)

        # Dict with operator
        if isinstance(expression, dict):
            if "and" in expression:
                return self._parse_and(expression["and"], source_name)
            if "or" in expression:
                return self._parse_or(expression["or"], source_name)
            if "not" in expression:
                return self._parse_not(expression["not"], source_name)

            raise ExpressionParseError(
                expression,
                "dict must contain 'and', 'or', or 'not' key"
            )

        raise ExpressionParseError(
            expression,
            f"expected string or dict, got {type(expression).__name__}"
        )

    def _parse_simple(
        self,
        condition_name: str,
        source_name: str = ""
    ) -> ParsedExpression[TContext]:
        """Parse a simple condition reference."""
        # Validate condition exists
        if not self.registry.has(condition_name):
            raise UnknownConditionError(
                condition_name,
                source_name or "expression"
            )

        def evaluator(
            ctx: TContext,
            trace: Optional["EvaluationTrace"] = None
        ) -> bool:
            return self.registry.evaluate(condition_name, ctx, trace)

        return ParsedExpression(
            evaluator=evaluator,
            source=condition_name,
            is_composite=False,
            referenced_conditions={condition_name}
        )

    def _parse_custom(
        self,
        custom_name: str,
        source_name: str = ""
    ) -> ParsedExpression[TContext]:
        """Parse a custom condition reference."""
        if custom_name not in self.custom_conditions:
            raise UnknownCustomConditionError(custom_name)

        custom_def = self.custom_conditions[custom_name]
        if "expression" not in custom_def:
            raise ExpressionParseError(
                f"custom:{custom_name}",
                "custom condition must have 'expression' field"
            )

        # Recursively parse the custom expression
        return self._parse_internal(
            custom_def["expression"],
            source_name=f"custom:{custom_name}"
        )

    def _parse_and(
        self,
        operands: List[ConditionExpression],
        source_name: str = ""
    ) -> ParsedExpression[TContext]:
        """Parse AND expression."""
        if not isinstance(operands, list):
            raise ExpressionParseError(
                {"and": operands},
                "'and' value must be a list"
            )

        if len(operands) < 2:
            raise ExpressionParseError(
                {"and": operands},
                "'and' requires at least 2 operands"
            )

        # Parse all operands
        parsed_operands = [
            self._parse_internal(op, source_name)
            for op in operands
        ]

        # Collect all referenced conditions
        all_refs = set()
        for parsed in parsed_operands:
            all_refs.update(parsed.referenced_conditions)

        def evaluator(
            ctx: TContext,
            trace: Optional["EvaluationTrace"] = None
        ) -> bool:
            # Short-circuit: return False on first False
            for parsed in parsed_operands:
                if not parsed.evaluate(ctx, trace):
                    return False
            return True

        return ParsedExpression(
            evaluator=evaluator,
            source={"and": operands},
            is_composite=True,
            referenced_conditions=all_refs
        )

    def _parse_or(
        self,
        operands: List[ConditionExpression],
        source_name: str = ""
    ) -> ParsedExpression[TContext]:
        """Parse OR expression."""
        if not isinstance(operands, list):
            raise ExpressionParseError(
                {"or": operands},
                "'or' value must be a list"
            )

        if len(operands) < 2:
            raise ExpressionParseError(
                {"or": operands},
                "'or' requires at least 2 operands"
            )

        # Parse all operands
        parsed_operands = [
            self._parse_internal(op, source_name)
            for op in operands
        ]

        # Collect all referenced conditions
        all_refs = set()
        for parsed in parsed_operands:
            all_refs.update(parsed.referenced_conditions)

        def evaluator(
            ctx: TContext,
            trace: Optional["EvaluationTrace"] = None
        ) -> bool:
            # Short-circuit: return True on first True
            for parsed in parsed_operands:
                if parsed.evaluate(ctx, trace):
                    return True
            return False

        return ParsedExpression(
            evaluator=evaluator,
            source={"or": operands},
            is_composite=True,
            referenced_conditions=all_refs
        )

    def _parse_not(
        self,
        operand: ConditionExpression,
        source_name: str = ""
    ) -> ParsedExpression[TContext]:
        """Parse NOT expression."""
        # Parse the operand
        parsed_operand = self._parse_internal(operand, source_name)

        def evaluator(
            ctx: TContext,
            trace: Optional["EvaluationTrace"] = None
        ) -> bool:
            return not parsed_operand.evaluate(ctx, trace)

        return ParsedExpression(
            evaluator=evaluator,
            source={"not": operand},
            is_composite=True,
            referenced_conditions=parsed_operand.referenced_conditions
        )

    def validate_expression(
        self,
        expression: ConditionExpression,
        source_name: str = ""
    ) -> List[str]:
        """
        Validate an expression without evaluating it.

        Args:
            expression: Expression to validate
            source_name: Name for error messages

        Returns:
            List of error messages (empty if valid)
        """
        errors = []

        try:
            parsed = self.parse(expression, source_name)
            # Check that all referenced conditions exist
            for cond in parsed.referenced_conditions:
                if not self.registry.has(cond):
                    errors.append(f"Unknown condition: {cond}")
        except ExpressionParseError as e:
            errors.append(str(e))
        except UnknownConditionError as e:
            errors.append(str(e))
        except UnknownCustomConditionError as e:
            errors.append(str(e))

        return errors

    def validate_custom_conditions(self) -> Dict[str, List[str]]:
        """
        Validate all custom conditions.

        Returns:
            Dict mapping condition name to list of errors (empty if valid)
        """
        results = {}

        for name, definition in self.custom_conditions.items():
            errors = []

            if "expression" not in definition:
                errors.append("Missing 'expression' field")
            else:
                errors.extend(
                    self.validate_expression(
                        definition["expression"],
                        f"custom:{name}"
                    )
                )

            if errors:
                results[name] = errors

        return results

    def get_all_referenced_conditions(
        self,
        expression: ConditionExpression
    ) -> set:
        """
        Get all simple conditions referenced by an expression.

        Args:
            expression: Expression to analyze

        Returns:
            Set of condition names
        """
        try:
            parsed = self.parse(expression)
            return parsed.referenced_conditions
        except Exception:
            return set()

    def clear_cache(self) -> None:
        """Clear the expression cache."""
        self._cache.clear()

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        return {
            "cache_size": len(self._cache),
            "cached_expressions": list(self._cache.keys())
        }

    def __repr__(self) -> str:
        return (
            f"ConditionExpressionParser("
            f"registry={self.registry.name!r}, "
            f"custom_count={len(self.custom_conditions)}, "
            f"cached={len(self._cache)})"
        )


# Export all public components
__all__ = [
    "ConditionExpressionParser",
    "ParsedExpression",
    "ConditionExpression",
    "ExpressionParseError",
    "UnknownConditionError",
    "UnknownCustomConditionError",
]
