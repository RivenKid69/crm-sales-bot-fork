"""
Tests for ConditionExpressionParser.

Tests AND/OR/NOT parsing and evaluation.
"""

import pytest
from unittest.mock import MagicMock, patch

class MockContext:
    """Mock context for testing."""
    pass

class MockRegistry:
    """Mock registry for testing."""

    def __init__(self, conditions: dict = None):
        self._conditions = conditions or {}
        self.name = "test_registry"

    def has(self, name: str) -> bool:
        return name in self._conditions

    def evaluate(self, name: str, ctx, trace=None) -> bool:
        if name not in self._conditions:
            from src.conditions.registry import ConditionNotFoundError
            raise ConditionNotFoundError(name, self.name)
        return self._conditions[name]

class TestConditionExpressionParser:
    """Tests for ConditionExpressionParser."""

    def test_parse_simple_condition(self):
        """Test parsing a simple string condition."""
        from src.conditions.expression_parser import ConditionExpressionParser

        registry = MockRegistry({"has_data": True})
        parser = ConditionExpressionParser(registry)

        expr = parser.parse("has_data")

        assert expr.source == "has_data"
        assert not expr.is_composite
        assert "has_data" in expr.referenced_conditions

    def test_evaluate_simple_true(self):
        """Test evaluating a simple condition that returns True."""
        from src.conditions.expression_parser import ConditionExpressionParser

        registry = MockRegistry({"has_data": True})
        parser = ConditionExpressionParser(registry)

        expr = parser.parse("has_data")
        ctx = MockContext()

        assert expr.evaluate(ctx) is True

    def test_evaluate_simple_false(self):
        """Test evaluating a simple condition that returns False."""
        from src.conditions.expression_parser import ConditionExpressionParser

        registry = MockRegistry({"has_data": False})
        parser = ConditionExpressionParser(registry)

        expr = parser.parse("has_data")
        ctx = MockContext()

        assert expr.evaluate(ctx) is False

    def test_parse_and_expression(self):
        """Test parsing AND expression."""
        from src.conditions.expression_parser import ConditionExpressionParser

        registry = MockRegistry({"cond1": True, "cond2": True})
        parser = ConditionExpressionParser(registry)

        expr = parser.parse({"and": ["cond1", "cond2"]})

        assert expr.is_composite
        assert "cond1" in expr.referenced_conditions
        assert "cond2" in expr.referenced_conditions

    def test_evaluate_and_all_true(self):
        """Test AND with all conditions True."""
        from src.conditions.expression_parser import ConditionExpressionParser

        registry = MockRegistry({"cond1": True, "cond2": True})
        parser = ConditionExpressionParser(registry)

        expr = parser.parse({"and": ["cond1", "cond2"]})
        ctx = MockContext()

        assert expr.evaluate(ctx) is True

    def test_evaluate_and_one_false(self):
        """Test AND with one condition False."""
        from src.conditions.expression_parser import ConditionExpressionParser

        registry = MockRegistry({"cond1": True, "cond2": False})
        parser = ConditionExpressionParser(registry)

        expr = parser.parse({"and": ["cond1", "cond2"]})
        ctx = MockContext()

        assert expr.evaluate(ctx) is False

    def test_parse_or_expression(self):
        """Test parsing OR expression."""
        from src.conditions.expression_parser import ConditionExpressionParser

        registry = MockRegistry({"cond1": True, "cond2": False})
        parser = ConditionExpressionParser(registry)

        expr = parser.parse({"or": ["cond1", "cond2"]})

        assert expr.is_composite
        assert "cond1" in expr.referenced_conditions
        assert "cond2" in expr.referenced_conditions

    def test_evaluate_or_one_true(self):
        """Test OR with one condition True."""
        from src.conditions.expression_parser import ConditionExpressionParser

        registry = MockRegistry({"cond1": False, "cond2": True})
        parser = ConditionExpressionParser(registry)

        expr = parser.parse({"or": ["cond1", "cond2"]})
        ctx = MockContext()

        assert expr.evaluate(ctx) is True

    def test_evaluate_or_all_false(self):
        """Test OR with all conditions False."""
        from src.conditions.expression_parser import ConditionExpressionParser

        registry = MockRegistry({"cond1": False, "cond2": False})
        parser = ConditionExpressionParser(registry)

        expr = parser.parse({"or": ["cond1", "cond2"]})
        ctx = MockContext()

        assert expr.evaluate(ctx) is False

    def test_parse_not_expression(self):
        """Test parsing NOT expression."""
        from src.conditions.expression_parser import ConditionExpressionParser

        registry = MockRegistry({"cond1": True})
        parser = ConditionExpressionParser(registry)

        expr = parser.parse({"not": "cond1"})

        assert expr.is_composite
        assert "cond1" in expr.referenced_conditions

    def test_evaluate_not_true(self):
        """Test NOT with True condition."""
        from src.conditions.expression_parser import ConditionExpressionParser

        registry = MockRegistry({"cond1": True})
        parser = ConditionExpressionParser(registry)

        expr = parser.parse({"not": "cond1"})
        ctx = MockContext()

        assert expr.evaluate(ctx) is False

    def test_evaluate_not_false(self):
        """Test NOT with False condition."""
        from src.conditions.expression_parser import ConditionExpressionParser

        registry = MockRegistry({"cond1": False})
        parser = ConditionExpressionParser(registry)

        expr = parser.parse({"not": "cond1"})
        ctx = MockContext()

        assert expr.evaluate(ctx) is True

    def test_nested_expression(self):
        """Test nested AND/OR/NOT expression."""
        from src.conditions.expression_parser import ConditionExpressionParser

        # Expression: (cond1 AND cond2) OR (NOT cond3)
        registry = MockRegistry({
            "cond1": True,
            "cond2": False,
            "cond3": False
        })
        parser = ConditionExpressionParser(registry)

        expr = parser.parse({
            "or": [
                {"and": ["cond1", "cond2"]},
                {"not": "cond3"}
            ]
        })
        ctx = MockContext()

        # cond1 AND cond2 = True AND False = False
        # NOT cond3 = NOT False = True
        # False OR True = True
        assert expr.evaluate(ctx) is True

    def test_complex_expression_from_yaml(self):
        """Test complex expression like in custom.yaml."""
        from src.conditions.expression_parser import ConditionExpressionParser

        # ready_for_demo expression from custom.yaml
        registry = MockRegistry({
            "has_contact_info": True,
            "has_pain_point": False,
            "has_high_interest": True,
            "client_frustrated": False
        })
        parser = ConditionExpressionParser(registry)

        expr = parser.parse({
            "and": [
                "has_contact_info",
                {"or": ["has_pain_point", "has_high_interest"]},
                {"not": "client_frustrated"}
            ]
        })
        ctx = MockContext()

        # has_contact_info = True
        # has_pain_point OR has_high_interest = False OR True = True
        # NOT client_frustrated = NOT False = True
        # True AND True AND True = True
        assert expr.evaluate(ctx) is True

    def test_custom_condition_reference(self):
        """Test parsing custom condition reference."""
        from src.conditions.expression_parser import ConditionExpressionParser

        registry = MockRegistry({"base_cond": True})
        custom_conditions = {
            "my_custom": {
                "description": "Custom condition",
                "expression": "base_cond"
            }
        }
        parser = ConditionExpressionParser(registry, custom_conditions)

        expr = parser.parse("custom:my_custom")
        ctx = MockContext()

        assert expr.evaluate(ctx) is True

    def test_unknown_condition_error(self):
        """Test error for unknown condition."""
        from src.conditions.expression_parser import (
            ConditionExpressionParser,
            UnknownConditionError
        )

        registry = MockRegistry({})
        parser = ConditionExpressionParser(registry)

        with pytest.raises(UnknownConditionError):
            parser.parse("nonexistent_condition")

    def test_unknown_custom_condition_error(self):
        """Test error for unknown custom condition."""
        from src.conditions.expression_parser import (
            ConditionExpressionParser,
            UnknownCustomConditionError
        )

        registry = MockRegistry({})
        parser = ConditionExpressionParser(registry)

        with pytest.raises(UnknownCustomConditionError):
            parser.parse("custom:nonexistent")

    def test_invalid_expression_error(self):
        """Test error for invalid expression format."""
        from src.conditions.expression_parser import (
            ConditionExpressionParser,
            ExpressionParseError
        )

        registry = MockRegistry({})
        parser = ConditionExpressionParser(registry)

        with pytest.raises(ExpressionParseError):
            parser.parse({"invalid_key": ["cond"]})

    def test_and_requires_two_operands(self):
        """Test that AND requires at least 2 operands."""
        from src.conditions.expression_parser import (
            ConditionExpressionParser,
            ExpressionParseError
        )

        registry = MockRegistry({"cond1": True})
        parser = ConditionExpressionParser(registry)

        with pytest.raises(ExpressionParseError):
            parser.parse({"and": ["cond1"]})

    def test_caching(self):
        """Test that expressions are cached."""
        from src.conditions.expression_parser import ConditionExpressionParser

        registry = MockRegistry({"cond1": True})
        parser = ConditionExpressionParser(registry)

        expr1 = parser.parse("cond1")
        expr2 = parser.parse("cond1")

        assert expr1 is expr2  # Same object from cache

    def test_validate_expression(self):
        """Test expression validation."""
        from src.conditions.expression_parser import ConditionExpressionParser

        registry = MockRegistry({"cond1": True})
        parser = ConditionExpressionParser(registry)

        # Valid expression
        errors = parser.validate_expression("cond1")
        assert errors == []

        # Invalid expression (unknown condition)
        errors = parser.validate_expression("unknown_cond")
        assert len(errors) > 0

    def test_validate_custom_conditions(self):
        """Test custom conditions validation."""
        from src.conditions.expression_parser import ConditionExpressionParser

        registry = MockRegistry({"base": True})
        custom_conditions = {
            "valid": {
                "expression": "base"
            },
            "invalid": {
                # Missing expression
            }
        }
        parser = ConditionExpressionParser(registry, custom_conditions)

        errors = parser.validate_custom_conditions()

        assert "invalid" in errors
        assert "valid" not in errors

