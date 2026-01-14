"""
Tests for Flow Loading functionality.

Tests the new modular flow system with extends, mixins, and parameter substitution.
"""

import pytest
from pathlib import Path
import yaml


class TestFlowConfig:
    """Tests for FlowConfig dataclass."""

    def test_flow_config_creation(self):
        """Test creating FlowConfig with all fields."""
        from src.config_loader import FlowConfig

        flow = FlowConfig(
            name="test_flow",
            version="2.0",
            description="Test flow",
            states={"greeting": {"goal": "Greet"}},
            phases={
                "order": ["phase1", "phase2"],
                "mapping": {"phase1": "state1", "phase2": "state2"},
                "post_phases_state": "closing",
                "progress_intents": {"intent1": "phase1"},
                "skip_conditions": {"phase2": ["condition1"]},
            },
            priorities=[{"name": "test", "priority": 100}],
            variables={"company": "TestCo"},
            entry_points={"default": "greeting", "hot_lead": "closing"},
            templates={},
        )

        assert flow.name == "test_flow"
        assert flow.version == "2.0"
        assert flow.phase_order == ["phase1", "phase2"]
        assert flow.post_phases_state == "closing"
        assert flow.phase_mapping == {"phase1": "state1", "phase2": "state2"}
        assert flow.progress_intents == {"intent1": "phase1"}
        assert flow.skip_conditions == {"phase2": ["condition1"]}

    def test_flow_config_defaults(self):
        """Test FlowConfig with minimal fields."""
        from src.config_loader import FlowConfig

        flow = FlowConfig(name="minimal")

        assert flow.version == "1.0"
        assert flow.phases is None
        assert flow.phase_order == []
        assert flow.post_phases_state is None
        assert flow.phase_mapping == {}

    def test_get_state_for_phase(self):
        """Test get_state_for_phase method."""
        from src.config_loader import FlowConfig

        flow = FlowConfig(
            name="test",
            phases={"mapping": {"situation": "spin_situation"}}
        )

        assert flow.get_state_for_phase("situation") == "spin_situation"
        assert flow.get_state_for_phase("unknown") is None

    def test_get_entry_point(self):
        """Test get_entry_point method."""
        from src.config_loader import FlowConfig

        flow = FlowConfig(
            name="test",
            entry_points={"default": "greeting", "hot_lead": "presentation"}
        )

        assert flow.get_entry_point() == "greeting"
        assert flow.get_entry_point("default") == "greeting"
        assert flow.get_entry_point("hot_lead") == "presentation"
        assert flow.get_entry_point("unknown") == "greeting"

    def test_get_variable(self):
        """Test get_variable method."""
        from src.config_loader import FlowConfig

        flow = FlowConfig(
            name="test",
            variables={"company": "TestCo", "product": "CRM"}
        )

        assert flow.get_variable("company") == "TestCo"
        assert flow.get_variable("unknown") is None
        assert flow.get_variable("unknown", "default") == "default"


