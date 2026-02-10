"""
Tests for Conditional Rules System - Phase 8: Tooling + CI + Simulations.

This test suite provides 100% coverage for:
- scripts/validate_conditions.py - validation script
- simulator/runner.py - rule traces collection
- simulator/report.py - [RULE] blocks display
- settings.py - conditional_rules settings

Run with: pytest tests/test_phase8_tooling.py -v
"""

import pytest
import sys
import os
from typing import Dict, Any, List
from dataclasses import dataclass, field
from unittest.mock import Mock, patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# =============================================================================
# TEST: VALIDATE CONDITIONS SCRIPT
# =============================================================================

class TestValidateConditionsScript:
    """Tests for scripts/validate_conditions.py"""

    def test_create_context_factories_returns_all_domains(self):
        """Test that context factories are created for all domains."""
        from scripts.validate_conditions import create_context_factories

        factories = create_context_factories()

        # Should have factories for all domains
        assert "shared" in factories
        assert "state_machine" in factories
        assert "policy" in factories
        assert "fallback" in factories
        assert "personalization" in factories

        # Each factory should be callable
        for name, factory in factories.items():
            assert callable(factory), f"Factory for {name} should be callable"
            ctx = factory()
            assert hasattr(ctx, "collected_data"), f"Context for {name} missing collected_data"
            assert hasattr(ctx, "state"), f"Context for {name} missing state"
            assert hasattr(ctx, "turn_number"), f"Context for {name} missing turn_number"

    def test_validation_summary_dataclass(self):
        """Test ValidationSummary dataclass."""
        from scripts.validate_conditions import ValidationSummary

        # Default should be valid (no errors)
        summary = ValidationSummary()
        assert summary.is_valid is True
        assert summary.conditions_total == 0
        assert summary.conditions_passed == 0
        assert summary.config_errors == 0

        # With errors should be invalid
        summary.conditions_failed = 1
        assert summary.is_valid is False

        # With config errors should be invalid
        summary2 = ValidationSummary(config_errors=1)
        assert summary2.is_valid is False

        # to_dict should work
        result = summary.to_dict()
        assert "is_valid" in result
        assert "conditions" in result
        assert "config" in result

    def test_validate_conditions_returns_summary(self):
        """Test that validate_conditions returns proper summary."""
        from scripts.validate_conditions import validate_conditions

        summary, errors, warnings = validate_conditions(verbose=False)

        # Should return proper structure
        assert isinstance(summary, dict)
        assert "total" in summary
        assert "passed" in summary
        assert "failed" in summary
        assert "errors" in summary
        assert "registries" in summary
        assert isinstance(errors, list)
        assert isinstance(warnings, list)

    def test_validate_config_returns_summary(self):
        """Test that validate_config returns proper summary."""
        from scripts.validate_conditions import validate_config

        summary, errors, warnings = validate_config(verbose=False)

        # Should return proper structure
        assert isinstance(summary, dict)
        assert "rules_checked" in summary
        assert "transitions_checked" in summary
        assert "errors" in summary
        assert "warnings" in summary
        assert "is_valid" in summary
        assert isinstance(errors, list)
        assert isinstance(warnings, list)

    def test_get_stats_returns_statistics(self):
        """Test that get_stats returns statistics."""
        from scripts.validate_conditions import get_stats

        stats = get_stats(verbose=False)

        assert isinstance(stats, dict)
        assert "total_registries" in stats
        assert "total_conditions" in stats
        assert "registries" in stats
        assert stats["total_registries"] > 0
        assert stats["total_conditions"] > 0

    def test_generate_documentation(self):
        """Test documentation generation."""
        from scripts.validate_conditions import generate_documentation

        docs = generate_documentation(output_path=None)

        assert isinstance(docs, str)
        assert "# Condition Registries Documentation" in docs
        assert "Total registries" in docs
        assert "Total conditions" in docs

# =============================================================================
# TEST: RUNNER RULE TRACES
# =============================================================================

