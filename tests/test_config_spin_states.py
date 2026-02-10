"""
Tests for SPIN selling states configuration.

Tests flows/spin_selling/states.yaml including state definitions and inheritance.
"""

import pytest
from pathlib import Path
import yaml

@pytest.fixture(scope="module")
def spin_states_config():
    """Load SPIN selling states configuration."""
    config_path = Path(__file__).parent.parent / "src" / "yaml_config" / "flows" / "spin_selling" / "states.yaml"
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

class TestSpinStatesStructure:
    """Tests for SPIN states structure."""

    def test_has_states_section(self, spin_states_config):
        """Config should have states section."""
        assert "states" in spin_states_config

    def test_states_not_empty(self, spin_states_config):
        """States section should not be empty."""
        assert len(spin_states_config["states"]) > 0

    def test_has_abstract_base(self, spin_states_config):
        """Should have _spin_base abstract state."""
        assert "_spin_base" in spin_states_config["states"]

class TestSpinBaseState:
    """Tests for _spin_base abstract state."""

    def test_spin_base_is_abstract(self, spin_states_config):
        """_spin_base should be marked as abstract."""
        base = spin_states_config["states"]["_spin_base"]
        assert "abstract" in base
        assert base["abstract"] is True

    def test_spin_base_extends_base_phase(self, spin_states_config):
        """_spin_base should extend _base_phase."""
        base = spin_states_config["states"]["_spin_base"]
        assert "extends" in base
        assert base["extends"] == "_base_phase"

    def test_spin_base_has_parameters(self, spin_states_config):
        """_spin_base should have parameters."""
        base = spin_states_config["states"]["_spin_base"]
        assert "parameters" in base

    def test_spin_base_default_price_action(self, spin_states_config):
        """_spin_base should have default_price_action parameter."""
        base = spin_states_config["states"]["_spin_base"]
        assert "default_price_action" in base["parameters"]
        assert base["parameters"]["default_price_action"] == "deflect_and_continue"

    def test_spin_base_default_unclear_action(self, spin_states_config):
        """_spin_base should have default_unclear_action parameter."""
        base = spin_states_config["states"]["_spin_base"]
        assert "default_unclear_action" in base["parameters"]
        assert base["parameters"]["default_unclear_action"] == "continue_current_goal"

    def test_spin_base_has_transitions(self, spin_states_config):
        """_spin_base should have transitions."""
        base = spin_states_config["states"]["_spin_base"]
        assert "transitions" in base

    def test_spin_base_rejection_transition(self, spin_states_config):
        """_spin_base should have rejection transition."""
        base = spin_states_config["states"]["_spin_base"]
        assert "rejection" in base["transitions"]
        assert base["transitions"]["rejection"] == "soft_close"

    def test_spin_base_demo_request_transition(self, spin_states_config):
        """_spin_base should have demo_request transition."""
        base = spin_states_config["states"]["_spin_base"]
        assert "demo_request" in base["transitions"]
        assert base["transitions"]["demo_request"] == "close"

    def test_spin_base_objection_transitions(self, spin_states_config):
        """_spin_base should have objection transitions."""
        base = spin_states_config["states"]["_spin_base"]
        assert "objection_price" in base["transitions"]
        assert "objection_competitor" in base["transitions"]
        assert "objection_no_time" in base["transitions"]
        assert "objection_think" in base["transitions"]

class TestSpinSituationState:
    """Tests for spin_situation state."""

    def test_spin_situation_exists(self, spin_states_config):
        """spin_situation state should exist."""
        assert "spin_situation" in spin_states_config["states"]

    def test_spin_situation_extends_base(self, spin_states_config):
        """spin_situation should extend _spin_base."""
        state = spin_states_config["states"]["spin_situation"]
        assert "extends" in state
        assert state["extends"] == "_spin_base"

    def test_spin_situation_has_goal(self, spin_states_config):
        """spin_situation should have goal."""
        state = spin_states_config["states"]["spin_situation"]
        assert "goal" in state
        assert "ситуаци" in state["goal"].lower()

    def test_spin_situation_has_phase(self, spin_states_config):
        """spin_situation should have phase."""
        state = spin_states_config["states"]["spin_situation"]
        assert "phase" in state
        assert state["phase"] == "situation"

    def test_spin_situation_required_data(self, spin_states_config):
        """spin_situation should have required data."""
        state = spin_states_config["states"]["spin_situation"]
        assert "required_data" in state
        assert "company_size" in state["required_data"]

    def test_spin_situation_optional_data(self, spin_states_config):
        """spin_situation should have optional data."""
        state = spin_states_config["states"]["spin_situation"]
        assert "optional_data" in state
        assert "current_tools" in state["optional_data"]
        assert "business_type" in state["optional_data"]

    def test_spin_situation_transitions(self, spin_states_config):
        """spin_situation should have transitions."""
        state = spin_states_config["states"]["spin_situation"]
        assert "transitions" in state
        assert "data_complete" in state["transitions"]
        assert state["transitions"]["data_complete"] == "spin_problem"

    def test_spin_situation_has_rules(self, spin_states_config):
        """spin_situation should have rules."""
        state = spin_states_config["states"]["spin_situation"]
        assert "rules" in state
        assert "unclear" in state["rules"]