class TestFlowLoading:
    """Tests for load_flow functionality."""

    @pytest.fixture
    def flow_config_dir(self, tmp_path):
        """Create a temporary config directory with flow files."""
        # Create directories
        (tmp_path / "flows" / "_base").mkdir(parents=True)
        (tmp_path / "flows" / "test_flow").mkdir(parents=True)

        # Create _base/states.yaml
        base_states = {
            "states": {
                "_base_greeting": {
                    "abstract": True,
                    "goal": "Base greeting goal",
                    "rules": {
                        "greeting": "greet_back",
                        "unclear": "ask_how_to_help",
                    }
                },
                "greeting": {
                    "extends": "_base_greeting",
                    "transitions": {
                        "rejection": "soft_close",
                    }
                },
                "soft_close": {
                    "goal": "Close softly",
                    "is_final": False,
                },
                "success": {
                    "goal": "Success",
                    "is_final": True,
                }
            }
        }
        with open(tmp_path / "flows" / "_base" / "states.yaml", 'w') as f:
            yaml.dump(base_states, f)

        # Create _base/mixins.yaml
        base_mixins = {
            "mixins": {
                "price_handling": {
                    "rules": {
                        "price_question": "answer_with_facts",
                        "pricing_details": "answer_with_facts",
                    }
                },
                "exit_intents": {
                    "transitions": {
                        "rejection": "soft_close",
                        "farewell": "soft_close",
                    }
                },
                "combined": {
                    "includes": ["price_handling", "exit_intents"],
                }
            }
        }
        with open(tmp_path / "flows" / "_base" / "mixins.yaml", 'w') as f:
            yaml.dump(base_mixins, f)

        # Create _base/priorities.yaml
        base_priorities = {
            "default_priorities": [
                {"name": "final_state", "priority": 0, "condition": "is_final"},
                {"name": "rejection", "priority": 100, "intents": ["rejection"]},
                {"name": "default", "priority": 999, "action": "continue"},
            ]
        }
        with open(tmp_path / "flows" / "_base" / "priorities.yaml", 'w') as f:
            yaml.dump(base_priorities, f)

        # Create test_flow/flow.yaml
        flow_yaml = {
            "flow": {
                "name": "test_flow",
                "version": "1.0",
                "description": "Test flow for unit tests",
                "variables": {
                    "entry_state": "test_state",
                    "company_name": "TestCompany",
                },
                "phases": {
                    "order": ["phase1", "phase2"],
                    "mapping": {
                        "phase1": "test_state",
                        "phase2": "test_state_2",
                    },
                    "post_phases_state": "success",
                },
                "entry_points": {
                    "default": "greeting",
                    "fast_track": "test_state_2",
                }
            }
        }
        with open(tmp_path / "flows" / "test_flow" / "flow.yaml", 'w') as f:
            yaml.dump(flow_yaml, f)

        # Create test_flow/states.yaml
        flow_states = {
            "states": {
                "_test_base": {
                    "abstract": True,
                    "mixins": ["price_handling", "exit_intents"],
                    "goal": "Base test goal",
                },
                "test_state": {
                    "extends": "_test_base",
                    "goal": "Test state goal",
                    "phase": "phase1",
                    "transitions": {
                        "data_complete": "test_state_2",
                    },
                    "rules": {
                        "custom_intent": "custom_action",
                    }
                },
                "test_state_2": {
                    "extends": "_test_base",
                    "goal": "Test state 2",
                    "phase": "phase2",
                    "transitions": {
                        "data_complete": "success",
                    }
                }
            }
        }
        with open(tmp_path / "flows" / "test_flow" / "states.yaml", 'w') as f:
            yaml.dump(flow_states, f)

        return tmp_path

    def test_load_flow_basic(self, flow_config_dir):
        """Test basic flow loading."""
        from src.config_loader import ConfigLoader

        loader = ConfigLoader(flow_config_dir)
        flow = loader.load_flow("test_flow")

        assert flow.name == "test_flow"
        assert flow.version == "1.0"
        assert "greeting" in flow.states
        assert "test_state" in flow.states
        assert "test_state_2" in flow.states

    def test_load_flow_phases(self, flow_config_dir):
        """Test that phases are loaded correctly."""
        from src.config_loader import ConfigLoader

        loader = ConfigLoader(flow_config_dir)
        flow = loader.load_flow("test_flow")

        assert flow.phase_order == ["phase1", "phase2"]
        assert flow.post_phases_state == "success"
        assert flow.phase_mapping == {"phase1": "test_state", "phase2": "test_state_2"}

    def test_load_flow_extends(self, flow_config_dir):
        """Test that extends inheritance works."""
        from src.config_loader import ConfigLoader

        loader = ConfigLoader(flow_config_dir)
        flow = loader.load_flow("test_flow")

        # test_state extends _test_base which has mixins
        test_state = flow.states["test_state"]

        # Should have inherited rules from price_handling mixin
        assert "price_question" in test_state.get("rules", {})
        assert test_state["rules"]["price_question"] == "answer_with_facts"

        # Should have its own rule
        assert test_state["rules"]["custom_intent"] == "custom_action"

    def test_load_flow_mixins(self, flow_config_dir):
        """Test that mixins are applied correctly."""
        from src.config_loader import ConfigLoader

        loader = ConfigLoader(flow_config_dir)
        flow = loader.load_flow("test_flow")

        test_state = flow.states["test_state"]

        # From exit_intents mixin
        assert "rejection" in test_state.get("transitions", {})
        assert test_state["transitions"]["rejection"] == "soft_close"

        # Own transition should override/add
        assert test_state["transitions"]["data_complete"] == "test_state_2"

    def test_load_flow_base_states(self, flow_config_dir):
        """Test that base states are included."""
        from src.config_loader import ConfigLoader

        loader = ConfigLoader(flow_config_dir)
        flow = loader.load_flow("test_flow")

        # greeting from _base/states.yaml
        assert "greeting" in flow.states
        assert "soft_close" in flow.states
        assert "success" in flow.states

    def test_load_flow_abstract_excluded(self, flow_config_dir):
        """Test that abstract states are not included in final states."""
        from src.config_loader import ConfigLoader

        loader = ConfigLoader(flow_config_dir)
        flow = loader.load_flow("test_flow")

        # Abstract states should not be in final states
        assert "_base_greeting" not in flow.states
        assert "_test_base" not in flow.states

    def test_load_flow_priorities(self, flow_config_dir):
        """Test that priorities are loaded."""
        from src.config_loader import ConfigLoader

        loader = ConfigLoader(flow_config_dir)
        flow = loader.load_flow("test_flow")

        assert len(flow.priorities) == 3
        assert flow.priorities[0]["name"] == "final_state"
        assert flow.priorities[0]["priority"] == 0

    def test_load_flow_entry_points(self, flow_config_dir):
        """Test entry points loading."""
        from src.config_loader import ConfigLoader

        loader = ConfigLoader(flow_config_dir)
        flow = loader.load_flow("test_flow")

        assert flow.get_entry_point() == "greeting"
        assert flow.get_entry_point("fast_track") == "test_state_2"

    def test_load_flow_not_found(self, flow_config_dir):
        """Test error when flow doesn't exist."""
        from src.config_loader import ConfigLoader, ConfigLoadError

        loader = ConfigLoader(flow_config_dir)

        with pytest.raises(ConfigLoadError) as exc_info:
            loader.load_flow("nonexistent_flow")

        assert "not found" in str(exc_info.value)