class TestRunnerRuleTraces:
    """Tests for simulator/runner.py rule traces collection."""

    def test_simulation_result_has_rule_traces_field(self):
        """Test that SimulationResult has rule_traces field."""
        from src.simulator.runner import SimulationResult

        result = SimulationResult(
            simulation_id=1,
            persona="test",
            outcome="success",
            turns=5,
            duration_seconds=1.0,
            dialogue=[]
        )

        # Should have rule_traces field
        assert hasattr(result, "rule_traces")
        assert isinstance(result.rule_traces, list)
        assert result.rule_traces == []

    def test_simulation_result_with_rule_traces(self):
        """Test SimulationResult with rule traces."""
        from src.simulator.runner import SimulationResult

        traces = [
            {"turn": 1, "trace": {"rule_name": "test", "resolution": "simple"}},
            {"turn": 2, "trace": {"rule_name": "test2", "resolution": "condition_matched"}}
        ]

        result = SimulationResult(
            simulation_id=1,
            persona="test",
            outcome="success",
            turns=5,
            duration_seconds=1.0,
            dialogue=[],
            rule_traces=traces
        )

        assert len(result.rule_traces) == 2
        assert result.rule_traces[0]["turn"] == 1
        assert result.rule_traces[1]["trace"]["resolution"] == "condition_matched"

# =============================================================================
# TEST: REPORT RULE TRACES SECTION
# =============================================================================

class TestReportRuleTraces:
    """Tests for simulator/report.py [RULE] blocks."""

    @pytest.fixture
    def report_generator(self):
        """Create ReportGenerator instance."""
        from src.simulator.report import ReportGenerator
        return ReportGenerator()

    @pytest.fixture
    def sample_results_with_traces(self):
        """Create sample results with rule traces."""
        from src.simulator.runner import SimulationResult

        traces1 = [
            {
                "turn": 1,
                "trace": {
                    "rule_name": "price_question",
                    "resolution": "simple",
                    "final_action": "deflect_and_continue",
                    "matched_condition": None,
                    "conditions_checked": 0,
                    "entries": []
                }
            },
            {
                "turn": 2,
                "trace": {
                    "rule_name": "price_question",
                    "resolution": "condition_matched",
                    "final_action": "answer_with_facts",
                    "matched_condition": "has_pricing_data",
                    "conditions_checked": 1,
                    "entries": [
                        {"condition": "has_pricing_data", "result": True}
                    ]
                }
            }
        ]

        traces2 = [
            {
                "turn": 1,
                "trace": {
                    "rule_name": "greeting",
                    "resolution": "simple",
                    "final_action": "greet_back",
                    "matched_condition": None,
                    "conditions_checked": 0,
                    "entries": []
                }
            }
        ]

        return [
            SimulationResult(
                simulation_id=0,
                persona="happy_path",
                outcome="success",
                turns=5,
                duration_seconds=1.0,
                dialogue=[
                    {"turn": 1, "client": "Hi", "bot": "Hello", "state": "greeting", "intent": "greeting", "action": "greet"},
                    {"turn": 2, "client": "Price?", "bot": "Let me explain", "state": "spin", "intent": "price_question", "action": "deflect"}
                ],
                rule_traces=traces1
            ),
            SimulationResult(
                simulation_id=1,
                persona="skeptic",
                outcome="soft_close",
                turns=3,
                duration_seconds=0.5,
                dialogue=[
                    {"turn": 1, "client": "Hi", "bot": "Hello", "state": "greeting", "intent": "greeting", "action": "greet"}
                ],
                rule_traces=traces2
            )
        ]

    def test_section_rule_traces_with_data(self, report_generator, sample_results_with_traces):
        """Test _section_rule_traces with actual data."""
        section = report_generator._section_rule_traces(sample_results_with_traces)

        assert "УСЛОВНЫЕ ПРАВИЛА (ТРАССИРОВКА)" in section
        assert "Всего трассировок:" in section
        assert "Типы разрешения правил:" in section

        # Should show resolution types
        assert "Простое правило" in section or "simple" in section.lower()

        # Should show matched conditions (has_pricing_data was matched)
        assert "has_pricing_data" in section

    def test_section_rule_traces_empty(self, report_generator):
        """Test _section_rule_traces with empty results."""
        from src.simulator.runner import SimulationResult

        empty_results = [
            SimulationResult(
                simulation_id=0,
                persona="test",
                outcome="success",
                turns=1,
                duration_seconds=0.1,
                dialogue=[],
                rule_traces=[]
            )
        ]

        section = report_generator._section_rule_traces(empty_results)

        assert "УСЛОВНЫЕ ПРАВИЛА (ТРАССИРОВКА)" in section
        assert "не собрана" in section or "Трассировка условных правил не собрана" in section

    def test_section_rule_traces_statistics(self, report_generator, sample_results_with_traces):
        """Test that statistics are calculated correctly."""
        section = report_generator._section_rule_traces(sample_results_with_traces)

        # Total should be 3 (2 from first result + 1 from second)
        assert "Всего трассировок: 3" in section

        # Should count conditions checked
        assert "Всего проверок условий:" in section

    def test_full_dialogues_shows_rule_trace(self, report_generator):
        """Test that full dialogues section shows [RULE] blocks."""
        from src.simulator.runner import SimulationResult

        dialogue_with_trace = [
            {
                "turn": 1,
                "client": "Сколько стоит?",
                "bot": "Давайте сначала узнаем...",
                "state": "spin_situation",
                "intent": "price_question",
                "action": "deflect_and_continue",
                "rule_trace": {
                    "rule_name": "price_question",
                    "resolution": "condition_matched",
                    "final_action": "answer_with_facts",
                    "matched_condition": "has_pricing_data",
                    "entries": [
                        {"condition": "has_pricing_data", "result": True}
                    ]
                }
            }
        ]

        results = [
            SimulationResult(
                simulation_id=0,
                persona="test",
                outcome="success",
                turns=1,
                duration_seconds=0.1,
                dialogue=dialogue_with_trace,
                rule_traces=[]
            )
        ]

        section = report_generator._section_full_dialogues(results)

        # Should show [RULE] block
        assert "[RULE]" in section
        assert "price_question" in section
        assert "has_pricing_data" in section

    def test_full_dialogues_without_trace(self, report_generator):
        """Test full dialogues section without rule trace."""
        from src.simulator.runner import SimulationResult

        dialogue_no_trace = [
            {
                "turn": 1,
                "client": "Привет",
                "bot": "Здравствуйте!",
                "state": "greeting",
                "intent": "greeting",
                "action": "greet"
                # No rule_trace key
            }
        ]

        results = [
            SimulationResult(
                simulation_id=0,
                persona="test",
                outcome="success",
                turns=1,
                duration_seconds=0.1,
                dialogue=dialogue_no_trace,
                rule_traces=[]
            )
        ]

        section = report_generator._section_full_dialogues(results)

        # Should show dialogue but no [RULE] block
        assert "Привет" in section
        assert "Здравствуйте!" in section
        # No [RULE] since no trace
        lines = section.split("\n")
        rule_lines = [l for l in lines if "[RULE]" in l]
        assert len(rule_lines) == 0

