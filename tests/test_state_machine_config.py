"""
Tests for StateMachine with ConfigLoader integration.

Tests that StateMachine correctly uses YAML configuration
and falls back to Python constants when config is not provided.
"""

import pytest
from pathlib import Path
import yaml
import tempfile


class TestStateMachineWithConfig:
    """Tests for StateMachine with LoadedConfig."""

    @pytest.fixture
    def config_dir(self, tmp_path):
        """Create a temporary config directory with test files."""
        # Create subdirectories
        (tmp_path / "states").mkdir()
        (tmp_path / "spin").mkdir()
        (tmp_path / "conditions").mkdir()

        # Create constants.yaml
        constants = {
            "spin": {
                "phases": ["situation", "problem"],
                "states": {
                    "situation": "spin_situation",
                    "problem": "spin_problem",
                },
                "progress_intents": {
                    "situation_provided": "situation",
                    "problem_revealed": "problem",
                }
            },
            "limits": {
                "max_consecutive_objections": 2,  # Custom value
                "max_total_objections": 4,        # Custom value
                "max_gobacks": 1,                 # Custom value
            },
            "intents": {
                "go_back": ["go_back"],
                "categories": {
                    "objection": ["objection_price"],
                    "positive": ["agreement"],
                }
            },
            "policy": {
                "overlay_allowed_states": ["spin_situation"],
                "protected_states": ["greeting"],
            },
            "lead_scoring": {
                "skip_phases": {"cold": [], "warm": ["spin_problem"]}
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
                    "greeting": "spin_situation",  # Custom goback
                }
            }
        }
        with open(tmp_path / "constants.yaml", 'w') as f:
            yaml.dump(constants, f)

        # Create states/sales_flow.yaml
        states = {
            "meta": {"version": "1.0"},
            "defaults": {"default_action": "custom_default_action"},
            "states": {
                "greeting": {
                    "goal": "Greet",
                    "transitions": {"price_question": "spin_situation"},
                    "rules": {"greeting": "greet_back"}
                },
                "spin_situation": {
                    "goal": "Understand",
                    "spin_phase": "situation",
                    "transitions": {"data_complete": "spin_problem"}
                },
                "spin_problem": {
                    "goal": "Find problems",
                    "spin_phase": "problem",
                }
            }
        }
        with open(tmp_path / "states" / "sales_flow.yaml", 'w') as f:
            yaml.dump(states, f)

        # Create spin/phases.yaml
        spin = {
            "phase_order": ["situation", "problem"],
            "phases": {
                "situation": {"state": "spin_situation", "skippable": False},
                "problem": {"state": "spin_problem", "skippable": True}
            }
        }
        with open(tmp_path / "spin" / "phases.yaml", 'w') as f:
            yaml.dump(spin, f)

        # Create conditions/custom.yaml
        custom = {"conditions": {}, "aliases": {}}
        with open(tmp_path / "conditions" / "custom.yaml", 'w') as f:
            yaml.dump(custom, f)

        return tmp_path

    def test_state_machine_without_config(self):
        """Test StateMachine works without config (backward compatibility)."""
        from src.state_machine import StateMachine

        sm = StateMachine()

        assert sm.state == "greeting"
        assert sm._config is None
        # Should use Python constants
        assert sm.max_consecutive_objections == 3
        assert sm.max_total_objections == 5

    def test_state_machine_with_config(self, config_dir):
        """Test StateMachine uses config values."""
        from src.state_machine import StateMachine
        from src.config_loader import ConfigLoader

        loader = ConfigLoader(config_dir)
        config = loader.load()

        sm = StateMachine(config=config)

        assert sm._config is config
        # Should use config values
        assert sm.max_consecutive_objections == 2
        assert sm.max_total_objections == 4

    def test_spin_phases_from_config(self, config_dir):
        """Test SPIN phases are loaded from config."""
        from src.state_machine import StateMachine
        from src.config_loader import ConfigLoader

        loader = ConfigLoader(config_dir)
        config = loader.load()

        sm = StateMachine(config=config)

        assert sm.spin_phases == ["situation", "problem"]

    def test_spin_states_from_config(self, config_dir):
        """Test SPIN states mapping from config."""
        from src.state_machine import StateMachine
        from src.config_loader import ConfigLoader

        loader = ConfigLoader(config_dir)
        config = loader.load()

        sm = StateMachine(config=config)

        assert sm.spin_states["situation"] == "spin_situation"
        assert sm.spin_states["problem"] == "spin_problem"

    def test_states_config_from_yaml(self, config_dir):
        """Test states configuration is loaded from YAML."""
        from src.state_machine import StateMachine
        from src.config_loader import ConfigLoader

        loader = ConfigLoader(config_dir)
        config = loader.load()

        sm = StateMachine(config=config)

        assert "greeting" in sm.states_config
        assert "spin_situation" in sm.states_config
        assert sm.states_config["greeting"]["goal"] == "Greet"

    def test_circular_flow_with_config(self, config_dir):
        """Test CircularFlowManager uses config."""
        from src.state_machine import StateMachine
        from src.config_loader import ConfigLoader

        loader = ConfigLoader(config_dir)
        config = loader.load()

        sm = StateMachine(config=config)

        # Should use custom max_gobacks
        assert sm.circular_flow.max_gobacks == 1
        # Should have custom allowed_gobacks
        assert "greeting" in sm.circular_flow.allowed_gobacks

    def test_objection_limit_with_config(self, config_dir):
        """Test objection limits use config values."""
        from src.state_machine import StateMachine
        from src.config_loader import ConfigLoader

        loader = ConfigLoader(config_dir)
        config = loader.load()

        sm = StateMachine(config=config)

        # Record objections (IntentTracker.record takes intent, state)
        sm.intent_tracker.record("objection_price", "greeting")
        sm.intent_tracker.record("objection_price", "greeting")

        # With config, limit is 2, so 2 objections should hit limit
        assert sm._check_objection_limit() is True

    def test_default_action_from_config(self, config_dir):
        """Test default action is loaded from config."""
        from src.state_machine import StateMachine
        from src.config_loader import ConfigLoader

        loader = ConfigLoader(config_dir)
        config = loader.load()

        sm = StateMachine(config=config)

        # RuleResolver should use custom default action
        assert sm._resolver.default_action == "custom_default_action"


