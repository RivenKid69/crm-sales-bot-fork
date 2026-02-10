"""
Tests for RuleResolver - Phase 3.

This test suite provides 100% coverage for:
- RuleResolver class
- RuleResult dataclass
- ValidationResult and ValidationError
- Rule format handling (simple, conditional dict, chain)
- Config validation

Run with: pytest tests/test_rule_resolver.py -v
"""

import pytest
from typing import Dict, Any

from src.conditions.base import SimpleContext
from src.conditions.registry import ConditionRegistry
from src.conditions.trace import EvaluationTrace, Resolution
from src.rules.resolver import (
    RuleResolver,
    RuleResult,
    ValidationResult,
    ValidationError,
    UnknownConditionError,
    UnknownTargetStateError,
    InvalidRuleFormatError,
    create_resolver
)

# =============================================================================
# TEST FIXTURES
# =============================================================================

@pytest.fixture
def test_registry():
    """Create a fresh registry with test conditions."""
    registry = ConditionRegistry("test", SimpleContext)

    @registry.condition("always_true", category="test")
    def always_true(ctx: SimpleContext) -> bool:
        return True

    @registry.condition("always_false", category="test")
    def always_false(ctx: SimpleContext) -> bool:
        return False

    @registry.condition("has_company_size", category="data")
    def has_company_size(ctx: SimpleContext) -> bool:
        return bool(ctx.collected_data.get("company_size"))

    @registry.condition("has_contact_info", category="data")
    def has_contact_info(ctx: SimpleContext) -> bool:
        return bool(ctx.collected_data.get("email") or ctx.collected_data.get("phone"))

    @registry.condition("price_repeated_3x", category="intent")
    def price_repeated_3x(ctx: SimpleContext) -> bool:
        return ctx.collected_data.get("price_streak", 0) >= 3

    @registry.condition("has_pricing_data", category="data")
    def has_pricing_data(ctx: SimpleContext) -> bool:
        return bool(ctx.collected_data.get("company_size") or ctx.collected_data.get("users_count"))

    return registry

@pytest.fixture
def resolver(test_registry):
    """Create resolver with test registry."""
    return RuleResolver(test_registry)

@pytest.fixture
def context_with_data():
    """Context with company_size."""
    return SimpleContext(
        collected_data={"company_size": 50},
        state="spin_situation",
        turn_number=5
    )

@pytest.fixture
def context_without_data():
    """Context without company_size."""
    return SimpleContext(
        collected_data={},
        state="spin_situation",
        turn_number=5
    )

@pytest.fixture
def context_with_contact():
    """Context with contact info."""
    return SimpleContext(
        collected_data={"email": "test@example.com"},
        state="close",
        turn_number=10
    )

# =============================================================================
# RULE RESULT TESTS
# =============================================================================

class TestRuleResult:
    """Tests for RuleResult dataclass."""

    def test_create_result(self):
        """Test creating a RuleResult."""
        result = RuleResult(action="answer_with_facts", next_state="presentation")
        assert result.action == "answer_with_facts"
        assert result.next_state == "presentation"
        assert result.trace is None

    def test_result_with_trace(self):
        """Test RuleResult with trace."""
        trace = EvaluationTrace(rule_name="test")
        result = RuleResult(action="test_action", trace=trace)
        assert result.trace is trace

    def test_tuple_unpacking(self):
        """Test tuple unpacking for backward compatibility."""
        result = RuleResult(action="answer_with_facts", next_state="close")
        action, state = result
        assert action == "answer_with_facts"
        assert state == "close"

    def test_to_dict(self):
        """Test converting to dictionary."""
        result = RuleResult(action="test", next_state="state")
        data = result.to_dict()
        assert data["action"] == "test"
        assert data["next_state"] == "state"

    def test_to_dict_with_trace(self):
        """Test to_dict includes trace."""
        trace = EvaluationTrace(rule_name="test")
        trace.set_result("action", Resolution.SIMPLE)
        result = RuleResult(action="test", trace=trace)
        data = result.to_dict()
        assert "trace" in data

# =============================================================================
# VALIDATION ERROR AND RESULT TESTS
# =============================================================================