class TestParameterSubstitution:
    """Tests for parameter substitution in flows."""

    @pytest.fixture
    def param_flow_dir(self, tmp_path):
        """Create flow with parameter templates."""
        (tmp_path / "flows" / "_base").mkdir(parents=True)
        (tmp_path / "flows" / "param_flow").mkdir(parents=True)

        # Empty base files
        with open(tmp_path / "flows" / "_base" / "states.yaml", 'w') as f:
            yaml.dump({"states": {}}, f)
        with open(tmp_path / "flows" / "_base" / "mixins.yaml", 'w') as f:
            yaml.dump({"mixins": {}}, f)
        with open(tmp_path / "flows" / "_base" / "priorities.yaml", 'w') as f:
            yaml.dump({"default_priorities": []}, f)

        # Flow with parameters
        flow_yaml = {
            "flow": {
                "name": "param_flow",
                "variables": {
                    "entry_state": "custom_entry",
                    "default_action": "custom_continue",
                },
                "entry_points": {
                    "default": "greeting",
                }
            }
        }
        with open(tmp_path / "flows" / "param_flow" / "flow.yaml", 'w') as f:
            yaml.dump(flow_yaml, f)

        # States with parameter placeholders
        states_yaml = {
            "states": {
                "greeting": {
                    "goal": "Greet",
                    "transitions": {
                        "next": "{{entry_state}}",
                    },
                    "rules": {
                        "unclear": "{{default_action}}",
                    }
                },
                "custom_entry": {
                    "goal": "Custom entry state",
                }
            }
        }
        with open(tmp_path / "flows" / "param_flow" / "states.yaml", 'w') as f:
            yaml.dump(states_yaml, f)

        return tmp_path

    def test_parameter_substitution_in_transitions(self, param_flow_dir):
        """Test that parameters are substituted in transitions."""
        from src.config_loader import ConfigLoader

        loader = ConfigLoader(param_flow_dir)
        flow = loader.load_flow("param_flow")

        greeting = flow.states["greeting"]
        assert greeting["transitions"]["next"] == "custom_entry"

    def test_parameter_substitution_in_rules(self, param_flow_dir):
        """Test that parameters are substituted in rules."""
        from src.config_loader import ConfigLoader

        loader = ConfigLoader(param_flow_dir)
        flow = loader.load_flow("param_flow")

        greeting = flow.states["greeting"]
        assert greeting["rules"]["unclear"] == "custom_continue"