class TestCircularFlowManager:
    """Tests for CircularFlowManager with custom config."""

    def test_default_values(self):
        """Test CircularFlowManager uses defaults without config."""
        from src.state_machine import CircularFlowManager

        cfm = CircularFlowManager()

        assert cfm.max_gobacks == 2
        assert "spin_problem" in cfm.allowed_gobacks
        assert cfm.allowed_gobacks["spin_problem"] == "spin_situation"

    def test_custom_max_gobacks(self):
        """Test custom max_gobacks."""
        from src.state_machine import CircularFlowManager

        cfm = CircularFlowManager(max_gobacks=5)

        assert cfm.max_gobacks == 5
        assert cfm.get_remaining_gobacks() == 5

    def test_custom_allowed_gobacks(self):
        """Test custom allowed_gobacks mapping."""
        from src.state_machine import CircularFlowManager

        custom_gobacks = {
            "state_b": "state_a",
            "state_c": "state_b",
        }
        cfm = CircularFlowManager(allowed_gobacks=custom_gobacks)

        assert cfm.allowed_gobacks == custom_gobacks
        assert cfm.can_go_back("state_b") is True
        assert cfm.can_go_back("state_a") is False

    def test_go_back_respects_limit(self):
        """Test go_back respects max_gobacks limit."""
        from src.state_machine import CircularFlowManager

        cfm = CircularFlowManager(max_gobacks=1)

        # First go back should work
        result = cfm.go_back("spin_problem")
        assert result == "spin_situation"

        # Second should fail (limit reached)
        result = cfm.go_back("spin_problem")
        assert result is None

    def test_go_back_with_custom_mapping(self):
        """Test go_back uses custom mapping."""
        from src.state_machine import CircularFlowManager

        cfm = CircularFlowManager(
            allowed_gobacks={"custom_state": "target_state"},
            max_gobacks=2
        )

        result = cfm.go_back("custom_state")
        assert result == "target_state"

    def test_reset_clears_count(self):
        """Test reset clears goback count."""
        from src.state_machine import CircularFlowManager

        cfm = CircularFlowManager(max_gobacks=2)
        cfm.go_back("spin_problem")
        cfm.go_back("spin_implication")

        assert cfm.goback_count == 2

        cfm.reset()

        assert cfm.goback_count == 0
        assert cfm.get_remaining_gobacks() == 2