class TestValidationError:
    """Tests for ValidationError dataclass."""

    def test_create_error(self):
        """Test creating ValidationError."""
        error = ValidationError(
            error_type="unknown_condition",
            message="Condition not found",
            state="spin_situation",
            rule_name="price_question",
            condition_name="nonexistent"
        )
        assert error.error_type == "unknown_condition"
        assert error.condition_name == "nonexistent"

    def test_to_dict(self):
        """Test converting to dictionary."""
        error = ValidationError(
            error_type="test",
            message="test message"
        )
        data = error.to_dict()
        assert data["type"] == "test"
        assert data["message"] == "test message"

class TestValidationResult:
    """Tests for ValidationResult dataclass."""

    def test_empty_result(self):
        """Test empty validation result is valid."""
        result = ValidationResult()
        assert result.is_valid is True
        assert result.errors == []
        assert result.warnings == []

    def test_with_error(self):
        """Test result with error is invalid."""
        result = ValidationResult()
        result.add_error("test", "test error")
        assert result.is_valid is False

    def test_with_warning(self):
        """Test result with only warning is still valid."""
        result = ValidationResult()
        result.add_warning("test", "test warning")
        assert result.is_valid is True

    def test_to_dict(self):
        """Test converting to dictionary."""
        result = ValidationResult(checked_rules=10, checked_transitions=5)
        result.add_error("test", "error")
        data = result.to_dict()
        assert data["is_valid"] is False
        assert data["checked_rules"] == 10

# =============================================================================
# SIMPLE RULE TESTS
# =============================================================================

class TestSimpleRules:
    """Tests for simple string rules."""

    def test_resolve_simple_state_rule(self, resolver, context_with_data):
        """Test resolving simple string rule from state."""
        state_rules = {"greeting": "greet_back"}
        action = resolver.resolve_action(
            intent="greeting",
            state_rules=state_rules,
            global_rules={},
            ctx=context_with_data
        )
        assert action == "greet_back"

    def test_resolve_simple_global_rule(self, resolver, context_with_data):
        """Test resolving simple rule from global rules."""
        action = resolver.resolve_action(
            intent="greeting",
            state_rules={},
            global_rules={"greeting": "greet_back"},
            ctx=context_with_data
        )
        assert action == "greet_back"

    def test_state_rules_take_precedence(self, resolver, context_with_data):
        """Test state rules take precedence over global."""
        action = resolver.resolve_action(
            intent="greeting",
            state_rules={"greeting": "state_action"},
            global_rules={"greeting": "global_action"},
            ctx=context_with_data
        )
        assert action == "state_action"

    def test_fallback_to_default(self, resolver, context_with_data):
        """Test fallback to default action."""
        action = resolver.resolve_action(
            intent="unknown_intent",
            state_rules={},
            global_rules={},
            ctx=context_with_data
        )
        assert action == "continue_current_goal"

    def test_custom_default_action(self, test_registry):
        """Test custom default action."""
        resolver = RuleResolver(test_registry, default_action="custom_default")
        action = resolver.resolve_action(
            intent="unknown",
            state_rules={},
            global_rules={},
            ctx=SimpleContext()
        )
        assert action == "custom_default"

# =============================================================================
# CONDITIONAL DICT RULE TESTS
# =============================================================================

class TestConditionalDictRules:
    """Tests for conditional dict rules {"when": ..., "then": ...}."""

    def test_condition_matches(self, resolver, context_with_data):
        """Test conditional rule when condition is True."""
        state_rules = {
            "price_question": {"when": "has_company_size", "then": "answer_with_facts"}
        }
        action = resolver.resolve_action(
            intent="price_question",
            state_rules=state_rules,
            global_rules={},
            ctx=context_with_data
        )
        assert action == "answer_with_facts"

    def test_condition_does_not_match(self, resolver, context_without_data):
        """Test conditional rule when condition is False."""
        state_rules = {
            "price_question": {"when": "has_company_size", "then": "answer_with_facts"}
        }
        action = resolver.resolve_action(
            intent="price_question",
            state_rules=state_rules,
            global_rules={"price_question": "deflect"},
            ctx=context_without_data
        )
        # Falls through to global rule
        assert action == "deflect"

    def test_unknown_condition_error(self, resolver, context_with_data):
        """Test error on unknown condition."""
        state_rules = {
            "test": {"when": "nonexistent_condition", "then": "action"}
        }
        with pytest.raises(UnknownConditionError) as exc_info:
            resolver.resolve_action(
                intent="test",
                state_rules=state_rules,
                global_rules={},
                ctx=context_with_data
            )
        assert "nonexistent_condition" in str(exc_info.value)

    def test_missing_when_key(self, resolver, context_with_data):
        """Test error when 'when' key is missing."""
        state_rules = {"test": {"then": "action"}}
        with pytest.raises(InvalidRuleFormatError):
            resolver.resolve_action(
                intent="test",
                state_rules=state_rules,
                global_rules={},
                ctx=context_with_data
            )

    def test_missing_then_key(self, resolver, context_with_data):
        """Test error when 'then' key is missing."""
        state_rules = {"test": {"when": "always_true"}}
        with pytest.raises(InvalidRuleFormatError):
            resolver.resolve_action(
                intent="test",
                state_rules=state_rules,
                global_rules={},
                ctx=context_with_data
            )

