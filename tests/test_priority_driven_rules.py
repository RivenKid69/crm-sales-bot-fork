"""
Tests for Priority-Driven apply_rules() (Этап 4).

Tests the new priority-driven rule application system that uses
configurable priorities from FlowConfig instead of hardcoded logic.
"""

import pytest
from pathlib import Path
import yaml

class TestPriorityDrivenRules:
    """Tests for priority-driven rule application."""

    @pytest.fixture
    def priority_flow_dir(self, tmp_path):
        """Create flow with comprehensive priority configuration."""
        (tmp_path / "flows" / "_base").mkdir(parents=True)
        (tmp_path / "flows" / "priority_test").mkdir(parents=True)

        # Create base files
        base_states = {
            "states": {
                "greeting": {
                    "goal": "Greet",
                    "transitions": {
                        "rejection": "soft_close",
                        "demo_request": "close",
                    },
                    "rules": {
                        "greeting": "greet_back",
                        "price_question": "deflect_and_continue",
                    }
                },
                "soft_close": {
                    "goal": "Soft close",
                    "is_final": False,
                    "transitions": {
                        "agreement": "greeting",
                    }
                },
                "close": {
                    "goal": "Close the deal",
                    "transitions": {
                        "contact_provided": "success",
                    }
                },
                "success": {
                    "goal": "Success",
                    "is_final": True,
                }
            }
        }
        with open(tmp_path / "flows" / "_base" / "states.yaml", 'w') as f:
            yaml.dump(base_states, f)

        with open(tmp_path / "flows" / "_base" / "mixins.yaml", 'w') as f:
            yaml.dump({"mixins": {}}, f)

        # Create comprehensive priorities
        base_priorities = {
            "default_priorities": [
                {
                    "name": "final_state",
                    "priority": 0,
                    "condition": "is_final",
                    "action": "final",
                    "description": "Terminal states return 'final'"
                },
                {
                    "name": "rejection",
                    "priority": 100,
                    "intents": ["rejection"],
                    "use_transitions": True,
                    "description": "Handle rejection immediately"
                },
                {
                    "name": "state_rules",
                    "priority": 200,
                    "source": "rules",
                    "use_resolver": True,
                    "description": "Apply state-specific rules"
                },
                {
                    "name": "transitions",
                    "priority": 500,
                    "use_transitions": True,
                    "description": "Use state transitions"
                },
                {
                    "name": "default",
                    "priority": 999,
                    "action": "continue_current_goal",
                    "description": "Default fallback"
                },
            ]
        }
        with open(tmp_path / "flows" / "_base" / "priorities.yaml", 'w') as f:
            yaml.dump(base_priorities, f)

        # Create test flow
        flow_yaml = {
            "flow": {
                "name": "priority_test",
                "entry_points": {"default": "greeting"}
            }
        }
        with open(tmp_path / "flows" / "priority_test" / "flow.yaml", 'w') as f:
            yaml.dump(flow_yaml, f)

        with open(tmp_path / "flows" / "priority_test" / "states.yaml", 'w') as f:
            yaml.dump({"states": {}}, f)

        return tmp_path

    def test_priority_driven_final_state(self, priority_flow_dir):
        """Test that final states return 'final' action via priority system."""
        from src.config_loader import ConfigLoader
        from src.state_machine import StateMachine

        loader = ConfigLoader(priority_flow_dir)
        flow = loader.load_flow("priority_test")
        sm = StateMachine(flow=flow)

        # Move to success (final) state
        sm.state = "success"
        action, next_state = sm.apply_rules("greeting")

        assert action == "final"
        assert next_state == "success"

    def test_priority_driven_rejection(self, priority_flow_dir):
        """Test that rejection intent triggers transition via priority."""
        from src.config_loader import ConfigLoader
        from src.state_machine import StateMachine

        loader = ConfigLoader(priority_flow_dir)
        flow = loader.load_flow("priority_test")
        sm = StateMachine(flow=flow)

        sm.state = "greeting"
        action, next_state = sm.apply_rules("rejection")

        assert action == "transition_to_soft_close"
        assert next_state == "soft_close"

    def test_priority_driven_state_rules(self, priority_flow_dir):
        """Test that state rules are applied via priority system."""
        from src.config_loader import ConfigLoader
        from src.state_machine import StateMachine

        loader = ConfigLoader(priority_flow_dir)
        flow = loader.load_flow("priority_test")
        sm = StateMachine(flow=flow)

        sm.state = "greeting"
        action, next_state = sm.apply_rules("greeting")

        assert action == "greet_back"
        assert next_state == "greeting"

    def test_priority_driven_transitions(self, priority_flow_dir):
        """Test that transitions work via priority system."""
        from src.config_loader import ConfigLoader
        from src.state_machine import StateMachine

        loader = ConfigLoader(priority_flow_dir)
        flow = loader.load_flow("priority_test")
        sm = StateMachine(flow=flow)

        sm.state = "greeting"
        action, next_state = sm.apply_rules("demo_request")

        assert action == "transition_to_close"
        assert next_state == "close"

    def test_priority_driven_default_fallback(self, priority_flow_dir):
        """Test that unknown intents fall back to default action."""
        from src.config_loader import ConfigLoader
        from src.state_machine import StateMachine

        loader = ConfigLoader(priority_flow_dir)
        flow = loader.load_flow("priority_test")
        sm = StateMachine(flow=flow)

        sm.state = "greeting"
        action, next_state = sm.apply_rules("unknown_intent_xyz")

        assert action == "continue_current_goal"
        assert next_state == "greeting"

