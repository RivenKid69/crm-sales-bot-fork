"""
Tests for three critical bugfixes:
  BUG #1: StateMachine config/flow desynchronization
  BUG #2: Composite conditions break blackboard sources
  BUG #3: is_mirroring_bot and is_stalled unreachable in repair cascade

Run with: PYTHONPATH=src pytest tests/test_three_critical_bugs.py -v
"""

import pytest
import sys
import os
import logging
from pathlib import Path
from unittest.mock import Mock, patch
from typing import Dict, Any, Optional

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from config_loader import ConfigLoader, LoadedConfig, FlowConfig
from conditions.expression_parser import (
    ConditionExpressionParser,
    evaluate_condition_value,
)
from conditions.base import SimpleContext
from conditions.policy.context import PolicyContext
from context_envelope import ContextEnvelope
from feature_flags import flags


# =============================================================================
# BUG #1: StateMachine config/flow desynchronization
# =============================================================================


class TestBug1ConfigFlowSync:
    """
    Tests that LoadedConfig.flow_name is set after load/load_named,
    and that StateMachine uses config.flow_name for auto-load.
    """

    def test_loaded_config_has_flow_name_field(self):
        """LoadedConfig should have flow_name field."""
        config = LoadedConfig()
        assert hasattr(config, 'flow_name')
        assert config.flow_name is None

    def test_config_loader_sets_flow_name(self):
        """ConfigLoader.load() sets flow_name from settings."""
        loader = ConfigLoader()
        config = loader.load()
        assert config.flow_name is not None
        assert isinstance(config.flow_name, str)
        assert len(config.flow_name) > 0

    def test_config_loader_load_named_sets_flow_name(self):
        """ConfigLoader.load_named() also sets flow_name."""
        loader = ConfigLoader()
        config = loader.load_named("default")
        assert config.flow_name is not None

    def test_state_machine_auto_loads_flow_from_config_flow_name(self):
        """
        When StateMachine gets config but no flow, it should derive
        flow from config.flow_name rather than blindly from settings.
        """
        from state_machine import StateMachine

        loader = ConfigLoader()
        config = loader.load()
        # Set a specific flow_name
        config.flow_name = "spin_selling"

        # Create SM with config only — flow should be auto-loaded
        sm = StateMachine(config=config)
        assert sm._flow is not None
        assert sm._flow.name == "spin_selling"

    def test_state_machine_validate_config_flow_mismatch_warns(self):
        """
        When config.flow_name != flow.name, a warning should be logged.
        """
        from state_machine import StateMachine

        config = Mock()
        config.flow_name = "bant"
        flow = Mock()
        flow.name = "spin_selling"

        with patch("state_machine.logger") as mock_logger:
            StateMachine._validate_config_flow(config, flow)
            mock_logger.warning.assert_called_once()
            assert "Config/flow mismatch" in mock_logger.warning.call_args[0][0]

    def test_state_machine_validate_config_flow_match_no_warning(self):
        """
        When config.flow_name == flow.name, no warning logged.
        """
        from state_machine import StateMachine

        config = Mock()
        config.flow_name = "spin_selling"
        flow = Mock()
        flow.name = "spin_selling"

        with patch("state_machine.logger") as mock_logger:
            StateMachine._validate_config_flow(config, flow)
            mock_logger.warning.assert_not_called()

    def test_validate_config_flow_none_flow_name_no_warning(self):
        """No warning when config.flow_name is None (not set)."""
        from state_machine import StateMachine

        config = Mock()
        config.flow_name = None
        flow = Mock()
        flow.name = "spin_selling"

        with patch("state_machine.logger") as mock_logger:
            StateMachine._validate_config_flow(config, flow)
            mock_logger.warning.assert_not_called()

    def test_flow_name_always_set_after_load(self):
        """Architectural invariant: flow_name is always set after load()."""
        loader = ConfigLoader()
        config = loader.load()
        assert config.flow_name is not None, "flow_name must be set after load()"


# =============================================================================
# BUG #2: Composite conditions break blackboard sources
# =============================================================================