class TestSpinProblemState:
    """Tests for spin_problem state."""

    def test_spin_problem_exists(self, spin_states_config):
        """spin_problem state should exist."""
        assert "spin_problem" in spin_states_config["states"]

    def test_spin_problem_extends_base(self, spin_states_config):
        """spin_problem should extend _spin_base."""
        state = spin_states_config["states"]["spin_problem"]
        assert state["extends"] == "_spin_base"

    def test_spin_problem_has_phase(self, spin_states_config):
        """spin_problem should have problem phase."""
        state = spin_states_config["states"]["spin_problem"]
        assert state["phase"] == "problem"

    def test_spin_problem_required_data(self, spin_states_config):
        """spin_problem should require pain_point."""
        state = spin_states_config["states"]["spin_problem"]
        assert "pain_point" in state["required_data"]

    def test_spin_problem_transitions_to_implication(self, spin_states_config):
        """spin_problem should transition to spin_implication."""
        state = spin_states_config["states"]["spin_problem"]
        assert "data_complete" in state["transitions"]
        assert state["transitions"]["data_complete"] == "spin_implication"

    def test_spin_problem_handles_no_problem(self, spin_states_config):
        """spin_problem should handle no_problem intent."""
        state = spin_states_config["states"]["spin_problem"]
        assert "no_problem" in state["transitions"]

    def test_spin_problem_handles_agreement(self, spin_states_config):
        """spin_problem should handle agreement intent."""
        state = spin_states_config["states"]["spin_problem"]
        assert "agreement" in state["transitions"]
        assert state["transitions"]["agreement"] == "presentation"

class TestSpinImplicationState:
    """Tests for spin_implication state."""

    def test_spin_implication_exists(self, spin_states_config):
        """spin_implication state should exist."""
        assert "spin_implication" in spin_states_config["states"]

    def test_spin_implication_has_phase(self, spin_states_config):
        """spin_implication should have implication phase."""
        state = spin_states_config["states"]["spin_implication"]
        assert state["phase"] == "implication"

    def test_spin_implication_has_on_enter(self, spin_states_config):
        """spin_implication should have on_enter action."""
        state = spin_states_config["states"]["spin_implication"]
        assert "on_enter" in state

    def test_spin_implication_sets_flag(self, spin_states_config):
        """spin_implication should set implication_probed flag."""
        state = spin_states_config["states"]["spin_implication"]
        assert "set_flags" in state["on_enter"]
        assert "implication_probed" in state["on_enter"]["set_flags"]
        assert state["on_enter"]["set_flags"]["implication_probed"] is True

    def test_spin_implication_required_data(self, spin_states_config):
        """spin_implication should require implication_probed."""
        state = spin_states_config["states"]["spin_implication"]
        assert "implication_probed" in state["required_data"]

    def test_spin_implication_optional_data(self, spin_states_config):
        """spin_implication should have optional data."""
        state = spin_states_config["states"]["spin_implication"]
        assert "pain_impact" in state["optional_data"]
        assert "financial_impact" in state["optional_data"]

    def test_spin_implication_transitions_to_need_payoff(self, spin_states_config):
        """spin_implication should transition to spin_need_payoff."""
        state = spin_states_config["states"]["spin_implication"]
        assert state["transitions"]["data_complete"] == "spin_need_payoff"

