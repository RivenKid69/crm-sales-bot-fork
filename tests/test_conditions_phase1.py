"""
Tests for Conditional Rules System - Phase 1: Foundation.

This test suite provides 100% coverage for:
- BaseContext and SimpleContext (base.py)
- ConditionRegistry, errors, metadata (registry.py)
- EvaluationTrace, TraceCollector (trace.py)
- Shared conditions (shared/__init__.py)
- ConditionRegistries aggregator (__init__.py)

Run with: pytest tests/test_conditions_phase1.py -v
"""

import pytest
from typing import Dict, Any
from datetime import datetime
from dataclasses import dataclass

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
    InvalidConditionSignatureError
)
from src.conditions.trace import (
    EvaluationTrace,
    TraceCollector,
    TraceSummary,
    ConditionEntry,
    Resolution
)
from src.conditions.shared import (
    shared_registry,
    has_collected_data,
    has_company_size,
    has_users_count,
    has_pricing_data,
    has_contact_info,
    has_pain_point,
    has_competitor_mention,
    has_role,
    has_industry,
    is_initial_state,
    is_success_state,
    is_failed_state,
    is_terminal_state,
    is_first_turn,
    is_early_conversation,
    is_late_conversation,
    is_extended_conversation,
    check_field,
    has_any_field,
    has_all_fields,
    get_field_value
)
from src.conditions import (
    ConditionRegistries
)


# =============================================================================
# TEST FIXTURES
# =============================================================================

@pytest.fixture
def simple_context():
    """Create a simple context for testing."""
    return SimpleContext(
        collected_data={"company_size": 50, "users_count": 10},
        state="spin_situation",
        turn_number=5
    )


@pytest.fixture
def empty_context():
    """Create an empty context for testing."""
    return SimpleContext(
        collected_data={},
        state="initial",
        turn_number=0
    )


@pytest.fixture
def test_registry():
    """Create a fresh registry for each test."""
    return ConditionRegistry("test_registry", SimpleContext)


@pytest.fixture
def populated_registry(test_registry):
    """Create a registry with some conditions registered."""
    @test_registry.condition("always_true", category="test")
    def always_true(ctx: SimpleContext) -> bool:
        return True

    @test_registry.condition("always_false", category="test")
    def always_false(ctx: SimpleContext) -> bool:
        return False

    @test_registry.condition(
        "has_data",
        description="Check if data exists",
        requires_fields={"company_size"},
        category="data"
    )
    def has_data(ctx: SimpleContext) -> bool:
        return bool(ctx.collected_data.get("company_size"))

    return test_registry


# =============================================================================
# BASE CONTEXT TESTS
# =============================================================================

class TestBaseContext:
    """Tests for BaseContext protocol and SimpleContext implementation."""

    def test_simple_context_creation(self):
        """Test creating a SimpleContext with all fields."""
        ctx = SimpleContext(
            collected_data={"key": "value"},
            state="test_state",
            turn_number=10
        )
        assert ctx.collected_data == {"key": "value"}
        assert ctx.state == "test_state"
        assert ctx.turn_number == 10

    def test_simple_context_defaults(self):
        """Test SimpleContext with default values."""
        ctx = SimpleContext()
        assert ctx.collected_data == {}
        assert ctx.state == ""
        assert ctx.turn_number == 0

    def test_simple_context_negative_turn_raises(self):
        """Test that negative turn_number raises ValueError."""
        with pytest.raises(ValueError, match="turn_number cannot be negative"):
            SimpleContext(turn_number=-1)

    def test_simple_context_factory_method(self):
        """Test create_test_context factory method."""
        ctx = SimpleContext.create_test_context(
            collected_data={"test": "data"},
            state="test",
            turn_number=5
        )
        assert ctx.collected_data == {"test": "data"}
        assert ctx.state == "test"
        assert ctx.turn_number == 5

    def test_simple_context_factory_defaults(self):
        """Test create_test_context with defaults."""
        ctx = SimpleContext.create_test_context()
        assert ctx.collected_data == {}
        assert ctx.state == "initial"
        assert ctx.turn_number == 0

    def test_is_valid_context_with_simple_context(self):
        """Test is_valid_context with SimpleContext."""
        ctx = SimpleContext()
        assert is_valid_context(ctx) is True

    def test_is_valid_context_with_invalid_object(self):
        """Test is_valid_context with non-context object."""
        assert is_valid_context("not a context") is False
        assert is_valid_context(123) is False
        assert is_valid_context(None) is False

    def test_base_context_protocol_compliance(self):
        """Test that SimpleContext implements BaseContext protocol."""
        ctx = SimpleContext()
        assert isinstance(ctx, BaseContext)

    def test_custom_context_protocol_compliance(self):
        """Test that custom context can implement BaseContext."""
        @dataclass
        class CustomContext:
            collected_data: Dict[str, Any]
            state: str
            turn_number: int

        custom = CustomContext(
            collected_data={"x": 1},
            state="custom",
            turn_number=3
        )
        assert isinstance(custom, BaseContext)


# =============================================================================
# CONDITION REGISTRY TESTS
# =============================================================================