# =============================================================================
# RULE CHAIN TESTS
# =============================================================================

class TestRuleChains:
    """Tests for rule chains (list format)."""

    def test_first_condition_matches(self, resolver, context_with_data):
        """Test chain where first condition matches."""
        state_rules = {
            "price_question": [
                {"when": "has_company_size", "then": "answer_with_facts"},
                {"when": "price_repeated_3x", "then": "answer_with_range"},
                "deflect"
            ]
        }
        action = resolver.resolve_action(
            intent="price_question",
            state_rules=state_rules,
            global_rules={},
            ctx=context_with_data
        )
        assert action == "answer_with_facts"

    def test_second_condition_matches(self, resolver):
        """Test chain where second condition matches."""
        ctx = SimpleContext(
            collected_data={"price_streak": 3},
            state="spin"
        )
        state_rules = {
            "price_question": [
                {"when": "has_company_size", "then": "answer_with_facts"},
                {"when": "price_repeated_3x", "then": "answer_with_range"},
                "deflect"
            ]
        }
        action = resolver.resolve_action(
            intent="price_question",
            state_rules=state_rules,
            global_rules={},
            ctx=ctx
        )
        assert action == "answer_with_range"

    def test_falls_through_to_default(self, resolver, context_without_data):
        """Test chain falls through to default."""
        state_rules = {
            "price_question": [
                {"when": "has_company_size", "then": "answer_with_facts"},
                {"when": "price_repeated_3x", "then": "answer_with_range"},
                "deflect_and_continue"
            ]
        }
        action = resolver.resolve_action(
            intent="price_question",
            state_rules=state_rules,
            global_rules={},
            ctx=context_without_data
        )
        assert action == "deflect_and_continue"

    def test_chain_with_none_default(self, resolver, context_without_data):
        """Test chain with None as default (stay in state)."""
        transitions = {
            "demo_request": [
                {"when": "has_contact_info", "then": "success"},
                None
            ]
        }
        result = resolver.resolve_transition(
            intent="demo_request",
            transitions=transitions,
            ctx=context_without_data
        )
        assert result is None

    def test_empty_chain_error(self, resolver, context_with_data):
        """Test error on empty chain."""
        state_rules = {"test": []}
        with pytest.raises(InvalidRuleFormatError):
            resolver.resolve_action(
                intent="test",
                state_rules=state_rules,
                global_rules={},
                ctx=context_with_data
            )

# =============================================================================
# TRANSITION TESTS
# =============================================================================

class TestTransitions:
    """Tests for transition resolution."""

    def test_simple_transition(self, resolver, context_with_data):
        """Test simple string transition."""
        transitions = {"agreement": "close"}
        result = resolver.resolve_transition(
            intent="agreement",
            transitions=transitions,
            ctx=context_with_data
        )
        assert result == "close"

    def test_conditional_transition_matches(self, resolver, context_with_contact):
        """Test conditional transition that matches."""
        transitions = {
            "demo_request": {"when": "has_contact_info", "then": "success"}
        }
        result = resolver.resolve_transition(
            intent="demo_request",
            transitions=transitions,
            ctx=context_with_contact
        )
        assert result == "success"

    def test_conditional_transition_no_match(self, resolver, context_without_data):
        """Test conditional transition that doesn't match."""
        transitions = {
            "demo_request": {"when": "has_contact_info", "then": "success"}
        }
        result = resolver.resolve_transition(
            intent="demo_request",
            transitions=transitions,
            ctx=context_without_data
        )
        assert result is None

    def test_no_transition_defined(self, resolver, context_with_data):
        """Test when no transition is defined."""
        result = resolver.resolve_transition(
            intent="undefined",
            transitions={},
            ctx=context_with_data
        )
        assert result is None

    def test_transition_none_value(self, resolver, context_with_data):
        """Test explicit None transition (stay in state)."""
        transitions = {"test": None}
        result = resolver.resolve_transition(
            intent="test",
            transitions=transitions,
            ctx=context_with_data
        )
        assert result is None

