"""
Tests for template validation in ConfigLoader.

This module tests the validation of {{template}} placeholders to ensure:
1. All templates are resolved after parameter substitution
2. Unresolved templates are detected and reported
3. Proper error messages are generated for debugging
4. Edge cases are handled correctly

Related to: Issue #4 - Templates {{entry_state}} without explicit default in some flows
"""

import pytest
from pathlib import Path
import sys
import tempfile
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from config_loader import ConfigLoader, ConfigValidationError, FlowConfig


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def config_loader():
    """Create a ConfigLoader instance."""
    return ConfigLoader()


@pytest.fixture
def temp_flow_dir(tmp_path):
    """Create a temporary flow directory structure for testing."""
    flows_dir = tmp_path / "flows"
    flows_dir.mkdir()

    # Create _base directory with minimal states
    base_dir = flows_dir / "_base"
    base_dir.mkdir()

    # Base states with templates
    base_states = {
        "states": {
            "_base_greeting": {
                "abstract": True,
                "goal": "Greet the user",
                "rules": {
                    "greeting": "greet_back"
                }
            },
            "_base_phase": {
                "abstract": True,
                "parameters": {
                    "next_phase_state": "presentation",
                    "default_price_action": "deflect_and_continue"
                }
            },
            "greeting": {
                "extends": "_base_greeting",
                "transitions": {
                    "price_question": "{{entry_state}}",
                    "agreement": "{{entry_state}}",
                    "demo_request": "close"
                }
            },
            "close": {
                "goal": "Close the deal",
                "is_final": False,
                "transitions": {
                    "agreement": "success"
                }
            },
            "success": {
                "goal": "Success",
                "is_final": True
            },
            "soft_close": {
                "goal": "Soft close",
                "is_final": False,
                "transitions": {
                    "agreement": "{{entry_state}}"
                }
            }
        },
        "defaults": {
            "entry_state": "greeting"
        }
    }

    with open(base_dir / "states.yaml", "w") as f:
        yaml.dump(base_states, f)

    # Base mixins
    base_mixins = {
        "mixins": {
            "price_handling": {
                "rules": {
                    "price_question": [
                        {"when": "can_answer_price", "then": "answer_with_facts"},
                        "{{default_price_action}}"
                    ]
                }
            },
            "phase_progress": {
                "transitions": {
                    "situation_provided": "{{next_phase_state}}",
                    "problem_revealed": "{{next_phase_state}}"
                }
            }
        },
        "defaults": {
            "default_price_action": "deflect_and_continue"
        }
    }

    with open(base_dir / "mixins.yaml", "w") as f:
        yaml.dump(base_mixins, f)

    # Base priorities
    base_priorities = {
        "default_priorities": []
    }

    with open(base_dir / "priorities.yaml", "w") as f:
        yaml.dump(base_priorities, f)

    return tmp_path


def create_test_flow(flows_dir, flow_name, flow_config, states_config=None):
    """Helper to create a test flow."""
    flow_dir = flows_dir / "flows" / flow_name
    flow_dir.mkdir(parents=True, exist_ok=True)

    with open(flow_dir / "flow.yaml", "w") as f:
        yaml.dump(flow_config, f)

    if states_config:
        with open(flow_dir / "states.yaml", "w") as f:
            yaml.dump(states_config, f)


# =============================================================================
# UNIT TESTS: _find_unresolved_templates
# =============================================================================

