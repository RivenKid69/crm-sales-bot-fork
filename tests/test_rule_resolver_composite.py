"""
Tests for RuleResolver with composite (AND/OR/NOT) conditions.

Tests the integration of ConditionExpressionParser with RuleResolver.
"""

import pytest

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

    def list_all(self):
        return list(self._conditions.keys())

class TestRuleResolverComposite:
    """Tests for RuleResolver with composite conditions."""

    def test_simple_condition_still_works(self):
        """Test that simple string conditions still work."""
        from src.rules.resolver import RuleResolver

        registry = MockRegistry({"has_data": True})
        resolver = RuleResolver(registry)

        rule = {"when": "has_data", "then": "do_action"}
        ctx = MockContext()

        result = resolver._evaluate_conditional_rule(rule, "test_rule", ctx)
        assert result == "do_action"

    def test_simple_condition_false(self):
        """Test simple condition that returns False."""
        from src.rules.resolver import RuleResolver

        registry = MockRegistry({"has_data": False})
        resolver = RuleResolver(registry)

        rule = {"when": "has_data", "then": "do_action"}
        ctx = MockContext()

        result = resolver._evaluate_conditional_rule(rule, "test_rule", ctx)
        assert result is None

    def test_composite_and_condition(self):
        """Test composite AND condition."""
        from src.rules.resolver import RuleResolver
        from src.conditions.expression_parser import ConditionExpressionParser

        registry = MockRegistry({"cond1": True, "cond2": True})
        parser = ConditionExpressionParser(registry)
        resolver = RuleResolver(registry, expression_parser=parser)

        rule = {
            "when": {"and": ["cond1", "cond2"]},
            "then": "do_action"
        }
        ctx = MockContext()

        result = resolver._evaluate_conditional_rule(rule, "test_rule", ctx)
        assert result == "do_action"

    def test_composite_and_condition_false(self):
        """Test composite AND condition when one is False."""
        from src.rules.resolver import RuleResolver
        from src.conditions.expression_parser import ConditionExpressionParser

        registry = MockRegistry({"cond1": True, "cond2": False})
        parser = ConditionExpressionParser(registry)
        resolver = RuleResolver(registry, expression_parser=parser)

        rule = {
            "when": {"and": ["cond1", "cond2"]},
            "then": "do_action"
        }
        ctx = MockContext()

        result = resolver._evaluate_conditional_rule(rule, "test_rule", ctx)
        assert result is None

    def test_composite_or_condition(self):
        """Test composite OR condition."""
        from src.rules.resolver import RuleResolver
        from src.conditions.expression_parser import ConditionExpressionParser

        registry = MockRegistry({"cond1": False, "cond2": True})
        parser = ConditionExpressionParser(registry)
        resolver = RuleResolver(registry, expression_parser=parser)

        rule = {
            "when": {"or": ["cond1", "cond2"]},
            "then": "do_action"
        }
        ctx = MockContext()

        result = resolver._evaluate_conditional_rule(rule, "test_rule", ctx)
        assert result == "do_action"

    def test_composite_not_condition(self):
        """Test composite NOT condition."""
        from src.rules.resolver import RuleResolver
        from src.conditions.expression_parser import ConditionExpressionParser

        registry = MockRegistry({"is_frustrated": False})
        parser = ConditionExpressionParser(registry)
        resolver = RuleResolver(registry, expression_parser=parser)

        rule = {
            "when": {"not": "is_frustrated"},
            "then": "proceed"
        }
        ctx = MockContext()

        result = resolver._evaluate_conditional_rule(rule, "test_rule", ctx)
        assert result == "proceed"

    def test_nested_composite_condition(self):
        """Test nested composite conditions."""
        from src.rules.resolver import RuleResolver
        from src.conditions.expression_parser import ConditionExpressionParser

        registry = MockRegistry({
            "has_contact": True,
            "has_pain": False,
            "has_interest": True,
            "is_frustrated": False
        })
        parser = ConditionExpressionParser(registry)
        resolver = RuleResolver(registry, expression_parser=parser)

        # Same as ready_for_demo from custom.yaml
        rule = {
            "when": {
                "and": [
                    "has_contact",
                    {"or": ["has_pain", "has_interest"]},
                    {"not": "is_frustrated"}
                ]
            },
            "then": "schedule_demo"
        }
        ctx = MockContext()

        result = resolver._evaluate_conditional_rule(rule, "test_rule", ctx)
        assert result == "schedule_demo"

    def test_composite_without_parser_raises_error(self):
        """Test that composite condition without parser raises error."""
        from src.rules.resolver import RuleResolver, InvalidRuleFormatError

        registry = MockRegistry({"cond1": True})
        resolver = RuleResolver(registry)  # No parser

        rule = {
            "when": {"and": ["cond1", "cond2"]},
            "then": "do_action"
        }
        ctx = MockContext()

        with pytest.raises(InvalidRuleFormatError) as exc_info:
            resolver._evaluate_conditional_rule(rule, "test_rule", ctx)

        assert "expression_parser" in str(exc_info.value)

    def test_resolve_action_with_composite(self):
        """Test resolve_action with composite conditions in rules."""
        from src.rules.resolver import RuleResolver
        from src.conditions.expression_parser import ConditionExpressionParser

        registry = MockRegistry({
            "can_answer": True,
            "has_data": True,
        })
        parser = ConditionExpressionParser(registry)
        resolver = RuleResolver(registry, expression_parser=parser)

        state_rules = {
            "price_question": [
                {"when": {"and": ["can_answer", "has_data"]}, "then": "answer_with_facts"},
                "deflect"
            ]
        }
        ctx = MockContext()

        result = resolver.resolve_action(
            "price_question",
            state_rules=state_rules,
            global_rules={},
            ctx=ctx
        )
        assert result == "answer_with_facts"

    def test_resolve_action_composite_fallback(self):
        """Test fallback when composite condition is False."""
        from src.rules.resolver import RuleResolver
        from src.conditions.expression_parser import ConditionExpressionParser

        registry = MockRegistry({
            "can_answer": True,
            "has_data": False,  # This makes AND fail
        })
        parser = ConditionExpressionParser(registry)
        resolver = RuleResolver(registry, expression_parser=parser)

        state_rules = {
            "price_question": [
                {"when": {"and": ["can_answer", "has_data"]}, "then": "answer_with_facts"},
                "deflect"
            ]
        }
        ctx = MockContext()

        result = resolver.resolve_action(
            "price_question",
            state_rules=state_rules,
            global_rules={},
            ctx=ctx
        )
        assert result == "deflect"