# =============================================================================
# TRACING TESTS
# =============================================================================

class TestTracing:
    """Tests for evaluation tracing."""

    def test_trace_simple_rule(self, resolver, context_with_data):
        """Test trace for simple rule."""
        trace = EvaluationTrace(rule_name="greeting", intent="greeting", state="greeting")
        action = resolver.resolve_action(
            intent="greeting",
            state_rules={"greeting": "greet_back"},
            global_rules={},
            ctx=context_with_data,
            trace=trace
        )
        assert trace.resolution == Resolution.SIMPLE
        assert trace.final_action == "greet_back"

    def test_trace_condition_matched(self, resolver, context_with_data):
        """Test trace when condition matches."""
        trace = EvaluationTrace(rule_name="price_question", intent="price_question", state="spin")
        action = resolver.resolve_action(
            intent="price_question",
            state_rules={"price_question": {"when": "has_company_size", "then": "answer"}},
            global_rules={},
            ctx=context_with_data,
            trace=trace
        )
        assert trace.resolution == Resolution.CONDITION_MATCHED
        assert trace.matched_condition == "has_company_size"

    def test_trace_default_used(self, resolver, context_without_data):
        """Test trace when default is used."""
        trace = EvaluationTrace(rule_name="price_question", intent="price_question", state="spin")
        action = resolver.resolve_action(
            intent="price_question",
            state_rules={
                "price_question": [
                    {"when": "has_company_size", "then": "answer"},
                    "deflect"
                ]
            },
            global_rules={},
            ctx=context_without_data,
            trace=trace
        )
        assert trace.resolution == Resolution.DEFAULT
        assert trace.final_action == "deflect"

    def test_trace_fallback(self, resolver, context_with_data):
        """Test trace when falling back to default action."""
        trace = EvaluationTrace(rule_name="unknown", intent="unknown", state="state")
        action = resolver.resolve_action(
            intent="unknown",
            state_rules={},
            global_rules={},
            ctx=context_with_data,
            trace=trace
        )
        assert trace.resolution == Resolution.FALLBACK

    def test_trace_records_condition_checks(self, resolver, context_without_data):
        """Test that trace records condition evaluations."""
        trace = EvaluationTrace(rule_name="test", intent="test", state="state")
        action = resolver.resolve_action(
            intent="test",
            state_rules={
                "test": [
                    {"when": "has_company_size", "then": "action1"},
                    {"when": "has_pricing_data", "then": "action2"},
                    "default"
                ]
            },
            global_rules={},
            ctx=context_without_data,
            trace=trace
        )
        # Should have checked both conditions
        assert trace.conditions_checked == 2

# =============================================================================
# CONFIG VALIDATION TESTS
# =============================================================================