class TestPriorityOverrides:
    """Tests for priority override mechanism."""

    @pytest.fixture
    def priority_flow_dir(self, tmp_path):
        """Create flow with priority overrides."""
        (tmp_path / "flows" / "_base").mkdir(parents=True)
        (tmp_path / "flows" / "priority_flow").mkdir(parents=True)

        # Base priorities
        base_priorities = {
            "default_priorities": [
                {"name": "first", "priority": 100, "action": "first_action"},
                {"name": "second", "priority": 200, "action": "second_action"},
                {"name": "third", "priority": 300, "action": "third_action"},
            ]
        }
        with open(tmp_path / "flows" / "_base" / "priorities.yaml", 'w') as f:
            yaml.dump(base_priorities, f)

        with open(tmp_path / "flows" / "_base" / "states.yaml", 'w') as f:
            yaml.dump({"states": {"greeting": {"goal": "Greet"}}}, f)
        with open(tmp_path / "flows" / "_base" / "mixins.yaml", 'w') as f:
            yaml.dump({"mixins": {}}, f)

        # Flow with overrides
        flow_yaml = {
            "flow": {
                "name": "priority_flow",
                "priorities": {
                    "extends": "default_priorities",
                    "overrides": [
                        {"name": "second", "priority": 50},  # Change priority
                        {"name": "first", "action": "new_first_action"},  # Change action
                    ]
                },
                "entry_points": {"default": "greeting"}
            }
        }
        with open(tmp_path / "flows" / "priority_flow" / "flow.yaml", 'w') as f:
            yaml.dump(flow_yaml, f)

        with open(tmp_path / "flows" / "priority_flow" / "states.yaml", 'w') as f:
            yaml.dump({"states": {}}, f)

        return tmp_path

    def test_priority_override_value(self, priority_flow_dir):
        """Test that priority values can be overridden."""
        from src.config_loader import ConfigLoader

        loader = ConfigLoader(priority_flow_dir)
        flow = loader.load_flow("priority_flow")

        # Find "second" priority
        second = next(p for p in flow.priorities if p["name"] == "second")
        assert second["priority"] == 50  # Changed from 200

    def test_priority_override_action(self, priority_flow_dir):
        """Test that priority actions can be overridden."""
        from src.config_loader import ConfigLoader

        loader = ConfigLoader(priority_flow_dir)
        flow = loader.load_flow("priority_flow")

        # Find "first" priority
        first = next(p for p in flow.priorities if p["name"] == "first")
        assert first["action"] == "new_first_action"  # Changed


class TestDeepMerge:
    """Tests for deep merge functionality."""

    def test_deep_merge_basic(self):
        """Test basic deep merge."""
        from src.config_loader import ConfigLoader

        loader = ConfigLoader()

        base = {"a": 1, "b": {"c": 2}}
        override = {"b": {"d": 3}, "e": 4}

        result = loader._deep_merge(base, override)

        assert result == {"a": 1, "b": {"c": 2, "d": 3}, "e": 4}

    def test_deep_merge_override(self):
        """Test that override values take precedence."""
        from src.config_loader import ConfigLoader

        loader = ConfigLoader()

        base = {"a": 1, "b": {"c": 2}}
        override = {"a": 10, "b": {"c": 20}}

        result = loader._deep_merge(base, override)

        assert result == {"a": 10, "b": {"c": 20}}

    def test_deep_merge_lists_replaced(self):
        """Test that lists are replaced, not merged."""
        from src.config_loader import ConfigLoader

        loader = ConfigLoader()

        base = {"a": [1, 2, 3]}
        override = {"a": [4, 5]}

        result = loader._deep_merge(base, override)

        assert result == {"a": [4, 5]}


class TestMixinIncludes:
    """Tests for mixin includes (nested mixins)."""

    @pytest.fixture
    def mixin_includes_dir(self, tmp_path):
        """Create flow with nested mixin includes."""
        (tmp_path / "flows" / "_base").mkdir(parents=True)
        (tmp_path / "flows" / "include_flow").mkdir(parents=True)

        # Mixins with includes
        mixins = {
            "mixins": {
                "mixin_a": {
                    "rules": {"intent_a": "action_a"}
                },
                "mixin_b": {
                    "rules": {"intent_b": "action_b"}
                },
                "combined_mixin": {
                    "includes": ["mixin_a", "mixin_b"],
                    "rules": {"intent_c": "action_c"}
                }
            }
        }
        with open(tmp_path / "flows" / "_base" / "mixins.yaml", 'w') as f:
            yaml.dump(mixins, f)

        with open(tmp_path / "flows" / "_base" / "states.yaml", 'w') as f:
            yaml.dump({"states": {}}, f)
        with open(tmp_path / "flows" / "_base" / "priorities.yaml", 'w') as f:
            yaml.dump({"default_priorities": []}, f)

        # Flow using combined mixin
        flow_yaml = {
            "flow": {
                "name": "include_flow",
                "entry_points": {"default": "test_state"}
            }
        }
        with open(tmp_path / "flows" / "include_flow" / "flow.yaml", 'w') as f:
            yaml.dump(flow_yaml, f)

        states_yaml = {
            "states": {
                "test_state": {
                    "goal": "Test",
                    "mixins": ["combined_mixin"],
                }
            }
        }
        with open(tmp_path / "flows" / "include_flow" / "states.yaml", 'w') as f:
            yaml.dump(states_yaml, f)

        return tmp_path

    def test_mixin_includes_resolved(self, mixin_includes_dir):
        """Test that mixin includes are properly resolved."""
        from src.config_loader import ConfigLoader

        loader = ConfigLoader(mixin_includes_dir)
        flow = loader.load_flow("include_flow")

        test_state = flow.states["test_state"]
        rules = test_state.get("rules", {})

        # Should have rules from all included mixins
        assert "intent_a" in rules  # From mixin_a
        assert "intent_b" in rules  # From mixin_b
        assert "intent_c" in rules  # From combined_mixin itself


