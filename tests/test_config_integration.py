"""
Integration tests for YAML configuration system.

Tests the full flow from YAML files through ConfigLoader,
ConditionExpressionParser, RuleResolver, to StateMachine.
"""

import pytest
from pathlib import Path
import yaml

class MockContext:
    """Mock context for condition evaluation."""
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)
        self.collected_data = kwargs.get('collected_data', {})
        self.state = kwargs.get('state', 'greeting')
        self.turn_number = kwargs.get('turn_number', 0)

class MockRegistry:
    """Mock registry that returns predefined values."""
    def __init__(self, conditions: dict = None):
        self._conditions = conditions or {}
        self.name = "mock_registry"

    def has(self, name: str) -> bool:
        return name in self._conditions

    def evaluate(self, name: str, ctx, trace=None) -> bool:
        if name not in self._conditions:
            from src.conditions.registry import ConditionNotFoundError
            raise ConditionNotFoundError(name, self.name)
        value = self._conditions[name]
        if callable(value):
            return value(ctx)
        return value

    def list_all(self):
        return list(self._conditions.keys())

class TestFullConfigIntegration:
    """Tests for full configuration integration."""

    @pytest.fixture
    def full_config_dir(self, tmp_path):
        """Create a complete config directory."""
        (tmp_path / "states").mkdir()
        (tmp_path / "spin").mkdir()
        (tmp_path / "conditions").mkdir()

        # Constants with all sections
        constants = {
            "spin": {
                "phases": ["situation", "problem", "implication"],
                "states": {
                    "situation": "spin_situation",
                    "problem": "spin_problem",
                    "implication": "spin_implication",
                },
            },
            "limits": {
                "max_consecutive_objections": 3,
                "max_total_objections": 5,
                "max_gobacks": 2,
            },
            "intents": {
                "go_back": ["go_back", "correct_info"],
                "categories": {
                    "objection": ["objection_price", "objection_no_time"],
                    "positive": ["agreement", "demo_request"],
                    "question": ["price_question"],
                }
            },
            "policy": {
                "overlay_allowed_states": ["spin_situation", "spin_problem"],
                "protected_states": ["greeting", "success"],
            },
            "lead_scoring": {
                "skip_phases": {
                    "cold": [],
                    "warm": ["spin_implication"],
                    "hot": ["spin_problem", "spin_implication"],
                }
            },
            "guard": {
                "max_turns": 25,
                "high_frustration_threshold": 7,
            },
            "frustration": {
                "thresholds": {"warning": 4, "high": 7, "critical": 9}
            },
            "circular_flow": {
                "allowed_gobacks": {
                    "spin_problem": "spin_situation",
                    "spin_implication": "spin_problem",
                }
            }
        }
        with open(tmp_path / "constants.yaml", 'w') as f:
            yaml.dump(constants, f)

        # States with conditional rules
        states = {
            "meta": {"version": "1.0"},
            "defaults": {"default_action": "continue_current_goal"},
            "states": {
                "greeting": {
                    "goal": "Greet",
                    "transitions": {
                        "price_question": "spin_situation",
                        "demo_request": "close",
                    },
                    "rules": {
                        "greeting": "greet_back",
                        "price_question": [
                            {"when": "has_pricing_data", "then": "answer_with_facts"},
                            "deflect_and_continue"
                        ]
                    }
                },
                "spin_situation": {
                    "goal": "Understand situation",
                    "spin_phase": "situation",
                    "transitions": {
                        "data_complete": "spin_problem",
                    },
                    "rules": {
                        "price_question": [
                            {"when": {"and": ["has_pricing_data", "can_answer"]}, "then": "answer_facts"},
                            {"when": "has_pricing_data", "then": "partial_answer"},
                            "deflect"
                        ]
                    }
                },
                "spin_problem": {
                    "goal": "Find problems",
                    "spin_phase": "problem",
                    "transitions": {
                        "data_complete": "spin_implication",
                    }
                },
                "spin_implication": {
                    "goal": "Show implications",
                    "spin_phase": "implication",
                },
                "close": {
                    "goal": "Close deal",
                },
                "success": {
                    "goal": "Success",
                    "is_final": True,
                }
            }
        }
        with open(tmp_path / "states" / "sales_flow.yaml", 'w') as f:
            yaml.dump(states, f)

        # SPIN phases
        spin = {
            "phase_order": ["situation", "problem", "implication"],
            "phases": {
                "situation": {"state": "spin_situation", "skippable": False},
                "problem": {"state": "spin_problem", "skippable": True},
                "implication": {"state": "spin_implication", "skippable": True},
            }
        }
        with open(tmp_path / "spin" / "phases.yaml", 'w') as f:
            yaml.dump(spin, f)

        # Custom conditions
        custom = {
            "conditions": {
                "ready_for_demo": {
                    "description": "Client ready for demo",
                    "expression": {
                        "and": [
                            "has_contact",
                            {"or": ["has_pain", "has_interest"]},
                            {"not": "is_frustrated"}
                        ]
                    }
                },
                "can_skip_problem": {
                    "description": "Can skip problem phase",
                    "expression": {
                        "or": ["has_explicit_pain", "lead_is_hot"]
                    }
                }
            },
            "aliases": {
                "demo_ready": "custom:ready_for_demo"
            }
        }
        with open(tmp_path / "conditions" / "custom.yaml", 'w') as f:
            yaml.dump(custom, f)

        return tmp_path

    def test_load_full_config(self, full_config_dir):
        """Test loading complete configuration."""
        from src.config_loader import ConfigLoader

        loader = ConfigLoader(full_config_dir)
        config = loader.load()

        assert len(config.states) == 6
        assert len(config.spin_phases) == 3
        assert len(config.custom_conditions) == 2

    def test_config_with_expression_parser(self, full_config_dir):
        """Test config with expression parser for custom conditions."""
        from src.config_loader import ConfigLoader
        from src.conditions.expression_parser import ConditionExpressionParser

        loader = ConfigLoader(full_config_dir)
        config = loader.load()

        registry = MockRegistry({
            "has_contact": True,
            "has_pain": False,
            "has_interest": True,
            "is_frustrated": False,
            "has_explicit_pain": True,
            "lead_is_hot": False,
        })

        parser = ConditionExpressionParser(registry, config.custom_conditions)

        # Test ready_for_demo
        expr = parser.parse("custom:ready_for_demo")
        ctx = MockContext()
        result = expr.evaluate(ctx)
        # has_contact AND (has_pain OR has_interest) AND NOT is_frustrated
        # True AND (False OR True) AND True = True
        assert result is True

    def test_rule_resolver_with_composite_from_config(self, full_config_dir):
        """Test RuleResolver with composite conditions from config."""
        from src.config_loader import ConfigLoader
        from src.conditions.expression_parser import ConditionExpressionParser
        from src.rules.resolver import RuleResolver

        loader = ConfigLoader(full_config_dir)
        config = loader.load()

        registry = MockRegistry({
            "has_pricing_data": True,
            "can_answer": True,
        })

        parser = ConditionExpressionParser(registry, config.custom_conditions)
        resolver = RuleResolver(
            registry,
            default_action=config.default_action,
            expression_parser=parser
        )

        state_rules = config.get_state_rules("spin_situation")
        ctx = MockContext()

        action = resolver.resolve_action(
            "price_question",
            state_rules=state_rules,
            global_rules={},
            ctx=ctx
        )

        # Both conditions true, should match first rule
        assert action == "answer_facts"

    def test_rule_resolver_fallback_in_chain(self, full_config_dir):
        """Test RuleResolver falls back in rule chain."""
        from src.config_loader import ConfigLoader
        from src.conditions.expression_parser import ConditionExpressionParser
        from src.rules.resolver import RuleResolver

        loader = ConfigLoader(full_config_dir)
        config = loader.load()

        registry = MockRegistry({
            "has_pricing_data": False,  # This makes all conditions fail
            "can_answer": True,
        })

        parser = ConditionExpressionParser(registry, config.custom_conditions)
        resolver = RuleResolver(
            registry,
            default_action=config.default_action,
            expression_parser=parser
        )

        state_rules = config.get_state_rules("spin_situation")
        ctx = MockContext()

        action = resolver.resolve_action(
            "price_question",
            state_rules=state_rules,
            global_rules={},
            ctx=ctx
        )

        # All conditions false, should fall back to "deflect"
        assert action == "deflect"

    def test_skip_phases_by_temperature(self, full_config_dir):
        """Test skip_phases configuration by lead temperature."""
        from src.config_loader import ConfigLoader

        loader = ConfigLoader(full_config_dir)
        config = loader.load()

        # Cold lead - no phases skipped
        cold_skip = config.get_skip_phases_for_temperature("cold")
        assert cold_skip == []

        # Warm lead - implication skipped
        warm_skip = config.get_skip_phases_for_temperature("warm")
        assert "spin_implication" in warm_skip

        # Hot lead - problem and implication skipped
        hot_skip = config.get_skip_phases_for_temperature("hot")
        assert "spin_problem" in hot_skip
        assert "spin_implication" in hot_skip

    def test_circular_flow_from_config(self, full_config_dir):
        """Test circular flow allowed_gobacks from config."""
        from src.config_loader import ConfigLoader

        loader = ConfigLoader(full_config_dir)
        config = loader.load()

        gobacks = config.circular_flow.get("allowed_gobacks", {})

        assert gobacks["spin_problem"] == "spin_situation"
        assert gobacks["spin_implication"] == "spin_problem"

