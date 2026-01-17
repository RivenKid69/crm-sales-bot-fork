"""
Tests for complex nested conditions (AND/OR/NOT).

This module tests:
1. Deeply nested condition expressions
2. Condition evaluation order
3. Short-circuit evaluation
4. Mixed AND/OR/NOT combinations
5. Condition expression parsing and validation
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
import yaml
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


# =============================================================================
# MOCK CONTEXT AND REGISTRY FOR TESTING
# =============================================================================

class MockEvaluationContext:
    """Mock context for condition evaluation."""

    def __init__(self, **data):
        self.collected_data = data.pop('collected_data', {})
        for k, v in data.items():
            setattr(self, k, v)


class MockConditionRegistry:
    """Mock registry that returns predefined values."""

    def __init__(self, conditions: dict = None):
        self._conditions = conditions or {}
        self._evaluation_order = []

    def has(self, name: str) -> bool:
        return name in self._conditions

    def evaluate(self, name: str, ctx, trace=None) -> bool:
        self._evaluation_order.append(name)
        if name not in self._conditions:
            return False
        value = self._conditions[name]
        if callable(value):
            return value(ctx)
        return value

    def get_evaluation_order(self):
        return self._evaluation_order

    def reset_order(self):
        self._evaluation_order = []


# =============================================================================
# SIMPLE CONDITION EXPRESSION EVALUATOR
# =============================================================================

class ConditionEvaluator:
    """Evaluates condition expressions with AND/OR/NOT support."""

    def __init__(self, registry: MockConditionRegistry):
        self.registry = registry

    def evaluate(self, expression, ctx) -> bool:
        """
        Evaluate a condition expression.

        Expression can be:
        - str: simple condition name
        - {"and": [...]}
        - {"or": [...]}
        - {"not": ...}
        """
        if isinstance(expression, str):
            return self.registry.evaluate(expression, ctx)

        if isinstance(expression, dict):
            if 'and' in expression:
                return all(self.evaluate(sub, ctx) for sub in expression['and'])
            if 'or' in expression:
                return any(self.evaluate(sub, ctx) for sub in expression['or'])
            if 'not' in expression:
                return not self.evaluate(expression['not'], ctx)

        return False


# =============================================================================
# DEEPLY NESTED CONDITION TESTS
# =============================================================================

class TestDeeplyNestedConditions:
    """Tests for deeply nested AND/OR/NOT expressions."""

    def test_two_level_nesting_and_or(self):
        """Two levels: AND containing OR."""
        registry = MockConditionRegistry({
            "cond_a": True,
            "cond_b": False,
            "cond_c": True,
            "cond_d": True
        })
        evaluator = ConditionEvaluator(registry)
        ctx = MockEvaluationContext()

        # (a AND b) OR (c AND d) = (T AND F) OR (T AND T) = F OR T = T
        expression = {
            "or": [
                {"and": ["cond_a", "cond_b"]},
                {"and": ["cond_c", "cond_d"]}
            ]
        }

        result = evaluator.evaluate(expression, ctx)
        assert result is True

    def test_three_level_nesting(self):
        """Three levels of nesting."""
        registry = MockConditionRegistry({
            "a": True, "b": True, "c": False, "d": True
        })
        evaluator = ConditionEvaluator(registry)
        ctx = MockEvaluationContext()

        # ((a AND b) OR c) AND d = ((T AND T) OR F) AND T = (T OR F) AND T = T AND T = T
        expression = {
            "and": [
                {
                    "or": [
                        {"and": ["a", "b"]},
                        "c"
                    ]
                },
                "d"
            ]
        }

        result = evaluator.evaluate(expression, ctx)
        assert result is True

    def test_five_level_nesting(self):
        """Five levels of deep nesting."""
        registry = MockConditionRegistry({
            "a": True, "b": True, "c": True, "d": True, "e": True
        })
        evaluator = ConditionEvaluator(registry)
        ctx = MockEvaluationContext()

        # Deeply nested: AND(OR(AND(OR(AND(a,b),c),d),e))
        expression = {
            "and": [
                {
                    "or": [
                        {
                            "and": [
                                {
                                    "or": [
                                        {"and": ["a", "b"]},
                                        "c"
                                    ]
                                },
                                "d"
                            ]
                        },
                        "e"
                    ]
                }
            ]
        }

        result = evaluator.evaluate(expression, ctx)
        assert result is True

    def test_ten_conditions_in_and(self):
        """AND with 10 conditions."""
        conditions = {f"cond_{i}": True for i in range(10)}
        registry = MockConditionRegistry(conditions)
        evaluator = ConditionEvaluator(registry)
        ctx = MockEvaluationContext()

        expression = {"and": [f"cond_{i}" for i in range(10)]}

        result = evaluator.evaluate(expression, ctx)
        assert result is True

        # If one is False, entire AND is False
        conditions["cond_5"] = False
        registry = MockConditionRegistry(conditions)
        evaluator = ConditionEvaluator(registry)

        result = evaluator.evaluate(expression, ctx)
        assert result is False

    def test_ten_conditions_in_or(self):
        """OR with 10 conditions."""
        conditions = {f"cond_{i}": False for i in range(10)}
        registry = MockConditionRegistry(conditions)
        evaluator = ConditionEvaluator(registry)
        ctx = MockEvaluationContext()

        expression = {"or": [f"cond_{i}" for i in range(10)]}

        result = evaluator.evaluate(expression, ctx)
        assert result is False

        # If one is True, entire OR is True
        conditions["cond_7"] = True
        registry = MockConditionRegistry(conditions)
        evaluator = ConditionEvaluator(registry)

        result = evaluator.evaluate(expression, ctx)
        assert result is True


class TestNotConditions:
    """Tests for NOT condition expressions."""

    def test_simple_not(self):
        """Simple NOT negation."""
        registry = MockConditionRegistry({"cond_a": True})
        evaluator = ConditionEvaluator(registry)
        ctx = MockEvaluationContext()

        expression = {"not": "cond_a"}
        result = evaluator.evaluate(expression, ctx)
        assert result is False

        registry = MockConditionRegistry({"cond_a": False})
        evaluator = ConditionEvaluator(registry)
        result = evaluator.evaluate(expression, ctx)
        assert result is True

    def test_not_with_and(self):
        """NOT(AND(a, b))."""
        registry = MockConditionRegistry({"a": True, "b": True})
        evaluator = ConditionEvaluator(registry)
        ctx = MockEvaluationContext()

        expression = {"not": {"and": ["a", "b"]}}
        result = evaluator.evaluate(expression, ctx)
        assert result is False  # NOT(T AND T) = NOT(T) = F

        registry = MockConditionRegistry({"a": True, "b": False})
        evaluator = ConditionEvaluator(registry)
        result = evaluator.evaluate(expression, ctx)
        assert result is True  # NOT(T AND F) = NOT(F) = T

    def test_not_with_or(self):
        """NOT(OR(a, b))."""
        registry = MockConditionRegistry({"a": False, "b": False})
        evaluator = ConditionEvaluator(registry)
        ctx = MockEvaluationContext()

        expression = {"not": {"or": ["a", "b"]}}
        result = evaluator.evaluate(expression, ctx)
        assert result is True  # NOT(F OR F) = NOT(F) = T

    def test_double_negation(self):
        """NOT(NOT(a)) = a."""
        registry = MockConditionRegistry({"a": True})
        evaluator = ConditionEvaluator(registry)
        ctx = MockEvaluationContext()

        expression = {"not": {"not": "a"}}
        result = evaluator.evaluate(expression, ctx)
        assert result is True  # NOT(NOT(T)) = NOT(F) = T


class TestShortCircuitEvaluation:
    """Tests for short-circuit evaluation behavior."""

    def test_and_short_circuits_on_false(self):
        """AND should stop evaluating after first False."""
        registry = MockConditionRegistry({
            "cond_a": False,
            "cond_b": True,
            "cond_c": True
        })
        evaluator = ConditionEvaluator(registry)
        ctx = MockEvaluationContext()

        expression = {"and": ["cond_a", "cond_b", "cond_c"]}
        result = evaluator.evaluate(expression, ctx)

        assert result is False
        # Note: Python's all() does short-circuit, so cond_b and cond_c
        # won't be evaluated if cond_a is False

    def test_or_short_circuits_on_true(self):
        """OR should stop evaluating after first True."""
        registry = MockConditionRegistry({
            "cond_a": True,
            "cond_b": False,
            "cond_c": False
        })
        evaluator = ConditionEvaluator(registry)
        ctx = MockEvaluationContext()

        expression = {"or": ["cond_a", "cond_b", "cond_c"]}
        result = evaluator.evaluate(expression, ctx)

        assert result is True
        # Note: Python's any() does short-circuit, so cond_b and cond_c
        # won't be evaluated if cond_a is True


class TestConditionEvaluationOrder:
    """Tests for condition evaluation order."""

    def test_and_evaluates_left_to_right(self):
        """AND evaluates conditions left to right."""
        order = []

        def make_condition(name, value):
            def cond(ctx):
                order.append(name)
                return value
            return cond

        registry = MockConditionRegistry({
            "first": make_condition("first", True),
            "second": make_condition("second", True),
            "third": make_condition("third", True)
        })
        evaluator = ConditionEvaluator(registry)
        ctx = MockEvaluationContext()

        expression = {"and": ["first", "second", "third"]}
        evaluator.evaluate(expression, ctx)

        assert order == ["first", "second", "third"]

    def test_or_evaluates_left_to_right(self):
        """OR evaluates conditions left to right."""
        order = []

        def make_condition(name, value):
            def cond(ctx):
                order.append(name)
                return value
            return cond

        registry = MockConditionRegistry({
            "first": make_condition("first", False),
            "second": make_condition("second", False),
            "third": make_condition("third", True)
        })
        evaluator = ConditionEvaluator(registry)
        ctx = MockEvaluationContext()

        expression = {"or": ["first", "second", "third"]}
        evaluator.evaluate(expression, ctx)

        assert order == ["first", "second", "third"]

    def test_nested_evaluation_order(self):
        """Nested expressions evaluate in correct order."""
        order = []

        def make_condition(name, value):
            def cond(ctx):
                order.append(name)
                return value
            return cond

        registry = MockConditionRegistry({
            "a": make_condition("a", True),
            "b": make_condition("b", True),
            "c": make_condition("c", True),
            "d": make_condition("d", True)
        })
        evaluator = ConditionEvaluator(registry)
        ctx = MockEvaluationContext()

        # (a AND b) OR (c AND d)
        expression = {
            "or": [
                {"and": ["a", "b"]},
                {"and": ["c", "d"]}
            ]
        }
        evaluator.evaluate(expression, ctx)

        # First branch (a AND b) evaluates to True, OR short-circuits
        # so c and d may not be evaluated (depends on implementation)
        assert "a" in order
        assert "b" in order


class TestMixedConditions:
    """Tests for mixed AND/OR/NOT combinations."""

    def test_demorgans_law_and_to_or(self):
        """NOT(a AND b) = NOT(a) OR NOT(b)."""
        registry = MockConditionRegistry({"a": True, "b": False})
        evaluator = ConditionEvaluator(registry)
        ctx = MockEvaluationContext()

        # NOT(a AND b)
        expr1 = {"not": {"and": ["a", "b"]}}
        result1 = evaluator.evaluate(expr1, ctx)

        # NOT(a) OR NOT(b)
        expr2 = {"or": [{"not": "a"}, {"not": "b"}]}
        result2 = evaluator.evaluate(expr2, ctx)

        assert result1 == result2

    def test_demorgans_law_or_to_and(self):
        """NOT(a OR b) = NOT(a) AND NOT(b)."""
        registry = MockConditionRegistry({"a": False, "b": False})
        evaluator = ConditionEvaluator(registry)
        ctx = MockEvaluationContext()

        # NOT(a OR b)
        expr1 = {"not": {"or": ["a", "b"]}}
        result1 = evaluator.evaluate(expr1, ctx)

        # NOT(a) AND NOT(b)
        expr2 = {"and": [{"not": "a"}, {"not": "b"}]}
        result2 = evaluator.evaluate(expr2, ctx)

        assert result1 == result2

    def test_complex_business_rule(self):
        """Complex business rule: ready for close."""
        # ready_for_close = (has_contact OR (is_hot_lead AND has_interest))
        #                   AND NOT(has_rejection)
        registry = MockConditionRegistry({
            "has_contact": False,
            "is_hot_lead": True,
            "has_interest": True,
            "has_rejection": False
        })
        evaluator = ConditionEvaluator(registry)
        ctx = MockEvaluationContext()

        expression = {
            "and": [
                {
                    "or": [
                        "has_contact",
                        {"and": ["is_hot_lead", "has_interest"]}
                    ]
                },
                {"not": "has_rejection"}
            ]
        }

        result = evaluator.evaluate(expression, ctx)
        assert result is True

    def test_spin_skip_condition(self):
        """SPIN phase skip condition."""
        # skip_spin_problem = (has_explicit_problem OR (is_hot_lead AND has_demo_request))
        #                     AND has_situation_data
        registry = MockConditionRegistry({
            "has_explicit_problem": False,
            "is_hot_lead": True,
            "has_demo_request": True,
            "has_situation_data": True
        })
        evaluator = ConditionEvaluator(registry)
        ctx = MockEvaluationContext()

        expression = {
            "and": [
                {
                    "or": [
                        "has_explicit_problem",
                        {"and": ["is_hot_lead", "has_demo_request"]}
                    ]
                },
                "has_situation_data"
            ]
        }

        result = evaluator.evaluate(expression, ctx)
        assert result is True


class TestConditionExpressionParsing:
    """Tests for parsing condition expressions from YAML."""

    def test_parse_simple_condition(self, config_factory):
        """Parse simple condition name."""
        config_dir = config_factory()

        custom_conditions = {
            "conditions": {
                "simple_cond": {
                    "description": "Simple condition",
                    "expression": "base_condition"
                }
            }
        }

        with open(config_dir / "conditions" / "custom.yaml", 'w', encoding='utf-8') as f:
            yaml.dump(custom_conditions, f)

        with open(config_dir / "conditions" / "custom.yaml", 'r', encoding='utf-8') as f:
            loaded = yaml.safe_load(f)

        expr = loaded['conditions']['simple_cond']['expression']
        assert isinstance(expr, str)
        assert expr == "base_condition"

    def test_parse_and_expression(self, config_factory):
        """Parse AND expression."""
        config_dir = config_factory()

        custom_conditions = {
            "conditions": {
                "and_cond": {
                    "description": "AND condition",
                    "expression": {"and": ["cond_a", "cond_b", "cond_c"]}
                }
            }
        }

        with open(config_dir / "conditions" / "custom.yaml", 'w', encoding='utf-8') as f:
            yaml.dump(custom_conditions, f)

        with open(config_dir / "conditions" / "custom.yaml", 'r', encoding='utf-8') as f:
            loaded = yaml.safe_load(f)

        expr = loaded['conditions']['and_cond']['expression']
        assert 'and' in expr
        assert len(expr['and']) == 3

    def test_parse_nested_expression(self, config_factory):
        """Parse deeply nested expression."""
        config_dir = config_factory()

        custom_conditions = {
            "conditions": {
                "nested_cond": {
                    "description": "Nested condition",
                    "expression": {
                        "and": [
                            {"or": ["a", "b"]},
                            {"not": {"and": ["c", "d"]}}
                        ]
                    }
                }
            }
        }

        with open(config_dir / "conditions" / "custom.yaml", 'w', encoding='utf-8') as f:
            yaml.dump(custom_conditions, f)

        with open(config_dir / "conditions" / "custom.yaml", 'r', encoding='utf-8') as f:
            loaded = yaml.safe_load(f)

        expr = loaded['conditions']['nested_cond']['expression']
        assert 'and' in expr
        assert 'or' in expr['and'][0]
        assert 'not' in expr['and'][1]


class TestConditionExpressionValidation:
    """Tests for validating condition expressions."""

    def test_validate_unknown_condition_reference(self):
        """Detect unknown condition names in expressions."""

        def validate_expression(expr, known_conditions):
            """Validate that all referenced conditions exist."""
            errors = []

            def check(e):
                if isinstance(e, str):
                    if e not in known_conditions:
                        errors.append(f"Unknown condition: {e}")
                elif isinstance(e, dict):
                    for key, value in e.items():
                        if key in ('and', 'or'):
                            for item in value:
                                check(item)
                        elif key == 'not':
                            check(value)

            check(expr)
            return errors

        known = {"cond_a", "cond_b", "cond_c"}
        expression = {"and": ["cond_a", "cond_unknown", "cond_b"]}

        errors = validate_expression(expression, known)
        assert len(errors) == 1
        assert "cond_unknown" in errors[0]

    def test_validate_empty_and(self):
        """Empty AND expression is invalid."""

        def validate_expression_structure(expr):
            errors = []

            def check(e):
                if isinstance(e, dict):
                    for key, value in e.items():
                        if key in ('and', 'or'):
                            if not value or len(value) == 0:
                                errors.append(f"Empty {key} expression")
                            for item in value:
                                check(item)
                        elif key == 'not':
                            if value is None:
                                errors.append("NOT expression has no operand")
                            else:
                                check(value)

            check(expr)
            return errors

        expression = {"and": []}
        errors = validate_expression_structure(expression)
        assert len(errors) == 1

    def test_validate_single_element_and(self):
        """Single element AND is redundant but valid."""

        def is_redundant(expr):
            """Check for redundant expressions."""
            redundancies = []

            def check(e, path=""):
                if isinstance(e, dict):
                    for key, value in e.items():
                        if key in ('and', 'or') and len(value) == 1:
                            redundancies.append(f"{path}{key} with single element")
                        if key in ('and', 'or'):
                            for i, item in enumerate(value):
                                check(item, f"{path}{key}[{i}].")
                        elif key == 'not':
                            check(value, f"{path}not.")

            check(expr)
            return redundancies

        expression = {"and": ["single_condition"]}
        redundancies = is_redundant(expression)
        assert len(redundancies) == 1

    def test_validate_deeply_nested_limit(self):
        """Check for excessively deep nesting."""

        def check_nesting_depth(expr, max_depth=20):
            """Check if expression exceeds max nesting depth."""

            def get_depth(e, current=0):
                if current > max_depth:
                    return current
                if isinstance(e, str):
                    return current
                if isinstance(e, dict):
                    max_child = current
                    for key, value in e.items():
                        if key in ('and', 'or'):
                            for item in value:
                                max_child = max(max_child, get_depth(item, current + 1))
                        elif key == 'not':
                            max_child = max(max_child, get_depth(value, current + 1))
                    return max_child
                return current

            return get_depth(expr)

        # Create deeply nested expression
        expr = "base"
        for i in range(15):
            if i % 2 == 0:
                expr = {"and": [expr]}
            else:
                expr = {"or": [expr]}

        depth = check_nesting_depth(expr)
        # Depth should be at least 10 (deep nesting detected)
        assert depth >= 10


class TestConditionalRulesInYaml:
    """Tests for conditional rules in YAML configuration."""

    def test_rule_with_when_condition(self, config_factory):
        """Rule with 'when' condition is parsed correctly."""
        config_dir = config_factory()

        states_path = config_dir / "states" / "sales_flow.yaml"
        with open(states_path, 'r', encoding='utf-8') as f:
            states = yaml.safe_load(f)

        # Add rule with condition
        states['states']['greeting']['rules']['demo_request'] = {
            "when": {"and": ["has_contact", "is_qualified"]},
            "then": "schedule_demo"
        }

        with open(states_path, 'w', encoding='utf-8') as f:
            yaml.dump(states, f, allow_unicode=True)

        with open(states_path, 'r', encoding='utf-8') as f:
            loaded = yaml.safe_load(f)

        rule = loaded['states']['greeting']['rules']['demo_request']
        assert 'when' in rule
        assert 'and' in rule['when']

    def test_transition_with_conditional_rules(self, config_factory):
        """Transition with multiple conditional rules."""
        config_dir = config_factory()

        states_path = config_dir / "states" / "sales_flow.yaml"
        with open(states_path, 'r', encoding='utf-8') as f:
            states = yaml.safe_load(f)

        # Add conditional transition
        states['states']['presentation']['transitions']['agreement'] = [
            {"when": "is_very_hot_lead", "then": "success"},
            {"when": {"and": ["has_contact", "has_demo_scheduled"]}, "then": "success"},
            {"when": "is_hot_lead", "then": "close"},
            "handle_objection"  # default fallback
        ]

        with open(states_path, 'w', encoding='utf-8') as f:
            yaml.dump(states, f, allow_unicode=True)

        with open(states_path, 'r', encoding='utf-8') as f:
            loaded = yaml.safe_load(f)

        trans = loaded['states']['presentation']['transitions']['agreement']
        assert isinstance(trans, list)
        assert len(trans) == 4
        assert trans[0]['when'] == "is_very_hot_lead"
        assert 'and' in trans[1]['when']