class TestStateMachineWithFlowConfig:
    """Tests for StateMachine integration with FlowConfig."""

    @pytest.fixture
    def flow_with_sm(self, tmp_path):
        """Create flow and StateMachine for testing."""
        # Create directories
        (tmp_path / "flows" / "_base").mkdir(parents=True)
        (tmp_path / "flows" / "test_flow").mkdir(parents=True)

        # Create base files
        with open(tmp_path / "flows" / "_base" / "states.yaml", 'w') as f:
            yaml.dump({"states": {"success": {"goal": "Success", "is_final": True}}}, f)
        with open(tmp_path / "flows" / "_base" / "mixins.yaml", 'w') as f:
            yaml.dump({"mixins": {}}, f)
        with open(tmp_path / "flows" / "_base" / "priorities.yaml", 'w') as f:
            yaml.dump({"default_priorities": []}, f)

        # Create test flow
        flow_yaml = {
            "flow": {
                "name": "test_flow",
                "phases": {
                    "order": ["alpha", "beta", "gamma"],
                    "mapping": {
                        "alpha": "state_alpha",
                        "beta": "state_beta",
                        "gamma": "state_gamma",
                    },
                    "post_phases_state": "closing",
                    "skip_conditions": {
                        "gamma": ["has_high_interest"],
                    },
                },
                "entry_points": {"default": "state_alpha"}
            }
        }
        with open(tmp_path / "flows" / "test_flow" / "flow.yaml", 'w') as f:
            yaml.dump(flow_yaml, f)

        states_yaml = {
            "states": {
                "state_alpha": {"goal": "Alpha", "phase": "alpha"},
                "state_beta": {"goal": "Beta", "phase": "beta"},
                "state_gamma": {"goal": "Gamma", "phase": "gamma"},
                "closing": {"goal": "Close"},
            }
        }
        with open(tmp_path / "flows" / "test_flow" / "states.yaml", 'w') as f:
            yaml.dump(states_yaml, f)

        return tmp_path

    def test_sm_with_flow_phase_order(self, flow_with_sm):
        """Test that StateMachine uses FlowConfig phase_order."""
        from src.config_loader import ConfigLoader
        from src.state_machine import StateMachine

        loader = ConfigLoader(flow_with_sm)
        flow = loader.load_flow("test_flow")
        sm = StateMachine(flow=flow)

        assert sm.phase_order == ["alpha", "beta", "gamma"]

    def test_sm_with_flow_phase_states(self, flow_with_sm):
        """Test that StateMachine uses FlowConfig phase_states."""
        from src.config_loader import ConfigLoader
        from src.state_machine import StateMachine

        loader = ConfigLoader(flow_with_sm)
        flow = loader.load_flow("test_flow")
        sm = StateMachine(flow=flow)

        assert sm.phase_states == {
            "alpha": "state_alpha",
            "beta": "state_beta",
            "gamma": "state_gamma",
        }

    def test_sm_with_flow_post_phases_state(self, flow_with_sm):
        """Test that StateMachine uses FlowConfig post_phases_state."""
        from src.config_loader import ConfigLoader
        from src.state_machine import StateMachine

        loader = ConfigLoader(flow_with_sm)
        flow = loader.load_flow("test_flow")
        sm = StateMachine(flow=flow)

        assert sm._post_phases_state == "closing"

    def test_sm_with_flow_states_config(self, flow_with_sm):
        """Test that StateMachine uses FlowConfig states."""
        from src.config_loader import ConfigLoader
        from src.state_machine import StateMachine

        loader = ConfigLoader(flow_with_sm)
        flow = loader.load_flow("test_flow")
        sm = StateMachine(flow=flow)

        assert "state_alpha" in sm.states_config
        assert "state_beta" in sm.states_config
        assert "closing" in sm.states_config

    def test_sm_with_flow_get_current_phase(self, flow_with_sm):
        """Test _get_current_phase with FlowConfig."""
        from src.config_loader import ConfigLoader
        from src.state_machine import StateMachine

        loader = ConfigLoader(flow_with_sm)
        flow = loader.load_flow("test_flow")
        sm = StateMachine(flow=flow)

        sm.state = "state_alpha"
        assert sm._get_current_phase() == "alpha"

        sm.state = "state_beta"
        assert sm._get_current_phase() == "beta"

    def test_sm_with_flow_next_phase_state(self, flow_with_sm):
        """Test _get_next_phase_state with FlowConfig."""
        from src.config_loader import ConfigLoader
        from src.state_machine import StateMachine

        loader = ConfigLoader(flow_with_sm)
        flow = loader.load_flow("test_flow")
        sm = StateMachine(flow=flow)

        assert sm._get_next_phase_state("alpha") == "state_beta"
        assert sm._get_next_phase_state("beta") == "state_gamma"
        assert sm._get_next_phase_state("gamma") == "closing"  # post_phases_state