class TestConfigConstants:
    """Tests for centralized constants module."""

    def test_constants_load_from_yaml(self):
        """Test that constants module loads from YAML."""
        from src.yaml_config.constants import (
            SPIN_PHASES, SPIN_STATES,
            MAX_CONSECUTIVE_OBJECTIONS, MAX_TOTAL_OBJECTIONS,
            OBJECTION_INTENTS, POSITIVE_INTENTS,
        )

        # These should be loaded from constants.yaml
        assert isinstance(SPIN_PHASES, list)
        assert len(SPIN_PHASES) >= 4  # situation, problem, implication, need_payoff

        assert isinstance(SPIN_STATES, dict)
        assert "situation" in SPIN_STATES

        assert isinstance(MAX_CONSECUTIVE_OBJECTIONS, int)
        assert MAX_CONSECUTIVE_OBJECTIONS > 0

        assert isinstance(OBJECTION_INTENTS, list)
        assert "objection_price" in OBJECTION_INTENTS

    def test_frustration_constants(self):
        """Test frustration-related constants."""
        from src.yaml_config.constants import (
            FRUSTRATION_WEIGHTS, FRUSTRATION_DECAY,
            FRUSTRATION_THRESHOLDS, MAX_FRUSTRATION
        )

        assert isinstance(FRUSTRATION_WEIGHTS, dict)
        assert "frustrated" in FRUSTRATION_WEIGHTS

        assert isinstance(FRUSTRATION_DECAY, dict)
        assert "positive" in FRUSTRATION_DECAY

        assert isinstance(FRUSTRATION_THRESHOLDS, dict)
        assert "warning" in FRUSTRATION_THRESHOLDS
        assert "high" in FRUSTRATION_THRESHOLDS
        assert "critical" in FRUSTRATION_THRESHOLDS

        assert isinstance(MAX_FRUSTRATION, int)
        assert MAX_FRUSTRATION == 10

    def test_guard_config(self):
        """Test guard configuration constants."""
        from src.yaml_config.constants import GUARD_CONFIG

        assert isinstance(GUARD_CONFIG, dict)
        assert "max_turns" in GUARD_CONFIG
        assert "high_frustration_threshold" in GUARD_CONFIG

    def test_policy_constants(self):
        """Test policy-related constants."""
        from src.yaml_config.constants import (
            OVERLAY_ALLOWED_STATES, PROTECTED_STATES,
            AGGRESSIVE_ACTIONS
        )

        assert isinstance(OVERLAY_ALLOWED_STATES, set)
        assert "spin_situation" in OVERLAY_ALLOWED_STATES

        assert isinstance(PROTECTED_STATES, set)
        assert "greeting" in PROTECTED_STATES

        assert isinstance(AGGRESSIVE_ACTIONS, set)

