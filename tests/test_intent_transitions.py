"""
Тесты для проверки переходов по интентам в FlowConfig

Проверяем что все интенты корректно обрабатываются
в состояниях SPIN Selling flow и не пропущены.

Использует FlowConfig (модульный YAML) вместо deprecated StateMachine.

Критические интенты:
- demo_request
- callback_request
- consultation_request
- objection_no_time
- objection_think
- farewell
- comparison
- pricing_details
"""

import pytest
import sys
sys.path.insert(0, 'src')

from config_loader import ConfigLoader
from config import QUESTION_INTENTS


@pytest.fixture(scope="module")
def spin_flow():
    """Load SPIN Selling flow config."""
    loader = ConfigLoader()
    return loader.load_flow("spin_selling")


@pytest.fixture(scope="module")
def spin_states(spin_flow):
    """Get all resolved states from SPIN flow."""
    return spin_flow.states


def _get_transition_target(transitions, intent):
    """Extract target state from transition (handles conditional rules)."""
    target = transitions.get(intent)
    if target is None:
        return None
    if isinstance(target, str):
        return target
    if isinstance(target, list):
        # Conditional: last item is default fallback
        return target[-1] if isinstance(target[-1], str) else target[-1].get("then")
    return None


def _has_rule(rules, intent):
    """Check if intent has a rule mapping."""
    return intent in rules


class TestGreetingTransitions:
    """Тесты переходов из состояния greeting"""

    def test_demo_request_goes_to_close(self, spin_states):
        """demo_request из greeting -> close"""
        t = spin_states["greeting"]["transitions"]
        assert _get_transition_target(t, "demo_request") == "close"

    def test_callback_request_goes_to_close(self, spin_states):
        """callback_request из greeting -> close"""
        t = spin_states["greeting"]["transitions"]
        assert _get_transition_target(t, "callback_request") == "close"

    def test_consultation_request_goes_to_entry_state(self, spin_states):
        """consultation_request из greeting -> entry_state (spin_situation)"""
        t = spin_states["greeting"]["transitions"]
        assert _get_transition_target(t, "consultation_request") == "spin_situation"

    def test_farewell_goes_to_soft_close(self, spin_states):
        """farewell из greeting -> soft_close"""
        t = spin_states["greeting"]["transitions"]
        assert _get_transition_target(t, "farewell") == "soft_close"

    def test_objection_no_time_goes_to_handle_objection(self, spin_states):
        """objection_no_time из greeting -> handle_objection (conditional)"""
        t = spin_states["greeting"]["transitions"]
        assert _get_transition_target(t, "objection_no_time") == "handle_objection"

    def test_objection_think_goes_to_handle_objection(self, spin_states):
        """objection_think из greeting -> handle_objection (conditional)"""
        t = spin_states["greeting"]["transitions"]
        assert _get_transition_target(t, "objection_think") == "handle_objection"

    def test_comparison_goes_to_entry_state(self, spin_states):
        """comparison из greeting -> spin_situation (transition)"""
        t = spin_states["greeting"]["transitions"]
        assert _get_transition_target(t, "comparison") == "spin_situation"

    def test_pricing_details_has_transition(self, spin_states):
        """pricing_details из greeting -> spin_situation (transition)"""
        t = spin_states["greeting"]["transitions"]
        assert _get_transition_target(t, "pricing_details") == "spin_situation"

    def test_pricing_details_has_rule(self, spin_states):
        """pricing_details обрабатывается через rule answer_with_pricing"""
        r = spin_states["greeting"]["rules"]
        assert r.get("pricing_details") == "answer_with_pricing"


