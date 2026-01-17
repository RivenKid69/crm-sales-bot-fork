"""
Tests for template variable interpolation.

This module tests:
1. Basic {{variable}} substitution
2. Nested variable references
3. Circular reference detection
4. Missing variable handling
5. Type preservation during interpolation
"""

import pytest
from pathlib import Path
import yaml
import sys
import re

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


# =============================================================================
# TEMPLATE INTERPOLATION ENGINE
# =============================================================================

class TemplateInterpolator:
    """
    Interpolates {{variable}} placeholders in configuration.
    """

    PATTERN = re.compile(r'\{\{(\w+)\}\}')
    MAX_RECURSION = 10

    def __init__(self, variables: dict):
        self.variables = variables
        self._interpolation_stack = []

    def interpolate(self, value, depth=0):
        """
        Interpolate all {{variable}} placeholders in a value.

        Args:
            value: String, dict, list, or other value to interpolate
            depth: Current recursion depth

        Returns:
            Value with all placeholders replaced
        """
        if depth > self.MAX_RECURSION:
            raise RecursionError("Max interpolation depth exceeded - possible circular reference")

        if isinstance(value, str):
            return self._interpolate_string(value, depth)
        elif isinstance(value, dict):
            return {k: self.interpolate(v, depth) for k, v in value.items()}
        elif isinstance(value, list):
            return [self.interpolate(item, depth) for item in value]
        else:
            return value

    def _interpolate_string(self, s: str, depth: int):
        """Interpolate a single string."""
        matches = self.PATTERN.findall(s)

        if not matches:
            return s

        result = s
        for var_name in matches:
            if var_name in self._interpolation_stack:
                raise ValueError(f"Circular reference detected: {' -> '.join(self._interpolation_stack)} -> {var_name}")

            if var_name not in self.variables:
                # Leave placeholder if variable not found
                continue

            self._interpolation_stack.append(var_name)
            try:
                var_value = self.variables[var_name]

                # Recursively interpolate the variable value
                var_value = self.interpolate(var_value, depth + 1)

                placeholder = "{{" + var_name + "}}"

                # If entire string is the placeholder, return value directly (preserves type)
                if result == placeholder:
                    result = var_value
                else:
                    # Replace within string
                    result = result.replace(placeholder, str(var_value))
            finally:
                self._interpolation_stack.pop()

        return result

    def validate_references(self) -> list:
        """
        Validate all variable references.

        Returns:
            List of validation errors
        """
        errors = []

        def check_value(value, path=""):
            if isinstance(value, str):
                for var_name in self.PATTERN.findall(value):
                    if var_name not in self.variables:
                        errors.append(f"Unknown variable '{var_name}' at {path}")
            elif isinstance(value, dict):
                for k, v in value.items():
                    check_value(v, f"{path}.{k}" if path else k)
            elif isinstance(value, list):
                for i, item in enumerate(value):
                    check_value(item, f"{path}[{i}]")

        # Check all variable values for references
        for name, value in self.variables.items():
            check_value(value, name)

        return errors

    def find_circular_references(self) -> list:
        """
        Find all circular references in variables.

        Returns:
            List of circular reference chains
        """
        circular = []

        def build_dependency_graph():
            """Build graph of variable dependencies."""
            deps = {}
            for name, value in self.variables.items():
                deps[name] = set()
                if isinstance(value, str):
                    deps[name].update(self.PATTERN.findall(value))
            return deps

        def find_cycles(graph):
            """Find cycles using DFS."""
            cycles = []
            visited = set()
            rec_stack = set()

            def dfs(node, path):
                if node in rec_stack:
                    cycle_start = path.index(node)
                    cycles.append(path[cycle_start:] + [node])
                    return

                if node in visited or node not in graph:
                    return

                visited.add(node)
                rec_stack.add(node)
                path.append(node)

                for dep in graph.get(node, []):
                    dfs(dep, path.copy())

                rec_stack.remove(node)

            for node in graph:
                dfs(node, [])

            return cycles

        deps = build_dependency_graph()
        return find_cycles(deps)


# =============================================================================
# BASIC INTERPOLATION TESTS
# =============================================================================