class TestSpinNeedPayoffState:
    """Tests for spin_need_payoff state."""

    def test_spin_need_payoff_exists(self, spin_states_config):
        """spin_need_payoff state should exist."""
        assert "spin_need_payoff" in spin_states_config["states"]

    def test_spin_need_payoff_has_phase(self, spin_states_config):
        """spin_need_payoff should have need_payoff phase."""
        state = spin_states_config["states"]["spin_need_payoff"]
        assert state["phase"] == "need_payoff"

    def test_spin_need_payoff_has_on_enter(self, spin_states_config):
        """spin_need_payoff should have on_enter action."""
        state = spin_states_config["states"]["spin_need_payoff"]
        assert "on_enter" in state

    def test_spin_need_payoff_sets_flag(self, spin_states_config):
        """spin_need_payoff should set need_payoff_probed flag."""
        state = spin_states_config["states"]["spin_need_payoff"]
        assert "set_flags" in state["on_enter"]
        assert "need_payoff_probed" in state["on_enter"]["set_flags"]

    def test_spin_need_payoff_required_data(self, spin_states_config):
        """spin_need_payoff should require need_payoff_probed."""
        state = spin_states_config["states"]["spin_need_payoff"]
        assert "need_payoff_probed" in state["required_data"]

    def test_spin_need_payoff_optional_data(self, spin_states_config):
        """spin_need_payoff should have optional data."""
        state = spin_states_config["states"]["spin_need_payoff"]
        assert "desired_outcome" in state["optional_data"]
        assert "value_acknowledged" in state["optional_data"]

    def test_spin_need_payoff_transitions_to_presentation(self, spin_states_config):
        """spin_need_payoff should transition to presentation."""
        state = spin_states_config["states"]["spin_need_payoff"]
        assert state["transitions"]["data_complete"] == "presentation"
        assert state["transitions"]["agreement"] == "presentation"

    def test_spin_need_payoff_handles_no_need(self, spin_states_config):
        """spin_need_payoff should handle no_need intent."""
        state = spin_states_config["states"]["spin_need_payoff"]
        assert "no_need" in state["transitions"]
        assert state["transitions"]["no_need"] == "soft_close"

class TestSpinStateCompleteness:
    """Tests for SPIN state completeness."""

    def test_all_spin_states_exist(self, spin_states_config):
        """All SPIN states should exist."""
        expected_states = [
            "_spin_base",
            "spin_situation",
            "spin_problem",
            "spin_implication",
            "spin_need_payoff",
        ]
        for state_name in expected_states:
            assert state_name in spin_states_config["states"], f"Missing: {state_name}"

    def test_all_concrete_states_extend_base(self, spin_states_config):
        """All concrete SPIN states should extend _spin_base."""
        concrete_states = [
            "spin_situation",
            "spin_problem",
            "spin_implication",
            "spin_need_payoff",
        ]
        for state_name in concrete_states:
            state = spin_states_config["states"][state_name]
            assert state["extends"] == "_spin_base", f"{state_name} should extend _spin_base"

    def test_all_concrete_states_have_goals(self, spin_states_config):
        """All concrete SPIN states should have goals."""
        concrete_states = [
            "spin_situation",
            "spin_problem",
            "spin_implication",
            "spin_need_payoff",
        ]
        for state_name in concrete_states:
            state = spin_states_config["states"][state_name]
            assert "goal" in state, f"{state_name} missing goal"
            assert len(state["goal"]) > 0

    def test_all_concrete_states_have_phases(self, spin_states_config):
        """All concrete SPIN states should have phases."""
        expected_phases = {
            "spin_situation": "situation",
            "spin_problem": "problem",
            "spin_implication": "implication",
            "spin_need_payoff": "need_payoff",
        }
        for state_name, expected_phase in expected_phases.items():
            state = spin_states_config["states"][state_name]
            assert state["phase"] == expected_phase

class TestSpinStateRules:
    """Tests for SPIN state rules."""

    def test_all_states_have_unclear_rules(self, spin_states_config):
        """All concrete states should handle unclear intent."""
        concrete_states = [
            "spin_situation",
            "spin_problem",
            "spin_implication",
            "spin_need_payoff",
        ]
        for state_name in concrete_states:
            state = spin_states_config["states"][state_name]
            assert "rules" in state, f"{state_name} missing rules"
            assert "unclear" in state["rules"], f"{state_name} missing unclear rule"

    def test_unclear_rules_have_when_conditions(self, spin_states_config):
        """Unclear rules should have conditional logic."""
        state = spin_states_config["states"]["spin_situation"]
        unclear_rules = state["rules"]["unclear"]
        # Should have at least one conditional rule
        has_conditional = any(
            isinstance(rule, dict) and "when" in rule
            for rule in unclear_rules
        )
        assert has_conditional

class TestSpinStateTransitions:
    """Tests for SPIN state transitions."""

    def test_spin_flow_is_linear(self, spin_states_config):
        """SPIN flow should progress linearly through phases."""
        flow = {
            "spin_situation": "spin_problem",
            "spin_problem": "spin_implication",
            "spin_implication": "spin_need_payoff",
            "spin_need_payoff": "presentation",
        }
        for state_name, expected_next in flow.items():
            state = spin_states_config["states"][state_name]
            assert state["transitions"]["data_complete"] == expected_next

    def test_all_states_can_reach_presentation(self, spin_states_config):
        """States should eventually lead to presentation."""
        # Check agreement transitions
        assert spin_states_config["states"]["spin_problem"]["transitions"]["agreement"] == "presentation"
        assert spin_states_config["states"]["spin_implication"]["transitions"]["agreement"] == "spin_need_payoff"
        assert spin_states_config["states"]["spin_need_payoff"]["transitions"]["agreement"] == "presentation"

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