class TestSpinSituationTransitions:
    """Тесты переходов из состояния spin_situation"""

    def test_demo_request_goes_to_close(self, spin_states):
        """demo_request из spin_situation -> close"""
        t = spin_states["spin_situation"]["transitions"]
        assert _get_transition_target(t, "demo_request") == "close"

    def test_callback_request_goes_to_close(self, spin_states):
        """callback_request из spin_situation -> close"""
        t = spin_states["spin_situation"]["transitions"]
        assert _get_transition_target(t, "callback_request") == "close"

    def test_farewell_goes_to_soft_close(self, spin_states):
        """farewell из spin_situation -> soft_close"""
        t = spin_states["spin_situation"]["transitions"]
        assert _get_transition_target(t, "farewell") == "soft_close"

    def test_objection_no_time_goes_to_handle_objection(self, spin_states):
        """objection_no_time -> handle_objection"""
        t = spin_states["spin_situation"]["transitions"]
        assert _get_transition_target(t, "objection_no_time") == "handle_objection"

    def test_objection_think_goes_to_handle_objection(self, spin_states):
        """objection_think -> handle_objection"""
        t = spin_states["spin_situation"]["transitions"]
        assert _get_transition_target(t, "objection_think") == "handle_objection"

    def test_comparison_handled_by_rule(self, spin_states):
        """comparison в spin_situation обрабатывается через rules"""
        r = spin_states["spin_situation"]["rules"]
        assert _has_rule(r, "comparison")

    def test_pricing_details_has_rule(self, spin_states):
        """pricing_details обрабатывается через rule (conditional or direct)"""
        r = spin_states["spin_situation"]["rules"]
        rule = r.get("pricing_details")
        assert rule is not None
        # Can be direct string or conditional list with answer_with_pricing fallback
        if isinstance(rule, list):
            assert rule[-1] == "answer_with_pricing"
        else:
            assert rule == "answer_with_pricing"

    def test_consultation_request_has_rule(self, spin_states):
        """consultation_request обрабатывается через rules"""
        r = spin_states["spin_situation"]["rules"]
        assert _has_rule(r, "consultation_request")


class TestSpinProblemTransitions:
    """Тесты переходов из состояния spin_problem"""

    def test_demo_request_goes_to_close(self, spin_states):
        t = spin_states["spin_problem"]["transitions"]
        assert _get_transition_target(t, "demo_request") == "close"

    def test_callback_request_goes_to_close(self, spin_states):
        t = spin_states["spin_problem"]["transitions"]
        assert _get_transition_target(t, "callback_request") == "close"

    def test_farewell_goes_to_soft_close(self, spin_states):
        t = spin_states["spin_problem"]["transitions"]
        assert _get_transition_target(t, "farewell") == "soft_close"

    def test_objection_no_time_goes_to_handle_objection(self, spin_states):
        t = spin_states["spin_problem"]["transitions"]
        assert _get_transition_target(t, "objection_no_time") == "handle_objection"

    def test_objection_think_goes_to_handle_objection(self, spin_states):
        t = spin_states["spin_problem"]["transitions"]
        assert _get_transition_target(t, "objection_think") == "handle_objection"


class TestSpinImplicationTransitions:
    """Тесты переходов из состояния spin_implication"""

    def test_demo_request_goes_to_close(self, spin_states):
        t = spin_states["spin_implication"]["transitions"]
        assert _get_transition_target(t, "demo_request") == "close"

    def test_callback_request_goes_to_close(self, spin_states):
        t = spin_states["spin_implication"]["transitions"]
        assert _get_transition_target(t, "callback_request") == "close"

    def test_farewell_goes_to_soft_close(self, spin_states):
        t = spin_states["spin_implication"]["transitions"]
        assert _get_transition_target(t, "farewell") == "soft_close"

    def test_objection_no_time_goes_to_handle_objection(self, spin_states):
        t = spin_states["spin_implication"]["transitions"]
        assert _get_transition_target(t, "objection_no_time") == "handle_objection"


class TestSpinNeedPayoffTransitions:
    """Тесты переходов из состояния spin_need_payoff"""

    def test_demo_request_goes_to_close(self, spin_states):
        t = spin_states["spin_need_payoff"]["transitions"]
        assert _get_transition_target(t, "demo_request") == "close"

    def test_callback_request_goes_to_close(self, spin_states):
        t = spin_states["spin_need_payoff"]["transitions"]
        assert _get_transition_target(t, "callback_request") == "close"

    def test_farewell_goes_to_soft_close(self, spin_states):
        t = spin_states["spin_need_payoff"]["transitions"]
        assert _get_transition_target(t, "farewell") == "soft_close"

    def test_objection_no_time_goes_to_handle_objection(self, spin_states):
        t = spin_states["spin_need_payoff"]["transitions"]
        assert _get_transition_target(t, "objection_no_time") == "handle_objection"