class TestConditionRegistry:
    """Tests for ConditionRegistry class."""

    def test_registry_creation(self):
        """Test creating a new registry."""
        registry = ConditionRegistry("test", SimpleContext)
        assert registry.name == "test"
        assert registry.context_type == SimpleContext
        assert len(registry) == 0

    def test_registry_with_allow_overwrite(self):
        """Test registry with allow_overwrite flag."""
        registry = ConditionRegistry("test", SimpleContext, allow_overwrite=True)
        assert registry.allow_overwrite is True

    def test_condition_decorator_registration(self, test_registry):
        """Test registering condition with decorator."""
        @test_registry.condition("test_cond", category="test")
        def test_cond(ctx: SimpleContext) -> bool:
            return True

        assert test_registry.has("test_cond")
        assert "test_cond" in test_registry
        assert len(test_registry) == 1

    def test_condition_with_description(self, test_registry):
        """Test condition with explicit description."""
        @test_registry.condition("described", description="A test condition")
        def described(ctx: SimpleContext) -> bool:
            return True

        meta = test_registry.get("described")
        assert meta.description == "A test condition"

    def test_condition_with_docstring_fallback(self, test_registry):
        """Test condition uses docstring as description fallback."""
        @test_registry.condition("documented")
        def documented(ctx: SimpleContext) -> bool:
            """This is the docstring."""
            return True

        meta = test_registry.get("documented")
        assert meta.description == "This is the docstring."

    def test_condition_with_requires_fields(self, test_registry):
        """Test condition with requires_fields."""
        @test_registry.condition(
            "with_fields",
            requires_fields={"field1", "field2"}
        )
        def with_fields(ctx: SimpleContext) -> bool:
            return True

        meta = test_registry.get("with_fields")
        assert meta.requires_fields == {"field1", "field2"}

    def test_condition_with_category(self, test_registry):
        """Test condition with category."""
        @test_registry.condition("categorized", category="special")
        def categorized(ctx: SimpleContext) -> bool:
            return True

        assert "categorized" in test_registry.list_by_category("special")
        assert "special" in test_registry.get_categories()

    def test_duplicate_registration_raises(self, test_registry):
        """Test that duplicate registration raises error."""
        @test_registry.condition("dupe")
        def dupe1(ctx: SimpleContext) -> bool:
            return True

        with pytest.raises(ConditionAlreadyRegisteredError):
            @test_registry.condition("dupe")
            def dupe2(ctx: SimpleContext) -> bool:
                return False

    def test_allow_overwrite_permits_duplicate(self):
        """Test that allow_overwrite permits duplicate registration."""
        registry = ConditionRegistry("test", SimpleContext, allow_overwrite=True)

        @registry.condition("overwritable")
        def v1(ctx: SimpleContext) -> bool:
            return True

        @registry.condition("overwritable")
        def v2(ctx: SimpleContext) -> bool:
            return False

        # Should have the second version
        ctx = SimpleContext()
        assert registry.evaluate("overwritable", ctx) is False

    def test_invalid_signature_no_params_raises(self, test_registry):
        """Test that condition with no params raises error."""
        with pytest.raises(InvalidConditionSignatureError):
            @test_registry.condition("no_params")
            def no_params() -> bool:
                return True

    def test_invalid_signature_multiple_params_raises(self, test_registry):
        """Test that condition with multiple params raises error."""
        with pytest.raises(InvalidConditionSignatureError):
            @test_registry.condition("multi_params")
            def multi_params(ctx: SimpleContext, extra: int) -> bool:
                return True

    def test_register_programmatic(self, test_registry, simple_context):
        """Test programmatic registration (non-decorator)."""
        def my_condition(ctx: SimpleContext) -> bool:
            return ctx.turn_number > 3

        test_registry.register(
            "my_condition",
            my_condition,
            description="Test condition",
            category="test"
        )

        assert test_registry.has("my_condition")
        assert test_registry.evaluate("my_condition", simple_context) is True

    def test_unregister_existing(self, populated_registry):
        """Test unregistering an existing condition."""
        assert populated_registry.has("always_true")
        result = populated_registry.unregister("always_true")
        assert result is True
        assert not populated_registry.has("always_true")

    def test_unregister_nonexistent(self, test_registry):
        """Test unregistering a non-existent condition."""
        result = test_registry.unregister("nonexistent")
        assert result is False

    def test_evaluate_success(self, populated_registry, simple_context):
        """Test successful condition evaluation."""
        result = populated_registry.evaluate("always_true", simple_context)
        assert result is True

        result = populated_registry.evaluate("always_false", simple_context)
        assert result is False

    def test_evaluate_not_found_raises(self, test_registry, simple_context):
        """Test evaluation of non-existent condition raises error."""
        with pytest.raises(ConditionNotFoundError) as exc_info:
            test_registry.evaluate("nonexistent", simple_context)
        assert "nonexistent" in str(exc_info.value)

    def test_evaluate_with_trace(self, populated_registry, simple_context):
        """Test evaluation records to trace."""
        trace = EvaluationTrace(rule_name="test")
        populated_registry.evaluate("has_data", simple_context, trace)

        assert len(trace.entries) == 1
        assert trace.entries[0].condition_name == "has_data"
        assert trace.entries[0].result is True

    def test_evaluate_error_raises(self, test_registry, simple_context):
        """Test that evaluation errors are wrapped."""
        @test_registry.condition("raises")
        def raises(ctx: SimpleContext) -> bool:
            raise ValueError("Something went wrong")

        with pytest.raises(ConditionEvaluationError) as exc_info:
            test_registry.evaluate("raises", simple_context)
        assert "Something went wrong" in str(exc_info.value)

    def test_get_existing(self, populated_registry):
        """Test getting metadata for existing condition."""
        meta = populated_registry.get("always_true")
        assert meta is not None
        assert meta.name == "always_true"
        assert meta.category == "test"

    def test_get_nonexistent(self, test_registry):
        """Test getting metadata for non-existent condition."""
        meta = test_registry.get("nonexistent")
        assert meta is None

    def test_has_existing(self, populated_registry):
        """Test has() for existing condition."""
        assert populated_registry.has("always_true") is True

    def test_has_nonexistent(self, test_registry):
        """Test has() for non-existent condition."""
        assert test_registry.has("nonexistent") is False

    def test_list_all(self, populated_registry):
        """Test listing all conditions."""
        conditions = populated_registry.list_all()
        assert "always_true" in conditions
        assert "always_false" in conditions
        assert "has_data" in conditions

    def test_list_by_category(self, populated_registry):
        """Test listing conditions by category."""
        test_conds = populated_registry.list_by_category("test")
        assert "always_true" in test_conds
        assert "always_false" in test_conds

        data_conds = populated_registry.list_by_category("data")
        assert "has_data" in data_conds

    def test_list_by_category_nonexistent(self, test_registry):
        """Test listing conditions for non-existent category."""
        result = test_registry.list_by_category("nonexistent")
        assert result == []

    def test_get_categories(self, populated_registry):
        """Test getting all categories."""
        categories = populated_registry.get_categories()
        assert "test" in categories
        assert "data" in categories

    def test_validate_all_success(self, populated_registry):
        """Test validate_all with valid conditions."""
        result = populated_registry.validate_all(SimpleContext)
        assert result.is_valid
        assert len(result.passed) == 3
        assert len(result.failed) == 0
        assert len(result.errors) == 0

    def test_validate_all_with_non_bool_return(self, test_registry):
        """Test validate_all catches non-bool returns."""
        @test_registry.condition("returns_string")
        def returns_string(ctx: SimpleContext):
            return "not a bool"  # type: ignore

        result = test_registry.validate_all(SimpleContext)
        assert not result.is_valid
        assert len(result.failed) == 1
        assert "returns_string" in result.failed[0]["name"]

    def test_validate_all_with_error(self, test_registry):
        """Test validate_all catches errors."""
        @test_registry.condition("raises_error")
        def raises_error(ctx: SimpleContext) -> bool:
            raise RuntimeError("Boom")

        result = test_registry.validate_all(SimpleContext)
        assert not result.is_valid
        assert len(result.errors) == 1
        assert "raises_error" in result.errors[0]["name"]

    def test_validation_result_properties(self):
        """Test ValidationResult properties."""
        result = ValidationResult(
            passed=["a", "b"],
            failed=[{"name": "c", "reason": "bad"}],
            errors=[]
        )
        assert result.total_count == 3
        assert result.is_valid is False

        valid_result = ValidationResult(passed=["a"], failed=[], errors=[])
        assert valid_result.is_valid is True

    def test_validation_result_to_dict(self):
        """Test ValidationResult.to_dict()."""
        result = ValidationResult(
            passed=["a"],
            failed=[{"name": "b", "reason": "bad"}],
            errors=[{"name": "c", "error": "boom"}]
        )
        d = result.to_dict()
        assert d["passed"] == ["a"]
        assert d["failed"] == [{"name": "b", "reason": "bad"}]
        assert d["errors"] == [{"name": "c", "error": "boom"}]
        assert d["is_valid"] is False
        assert d["total_count"] == 3

    def test_get_documentation(self, populated_registry):
        """Test documentation generation."""
        docs = populated_registry.get_documentation()
        assert "Test Registry Conditions" in docs
        assert "always_true" in docs
        assert "has_data" in docs
        assert "SimpleContext" in docs

    def test_get_stats(self, populated_registry):
        """Test statistics generation."""
        stats = populated_registry.get_stats()
        assert stats["name"] == "test_registry"
        assert stats["context_type"] == "SimpleContext"
        assert stats["total_conditions"] == 3
        assert stats["total_categories"] == 2

    def test_len(self, populated_registry):
        """Test __len__ method."""
        assert len(populated_registry) == 3

    def test_contains(self, populated_registry):
        """Test __contains__ method."""
        assert "always_true" in populated_registry
        assert "nonexistent" not in populated_registry

    def test_repr(self, populated_registry):
        """Test __repr__ method."""
        repr_str = repr(populated_registry)
        assert "test_registry" in repr_str
        assert "SimpleContext" in repr_str
        assert "3" in repr_str


