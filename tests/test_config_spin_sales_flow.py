"""
Comprehensive tests for SPIN phases and sales_flow configuration.

Tests 100% coverage of:
- spin/phases.yaml
- states/sales_flow.yaml
"""

import pytest
from pathlib import Path
import yaml

import sys

# Paths to config files
YAML_CONFIG_DIR = Path(__file__).parent.parent / "src" / "yaml_config"
SPIN_PHASES_FILE = YAML_CONFIG_DIR / "spin" / "phases.yaml"
SALES_FLOW_FILE = YAML_CONFIG_DIR / "states" / "sales_flow.yaml"

@pytest.fixture(scope="module")
def spin_phases():
    """Load spin/phases.yaml fixture."""
    with open(SPIN_PHASES_FILE, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

@pytest.fixture(scope="module")
def sales_flow():
    """Load states/sales_flow.yaml fixture."""
    with open(SALES_FLOW_FILE, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

# =============================================================================
# SPIN PHASES.YAML TESTS
# =============================================================================

class TestSpinPhasesOrder:
    """Tests for phase_order configuration."""

    def test_phase_order_exists(self, spin_phases):
        """Test phase_order list exists."""
        assert "phase_order" in spin_phases

    def test_phase_order_count(self, spin_phases):
        """Test phase_order has 4 phases."""
        assert len(spin_phases["phase_order"]) == 4

    def test_phase_order_values(self, spin_phases):
        """Test phase_order has correct phases."""
        order = spin_phases["phase_order"]
        assert order == ["situation", "problem", "implication", "need_payoff"]

    def test_phase_order_is_list(self, spin_phases):
        """Test phase_order is a list."""
        assert isinstance(spin_phases["phase_order"], list)

class TestSpinPhasesSituation:
    """Tests for situation phase configuration."""

    def test_situation_phase_exists(self, spin_phases):
        """Test situation phase exists."""
        assert "situation" in spin_phases["phases"]

    def test_situation_state(self, spin_phases):
        """Test situation.state parameter."""
        phase = spin_phases["phases"]["situation"]
        assert phase["state"] == "spin_situation"

    def test_situation_description(self, spin_phases):
        """Test situation.description parameter."""
        phase = spin_phases["phases"]["situation"]
        assert "description" in phase
        assert len(phase["description"]) > 0

    def test_situation_skippable(self, spin_phases):
        """Test situation.skippable = false."""
        phase = spin_phases["phases"]["situation"]
        assert phase["skippable"] is False

    def test_situation_skip_conditions_empty(self, spin_phases):
        """Test situation.skip_conditions is empty."""
        phase = spin_phases["phases"]["situation"]
        assert phase["skip_conditions"] == []

class TestSpinPhasesProblem:
    """Tests for problem phase configuration."""

    def test_problem_phase_exists(self, spin_phases):
        """Test problem phase exists."""
        assert "problem" in spin_phases["phases"]

    def test_problem_state(self, spin_phases):
        """Test problem.state parameter."""
        phase = spin_phases["phases"]["problem"]
        assert phase["state"] == "spin_problem"

    def test_problem_description(self, spin_phases):
        """Test problem.description parameter."""
        phase = spin_phases["phases"]["problem"]
        assert "description" in phase
        assert len(phase["description"]) > 0

    def test_problem_skippable(self, spin_phases):
        """Test problem.skippable = false."""
        phase = spin_phases["phases"]["problem"]
        assert phase["skippable"] is False

    def test_problem_skip_conditions_empty(self, spin_phases):
        """Test problem.skip_conditions is empty."""
        phase = spin_phases["phases"]["problem"]
        assert phase["skip_conditions"] == []

class TestSpinPhasesImplication:
    """Tests for implication phase configuration."""

    def test_implication_phase_exists(self, spin_phases):
        """Test implication phase exists."""
        assert "implication" in spin_phases["phases"]

    def test_implication_state(self, spin_phases):
        """Test implication.state parameter."""
        phase = spin_phases["phases"]["implication"]
        assert phase["state"] == "spin_implication"

    def test_implication_description(self, spin_phases):
        """Test implication.description parameter."""
        phase = spin_phases["phases"]["implication"]
        assert "description" in phase
        assert len(phase["description"]) > 0

    def test_implication_skippable(self, spin_phases):
        """Test implication.skippable = true."""
        phase = spin_phases["phases"]["implication"]
        assert phase["skippable"] is True

    def test_implication_skip_conditions(self, spin_phases):
        """Test implication.skip_conditions has conditions."""
        phase = spin_phases["phases"]["implication"]
        skip = phase["skip_conditions"]
        assert "has_high_interest" in skip
        assert "lead_is_hot" in skip

class TestSpinPhasesNeedPayoff:
    """Tests for need_payoff phase configuration."""

    def test_need_payoff_phase_exists(self, spin_phases):
        """Test need_payoff phase exists."""
        assert "need_payoff" in spin_phases["phases"]

    def test_need_payoff_state(self, spin_phases):
        """Test need_payoff.state parameter."""
        phase = spin_phases["phases"]["need_payoff"]
        assert phase["state"] == "spin_need_payoff"

    def test_need_payoff_description(self, spin_phases):
        """Test need_payoff.description parameter."""
        phase = spin_phases["phases"]["need_payoff"]
        assert "description" in phase
        assert len(phase["description"]) > 0

    def test_need_payoff_skippable(self, spin_phases):
        """Test need_payoff.skippable = true."""
        phase = spin_phases["phases"]["need_payoff"]
        assert phase["skippable"] is True

    def test_need_payoff_skip_conditions(self, spin_phases):
        """Test need_payoff.skip_conditions has conditions."""
        phase = spin_phases["phases"]["need_payoff"]
        skip = phase["skip_conditions"]
        assert "has_desired_outcome" in skip
        assert "lead_is_hot" in skip

class TestSpinPhasesProbeActions:
    """Tests for probe_actions configuration."""

    def test_probe_actions_exists(self, spin_phases):
        """Test probe_actions section exists."""
        assert "probe_actions" in spin_phases

    def test_probe_action_situation(self, spin_phases):
        """Test probe_actions.situation."""
        actions = spin_phases["probe_actions"]
        assert actions["situation"] == "probe_situation"

    def test_probe_action_problem(self, spin_phases):
        """Test probe_actions.problem."""
        actions = spin_phases["probe_actions"]
        assert actions["problem"] == "probe_problem"

    def test_probe_action_implication(self, spin_phases):
        """Test probe_actions.implication."""
        actions = spin_phases["probe_actions"]
        assert actions["implication"] == "probe_implication"

    def test_probe_action_need_payoff(self, spin_phases):
        """Test probe_actions.need_payoff."""
        actions = spin_phases["probe_actions"]
        assert actions["need_payoff"] == "probe_need_payoff"

class TestSpinPhasesEntryFlags:
    """Tests for entry_flags configuration."""

    def test_entry_flags_exists(self, spin_phases):
        """Test entry_flags section exists."""
        assert "entry_flags" in spin_phases

    def test_entry_flag_implication(self, spin_phases):
        """Test entry_flags.implication."""
        flags = spin_phases["entry_flags"]
        assert flags["implication"] == "implication_probed"

    def test_entry_flag_need_payoff(self, spin_phases):
        """Test entry_flags.need_payoff."""
        flags = spin_phases["entry_flags"]
        assert flags["need_payoff"] == "need_payoff_probed"

# =============================================================================
# SALES FLOW.YAML TESTS
# =============================================================================

class TestSalesFlowMeta:
    """Tests for sales_flow meta section."""

    def test_meta_exists(self, sales_flow):
        """Test meta section exists."""
        assert "meta" in sales_flow

    def test_meta_version(self, sales_flow):
        """Test meta.version."""
        assert sales_flow["meta"]["version"] == "1.0"

    def test_meta_description(self, sales_flow):
        """Test meta.description."""
        assert "description" in sales_flow["meta"]
        assert "SPIN" in sales_flow["meta"]["description"]

class TestSalesFlowDefaults:
    """Tests for sales_flow defaults section."""

    def test_defaults_exists(self, sales_flow):
        """Test defaults section exists."""
        assert "defaults" in sales_flow

    def test_default_action(self, sales_flow):
        """Test defaults.default_action."""
        assert sales_flow["defaults"]["default_action"] == "continue_current_goal"

class TestSalesFlowStatesExist:
    """Tests for state existence."""

    def test_states_section_exists(self, sales_flow):
        """Test states section exists."""
        assert "states" in sales_flow

    def test_greeting_state_exists(self, sales_flow):
        """Test greeting state exists."""
        assert "greeting" in sales_flow["states"]

    def test_spin_situation_state_exists(self, sales_flow):
        """Test spin_situation state exists."""
        assert "spin_situation" in sales_flow["states"]

    def test_spin_problem_state_exists(self, sales_flow):
        """Test spin_problem state exists."""
        assert "spin_problem" in sales_flow["states"]

    def test_spin_implication_state_exists(self, sales_flow):
        """Test spin_implication state exists."""
        assert "spin_implication" in sales_flow["states"]

    def test_spin_need_payoff_state_exists(self, sales_flow):
        """Test spin_need_payoff state exists."""
        assert "spin_need_payoff" in sales_flow["states"]

    def test_presentation_state_exists(self, sales_flow):
        """Test presentation state exists."""
        assert "presentation" in sales_flow["states"]

    def test_handle_objection_state_exists(self, sales_flow):
        """Test handle_objection state exists."""
        assert "handle_objection" in sales_flow["states"]

    def test_close_state_exists(self, sales_flow):
        """Test close state exists."""
        assert "close" in sales_flow["states"]

    def test_success_state_exists(self, sales_flow):
        """Test success state exists."""
        assert "success" in sales_flow["states"]

    def test_soft_close_state_exists(self, sales_flow):
        """Test soft_close state exists."""
        assert "soft_close" in sales_flow["states"]

class TestSalesFlowGreeting:
    """Tests for greeting state configuration."""

    def test_greeting_goal(self, sales_flow):
        """Test greeting.goal."""
        state = sales_flow["states"]["greeting"]
        assert "goal" in state
        assert len(state["goal"]) > 0

    def test_greeting_required_data_empty(self, sales_flow):
        """Test greeting.required_data is empty."""
        state = sales_flow["states"]["greeting"]
        assert state["required_data"] == []

    def test_greeting_transitions_price_question(self, sales_flow):
        """Test greeting transitions for price_question."""
        transitions = sales_flow["states"]["greeting"]["transitions"]
        assert transitions["price_question"] == "spin_situation"

    def test_greeting_transitions_question_features(self, sales_flow):
        """Test greeting transitions for question_features."""
        transitions = sales_flow["states"]["greeting"]["transitions"]
        assert transitions["question_features"] == "spin_situation"

    def test_greeting_transitions_demo_request(self, sales_flow):
        """Test greeting transitions for demo_request."""
        transitions = sales_flow["states"]["greeting"]["transitions"]
        assert transitions["demo_request"] == "close"

    def test_greeting_transitions_rejection(self, sales_flow):
        """Test greeting transitions for rejection."""
        transitions = sales_flow["states"]["greeting"]["transitions"]
        assert transitions["rejection"] == "soft_close"

    def test_greeting_rules_greeting(self, sales_flow):
        """Test greeting rules for greeting intent."""
        rules = sales_flow["states"]["greeting"]["rules"]
        assert rules["greeting"] == "greet_back"

    def test_greeting_rules_unclear(self, sales_flow):
        """Test greeting rules for unclear intent."""
        rules = sales_flow["states"]["greeting"]["rules"]
        assert rules["unclear"] == "ask_how_to_help"

class TestSalesFlowSpinSituation:
    """Tests for spin_situation state configuration."""

    def test_spin_situation_goal(self, sales_flow):
        """Test spin_situation.goal."""
        state = sales_flow["states"]["spin_situation"]
        assert "goal" in state
        # Goal should describe understanding client's situation
        assert "ситуаци" in state["goal"].lower() or "situation" in state["goal"].lower()

    def test_spin_situation_spin_phase(self, sales_flow):
        """Test spin_situation.spin_phase."""
        state = sales_flow["states"]["spin_situation"]
        assert state["spin_phase"] == "situation"

    def test_spin_situation_required_data(self, sales_flow):
        """Test spin_situation.required_data includes company_size."""
        state = sales_flow["states"]["spin_situation"]
        assert "company_size" in state["required_data"]

    def test_spin_situation_optional_data(self, sales_flow):
        """Test spin_situation.optional_data."""
        state = sales_flow["states"]["spin_situation"]
        optional = state["optional_data"]
        assert "current_tools" in optional
        assert "business_type" in optional

    def test_spin_situation_transitions_data_complete(self, sales_flow):
        """Test spin_situation transitions for data_complete."""
        transitions = sales_flow["states"]["spin_situation"]["transitions"]
        assert transitions["data_complete"] == "spin_problem"

    def test_spin_situation_transitions_situation_provided(self, sales_flow):
        """Test spin_situation transitions for situation_provided."""
        transitions = sales_flow["states"]["spin_situation"]["transitions"]
        assert transitions["situation_provided"] == "spin_problem"

    def test_spin_situation_rules_price_question(self, sales_flow):
        """Test spin_situation rules for price_question."""
        rules = sales_flow["states"]["spin_situation"]["rules"]
        assert "price_question" in rules
        # Should be conditional
        assert isinstance(rules["price_question"], list)

class TestSalesFlowSpinProblem:
    """Tests for spin_problem state configuration."""

    def test_spin_problem_goal(self, sales_flow):
        """Test spin_problem.goal."""
        state = sales_flow["states"]["spin_problem"]
        assert "goal" in state
        assert "проблем" in state["goal"].lower() or "problem" in state["goal"].lower()

    def test_spin_problem_spin_phase(self, sales_flow):
        """Test spin_problem.spin_phase."""
        state = sales_flow["states"]["spin_problem"]
        assert state["spin_phase"] == "problem"

    def test_spin_problem_required_data(self, sales_flow):
        """Test spin_problem.required_data includes pain_point."""
        state = sales_flow["states"]["spin_problem"]
        assert "pain_point" in state["required_data"]

    def test_spin_problem_transitions_data_complete(self, sales_flow):
        """Test spin_problem transitions for data_complete."""
        transitions = sales_flow["states"]["spin_problem"]["transitions"]
        assert transitions["data_complete"] == "spin_implication"

    def test_spin_problem_transitions_problem_revealed(self, sales_flow):
        """Test spin_problem transitions for problem_revealed."""
        transitions = sales_flow["states"]["spin_problem"]["transitions"]
        assert transitions["problem_revealed"] == "spin_implication"

    def test_spin_problem_transitions_no_problem(self, sales_flow):
        """Test spin_problem transitions for no_problem."""
        transitions = sales_flow["states"]["spin_problem"]["transitions"]
        assert transitions["no_problem"] == "spin_implication"

class TestSalesFlowSpinImplication:
    """Tests for spin_implication state configuration."""

    def test_spin_implication_goal(self, sales_flow):
        """Test spin_implication.goal."""
        state = sales_flow["states"]["spin_implication"]
        assert "goal" in state

    def test_spin_implication_spin_phase(self, sales_flow):
        """Test spin_implication.spin_phase."""
        state = sales_flow["states"]["spin_implication"]
        assert state["spin_phase"] == "implication"

    def test_spin_implication_required_data(self, sales_flow):
        """Test spin_implication.required_data includes implication_probed."""
        state = sales_flow["states"]["spin_implication"]
        assert "implication_probed" in state["required_data"]

    def test_spin_implication_optional_data(self, sales_flow):
        """Test spin_implication.optional_data."""
        state = sales_flow["states"]["spin_implication"]
        optional = state["optional_data"]
        assert "pain_impact" in optional
        assert "financial_impact" in optional

    def test_spin_implication_transitions_data_complete(self, sales_flow):
        """Test spin_implication transitions for data_complete."""
        transitions = sales_flow["states"]["spin_implication"]["transitions"]
        assert transitions["data_complete"] == "spin_need_payoff"

    def test_spin_implication_transitions_implication_acknowledged(self, sales_flow):
        """Test spin_implication transitions for implication_acknowledged."""
        transitions = sales_flow["states"]["spin_implication"]["transitions"]
        assert transitions["implication_acknowledged"] == "spin_need_payoff"

class TestSalesFlowSpinNeedPayoff:
    """Tests for spin_need_payoff state configuration."""

    def test_spin_need_payoff_goal(self, sales_flow):
        """Test spin_need_payoff.goal."""
        state = sales_flow["states"]["spin_need_payoff"]
        assert "goal" in state

    def test_spin_need_payoff_spin_phase(self, sales_flow):
        """Test spin_need_payoff.spin_phase."""
        state = sales_flow["states"]["spin_need_payoff"]
        assert state["spin_phase"] == "need_payoff"

    def test_spin_need_payoff_required_data(self, sales_flow):
        """Test spin_need_payoff.required_data includes need_payoff_probed."""
        state = sales_flow["states"]["spin_need_payoff"]
        assert "need_payoff_probed" in state["required_data"]

    def test_spin_need_payoff_optional_data(self, sales_flow):
        """Test spin_need_payoff.optional_data."""
        state = sales_flow["states"]["spin_need_payoff"]
        optional = state["optional_data"]
        assert "desired_outcome" in optional
        assert "value_acknowledged" in optional

    def test_spin_need_payoff_transitions_data_complete(self, sales_flow):
        """Test spin_need_payoff transitions for data_complete."""
        transitions = sales_flow["states"]["spin_need_payoff"]["transitions"]
        assert transitions["data_complete"] == "presentation"

    def test_spin_need_payoff_transitions_need_expressed(self, sales_flow):
        """Test spin_need_payoff transitions for need_expressed."""
        transitions = sales_flow["states"]["spin_need_payoff"]["transitions"]
        assert transitions["need_expressed"] == "presentation"

    def test_spin_need_payoff_transitions_no_need(self, sales_flow):
        """Test spin_need_payoff transitions for no_need."""
        transitions = sales_flow["states"]["spin_need_payoff"]["transitions"]
        assert transitions["no_need"] == "soft_close"

class TestSalesFlowPresentation:
    """Tests for presentation state configuration."""

    def test_presentation_goal(self, sales_flow):
        """Test presentation.goal."""
        state = sales_flow["states"]["presentation"]
        assert "goal" in state

    def test_presentation_required_data_empty(self, sales_flow):
        """Test presentation.required_data is empty."""
        state = sales_flow["states"]["presentation"]
        assert state["required_data"] == []

    def test_presentation_transitions_agreement(self, sales_flow):
        """Test presentation transitions for agreement."""
        transitions = sales_flow["states"]["presentation"]["transitions"]
        assert transitions["agreement"] == "close"

    def test_presentation_transitions_objection_price(self, sales_flow):
        """Test presentation transitions for objection_price."""
        transitions = sales_flow["states"]["presentation"]["transitions"]
        assert transitions["objection_price"] == "handle_objection"

    def test_presentation_transitions_demo_request(self, sales_flow):
        """Test presentation transitions for demo_request."""
        transitions = sales_flow["states"]["presentation"]["transitions"]
        assert transitions["demo_request"] == "close"

    def test_presentation_rules_price_question(self, sales_flow):
        """Test presentation rules for price_question."""
        rules = sales_flow["states"]["presentation"]["rules"]
        assert rules["price_question"] == "answer_with_facts"

class TestSalesFlowHandleObjection:
    """Tests for handle_objection state configuration."""

    def test_handle_objection_goal(self, sales_flow):
        """Test handle_objection.goal."""
        state = sales_flow["states"]["handle_objection"]
        assert "goal" in state
        assert "возражени" in state["goal"].lower() or "objection" in state["goal"].lower()

    def test_handle_objection_required_data_empty(self, sales_flow):
        """Test handle_objection.required_data is empty."""
        state = sales_flow["states"]["handle_objection"]
        assert state["required_data"] == []

    def test_handle_objection_transitions_agreement(self, sales_flow):
        """Test handle_objection transitions for agreement."""
        transitions = sales_flow["states"]["handle_objection"]["transitions"]
        assert transitions["agreement"] == "close"

    def test_handle_objection_transitions_objection_price_conditional(self, sales_flow):
        """Test handle_objection has conditional transitions for objection_price."""
        transitions = sales_flow["states"]["handle_objection"]["transitions"]
        objection_price = transitions["objection_price"]
        # Should be a list with conditions
        assert isinstance(objection_price, list)
        # First item should be conditional
        assert objection_price[0]["when"] == "objection_limit_reached"
        assert objection_price[0]["then"] == "soft_close"

    def test_handle_objection_rules_with_roi(self, sales_flow):
        """Test handle_objection rules for price_question with ROI."""
        rules = sales_flow["states"]["handle_objection"]["rules"]
        price_rules = rules["price_question"]
        # Should have conditional with can_handle_with_roi
        assert isinstance(price_rules, list)
        has_roi_condition = any(
            isinstance(r, dict) and r.get("when") == "can_handle_with_roi"
            for r in price_rules
        )
        assert has_roi_condition

class TestSalesFlowClose:
    """Tests for close state configuration."""

    def test_close_goal(self, sales_flow):
        """Test close.goal."""
        state = sales_flow["states"]["close"]
        assert "goal" in state
        assert "контакт" in state["goal"].lower() or "демо" in state["goal"].lower()

    def test_close_required_data(self, sales_flow):
        """Test close.required_data includes contact_info."""
        state = sales_flow["states"]["close"]
        assert "contact_info" in state["required_data"]

    def test_close_transitions_data_complete(self, sales_flow):
        """Test close transitions for data_complete."""
        transitions = sales_flow["states"]["close"]["transitions"]
        assert transitions["data_complete"] == "success"

    def test_close_transitions_contact_provided(self, sales_flow):
        """Test close transitions for contact_provided."""
        transitions = sales_flow["states"]["close"]["transitions"]
        assert transitions["contact_provided"] == "success"

    def test_close_transitions_agreement_conditional(self, sales_flow):
        """Test close has conditional transitions for agreement."""
        transitions = sales_flow["states"]["close"]["transitions"]
        agreement = transitions["agreement"]
        # Should be a list with conditions
        assert isinstance(agreement, list)
        # First item should be conditional
        assert agreement[0]["when"] == "ready_for_close"
        assert agreement[0]["then"] == "success"

class TestSalesFlowSuccess:
    """Tests for success state configuration."""

    def test_success_goal(self, sales_flow):
        """Test success.goal."""
        state = sales_flow["states"]["success"]
        assert "goal" in state

    def test_success_is_final(self, sales_flow):
        """Test success.is_final = true."""
        state = sales_flow["states"]["success"]
        assert state["is_final"] is True

class TestSalesFlowSoftClose:
    """Tests for soft_close state configuration."""

    def test_soft_close_goal(self, sales_flow):
        """Test soft_close.goal."""
        state = sales_flow["states"]["soft_close"]
        assert "goal" in state

    def test_soft_close_is_not_final(self, sales_flow):
        """Test soft_close.is_final = false."""
        state = sales_flow["states"]["soft_close"]
        assert state["is_final"] is False

    def test_soft_close_transitions_agreement(self, sales_flow):
        """Test soft_close transitions for agreement."""
        transitions = sales_flow["states"]["soft_close"]["transitions"]
        assert transitions["agreement"] == "spin_situation"

    def test_soft_close_transitions_demo_request(self, sales_flow):
        """Test soft_close transitions for demo_request."""
        transitions = sales_flow["states"]["soft_close"]["transitions"]
        assert transitions["demo_request"] == "close"

    def test_soft_close_transitions_go_back(self, sales_flow):
        """Test soft_close transitions for go_back."""
        transitions = sales_flow["states"]["soft_close"]["transitions"]
        assert transitions["go_back"] == "greeting"

    def test_soft_close_transitions_price_question(self, sales_flow):
        """Test soft_close transitions for price_question."""
        transitions = sales_flow["states"]["soft_close"]["transitions"]
        assert transitions["price_question"] == "presentation"

class TestSalesFlowConsistency:
    """Tests for internal consistency of sales_flow."""

    def test_all_transition_targets_are_valid_states(self, sales_flow):
        """Test all transition targets point to valid states."""
        states = sales_flow["states"]
        valid_states = set(states.keys())

        for state_name, state_config in states.items():
            transitions = state_config.get("transitions", {})
            for intent, target in transitions.items():
                # Handle conditional transitions
                if isinstance(target, list):
                    for item in target:
                        if isinstance(item, dict):
                            actual_target = item.get("then")
                        else:
                            actual_target = item
                        assert actual_target in valid_states, \
                            f"State {state_name} has invalid transition target {actual_target}"
                elif isinstance(target, str):
                    assert target in valid_states, \
                        f"State {state_name} has invalid transition target {target}"

    def test_all_spin_phases_have_states(self, sales_flow, spin_phases):
        """Test all SPIN phases have corresponding states."""
        for phase in spin_phases["phase_order"]:
            expected_state = spin_phases["phases"][phase]["state"]
            assert expected_state in sales_flow["states"], \
                f"Phase {phase} state {expected_state} not found"

    def test_spin_states_have_spin_phase(self, sales_flow):
        """Test all spin_* states have spin_phase attribute."""
        spin_states = ["spin_situation", "spin_problem", "spin_implication", "spin_need_payoff"]
        for state_name in spin_states:
            state = sales_flow["states"][state_name]
            assert "spin_phase" in state, f"State {state_name} missing spin_phase"

    def test_final_states_have_is_final(self, sales_flow):
        """Test states marked as final have is_final attribute."""
        assert sales_flow["states"]["success"]["is_final"] is True

    def test_required_data_progression(self, sales_flow):
        """Test that required_data becomes more complex as we progress."""
        situation = sales_flow["states"]["spin_situation"]["required_data"]
        close = sales_flow["states"]["close"]["required_data"]

        assert len(situation) >= 1  # At least company_size
        assert len(close) >= 1  # At least contact_info

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
