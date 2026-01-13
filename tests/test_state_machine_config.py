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


class TestDynamicSpinConfiguration:
    """
    Tests for dynamic SPIN configuration from YAML.

    Verifies that StateMachine reads SPIN phases, states, and progress intents
    from config instead of hardcoded values.
    """

    @pytest.fixture
    def custom_spin_config_dir(self, tmp_path):
        """Create config with custom SPIN phases (only 2 phases instead of 4)."""
        (tmp_path / "states").mkdir()
        (tmp_path / "spin").mkdir()
        (tmp_path / "conditions").mkdir()

        # Custom constants with only 2 SPIN phases
        constants = {
            "spin": {
                "phases": ["discovery", "solution"],  # Custom phase names
                "states": {
                    "discovery": "spin_discovery",
                    "solution": "spin_solution",
                },
                "progress_intents": {
                    "discovery_complete": "discovery",
                    "solution_accepted": "solution",
                }
            },
            "limits": {
                "max_consecutive_objections": 3,
                "max_total_objections": 5,
                "max_gobacks": 2,
            },
            "intents": {
                "go_back": ["go_back"],
                "categories": {
                    "objection": ["objection_price"],
                    "positive": ["agreement"],
                }
            },
            "policy": {},
            "lead_scoring": {"skip_phases": {}},
            "guard": {"high_frustration_threshold": 7},
            "frustration": {"thresholds": {"high": 7}},
            "circular_flow": {
                "allowed_gobacks": {
                    "spin_solution": "spin_discovery",
                }
            }
        }
        with open(tmp_path / "constants.yaml", 'w') as f:
            yaml.dump(constants, f)

        # States with custom SPIN
        states = {
            "states": {
                "greeting": {
                    "goal": "Greet",
                    "transitions": {"any": "spin_discovery"},
                },
                "spin_discovery": {
                    "goal": "Discover needs",
                    "spin_phase": "discovery",
                    "transitions": {
                        "data_complete": "spin_solution",
                        "discovery_complete": "spin_solution",
                    }
                },
                "spin_solution": {
                    "goal": "Present solution",
                    "spin_phase": "solution",
                    "transitions": {"data_complete": "close"}
                },
                "close": {
                    "goal": "Close deal",
                    "is_final": True,
                }
            }
        }
        with open(tmp_path / "states" / "sales_flow.yaml", 'w') as f:
            yaml.dump(states, f)

        spin = {
            "phase_order": ["discovery", "solution"],
            "phases": {
                "discovery": {"state": "spin_discovery", "skippable": False},
                "solution": {"state": "spin_solution", "skippable": False}
            }
        }
        with open(tmp_path / "spin" / "phases.yaml", 'w') as f:
            yaml.dump(spin, f)

        with open(tmp_path / "conditions" / "custom.yaml", 'w') as f:
            yaml.dump({}, f)

        return tmp_path

    def test_spin_progress_intents_property(self, custom_spin_config_dir):
        """Test spin_progress_intents property reads from config."""
        from src.state_machine import StateMachine
        from src.config_loader import ConfigLoader

        loader = ConfigLoader(custom_spin_config_dir)
        config = loader.load()

        sm = StateMachine(config=config)

        # Should use custom progress intents from config
        assert sm.spin_progress_intents == {
            "discovery_complete": "discovery",
            "solution_accepted": "solution",
        }

    def test_spin_phases_property_from_config(self, custom_spin_config_dir):
        """Test spin_phases property reads from config."""
        from src.state_machine import StateMachine
        from src.config_loader import ConfigLoader

        loader = ConfigLoader(custom_spin_config_dir)
        config = loader.load()

        sm = StateMachine(config=config)

        # Should use custom phases
        assert sm.spin_phases == ["discovery", "solution"]
        assert len(sm.spin_phases) == 2

    def test_spin_states_property_from_config(self, custom_spin_config_dir):
        """Test spin_states property reads from config."""
        from src.state_machine import StateMachine
        from src.config_loader import ConfigLoader

        loader = ConfigLoader(custom_spin_config_dir)
        config = loader.load()

        sm = StateMachine(config=config)

        # Should use custom state mapping
        assert sm.spin_states["discovery"] == "spin_discovery"
        assert sm.spin_states["solution"] == "spin_solution"
        assert "situation" not in sm.spin_states

    def test_get_next_spin_state_uses_config(self, custom_spin_config_dir):
        """Test _get_next_spin_state uses config phases and states."""
        from src.state_machine import StateMachine
        from src.config_loader import ConfigLoader

        loader = ConfigLoader(custom_spin_config_dir)
        config = loader.load()

        sm = StateMachine(config=config)

        # Test transition from discovery to solution
        next_state = sm._get_next_spin_state("discovery")
        assert next_state == "spin_solution"

        # Test last phase returns presentation
        next_state = sm._get_next_spin_state("solution")
        assert next_state == "presentation"

        # Test unknown phase returns None
        next_state = sm._get_next_spin_state("situation")  # Not in config
        assert next_state is None

    def test_is_spin_phase_progression_uses_config(self, custom_spin_config_dir):
        """Test _is_spin_phase_progression uses config phases."""
        from src.state_machine import StateMachine
        from src.config_loader import ConfigLoader

        loader = ConfigLoader(custom_spin_config_dir)
        config = loader.load()

        sm = StateMachine(config=config)

        # Test valid progression
        assert sm._is_spin_phase_progression("discovery", "discovery") is True
        assert sm._is_spin_phase_progression("solution", "discovery") is True

        # Test backward = not progression
        assert sm._is_spin_phase_progression("discovery", "solution") is False

        # Test unknown phases
        assert sm._is_spin_phase_progression("situation", "discovery") is False
        assert sm._is_spin_phase_progression("discovery", "problem") is False

    def test_apply_rules_uses_config_progress_intents(self, custom_spin_config_dir):
        """Test apply_rules uses spin_progress_intents from config."""
        from src.state_machine import StateMachine
        from src.config_loader import ConfigLoader

        loader = ConfigLoader(custom_spin_config_dir)
        config = loader.load()

        sm = StateMachine(config=config)
        sm.state = "spin_discovery"

        # Process custom progress intent
        action, next_state = sm.apply_rules("discovery_complete")

        # Should transition using custom intent
        assert next_state == "spin_solution"

    def test_states_config_uses_yaml_states(self, custom_spin_config_dir):
        """Test states_config property returns YAML states."""
        from src.state_machine import StateMachine
        from src.config_loader import ConfigLoader

        loader = ConfigLoader(custom_spin_config_dir)
        config = loader.load()

        sm = StateMachine(config=config)

        # Should have custom states
        assert "spin_discovery" in sm.states_config
        assert "spin_solution" in sm.states_config
        # Should NOT have standard SPIN states
        assert "spin_situation" not in sm.states_config
        assert "spin_problem" not in sm.states_config

    def test_fallback_to_constants_without_config(self):
        """Test fallback to Python constants when no config provided."""
        from src.state_machine import StateMachine
        from src.yaml_config.constants import (
            SPIN_PHASES as CONST_SPIN_PHASES,
            SPIN_STATES as CONST_SPIN_STATES,
            SPIN_PROGRESS_INTENTS as CONST_SPIN_PROGRESS_INTENTS,
        )

        sm = StateMachine()

        # Should fall back to imported constants
        assert sm.spin_phases == CONST_SPIN_PHASES
        assert sm.spin_states == CONST_SPIN_STATES
        assert sm.spin_progress_intents == CONST_SPIN_PROGRESS_INTENTS