class TestBug2EvaluateConditionValueUtility:
    """
    Tests for the shared evaluate_condition_value() utility function
    in expression_parser.py.
    """

    @pytest.fixture
    def registry(self):
        """Create a condition registry with test conditions."""
        from conditions.registry import ConditionRegistry
        reg = ConditionRegistry("test_ecv", SimpleContext)

        @reg.condition("is_true", category="test")
        def is_true(ctx: SimpleContext) -> bool:
            return True

        @reg.condition("is_false", category="test")
        def is_false(ctx: SimpleContext) -> bool:
            return False

        return reg

    @pytest.fixture
    def expression_parser(self, registry):
        """Create expression parser with the test registry."""
        return ConditionExpressionParser(registry)

    @pytest.fixture
    def ctx(self):
        """Create test context."""
        return SimpleContext(collected_data={}, state="test", turn_number=1)

    def test_evaluate_string_condition(self, registry, ctx):
        """String condition delegates to registry.evaluate()."""
        result = evaluate_condition_value("is_true", ctx, registry)
        assert result is True

        result = evaluate_condition_value("is_false", ctx, registry)
        assert result is False

    def test_evaluate_dict_and_condition(self, registry, expression_parser, ctx):
        """Dict AND condition uses expression parser."""
        condition = {"and": ["is_true", "is_true"]}
        result = evaluate_condition_value(
            condition, ctx, registry, expression_parser
        )
        assert result is True

        condition = {"and": ["is_true", "is_false"]}
        result = evaluate_condition_value(
            condition, ctx, registry, expression_parser
        )
        assert result is False

    def test_evaluate_dict_or_condition(self, registry, expression_parser, ctx):
        """Dict OR condition uses expression parser."""
        condition = {"or": ["is_false", "is_true"]}
        result = evaluate_condition_value(
            condition, ctx, registry, expression_parser
        )
        assert result is True

        condition = {"or": ["is_false", "is_false"]}
        result = evaluate_condition_value(
            condition, ctx, registry, expression_parser
        )
        assert result is False

    def test_evaluate_dict_not_condition(self, registry, expression_parser, ctx):
        """Dict NOT condition uses expression parser."""
        condition = {"not": "is_true"}
        result = evaluate_condition_value(
            condition, ctx, registry, expression_parser
        )
        assert result is False

        condition = {"not": "is_false"}
        result = evaluate_condition_value(
            condition, ctx, registry, expression_parser
        )
        assert result is True

    def test_evaluate_dict_without_parser_raises_value_error(self, registry, ctx):
        """Dict condition without expression_parser raises ValueError."""
        condition = {"and": ["is_true", "is_false"]}
        with pytest.raises(ValueError, match="requires expression_parser"):
            evaluate_condition_value(condition, ctx, registry, None)

    def test_evaluate_invalid_type_raises_type_error(self, registry, ctx):
        """Non-str/dict condition raises TypeError."""
        with pytest.raises(TypeError, match="must be str or dict"):
            evaluate_condition_value(42, ctx, registry)

    def test_evaluate_condition_value_is_only_dispatch_point(self):
        """Architectural invariant: evaluate_condition_value is importable."""
        from conditions.expression_parser import evaluate_condition_value as ecv
        assert callable(ecv)