# =============================================================================
# ERROR TESTS
# =============================================================================

class TestErrors:
    """Tests for custom exceptions."""

    def test_condition_not_found_error(self):
        """Test ConditionNotFoundError attributes."""
        error = ConditionNotFoundError("my_cond", "my_registry")
        assert error.condition_name == "my_cond"
        assert error.registry_name == "my_registry"
        assert "my_cond" in str(error)
        assert "my_registry" in str(error)

    def test_condition_not_found_error_without_registry(self):
        """Test ConditionNotFoundError without registry name."""
        error = ConditionNotFoundError("my_cond")
        assert "my_cond" in str(error)
        assert "registry" not in str(error).lower() or "in registry" not in str(error)

    def test_condition_evaluation_error(self):
        """Test ConditionEvaluationError attributes."""
        original = ValueError("bad value")
        error = ConditionEvaluationError("my_cond", original, "my_registry")
        assert error.condition_name == "my_cond"
        assert error.original_error == original
        assert error.registry_name == "my_registry"
        assert "my_cond" in str(error)
        assert "bad value" in str(error)

    def test_condition_already_registered_error(self):
        """Test ConditionAlreadyRegisteredError attributes."""
        error = ConditionAlreadyRegisteredError("my_cond", "my_registry")
        assert error.condition_name == "my_cond"
        assert error.registry_name == "my_registry"
        assert "my_cond" in str(error)
        assert "already registered" in str(error)

    def test_invalid_condition_signature_error(self):
        """Test InvalidConditionSignatureError attributes."""
        error = InvalidConditionSignatureError("my_cond", "must accept one param")
        assert error.condition_name == "my_cond"
        assert error.reason == "must accept one param"
        assert "my_cond" in str(error)
        assert "must accept one param" in str(error)