class TestFlowValidation:
    """Tests for flow validation."""

    @pytest.fixture
    def validation_flow_dir(self, tmp_path):
        """Create flow for validation tests."""
        (tmp_path / "flows" / "_base").mkdir(parents=True)
        (tmp_path / "flows" / "valid_flow").mkdir(parents=True)
        (tmp_path / "flows" / "invalid_flow").mkdir(parents=True)

        # Base files
        with open(tmp_path / "flows" / "_base" / "states.yaml", 'w') as f:
            yaml.dump({"states": {}}, f)
        with open(tmp_path / "flows" / "_base" / "mixins.yaml", 'w') as f:
            yaml.dump({"mixins": {}}, f)
        with open(tmp_path / "flows" / "_base" / "priorities.yaml", 'w') as f:
            yaml.dump({"default_priorities": []}, f)

        # Valid flow
        valid_flow = {
            "flow": {
                "name": "valid_flow",
                "phases": {
                    "order": ["phase1"],
                    "mapping": {"phase1": "state1"},
                },
                "entry_points": {"default": "state1"}
            }
        }
        with open(tmp_path / "flows" / "valid_flow" / "flow.yaml", 'w') as f:
            yaml.dump(valid_flow, f)
        with open(tmp_path / "flows" / "valid_flow" / "states.yaml", 'w') as f:
            yaml.dump({"states": {"state1": {"goal": "State 1"}}}, f)

        # Invalid flow - phase references nonexistent state
        invalid_flow = {
            "flow": {
                "name": "invalid_flow",
                "phases": {
                    "order": ["phase1"],
                    "mapping": {"phase1": "nonexistent_state"},
                },
                "entry_points": {"default": "state1"}
            }
        }
        with open(tmp_path / "flows" / "invalid_flow" / "flow.yaml", 'w') as f:
            yaml.dump(invalid_flow, f)
        with open(tmp_path / "flows" / "invalid_flow" / "states.yaml", 'w') as f:
            yaml.dump({"states": {"state1": {"goal": "State 1"}}}, f)

        return tmp_path

    def test_valid_flow_passes(self, validation_flow_dir):
        """Test that valid flow passes validation."""
        from src.config_loader import ConfigLoader

        loader = ConfigLoader(validation_flow_dir)
        flow = loader.load_flow("valid_flow")

        assert flow is not None
        assert flow.name == "valid_flow"

    def test_invalid_phase_mapping_fails(self, validation_flow_dir):
        """Test that invalid phase mapping fails validation."""
        from src.config_loader import ConfigLoader, ConfigValidationError

        loader = ConfigLoader(validation_flow_dir)

        with pytest.raises(ConfigValidationError) as exc_info:
            loader.load_flow("invalid_flow")

        assert "nonexistent_state" in str(exc_info.value)

    def test_skip_validation(self, validation_flow_dir):
        """Test that validation can be skipped."""
        from src.config_loader import ConfigLoader

        loader = ConfigLoader(validation_flow_dir)
        flow = loader.load_flow("invalid_flow", validate=False)

        assert flow is not None