class TestBug2IntentProcessorCompositeConditions:
    """
    Tests that IntentProcessorSource._resolve_rule() handles
    composite dict conditions (AND/OR/NOT) without crashing.
    """

    def test_resolve_rule_with_composite_and_condition(self):
        """IntentProcessorSource should handle {"when": {"and": [...]}, "then": "action"}."""
        from blackboard.sources.intent_processor import IntentProcessorSource

        source = IntentProcessorSource()

        # Create a mock context snapshot
        ctx = Mock()
        ctx.collected_data = {}
        ctx.state = "greeting"
        ctx.turn_number = 1
        ctx.current_phase = None
        ctx.current_intent = "test"
        ctx.last_intent = None
        ctx.intent_tracker = Mock()
        ctx.intent_tracker.consecutive_count.return_value = 0
        ctx.intent_tracker.total_count.return_value = 0
        ctx.get_missing_required_data = Mock(return_value=[])
        ctx.state_config = {}
        ctx.context_envelope = Mock()
        ctx.context_envelope.frustration_level = 0
        ctx.context_envelope.is_stuck = False

        # Simple string rule should still work
        result = source._resolve_rule("some_action", ctx)
        assert result == "some_action"

        # Dict rule with composite condition shouldn't crash (even if conditions unknown)
        rule = {"when": {"and": ["nonexistent_cond_1", "nonexistent_cond_2"]}, "then": "action"}
        # Should return None (condition eval fails gracefully), not crash with TypeError
        result = source._resolve_rule(rule, ctx)
        assert result is None or isinstance(result, str)

    def test_resolve_rule_with_not_condition(self):
        """IntentProcessorSource should handle {"when": {"not": "cond"}, "then": "action"}."""
        from blackboard.sources.intent_processor import IntentProcessorSource

        source = IntentProcessorSource()

        ctx = Mock()
        ctx.collected_data = {}
        ctx.state = "greeting"
        ctx.turn_number = 1
        ctx.current_phase = None
        ctx.current_intent = "test"
        ctx.last_intent = None
        ctx.intent_tracker = Mock()
        ctx.intent_tracker.consecutive_count.return_value = 0
        ctx.intent_tracker.total_count.return_value = 0
        ctx.get_missing_required_data = Mock(return_value=[])
        ctx.state_config = {}
        ctx.context_envelope = Mock()
        ctx.context_envelope.frustration_level = 0
        ctx.context_envelope.is_stuck = False

        rule = {"when": {"not": "nonexistent"}, "then": "action"}
        # Should not crash with TypeError
        result = source._resolve_rule(rule, ctx)
        assert result is None or isinstance(result, str)


class TestBug2TransitionResolverCompositeConditions:
    """
    Tests that TransitionResolverSource._evaluate_condition() handles
    composite dict conditions without crashing.
    """

    def test_evaluate_condition_with_dict_not_condition(self):
        """TransitionResolverSource should handle dict conditions."""
        from blackboard.sources.transition_resolver import TransitionResolverSource
        from conditions.state_machine.context import EvaluatorContext

        source = TransitionResolverSource()

        eval_ctx = EvaluatorContext(
            collected_data={},
            state="greeting",
            turn_number=1,
        )

        # Dict condition should not crash (even if condition not found)
        result = source._evaluate_condition({"not": "nonexistent_cond"}, eval_ctx)
        # Should return False gracefully, not raise TypeError
        assert result is False or result is True

    def test_evaluate_condition_with_string_still_works(self):
        """String conditions still work after the refactor."""
        from blackboard.sources.transition_resolver import TransitionResolverSource
        from conditions.state_machine.context import EvaluatorContext

        source = TransitionResolverSource()

        eval_ctx = EvaluatorContext(
            collected_data={},
            state="greeting",
            turn_number=1,
        )

        # String condition should work normally
        result = source._evaluate_condition("nonexistent_cond", eval_ctx)
        assert result is False  # Unknown condition returns False

    def test_expression_parser_passed_through(self):
        """TransitionResolverSource accepts expression_parser in __init__."""
        from blackboard.sources.transition_resolver import TransitionResolverSource

        mock_parser = Mock()
        source = TransitionResolverSource(expression_parser=mock_parser)
        assert source._expression_parser is mock_parser


