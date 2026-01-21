"""
Comprehensive tests for flow configuration files.

Tests 100% coverage of:
- flows/spin_selling/flow.yaml
- flows/_base/states.yaml
- flows/_base/priorities.yaml
- flows/_base/mixins.yaml
"""

import pytest
from pathlib import Path
import yaml

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


# Paths to config files
YAML_CONFIG_DIR = Path(__file__).parent.parent / "src" / "yaml_config"
SPIN_FLOW_FILE = YAML_CONFIG_DIR / "flows" / "spin_selling" / "flow.yaml"
BASE_STATES_FILE = YAML_CONFIG_DIR / "flows" / "_base" / "states.yaml"
PRIORITIES_FILE = YAML_CONFIG_DIR / "flows" / "_base" / "priorities.yaml"
MIXINS_FILE = YAML_CONFIG_DIR / "flows" / "_base" / "mixins.yaml"


@pytest.fixture(scope="module")
def spin_flow():
    """Load spin_selling flow.yaml fixture."""
    with open(SPIN_FLOW_FILE, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="module")
def base_states():
    """Load base states.yaml fixture."""
    with open(BASE_STATES_FILE, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="module")
def priorities():
    """Load priorities.yaml fixture."""
    with open(PRIORITIES_FILE, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="module")
def mixins():
    """Load mixins.yaml fixture."""
    with open(MIXINS_FILE, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


# =============================================================================
# SPIN SELLING FLOW.YAML TESTS
# =============================================================================

class TestSpinSellingFlowBasics:
    """Tests for basic flow configuration."""

    def test_flow_section_exists(self, spin_flow):
        """Test flow section exists."""
        assert "flow" in spin_flow

    def test_flow_name(self, spin_flow):
        """Test flow.name parameter."""
        assert spin_flow["flow"]["name"] == "spin_selling"

    def test_flow_version(self, spin_flow):
        """Test flow.version parameter."""
        assert spin_flow["flow"]["version"] == "2.0"

    def test_flow_description(self, spin_flow):
        """Test flow.description parameter."""
        assert "description" in spin_flow["flow"]
        assert "SPIN" in spin_flow["flow"]["description"]


class TestSpinSellingFlowVariables:
    """Tests for flow variables section."""

    def test_variables_section_exists(self, spin_flow):
        """Test variables section exists."""
        assert "variables" in spin_flow["flow"]

    def test_entry_state_variable(self, spin_flow):
        """Test flow.variables.entry_state."""
        assert spin_flow["flow"]["variables"]["entry_state"] == "spin_situation"

    def test_company_name_variable(self, spin_flow):
        """Test flow.variables.company_name."""
        assert spin_flow["flow"]["variables"]["company_name"] == "Poster"

    def test_product_name_variable(self, spin_flow):
        """Test flow.variables.product_name."""
        assert spin_flow["flow"]["variables"]["product_name"] == "CRM-система"


class TestSpinSellingFlowPhases:
    """Tests for flow phases configuration."""

    def test_phases_section_exists(self, spin_flow):
        """Test phases section exists."""
        assert "phases" in spin_flow["flow"]

    def test_phases_order(self, spin_flow):
        """Test flow.phases.order list."""
        order = spin_flow["flow"]["phases"]["order"]
        assert order == ["situation", "problem", "implication", "need_payoff"]

    def test_post_phases_state(self, spin_flow):
        """Test flow.phases.post_phases_state."""
        assert spin_flow["flow"]["phases"]["post_phases_state"] == "presentation"

    def test_phases_mapping_situation(self, spin_flow):
        """Test flow.phases.mapping.situation."""
        mapping = spin_flow["flow"]["phases"]["mapping"]
        assert mapping["situation"] == "spin_situation"

    def test_phases_mapping_problem(self, spin_flow):
        """Test flow.phases.mapping.problem."""
        mapping = spin_flow["flow"]["phases"]["mapping"]
        assert mapping["problem"] == "spin_problem"

    def test_phases_mapping_implication(self, spin_flow):
        """Test flow.phases.mapping.implication."""
        mapping = spin_flow["flow"]["phases"]["mapping"]
        assert mapping["implication"] == "spin_implication"

    def test_phases_mapping_need_payoff(self, spin_flow):
        """Test flow.phases.mapping.need_payoff."""
        mapping = spin_flow["flow"]["phases"]["mapping"]
        assert mapping["need_payoff"] == "spin_need_payoff"

    def test_progress_intents_situation_provided(self, spin_flow):
        """Test flow.phases.progress_intents.situation_provided."""
        progress = spin_flow["flow"]["phases"]["progress_intents"]
        assert progress["situation_provided"] == "situation"

    def test_progress_intents_problem_revealed(self, spin_flow):
        """Test flow.phases.progress_intents.problem_revealed."""
        progress = spin_flow["flow"]["phases"]["progress_intents"]
        assert progress["problem_revealed"] == "problem"

    def test_progress_intents_implication_acknowledged(self, spin_flow):
        """Test flow.phases.progress_intents.implication_acknowledged."""
        progress = spin_flow["flow"]["phases"]["progress_intents"]
        assert progress["implication_acknowledged"] == "implication"

    def test_progress_intents_need_expressed(self, spin_flow):
        """Test flow.phases.progress_intents.need_expressed."""
        progress = spin_flow["flow"]["phases"]["progress_intents"]
        assert progress["need_expressed"] == "need_payoff"


class TestSpinSellingFlowSkipConditions:
    """Tests for phase skip conditions."""

    def test_skip_conditions_section_exists(self, spin_flow):
        """Test skip_conditions section exists."""
        assert "skip_conditions" in spin_flow["flow"]["phases"]

    def test_skip_conditions_implication(self, spin_flow):
        """Test skip_conditions for implication phase."""
        skip = spin_flow["flow"]["phases"]["skip_conditions"]
        assert "implication" in skip
        assert "has_high_interest" in skip["implication"]
        assert "lead_is_hot" in skip["implication"]

    def test_skip_conditions_need_payoff(self, spin_flow):
        """Test skip_conditions for need_payoff phase."""
        skip = spin_flow["flow"]["phases"]["skip_conditions"]
        assert "need_payoff" in skip
        assert "has_desired_outcome" in skip["need_payoff"]
        assert "lead_is_hot" in skip["need_payoff"]


class TestSpinSellingFlowEntryPoints:
    """Tests for entry points configuration."""

    def test_entry_points_section_exists(self, spin_flow):
        """Test entry_points section exists."""
        assert "entry_points" in spin_flow["flow"]

    def test_entry_point_default(self, spin_flow):
        """Test entry_points.default."""
        assert spin_flow["flow"]["entry_points"]["default"] == "greeting"

    def test_entry_point_hot_lead(self, spin_flow):
        """Test entry_points.hot_lead."""
        assert spin_flow["flow"]["entry_points"]["hot_lead"] == "presentation"

    def test_entry_point_returning_customer(self, spin_flow):
        """Test entry_points.returning_customer."""
        assert spin_flow["flow"]["entry_points"]["returning_customer"] == "spin_situation"


# =============================================================================
# BASE STATES.YAML TESTS
# =============================================================================

class TestBaseStatesAbstract:
    """Tests for abstract base states."""

    def test_states_section_exists(self, base_states):
        """Test states section exists."""
        assert "states" in base_states

    def test_base_greeting_is_abstract(self, base_states):
        """Test _base_greeting is abstract."""
        state = base_states["states"]["_base_greeting"]
        assert state.get("abstract") is True

    def test_base_greeting_goal(self, base_states):
        """Test _base_greeting.goal."""
        state = base_states["states"]["_base_greeting"]
        assert "goal" in state

    def test_base_greeting_rules(self, base_states):
        """Test _base_greeting.rules."""
        state = base_states["states"]["_base_greeting"]
        rules = state["rules"]
        assert rules["greeting"] == "greet_back"
        assert rules["unclear"] == "ask_how_to_help"
        assert rules["gratitude"] == "acknowledge_and_continue"
        assert rules["small_talk"] == "small_talk_and_continue"

    def test_base_terminal_is_abstract(self, base_states):
        """Test _base_terminal is abstract."""
        state = base_states["states"]["_base_terminal"]
        assert state.get("abstract") is True

    def test_base_terminal_rules(self, base_states):
        """Test _base_terminal.rules."""
        state = base_states["states"]["_base_terminal"]
        rules = state["rules"]
        assert rules["farewell"] == "polite_farewell"
        assert rules["gratitude"] == "acknowledge_farewell"

    def test_base_phase_is_abstract(self, base_states):
        """Test _base_phase is abstract."""
        state = base_states["states"]["_base_phase"]
        assert state.get("abstract") is True

    def test_base_phase_mixins(self, base_states):
        """Test _base_phase.mixins list."""
        state = base_states["states"]["_base_phase"]
        mixins = state["mixins"]
        assert "price_handling" in mixins
        assert "product_questions" in mixins
        assert "objection_handling" in mixins
        assert "dialogue_repair" in mixins
        assert "exit_intents" in mixins
        assert "close_shortcuts" in mixins
        assert "social_intents" in mixins

    def test_base_phase_parameters(self, base_states):
        """Test _base_phase.parameters."""
        state = base_states["states"]["_base_phase"]
        params = state["parameters"]
        assert params["default_price_action"] == "deflect_and_continue"
        assert params["default_unclear_action"] == "continue_current_goal"


class TestBaseStatesGreeting:
    """Tests for greeting state."""

    def test_greeting_extends_base(self, base_states):
        """Test greeting extends _base_greeting."""
        state = base_states["states"]["greeting"]
        assert state["extends"] == "_base_greeting"

    def test_greeting_transitions_price_question(self, base_states):
        """Test greeting transitions for price_question."""
        transitions = base_states["states"]["greeting"]["transitions"]
        assert transitions["price_question"] == "{{entry_state}}"

    def test_greeting_transitions_question_features(self, base_states):
        """Test greeting transitions for question_features."""
        transitions = base_states["states"]["greeting"]["transitions"]
        assert transitions["question_features"] == "{{entry_state}}"

    def test_greeting_transitions_question_integrations(self, base_states):
        """Test greeting transitions for question_integrations."""
        transitions = base_states["states"]["greeting"]["transitions"]
        assert transitions["question_integrations"] == "{{entry_state}}"

    def test_greeting_transitions_agreement(self, base_states):
        """Test greeting transitions for agreement."""
        transitions = base_states["states"]["greeting"]["transitions"]
        assert transitions["agreement"] == "{{entry_state}}"

    def test_greeting_transitions_demo_request(self, base_states):
        """Test greeting transitions for demo_request."""
        transitions = base_states["states"]["greeting"]["transitions"]
        assert transitions["demo_request"] == "close"

    def test_greeting_transitions_callback_request(self, base_states):
        """Test greeting transitions for callback_request."""
        transitions = base_states["states"]["greeting"]["transitions"]
        assert transitions["callback_request"] == "close"

    def test_greeting_transitions_rejection(self, base_states):
        """Test greeting transitions for rejection."""
        transitions = base_states["states"]["greeting"]["transitions"]
        assert transitions["rejection"] == "soft_close"

    def test_greeting_transitions_farewell(self, base_states):
        """Test greeting transitions for farewell."""
        transitions = base_states["states"]["greeting"]["transitions"]
        assert transitions["farewell"] == "soft_close"

    def test_greeting_transitions_objection_price(self, base_states):
        """Test greeting transitions for objection_price.

        FIX: Now uses conditional rules - handle_objection by default,
        soft_close only when objection_limit_reached.
        """
        transitions = base_states["states"]["greeting"]["transitions"]
        # New format: list with conditional rule
        assert isinstance(transitions["objection_price"], list)
        # Default (last item) is handle_objection
        assert transitions["objection_price"][-1] == "handle_objection"
        # Conditional rule for limit reached
        assert transitions["objection_price"][0]["when"] == "objection_limit_reached"
        assert transitions["objection_price"][0]["then"] == "soft_close"

    def test_greeting_transitions_objection_no_time(self, base_states):
        """Test greeting transitions for objection_no_time.

        FIX: Now uses conditional rules - handle_objection by default,
        soft_close only when objection_limit_reached.
        """
        transitions = base_states["states"]["greeting"]["transitions"]
        # New format: list with conditional rule
        assert isinstance(transitions["objection_no_time"], list)
        # Default (last item) is handle_objection
        assert transitions["objection_no_time"][-1] == "handle_objection"
        # Conditional goes to soft_close when limit reached
        assert transitions["objection_no_time"][0]["when"] == "objection_limit_reached"
        assert transitions["objection_no_time"][0]["then"] == "soft_close"


class TestBaseStatesSuccess:
    """Tests for success state."""

    def test_success_extends_base_terminal(self, base_states):
        """Test success extends _base_terminal."""
        state = base_states["states"]["success"]
        assert state["extends"] == "_base_terminal"

    def test_success_is_final(self, base_states):
        """Test success.is_final = true."""
        state = base_states["states"]["success"]
        assert state["is_final"] is True

    def test_success_goal(self, base_states):
        """Test success.goal."""
        state = base_states["states"]["success"]
        assert "goal" in state


class TestBaseStatesSoftClose:
    """Tests for soft_close state."""

    def test_soft_close_extends_base_terminal(self, base_states):
        """Test soft_close extends _base_terminal."""
        state = base_states["states"]["soft_close"]
        assert state["extends"] == "_base_terminal"

    def test_soft_close_is_not_final(self, base_states):
        """Test soft_close.is_final = false."""
        state = base_states["states"]["soft_close"]
        assert state["is_final"] is False

    def test_soft_close_transitions_agreement(self, base_states):
        """Test soft_close transitions for agreement."""
        transitions = base_states["states"]["soft_close"]["transitions"]
        assert transitions["agreement"] == "{{entry_state}}"

    def test_soft_close_transitions_demo_request(self, base_states):
        """Test soft_close transitions for demo_request."""
        transitions = base_states["states"]["soft_close"]["transitions"]
        assert transitions["demo_request"] == "close"

    def test_soft_close_transitions_go_back(self, base_states):
        """Test soft_close transitions for go_back."""
        transitions = base_states["states"]["soft_close"]["transitions"]
        assert transitions["go_back"] == "greeting"


class TestBaseStatesPresentation:
    """Tests for presentation state."""

    def test_presentation_extends_base_phase(self, base_states):
        """Test presentation extends _base_phase."""
        state = base_states["states"]["presentation"]
        assert state["extends"] == "_base_phase"

    def test_presentation_goal(self, base_states):
        """Test presentation.goal."""
        state = base_states["states"]["presentation"]
        assert "goal" in state

    def test_presentation_parameters(self, base_states):
        """Test presentation.parameters."""
        state = base_states["states"]["presentation"]
        params = state["parameters"]
        assert params["default_price_action"] == "answer_with_facts"
        assert params["default_unclear_action"] == "clarify_and_continue"

    def test_presentation_transitions_agreement(self, base_states):
        """Test presentation transitions for agreement."""
        transitions = base_states["states"]["presentation"]["transitions"]
        assert transitions["agreement"] == "close"

    def test_presentation_transitions_objection_price(self, base_states):
        """Test presentation transitions for objection_price."""
        transitions = base_states["states"]["presentation"]["transitions"]
        assert transitions["objection_price"] == "handle_objection"


class TestBaseStatesHandleObjection:
    """Tests for handle_objection state."""

    def test_handle_objection_extends_base_phase(self, base_states):
        """Test handle_objection extends _base_phase."""
        state = base_states["states"]["handle_objection"]
        assert state["extends"] == "_base_phase"

    def test_handle_objection_goal(self, base_states):
        """Test handle_objection.goal."""
        state = base_states["states"]["handle_objection"]
        assert "goal" in state

    def test_handle_objection_conditional_transitions(self, base_states):
        """Test handle_objection has conditional transitions for objections."""
        transitions = base_states["states"]["handle_objection"]["transitions"]

        # objection_price should have conditional with objection_limit_reached
        objection_price = transitions["objection_price"]
        assert isinstance(objection_price, list)
        assert any(
            isinstance(t, dict) and t.get("when") == "objection_limit_reached"
            for t in objection_price
        )


class TestBaseStatesClose:
    """Tests for close state."""

    def test_close_extends_base_phase(self, base_states):
        """Test close extends _base_phase."""
        state = base_states["states"]["close"]
        assert state["extends"] == "_base_phase"

    def test_close_required_data(self, base_states):
        """Test close.required_data includes contact_info."""
        state = base_states["states"]["close"]
        assert "contact_info" in state["required_data"]

    def test_close_transitions_data_complete(self, base_states):
        """Test close transitions for data_complete."""
        transitions = base_states["states"]["close"]["transitions"]
        assert transitions["data_complete"] == "success"

    def test_close_transitions_contact_provided(self, base_states):
        """Test close transitions for contact_provided."""
        transitions = base_states["states"]["close"]["transitions"]
        assert transitions["contact_provided"] == "success"


class TestBaseStatesDefaults:
    """Tests for defaults section."""

    def test_defaults_section_exists(self, base_states):
        """Test defaults section exists."""
        assert "defaults" in base_states

    def test_defaults_entry_state(self, base_states):
        """Test defaults.entry_state."""
        assert base_states["defaults"]["entry_state"] == "greeting"


# =============================================================================
# PRIORITIES.YAML TESTS
# =============================================================================

class TestDefaultPriorities:
    """Tests for default_priorities configuration."""

    def test_default_priorities_exists(self, priorities):
        """Test default_priorities section exists."""
        assert "default_priorities" in priorities

    def test_priorities_are_sorted(self, priorities):
        """Test priorities are in ascending order by priority value."""
        prios = priorities["default_priorities"]
        prev_priority = -1
        for p in prios:
            assert p["priority"] >= prev_priority, \
                f"Priority {p['name']} ({p['priority']}) is out of order"
            prev_priority = p["priority"]


class TestPriorityFinalState:
    """Tests for final_state priority."""

    def test_final_state_priority(self, priorities):
        """Test final_state has priority 0."""
        prio = next(p for p in priorities["default_priorities"] if p["name"] == "final_state")
        assert prio["priority"] == 0

    def test_final_state_condition(self, priorities):
        """Test final_state uses is_final condition."""
        prio = next(p for p in priorities["default_priorities"] if p["name"] == "final_state")
        assert prio["condition"] == "is_final"

    def test_final_state_action(self, priorities):
        """Test final_state action."""
        prio = next(p for p in priorities["default_priorities"] if p["name"] == "final_state")
        assert prio["action"] == "final"


class TestPriorityRejection:
    """Tests for rejection priority."""

    def test_rejection_priority(self, priorities):
        """Test rejection has priority 100."""
        prio = next(p for p in priorities["default_priorities"] if p["name"] == "rejection")
        assert prio["priority"] == 100

    def test_rejection_intents(self, priorities):
        """Test rejection handles rejection intent."""
        prio = next(p for p in priorities["default_priorities"] if p["name"] == "rejection")
        assert "rejection" in prio["intents"]

    def test_rejection_uses_transitions(self, priorities):
        """Test rejection uses transitions."""
        prio = next(p for p in priorities["default_priorities"] if p["name"] == "rejection")
        assert prio["use_transitions"] is True


class TestPriorityGoBack:
    """Tests for go_back priority."""

    def test_go_back_priority(self, priorities):
        """Test go_back has priority 150."""
        prio = next(p for p in priorities["default_priorities"] if p["name"] == "go_back")
        assert prio["priority"] == 150

    def test_go_back_intents(self, priorities):
        """Test go_back handles go_back and correct_info intents."""
        prio = next(p for p in priorities["default_priorities"] if p["name"] == "go_back")
        assert "go_back" in prio["intents"]
        assert "correct_info" in prio["intents"]

    def test_go_back_feature_flag(self, priorities):
        """Test go_back requires circular_flow feature flag."""
        prio = next(p for p in priorities["default_priorities"] if p["name"] == "go_back")
        assert prio["feature_flag"] == "circular_flow"

    def test_go_back_handler(self, priorities):
        """Test go_back uses circular_flow_handler."""
        prio = next(p for p in priorities["default_priorities"] if p["name"] == "go_back")
        assert prio["handler"] == "circular_flow_handler"


class TestPriorityObjectionLimit:
    """Tests for objection_limit priority."""

    def test_objection_limit_priority(self, priorities):
        """Test objection_limit has priority 170."""
        prio = next(p for p in priorities["default_priorities"] if p["name"] == "objection_limit")
        assert prio["priority"] == 170

    def test_objection_limit_category(self, priorities):
        """Test objection_limit handles objection category."""
        prio = next(p for p in priorities["default_priorities"] if p["name"] == "objection_limit")
        assert prio["intent_category"] == "objection"

    def test_objection_limit_condition(self, priorities):
        """Test objection_limit condition."""
        prio = next(p for p in priorities["default_priorities"] if p["name"] == "objection_limit")
        assert prio["condition"] == "objection_limit_reached"

    def test_objection_limit_action(self, priorities):
        """Test objection_limit action."""
        prio = next(p for p in priorities["default_priorities"] if p["name"] == "objection_limit")
        assert prio["action"] == "transition_to_soft_close"

    def test_objection_limit_else(self, priorities):
        """Test objection_limit else clause."""
        prio = next(p for p in priorities["default_priorities"] if p["name"] == "objection_limit")
        assert prio["else"] == "use_transitions"


class TestPriorityStateRules:
    """Tests for state_rules priority."""

    def test_state_rules_priority(self, priorities):
        """Test state_rules has priority 200."""
        prio = next(p for p in priorities["default_priorities"] if p["name"] == "state_rules")
        assert prio["priority"] == 200

    def test_state_rules_source(self, priorities):
        """Test state_rules source."""
        prio = next(p for p in priorities["default_priorities"] if p["name"] == "state_rules")
        assert prio["source"] == "rules"

    def test_state_rules_use_resolver(self, priorities):
        """Test state_rules uses resolver."""
        prio = next(p for p in priorities["default_priorities"] if p["name"] == "state_rules")
        assert prio["use_resolver"] is True


class TestPriorityQuestionHandling:
    """Tests for question_handling priority."""

    def test_question_handling_priority(self, priorities):
        """Test question_handling has priority 300."""
        prio = next(p for p in priorities["default_priorities"] if p["name"] == "question_handling")
        assert prio["priority"] == 300

    def test_question_handling_category(self, priorities):
        """Test question_handling handles question category."""
        prio = next(p for p in priorities["default_priorities"] if p["name"] == "question_handling")
        assert prio["intent_category"] == "question"


class TestPriorityPhaseProgress:
    """Tests for phase_progress priority."""

    def test_phase_progress_priority(self, priorities):
        """Test phase_progress has priority 400."""
        prio = next(p for p in priorities["default_priorities"] if p["name"] == "phase_progress")
        assert prio["priority"] == 400

    def test_phase_progress_handler(self, priorities):
        """Test phase_progress uses phase_progress_handler."""
        prio = next(p for p in priorities["default_priorities"] if p["name"] == "phase_progress")
        assert prio["handler"] == "phase_progress_handler"


class TestPriorityTransitions:
    """Tests for transitions priority."""

    def test_transitions_priority(self, priorities):
        """Test transitions has priority 500."""
        prio = next(p for p in priorities["default_priorities"] if p["name"] == "transitions")
        assert prio["priority"] == 500

    def test_transitions_use_transitions(self, priorities):
        """Test transitions uses transitions."""
        prio = next(p for p in priorities["default_priorities"] if p["name"] == "transitions")
        assert prio["use_transitions"] is True


class TestPriorityDataComplete:
    """Tests for data_complete priority."""

    def test_data_complete_priority(self, priorities):
        """Test data_complete has priority 600."""
        prio = next(p for p in priorities["default_priorities"] if p["name"] == "data_complete")
        assert prio["priority"] == 600

    def test_data_complete_trigger(self, priorities):
        """Test data_complete trigger."""
        prio = next(p for p in priorities["default_priorities"] if p["name"] == "data_complete")
        assert prio["trigger"] == "data_complete"

    def test_data_complete_condition(self, priorities):
        """Test data_complete condition."""
        prio = next(p for p in priorities["default_priorities"] if p["name"] == "data_complete")
        assert prio["condition"] == "has_all_required_data"


class TestPriorityAnyTransition:
    """Tests for any_transition priority."""

    def test_any_transition_priority(self, priorities):
        """Test any_transition has priority 700."""
        prio = next(p for p in priorities["default_priorities"] if p["name"] == "any_transition")
        assert prio["priority"] == 700

    def test_any_transition_trigger(self, priorities):
        """Test any_transition trigger."""
        prio = next(p for p in priorities["default_priorities"] if p["name"] == "any_transition")
        assert prio["trigger"] == "any"


class TestPriorityDefault:
    """Tests for default priority."""

    def test_default_priority(self, priorities):
        """Test default has priority 999."""
        prio = next(p for p in priorities["default_priorities"] if p["name"] == "default")
        assert prio["priority"] == 999

    def test_default_action(self, priorities):
        """Test default action."""
        prio = next(p for p in priorities["default_priorities"] if p["name"] == "default")
        assert prio["action"] == "continue_current_goal"


class TestAlternativePriorities:
    """Tests for alternative priority profiles."""

    def test_aggressive_priorities_exists(self, priorities):
        """Test aggressive_priorities section exists."""
        assert "aggressive_priorities" in priorities

    def test_aggressive_extends_default(self, priorities):
        """Test aggressive_priorities extends default_priorities."""
        assert priorities["aggressive_priorities"]["extends"] == "default_priorities"

    def test_aggressive_overrides_phase_progress(self, priorities):
        """Test aggressive_priorities overrides phase_progress priority."""
        overrides = priorities["aggressive_priorities"]["overrides"]
        phase_override = next(o for o in overrides if o["name"] == "phase_progress")
        assert phase_override["priority"] == 250

    def test_support_priorities_exists(self, priorities):
        """Test support_priorities section exists."""
        assert "support_priorities" in priorities

    def test_support_priorities_urgent_escalation(self, priorities):
        """Test support_priorities has urgent_escalation."""
        support = priorities["support_priorities"]
        urgent = next(p for p in support if p["name"] == "urgent_escalation")
        assert urgent["priority"] == 50
        assert urgent["condition"] == "is_urgent"
        assert urgent["action"] == "escalate_to_human"


# =============================================================================
# MIXINS.YAML TESTS
# =============================================================================

class TestMixinsPriceHandling:
    """Tests for price_handling mixin."""

    def test_mixins_section_exists(self, mixins):
        """Test mixins section exists."""
        assert "mixins" in mixins

    def test_price_handling_exists(self, mixins):
        """Test price_handling mixin exists."""
        assert "price_handling" in mixins["mixins"]

    def test_price_handling_description(self, mixins):
        """Test price_handling has description."""
        mixin = mixins["mixins"]["price_handling"]
        assert "description" in mixin

    def test_price_handling_rules_price_question(self, mixins):
        """Test price_handling rules for price_question."""
        rules = mixins["mixins"]["price_handling"]["rules"]
        assert "price_question" in rules
        # Should have conditional rules
        assert isinstance(rules["price_question"], list)

    def test_price_handling_rules_pricing_details(self, mixins):
        """Test price_handling rules for pricing_details."""
        rules = mixins["mixins"]["price_handling"]["rules"]
        assert "pricing_details" in rules


class TestMixinsProductQuestions:
    """Tests for product_questions mixin."""

    def test_product_questions_exists(self, mixins):
        """Test product_questions mixin exists."""
        assert "product_questions" in mixins["mixins"]

    def test_product_questions_rules_features(self, mixins):
        """Test product_questions rules for question_features."""
        rules = mixins["mixins"]["product_questions"]["rules"]
        assert rules["question_features"] == "answer_and_continue"

    def test_product_questions_rules_integrations(self, mixins):
        """Test product_questions rules for question_integrations."""
        rules = mixins["mixins"]["product_questions"]["rules"]
        assert rules["question_integrations"] == "answer_and_continue"

    def test_product_questions_rules_comparison(self, mixins):
        """Test product_questions rules for comparison."""
        rules = mixins["mixins"]["product_questions"]["rules"]
        assert rules["comparison"] == "answer_and_continue"

    def test_product_questions_rules_consultation(self, mixins):
        """Test product_questions rules for consultation_request."""
        rules = mixins["mixins"]["product_questions"]["rules"]
        assert rules["consultation_request"] == "acknowledge_and_continue"


class TestMixinsObjectionHandling:
    """Tests for objection_handling mixin."""

    def test_objection_handling_exists(self, mixins):
        """Test objection_handling mixin exists."""
        assert "objection_handling" in mixins["mixins"]

    def test_objection_handling_transitions_price(self, mixins):
        """Test objection_handling transitions for objection_price.

        FIX: Now uses conditional rules - handle_objection by default.
        """
        transitions = mixins["mixins"]["objection_handling"]["transitions"]
        # New format: list with conditional rule
        assert isinstance(transitions["objection_price"], list)
        assert transitions["objection_price"][-1] == "handle_objection"

    def test_objection_handling_transitions_competitor(self, mixins):
        """Test objection_handling transitions for objection_competitor.

        FIX: Now uses conditional rules - handle_objection by default.
        """
        transitions = mixins["mixins"]["objection_handling"]["transitions"]
        assert isinstance(transitions["objection_competitor"], list)
        assert transitions["objection_competitor"][-1] == "handle_objection"

    def test_objection_handling_transitions_no_time(self, mixins):
        """Test objection_handling transitions for objection_no_time.

        FIX: Now uses conditional rules - handle_objection by default,
        soft_close only when objection_limit_reached.
        """
        transitions = mixins["mixins"]["objection_handling"]["transitions"]
        assert isinstance(transitions["objection_no_time"], list)
        assert transitions["objection_no_time"][-1] == "handle_objection"

    def test_objection_handling_transitions_think(self, mixins):
        """Test objection_handling transitions for objection_think.

        FIX: Now uses conditional rules - handle_objection by default,
        soft_close only when objection_limit_reached.
        """
        transitions = mixins["mixins"]["objection_handling"]["transitions"]
        assert isinstance(transitions["objection_think"], list)
        assert transitions["objection_think"][-1] == "handle_objection"


class TestMixinsDialogueRepair:
    """Tests for dialogue_repair mixin."""

    def test_dialogue_repair_exists(self, mixins):
        """Test dialogue_repair mixin exists."""
        assert "dialogue_repair" in mixins["mixins"]

    def test_dialogue_repair_rules_unclear(self, mixins):
        """Test dialogue_repair rules for unclear."""
        rules = mixins["mixins"]["dialogue_repair"]["rules"]
        assert "unclear" in rules
        # Should have conditional rules
        assert isinstance(rules["unclear"], list)


class TestMixinsExitIntents:
    """Tests for exit_intents mixin."""

    def test_exit_intents_exists(self, mixins):
        """Test exit_intents mixin exists."""
        assert "exit_intents" in mixins["mixins"]

    def test_exit_intents_transitions_rejection(self, mixins):
        """Test exit_intents transitions for rejection."""
        transitions = mixins["mixins"]["exit_intents"]["transitions"]
        assert transitions["rejection"] == "soft_close"

    def test_exit_intents_transitions_farewell(self, mixins):
        """Test exit_intents transitions for farewell."""
        transitions = mixins["mixins"]["exit_intents"]["transitions"]
        assert transitions["farewell"] == "soft_close"


class TestMixinsCloseShortcuts:
    """Tests for close_shortcuts mixin."""

    def test_close_shortcuts_exists(self, mixins):
        """Test close_shortcuts mixin exists."""
        assert "close_shortcuts" in mixins["mixins"]

    def test_close_shortcuts_transitions_demo(self, mixins):
        """Test close_shortcuts transitions for demo_request."""
        transitions = mixins["mixins"]["close_shortcuts"]["transitions"]
        assert transitions["demo_request"] == "close"

    def test_close_shortcuts_transitions_callback(self, mixins):
        """Test close_shortcuts transitions for callback_request."""
        transitions = mixins["mixins"]["close_shortcuts"]["transitions"]
        assert transitions["callback_request"] == "close"


class TestMixinsSocialIntents:
    """Tests for social_intents mixin."""

    def test_social_intents_exists(self, mixins):
        """Test social_intents mixin exists."""
        assert "social_intents" in mixins["mixins"]

    def test_social_intents_rules_gratitude(self, mixins):
        """Test social_intents rules for gratitude."""
        rules = mixins["mixins"]["social_intents"]["rules"]
        assert rules["gratitude"] == "acknowledge_and_continue"

    def test_social_intents_rules_small_talk(self, mixins):
        """Test social_intents rules for small_talk."""
        rules = mixins["mixins"]["social_intents"]["rules"]
        assert rules["small_talk"] == "small_talk_and_continue"


class TestMixinsSpinCommon:
    """Tests for spin_common mixin."""

    def test_spin_common_exists(self, mixins):
        """Test spin_common mixin exists."""
        assert "spin_common" in mixins["mixins"]

    def test_spin_common_includes_all_mixins(self, mixins):
        """Test spin_common includes all required mixins."""
        includes = mixins["mixins"]["spin_common"]["includes"]
        assert "price_handling" in includes
        assert "product_questions" in includes
        assert "objection_handling" in includes
        assert "dialogue_repair" in includes
        assert "exit_intents" in includes
        assert "close_shortcuts" in includes
        assert "social_intents" in includes


class TestMixinsDefaults:
    """Tests for mixins defaults section."""

    def test_defaults_section_exists(self, mixins):
        """Test defaults section exists."""
        assert "defaults" in mixins

    def test_default_price_action(self, mixins):
        """Test defaults.default_price_action."""
        assert mixins["defaults"]["default_price_action"] == "deflect_and_continue"

    def test_default_unclear_action(self, mixins):
        """Test defaults.default_unclear_action."""
        assert mixins["defaults"]["default_unclear_action"] == "continue_current_goal"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