class TestConfigValidation:
    """Tests for config validation."""

    def test_valid_config(self, resolver):
        """Test validation of valid config."""
        states_config = {
            "greeting": {
                "rules": {"greeting": "greet_back"},
                "transitions": {"agreement": "spin_situation"}
            },
            "spin_situation": {
                "rules": {},
                "transitions": {}
            }
        }
        result = resolver.validate_config(states_config)
        assert result.is_valid is True

    def test_unknown_condition_error(self, resolver):
        """Test validation catches unknown conditions."""
        states_config = {
            "state": {
                "rules": {
                    "intent": {"when": "nonexistent_condition", "then": "action"}
                },
                "transitions": {}
            }
        }
        result = resolver.validate_config(states_config)
        assert result.is_valid is False
        assert any(e.error_type == "unknown_condition" for e in result.errors)

    def test_unknown_target_state_error(self, resolver):
        """Test validation catches unknown target states."""
        states_config = {
            "state": {
                "rules": {},
                "transitions": {"intent": "nonexistent_state"}
            }
        }
        result = resolver.validate_config(states_config)
        assert result.is_valid is False
        assert any(e.error_type == "unknown_target_state" for e in result.errors)

    def test_valid_conditional_transition(self, resolver):
        """Test validation of valid conditional transition."""
        states_config = {
            "state1": {
                "rules": {},
                "transitions": {
                    "intent": {"when": "has_company_size", "then": "state2"}
                }
            },
            "state2": {"rules": {}, "transitions": {}}
        }
        result = resolver.validate_config(states_config)
        assert result.is_valid is True

    def test_chain_validation(self, resolver):
        """Test validation of rule chains."""
        states_config = {
            "state1": {
                "rules": {
                    "intent": [
                        {"when": "has_company_size", "then": "action1"},
                        {"when": "always_true", "then": "action2"},
                        "default"
                    ]
                },
                "transitions": {}
            }
        }
        result = resolver.validate_config(states_config)
        assert result.is_valid is True

    def test_chain_with_unknown_condition(self, resolver):
        """Test validation catches unknown condition in chain."""
        states_config = {
            "state": {
                "rules": {
                    "intent": [
                        {"when": "unknown_cond", "then": "action"},
                        "default"
                    ]
                },
                "transitions": {}
            }
        }
        result = resolver.validate_config(states_config)
        assert result.is_valid is False

    def test_global_rules_validation(self, resolver):
        """Test validation of global rules."""
        states_config = {
            "state": {"rules": {}, "transitions": {}}
        }
        global_rules = {
            "intent": {"when": "unknown", "then": "action"}
        }
        result = resolver.validate_config(states_config, global_rules)
        assert result.is_valid is False

    def test_missing_when_key_validation(self, resolver):
        """Test validation catches missing 'when' key."""
        states_config = {
            "state": {
                "rules": {"intent": {"then": "action"}},
                "transitions": {}
            }
        }
        result = resolver.validate_config(states_config)
        assert result.is_valid is False
        assert any(e.error_type == "missing_key" for e in result.errors)

# =============================================================================
# FACTORY FUNCTION TESTS
# =============================================================================

class TestFactoryFunction:
    """Tests for create_resolver factory function."""

    def test_create_with_custom_registry(self, test_registry):
        """Test creating resolver with custom registry."""
        resolver = create_resolver(test_registry)
        assert resolver.registry is test_registry

    def test_create_with_default_registry(self):
        """Test creating resolver with default registry."""
        # This uses the sm_registry from conditions module
        resolver = create_resolver()
        assert resolver.registry is not None

    def test_create_with_default_registry_default_fallback_no_type_error(self):
        """Unknown intent fallback should work with default create_resolver()."""
        resolver = create_resolver()

        result = resolver.resolve_action(
            intent="totally_unknown_intent_for_logging_contract",
            state_rules={},
            global_rules={},
            ctx=SimpleContext(),
        )

        assert result.action == "continue_current_goal"

# =============================================================================
# ERROR EXCEPTION TESTS
# =============================================================================

class TestExceptions:
    """Tests for custom exceptions."""

    def test_unknown_condition_error_message(self):
        """Test UnknownConditionError message format."""
        error = UnknownConditionError("cond", "rule", "state")
        assert "cond" in str(error)
        assert "rule" in str(error)
        assert "state" in str(error)

    def test_unknown_target_state_error_message(self):
        """Test UnknownTargetStateError message format."""
        error = UnknownTargetStateError("target", "rule", "state")
        assert "target" in str(error)
        assert "rule" in str(error)

    def test_invalid_rule_format_error_message(self):
        """Test InvalidRuleFormatError message format."""
        error = InvalidRuleFormatError("rule", "reason", "state")
        assert "rule" in str(error)
        assert "reason" in str(error)

# =============================================================================
# INTEGRATION TESTS
# =============================================================================

# =============================================================================
# ADDITIONAL COVERAGE TESTS
# =============================================================================