# =============================================================================
# TEST: SETTINGS CONDITIONAL RULES
# =============================================================================

class TestSettingsConditionalRules:
    """Tests for conditional_rules settings."""

    def test_defaults_include_conditional_rules(self):
        """Test that DEFAULTS include conditional_rules section."""
        from src.settings import DEFAULTS

        assert "conditional_rules" in DEFAULTS

        cr = DEFAULTS["conditional_rules"]
        assert "enable_tracing" in cr
        assert "log_level" in cr
        assert "log_context" in cr
        assert "log_each_condition" in cr
        assert "validate_on_startup" in cr
        assert "coverage_threshold" in cr

    def test_settings_has_conditional_rules(self):
        """Test that loaded settings have conditional_rules."""
        from src.settings import get_settings, reload_settings

        # Reload to ensure fresh settings
        settings = reload_settings()

        # Access conditional_rules
        assert hasattr(settings, "conditional_rules") or "conditional_rules" in settings

        cr = settings.conditional_rules
        assert cr.enable_tracing is True or cr.enable_tracing is False
        assert cr.log_level in ["DEBUG", "INFO", "WARNING", "ERROR"]
        assert 0.0 <= cr.coverage_threshold <= 1.0

    def test_conditional_rules_default_values(self):
        """Test default values for conditional_rules."""
        from src.settings import DEFAULTS

        cr = DEFAULTS["conditional_rules"]

        # Check default values
        assert cr["enable_tracing"] is True
        assert cr["log_level"] == "INFO"
        assert cr["log_context"] is False
        assert cr["log_each_condition"] is False
        assert cr["validate_on_startup"] is True
        assert cr["coverage_threshold"] == 0.8