class TestStateMachineReset:
    """Tests for StateMachine reset with config."""

    def test_reset_preserves_config(self, tmp_path):
        """Test that reset preserves the config reference."""
        from src.state_machine import StateMachine
        from src.config_loader import ConfigLoader

        # Create minimal config
        self._create_minimal_config(tmp_path)

        loader = ConfigLoader(tmp_path)
        config = loader.load()

        sm = StateMachine(config=config)
        sm.state = "spin_situation"
        sm.collected_data = {"test": "data"}

        sm.reset()

        assert sm.state == "greeting"
        assert sm.collected_data == {}
        assert sm._config is config  # Config preserved

    def _create_minimal_config(self, tmp_path):
        """Helper to create minimal valid config."""
        (tmp_path / "states").mkdir()
        (tmp_path / "spin").mkdir()
        (tmp_path / "conditions").mkdir()

        constants = {
            "spin": {"states": {}},
            "limits": {"max_gobacks": 2},
            "guard": {"high_frustration_threshold": 7},
            "frustration": {"thresholds": {"high": 7}},
            "circular_flow": {"allowed_gobacks": {}},
            "lead_scoring": {"skip_phases": {}},
        }
        with open(tmp_path / "constants.yaml", 'w') as f:
            yaml.dump(constants, f)

        states = {"states": {"greeting": {}}}
        with open(tmp_path / "states" / "sales_flow.yaml", 'w') as f:
            yaml.dump(states, f)

        spin = {"phase_order": [], "phases": {}}
        with open(tmp_path / "spin" / "phases.yaml", 'w') as f:
            yaml.dump(spin, f)

        with open(tmp_path / "conditions" / "custom.yaml", 'w') as f:
            yaml.dump({}, f)


class TestStateMachineTracing:
    """Tests for StateMachine tracing with config."""

    def test_tracing_enabled(self):
        """Test tracing can be enabled."""
        from src.state_machine import StateMachine

        sm = StateMachine(enable_tracing=True)

        assert sm._enable_tracing is True
        assert sm._trace_collector is not None

    def test_tracing_with_config(self, tmp_path):
        """Test tracing works with config."""
        from src.state_machine import StateMachine
        from src.config_loader import ConfigLoader

        # Create minimal config
        (tmp_path / "states").mkdir()
        (tmp_path / "spin").mkdir()
        (tmp_path / "conditions").mkdir()

        constants = {
            "spin": {"states": {}},
            "limits": {},
            "guard": {"high_frustration_threshold": 7},
            "frustration": {"thresholds": {"high": 7}},
            "circular_flow": {"allowed_gobacks": {}},
            "lead_scoring": {"skip_phases": {}},
        }
        with open(tmp_path / "constants.yaml", 'w') as f:
            yaml.dump(constants, f)

        states = {"states": {"greeting": {}}}
        with open(tmp_path / "states" / "sales_flow.yaml", 'w') as f:
            yaml.dump(states, f)

        spin = {"phase_order": [], "phases": {}}
        with open(tmp_path / "spin" / "phases.yaml", 'w') as f:
            yaml.dump(spin, f)

        with open(tmp_path / "conditions" / "custom.yaml", 'w') as f:
            yaml.dump({}, f)

        loader = ConfigLoader(tmp_path)
        config = loader.load()

        sm = StateMachine(enable_tracing=True, config=config)

        assert sm._enable_tracing is True
        assert sm._config is config
