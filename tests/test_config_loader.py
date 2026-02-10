"""
Tests for ConfigLoader.

Tests YAML configuration loading and validation.
"""

import pytest
from pathlib import Path
import tempfile
import yaml

class TestConfigLoader:
    """Tests for ConfigLoader."""

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
                "max_consecutive_objections": 3,
                "max_total_objections": 5,
                "max_gobacks": 2,
            },
            "intents": {
                "go_back": ["go_back", "correct_info"],
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
                "skip_phases": {
                    "cold": [],
                    "warm": ["spin_problem"],
                }
            },
            "guard": {
                "max_turns": 25,
                "high_frustration_threshold": 7,
            },
            "frustration": {
                "thresholds": {
                    "warning": 4,
                    "high": 7,
                    "critical": 9,
                }
            },
            "circular_flow": {
                "allowed_gobacks": {
                    "spin_problem": "spin_situation",
                }
            }
        }
        with open(tmp_path / "constants.yaml", 'w') as f:
            yaml.dump(constants, f)

        # Create states/sales_flow.yaml
        states = {
            "meta": {"version": "1.0"},
            "defaults": {"default_action": "continue"},
            "states": {
                "greeting": {
                    "goal": "Greet",
                    "transitions": {
                        "price_question": "spin_situation",
                    },
                    "rules": {
                        "greeting": "greet_back",
                    }
                },
                "spin_situation": {
                    "goal": "Understand situation",
                    "spin_phase": "situation",
                    "transitions": {
                        "data_complete": "spin_problem",
                    }
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
                "situation": {
                    "state": "spin_situation",
                    "skippable": False,
                },
                "problem": {
                    "state": "spin_problem",
                    "skippable": True,
                }
            }
        }
        with open(tmp_path / "spin" / "phases.yaml", 'w') as f:
            yaml.dump(spin, f)

        # Create conditions/custom.yaml
        custom = {
            "conditions": {
                "test_custom": {
                    "description": "Test",
                    "expression": {"and": ["cond1", "cond2"]}
                }
            },
            "aliases": {
                "tc": "custom:test_custom"
            }
        }
        with open(tmp_path / "conditions" / "custom.yaml", 'w') as f:
            yaml.dump(custom, f)

        return tmp_path

    def test_load_valid_config(self, config_dir):
        """Test loading valid configuration."""
        from src.config_loader import ConfigLoader

        loader = ConfigLoader(config_dir)
        config = loader.load()

        assert config.states is not None
        assert "greeting" in config.states
        assert "spin_situation" in config.states
        assert config.spin_phases == ["situation", "problem"]
        assert config.default_action == "continue"

    def test_load_states(self, config_dir):
        """Test that states are loaded correctly."""
        from src.config_loader import ConfigLoader

        loader = ConfigLoader(config_dir)
        config = loader.load()

        assert len(config.states) == 3
        assert config.states["greeting"]["goal"] == "Greet"
        assert config.states["spin_situation"]["spin_phase"] == "situation"

    def test_load_constants(self, config_dir):
        """Test that constants are loaded."""
        from src.config_loader import ConfigLoader

        loader = ConfigLoader(config_dir)
        config = loader.load()

        assert config.limits["max_consecutive_objections"] == 3
        assert config.limits["max_total_objections"] == 5
        assert config.guard["max_turns"] == 25

    def test_load_custom_conditions(self, config_dir):
        """Test that custom conditions are loaded."""
        from src.config_loader import ConfigLoader

        loader = ConfigLoader(config_dir)
        config = loader.load()

        assert "test_custom" in config.custom_conditions
        assert config.condition_aliases["tc"] == "custom:test_custom"

    def test_get_state_config(self, config_dir):
        """Test get_state_config method."""
        from src.config_loader import ConfigLoader

        loader = ConfigLoader(config_dir)
        config = loader.load()

        state_config = config.get_state_config("greeting")
        assert state_config is not None
        assert state_config["goal"] == "Greet"

        # Non-existent state
        assert config.get_state_config("nonexistent") is None

    def test_get_state_transitions(self, config_dir):
        """Test get_state_transitions method."""
        from src.config_loader import ConfigLoader

        loader = ConfigLoader(config_dir)
        config = loader.load()

        transitions = config.get_state_transitions("greeting")
        assert "price_question" in transitions
        assert transitions["price_question"] == "spin_situation"

    def test_get_spin_state(self, config_dir):
        """Test get_spin_state method."""
        from src.config_loader import ConfigLoader

        loader = ConfigLoader(config_dir)
        config = loader.load()

        assert config.get_spin_state("situation") == "spin_situation"
        assert config.get_spin_state("problem") == "spin_problem"

    def test_is_phase_skippable(self, config_dir):
        """Test is_phase_skippable method."""
        from src.config_loader import ConfigLoader

        loader = ConfigLoader(config_dir)
        config = loader.load()

        assert config.is_phase_skippable("situation") is False
        assert config.is_phase_skippable("problem") is True

    def test_missing_required_file(self, tmp_path):
        """Test error when required file is missing."""
        from src.config_loader import ConfigLoader, ConfigLoadError

        loader = ConfigLoader(tmp_path)

        with pytest.raises(ConfigLoadError):
            loader.load()

    def test_invalid_yaml(self, tmp_path):
        """Test error when YAML is invalid."""
        from src.config_loader import ConfigLoader, ConfigLoadError

        # Create invalid YAML
        (tmp_path / "states").mkdir()
        (tmp_path / "spin").mkdir()
        (tmp_path / "conditions").mkdir()

        with open(tmp_path / "constants.yaml", 'w') as f:
            f.write("invalid: yaml: content: [")

        with pytest.raises(ConfigLoadError):
            ConfigLoader(tmp_path).load()

class TestConfigValidation:
    """Tests for configuration validation."""

    @pytest.fixture
    def base_config_dir(self, tmp_path):
        """Create base config directory."""
        (tmp_path / "states").mkdir()
        (tmp_path / "spin").mkdir()
        (tmp_path / "conditions").mkdir()
        return tmp_path

    def _write_configs(self, config_dir, constants, states, spin):
        """Helper to write config files."""
        with open(config_dir / "constants.yaml", 'w') as f:
            yaml.dump(constants, f)
        with open(config_dir / "states" / "sales_flow.yaml", 'w') as f:
            yaml.dump(states, f)
        with open(config_dir / "spin" / "phases.yaml", 'w') as f:
            yaml.dump(spin, f)
        # Empty custom.yaml
        with open(config_dir / "conditions" / "custom.yaml", 'w') as f:
            yaml.dump({}, f)

    def test_valid_config_passes(self, base_config_dir):
        """Test that valid config passes validation."""
        from src.config_loader import ConfigLoader

        constants = {
            "spin": {"states": {"situation": "spin_situation"}},
            "guard": {"high_frustration_threshold": 7},
            "frustration": {"thresholds": {"high": 7}},
            "circular_flow": {"allowed_gobacks": {}},
            "lead_scoring": {"skip_phases": {}},
        }
        states = {
            "states": {
                "greeting": {"transitions": {"test": "spin_situation"}},
                "spin_situation": {},
            }
        }
        spin = {"phase_order": ["situation"], "phases": {"situation": {"state": "spin_situation"}}}

        self._write_configs(base_config_dir, constants, states, spin)

        loader = ConfigLoader(base_config_dir)
        config = loader.load()  # Should not raise

        assert config is not None

    def test_unknown_transition_target(self, base_config_dir):
        """Test error for unknown transition target."""
        from src.config_loader import ConfigLoader, ConfigValidationError

        constants = {
            "spin": {"states": {}},
            "guard": {"high_frustration_threshold": 7},
            "frustration": {"thresholds": {"high": 7}},
            "circular_flow": {"allowed_gobacks": {}},
            "lead_scoring": {"skip_phases": {}},
        }
        states = {
            "states": {
                "greeting": {"transitions": {"test": "nonexistent_state"}},
            }
        }
        spin = {"phase_order": [], "phases": {}}

        self._write_configs(base_config_dir, constants, states, spin)

        with pytest.raises(ConfigValidationError) as exc_info:
            ConfigLoader(base_config_dir).load()

        assert "nonexistent_state" in str(exc_info.value)

    def test_threshold_mismatch_error(self, base_config_dir):
        """Test error when guard and frustration thresholds don't match."""
        from src.config_loader import ConfigLoader, ConfigValidationError

        constants = {
            "spin": {"states": {}},
            "guard": {"high_frustration_threshold": 7},
            "frustration": {"thresholds": {"high": 5}},  # Mismatch!
            "circular_flow": {"allowed_gobacks": {}},
            "lead_scoring": {"skip_phases": {}},
        }
        states = {"states": {"greeting": {}}}
        spin = {"phase_order": [], "phases": {}}

        self._write_configs(base_config_dir, constants, states, spin)

        with pytest.raises(ConfigValidationError) as exc_info:
            ConfigLoader(base_config_dir).load()

        assert "Threshold mismatch" in str(exc_info.value)

    def test_skip_validation(self, base_config_dir):
        """Test that validation can be skipped."""
        from src.config_loader import ConfigLoader

        constants = {
            "spin": {"states": {}},
            "guard": {"high_frustration_threshold": 7},
            "frustration": {"thresholds": {"high": 5}},  # Would fail validation
            "circular_flow": {"allowed_gobacks": {}},
            "lead_scoring": {"skip_phases": {}},
        }
        states = {"states": {"greeting": {"transitions": {"test": "nonexistent"}}}}
        spin = {"phase_order": [], "phases": {}}

        self._write_configs(base_config_dir, constants, states, spin)

        # Should not raise when validation is skipped
        config = ConfigLoader(base_config_dir).load(validate=False)
        assert config is not None

class TestGlobalConfig:
    """Tests for global config functions."""

    def test_get_config_singleton(self, tmp_path):
        """Test that get_config returns same instance."""
        from src.config_loader import init_config, get_config

        # Create minimal valid config
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
        states = {"states": {"greeting": {}}}
        spin = {"phase_order": [], "phases": {}}

        with open(tmp_path / "constants.yaml", 'w') as f:
            yaml.dump(constants, f)
        with open(tmp_path / "states" / "sales_flow.yaml", 'w') as f:
            yaml.dump(states, f)
        with open(tmp_path / "spin" / "phases.yaml", 'w') as f:
            yaml.dump(spin, f)
        with open(tmp_path / "conditions" / "custom.yaml", 'w') as f:
            yaml.dump({}, f)

        config1 = init_config(tmp_path)
        config2 = get_config()

        assert config1 is config2