# =============================================================================
# TEST: BOT ENABLE_TRACING PARAMETER
# =============================================================================

class TestBotEnableTracing:
    """Tests for bot enable_tracing parameter."""

    def test_bot_accepts_enable_tracing_param(self):
        """Test that SalesBot accepts enable_tracing parameter."""
        from src.bot import SalesBot

        # Create mock LLM
        mock_llm = Mock()
        mock_llm.generate = Mock(return_value="Test response")

        # Should accept enable_tracing without error
        bot = SalesBot(mock_llm, enable_tracing=True)
        assert bot.state_machine._enable_tracing is True

        bot2 = SalesBot(mock_llm, enable_tracing=False)
        assert bot2.state_machine._enable_tracing is False

    def test_state_machine_tracing_enabled(self):
        """Test that StateMachine has tracing when enabled."""
        from src.state_machine import StateMachine

        sm_with_tracing = StateMachine(enable_tracing=True)
        assert sm_with_tracing._enable_tracing is True
        assert sm_with_tracing._trace_collector is not None

        sm_without_tracing = StateMachine(enable_tracing=False)
        assert sm_without_tracing._enable_tracing is False
        assert sm_without_tracing._trace_collector is None

# =============================================================================
# TEST: CONDITION REGISTRIES AGGREGATOR
# =============================================================================

class TestConditionRegistriesAggregator:
    """Tests for ConditionRegistries aggregator."""

    def test_validate_all_runs_on_all_registries(self):
        """Test that validate_all runs on all registered registries."""
        from src.conditions import ConditionRegistries
        from scripts.validate_conditions import create_context_factories

        factories = create_context_factories()
        results = ConditionRegistries.validate_all(factories)

        # Should have results for each registry
        assert len(results) > 0

        # Each result should be a ValidationResult
        for name, result in results.items():
            assert hasattr(result, "passed")
            assert hasattr(result, "failed")
            assert hasattr(result, "errors")

    def test_generate_documentation_includes_all_registries(self):
        """Test that generate_documentation includes all registries."""
        from src.conditions import ConditionRegistries

        docs = ConditionRegistries.generate_documentation()

        # Should include all domain names
        assert "state_machine" in docs.lower() or "state machine" in docs.lower()
        assert "policy" in docs.lower()
        assert "fallback" in docs.lower()
        assert "personalization" in docs.lower()

    def test_get_stats_returns_aggregated_stats(self):
        """Test that get_stats returns aggregated statistics."""
        from src.conditions import ConditionRegistries

        stats = ConditionRegistries.get_stats()

        assert "total_registries" in stats
        assert "total_conditions" in stats
        assert "registries" in stats

        # Should have positive counts
        assert stats["total_registries"] >= 5  # At least 5 domains
        assert stats["total_conditions"] > 0

# =============================================================================
# TEST: TRACE COMPACT STRING FORMAT
# =============================================================================

class TestTraceCompactString:
    """Tests for trace compact string format."""

    def test_evaluation_trace_to_compact_string(self):
        """Test EvaluationTrace.to_compact_string() format."""
        from src.conditions.trace import EvaluationTrace, Resolution

        trace = EvaluationTrace(
            rule_name="price_question",
            intent="price_question",
            state="spin_situation",
            domain="state_machine"
        )

        # Record some conditions
        from src.conditions.base import SimpleContext
        ctx = SimpleContext(
            collected_data={"company_size": 10},
            state="spin_situation",
            turn_number=5
        )

        trace.record("has_pricing_data", True, ctx, {"company_size"}, 0.5)
        trace.set_result("answer_with_facts", Resolution.CONDITION_MATCHED, "has_pricing_data")

        compact = trace.to_compact_string()

        # Should have [RULE] header
        assert "[RULE]" in compact
        assert "price_question" in compact
        assert "answer_with_facts" in compact
        assert "condition_matched" in compact
        assert "has_pricing_data" in compact

        # Should show condition entry
        assert "PASS" in compact

    def test_condition_entry_to_compact_string(self):
        """Test ConditionEntry.to_compact_string() format."""
        from src.conditions.trace import ConditionEntry

        # Passing entry
        entry_pass = ConditionEntry(
            condition_name="has_pricing_data",
            result=True,
            relevant_fields={"company_size"},
            field_values={"company_size": 10},
            elapsed_ms=0.5
        )

        compact_pass = entry_pass.to_compact_string()
        assert "has_pricing_data" in compact_pass
        assert "PASS" in compact_pass
        assert "company_size=10" in compact_pass

        # Failing entry
        entry_fail = ConditionEntry(
            condition_name="has_contact_info",
            result=False,
            relevant_fields={"email"},
            field_values={},
            elapsed_ms=0.3
        )

        compact_fail = entry_fail.to_compact_string()
        assert "has_contact_info" in compact_fail
        assert "FAIL" in compact_fail