class TestShortCircuitEvaluation:
    """Tests for short-circuit evaluation."""

    def test_and_short_circuit(self):
        """Test AND short-circuits on first False."""
        from src.conditions.expression_parser import ConditionExpressionParser

        # Track evaluation calls
        eval_calls = []

        class TrackingRegistry:
            name = "tracking"

            def has(self, name):
                return True

            def evaluate(self, name, ctx, trace=None):
                eval_calls.append(name)
                return name != "false_cond"

        registry = TrackingRegistry()
        parser = ConditionExpressionParser(registry)

        expr = parser.parse({
            "and": ["false_cond", "other_cond"]
        })
        ctx = MockContext()

        result = expr.evaluate(ctx)

        assert result is False
        assert "false_cond" in eval_calls
        assert "other_cond" not in eval_calls  # Short-circuited

    def test_or_short_circuit(self):
        """Test OR short-circuits on first True."""
        from src.conditions.expression_parser import ConditionExpressionParser

        eval_calls = []

        class TrackingRegistry:
            name = "tracking"

            def has(self, name):
                return True

            def evaluate(self, name, ctx, trace=None):
                eval_calls.append(name)
                return name == "true_cond"

        registry = TrackingRegistry()
        parser = ConditionExpressionParser(registry)

        expr = parser.parse({
            "or": ["true_cond", "other_cond"]
        })
        ctx = MockContext()

        result = expr.evaluate(ctx)

        assert result is True
        assert "true_cond" in eval_calls
        assert "other_cond" not in eval_calls  # Short-circuited