class TestBasicInterpolation:
    """Tests for basic variable substitution."""

    def test_simple_string_interpolation(self):
        """Simple {{var}} replacement in string."""
        variables = {"company_name": "Acme Corp"}
        interpolator = TemplateInterpolator(variables)

        result = interpolator.interpolate("Welcome to {{company_name}}!")
        assert result == "Welcome to Acme Corp!"

    def test_multiple_variables_in_string(self):
        """Multiple variables in single string."""
        variables = {
            "company_name": "Acme Corp",
            "product_name": "SuperCRM"
        }
        interpolator = TemplateInterpolator(variables)

        result = interpolator.interpolate("{{company_name}} presents {{product_name}}")
        assert result == "Acme Corp presents SuperCRM"

    def test_variable_as_entire_value(self):
        """Variable as entire value preserves type."""
        variables = {"max_turns": 25, "enabled": True}
        interpolator = TemplateInterpolator(variables)

        # Integer
        result = interpolator.interpolate("{{max_turns}}")
        assert result == 25
        assert isinstance(result, int)

        # Boolean
        result = interpolator.interpolate("{{enabled}}")
        assert result is True
        assert isinstance(result, bool)

    def test_variable_in_dict(self):
        """Variable substitution in dict values."""
        variables = {"entry_state": "greeting"}
        interpolator = TemplateInterpolator(variables)

        config = {
            "entry_points": {
                "default": "{{entry_state}}"
            }
        }

        result = interpolator.interpolate(config)
        assert result["entry_points"]["default"] == "greeting"

    def test_variable_in_list(self):
        """Variable substitution in list items."""
        variables = {"state1": "greeting", "state2": "close"}
        interpolator = TemplateInterpolator(variables)

        config = ["{{state1}}", "spin_situation", "{{state2}}"]

        result = interpolator.interpolate(config)
        assert result == ["greeting", "spin_situation", "close"]

    def test_no_interpolation_needed(self):
        """String without placeholders passes through unchanged."""
        variables = {"company_name": "Acme Corp"}
        interpolator = TemplateInterpolator(variables)

        result = interpolator.interpolate("No variables here")
        assert result == "No variables here"


class TestNestedVariables:
    """Tests for nested variable references."""

    def test_variable_references_another_variable(self):
        """Variable value references another variable."""
        variables = {
            "base_url": "http://example.com",
            "api_url": "{{base_url}}/api"
        }
        interpolator = TemplateInterpolator(variables)

        result = interpolator.interpolate("{{api_url}}")
        assert result == "http://example.com/api"

    def test_two_level_nesting(self):
        """Two levels of variable nesting."""
        variables = {
            "host": "localhost",
            "port": "8080",
            "base_url": "http://{{host}}:{{port}}",
            "api_url": "{{base_url}}/api"
        }
        interpolator = TemplateInterpolator(variables)

        result = interpolator.interpolate("{{api_url}}")
        assert result == "http://localhost:8080/api"

    def test_three_level_nesting(self):
        """Three levels of variable nesting."""
        variables = {
            "level1": "A",
            "level2": "{{level1}}B",
            "level3": "{{level2}}C",
            "final": "{{level3}}D"
        }
        interpolator = TemplateInterpolator(variables)

        result = interpolator.interpolate("{{final}}")
        assert result == "ABCD"

    def test_multiple_nested_in_same_string(self):
        """Multiple nested variables in same string."""
        variables = {
            "first": "Hello",
            "second": "World",
            "greeting": "{{first}} {{second}}!",
            "full_message": "Message: {{greeting}}"
        }
        interpolator = TemplateInterpolator(variables)

        result = interpolator.interpolate("{{full_message}}")
        assert result == "Message: Hello World!"