class TestFindUnresolvedTemplates:
    """Tests for _find_unresolved_templates method."""

    def test_find_template_in_string(self, config_loader):
        """Find template in simple string."""
        config = "{{entry_state}}"
        result = config_loader._find_unresolved_templates(config, "test")

        assert len(result) == 1
        assert result[0]["template"] == "{{entry_state}}"
        assert result[0]["variable"] == "entry_state"
        assert result[0]["path"] == "test"

    def test_find_multiple_templates_in_string(self, config_loader):
        """Find multiple templates in same string."""
        config = "{{first}} to {{second}}"
        result = config_loader._find_unresolved_templates(config, "test")

        assert len(result) == 2
        templates = [r["template"] for r in result]
        assert "{{first}}" in templates
        assert "{{second}}" in templates

    def test_find_template_in_dict(self, config_loader):
        """Find template nested in dict."""
        config = {
            "transitions": {
                "price_question": "{{entry_state}}"
            }
        }
        result = config_loader._find_unresolved_templates(config, "greeting")

        assert len(result) == 1
        assert result[0]["template"] == "{{entry_state}}"
        assert result[0]["path"] == "greeting.transitions.price_question"

    def test_find_template_in_list(self, config_loader):
        """Find template in list."""
        config = ["state1", "{{next_state}}", "state3"]
        result = config_loader._find_unresolved_templates(config, "test")

        assert len(result) == 1
        assert result[0]["template"] == "{{next_state}}"
        assert result[0]["path"] == "test[1]"

    def test_find_template_in_nested_structure(self, config_loader):
        """Find templates in deeply nested structure."""
        config = {
            "level1": {
                "level2": {
                    "level3": [
                        {"value": "{{deep_template}}"}
                    ]
                }
            }
        }
        result = config_loader._find_unresolved_templates(config, "root")

        assert len(result) == 1
        assert result[0]["template"] == "{{deep_template}}"
        assert result[0]["path"] == "root.level1.level2.level3[0].value"

    def test_find_template_in_conditional_rule(self, config_loader):
        """Find template in conditional rule (common pattern)."""
        config = {
            "rules": {
                "price_question": [
                    {"when": "can_answer", "then": "answer"},
                    "{{default_price_action}}"
                ]
            }
        }
        result = config_loader._find_unresolved_templates(config, "state")

        assert len(result) == 1
        assert result[0]["template"] == "{{default_price_action}}"
        assert result[0]["path"] == "state.rules.price_question[1]"

    def test_no_templates_returns_empty_list(self, config_loader):
        """No templates returns empty list."""
        config = {
            "transitions": {
                "greeting": "close",
                "farewell": "success"
            }
        }
        result = config_loader._find_unresolved_templates(config, "state")

        assert len(result) == 0

    def test_handles_non_string_values(self, config_loader):
        """Non-string values (int, bool, None) are handled."""
        config = {
            "count": 42,
            "enabled": True,
            "nothing": None,
            "template": "{{var}}"
        }
        result = config_loader._find_unresolved_templates(config, "test")

        assert len(result) == 1
        assert result[0]["template"] == "{{var}}"

    def test_handles_partial_braces(self, config_loader):
        """Partial braces like {var} or {{var are not detected."""
        config = {
            "single": "{var}",
            "open": "{{var",
            "close": "var}}",
            "valid": "{{var}}"
        }
        result = config_loader._find_unresolved_templates(config, "test")

        # Only valid {{var}} should be detected
        assert len(result) == 1
        assert result[0]["variable"] == "var"


# =============================================================================
# UNIT TESTS: _validate_templates_resolved
# =============================================================================