class TestPresentationTransitions:
    """Тесты переходов из состояния presentation"""

    def test_demo_request_goes_to_close(self, spin_states):
        t = spin_states["presentation"]["transitions"]
        assert _get_transition_target(t, "demo_request") == "close"

    def test_callback_request_goes_to_close(self, spin_states):
        t = spin_states["presentation"]["transitions"]
        assert _get_transition_target(t, "callback_request") == "close"

    def test_farewell_goes_to_soft_close(self, spin_states):
        t = spin_states["presentation"]["transitions"]
        assert _get_transition_target(t, "farewell") == "soft_close"

    def test_objection_no_time_goes_to_handle_objection(self, spin_states):
        t = spin_states["presentation"]["transitions"]
        assert _get_transition_target(t, "objection_no_time") == "handle_objection"

    def test_objection_think_goes_to_handle_objection(self, spin_states):
        t = spin_states["presentation"]["transitions"]
        assert _get_transition_target(t, "objection_think") == "handle_objection"

    def test_objection_competitor_goes_to_handle_objection(self, spin_states):
        t = spin_states["presentation"]["transitions"]
        assert _get_transition_target(t, "objection_competitor") == "handle_objection"

    def test_comparison_handled_by_rule(self, spin_states):
        """comparison в presentation обрабатывается через rules"""
        r = spin_states["presentation"]["rules"]
        assert r.get("comparison") == "answer_with_facts"

    def test_pricing_details_has_rule(self, spin_states):
        """pricing_details -> answer_with_pricing (conditional or direct)"""
        r = spin_states["presentation"]["rules"]
        rule = r.get("pricing_details")
        assert rule is not None
        if isinstance(rule, list):
            assert rule[-1] == "answer_with_pricing"
        else:
            assert rule == "answer_with_pricing"


class TestHandleObjectionTransitions:
    """Тесты переходов из состояния handle_objection"""

    def test_demo_request_goes_to_close(self, spin_states):
        t = spin_states["handle_objection"]["transitions"]
        assert _get_transition_target(t, "demo_request") == "close"

    def test_callback_request_goes_to_close(self, spin_states):
        t = spin_states["handle_objection"]["transitions"]
        assert _get_transition_target(t, "callback_request") == "close"

    def test_farewell_goes_to_soft_close(self, spin_states):
        t = spin_states["handle_objection"]["transitions"]
        assert _get_transition_target(t, "farewell") == "soft_close"

    def test_agreement_goes_to_presentation(self, spin_states):
        """agreement из handle_objection -> presentation (return state)"""
        t = spin_states["handle_objection"]["transitions"]
        target = _get_transition_target(t, "agreement")
        # agreement can go to presentation or close depending on conditional
        assert target in ("presentation", "close")

    def test_objection_no_time_goes_to_handle_objection(self, spin_states):
        """objection_no_time в handle_objection -> stays or soft_close"""
        t = spin_states["handle_objection"]["transitions"]
        target = _get_transition_target(t, "objection_no_time")
        assert target == "handle_objection"

    def test_objection_think_goes_to_handle_objection(self, spin_states):
        t = spin_states["handle_objection"]["transitions"]
        target = _get_transition_target(t, "objection_think")
        assert target == "handle_objection"

    def test_objection_price_goes_to_handle_objection(self, spin_states):
        t = spin_states["handle_objection"]["transitions"]
        target = _get_transition_target(t, "objection_price")
        assert target == "handle_objection"


class TestCloseTransitions:
    """Тесты переходов из состояния close"""

    def test_farewell_goes_to_soft_close(self, spin_states):
        t = spin_states["close"]["transitions"]
        assert _get_transition_target(t, "farewell") == "soft_close"

    def test_rejection_goes_to_soft_close(self, spin_states):
        t = spin_states["close"]["transitions"]
        assert _get_transition_target(t, "rejection") == "soft_close"

    def test_objection_price_goes_to_handle_objection(self, spin_states):
        t = spin_states["close"]["transitions"]
        assert _get_transition_target(t, "objection_price") == "handle_objection"

    def test_objection_no_time_goes_to_handle_objection(self, spin_states):
        t = spin_states["close"]["transitions"]
        assert _get_transition_target(t, "objection_no_time") == "handle_objection"

    def test_objection_think_goes_to_handle_objection(self, spin_states):
        t = spin_states["close"]["transitions"]
        assert _get_transition_target(t, "objection_think") == "handle_objection"

    def test_contact_provided_goes_to_success(self, spin_states):
        """contact_provided в close -> success"""
        t = spin_states["close"]["transitions"]
        assert _get_transition_target(t, "contact_provided") == "success"

    def test_demo_request_transition(self, spin_states):
        """demo_request в close -> success (conditional) or close"""
        t = spin_states["close"]["transitions"]
        target = t.get("demo_request")
        # Conditional: ready_for_close → success, default → close (stay)
        assert target is not None

    def test_callback_request_transition(self, spin_states):
        """callback_request в close -> success (conditional) or close"""
        t = spin_states["close"]["transitions"]
        target = t.get("callback_request")
        assert target is not None