class TestAdditionalCoverage:
    """Tests for additional coverage of edge cases."""

    def test_transition_without_rule_traces(self, resolver, context_with_data):
        """Test trace when transition rule doesn't exist."""
        trace = EvaluationTrace(rule_name="unknown", intent="unknown", state="state")
        result = resolver.resolve_transition(
            intent="nonexistent",
            transitions={},
            ctx=context_with_data,
            trace=trace
        )
        assert result is None
        assert trace.resolution == Resolution.NONE

    def test_none_rule_traces(self, resolver, context_with_data):
        """Test trace when rule is explicitly None."""
        trace = EvaluationTrace(rule_name="test", intent="test", state="state")
        result = resolver.resolve_transition(
            intent="test",
            transitions={"test": None},
            ctx=context_with_data,
            trace=trace
        )
        assert result is None
        assert trace.resolution == Resolution.NONE

    def test_string_in_middle_of_chain(self, resolver, context_with_data):
        """Test string in middle of chain (not at end)."""
        # The string "immediate_action" is in the middle, not at the end
        state_rules = {
            "test": [
                {"when": "always_false", "then": "action1"},
                "immediate_action",  # This should be returned immediately
                {"when": "always_true", "then": "action2"},
            ]
        }
        action = resolver.resolve_action(
            intent="test",
            state_rules=state_rules,
            global_rules={},
            ctx=context_with_data
        )
        assert action == "immediate_action"

    def test_string_in_middle_of_chain_with_trace(self, resolver, context_with_data):
        """Test trace when string at end of chain is hit (as default)."""
        trace = EvaluationTrace(rule_name="test", intent="test", state="state")
        state_rules = {
            "test": [
                {"when": "always_false", "then": "action1"},
                "immediate_action",  # At end of chain, this is the default
            ]
        }
        action = resolver.resolve_action(
            intent="test",
            state_rules=state_rules,
            global_rules={},
            ctx=context_with_data,
            trace=trace
        )
        assert action == "immediate_action"
        # String at end is treated as DEFAULT, not SIMPLE
        assert trace.resolution == Resolution.DEFAULT

    def test_none_in_middle_of_chain(self, resolver, context_with_data):
        """Test None in middle of chain (not at end)."""
        transitions = {
            "test": [
                {"when": "always_false", "then": "state1"},
                None,  # This should be returned immediately
                {"when": "always_true", "then": "state2"},
            ]
        }
        result = resolver.resolve_transition(
            intent="test",
            transitions=transitions,
            ctx=context_with_data
        )
        assert result is None

    def test_none_in_middle_of_chain_with_trace(self, resolver, context_with_data):
        """Test trace when None at end of chain is hit (as default)."""
        trace = EvaluationTrace(rule_name="test", intent="test", state="state")
        transitions = {
            "test": [
                {"when": "always_false", "then": "state1"},
                None,  # At end of chain, this is the default
            ]
        }
        result = resolver.resolve_transition(
            intent="test",
            transitions=transitions,
            ctx=context_with_data,
            trace=trace
        )
        assert result is None
        # None at end is treated as DEFAULT
        assert trace.resolution == Resolution.DEFAULT

    def test_chain_no_match_no_default(self, resolver, context_with_data):
        """Test chain with no match and no default returns None."""
        state_rules = {
            "test": [
                {"when": "always_false", "then": "action1"},
                {"when": "always_false", "then": "action2"},
            ]
        }
        action = resolver.resolve_action(
            intent="test",
            state_rules=state_rules,
            global_rules={"test": "global_default"},  # Should fall through to global
            ctx=context_with_data
        )
        assert action == "global_default"

    def test_validate_missing_then_key(self, resolver):
        """Test validation catches missing 'then' key in conditional rule."""
        states_config = {
            "state": {
                "rules": {
                    "intent": {"when": "always_true"}  # Missing 'then'
                },
                "transitions": {}
            }
        }
        result = resolver.validate_config(states_config)
        assert result.is_valid is False
        assert any(e.error_type == "missing_key" and "'then'" in e.message for e in result.errors)

    def test_validate_conditional_transition_unknown_target(self, resolver):
        """Test validation catches unknown target in conditional transition."""
        states_config = {
            "state1": {
                "rules": {},
                "transitions": {
                    "intent": {"when": "always_true", "then": "nonexistent_state"}
                }
            }
        }
        result = resolver.validate_config(states_config)
        assert result.is_valid is False
        assert any(e.error_type == "unknown_target_state" for e in result.errors)

    def test_validate_empty_chain(self, resolver):
        """Test validation catches empty chain in config."""
        states_config = {
            "state": {
                "rules": {"intent": []},
                "transitions": {}
            }
        }
        result = resolver.validate_config(states_config)
        assert result.is_valid is False
        assert any(e.error_type == "empty_chain" for e in result.errors)

    def test_validate_chain_unknown_target_in_transition(self, resolver):
        """Test validation catches unknown target in chain transition."""
        states_config = {
            "state1": {
                "rules": {},
                "transitions": {
                    "intent": [
                        {"when": "always_true", "then": "nonexistent_state"},
                        "also_nonexistent"
                    ]
                }
            }
        }
        result = resolver.validate_config(states_config)
        assert result.is_valid is False
        # Should have errors for both the conditional and the default
        target_errors = [e for e in result.errors if e.error_type == "unknown_target_state"]
        assert len(target_errors) >= 1

    def test_validate_invalid_item_in_chain(self, resolver):
        """Test validation catches invalid item type in chain."""
        states_config = {
            "state": {
                "rules": {
                    "intent": [
                        {"when": "always_true", "then": "action"},
                        123,  # Invalid type (int)
                        "default"
                    ]
                },
                "transitions": {}
            }
        }
        result = resolver.validate_config(states_config)
        assert result.is_valid is False
        assert any(e.error_type == "invalid_chain_item" for e in result.errors)

    def test_validate_invalid_rule_format(self, resolver):
        """Test validation catches invalid rule format."""
        states_config = {
            "state": {
                "rules": {
                    "intent": 123  # Invalid type (int)
                },
                "transitions": {}
            }
        }
        result = resolver.validate_config(states_config)
        assert result.is_valid is False
        assert any(e.error_type == "invalid_format" for e in result.errors)

    def test_string_truly_in_middle_of_chain(self, resolver, context_with_data):
        """Test string truly in middle of chain (with more items after it)."""
        state_rules = {
            "test": [
                {"when": "always_false", "then": "action1"},
                "middle_string",  # This is NOT at end - there's more after
                {"when": "always_true", "then": "action2"},
                "final_default"
            ]
        }
        action = resolver.resolve_action(
            intent="test",
            state_rules=state_rules,
            global_rules={},
            ctx=context_with_data
        )
        # Should return middle_string because it's the first non-conditional match
        assert action == "middle_string"

    def test_string_truly_in_middle_with_trace(self, resolver, context_with_data):
        """Test trace for string truly in middle of chain."""
        trace = EvaluationTrace(rule_name="test", intent="test", state="state")
        state_rules = {
            "test": [
                {"when": "always_false", "then": "action1"},
                "middle_string",
                {"when": "always_true", "then": "action2"},
                "default"
            ]
        }
        action = resolver.resolve_action(
            intent="test",
            state_rules=state_rules,
            global_rules={},
            ctx=context_with_data,
            trace=trace
        )
        assert action == "middle_string"
        assert trace.resolution == Resolution.SIMPLE

    def test_none_truly_in_middle_of_chain(self, resolver, context_with_data):
        """Test None truly in middle of chain (with more items after it)."""
        transitions = {
            "test": [
                {"when": "always_false", "then": "state1"},
                None,  # This is NOT at end - there's more after
                {"when": "always_true", "then": "state2"},
                None
            ]
        }
        result = resolver.resolve_transition(
            intent="test",
            transitions=transitions,
            ctx=context_with_data
        )
        # Should return None because it's the first non-conditional match
        assert result is None

    def test_none_truly_in_middle_with_trace(self, resolver, context_with_data):
        """Test trace for None truly in middle of chain."""
        trace = EvaluationTrace(rule_name="test", intent="test", state="state")
        transitions = {
            "test": [
                {"when": "always_false", "then": "state1"},
                None,  # Not at end
                {"when": "always_true", "then": "state2"},
                "default"
            ]
        }
        result = resolver.resolve_transition(
            intent="test",
            transitions=transitions,
            ctx=context_with_data,
            trace=trace
        )
        assert result is None
        assert trace.resolution == Resolution.NONE

    def test_validate_missing_when_key_in_conditional(self, resolver):
        """Test validation catches missing 'when' key in conditional rule."""
        states_config = {
            "state": {
                "rules": {},
                "transitions": {
                    "intent": {"then": "target"}  # Missing 'when'
                }
            }
        }
        result = resolver.validate_config(states_config)
        assert result.is_valid is False
        assert any(e.error_type == "missing_key" and "'when'" in e.message for e in result.errors)

    def test_validate_none_in_chain_is_valid(self, resolver):
        """Test that None in chain is valid for validation."""
        states_config = {
            "state1": {
                "rules": {},
                "transitions": {
                    "intent": [
                        {"when": "always_true", "then": "state2"},
                        None  # Valid
                    ]
                }
            },
            "state2": {"rules": {}, "transitions": {}}
        }
        result = resolver.validate_config(states_config)
        assert result.is_valid is True

    def test_evaluate_invalid_rule_type_raises_error(self, resolver, context_with_data):
        """Test that evaluating a rule with invalid type raises error."""
        # Create a mock rules dict with an invalid type
        # The resolver._evaluate_rule is called internally
        # We can test this by calling resolve_action with a state_rules
        # that has an invalid type value
        state_rules = {"test": 123}  # int is not a valid rule type

        with pytest.raises(InvalidRuleFormatError) as exc_info:
            resolver.resolve_action(
                intent="test",
                state_rules=state_rules,
                global_rules={},
                ctx=context_with_data
            )
        assert "unexpected type" in str(exc_info.value)
        assert "int" in str(exc_info.value)

    def test_validate_none_transition_is_valid(self, resolver):
        """Test that None as transition value is valid."""
        states_config = {
            "state": {
                "rules": {},
                "transitions": {
                    "intent": None  # Valid - means stay in current state
                }
            }
        }
        result = resolver.validate_config(states_config)
        assert result.is_valid is True