class TestRuleResolverValidation:
    """Tests for validation of composite conditions."""

    def test_validate_composite_and_condition(self):
        """Test validation of AND composite condition."""
        from src.rules.resolver import RuleResolver

        registry = MockRegistry({"cond1": True, "cond2": True})
        resolver = RuleResolver(registry)

        states_config = {
            "test_state": {
                "rules": {
                    "test_intent": {"when": {"and": ["cond1", "cond2"]}, "then": "action"}
                }
            }
        }

        result = resolver.validate_config(states_config)
        assert result.is_valid

    def test_validate_unknown_condition_in_composite(self):
        """Test validation catches unknown conditions in composite."""
        from src.rules.resolver import RuleResolver

        registry = MockRegistry({"cond1": True})  # cond2 not registered
        resolver = RuleResolver(registry)

        states_config = {
            "test_state": {
                "rules": {
                    "test_intent": {"when": {"and": ["cond1", "unknown_cond"]}, "then": "action"}
                }
            }
        }

        result = resolver.validate_config(states_config)
        assert not result.is_valid
        assert any("unknown_cond" in e.condition_name for e in result.errors)

    def test_validate_nested_composite(self):
        """Test validation of nested composite conditions."""
        from src.rules.resolver import RuleResolver

        registry = MockRegistry({"a": True, "b": True, "c": True})
        resolver = RuleResolver(registry)

        states_config = {
            "test_state": {
                "rules": {
                    "test_intent": {
                        "when": {
                            "and": [
                                "a",
                                {"or": ["b", "c"]},
                                {"not": "a"}
                            ]
                        },
                        "then": "action"
                    }
                }
            }
        }

        result = resolver.validate_config(states_config)
        assert result.is_valid

    def test_validate_invalid_composite_format(self):
        """Test validation catches invalid composite format."""
        from src.rules.resolver import RuleResolver

        registry = MockRegistry({})
        resolver = RuleResolver(registry)

        states_config = {
            "test_state": {
                "rules": {
                    "test_intent": {
                        "when": {"invalid_key": ["cond1"]},
                        "then": "action"
                    }
                }
            }
        }

        result = resolver.validate_config(states_config)
        assert not result.is_valid

    def test_validate_custom_condition_reference(self):
        """Test validation allows custom: prefix."""
        from src.rules.resolver import RuleResolver

        registry = MockRegistry({"base": True})
        resolver = RuleResolver(registry)

        states_config = {
            "test_state": {
                "rules": {
                    "test_intent": {
                        "when": {"and": ["base", "custom:my_custom"]},
                        "then": "action"
                    }
                }
            }
        }

        result = resolver.validate_config(states_config)
        # custom: conditions are validated separately, so this should pass
        assert result.is_valid