# =============================================================================
# TRACE TESTS
# =============================================================================

class TestEvaluationTrace:
    """Tests for EvaluationTrace class."""

    def test_trace_creation(self):
        """Test creating a new trace."""
        trace = EvaluationTrace(
            rule_name="test_rule",
            intent="test_intent",
            state="test_state",
            domain="test_domain"
        )
        assert trace.rule_name == "test_rule"
        assert trace.intent == "test_intent"
        assert trace.state == "test_state"
        assert trace.domain == "test_domain"
        assert trace.resolution == Resolution.NONE
        assert trace.final_action is None

    def test_trace_record(self, simple_context):
        """Test recording a condition evaluation."""
        trace = EvaluationTrace(rule_name="test")
        trace.record(
            condition_name="has_data",
            result=True,
            ctx=simple_context,
            relevant_fields={"company_size"},
            elapsed_ms=1.5
        )

        assert len(trace.entries) == 1
        entry = trace.entries[0]
        assert entry.condition_name == "has_data"
        assert entry.result is True
        assert entry.elapsed_ms == 1.5
        assert entry.field_values == {"company_size": 50}

    def test_trace_set_result(self):
        """Test setting the final result."""
        trace = EvaluationTrace(rule_name="test")
        trace.set_result(
            final_action="do_something",
            resolution=Resolution.CONDITION_MATCHED,
            matched_condition="has_data"
        )

        assert trace.final_action == "do_something"
        assert trace.resolution == Resolution.CONDITION_MATCHED
        assert trace.matched_condition == "has_data"
        assert trace.end_time is not None

    def test_trace_properties(self, simple_context):
        """Test computed properties."""
        trace = EvaluationTrace(rule_name="test")
        trace.record("cond1", True, simple_context, elapsed_ms=1.0)
        trace.record("cond2", False, simple_context, elapsed_ms=2.0)
        trace.record("cond3", True, simple_context, elapsed_ms=0.5)

        assert trace.conditions_checked == 3
        assert trace.conditions_passed == 2
        assert trace.total_elapsed_ms == 3.5

    def test_trace_to_dict(self, simple_context):
        """Test conversion to dictionary."""
        trace = EvaluationTrace(
            rule_name="test",
            intent="price_question",
            state="spin",
            domain="state_machine"
        )
        trace.record("has_data", True, simple_context, {"company_size"}, 1.0)
        trace.set_result("answer", Resolution.CONDITION_MATCHED, "has_data")

        d = trace.to_dict()
        assert d["rule_name"] == "test"
        assert d["intent"] == "price_question"
        assert d["state"] == "spin"
        assert d["domain"] == "state_machine"
        assert d["resolution"] == "condition_matched"
        assert d["final_action"] == "answer"
        assert d["matched_condition"] == "has_data"
        assert d["conditions_checked"] == 1
        assert d["conditions_passed"] == 1
        assert len(d["entries"]) == 1

    def test_trace_to_compact_string(self, simple_context):
        """Test conversion to compact string."""
        trace = EvaluationTrace(rule_name="price_question")
        trace.record("has_data", True, simple_context, {"company_size"}, 1.0)
        trace.set_result("answer_with_facts", Resolution.CONDITION_MATCHED, "has_data")

        compact = trace.to_compact_string()
        assert "[RULE] price_question -> answer_with_facts" in compact
        assert "condition_matched" in compact
        assert "has_data: PASS" in compact

    def test_trace_repr(self):
        """Test __repr__ method."""
        trace = EvaluationTrace(rule_name="test")
        trace.set_result("action", Resolution.SIMPLE)
        repr_str = repr(trace)
        assert "test" in repr_str
        assert "simple" in repr_str


class TestConditionEntry:
    """Tests for ConditionEntry class."""

    def test_entry_creation(self):
        """Test creating a condition entry."""
        entry = ConditionEntry(
            condition_name="test_cond",
            result=True,
            relevant_fields={"field1"},
            field_values={"field1": "value1"},
            elapsed_ms=2.5
        )
        assert entry.condition_name == "test_cond"
        assert entry.result is True
        assert entry.elapsed_ms == 2.5

    def test_entry_to_dict(self):
        """Test entry conversion to dict."""
        entry = ConditionEntry(
            condition_name="test",
            result=True,
            relevant_fields={"f1"},
            field_values={"f1": 10},
            elapsed_ms=1.234
        )
        d = entry.to_dict()
        assert d["condition"] == "test"
        assert d["result"] is True
        assert d["elapsed_ms"] == 1.234
        assert "f1" in d["relevant_fields"]
        assert d["field_values"]["f1"] == 10

    def test_entry_to_compact_string_pass(self):
        """Test compact string for passing condition."""
        entry = ConditionEntry(
            condition_name="has_data",
            result=True,
            field_values={"company_size": 50}
        )
        compact = entry.to_compact_string()
        assert "has_data: PASS" in compact
        assert "company_size=50" in compact

    def test_entry_to_compact_string_fail(self):
        """Test compact string for failing condition."""
        entry = ConditionEntry(
            condition_name="has_data",
            result=False,
            field_values={}
        )
        compact = entry.to_compact_string()
        assert "has_data: FAIL" in compact