class TestConfigValidationIntegration:
    """Tests for config validation in integration scenarios."""

    def test_validation_catches_invalid_transitions(self, tmp_path):
        """Test that validation catches invalid state transitions."""
        from src.config_loader import ConfigLoader, ConfigValidationError

        (tmp_path / "states").mkdir()
        (tmp_path / "spin").mkdir()
        (tmp_path / "conditions").mkdir()

        constants = {
            "spin": {"states": {}},
            "guard": {"high_frustration_threshold": 7},
            "frustration": {"thresholds": {"high": 7}},
            "circular_flow": {"allowed_gobacks": {}},
            "lead_scoring": {"skip_phases": {}},
        }
        with open(tmp_path / "constants.yaml", 'w') as f:
            yaml.dump(constants, f)

        states = {
            "states": {
                "greeting": {
                    "transitions": {
                        "test": "nonexistent_state"  # Invalid!
                    }
                }
            }
        }
        with open(tmp_path / "states" / "sales_flow.yaml", 'w') as f:
            yaml.dump(states, f)

        with open(tmp_path / "spin" / "phases.yaml", 'w') as f:
            yaml.dump({"phase_order": [], "phases": {}}, f)

        with open(tmp_path / "conditions" / "custom.yaml", 'w') as f:
            yaml.dump({}, f)

        with pytest.raises(ConfigValidationError) as exc_info:
            ConfigLoader(tmp_path).load()

        assert "nonexistent_state" in str(exc_info.value)

    def test_validation_catches_threshold_mismatch(self, tmp_path):
        """Test that validation catches threshold mismatches."""
        from src.config_loader import ConfigLoader, ConfigValidationError

        (tmp_path / "states").mkdir()
        (tmp_path / "spin").mkdir()
        (tmp_path / "conditions").mkdir()

        constants = {
            "spin": {"states": {}},
            "guard": {"high_frustration_threshold": 7},
            "frustration": {"thresholds": {"high": 5}},  # Mismatch!
            "circular_flow": {"allowed_gobacks": {}},
            "lead_scoring": {"skip_phases": {}},
        }
        with open(tmp_path / "constants.yaml", 'w') as f:
            yaml.dump(constants, f)

        with open(tmp_path / "states" / "sales_flow.yaml", 'w') as f:
            yaml.dump({"states": {"greeting": {}}}, f)

        with open(tmp_path / "spin" / "phases.yaml", 'w') as f:
            yaml.dump({"phase_order": [], "phases": {}}, f)

        with open(tmp_path / "conditions" / "custom.yaml", 'w') as f:
            yaml.dump({}, f)

        with pytest.raises(ConfigValidationError) as exc_info:
            ConfigLoader(tmp_path).load()

        assert "Threshold mismatch" in str(exc_info.value)