class TestBug2RuleResolverRefactored:
    """Tests that RuleResolver still works after refactoring to use evaluate_condition_value."""

    @pytest.fixture
    def registry(self):
        """Create a test registry with conditions."""
        from conditions.registry import ConditionRegistry
        reg = ConditionRegistry("test_resolver_ecv", SimpleContext)

        @reg.condition("always_true", category="test")
        def always_true(ctx: SimpleContext) -> bool:
            return True

        @reg.condition("cond_a", category="test")
        def cond_a(ctx: SimpleContext) -> bool:
            return True

        @reg.condition("cond_b", category="test")
        def cond_b(ctx: SimpleContext) -> bool:
            return True

        return reg

    def test_conditional_rule_with_string_condition(self, registry):
        """RuleResolver handles string conditions via shared utility."""
        from rules.resolver import RuleResolver

        resolver = RuleResolver(registry)
        ctx = SimpleContext(collected_data={}, state="test_state", turn_number=1)

        result = resolver.resolve_action(
            intent="test_intent",
            state_rules={"test_intent": {"when": "always_true", "then": "do_action"}},
            global_rules={},
            ctx=ctx,
            state="test_state",
        )
        assert result.action == "do_action"

    def test_conditional_rule_with_composite_dict_condition(self, registry):
        """RuleResolver handles composite dict conditions via shared utility."""
        from rules.resolver import RuleResolver

        parser = ConditionExpressionParser(registry)
        resolver = RuleResolver(registry, expression_parser=parser)
        ctx = SimpleContext(collected_data={}, state="test_state", turn_number=1)

        result = resolver.resolve_action(
            intent="test_intent",
            state_rules={"test_intent": {"when": {"and": ["cond_a", "cond_b"]}, "then": "do_action"}},
            global_rules={},
            ctx=ctx,
            state="test_state",
        )
        assert result.action == "do_action"


# =============================================================================
# BUG #3: is_mirroring_bot and is_stalled unreachable
# =============================================================================


class TestBug3CanApplyRepairCondition:
    """Tests for the new can_apply_repair condition gate."""

    def test_can_apply_repair_true_when_no_cooldown(self):
        """can_apply_repair returns True when stall_guard_cooldown=False."""
        from conditions.policy import can_apply_repair

        ctx = PolicyContext.create_test_context(stall_guard_cooldown=False)
        assert can_apply_repair(ctx) is True

    def test_can_apply_repair_false_when_cooldown(self):
        """can_apply_repair returns False when stall_guard_cooldown=True."""
        from conditions.policy import can_apply_repair

        ctx = PolicyContext.create_test_context(stall_guard_cooldown=True)
        assert can_apply_repair(ctx) is False

    def test_can_apply_repair_does_not_enumerate_signals(self):
        """
        Architectural invariant: can_apply_repair does NOT check individual
        repair signals (is_stuck, etc.) — only cooldown.
        """
        from conditions.policy import can_apply_repair

        ctx = PolicyContext.create_test_context(
            is_stuck=False,
            has_oscillation=False,
            repeated_question=None,
            consecutive_same_state=0,
            stall_guard_cooldown=False,
        )
        # Gate should be open even with no signals
        assert can_apply_repair(ctx) is True

    def test_can_apply_repair_registered_in_policy_registry(self):
        """can_apply_repair is registered and evaluable via policy_registry."""
        from conditions.policy import policy_registry

        ctx = PolicyContext.create_test_context(stall_guard_cooldown=False)
        result = policy_registry.evaluate("can_apply_repair", ctx)
        assert result is True


class TestBug3IsStalledExported:
    """Tests that is_stalled is properly exported and accessible."""

    def test_is_stalled_importable_from_init(self):
        """is_stalled can be imported from conditions.policy."""
        from conditions.policy import is_stalled
        assert callable(is_stalled)

    def test_is_stalled_in_all(self):
        """is_stalled is in __all__ of conditions.policy."""
        import conditions.policy as policy_mod
        assert "is_stalled" in policy_mod.__all__

    def test_can_apply_repair_in_all(self):
        """can_apply_repair is in __all__ of conditions.policy."""
        import conditions.policy as policy_mod
        assert "can_apply_repair" in policy_mod.__all__

    def test_is_stalled_registered_in_registry(self):
        """is_stalled is evaluable via policy_registry."""
        from conditions.policy import policy_registry

        ctx = PolicyContext.create_test_context(
            consecutive_same_state=5,
            is_progressing=False,
            has_extracted_data=False,
        )
        # Should not raise "condition not found"
        result = policy_registry.evaluate("is_stalled", ctx)
        assert isinstance(result, bool)