class TestPriorityOrdering:
    """Tests for priority ordering behavior."""

    @pytest.fixture
    def ordering_flow_dir(self, tmp_path):
        """Create flow with specific priority ordering."""
        (tmp_path / "flows" / "_base").mkdir(parents=True)
        (tmp_path / "flows" / "ordering_test").mkdir(parents=True)

        base_states = {
            "states": {
                "test_state": {
                    "goal": "Test",
                    "transitions": {
                        "test_intent": "next_state",
                    },
                    "rules": {
                        "test_intent": "rule_action",
                    }
                },
                "next_state": {
                    "goal": "Next",
                }
            }
        }
        with open(tmp_path / "flows" / "_base" / "states.yaml", 'w') as f:
            yaml.dump(base_states, f)

        with open(tmp_path / "flows" / "_base" / "mixins.yaml", 'w') as f:
            yaml.dump({"mixins": {}}, f)

        # Rules have lower priority than transitions in this config
        priorities_rules_first = {
            "default_priorities": [
                {
                    "name": "state_rules",
                    "priority": 100,
                    "source": "rules",
                    "use_resolver": True,
                },
                {
                    "name": "transitions",
                    "priority": 200,
                    "use_transitions": True,
                },
                {
                    "name": "default",
                    "priority": 999,
                    "action": "continue_current_goal",
                },
            ]
        }
        with open(tmp_path / "flows" / "_base" / "priorities.yaml", 'w') as f:
            yaml.dump(priorities_rules_first, f)

        flow_yaml = {
            "flow": {
                "name": "ordering_test",
                "entry_points": {"default": "test_state"}
            }
        }
        with open(tmp_path / "flows" / "ordering_test" / "flow.yaml", 'w') as f:
            yaml.dump(flow_yaml, f)

        with open(tmp_path / "flows" / "ordering_test" / "states.yaml", 'w') as f:
            yaml.dump({"states": {}}, f)

        return tmp_path

    def test_rules_before_transitions(self, ordering_flow_dir):
        """Test that rules are applied before transitions when priority is lower."""
        from src.config_loader import ConfigLoader
        from src.state_machine import StateMachine

        loader = ConfigLoader(ordering_flow_dir)
        flow = loader.load_flow("ordering_test")
        sm = StateMachine(flow=flow)

        sm.state = "test_state"
        action, next_state = sm.apply_rules("test_intent")

        # Rules priority (100) < transitions (200), so rules should win
        assert action == "rule_action"
        assert next_state == "test_state"

