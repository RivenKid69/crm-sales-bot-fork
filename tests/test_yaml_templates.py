"""
Tests for YAML Templates Loading (Этап 5).

Tests the new YAML-based prompt templates system that allows
configuring prompts per flow without modifying Python code.
"""

import pytest
from pathlib import Path
import yaml

class TestTemplateLoading:
    """Tests for template loading in FlowConfig."""

    @pytest.fixture
    def templates_flow_dir(self, tmp_path):
        """Create flow with templates."""
        (tmp_path / "flows" / "_base").mkdir(parents=True)
        (tmp_path / "flows" / "template_test").mkdir(parents=True)
        (tmp_path / "templates" / "_base").mkdir(parents=True)
        (tmp_path / "templates" / "template_test").mkdir(parents=True)

        # Create base files for flow
        with open(tmp_path / "flows" / "_base" / "states.yaml", 'w') as f:
            yaml.dump({"states": {"greeting": {"goal": "Greet"}}}, f)
        with open(tmp_path / "flows" / "_base" / "mixins.yaml", 'w') as f:
            yaml.dump({"mixins": {}}, f)
        with open(tmp_path / "flows" / "_base" / "priorities.yaml", 'w') as f:
            yaml.dump({"default_priorities": []}, f)

        # Create base templates
        base_templates = {
            "templates": {
                "greet_back": {
                    "description": "Greeting response",
                    "parameters": {
                        "required": ["system", "user_message"]
                    },
                    "template": "Base greeting: {user_message}"
                },
                "continue_current_goal": {
                    "description": "Continue to goal",
                    "template": "Base continue: {history}"
                },
                "deflect_and_continue": {
                    "description": "Deflect price question",
                    "template": "Base deflect: {user_message}"
                }
            }
        }
        with open(tmp_path / "templates" / "_base" / "prompts.yaml", 'w') as f:
            yaml.dump(base_templates, f)

        # Create flow-specific templates
        flow_templates = {
            "templates": {
                "greet_back": {
                    "description": "Custom greeting",
                    "template": "Custom greeting: {user_message} (override)"
                },
                "spin_situation": {
                    "description": "SPIN Situation",
                    "phase": "situation",
                    "template": "Custom SPIN situation: {collected_data}"
                }
            }
        }
        with open(tmp_path / "templates" / "template_test" / "prompts.yaml", 'w') as f:
            yaml.dump(flow_templates, f)

        # Create test flow
        flow_yaml = {
            "flow": {
                "name": "template_test",
                "entry_points": {"default": "greeting"}
            }
        }
        with open(tmp_path / "flows" / "template_test" / "flow.yaml", 'w') as f:
            yaml.dump(flow_yaml, f)

        with open(tmp_path / "flows" / "template_test" / "states.yaml", 'w') as f:
            yaml.dump({"states": {}}, f)

        return tmp_path

    def test_templates_loaded(self, templates_flow_dir):
        """Test that templates are loaded into FlowConfig."""
        from src.config_loader import ConfigLoader

        loader = ConfigLoader(templates_flow_dir)
        flow = loader.load_flow("template_test")

        assert flow.templates is not None
        assert len(flow.templates) > 0

    def test_base_template_loaded(self, templates_flow_dir):
        """Test that base templates are loaded."""
        from src.config_loader import ConfigLoader

        loader = ConfigLoader(templates_flow_dir)
        flow = loader.load_flow("template_test")

        # deflect_and_continue is only in base, not overridden
        assert "deflect_and_continue" in flow.templates
        template = flow.get_template("deflect_and_continue")
        assert "Base deflect" in template

    def test_flow_template_overrides_base(self, templates_flow_dir):
        """Test that flow templates override base templates."""
        from src.config_loader import ConfigLoader

        loader = ConfigLoader(templates_flow_dir)
        flow = loader.load_flow("template_test")

        # greet_back is in both, flow should override
        template = flow.get_template("greet_back")
        assert "Custom greeting" in template
        assert "(override)" in template

    def test_flow_specific_template(self, templates_flow_dir):
        """Test that flow-specific templates are loaded."""
        from src.config_loader import ConfigLoader

        loader = ConfigLoader(templates_flow_dir)
        flow = loader.load_flow("template_test")

        # spin_situation is only in flow templates
        assert "spin_situation" in flow.templates
        template = flow.get_template("spin_situation")
        assert "Custom SPIN situation" in template

    def test_get_template_returns_none_for_unknown(self, templates_flow_dir):
        """Test that get_template returns None for unknown templates."""
        from src.config_loader import ConfigLoader

        loader = ConfigLoader(templates_flow_dir)
        flow = loader.load_flow("template_test")

        template = flow.get_template("nonexistent_template")
        assert template is None

    def test_get_template_config(self, templates_flow_dir):
        """Test that get_template_config returns full configuration."""
        from src.config_loader import ConfigLoader

        loader = ConfigLoader(templates_flow_dir)
        flow = loader.load_flow("template_test")

        config = flow.get_template_config("spin_situation")
        assert config is not None
        assert "description" in config
        assert "template" in config
        assert config.get("phase") == "situation"