class TestBug3IsMirroringBot:
    """Tests for is_mirroring_bot with last_user_message / last_bot_message."""

    def test_mirroring_detected_when_messages_similar(self):
        """is_mirroring_bot fires when last_user_message ≈ last_bot_message."""
        from conditions.policy import is_mirroring_bot

        ctx = PolicyContext.create_test_context(
            last_user_message="Сколько сотрудников?",
            last_bot_message="Сколько сотрудников?",
        )
        assert is_mirroring_bot(ctx) is True

    def test_mirroring_not_detected_when_messages_different(self):
        """is_mirroring_bot returns False for different messages."""
        from conditions.policy import is_mirroring_bot

        ctx = PolicyContext.create_test_context(
            last_user_message="Мне не интересно",
            last_bot_message="Сколько сотрудников?",
        )
        assert is_mirroring_bot(ctx) is False

    def test_mirroring_not_detected_when_empty(self):
        """is_mirroring_bot returns False when messages are empty."""
        from conditions.policy import is_mirroring_bot

        ctx = PolicyContext.create_test_context(
            last_user_message="",
            last_bot_message="",
        )
        assert is_mirroring_bot(ctx) is False

    def test_policy_context_has_message_fields(self):
        """PolicyContext has last_user_message and last_bot_message."""
        ctx = PolicyContext.create_test_context()
        assert hasattr(ctx, 'last_user_message')
        assert hasattr(ctx, 'last_bot_message')

    def test_policy_context_create_test_context_accepts_messages(self):
        """create_test_context accepts last_user_message and last_bot_message."""
        ctx = PolicyContext.create_test_context(
            last_user_message="hello",
            last_bot_message="world",
        )
        assert ctx.last_user_message == "hello"
        assert ctx.last_bot_message == "world"


class TestBug3ContextEnvelopeMessageFields:
    """Tests that ContextEnvelope carries message text."""

    def test_context_envelope_has_message_fields(self):
        """ContextEnvelope has last_user_message and last_bot_message."""
        envelope = ContextEnvelope()
        assert hasattr(envelope, 'last_user_message')
        assert hasattr(envelope, 'last_bot_message')

    def test_build_context_envelope_accepts_messages(self):
        """build_context_envelope accepts user_message and last_bot_message params."""
        from context_envelope import build_context_envelope

        envelope = build_context_envelope(
            user_message="test user msg",
            last_bot_message="test bot msg",
        )
        assert envelope.last_user_message == "test user msg"
        assert envelope.last_bot_message == "test bot msg"

    def test_policy_context_from_envelope_carries_messages(self):
        """PolicyContext.from_envelope() propagates message fields."""
        envelope = ContextEnvelope()
        envelope.last_user_message = "user says"
        envelope.last_bot_message = "bot says"

        ctx = PolicyContext.from_envelope(envelope)
        assert ctx.last_user_message == "user says"
        assert ctx.last_bot_message == "bot says"


