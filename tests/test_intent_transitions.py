"""
Тесты для проверки переходов по интентам в StateMachine

Проверяем что все интенты из patterns.py корректно обрабатываются
в SALES_STATES и не приводят к continue_current_goal когда нужен переход.

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

from state_machine import StateMachine
from config import SALES_STATES, QUESTION_INTENTS


class TestGreetingTransitions:
    """Тесты переходов из состояния greeting"""

    def setup_method(self):
        self.sm = StateMachine()
        assert self.sm.state == "greeting"

    def test_demo_request_goes_to_close(self):
        """demo_request из greeting -> close"""
        result = self.sm.process("demo_request", {})
        assert result["next_state"] == "close"
        assert result["action"] == "transition_to_close"

    def test_callback_request_goes_to_close(self):
        """callback_request из greeting -> close"""
        result = self.sm.process("callback_request", {})
        assert result["next_state"] == "close"
        assert result["action"] == "transition_to_close"

    def test_consultation_request_goes_to_spin_situation(self):
        """consultation_request из greeting -> spin_situation (через answer_question)"""
        result = self.sm.process("consultation_request", {})
        assert result["next_state"] == "spin_situation"
        # consultation_request в QUESTION_INTENTS, поэтому action = answer_question
        assert result["action"] == "answer_question"

    def test_farewell_goes_to_soft_close(self):
        """farewell из greeting -> soft_close"""
        result = self.sm.process("farewell", {})
        assert result["next_state"] == "soft_close"
        assert result["is_final"] == True

    def test_objection_no_time_goes_to_soft_close(self):
        """objection_no_time из greeting -> soft_close"""
        result = self.sm.process("objection_no_time", {})
        assert result["next_state"] == "soft_close"
        assert result["is_final"] == True

    def test_objection_think_goes_to_soft_close(self):
        """objection_think из greeting -> soft_close"""
        result = self.sm.process("objection_think", {})
        assert result["next_state"] == "soft_close"
        assert result["is_final"] == True

    def test_comparison_goes_to_spin_situation(self):
        """comparison из greeting -> spin_situation (через answer_question)"""
        result = self.sm.process("comparison", {})
        assert result["next_state"] == "spin_situation"
        # comparison в QUESTION_INTENTS, поэтому action = answer_question
        assert result["action"] == "answer_question"

    def test_pricing_details_goes_to_spin_situation(self):
        """pricing_details из greeting -> spin_situation (через answer_question)"""
        result = self.sm.process("pricing_details", {})
        assert result["next_state"] == "spin_situation"
        # pricing_details в QUESTION_INTENTS, поэтому action = answer_question
        assert result["action"] == "answer_question"


class TestSpinSituationTransitions:
    """Тесты переходов из состояния spin_situation"""

    def setup_method(self):
        self.sm = StateMachine()
        self.sm.process("agreement", {})  # Переход в spin_situation
        assert self.sm.state == "spin_situation"

    def test_demo_request_goes_to_close(self):
        """demo_request из spin_situation -> close"""
        result = self.sm.process("demo_request", {})
        assert result["next_state"] == "close"
        assert result["action"] == "transition_to_close"

    def test_callback_request_goes_to_close(self):
        """callback_request из spin_situation -> close"""
        result = self.sm.process("callback_request", {})
        assert result["next_state"] == "close"
        assert result["action"] == "transition_to_close"

    def test_farewell_goes_to_soft_close(self):
        """farewell из spin_situation -> soft_close"""
        result = self.sm.process("farewell", {})
        assert result["next_state"] == "soft_close"
        assert result["is_final"] == True

    def test_objection_no_time_goes_to_soft_close(self):
        """objection_no_time из spin_situation -> soft_close"""
        result = self.sm.process("objection_no_time", {})
        assert result["next_state"] == "soft_close"
        assert result["is_final"] == True

    def test_objection_think_goes_to_soft_close(self):
        """objection_think из spin_situation -> soft_close"""
        result = self.sm.process("objection_think", {})
        assert result["next_state"] == "soft_close"
        assert result["is_final"] == True

    def test_comparison_stays_with_answer_and_continue(self):
        """comparison в spin_situation обрабатывается через rules"""
        result = self.sm.process("comparison", {})
        # comparison в rules -> answer_and_continue, остаёмся в том же состоянии
        assert result["next_state"] == "spin_situation"
        assert result["action"] == "answer_and_continue"

    def test_pricing_details_stays_with_deflect(self):
        """pricing_details в spin_situation обрабатывается через rules"""
        result = self.sm.process("pricing_details", {})
        assert result["next_state"] == "spin_situation"
        assert result["action"] == "deflect_and_continue"

    def test_consultation_request_stays_with_acknowledge(self):
        """consultation_request в spin_situation обрабатывается через rules"""
        result = self.sm.process("consultation_request", {})
        assert result["next_state"] == "spin_situation"
        assert result["action"] == "acknowledge_and_continue"


class TestSpinProblemTransitions:
    """Тесты переходов из состояния spin_problem"""

    def setup_method(self):
        self.sm = StateMachine()
        self.sm.process("agreement", {})
        self.sm.process("info_provided", {"company_size": 10})
        assert self.sm.state == "spin_problem"

    def test_demo_request_goes_to_close(self):
        """demo_request из spin_problem -> close"""
        result = self.sm.process("demo_request", {})
        assert result["next_state"] == "close"

    def test_callback_request_goes_to_close(self):
        """callback_request из spin_problem -> close"""
        result = self.sm.process("callback_request", {})
        assert result["next_state"] == "close"

    def test_farewell_goes_to_soft_close(self):
        """farewell из spin_problem -> soft_close"""
        result = self.sm.process("farewell", {})
        assert result["next_state"] == "soft_close"
        assert result["is_final"] == True

    def test_objection_no_time_goes_to_soft_close(self):
        """objection_no_time из spin_problem -> soft_close"""
        result = self.sm.process("objection_no_time", {})
        assert result["next_state"] == "soft_close"

    def test_objection_think_goes_to_soft_close(self):
        """objection_think из spin_problem -> soft_close"""
        result = self.sm.process("objection_think", {})
        assert result["next_state"] == "soft_close"


class TestSpinImplicationTransitions:
    """Тесты переходов из состояния spin_implication"""

    def setup_method(self):
        self.sm = StateMachine()
        self.sm.process("agreement", {})
        self.sm.process("info_provided", {"company_size": 10})
        self.sm.process("info_provided", {"pain_point": "теряем клиентов"})
        assert self.sm.state == "spin_implication"

    def test_demo_request_goes_to_close(self):
        """demo_request из spin_implication -> close"""
        result = self.sm.process("demo_request", {})
        assert result["next_state"] == "close"

    def test_callback_request_goes_to_close(self):
        """callback_request из spin_implication -> close"""
        result = self.sm.process("callback_request", {})
        assert result["next_state"] == "close"

    def test_farewell_goes_to_soft_close(self):
        """farewell из spin_implication -> soft_close"""
        result = self.sm.process("farewell", {})
        assert result["next_state"] == "soft_close"

    def test_objection_no_time_goes_to_soft_close(self):
        """objection_no_time из spin_implication -> soft_close"""
        result = self.sm.process("objection_no_time", {})
        assert result["next_state"] == "soft_close"


class TestSpinNeedPayoffTransitions:
    """Тесты переходов из состояния spin_need_payoff"""

    def setup_method(self):
        self.sm = StateMachine()
        self.sm.process("agreement", {})
        self.sm.process("info_provided", {"company_size": 10})
        self.sm.process("info_provided", {"pain_point": "теряем клиентов"})
        self.sm.process("agreement", {})
        assert self.sm.state == "spin_need_payoff"

    def test_demo_request_goes_to_close(self):
        """demo_request из spin_need_payoff -> close"""
        result = self.sm.process("demo_request", {})
        assert result["next_state"] == "close"

    def test_callback_request_goes_to_close(self):
        """callback_request из spin_need_payoff -> close"""
        result = self.sm.process("callback_request", {})
        assert result["next_state"] == "close"

    def test_farewell_goes_to_soft_close(self):
        """farewell из spin_need_payoff -> soft_close"""
        result = self.sm.process("farewell", {})
        assert result["next_state"] == "soft_close"

    def test_objection_no_time_goes_to_soft_close(self):
        """objection_no_time из spin_need_payoff -> soft_close"""
        result = self.sm.process("objection_no_time", {})
        assert result["next_state"] == "soft_close"


class TestPresentationTransitions:
    """Тесты переходов из состояния presentation"""

    def setup_method(self):
        self.sm = StateMachine()
        self.sm.process("agreement", {})
        self.sm.process("info_provided", {"company_size": 10})
        self.sm.process("info_provided", {"pain_point": "теряем клиентов"})
        self.sm.process("agreement", {})
        self.sm.process("agreement", {})
        assert self.sm.state == "presentation"

    def test_demo_request_goes_to_close(self):
        """demo_request из presentation -> close"""
        result = self.sm.process("demo_request", {})
        assert result["next_state"] == "close"

    def test_callback_request_goes_to_close(self):
        """callback_request из presentation -> close"""
        result = self.sm.process("callback_request", {})
        assert result["next_state"] == "close"

    def test_farewell_goes_to_soft_close(self):
        """farewell из presentation -> soft_close"""
        result = self.sm.process("farewell", {})
        assert result["next_state"] == "soft_close"

    def test_objection_no_time_goes_to_handle_objection(self):
        """objection_no_time из presentation -> handle_objection"""
        result = self.sm.process("objection_no_time", {})
        assert result["next_state"] == "handle_objection"

    def test_objection_think_goes_to_handle_objection(self):
        """objection_think из presentation -> handle_objection"""
        result = self.sm.process("objection_think", {})
        assert result["next_state"] == "handle_objection"

    def test_objection_competitor_goes_to_handle_objection(self):
        """objection_competitor из presentation -> handle_objection"""
        result = self.sm.process("objection_competitor", {})
        assert result["next_state"] == "handle_objection"

    def test_comparison_stays_with_answer_and_continue(self):
        """comparison в presentation обрабатывается через rules"""
        result = self.sm.process("comparison", {})
        assert result["next_state"] == "presentation"
        assert result["action"] == "answer_and_continue"

    def test_pricing_details_stays_with_answer_with_facts(self):
        """pricing_details в presentation обрабатывается через rules"""
        result = self.sm.process("pricing_details", {})
        assert result["next_state"] == "presentation"
        assert result["action"] == "answer_with_facts"


class TestHandleObjectionTransitions:
    """Тесты переходов из состояния handle_objection"""

    def setup_method(self):
        self.sm = StateMachine()
        self.sm.state = "handle_objection"

    def test_demo_request_goes_to_close(self):
        """demo_request из handle_objection -> close"""
        result = self.sm.process("demo_request", {})
        assert result["next_state"] == "close"

    def test_callback_request_goes_to_close(self):
        """callback_request из handle_objection -> close"""
        result = self.sm.process("callback_request", {})
        assert result["next_state"] == "close"

    def test_farewell_goes_to_soft_close(self):
        """farewell из handle_objection -> soft_close"""
        result = self.sm.process("farewell", {})
        assert result["next_state"] == "soft_close"

    def test_agreement_goes_to_close(self):
        """agreement из handle_objection -> close"""
        result = self.sm.process("agreement", {})
        assert result["next_state"] == "close"

    def test_objection_no_time_stays_in_handle_objection(self):
        """objection_no_time в handle_objection остаётся"""
        result = self.sm.process("objection_no_time", {})
        assert result["next_state"] == "handle_objection"

    def test_objection_think_stays_in_handle_objection(self):
        """objection_think в handle_objection остаётся"""
        result = self.sm.process("objection_think", {})
        assert result["next_state"] == "handle_objection"

    def test_objection_price_stays_in_handle_objection(self):
        """objection_price в handle_objection остаётся"""
        result = self.sm.process("objection_price", {})
        assert result["next_state"] == "handle_objection"


class TestCloseTransitions:
    """Тесты переходов из состояния close"""

    def setup_method(self):
        self.sm = StateMachine()
        self.sm.state = "close"

    def test_farewell_goes_to_soft_close(self):
        """farewell из close -> soft_close"""
        result = self.sm.process("farewell", {})
        assert result["next_state"] == "soft_close"

    def test_rejection_goes_to_soft_close(self):
        """rejection из close -> soft_close"""
        result = self.sm.process("rejection", {})
        assert result["next_state"] == "soft_close"

    def test_objection_price_goes_to_handle_objection(self):
        """objection_price из close -> handle_objection"""
        result = self.sm.process("objection_price", {})
        assert result["next_state"] == "handle_objection"

    def test_objection_no_time_goes_to_handle_objection(self):
        """objection_no_time из close -> handle_objection"""
        result = self.sm.process("objection_no_time", {})
        assert result["next_state"] == "handle_objection"

    def test_objection_think_goes_to_handle_objection(self):
        """objection_think из close -> handle_objection"""
        result = self.sm.process("objection_think", {})
        assert result["next_state"] == "handle_objection"

    def test_demo_request_stays_with_confirm_and_collect(self):
        """demo_request в close обрабатывается через rules"""
        result = self.sm.process("demo_request", {})
        assert result["next_state"] == "close"
        assert result["action"] == "confirm_and_collect_contact"

    def test_callback_request_stays_with_confirm_and_collect(self):
        """callback_request в close обрабатывается через rules"""
        result = self.sm.process("callback_request", {})
        assert result["next_state"] == "close"
        assert result["action"] == "confirm_and_collect_contact"

    def test_contact_provided_completes_to_success(self):
        """contact_provided в close с данными -> success"""
        result = self.sm.process("contact_provided", {"contact_info": "+7999123456"})
        assert result["next_state"] == "success"
        assert result["is_final"] == True


class TestQuestionIntentsConfig:
    """Тесты что QUESTION_INTENTS правильно настроены"""

    def test_comparison_in_question_intents(self):
        """comparison должен быть в QUESTION_INTENTS"""
        assert "comparison" in QUESTION_INTENTS

    def test_pricing_details_in_question_intents(self):
        """pricing_details должен быть в QUESTION_INTENTS"""
        assert "pricing_details" in QUESTION_INTENTS

    def test_question_features_in_question_intents(self):
        """question_features должен быть в QUESTION_INTENTS"""
        assert "question_features" in QUESTION_INTENTS

    def test_question_integrations_in_question_intents(self):
        """question_integrations должен быть в QUESTION_INTENTS"""
        assert "question_integrations" in QUESTION_INTENTS

    def test_price_question_in_question_intents(self):
        """price_question должен быть в QUESTION_INTENTS"""
        assert "price_question" in QUESTION_INTENTS


class TestAllStatesHaveRequiredTransitions:
    """Тесты что все состояния имеют необходимые переходы"""

    @pytest.mark.parametrize("state", [
        "greeting", "spin_situation", "spin_problem",
        "spin_implication", "spin_need_payoff", "qualification"
    ])
    def test_early_states_have_demo_request_transition(self, state):
        """Все ранние состояния имеют переход для demo_request"""
        transitions = SALES_STATES[state]["transitions"]
        assert "demo_request" in transitions
        assert transitions["demo_request"] == "close"

    @pytest.mark.parametrize("state", [
        "greeting", "spin_situation", "spin_problem",
        "spin_implication", "spin_need_payoff", "qualification"
    ])
    def test_early_states_have_callback_request_transition(self, state):
        """Все ранние состояния имеют переход для callback_request"""
        transitions = SALES_STATES[state]["transitions"]
        assert "callback_request" in transitions
        assert transitions["callback_request"] == "close"

    @pytest.mark.parametrize("state", [
        "greeting", "spin_situation", "spin_problem",
        "spin_implication", "spin_need_payoff", "presentation",
        "handle_objection", "close", "qualification"
    ])
    def test_states_have_farewell_transition(self, state):
        """Все состояния имеют переход для farewell"""
        transitions = SALES_STATES[state]["transitions"]
        assert "farewell" in transitions
        assert transitions["farewell"] == "soft_close"

    @pytest.mark.parametrize("state", [
        "spin_situation", "spin_problem", "spin_implication",
        "spin_need_payoff", "presentation", "qualification"
    ])
    def test_spin_and_presentation_states_handle_comparison(self, state):
        """SPIN состояния и presentation обрабатывают comparison через rules"""
        rules = SALES_STATES[state].get("rules", {})
        assert "comparison" in rules


class TestIntegrationScenarios:
    """Интеграционные тесты реальных сценариев"""

    def test_scenario_demo_request_immediately(self):
        """Сценарий: клиент сразу просит демо"""
        sm = StateMachine()

        # Приветствие
        result = sm.process("greeting", {})

        # Сразу просит демо
        result = sm.process("demo_request", {})

        assert result["next_state"] == "close"
        assert result["goal"] == "Взять контакт или назначить демо"

    def test_scenario_callback_request_during_spin(self):
        """Сценарий: клиент просит перезвонить в середине SPIN"""
        sm = StateMachine()

        sm.process("agreement", {})  # -> spin_situation
        sm.process("info_provided", {"company_size": 5})  # -> spin_problem

        # Вместо продолжения просит перезвонить
        result = sm.process("callback_request", {})

        assert result["next_state"] == "close"

    def test_scenario_no_time_objection_early(self):
        """Сценарий: клиент говорит 'нет времени' на ранней стадии"""
        sm = StateMachine()

        sm.process("greeting", {})

        # Сразу говорит нет времени
        result = sm.process("objection_no_time", {})

        assert result["next_state"] == "soft_close"
        assert result["is_final"] == True

    def test_scenario_think_objection_after_presentation(self):
        """Сценарий: клиент говорит 'надо подумать' после презентации"""
        sm = StateMachine()
        sm.state = "presentation"

        result = sm.process("objection_think", {})

        assert result["next_state"] == "handle_objection"

    def test_scenario_farewell_closes_gracefully(self):
        """Сценарий: клиент прощается на любом этапе"""
        sm = StateMachine()

        sm.process("agreement", {})  # -> spin_situation

        # Прощается
        result = sm.process("farewell", {})

        assert result["next_state"] == "soft_close"
        assert result["is_final"] == True

    def test_scenario_comparison_gets_answer_and_continues(self):
        """Сценарий: клиент спрашивает о сравнении с конкурентом"""
        sm = StateMachine()

        sm.process("agreement", {})  # -> spin_situation

        # Спрашивает сравнение
        result = sm.process("comparison", {})

        assert result["next_state"] == "spin_situation"
        assert result["action"] == "answer_and_continue"

    def test_scenario_pricing_details_deflected_in_spin(self):
        """Сценарий: клиент спрашивает детали по цене в SPIN"""
        sm = StateMachine()

        sm.process("agreement", {})  # -> spin_situation

        # Спрашивает детали по цене
        result = sm.process("pricing_details", {})

        assert result["next_state"] == "spin_situation"
        assert result["action"] == "deflect_and_continue"

    def test_scenario_pricing_details_answered_in_presentation(self):
        """Сценарий: клиент спрашивает детали по цене в presentation"""
        sm = StateMachine()
        sm.state = "presentation"

        result = sm.process("pricing_details", {})

        assert result["next_state"] == "presentation"
        assert result["action"] == "answer_with_facts"


class TestNoUnexpectedContinueCurrentGoal:
    """Тесты что важные интенты НЕ попадают в continue_current_goal"""

    critical_intents = [
        "demo_request",
        "callback_request",
        "farewell",
        "comparison",
        "pricing_details",
    ]

    @pytest.mark.parametrize("intent", critical_intents)
    def test_greeting_handles_critical_intents(self, intent):
        """greeting не возвращает continue_current_goal для критических интентов"""
        sm = StateMachine()
        result = sm.process(intent, {})
        assert result["action"] != "continue_current_goal", \
            f"Intent {intent} неожиданно вернул continue_current_goal в greeting"

    @pytest.mark.parametrize("intent", critical_intents)
    def test_spin_situation_handles_critical_intents(self, intent):
        """spin_situation не возвращает continue_current_goal для критических интентов"""
        sm = StateMachine()
        sm.process("agreement", {})
        result = sm.process(intent, {})
        assert result["action"] != "continue_current_goal", \
            f"Intent {intent} неожиданно вернул continue_current_goal в spin_situation"

    @pytest.mark.parametrize("intent", critical_intents)
    def test_presentation_handles_critical_intents(self, intent):
        """presentation не возвращает continue_current_goal для критических интентов"""
        sm = StateMachine()
        sm.state = "presentation"
        result = sm.process(intent, {})
        assert result["action"] != "continue_current_goal", \
            f"Intent {intent} неожиданно вернул continue_current_goal в presentation"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
