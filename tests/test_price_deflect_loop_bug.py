"""
Тесты для фикса: Price Deflect Loop Bug

ПРОБЛЕМА (из simulation_report.txt, симуляция #10):
Клиент спрашивал "почем?" 6 раз, бот каждый раз deflect'ил,
даже когда users_count=10 уже был извлечён.

КОРНЕВАЯ ПРИЧИНА (исправлена):
state_machine.py — когда intent="price_question" в SPIN-фазах,
возвращался action="deflect_and_continue" без проверки собранных данных.

ИСПРАВЛЕНИЕ:
Добавлена проверка: если price_question И company_size/users_count ЕСТЬ →
возвращается answer_with_facts вместо deflect_and_continue.
"""

import pytest
import sys

from src.state_machine import StateMachine
from src.config import SALES_STATES

class TestPriceDeflectLoopFix:
    """
    Тесты подтверждающие что фикс работает:
    price_question с данными → answer_with_facts
    """

    def setup_method(self):
        self.sm = StateMachine()

    # =========================================================================
    # ТЕСТЫ ФИКСА: price_question с данными → answer_with_facts
    # =========================================================================

    def test_price_question_with_users_count_answers(self):
        """
        FIX: Когда users_count известен, price_question возвращает answer_with_facts.
        """
        self.sm.state = "spin_need_payoff"
        self.sm.collected_data = {
            "company_size": 5,
            "users_count": 10,
            "pain_point": "долги и накладные",
        }

        action, next_state = self.sm.apply_rules("price_question")

        assert action == "answer_with_facts", \
            f"При наличии users_count=10 бот должен ответить на вопрос о цене. " \
            f"Получили action={action}"

    def test_price_question_with_company_size_answers(self):
        """
        FIX: Когда company_size известен, price_question возвращает answer_with_facts.
        """
        self.sm.state = "spin_problem"
        self.sm.collected_data = {"company_size": 12}

        action, next_state = self.sm.apply_rules("price_question")

        assert action == "answer_with_facts", \
            f"При наличии company_size=12 бот должен ответить на вопрос о цене. " \
            f"Получили action={action}"

    def test_price_question_repeated_with_data_answers(self):
        """
        FIX: При повторных price_question с данными — всегда answer_with_facts.
        """
        self.sm.state = "spin_need_payoff"
        self.sm.collected_data = {"users_count": 10}

        action1, _ = self.sm.apply_rules("price_question")
        action2, _ = self.sm.apply_rules("price_question")
        action3, _ = self.sm.apply_rules("price_question")

        actions = [action1, action2, action3]
        assert all(a == "answer_with_facts" for a in actions), \
            f"Все 3 price_question с users_count=10 должны быть answer_with_facts. " \
            f"Получили: {actions}"

    def test_fix_in_spin_situation_with_data(self):
        """
        FIX: В spin_situation с данными → answer_with_facts.
        """
        self.sm.state = "spin_situation"
        self.sm.collected_data = {"company_size": 15}

        action, _ = self.sm.apply_rules("price_question")

        assert action == "answer_with_facts", \
            f"В spin_situation с company_size=15 должен быть answer_with_facts. " \
            f"Получили: {action}"

    def test_fix_in_spin_problem_with_data(self):
        """
        FIX: В spin_problem с данными → answer_with_facts.
        """
        self.sm.state = "spin_problem"
        self.sm.collected_data = {"company_size": 8, "pain_point": "теряем клиентов"}

        action, _ = self.sm.apply_rules("price_question")

        assert action == "answer_with_facts", \
            f"В spin_problem с company_size=8 должен быть answer_with_facts. " \
            f"Получили: {action}"

    def test_fix_in_spin_implication_with_data(self):
        """
        FIX: В spin_implication с данными → answer_with_facts.
        """
        self.sm.state = "spin_implication"
        self.sm.collected_data = {
            "company_size": 20,
            "pain_point": "много ручной работы",
            "implication_probed": True,
        }

        action, _ = self.sm.apply_rules("price_question")

        assert action == "answer_with_facts", \
            f"В spin_implication с company_size=20 должен быть answer_with_facts. " \
            f"Получили: {action}"

    def test_fix_in_spin_need_payoff_with_data(self):
        """
        FIX: В spin_need_payoff с данными → answer_with_facts.

        Это ТОЧНАЯ репродукция симуляции #10!
        """
        self.sm.state = "spin_need_payoff"
        self.sm.collected_data = {
            "company_size": 5,
            "users_count": 10,
            "pain_point": "долги и накладные",
            "implication_probed": True,
            "need_payoff_probed": True,
        }

        action, _ = self.sm.apply_rules("price_question")

        assert action == "answer_with_facts", \
            f"В spin_need_payoff с полными данными должен быть answer_with_facts. " \
            f"Получили: {action}"

    # =========================================================================
    # ТЕСТЫ: price_question БЕЗ данных → deflect_and_continue (правильно)
    # =========================================================================

    def test_price_question_without_data_deflects(self):
        """
        Когда данных НЕТ — deflect_and_continue (правильно).
        """
        self.sm.state = "spin_situation"
        self.sm.collected_data = {}

        action, _ = self.sm.apply_rules("price_question")

        assert action == "deflect_and_continue", \
            "Без данных deflect_and_continue — правильно"

    def test_price_question_with_only_pain_point_deflects(self):
        """
        Если есть только pain_point (без company_size) — deflect.
        """
        self.sm.state = "spin_problem"
        self.sm.collected_data = {"pain_point": "теряем клиентов"}

        action, _ = self.sm.apply_rules("price_question")

        assert action == "deflect_and_continue", \
            "Без company_size/users_count — deflect_and_continue"

    def test_price_question_with_zero_company_size_deflects(self):
        """
        Если company_size=0 — deflect (некорректное значение).
        """
        self.sm.state = "spin_situation"
        self.sm.collected_data = {"company_size": 0}

        action, _ = self.sm.apply_rules("price_question")

        assert action == "deflect_and_continue", \
            "company_size=0 — deflect_and_continue"

    # =========================================================================
    # ТЕСТЫ: presentation и close работают как раньше
    # =========================================================================

    def test_price_question_in_presentation_answers(self):
        """
        В presentation state — answer_with_facts (как и раньше).
        """
        self.sm.state = "presentation"
        self.sm.collected_data = {"company_size": 10}

        action, _ = self.sm.apply_rules("price_question")

        assert action == "answer_with_facts"

    def test_price_question_in_close_answers(self):
        """
        В close state — answer_with_facts (как и раньше).
        """
        self.sm.state = "close"
        self.sm.collected_data = {"company_size": 10}

        action, _ = self.sm.apply_rules("price_question")

        assert action == "answer_with_facts"