class TestResolution:
    """Tests for Resolution enum."""

    def test_resolution_values(self):
        """Test Resolution enum values."""
        assert Resolution.SIMPLE.value == "simple"
        assert Resolution.CONDITION_MATCHED.value == "condition_matched"
        assert Resolution.DEFAULT.value == "default"
        assert Resolution.FALLBACK.value == "fallback"
        assert Resolution.NONE.value == "none"


class TestTraceCollector:
    """Tests for TraceCollector class."""

    def test_collector_creation(self):
        """Test creating a trace collector."""
        collector = TraceCollector()
        assert len(collector) == 0

    def test_collector_create_trace(self):
        """Test creating traces through collector."""
        collector = TraceCollector()
        trace = collector.create_trace(
            rule_name="test",
            intent="price_question",
            state="spin",
            domain="state_machine"
        )

        assert len(collector) == 1
        assert trace.rule_name == "test"
        assert trace in collector

    def test_collector_add_trace(self):
        """Test adding existing trace."""
        collector = TraceCollector()
        trace = EvaluationTrace(rule_name="external")
        collector.add_trace(trace)

        assert len(collector) == 1
        assert trace in list(collector)

    def test_collector_get_traces(self):
        """Test getting all traces."""
        collector = TraceCollector()
        collector.create_trace("test1")
        collector.create_trace("test2")

        traces = collector.get_traces()
        assert len(traces) == 2

    def test_collector_get_traces_by_domain(self):
        """Test filtering traces by domain."""
        collector = TraceCollector()
        collector.create_trace("t1", domain="state_machine")
        collector.create_trace("t2", domain="policy")
        collector.create_trace("t3", domain="state_machine")

        sm_traces = collector.get_traces_by_domain("state_machine")
        assert len(sm_traces) == 2

        policy_traces = collector.get_traces_by_domain("policy")
        assert len(policy_traces) == 1

    def test_collector_get_traces_by_resolution(self):
        """Test filtering traces by resolution."""
        collector = TraceCollector()

        t1 = collector.create_trace("t1")
        t1.set_result("a1", Resolution.SIMPLE)

        t2 = collector.create_trace("t2")
        t2.set_result("a2", Resolution.CONDITION_MATCHED, "cond")

        t3 = collector.create_trace("t3")
        t3.set_result("a3", Resolution.DEFAULT)

        simple_traces = collector.get_traces_by_resolution(Resolution.SIMPLE)
        assert len(simple_traces) == 1

        matched_traces = collector.get_traces_by_resolution(Resolution.CONDITION_MATCHED)
        assert len(matched_traces) == 1

    def test_collector_get_summary(self, simple_context):
        """Test getting summary statistics."""
        collector = TraceCollector()

        t1 = collector.create_trace("t1", domain="state_machine")
        t1.record("cond1", True, simple_context, elapsed_ms=1.0)
        t1.set_result("action1", Resolution.CONDITION_MATCHED, "cond1")

        t2 = collector.create_trace("t2", domain="state_machine")
        t2.record("cond2", False, simple_context, elapsed_ms=0.5)
        t2.set_result("action2", Resolution.DEFAULT)

        t3 = collector.create_trace("t3", domain="policy")
        t3.set_result("action3", Resolution.SIMPLE)

        summary = collector.get_summary()
        assert summary.total_traces == 3
        assert summary.by_domain["state_machine"] == 2
        assert summary.by_domain["policy"] == 1
        assert summary.by_resolution["condition_matched"] == 1
        assert summary.by_resolution["default"] == 1
        assert summary.by_resolution["simple"] == 1
        assert summary.total_conditions_checked == 2
        assert summary.total_elapsed_ms == 1.5
        assert summary.matched_conditions["cond1"] == 1

    def test_collector_clear(self):
        """Test clearing the collector."""
        collector = TraceCollector()
        collector.create_trace("test")
        assert len(collector) == 1

        collector.clear()
        assert len(collector) == 0

    def test_collector_iteration(self):
        """Test iterating over collector."""
        collector = TraceCollector()
        collector.create_trace("t1")
        collector.create_trace("t2")

        names = [t.rule_name for t in collector]
        assert "t1" in names
        assert "t2" in names

    def test_collector_repr(self):
        """Test __repr__ method."""
        collector = TraceCollector()
        collector.create_trace("test")
        repr_str = repr(collector)
        assert "1" in repr_str


class TestTraceSummary:
    """Tests for TraceSummary class."""

    def test_summary_to_dict(self):
        """Test summary conversion to dict."""
        summary = TraceSummary(
            total_traces=10,
            by_resolution={"simple": 5, "condition_matched": 5},
            by_domain={"state_machine": 10},
            total_conditions_checked=20,
            total_elapsed_ms=15.5,
            matched_conditions={"cond1": 3, "cond2": 2}
        )

        d = summary.to_dict()
        assert d["total_traces"] == 10
        assert d["by_resolution"]["simple"] == 5
        assert d["avg_conditions_per_trace"] == 2.0
        assert d["total_elapsed_ms"] == 15.5

    def test_summary_avg_with_zero_traces(self):
        """Test average calculation with zero traces."""
        summary = TraceSummary(total_traces=0)
        d = summary.to_dict()
        assert d["avg_conditions_per_trace"] == 0


# =============================================================================
# SHARED CONDITIONS TESTS
# =============================================================================