class TestValidateTemplatesResolved:
    """Tests for _validate_templates_resolved method."""

    def test_valid_states_no_templates(self, config_loader):
        """Fully resolved states return no errors."""
        states = {
            "greeting": {
                "goal": "Greet",
                "transitions": {
                    "next": "close"
                }
            },
            "close": {
                "goal": "Close",
                "is_final": True
            }
        }
        errors = config_loader._validate_templates_resolved(states, "test_flow")

        assert len(errors) == 0

    def test_unresolved_entry_state(self, config_loader):
        """Detect unresolved {{entry_state}}."""
        states = {
            "greeting": {
                "transitions": {
                    "price_question": "{{entry_state}}"
                }
            }
        }
        errors = config_loader._validate_templates_resolved(states, "test_flow")

        assert len(errors) == 1
        assert "{{entry_state}}" in errors[0]
        assert "entry_state" in errors[0]
        assert "greeting.transitions.price_question" in errors[0]
        assert "test_flow" in errors[0]

    def test_unresolved_next_phase_state(self, config_loader):
        """Detect unresolved {{next_phase_state}}."""
        states = {
            "spin_situation": {
                "transitions": {
                    "situation_provided": "{{next_phase_state}}"
                }
            }
        }
        errors = config_loader._validate_templates_resolved(states, "spin_selling")

        assert len(errors) == 1
        assert "{{next_phase_state}}" in errors[0]

    def test_multiple_unresolved_templates(self, config_loader):
        """Detect multiple unresolved templates."""
        states = {
            "greeting": {
                "transitions": {
                    "next": "{{entry_state}}"
                }
            },
            "phase": {
                "transitions": {
                    "progress": "{{next_phase_state}}",
                    "back": "{{prev_phase_state}}"
                }
            }
        }
        errors = config_loader._validate_templates_resolved(states, "test_flow")

        assert len(errors) == 3
        templates = [e for e in errors]
        assert any("{{entry_state}}" in e for e in templates)
        assert any("{{next_phase_state}}" in e for e in templates)
        assert any("{{prev_phase_state}}" in e for e in templates)

    def test_skip_abstract_states(self, config_loader):
        """Abstract states are skipped (they are templates themselves)."""
        states = {
            "_base_phase": {
                "abstract": True,
                "transitions": {
                    "next": "{{next_phase_state}}"  # OK - abstract state
                }
            },
            "concrete_state": {
                "transitions": {
                    "next": "close"  # Resolved
                }
            }
        }
        errors = config_loader._validate_templates_resolved(states, "test_flow")

        assert len(errors) == 0

    def test_unresolved_in_rules(self, config_loader):
        """Detect unresolved templates in rules."""
        states = {
            "phase": {
                "rules": {
                    "price_question": [
                        {"when": "can_answer", "then": "answer"},
                        "{{default_price_action}}"
                    ]
                }
            }
        }
        errors = config_loader._validate_templates_resolved(states, "test_flow")

        assert len(errors) == 1
        assert "{{default_price_action}}" in errors[0]

    def test_error_message_format(self, config_loader):
        """Error message contains all required information."""
        states = {
            "greeting": {
                "transitions": {
                    "price_question": "{{entry_state}}"
                }
            }
        }
        errors = config_loader._validate_templates_resolved(states, "test_flow")

        error = errors[0]
        # Should contain template
        assert "{{entry_state}}" in error
        # Should contain path
        assert "greeting.transitions.price_question" in error
        # Should contain flow name
        assert "test_flow" in error
        # Should contain variable name for fix suggestion
        assert "'entry_state'" in error
        # Should suggest where to define it
        assert "flow.yaml" in error or "variables" in error


# =============================================================================
# INTEGRATION TESTS: load_flow with validation
# =============================================================================

class TestLoadFlowTemplateValidation:
    """Integration tests for template validation in load_flow."""

    def test_flow_with_all_templates_resolved(self, temp_flow_dir):
        """Flow with all templates resolved passes validation."""
        flow_config = {
            "flow": {
                "name": "valid_flow",
                "version": "1.0",
                "variables": {
                    "entry_state": "qualification",
                    "next_phase_state": "presentation",
                    "default_price_action": "answer_with_facts"
                },
                "entry_points": {
                    "default": "greeting"
                }
            }
        }

        states_config = {
            "states": {
                "qualification": {
                    "goal": "Qualify the lead",
                    "parameters": {
                        "next_phase_state": "presentation"
                    },
                    "transitions": {
                        "data_complete": "presentation"
                    }
                },
                "presentation": {
                    "goal": "Present solution",
                    "transitions": {
                        "agreement": "close"
                    }
                }
            }
        }

        create_test_flow(temp_flow_dir, "valid_flow", flow_config, states_config)

        loader = ConfigLoader(temp_flow_dir)
        # Should not raise
        flow = loader.load_flow("valid_flow", validate=True)

        assert flow.name == "valid_flow"

    def test_flow_missing_entry_state_fails(self, temp_flow_dir):
        """Flow without entry_state variable fails validation."""
        flow_config = {
            "flow": {
                "name": "missing_entry_state",
                "version": "1.0",
                "variables": {
                    # Missing entry_state!
                    "company_name": "Test"
                },
                "entry_points": {
                    "default": "greeting"
                }
            }
        }

        create_test_flow(temp_flow_dir, "missing_entry_state", flow_config)

        loader = ConfigLoader(temp_flow_dir)

        with pytest.raises(ConfigValidationError) as exc_info:
            loader.load_flow("missing_entry_state", validate=True)

        assert "{{entry_state}}" in str(exc_info.value)
        assert "entry_state" in str(exc_info.value)

    def test_flow_with_state_level_parameters(self, temp_flow_dir):
        """State-level parameters override flow variables."""
        flow_config = {
            "flow": {
                "name": "state_params_flow",
                "version": "1.0",
                "variables": {
                    "entry_state": "phase1",
                    "next_phase_state": "default_next"
                },
                "entry_points": {
                    "default": "greeting"
                }
            }
        }

        states_config = {
            "states": {
                "phase1": {
                    "goal": "Phase 1",
                    "parameters": {
                        "next_phase_state": "phase2"  # Override flow variable
                    },
                    "transitions": {
                        "done": "{{next_phase_state}}"  # Should resolve to phase2
                    }
                },
                "phase2": {
                    "goal": "Phase 2",
                    "transitions": {
                        "done": "close"
                    }
                }
            }
        }

        create_test_flow(temp_flow_dir, "state_params_flow", flow_config, states_config)

        loader = ConfigLoader(temp_flow_dir)
        flow = loader.load_flow("state_params_flow", validate=True)

        # Verify the template was resolved with state-level parameter
        phase1_transitions = flow.states["phase1"]["transitions"]
        assert phase1_transitions["done"] == "phase2"

    def test_validation_can_be_disabled(self, temp_flow_dir):
        """Validation can be disabled with validate=False."""
        flow_config = {
            "flow": {
                "name": "no_validate",
                "version": "1.0",
                "variables": {},  # Missing entry_state
                "entry_points": {
                    "default": "greeting"
                }
            }
        }

        create_test_flow(temp_flow_dir, "no_validate", flow_config)

        loader = ConfigLoader(temp_flow_dir)
        # Should not raise when validation disabled
        flow = loader.load_flow("no_validate", validate=False)

        assert flow.name == "no_validate"