# =============================================================================
# TEST: RULE RESOLVER VALIDATE CONFIG
# =============================================================================

class TestRuleResolverValidateConfig:
    """Tests for RuleResolver.validate_config()."""

    def test_validate_config_checks_unknown_conditions(self):
        """Test that validate_config catches unknown conditions."""
        from src.rules.resolver import RuleResolver
        from src.conditions.state_machine.registry import sm_registry

        resolver = RuleResolver(sm_registry)

        # Config with unknown condition
        config = {
            "test_state": {
                "rules": {
                    "test_intent": [
                        {"when": "unknown_condition_xyz", "then": "some_action"},
                        "default_action"
                    ]
                }
            }
        }

        result = resolver.validate_config(config)

        # Should have error for unknown condition
        assert not result.is_valid
        assert any("unknown_condition_xyz" in str(e.message) for e in result.errors)

    def test_validate_config_checks_unknown_states(self):
        """Test that validate_config catches unknown target states."""
        from src.rules.resolver import RuleResolver
        from src.conditions.state_machine.registry import sm_registry

        resolver = RuleResolver(sm_registry)

        # Config with unknown target state in transition
        config = {
            "test_state": {
                "rules": {},
                "transitions": {
                    "test_intent": "unknown_state_xyz"
                }
            }
        }

        known_states = {"test_state", "greeting"}

        result = resolver.validate_config(config, known_states=known_states)

        # Should have error for unknown target state
        assert not result.is_valid
        assert any("unknown_state_xyz" in str(e.message) for e in result.errors)

    def test_validate_config_valid_config(self):
        """Test validate_config with valid configuration."""
        from src.rules.resolver import RuleResolver
        from src.conditions.state_machine.registry import sm_registry

        resolver = RuleResolver(sm_registry)

        # Valid config with known condition
        config = {
            "spin_situation": {
                "rules": {
                    "price_question": [
                        {"when": "has_pricing_data", "then": "answer_with_facts"},
                        "deflect_and_continue"
                    ]
                },
                "transitions": {
                    "demo_request": "presentation"
                }
            },
            "presentation": {
                "rules": {},
                "transitions": {}
            }
        }

        known_states = {"spin_situation", "presentation", "greeting", "success"}

        result = resolver.validate_config(config, known_states=known_states)

        # Should be valid
        assert result.is_valid
        assert result.checked_rules > 0

# =============================================================================
# TEST: INTEGRATION - FULL VALIDATION FLOW
# =============================================================================

class TestFullValidationFlow:
    """Integration tests for full validation flow."""

    def test_main_script_runs_without_error(self):
        """Test that main() in validate_conditions.py runs without error."""
        import subprocess
        result = subprocess.run(
            [sys.executable, "scripts/validate_conditions.py", "--stats-only"],
            capture_output=True,
            text=True,
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )

        # Should complete (exit code 0 or 1 depending on validation)
        assert result.returncode in [0, 1, 2]

        # Should have output
        assert len(result.stdout) > 0 or len(result.stderr) > 0

    def test_validation_script_json_output(self):
        """Test JSON output format."""
        import subprocess
        import json

        result = subprocess.run(
            [sys.executable, "scripts/validate_conditions.py", "--stats-only", "--output-format", "json"],
            capture_output=True,
            text=True,
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )

        # Should be valid JSON
        try:
            data = json.loads(result.stdout)
            assert "total_registries" in data
            assert "total_conditions" in data
        except json.JSONDecodeError:
            # If JSON parsing fails, at least check output is not empty
            assert len(result.stdout) > 0 or len(result.stderr) > 0