class TestSharedConditions:
    """Tests for shared conditions."""

    def test_shared_registry_exists(self):
        """Test that shared_registry is created."""
        assert shared_registry is not None
        assert shared_registry.name == "shared"

    # Data conditions
    def test_has_collected_data_true(self, simple_context):
        """Test has_collected_data with data."""
        assert has_collected_data(simple_context) is True

    def test_has_collected_data_false(self, empty_context):
        """Test has_collected_data without data."""
        assert has_collected_data(empty_context) is False

    def test_has_company_size_true(self, simple_context):
        """Test has_company_size with data."""
        assert has_company_size(simple_context) is True

    def test_has_company_size_false(self, empty_context):
        """Test has_company_size without data."""
        assert has_company_size(empty_context) is False

    def test_has_users_count_true(self, simple_context):
        """Test has_users_count with data."""
        assert has_users_count(simple_context) is True

    def test_has_users_count_false(self, empty_context):
        """Test has_users_count without data."""
        assert has_users_count(empty_context) is False

    def test_has_pricing_data_with_company_size(self):
        """Test has_pricing_data with only company_size."""
        ctx = SimpleContext(collected_data={"company_size": 10})
        assert has_pricing_data(ctx) is True

    def test_has_pricing_data_with_users_count(self):
        """Test has_pricing_data with only users_count."""
        ctx = SimpleContext(collected_data={"users_count": 5})
        assert has_pricing_data(ctx) is True

    def test_has_pricing_data_false(self, empty_context):
        """Test has_pricing_data without data."""
        assert has_pricing_data(empty_context) is False

    def test_has_contact_info_with_email(self):
        """Test has_contact_info with email."""
        ctx = SimpleContext(collected_data={"email": "test@test.com"})
        assert has_contact_info(ctx) is True

    def test_has_contact_info_with_phone(self):
        """Test has_contact_info with phone."""
        ctx = SimpleContext(collected_data={"phone": "123456"})
        assert has_contact_info(ctx) is True

    def test_has_contact_info_with_contact(self):
        """Test has_contact_info with contact."""
        ctx = SimpleContext(collected_data={"contact": "John"})
        assert has_contact_info(ctx) is True

    def test_has_contact_info_false(self, empty_context):
        """Test has_contact_info without data."""
        assert has_contact_info(empty_context) is False

    def test_has_pain_point_with_pain_point(self):
        """Test has_pain_point with pain_point."""
        ctx = SimpleContext(collected_data={"pain_point": "slow reports"})
        assert has_pain_point(ctx) is True

    def test_has_pain_point_with_pain_category(self):
        """Test has_pain_point with pain_category."""
        ctx = SimpleContext(collected_data={"pain_category": "efficiency"})
        assert has_pain_point(ctx) is True

    def test_has_pain_point_false(self, empty_context):
        """Test has_pain_point without data."""
        assert has_pain_point(empty_context) is False

    def test_has_competitor_mention_with_competitor(self):
        """Test has_competitor_mention with competitor."""
        ctx = SimpleContext(collected_data={"competitor": "SalesForce"})
        assert has_competitor_mention(ctx) is True

    def test_has_competitor_mention_with_current_crm(self):
        """Test has_competitor_mention with current_crm."""
        ctx = SimpleContext(collected_data={"current_crm": "HubSpot"})
        assert has_competitor_mention(ctx) is True

    def test_has_competitor_mention_false(self, empty_context):
        """Test has_competitor_mention without data."""
        assert has_competitor_mention(empty_context) is False

    def test_has_role_true(self):
        """Test has_role with data."""
        ctx = SimpleContext(collected_data={"role": "manager"})
        assert has_role(ctx) is True

    def test_has_role_false(self, empty_context):
        """Test has_role without data."""
        assert has_role(empty_context) is False

    def test_has_industry_true(self):
        """Test has_industry with data."""
        ctx = SimpleContext(collected_data={"industry": "tech"})
        assert has_industry(ctx) is True

    def test_has_industry_false(self, empty_context):
        """Test has_industry without data."""
        assert has_industry(empty_context) is False

    # State conditions
    def test_is_initial_state_true(self, empty_context):
        """Test is_initial_state in initial state."""
        empty_context.state = "initial"
        assert is_initial_state(empty_context) is True

    def test_is_initial_state_false(self, simple_context):
        """Test is_initial_state in non-initial state."""
        assert is_initial_state(simple_context) is False

    def test_is_success_state_true(self):
        """Test is_success_state in success state."""
        ctx = SimpleContext(state="success")
        assert is_success_state(ctx) is True

    def test_is_success_state_false(self, simple_context):
        """Test is_success_state in non-success state."""
        assert is_success_state(simple_context) is False

    def test_is_failed_state_true(self):
        """Test is_failed_state in failed state."""
        ctx = SimpleContext(state="failed")
        assert is_failed_state(ctx) is True

    def test_is_failed_state_false(self, simple_context):
        """Test is_failed_state in non-failed state."""
        assert is_failed_state(simple_context) is False

    def test_is_terminal_state_success(self):
        """Test is_terminal_state in success state."""
        ctx = SimpleContext(state="success")
        assert is_terminal_state(ctx) is True

    def test_is_terminal_state_failed(self):
        """Test is_terminal_state in failed state."""
        ctx = SimpleContext(state="failed")
        assert is_terminal_state(ctx) is True

    def test_is_terminal_state_false(self, simple_context):
        """Test is_terminal_state in non-terminal state."""
        assert is_terminal_state(simple_context) is False

    # Turn conditions
    def test_is_first_turn_true(self, empty_context):
        """Test is_first_turn on turn 0."""
        assert is_first_turn(empty_context) is True

    def test_is_first_turn_false(self, simple_context):
        """Test is_first_turn on later turn."""
        assert is_first_turn(simple_context) is False

    def test_is_early_conversation_true(self):
        """Test is_early_conversation on turn 2."""
        ctx = SimpleContext(turn_number=2)
        assert is_early_conversation(ctx) is True

    def test_is_early_conversation_false(self, simple_context):
        """Test is_early_conversation on turn 5."""
        assert is_early_conversation(simple_context) is False

    def test_is_late_conversation_true(self):
        """Test is_late_conversation on turn 15."""
        ctx = SimpleContext(turn_number=15)
        assert is_late_conversation(ctx) is True

    def test_is_late_conversation_false(self, simple_context):
        """Test is_late_conversation on turn 5."""
        assert is_late_conversation(simple_context) is False

    def test_is_extended_conversation_true(self):
        """Test is_extended_conversation on turn 25."""
        ctx = SimpleContext(turn_number=25)
        assert is_extended_conversation(ctx) is True

    def test_is_extended_conversation_false(self):
        """Test is_extended_conversation on turn 15."""
        ctx = SimpleContext(turn_number=15)
        assert is_extended_conversation(ctx) is False

    # Helper functions
    def test_check_field_true(self, simple_context):
        """Test check_field with existing field."""
        assert check_field(simple_context, "company_size") is True

    def test_check_field_false(self, simple_context):
        """Test check_field with missing field."""
        assert check_field(simple_context, "nonexistent") is False

    def test_has_any_field_true(self, simple_context):
        """Test has_any_field with one matching."""
        assert has_any_field(simple_context, ["nonexistent", "company_size"]) is True

    def test_has_any_field_false(self, simple_context):
        """Test has_any_field with none matching."""
        assert has_any_field(simple_context, ["nonexistent", "also_missing"]) is False

    def test_has_all_fields_true(self, simple_context):
        """Test has_all_fields with all present."""
        assert has_all_fields(simple_context, ["company_size", "users_count"]) is True

    def test_has_all_fields_false(self, simple_context):
        """Test has_all_fields with one missing."""
        assert has_all_fields(simple_context, ["company_size", "nonexistent"]) is False

    def test_get_field_value_existing(self, simple_context):
        """Test get_field_value for existing field."""
        assert get_field_value(simple_context, "company_size") == 50

    def test_get_field_value_missing_with_default(self, simple_context):
        """Test get_field_value for missing field with default."""
        assert get_field_value(simple_context, "nonexistent", "default") == "default"

    def test_get_field_value_missing_no_default(self, simple_context):
        """Test get_field_value for missing field without default."""
        assert get_field_value(simple_context, "nonexistent") is None

    def test_shared_conditions_registered(self):
        """Test that shared conditions are properly registered."""
        conditions = shared_registry.list_all()
        assert "has_collected_data" in conditions
        assert "has_pricing_data" in conditions
        assert "is_initial_state" in conditions
        assert "is_first_turn" in conditions

    def test_shared_conditions_categories(self):
        """Test that shared conditions have correct categories."""
        categories = shared_registry.get_categories()
        assert "data" in categories
        assert "state" in categories
        assert "turn" in categories