class TestCircularReferences:
    """Tests for circular reference detection."""

    def test_detect_self_reference(self):
        """Detect self-referencing variable."""
        variables = {"self_ref": "{{self_ref}}"}
        interpolator = TemplateInterpolator(variables)

        with pytest.raises(ValueError) as exc_info:
            interpolator.interpolate("{{self_ref}}")

        assert "circular" in str(exc_info.value).lower()

    def test_detect_two_variable_cycle(self):
        """Detect A -> B -> A cycle."""
        variables = {
            "var_a": "{{var_b}}",
            "var_b": "{{var_a}}"
        }
        interpolator = TemplateInterpolator(variables)

        with pytest.raises(ValueError) as exc_info:
            interpolator.interpolate("{{var_a}}")

        assert "circular" in str(exc_info.value).lower()

    def test_detect_three_variable_cycle(self):
        """Detect A -> B -> C -> A cycle."""
        variables = {
            "var_a": "{{var_b}}",
            "var_b": "{{var_c}}",
            "var_c": "{{var_a}}"
        }
        interpolator = TemplateInterpolator(variables)

        with pytest.raises(ValueError) as exc_info:
            interpolator.interpolate("{{var_a}}")

        assert "circular" in str(exc_info.value).lower()

    def test_find_circular_references(self):
        """Find all circular references in variables."""
        variables = {
            "a": "{{b}}",
            "b": "{{c}}",
            "c": "{{a}}",
            "d": "standalone"
        }
        interpolator = TemplateInterpolator(variables)

        cycles = interpolator.find_circular_references()
        assert len(cycles) > 0

        # The cycle should contain a, b, c
        cycle_vars = set()
        for cycle in cycles:
            cycle_vars.update(cycle)
        assert "a" in cycle_vars
        assert "b" in cycle_vars
        assert "c" in cycle_vars

    def test_no_circular_references(self):
        """No false positives for valid config."""
        variables = {
            "host": "localhost",
            "port": "8080",
            "base_url": "http://{{host}}:{{port}}",
            "api_url": "{{base_url}}/api"
        }
        interpolator = TemplateInterpolator(variables)

        cycles = interpolator.find_circular_references()
        assert len(cycles) == 0


class TestMissingVariables:
    """Tests for handling missing variable references."""

    def test_missing_variable_preserved(self):
        """Missing variable placeholder is preserved."""
        variables = {"exists": "value"}
        interpolator = TemplateInterpolator(variables)

        result = interpolator.interpolate("{{exists}} and {{missing}}")
        assert result == "value and {{missing}}"

    def test_validate_references_finds_missing(self):
        """validate_references finds missing variable references."""
        variables = {
            "template": "Hello {{name}}, welcome to {{company}}"
        }
        interpolator = TemplateInterpolator(variables)

        errors = interpolator.validate_references()
        assert len(errors) == 2
        assert any("name" in e for e in errors)
        assert any("company" in e for e in errors)

    def test_validate_references_all_present(self):
        """validate_references returns empty list when all present."""
        variables = {
            "name": "John",
            "company": "Acme",
            "template": "Hello {{name}}, welcome to {{company}}"
        }
        interpolator = TemplateInterpolator(variables)

        errors = interpolator.validate_references()
        assert len(errors) == 0


class TestTypePreservation:
    """Tests for type preservation during interpolation."""

    def test_integer_preserved(self):
        """Integer values are preserved."""
        variables = {"count": 42}
        interpolator = TemplateInterpolator(variables)

        result = interpolator.interpolate("{{count}}")
        assert result == 42
        assert isinstance(result, int)

    def test_float_preserved(self):
        """Float values are preserved."""
        variables = {"threshold": 0.75}
        interpolator = TemplateInterpolator(variables)

        result = interpolator.interpolate("{{threshold}}")
        assert result == 0.75
        assert isinstance(result, float)

    def test_boolean_preserved(self):
        """Boolean values are preserved."""
        variables = {"enabled": True, "disabled": False}
        interpolator = TemplateInterpolator(variables)

        assert interpolator.interpolate("{{enabled}}") is True
        assert interpolator.interpolate("{{disabled}}") is False

    def test_list_preserved(self):
        """List values are preserved."""
        variables = {"phases": ["situation", "problem", "implication"]}
        interpolator = TemplateInterpolator(variables)

        result = interpolator.interpolate("{{phases}}")
        assert result == ["situation", "problem", "implication"]
        assert isinstance(result, list)

    def test_dict_preserved(self):
        """Dict values are preserved."""
        variables = {"config": {"key": "value", "count": 5}}
        interpolator = TemplateInterpolator(variables)

        result = interpolator.interpolate("{{config}}")
        assert result == {"key": "value", "count": 5}
        assert isinstance(result, dict)

    def test_mixed_in_string_becomes_string(self):
        """When variable is part of string, everything becomes string."""
        variables = {"count": 42}
        interpolator = TemplateInterpolator(variables)

        result = interpolator.interpolate("Count is {{count}}")
        assert result == "Count is 42"
        assert isinstance(result, str)