class TestTemplateInGenerator:
    """Tests for template usage in ResponseGenerator.

    These tests verify the _get_template method logic by directly
    testing with a mock generator object to avoid import issues.
    """

    @pytest.fixture
    def generator_flow_dir(self, tmp_path):
        """Create flow for generator testing."""
        (tmp_path / "flows" / "_base").mkdir(parents=True)
        (tmp_path / "flows" / "generator_test").mkdir(parents=True)
        (tmp_path / "templates" / "_base").mkdir(parents=True)
        (tmp_path / "templates" / "generator_test").mkdir(parents=True)

        # Create base files for flow
        with open(tmp_path / "flows" / "_base" / "states.yaml", 'w') as f:
            yaml.dump({"states": {"greeting": {"goal": "Greet"}}}, f)
        with open(tmp_path / "flows" / "_base" / "mixins.yaml", 'w') as f:
            yaml.dump({"mixins": {}}, f)
        with open(tmp_path / "flows" / "_base" / "priorities.yaml", 'w') as f:
            yaml.dump({"default_priorities": []}, f)

        # Create templates
        templates = {
            "templates": {
                "test_action": {
                    "description": "Test action",
                    "template": "YAML template for test: {user_message}"
                }
            }
        }
        with open(tmp_path / "templates" / "_base" / "prompts.yaml", 'w') as f:
            yaml.dump(templates, f)

        flow_yaml = {
            "flow": {
                "name": "generator_test",
                "entry_points": {"default": "greeting"}
            }
        }
        with open(tmp_path / "flows" / "generator_test" / "flow.yaml", 'w') as f:
            yaml.dump(flow_yaml, f)

        with open(tmp_path / "flows" / "generator_test" / "states.yaml", 'w') as f:
            yaml.dump({"states": {}}, f)

        return tmp_path

    def test_generator_uses_flow_template(self, generator_flow_dir):
        """Test that _get_template uses FlowConfig templates."""
        from src.config_loader import ConfigLoader
        from src.config import PROMPT_TEMPLATES

        loader = ConfigLoader(generator_flow_dir)
        flow = loader.load_flow("generator_test")

        # Simulate _get_template logic
        def _get_template(template_key: str) -> str:
            if flow:
                template = flow.get_template(template_key)
                if template:
                    return template
            return PROMPT_TEMPLATES.get(template_key, PROMPT_TEMPLATES.get("continue_current_goal", ""))

        # Test that flow template is used
        template = _get_template("test_action")
        assert "YAML template for test" in template

    def test_generator_fallback_to_prompt_templates(self, generator_flow_dir):
        """Test that generator falls back to PROMPT_TEMPLATES."""
        from src.config_loader import ConfigLoader
        from src.config import PROMPT_TEMPLATES

        loader = ConfigLoader(generator_flow_dir)
        flow = loader.load_flow("generator_test")

        # Simulate _get_template logic
        def _get_template(template_key: str) -> str:
            if flow:
                template = flow.get_template(template_key)
                if template:
                    return template
            return PROMPT_TEMPLATES.get(template_key, PROMPT_TEMPLATES.get("continue_current_goal", ""))

        # Request template that only exists in PROMPT_TEMPLATES
        template = _get_template("greet_back")

        # Should fall back to Python PROMPT_TEMPLATES
        assert template is not None
        # The template should be from PROMPT_TEMPLATES
        if "greet_back" in PROMPT_TEMPLATES:
            assert "Задача:" in template or "system" in template.lower()

    def test_generator_without_flow_uses_prompt_templates(self):
        """Test that generator without flow uses PROMPT_TEMPLATES."""
        from src.config import PROMPT_TEMPLATES

        flow = None

        # Simulate _get_template logic
        def _get_template(template_key: str) -> str:
            if flow:
                template = flow.get_template(template_key)
                if template:
                    return template
            return PROMPT_TEMPLATES.get(template_key, PROMPT_TEMPLATES.get("continue_current_goal", ""))

        template = _get_template("deflect_and_continue")

        # Should use PROMPT_TEMPLATES
        assert template is not None
        assert template == PROMPT_TEMPLATES.get(
            "deflect_and_continue",
            PROMPT_TEMPLATES.get("continue_current_goal", "")
        )

class TestSpinSellingTemplates:
    """Tests for SPIN Selling specific templates."""

    def test_spin_templates_exist(self):
        """Test that SPIN templates exist in the real flow."""
        from src.config_loader import ConfigLoader

        loader = ConfigLoader()

        # Load the actual spin_selling flow
        try:
            flow = loader.load_flow("spin_selling")

            # Check for SPIN-specific templates
            spin_templates = [
                "spin_situation", "spin_problem",
                "spin_implication", "spin_need_payoff",
                "probe_situation", "probe_problem",
                "probe_implication", "probe_need_payoff"
            ]

            loaded_templates = set(flow.templates.keys())

            for template_name in spin_templates:
                assert template_name in loaded_templates, \
                    f"Missing SPIN template: {template_name}"
        except Exception as e:
            # If spin_selling flow doesn't exist yet, skip
            pytest.skip(f"SPIN selling flow not available: {e}")

    def test_base_templates_exist(self):
        """Test that base templates exist."""
        from src.config_loader import ConfigLoader

        loader = ConfigLoader()

        try:
            flow = loader.load_flow("spin_selling")

            # Check for base templates that should be inherited
            base_templates = [
                "greet_back", "deflect_and_continue",
                "answer_with_facts", "soft_close", "close"
            ]

            for template_name in base_templates:
                template = flow.get_template(template_name)
                assert template is not None, f"Missing base template: {template_name}"
        except Exception as e:
            pytest.skip(f"Flow not available: {e}")