class TestConfigRulesAnalysis:
    """
    Анализ конфигурации — проверяем условные правила (Phase 8 Conditional Rules).

    В SPIN-фазах price_question имеет условную логику:
    [{"when": "can_answer_price", "then": "answer_with_facts"}, "deflect_and_continue"]

    В presentation/close — простое answer_with_facts.
    """

    def test_spin_situation_rules_has_conditional_price_question(self):
        """Config: spin_situation.rules имеет условный price_question"""
        rules = SALES_STATES["spin_situation"]["rules"]
        price_rule = rules.get("price_question")
        # Должен быть список с условием и fallback
        assert isinstance(price_rule, list), \
            f"price_question в spin_situation должен быть списком (conditional rule). Получили: {type(price_rule)}"
        assert len(price_rule) == 2, \
            f"Conditional rule должен иметь 2 элемента: условие и fallback. Получили: {price_rule}"
        assert price_rule[0].get("when") == "can_answer_price", \
            f"Первый элемент должен иметь when='can_answer_price'. Получили: {price_rule[0]}"
        assert price_rule[0].get("then") == "answer_with_facts", \
            f"Первый элемент должен иметь then='answer_with_facts'. Получили: {price_rule[0]}"
        assert price_rule[1] == "deflect_and_continue", \
            f"Fallback должен быть 'deflect_and_continue'. Получили: {price_rule[1]}"

    def test_spin_problem_rules_has_conditional_price_question(self):
        """Config: spin_problem.rules имеет условный price_question"""
        rules = SALES_STATES["spin_problem"]["rules"]
        price_rule = rules.get("price_question")
        assert isinstance(price_rule, list)
        assert price_rule[1] == "deflect_and_continue"

    def test_spin_implication_rules_has_conditional_price_question(self):
        """Config: spin_implication.rules имеет условный price_question"""
        rules = SALES_STATES["spin_implication"]["rules"]
        price_rule = rules.get("price_question")
        assert isinstance(price_rule, list)
        assert price_rule[1] == "deflect_and_continue"

    def test_spin_need_payoff_rules_has_conditional_price_question(self):
        """Config: spin_need_payoff.rules имеет условный price_question"""
        rules = SALES_STATES["spin_need_payoff"]["rules"]
        price_rule = rules.get("price_question")
        assert isinstance(price_rule, list)
        assert price_rule[1] == "deflect_and_continue"

    def test_presentation_rules_has_answer(self):
        """Config: presentation.rules имеет price_question: answer_with_facts"""
        rules = SALES_STATES["presentation"]["rules"]
        assert rules.get("price_question") == "answer_with_facts"

    def test_close_rules_has_answer(self):
        """Config: close.rules имеет price_question: answer_with_facts"""
        rules = SALES_STATES["close"]["rules"]
        assert rules.get("price_question") == "answer_with_facts"