class TestAlteredSpinFlow:
    """
    Integration tests for state machine with altered SPIN flow.

    Tests complete dialog flows with custom SPIN phases.
    """

    @pytest.fixture
    def three_phase_config_dir(self, tmp_path):
        """Create config with 3 custom SPIN phases."""
        (tmp_path / "states").mkdir()
        (tmp_path / "spin").mkdir()
        (tmp_path / "conditions").mkdir()

        constants = {
            "spin": {
                "phases": ["explore", "understand", "propose"],
                "states": {
                    "explore": "spin_explore",
                    "understand": "spin_understand",
                    "propose": "spin_propose",
                },
                "progress_intents": {
                    "context_gathered": "explore",
                    "needs_identified": "understand",
                    "solution_ready": "propose",
                }
            },
            "limits": {"max_consecutive_objections": 3, "max_total_objections": 5, "max_gobacks": 2},
            "intents": {"go_back": ["go_back"], "categories": {"objection": [], "positive": ["agreement"]}},
            "policy": {},
            "lead_scoring": {"skip_phases": {}},
            "guard": {"high_frustration_threshold": 7},
            "frustration": {"thresholds": {"high": 7}},
            "circular_flow": {"allowed_gobacks": {}},
        }
        with open(tmp_path / "constants.yaml", 'w') as f:
            yaml.dump(constants, f)

        states = {
            "states": {
                "greeting": {"goal": "Greet", "transitions": {"any": "spin_explore"}},
                "spin_explore": {
                    "goal": "Explore context",
                    "spin_phase": "explore",
                    "transitions": {"data_complete": "spin_understand", "context_gathered": "spin_understand"}
                },
                "spin_understand": {
                    "goal": "Understand needs",
                    "spin_phase": "understand",
                    "transitions": {"data_complete": "spin_propose", "needs_identified": "spin_propose"}
                },
                "spin_propose": {
                    "goal": "Propose solution",
                    "spin_phase": "propose",
                    "transitions": {"data_complete": "presentation", "solution_ready": "presentation"}
                },
                "presentation": {"goal": "Present", "transitions": {"agreement": "success"}},
                "success": {"goal": "Done", "is_final": True}
            }
        }
        with open(tmp_path / "states" / "sales_flow.yaml", 'w') as f:
            yaml.dump(states, f)

        spin = {
            "phase_order": ["explore", "understand", "propose"],
            "phases": {
                "explore": {"state": "spin_explore", "skippable": False},
                "understand": {"state": "spin_understand", "skippable": True},
                "propose": {"state": "spin_propose", "skippable": True},
            }
        }
        with open(tmp_path / "spin" / "phases.yaml", 'w') as f:
            yaml.dump(spin, f)

        with open(tmp_path / "conditions" / "custom.yaml", 'w') as f:
            yaml.dump({}, f)

        return tmp_path

    def test_complete_custom_spin_flow(self, three_phase_config_dir):
        """Test complete flow through custom 3-phase SPIN."""
        from src.state_machine import StateMachine
        from src.config_loader import ConfigLoader

        loader = ConfigLoader(three_phase_config_dir)
        config = loader.load()

        sm = StateMachine(config=config)

        # Start at greeting
        assert sm.state == "greeting"

        # Move to explore
        result = sm.process("greeting")
        assert sm.state == "spin_explore"
        assert sm._get_current_spin_phase() == "explore"

        # Progress through custom phases using custom intents
        result = sm.process("context_gathered")
        assert sm.state == "spin_understand"
        assert sm._get_current_spin_phase() == "understand"

        result = sm.process("needs_identified")
        assert sm.state == "spin_propose"
        assert sm._get_current_spin_phase() == "propose"

        result = sm.process("solution_ready")
        assert sm.state == "presentation"

    def test_get_next_spin_state_with_three_phases(self, three_phase_config_dir):
        """Test _get_next_spin_state works with 3 custom phases."""
        from src.state_machine import StateMachine
        from src.config_loader import ConfigLoader

        loader = ConfigLoader(three_phase_config_dir)
        config = loader.load()

        sm = StateMachine(config=config)

        # Test progression through 3 phases
        assert sm._get_next_spin_state("explore") == "spin_understand"
        assert sm._get_next_spin_state("understand") == "spin_propose"
        assert sm._get_next_spin_state("propose") == "presentation"

    def test_phase_progression_validation(self, three_phase_config_dir):
        """Test _is_spin_phase_progression with 3 phases."""
        from src.state_machine import StateMachine
        from src.config_loader import ConfigLoader

        loader = ConfigLoader(three_phase_config_dir)
        config = loader.load()

        sm = StateMachine(config=config)

        # Forward progression
        assert sm._is_spin_phase_progression("explore", "explore") is True
        assert sm._is_spin_phase_progression("understand", "explore") is True
        assert sm._is_spin_phase_progression("propose", "explore") is True
        assert sm._is_spin_phase_progression("propose", "understand") is True

        # Backward = not progression
        assert sm._is_spin_phase_progression("explore", "understand") is False
        assert sm._is_spin_phase_progression("explore", "propose") is False