class TestFlowConfigInterpolation:
    """Tests for interpolation in actual flow configuration."""

    def test_interpolate_flow_variables(self, config_factory):
        """Test interpolation in flow config context."""
        config_dir = config_factory()

        flow_config = {
            "flow": {
                "name": "spin_selling",
                "variables": {
                    "company_name": "Acme Corp",
                    "product_name": "SuperCRM",
                    "entry_state": "greeting"
                },
                "entry_points": {
                    "default": "{{entry_state}}",
                    "hot_lead": "presentation"
                },
                "templates": {
                    "greeting": "Welcome to {{company_name}}! Let me tell you about {{product_name}}."
                }
            }
        }

        variables = flow_config['flow']['variables']
        interpolator = TemplateInterpolator(variables)

        # Interpolate entry points
        entry_points = interpolator.interpolate(flow_config['flow']['entry_points'])
        assert entry_points['default'] == 'greeting'

        # Interpolate templates
        templates = interpolator.interpolate(flow_config['flow']['templates'])
        assert "Acme Corp" in templates['greeting']
        assert "SuperCRM" in templates['greeting']

    def test_interpolate_state_parameters(self, config_factory):
        """Test interpolation of state parameters."""
        state_config = {
            "spin_situation": {
                "goal": "Learn about {{company_name}}",
                "parameters": {
                    "company": "{{company_name}}",
                    "max_questions": "{{situation_questions}}"
                },
                "transitions": {
                    "data_complete": "{{next_phase_state}}"
                }
            }
        }

        variables = {
            "company_name": "Acme Corp",
            "situation_questions": 3,
            "next_phase_state": "spin_problem"
        }
        interpolator = TemplateInterpolator(variables)

        result = interpolator.interpolate(state_config)

        assert result['spin_situation']['goal'] == "Learn about Acme Corp"
        assert result['spin_situation']['parameters']['company'] == "Acme Corp"
        assert result['spin_situation']['parameters']['max_questions'] == 3
        assert result['spin_situation']['transitions']['data_complete'] == "spin_problem"


class TestEdgeCases:
    """Tests for edge cases in interpolation."""

    def test_empty_string(self):
        """Empty string passes through."""
        interpolator = TemplateInterpolator({})
        assert interpolator.interpolate("") == ""

    def test_none_value(self):
        """None value passes through."""
        interpolator = TemplateInterpolator({})
        assert interpolator.interpolate(None) is None

    def test_empty_dict(self):
        """Empty dict passes through."""
        interpolator = TemplateInterpolator({})
        assert interpolator.interpolate({}) == {}

    def test_empty_list(self):
        """Empty list passes through."""
        interpolator = TemplateInterpolator({})
        assert interpolator.interpolate([]) == []

    def test_partial_match_not_variable(self):
        """Partial matches like {var} or {{var are not substituted."""
        variables = {"var": "value"}
        interpolator = TemplateInterpolator(variables)

        assert interpolator.interpolate("{var}") == "{var}"
        assert interpolator.interpolate("{{var") == "{{var"
        assert interpolator.interpolate("var}}") == "var}}"

    def test_escaped_braces(self):
        """Test behavior with various brace patterns."""
        variables = {"var": "value"}
        interpolator = TemplateInterpolator(variables)

        # These should NOT match
        assert interpolator.interpolate("{ {var} }") == "{ {var} }"
        assert interpolator.interpolate("{{}}") == "{{}}"  # Empty placeholder

    def test_variable_with_underscore(self):
        """Variable names with underscores work."""
        variables = {"my_var_name": "value"}
        interpolator = TemplateInterpolator(variables)

        result = interpolator.interpolate("{{my_var_name}}")
        assert result == "value"

    def test_deeply_nested_dict_interpolation(self):
        """Deeply nested dict structures are fully interpolated."""
        variables = {"val": "X"}
        interpolator = TemplateInterpolator(variables)

        config = {
            "level1": {
                "level2": {
                    "level3": {
                        "level4": {
                            "value": "{{val}}"
                        }
                    }
                }
            }
        }

        result = interpolator.interpolate(config)
        assert result['level1']['level2']['level3']['level4']['value'] == "X"

    def test_max_recursion_limit(self):
        """Max recursion depth is enforced."""
        # Create very deep nesting
        variables = {}
        for i in range(15):
            if i == 0:
                variables[f"var_{i}"] = "base"
            else:
                variables[f"var_{i}"] = f"{{{{var_{i-1}}}}}"

        interpolator = TemplateInterpolator(variables)

        # Should raise on very deep nesting
        with pytest.raises(RecursionError):
            interpolator.interpolate("{{var_14}}")