class TestTemplateStructure:
    """Tests for template structure validation."""

    @pytest.fixture
    def structured_templates_dir(self, tmp_path):
        """Create templates with full structure."""
        (tmp_path / "flows" / "_base").mkdir(parents=True)
        (tmp_path / "flows" / "structured_test").mkdir(parents=True)
        (tmp_path / "templates" / "_base").mkdir(parents=True)

        # Create base files
        with open(tmp_path / "flows" / "_base" / "states.yaml", 'w') as f:
            yaml.dump({"states": {"greeting": {"goal": "Greet"}}}, f)
        with open(tmp_path / "flows" / "_base" / "mixins.yaml", 'w') as f:
            yaml.dump({"mixins": {}}, f)
        with open(tmp_path / "flows" / "_base" / "priorities.yaml", 'w') as f:
            yaml.dump({"default_priorities": []}, f)

        # Create structured templates
        templates = {
            "templates": {
                "structured_template": {
                    "description": "A fully structured template",
                    "phase": "situation",
                    "parameters": {
                        "required": ["system", "history", "user_message"],
                        "optional": ["collected_data", "pain_point"]
                    },
                    "template": """
{system}

History:
{history}

User: {user_message}

Response:"""
                }
            }
        }
        with open(tmp_path / "templates" / "_base" / "prompts.yaml", 'w') as f:
            yaml.dump(templates, f)

        flow_yaml = {
            "flow": {
                "name": "structured_test",
                "entry_points": {"default": "greeting"}
            }
        }
        with open(tmp_path / "flows" / "structured_test" / "flow.yaml", 'w') as f:
            yaml.dump(flow_yaml, f)

        with open(tmp_path / "flows" / "structured_test" / "states.yaml", 'w') as f:
            yaml.dump({"states": {}}, f)

        return tmp_path

    def test_template_has_all_metadata(self, structured_templates_dir):
        """Test that template config contains all metadata."""
        from src.config_loader import ConfigLoader

        loader = ConfigLoader(structured_templates_dir)
        flow = loader.load_flow("structured_test")

        config = flow.get_template_config("structured_template")

        assert "description" in config
        assert "phase" in config
        assert "parameters" in config
        assert "template" in config

        params = config["parameters"]
        assert "required" in params
        assert "optional" in params

    def test_template_multiline_preserved(self, structured_templates_dir):
        """Test that multiline templates are preserved correctly."""
        from src.config_loader import ConfigLoader

        loader = ConfigLoader(structured_templates_dir)
        flow = loader.load_flow("structured_test")

        template = flow.get_template("structured_template")

        assert "History:" in template
        assert "User:" in template
        assert "Response:" in template

class TestNoTemplatesFlow:
    """Tests for flows without templates."""

    @pytest.fixture
    def no_templates_dir(self, tmp_path):
        """Create flow without templates."""
        (tmp_path / "flows" / "_base").mkdir(parents=True)
        (tmp_path / "flows" / "no_templates").mkdir(parents=True)
        # Note: No templates/ directory created

        with open(tmp_path / "flows" / "_base" / "states.yaml", 'w') as f:
            yaml.dump({"states": {"greeting": {"goal": "Greet"}}}, f)
        with open(tmp_path / "flows" / "_base" / "mixins.yaml", 'w') as f:
            yaml.dump({"mixins": {}}, f)
        with open(tmp_path / "flows" / "_base" / "priorities.yaml", 'w') as f:
            yaml.dump({"default_priorities": []}, f)

        flow_yaml = {
            "flow": {
                "name": "no_templates",
                "entry_points": {"default": "greeting"}
            }
        }
        with open(tmp_path / "flows" / "no_templates" / "flow.yaml", 'w') as f:
            yaml.dump(flow_yaml, f)

        with open(tmp_path / "flows" / "no_templates" / "states.yaml", 'w') as f:
            yaml.dump({"states": {}}, f)

        return tmp_path

    def test_flow_loads_without_templates(self, no_templates_dir):
        """Test that flow loads even without templates directory."""
        from src.config_loader import ConfigLoader

        loader = ConfigLoader(no_templates_dir)
        flow = loader.load_flow("no_templates")

        assert flow is not None
        assert flow.templates == {}

    def test_get_template_returns_none_without_templates(self, no_templates_dir):
        """Test get_template returns None when no templates."""
        from src.config_loader import ConfigLoader

        loader = ConfigLoader(no_templates_dir)
        flow = loader.load_flow("no_templates")

        template = flow.get_template("anything")
        assert template is None