class TestIntegration:
    """Integration tests for realistic scenarios."""

    def test_price_question_scenario(self, resolver):
        """Test price_question scenario from plan section 5.1."""
        # Context without data - should deflect
        ctx_no_data = SimpleContext(collected_data={}, state="spin_situation")

        # Context with data - should answer
        ctx_with_data = SimpleContext(
            collected_data={"company_size": 50},
            state="spin_situation"
        )

        rules = {
            "price_question": [
                {"when": "has_pricing_data", "then": "answer_with_facts"},
                "deflect_and_continue"
            ]
        }

        action_no_data = resolver.resolve_action(
            "price_question", rules, {}, ctx_no_data
        )
        action_with_data = resolver.resolve_action(
            "price_question", rules, {}, ctx_with_data
        )

        assert action_no_data == "deflect_and_continue"
        assert action_with_data == "answer_with_facts"

    def test_demo_request_transition_scenario(self, resolver):
        """Test demo_request transition scenario from plan section 5.5."""
        # Context without contact - stay
        ctx_no_contact = SimpleContext(collected_data={}, state="close")

        # Context with contact - go to success
        ctx_with_contact = SimpleContext(
            collected_data={"email": "test@example.com"},
            state="close"
        )

        transitions = {
            "demo_request": [
                {"when": "has_contact_info", "then": "success"},
                None
            ]
        }

        result_no_contact = resolver.resolve_transition(
            "demo_request", transitions, ctx_no_contact
        )
        result_with_contact = resolver.resolve_transition(
            "demo_request", transitions, ctx_with_contact
        )

        assert result_no_contact is None  # Stay in close
        assert result_with_contact == "success"

    def test_full_rule_result(self, resolver, context_with_data):
        """Test getting full RuleResult with action and transition."""
        state_rules = {"price_question": "answer_with_facts"}
        transitions = {"price_question": "presentation"}

        action = resolver.resolve_action(
            "price_question", state_rules, {}, context_with_data
        )
        next_state = resolver.resolve_transition(
            "price_question", transitions, context_with_data
        )

        result = RuleResult(action=action, next_state=next_state)
        assert result.action == "answer_with_facts"
        assert result.next_state == "presentation"

        # Test tuple unpacking
        act, st = result
        assert act == "answer_with_facts"
        assert st == "presentation"