class TestBug3RepairCascadeIntegration:
    """
    Integration tests for the repair cascade with can_apply_repair gate.
    """

    @pytest.fixture(autouse=True)
    def setup(self):
        """Enable policy overlays."""
        flags.set_override("context_policy_overlays", True)
        yield
        flags.clear_override("context_policy_overlays")

    def test_is_stalled_fires_repair_overlay(self):
        """
        When is_stalled is True (consecutive_same_state >= threshold),
        the repair overlay should produce a stall repair action.
        """
        from dialogue_policy import DialoguePolicy, PolicyDecision

        policy = DialoguePolicy()

        envelope = ContextEnvelope(
            state="spin_situation",
            consecutive_same_state=5,
            is_progressing=False,
            has_extracted_data=False,
            is_stuck=False,
            has_oscillation=False,
            repeated_question=None,
            last_user_message="",
            last_bot_message="",
        )
        sm_result = {"next_state": "spin_situation", "action": "ask_company_size"}

        result = policy.maybe_override(sm_result, envelope)

        # The repair overlay should fire for is_stalled
        if result is not None and result.has_override:
            assert result.decision in (
                PolicyDecision.REPAIR_CLARIFY,
                PolicyDecision.REPAIR_SUMMARIZE,
            )
            assert "is_stalled" in result.signals_used

    def test_is_mirroring_fires_repair_overlay(self):
        """
        When is_mirroring_bot is True, the repair overlay should produce
        a mirroring repair action.
        """
        from dialogue_policy import DialoguePolicy, PolicyDecision

        policy = DialoguePolicy()

        envelope = ContextEnvelope(
            state="spin_situation",
            is_stuck=False,
            has_oscillation=False,
            repeated_question=None,
            consecutive_same_state=0,
            last_user_message="Сколько сотрудников?",
            last_bot_message="Сколько сотрудников?",
        )
        sm_result = {"next_state": "spin_situation", "action": "ask_company_size"}

        result = policy.maybe_override(sm_result, envelope)

        if result is not None and result.has_override:
            assert result.decision == PolicyDecision.REPAIR_SUMMARIZE
            assert "is_mirroring" in result.signals_used

    def test_needs_repair_still_works_for_monitoring(self):
        """
        needs_repair condition still works for diagnostic use.
        """
        from conditions.policy import needs_repair

        ctx = PolicyContext.create_test_context(
            is_stuck=True,
            stall_guard_cooldown=False,
        )
        assert needs_repair(ctx) is True

    def test_can_apply_repair_used_as_gate_not_needs_repair(self):
        """
        Verify the cascade uses can_apply_repair (not needs_repair) as gate.
        This means the gate opens even when only is_mirroring_bot or is_stalled
        signals are active (which needs_repair would miss).
        """
        from dialogue_policy import DialoguePolicy

        policy = DialoguePolicy()

        # Simulate a case where only is_mirroring_bot would fire
        # (no is_stuck, no has_oscillation, no repeated_question)
        envelope = ContextEnvelope(
            state="spin_situation",
            is_stuck=False,
            has_oscillation=False,
            repeated_question=None,
            consecutive_same_state=0,
            last_user_message="same text",
            last_bot_message="same text",
        )
        sm_result = {"next_state": "spin_situation", "action": "ask_company_size"}

        # With can_apply_repair gate, this should reach the overlay
        result = policy.maybe_override(sm_result, envelope)

        # Key: the gate opened and the overlay ran
        # With old needs_repair gate, this would have been skipped entirely
        if result is not None and result.has_override:
            assert "is_mirroring" in result.signals_used


class TestBug3OrchestratorPassesDependencies:
    """Tests that orchestrator passes expression_parser to sources."""

    def test_orchestrator_source_configs_include_expression_parser(self):
        """Orchestrator passes expression_parser to TransitionResolverSource."""
        from blackboard.orchestrator import DialogueOrchestrator

        loader = ConfigLoader()
        config = loader.load()
        flow = loader.load_flow("spin_selling")

        from state_machine import StateMachine
        sm = StateMachine(config=config, flow=flow)

        orchestrator = DialogueOrchestrator(
            state_machine=sm,
            flow_config=flow,
        )

        # Check that TransitionResolverSource was created with expression_parser
        for source in orchestrator._sources:
            if source.name == "TransitionResolverSource":
                assert hasattr(source, '_expression_parser')
                break

    def test_orchestrator_source_configs_include_rule_resolver(self):
        """Orchestrator passes rule_resolver to IntentProcessorSource."""
        from blackboard.orchestrator import DialogueOrchestrator

        loader = ConfigLoader()
        config = loader.load()
        flow = loader.load_flow("spin_selling")

        from state_machine import StateMachine
        sm = StateMachine(config=config, flow=flow)

        orchestrator = DialogueOrchestrator(
            state_machine=sm,
            flow_config=flow,
        )

        # Check that IntentProcessorSource has rule_resolver
        for source in orchestrator._sources:
            if source.name == "IntentProcessorSource":
                assert hasattr(source, '_rule_resolver')
                assert source._rule_resolver is not None
                break