class TestBackwardCompatibility:
    """Tests for backward compatibility with legacy (no FlowConfig) mode."""

    def test_legacy_mode_without_flow(self):
        """Test that StateMachine works without FlowConfig."""
        from src.state_machine import StateMachine

        sm = StateMachine()

        # Should work with legacy hardcoded logic
        action, next_state = sm.apply_rules("greeting")

        # Should get some response (specific result depends on legacy config)
        assert action is not None
        assert next_state is not None

    def test_legacy_mode_rejection(self):
        """Test rejection handling in legacy mode."""
        from src.state_machine import StateMachine

        sm = StateMachine()
        sm.state = "greeting"

        action, next_state = sm.apply_rules("rejection")

        # Should transition to soft_close in legacy mode
        assert "soft_close" in next_state or action == "transition_to_soft_close"

    def test_mixed_mode_priorities_property(self):
        """Test priorities property returns correct list."""
        from src.state_machine import StateMachine

        sm = StateMachine()

        # Without FlowConfig, should return default priorities
        priorities = sm.priorities
        assert isinstance(priorities, list)

class TestPhaseProgressHandler:
    """Tests for phase_progress_handler priority."""

    @pytest.fixture
    def phase_flow_dir(self, tmp_path):
        """Create flow with phase configuration."""
        (tmp_path / "flows" / "_base").mkdir(parents=True)
        (tmp_path / "flows" / "phase_test").mkdir(parents=True)

        base_states = {
            "states": {
                "phase_a": {
                    "goal": "Phase A",
                    "phase": "alpha",
                    "transitions": {
                        "data_complete": "phase_b",
                        "info_provided": "phase_b",
                    }
                },
                "phase_b": {
                    "goal": "Phase B",
                    "phase": "beta",
                    "transitions": {
                        "data_complete": "closing",
                    }
                },
                "closing": {
                    "goal": "Close",
                }
            }
        }
        with open(tmp_path / "flows" / "_base" / "states.yaml", 'w') as f:
            yaml.dump(base_states, f)

        with open(tmp_path / "flows" / "_base" / "mixins.yaml", 'w') as f:
            yaml.dump({"mixins": {}}, f)

        priorities = {
            "default_priorities": [
                {
                    "name": "phase_progress",
                    "priority": 400,
                    "handler": "phase_progress_handler",
                },
                {
                    "name": "transitions",
                    "priority": 500,
                    "use_transitions": True,
                },
                {
                    "name": "default",
                    "priority": 999,
                    "action": "continue_current_goal",
                },
            ]
        }
        with open(tmp_path / "flows" / "_base" / "priorities.yaml", 'w') as f:
            yaml.dump(priorities, f)

        flow_yaml = {
            "flow": {
                "name": "phase_test",
                "phases": {
                    "order": ["alpha", "beta"],
                    "mapping": {
                        "alpha": "phase_a",
                        "beta": "phase_b",
                    },
                    "post_phases_state": "closing",
                    "progress_intents": {
                        "info_provided": "alpha",
                    }
                },
                "entry_points": {"default": "phase_a"}
            }
        }
        with open(tmp_path / "flows" / "phase_test" / "flow.yaml", 'w') as f:
            yaml.dump(flow_yaml, f)

        with open(tmp_path / "flows" / "phase_test" / "states.yaml", 'w') as f:
            yaml.dump({"states": {}}, f)

        return tmp_path

    def test_phase_progress_transition(self, phase_flow_dir):
        """Test phase progress triggers transition."""
        from src.config_loader import ConfigLoader
        from src.state_machine import StateMachine

        loader = ConfigLoader(phase_flow_dir)
        flow = loader.load_flow("phase_test")
        sm = StateMachine(flow=flow)

        sm.state = "phase_a"
        action, next_state = sm.apply_rules("info_provided")

        # Should transition based on progress_intents
        assert next_state == "phase_b"