# =============================================================================
# TESTS FOR EXISTING FLOWS (REGRESSION)
# =============================================================================

class TestExistingFlowsTemplateValidation:
    """Test that existing flows pass template validation."""

    @pytest.fixture
    def real_loader(self):
        """Get ConfigLoader pointing to real config directory."""
        config_dir = Path(__file__).parent.parent / "src" / "yaml_config"
        return ConfigLoader(config_dir)

    @pytest.mark.parametrize("flow_name", [
        "spin_selling",
        "bant",
        "challenger",
        "consultative",
        "value",
        "sandler",
        "solution",
        "gap",
        "aida",
        "snap",
        "transactional",
        "relationship",
        "inbound",
        "demo_first",
        "neat",
        "meddic",
        "command",
        "customer_centric",
        "fab",
        "social",
    ])
    def test_flow_has_no_unresolved_templates(self, real_loader, flow_name):
        """Each existing flow should have all templates resolved."""
        try:
            flow = real_loader.load_flow(flow_name, validate=True)
            # If we get here, validation passed

            # Additionally verify no templates remain in states
            for state_name, state_config in flow.states.items():
                if state_config.get("abstract", False):
                    continue
                unresolved = real_loader._find_unresolved_templates(state_config, state_name)
                assert len(unresolved) == 0, \
                    f"Flow '{flow_name}' state '{state_name}' has unresolved templates: {unresolved}"

        except FileNotFoundError:
            pytest.skip(f"Flow '{flow_name}' not found")


# =============================================================================
# EDGE CASES
# =============================================================================

class TestTemplateValidationEdgeCases:
    """Edge cases for template validation."""

    def test_empty_flow_states(self, config_loader):
        """Empty states dict returns no errors."""
        errors = config_loader._validate_templates_resolved({}, "test")
        assert len(errors) == 0

    def test_template_in_goal_field(self, config_loader):
        """Template in goal field is detected."""
        states = {
            "state": {
                "goal": "Learn about {{company_name}}"
            }
        }
        errors = config_loader._validate_templates_resolved(states, "test")

        assert len(errors) == 1
        assert "{{company_name}}" in errors[0]

    def test_template_with_underscores(self, config_loader):
        """Template with underscores is detected."""
        states = {
            "state": {
                "transitions": {
                    "next": "{{my_complex_variable_name}}"
                }
            }
        }
        errors = config_loader._validate_templates_resolved(states, "test")

        assert len(errors) == 1
        assert "{{my_complex_variable_name}}" in errors[0]

    def test_adjacent_templates(self, config_loader):
        """Adjacent templates are both detected."""
        states = {
            "state": {
                "value": "{{first}}{{second}}"
            }
        }
        errors = config_loader._validate_templates_resolved(states, "test")

        assert len(errors) == 2

    def test_get_required_template_variables(self, config_loader):
        """Required template variables are documented."""
        required = config_loader._get_required_template_variables()

        assert "entry_state" in required
        assert "next_phase_state" in required
        assert "prev_phase_state" in required
        assert "default_price_action" in required
        assert "default_unclear_action" in required

        # Each should have a description
        for var, desc in required.items():
            assert len(desc) > 0, f"Variable '{var}' has no description"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