# =============================================================================
# CONDITION REGISTRIES AGGREGATOR TESTS
# =============================================================================

class TestConditionRegistries:
    """Tests for ConditionRegistries aggregator."""

    @pytest.fixture(autouse=True)
    def reset_registries(self):
        """Reset registries before each test."""
        # Save current state
        saved = dict(ConditionRegistries._registries)

        # Reset to only shared
        ConditionRegistries.clear()
        ConditionRegistries.register("shared", shared_registry)

        yield

        # Restore state
        ConditionRegistries.clear()
        for name, reg in saved.items():
            ConditionRegistries._registries[name] = reg

    def test_register_new_registry(self):
        """Test registering a new registry."""
        test_reg = ConditionRegistry("test_domain", SimpleContext)
        ConditionRegistries.register("test_domain", test_reg)

        assert "test_domain" in ConditionRegistries.list_registries()

    def test_register_duplicate_raises(self):
        """Test that registering duplicate raises error."""
        test_reg = ConditionRegistry("duplicate", SimpleContext)
        ConditionRegistries.register("duplicate", test_reg)

        with pytest.raises(ValueError, match="already registered"):
            ConditionRegistries.register("duplicate", test_reg)

    def test_unregister_existing(self):
        """Test unregistering an existing registry."""
        test_reg = ConditionRegistry("to_remove", SimpleContext)
        ConditionRegistries.register("to_remove", test_reg)

        result = ConditionRegistries.unregister("to_remove")
        assert result is True
        assert "to_remove" not in ConditionRegistries.list_registries()

    def test_unregister_nonexistent(self):
        """Test unregistering non-existent registry."""
        result = ConditionRegistries.unregister("nonexistent")
        assert result is False

    def test_get_existing(self):
        """Test getting an existing registry."""
        registry = ConditionRegistries.get("shared")
        assert registry is shared_registry

    def test_get_nonexistent(self):
        """Test getting a non-existent registry."""
        registry = ConditionRegistries.get("nonexistent")
        assert registry is None

    def test_list_registries(self):
        """Test listing all registries."""
        registries = ConditionRegistries.list_registries()
        assert "shared" in registries

    def test_validate_all_with_factories(self):
        """Test validating all registries with factories."""
        results = ConditionRegistries.validate_all({
            "shared": SimpleContext
        })

        assert "shared" in results
        assert results["shared"].is_valid

    def test_validate_all_missing_factory(self):
        """Test validate_all with missing factory."""
        test_reg = ConditionRegistry("no_factory", SimpleContext)
        ConditionRegistries.register("no_factory", test_reg)

        results = ConditionRegistries.validate_all({})

        assert "no_factory" in results
        assert not results["no_factory"].is_valid

    def test_get_stats(self):
        """Test getting aggregate statistics."""
        stats = ConditionRegistries.get_stats()

        assert "total_registries" in stats
        assert "total_conditions" in stats
        assert "registries" in stats
        assert stats["total_registries"] >= 1

    def test_generate_documentation(self):
        """Test generating documentation."""
        docs = ConditionRegistries.generate_documentation()

        assert "Condition Registries Documentation" in docs
        assert "shared" in docs.lower()

    def test_clear(self):
        """Test clearing all registries."""
        test_reg = ConditionRegistry("temp", SimpleContext)
        ConditionRegistries.register("temp", test_reg)

        ConditionRegistries.clear()

        assert len(ConditionRegistries.list_registries()) == 0

    def test_has_condition_true(self):
        """Test has_condition for existing condition."""
        assert ConditionRegistries.has_condition("has_pricing_data") is True

    def test_has_condition_false(self):
        """Test has_condition for non-existent condition."""
        assert ConditionRegistries.has_condition("nonexistent") is False

    def test_find_condition_found(self):
        """Test find_condition for existing condition."""
        result = ConditionRegistries.find_condition("has_pricing_data")
        assert result == "shared"

    def test_find_condition_not_found(self):
        """Test find_condition for non-existent condition."""
        result = ConditionRegistries.find_condition("nonexistent")
        assert result is None