class TestRealConfigFiles:
    """Tests that verify the actual config files in src/config/."""

    def test_load_real_config(self):
        """Test loading the actual config files."""
        from src.config_loader import ConfigLoader

        loader = ConfigLoader()  # Uses default path
        config = loader.load()

        # Verify structure
        assert len(config.states) > 0
        assert len(config.spin_phases) == 4
        assert "situation" in config.spin_phases

        # Verify key states exist
        assert "greeting" in config.states
        assert "spin_situation" in config.states
        assert "close" in config.states

    def test_real_custom_conditions(self):
        """Test custom conditions from real config."""
        from src.config_loader import ConfigLoader

        loader = ConfigLoader()
        config = loader.load()

        # Should have custom conditions
        assert len(config.custom_conditions) > 0

        # Check some expected conditions exist
        assert "ready_for_demo" in config.custom_conditions
        assert "needs_repair" in config.custom_conditions

    def test_real_spin_config(self):
        """Test SPIN configuration from real config."""
        from src.config_loader import ConfigLoader

        loader = ConfigLoader()
        config = loader.load()

        # Verify SPIN phases
        assert config.spin_phases == ["situation", "problem", "implication", "need_payoff"]

        # Verify phase states
        assert config.get_spin_state("situation") == "spin_situation"
        assert config.get_spin_state("problem") == "spin_problem"

        # Verify skippability
        assert config.is_phase_skippable("situation") is False
        assert config.is_phase_skippable("implication") is True

    def test_real_threshold_sync(self):
        """Test that real config has synced thresholds."""
        from src.config_loader import ConfigLoader

        loader = ConfigLoader()
        config = loader.load()

        guard_threshold = config.guard.get("high_frustration_threshold")
        frustration_high = config.frustration.get("thresholds", {}).get("high")

        assert guard_threshold == frustration_high, \
            f"Thresholds not synced: guard={guard_threshold}, frustration={frustration_high}"