class TestQuestionIntentsConfig:
    """Тесты что QUESTION_INTENTS правильно настроены"""

    def test_comparison_in_question_intents(self):
        assert "comparison" in QUESTION_INTENTS

    def test_pricing_details_in_question_intents(self):
        assert "pricing_details" in QUESTION_INTENTS

    def test_question_features_in_question_intents(self):
        assert "question_features" in QUESTION_INTENTS

    def test_question_integrations_in_question_intents(self):
        assert "question_integrations" in QUESTION_INTENTS

    def test_price_question_in_question_intents(self):
        assert "price_question" in QUESTION_INTENTS


class TestAllStatesHaveRequiredTransitions:
    """Тесты что все состояния имеют необходимые переходы"""

    @pytest.mark.parametrize("state", [
        "greeting", "spin_situation", "spin_problem",
        "spin_implication", "spin_need_payoff"
    ])
    def test_early_states_have_demo_request_transition(self, state, spin_states):
        """Все ранние состояния имеют переход для demo_request"""
        t = spin_states[state]["transitions"]
        assert "demo_request" in t
        assert _get_transition_target(t, "demo_request") == "close"

    @pytest.mark.parametrize("state", [
        "greeting", "spin_situation", "spin_problem",
        "spin_implication", "spin_need_payoff"
    ])
    def test_early_states_have_callback_request_transition(self, state, spin_states):
        """Все ранние состояния имеют переход для callback_request"""
        t = spin_states[state]["transitions"]
        assert "callback_request" in t
        assert _get_transition_target(t, "callback_request") == "close"

    @pytest.mark.parametrize("state", [
        "greeting", "spin_situation", "spin_problem",
        "spin_implication", "spin_need_payoff", "presentation",
        "handle_objection", "close"
    ])
    def test_states_have_farewell_transition(self, state, spin_states):
        """Все состояния имеют переход для farewell"""
        t = spin_states[state]["transitions"]
        assert "farewell" in t
        assert _get_transition_target(t, "farewell") == "soft_close"

    @pytest.mark.parametrize("state", [
        "spin_situation", "spin_problem", "spin_implication",
        "spin_need_payoff", "presentation"
    ])
    def test_spin_and_presentation_states_handle_comparison(self, state, spin_states):
        """SPIN и presentation обрабатывают comparison через rules"""
        r = spin_states[state].get("rules", {})
        assert "comparison" in r


class TestCriticalIntentsCoverage:
    """Тесты что критические интенты НЕ пропущены ни в rules, ни в transitions"""

    critical_intents = [
        "demo_request",
        "callback_request",
        "farewell",
        "comparison",
        "pricing_details",
    ]

    @pytest.mark.parametrize("intent", critical_intents)
    def test_greeting_handles_critical_intents(self, intent, spin_states):
        """greeting имеет обработку для критических интентов"""
        state = spin_states["greeting"]
        has_transition = intent in state.get("transitions", {})
        has_rule = intent in state.get("rules", {})
        assert has_transition or has_rule, \
            f"Intent {intent} не обработан в greeting (ни transition, ни rule)"

    @pytest.mark.parametrize("intent", critical_intents)
    def test_spin_situation_handles_critical_intents(self, intent, spin_states):
        """spin_situation имеет обработку для критических интентов"""
        state = spin_states["spin_situation"]
        has_transition = intent in state.get("transitions", {})
        has_rule = intent in state.get("rules", {})
        assert has_transition or has_rule, \
            f"Intent {intent} не обработан в spin_situation"

    @pytest.mark.parametrize("intent", critical_intents)
    def test_presentation_handles_critical_intents(self, intent, spin_states):
        """presentation имеет обработку для критических интентов"""
        state = spin_states["presentation"]
        has_transition = intent in state.get("transitions", {})
        has_rule = intent in state.get("rules", {})
        assert has_transition or has_rule, \
            f"Intent {intent} не обработан в presentation"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