# =============================================================================
# INTEGRATION TESTS
# =============================================================================

class TestIntegration:
    """Integration tests for the conditions system."""

    def test_full_workflow(self):
        """Test a complete workflow: register, evaluate, trace."""
        # Create registry
        registry = ConditionRegistry("integration_test", SimpleContext)

        # Register conditions
        @registry.condition(
            "has_enough_data",
            description="Check if enough data collected",
            requires_fields={"company_size", "pain_point"},
            category="data"
        )
        def has_enough_data(ctx: SimpleContext) -> bool:
            return bool(
                ctx.collected_data.get("company_size") and
                ctx.collected_data.get("pain_point")
            )

        @registry.condition("is_ready", category="state")
        def is_ready(ctx: SimpleContext) -> bool:
            return ctx.turn_number >= 3 and ctx.state == "spin_situation"

        # Create context
        ctx = SimpleContext(
            collected_data={"company_size": 50, "pain_point": "slow process"},
            state="spin_situation",
            turn_number=5
        )

        # Create trace collector
        collector = TraceCollector()
        trace = collector.create_trace(
            "price_question",
            intent="price_question",
            state=ctx.state,
            domain="integration_test"
        )

        # Evaluate conditions
        data_ok = registry.evaluate("has_enough_data", ctx, trace)
        ready_ok = registry.evaluate("is_ready", ctx, trace)

        # Set result
        if data_ok and ready_ok:
            trace.set_result(
                "answer_with_facts",
                Resolution.CONDITION_MATCHED,
                "has_enough_data"
            )
        else:
            trace.set_result("deflect", Resolution.DEFAULT)

        # Verify results
        assert data_ok is True
        assert ready_ok is True
        assert trace.final_action == "answer_with_facts"
        assert trace.conditions_checked == 2
        assert trace.conditions_passed == 2

        # Verify trace output
        compact = trace.to_compact_string()
        assert "answer_with_facts" in compact
        assert "condition_matched" in compact

        # Verify summary
        summary = collector.get_summary()
        assert summary.total_traces == 1
        assert summary.total_conditions_checked == 2

    def test_validation_workflow(self):
        """Test validating conditions in CI-like scenario."""
        registry = ConditionRegistry("validation_test", SimpleContext)

        @registry.condition("valid_cond")
        def valid_cond(ctx: SimpleContext) -> bool:
            return True

        @registry.condition("another_valid")
        def another_valid(ctx: SimpleContext) -> bool:
            return ctx.turn_number >= 0

        # Validate all conditions
        result = registry.validate_all(SimpleContext)

        assert result.is_valid
        assert len(result.passed) == 2
        assert "valid_cond" in result.passed
        assert "another_valid" in result.passed

    def test_documentation_generation(self):
        """Test generating documentation for a registry."""
        registry = ConditionRegistry("docs_test", SimpleContext)

        @registry.condition(
            "documented_cond",
            description="This is a well-documented condition",
            requires_fields={"field1", "field2"},
            category="important"
        )
        def documented_cond(ctx: SimpleContext) -> bool:
            return True

        docs = registry.get_documentation()

        assert "Docs Test Conditions" in docs
        assert "documented_cond" in docs
        assert "This is a well-documented condition" in docs
        assert "field1" in docs or "field2" in docs

    def test_shared_registry_integration(self):
        """Test using shared registry with evaluation."""
        ctx = SimpleContext(
            collected_data={"company_size": 100, "email": "test@test.com"},
            state="spin_situation",
            turn_number=5
        )

        # Use shared conditions
        assert shared_registry.evaluate("has_pricing_data", ctx) is True
        assert shared_registry.evaluate("has_contact_info", ctx) is True
        assert shared_registry.evaluate("is_late_conversation", ctx) is False

        # With trace
        trace = EvaluationTrace(rule_name="test")
        shared_registry.evaluate("has_pricing_data", ctx, trace)

        assert len(trace.entries) == 1
        assert trace.entries[0].result is True
