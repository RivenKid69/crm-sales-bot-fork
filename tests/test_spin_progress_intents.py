"""
Тесты для SPIN Progress Intents

Проверяют что situation_provided, problem_revealed, implication_acknowledged,
need_expressed корректно обрабатываются в transitions SALES_STATES.

Также проверяют contact_provided в close state и go_back/correct_info в INTENT_TO_CATEGORY.
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from state_machine import StateMachine, SPIN_PROGRESS_INTENTS
from config import SALES_STATES
from knowledge.retriever import INTENT_TO_CATEGORY


class TestSPINProgressIntentsInTransitions:
    """Тесты что все SPIN progress intents есть в transitions соответствующих состояний"""

    def test_situation_provided_in_spin_situation_transitions(self):
        """situation_provided должен быть в transitions spin_situation"""
        transitions = SALES_STATES["spin_situation"]["transitions"]
        assert "situation_provided" in transitions, (
            "situation_provided отсутствует в transitions spin_situation"
        )
        assert transitions["situation_provided"] == "spin_problem", (
            "situation_provided должен вести в spin_problem"
        )

    def test_problem_revealed_in_spin_problem_transitions(self):
        """problem_revealed должен быть в transitions spin_problem"""
        transitions = SALES_STATES["spin_problem"]["transitions"]
        assert "problem_revealed" in transitions, (
            "problem_revealed отсутствует в transitions spin_problem"
        )
        assert transitions["problem_revealed"] == "spin_implication", (
            "problem_revealed должен вести в spin_implication"
        )

    def test_implication_acknowledged_in_spin_implication_transitions(self):
        """implication_acknowledged должен быть в transitions spin_implication"""
        transitions = SALES_STATES["spin_implication"]["transitions"]
        assert "implication_acknowledged" in transitions, (
            "implication_acknowledged отсутствует в transitions spin_implication"
        )
        assert transitions["implication_acknowledged"] == "spin_need_payoff", (
            "implication_acknowledged должен вести в spin_need_payoff"
        )

    def test_need_expressed_in_spin_need_payoff_transitions(self):
        """need_expressed должен быть в transitions spin_need_payoff"""
        transitions = SALES_STATES["spin_need_payoff"]["transitions"]
        assert "need_expressed" in transitions, (
            "need_expressed отсутствует в transitions spin_need_payoff"
        )
        assert transitions["need_expressed"] == "presentation", (
            "need_expressed должен вести в presentation"
        )

    def test_all_spin_progress_intents_have_transitions(self):
        """Все интенты из SPIN_PROGRESS_INTENTS должны иметь соответствующие transitions"""
        intent_to_state = {
            "situation_provided": "spin_situation",
            "problem_revealed": "spin_problem",
            "implication_acknowledged": "spin_implication",
            "need_expressed": "spin_need_payoff",
        }

        for intent, state in intent_to_state.items():
            transitions = SALES_STATES[state]["transitions"]
            assert intent in transitions, (
                f"{intent} отсутствует в transitions {state}"
            )


class TestSPINProgressIntentsInStateMachine:
    """Тесты поведения StateMachine с SPIN progress intents"""

    def setup_method(self):
        self.sm = StateMachine()

    def _go_to_spin_situation(self):
        """Перейти в spin_situation"""
        self.sm.process("agreement", {})
        assert self.sm.state == "spin_situation"

    def _go_to_spin_problem(self):
        """Перейти в spin_problem"""
        self._go_to_spin_situation()
        self.sm.process("info_provided", {"company_size": 10})
        assert self.sm.state == "spin_problem"

    def _go_to_spin_implication(self):
        """Перейти в spin_implication"""
        self._go_to_spin_problem()
        self.sm.process("info_provided", {"pain_point": "теряем клиентов"})
        assert self.sm.state == "spin_implication"

    def _go_to_spin_need_payoff(self):
        """Перейти в spin_need_payoff"""
        self._go_to_spin_implication()
        self.sm.process("agreement", {})
        assert self.sm.state == "spin_need_payoff"

    def test_situation_provided_transitions_to_spin_problem(self):
        """situation_provided из spin_situation -> spin_problem"""
        self._go_to_spin_situation()

        result = self.sm.process("situation_provided", {"company_size": 15})

        assert result["next_state"] == "spin_problem"
        assert result["spin_phase"] == "problem"

    def test_problem_revealed_transitions_to_spin_implication(self):
        """problem_revealed из spin_problem -> spin_implication"""
        self._go_to_spin_problem()

        result = self.sm.process("problem_revealed", {"pain_point": "нет контроля"})

        assert result["next_state"] == "spin_implication"
        assert result["spin_phase"] == "implication"

    def test_implication_acknowledged_transitions_to_spin_need_payoff(self):
        """implication_acknowledged из spin_implication -> spin_need_payoff"""
        self._go_to_spin_implication()

        result = self.sm.process("implication_acknowledged", {"pain_impact": "теряем 100k в месяц"})

        assert result["next_state"] == "spin_need_payoff"
        assert result["spin_phase"] == "need_payoff"

    def test_need_expressed_transitions_to_presentation(self):
        """need_expressed из spin_need_payoff -> presentation"""
        self._go_to_spin_need_payoff()

        result = self.sm.process("need_expressed", {"desired_outcome": "автоматизация"})

        assert result["next_state"] == "presentation"


class TestContactProvidedInCloseState:
    """Тесты для contact_provided в close state"""

    def test_contact_provided_in_close_transitions(self):
        """contact_provided должен быть в transitions close"""
        transitions = SALES_STATES["close"]["transitions"]
        assert "contact_provided" in transitions, (
            "contact_provided отсутствует в transitions close"
        )
        assert transitions["contact_provided"] == "success", (
            "contact_provided должен вести в success"
        )

    def test_contact_provided_transitions_to_success(self):
        """contact_provided из close -> success"""
        sm = StateMachine()

        # Переходим в close state
        sm.process("demo_request", {})
        assert sm.state == "close"

        # Предоставляем контакт
        result = sm.process("contact_provided", {"contact_info": "+7 999 123-45-67"})

        assert result["next_state"] == "success"
        assert result["is_final"] == True


class TestNavigationIntentsInIntentToCategory:
    """Тесты для go_back и correct_info в INTENT_TO_CATEGORY"""

    def test_go_back_in_intent_to_category(self):
        """go_back должен быть в INTENT_TO_CATEGORY"""
        assert "go_back" in INTENT_TO_CATEGORY, (
            "go_back отсутствует в INTENT_TO_CATEGORY"
        )
        assert INTENT_TO_CATEGORY["go_back"] == [], (
            "go_back должен иметь пустой список категорий"
        )

    def test_correct_info_in_intent_to_category(self):
        """correct_info должен быть в INTENT_TO_CATEGORY"""
        assert "correct_info" in INTENT_TO_CATEGORY, (
            "correct_info отсутствует в INTENT_TO_CATEGORY"
        )
        assert INTENT_TO_CATEGORY["correct_info"] == [], (
            "correct_info должен иметь пустой список категорий"
        )


class TestNoLegacyQualificationState:
    """Тесты что legacy qualification state удалён"""

    def test_qualification_not_in_sales_states(self):
        """qualification state должен быть удалён из SALES_STATES"""
        assert "qualification" not in SALES_STATES, (
            "Legacy qualification state должен быть удалён из SALES_STATES"
        )

    def test_no_transitions_to_qualification(self):
        """Ни одно состояние не должно иметь перехода в qualification"""
        for state_name, state_config in SALES_STATES.items():
            if "transitions" in state_config:
                for intent, target_state in state_config["transitions"].items():
                    assert target_state != "qualification", (
                        f"Состояние {state_name} имеет переход в qualification через {intent}"
                    )


class TestSPINProgressIntentsMapping:
    """Тесты соответствия SPIN_PROGRESS_INTENTS реальным transitions"""

    def test_spin_progress_intents_match_transitions(self):
        """SPIN_PROGRESS_INTENTS должны соответствовать реальным transitions"""
        expected_mappings = {
            "situation_provided": ("spin_situation", "spin_problem"),
            "problem_revealed": ("spin_problem", "spin_implication"),
            "implication_acknowledged": ("spin_implication", "spin_need_payoff"),
            "need_expressed": ("spin_need_payoff", "presentation"),
        }

        for intent, (from_state, to_state) in expected_mappings.items():
            assert intent in SPIN_PROGRESS_INTENTS, (
                f"{intent} отсутствует в SPIN_PROGRESS_INTENTS"
            )

            transitions = SALES_STATES[from_state]["transitions"]
            assert intent in transitions, (
                f"{intent} отсутствует в transitions {from_state}"
            )
            assert transitions[intent] == to_state, (
                f"{intent} должен вести из {from_state} в {to_state}, "
                f"но ведёт в {transitions[intent]}"
            )