class TestObjectionLimitPriority:
    """Tests for objection limit handling via priorities."""

    @pytest.fixture
    def objection_flow_dir(self, tmp_path):
        """Create flow with objection limit priority."""
        (tmp_path / "flows" / "_base").mkdir(parents=True)
        (tmp_path / "flows" / "objection_test").mkdir(parents=True)

        base_states = {
            "states": {
                "selling": {
                    "goal": "Selling",
                    "transitions": {
                        "objection_price": "handle_objection",
                    }
                },
                "handle_objection": {
                    "goal": "Handle objection",
                    "transitions": {
                        "agreement": "selling",
                        "objection_price": "handle_objection",
                    }
                },
                "soft_close": {
                    "goal": "Soft close",
                }
            }
        }
        with open(tmp_path / "flows" / "_base" / "states.yaml", 'w') as f:
            yaml.dump(base_states, f)

        with open(tmp_path / "flows" / "_base" / "mixins.yaml", 'w') as f:
            yaml.dump({"mixins": {}}, f)

        priorities = {
            "default_priorities": [
                {
                    "name": "objection_limit",
                    "priority": 170,
                    "intent_category": "objection",
                    "condition": "objection_limit_reached",
                    "action": "transition_to_soft_close",
                    "else": "use_transitions",
                },
                {
                    "name": "transitions",
                    "priority": 500,
                    "use_transitions": True,
                },
                {
                    "name": "default",
                    "priority": 999,
                    "action": "continue_current_goal",
                },
            ]
        }
        with open(tmp_path / "flows" / "_base" / "priorities.yaml", 'w') as f:
            yaml.dump(priorities, f)

        flow_yaml = {
            "flow": {
                "name": "objection_test",
                "entry_points": {"default": "selling"}
            }
        }
        with open(tmp_path / "flows" / "objection_test" / "flow.yaml", 'w') as f:
            yaml.dump(flow_yaml, f)

        with open(tmp_path / "flows" / "objection_test" / "states.yaml", 'w') as f:
            yaml.dump({"states": {}}, f)

        return tmp_path

    def test_objection_before_limit(self, objection_flow_dir):
        """Test objection handling before limit reached."""
        from src.config_loader import ConfigLoader
        from src.state_machine import StateMachine

        loader = ConfigLoader(objection_flow_dir)
        flow = loader.load_flow("objection_test")
        sm = StateMachine(flow=flow)

        sm.state = "selling"
        action, next_state = sm.apply_rules("objection_price")

        # Should transition to handle_objection (not soft_close yet)
        assert next_state == "handle_objection"

class TestConditionalRulesViaPriority:
    """Tests for conditional rules via priority system."""

    @pytest.fixture
    def conditional_flow_dir(self, tmp_path):
        """Create flow with conditional rules."""
        (tmp_path / "flows" / "_base").mkdir(parents=True)
        (tmp_path / "flows" / "conditional_test").mkdir(parents=True)

        base_states = {
            "states": {
                "selling": {
                    "goal": "Selling",
                    "rules": {
                        "price_question": [
                            {"when": "can_answer_price", "then": "answer_with_facts"},
                            "deflect_and_continue"
                        ]
                    }
                }
            }
        }
        with open(tmp_path / "flows" / "_base" / "states.yaml", 'w') as f:
            yaml.dump(base_states, f)

        with open(tmp_path / "flows" / "_base" / "mixins.yaml", 'w') as f:
            yaml.dump({"mixins": {}}, f)

        priorities = {
            "default_priorities": [
                {
                    "name": "state_rules",
                    "priority": 200,
                    "source": "rules",
                    "use_resolver": True,
                },
                {
                    "name": "default",
                    "priority": 999,
                    "action": "continue_current_goal",
                },
            ]
        }
        with open(tmp_path / "flows" / "_base" / "priorities.yaml", 'w') as f:
            yaml.dump(priorities, f)

        flow_yaml = {
            "flow": {
                "name": "conditional_test",
                "entry_points": {"default": "selling"}
            }
        }
        with open(tmp_path / "flows" / "conditional_test" / "flow.yaml", 'w') as f:
            yaml.dump(flow_yaml, f)

        with open(tmp_path / "flows" / "conditional_test" / "states.yaml", 'w') as f:
            yaml.dump({"states": {}}, f)

        return tmp_path

    def test_conditional_rule_fallback(self, conditional_flow_dir):
        """Test conditional rule resolves to fallback when condition not met."""
        from src.config_loader import ConfigLoader
        from src.state_machine import StateMachine

        loader = ConfigLoader(conditional_flow_dir)
        flow = loader.load_flow("conditional_test")
        sm = StateMachine(flow=flow)

        sm.state = "selling"
        sm.collected_data = {}  # No pricing data

        action, next_state = sm.apply_rules("price_question")

        # Should use fallback (deflect_and_continue) since can_answer_price is False
        assert action == "deflect_and_continue"
        assert next_state == "selling"