class TestDeflectLoopScenarioFixed:
    """
    Полная симуляция deflect loop — теперь исправлена.
    """

    def setup_method(self):
        self.sm = StateMachine()

    def test_full_deflect_loop_scenario_fixed(self):
        """
        Воспроизводим полный сценарий симуляции #10 — теперь исправлен:

        [Ход 2] данных нет → deflect (правильно)
        [Ход 3] company_size=5 → answer_with_facts (FIX!)
        [Ход 6] company_size=5 → answer_with_facts (FIX!)
        [Ход 7] users_count=10 → answer_with_facts (FIX!)
        """
        collected_data_sequence = [
            {},  # Ход 2: данных нет
            {"company_size": 5},  # Ход 3: извлекли company_size
            {"company_size": 5},  # Ход 6: данные сохранены
            {"company_size": 5, "users_count": 10},  # Ход 7: извлекли users_count
            {"company_size": 5, "users_count": 10},  # Ход 8
            {"company_size": 5, "users_count": 10},  # Ход 9
        ]

        states = ["spin_situation", "spin_problem", "spin_need_payoff",
                  "spin_need_payoff", "spin_need_payoff", "spin_need_payoff"]

        results = []
        for i, (data, state) in enumerate(zip(collected_data_sequence, states)):
            self.sm.state = state
            self.sm.collected_data = data.copy()
            action, _ = self.sm.apply_rules("price_question")
            results.append({
                "ход": i + 2,
                "state": state,
                "data": data,
                "action": action,
            })

        # Ход 2: данных нет → deflect (правильно)
        assert results[0]["action"] == "deflect_and_continue", \
            f"Ход 2: без данных должен быть deflect. Получили: {results[0]}"

        # Ходы 3-9: данные есть → answer_with_facts
        for r in results[1:]:
            assert r["action"] == "answer_with_facts", \
                f"Ход {r['ход']}: с данными должен быть answer_with_facts. Получили: {r}"

    def test_scenario_with_only_users_count(self):
        """
        Сценарий когда клиент сразу сказал количество пользователей.
        """
        self.sm.state = "spin_situation"
        self.sm.collected_data = {"users_count": 15}

        action, _ = self.sm.apply_rules("price_question")

        assert action == "answer_with_facts", \
            "С users_count=15 должен быть answer_with_facts"

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
