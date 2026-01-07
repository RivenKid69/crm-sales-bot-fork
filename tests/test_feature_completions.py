"""
Тесты для завершённой функциональности:
1. objection_price в SPIN-фазах
2. Симметричная обработка возражений в greeting
3. ObjectionFlowManager (защита от зацикливания)
4. Унификация info_provided/situation_provided
5. go_back из soft_close
6. question_features/question_integrations в rules SPIN-фаз
7. Fallback для неизвестных интентов в INTENT_TO_CATEGORY
"""

import sys
from pathlib import Path

# Добавляем src в путь
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest
from state_machine import (
    StateMachine,
    ObjectionFlowManager,
    CircularFlowManager,
    OBJECTION_INTENTS,
)
from config import SALES_STATES


# =============================================================================
# 1. objection_price в SPIN-фазах
# =============================================================================

class TestObjectionPriceInSpinPhases:
    """Тесты: objection_price должен обрабатываться во всех SPIN-фазах."""

    @pytest.fixture
    def sm(self):
        return StateMachine()

    @pytest.mark.parametrize("spin_state", [
        "spin_situation",
        "spin_problem",
        "spin_implication",
        "spin_need_payoff",
    ])
    def test_objection_price_transition_exists(self, spin_state):
        """objection_price должен быть в transitions для всех SPIN-фаз."""
        config = SALES_STATES.get(spin_state, {})
        transitions = config.get("transitions", {})

        assert "objection_price" in transitions, \
            f"objection_price should be in {spin_state} transitions"
        assert transitions["objection_price"] == "handle_objection", \
            f"objection_price should lead to handle_objection from {spin_state}"

    @pytest.mark.parametrize("spin_state", [
        "spin_situation",
        "spin_problem",
        "spin_implication",
        "spin_need_payoff",
    ])
    def test_objection_price_processing(self, sm, spin_state):
        """objection_price должен переводить в handle_objection из SPIN-фаз."""
        sm.state = spin_state

        result = sm.process("objection_price")

        assert result["next_state"] == "handle_objection", \
            f"objection_price from {spin_state} should go to handle_objection"


# =============================================================================
# 2. Симметричная обработка возражений в greeting
# =============================================================================

class TestSymmetricObjectionHandlingInGreeting:
    """Тесты: все возражения обрабатываются симметрично в greeting."""

    def test_objection_price_in_greeting(self):
        """objection_price должен быть в transitions для greeting."""
        config = SALES_STATES.get("greeting", {})
        transitions = config.get("transitions", {})

        assert "objection_price" in transitions
        assert transitions["objection_price"] == "handle_objection"

    def test_objection_competitor_in_greeting(self):
        """objection_competitor должен быть в transitions для greeting."""
        config = SALES_STATES.get("greeting", {})
        transitions = config.get("transitions", {})

        assert "objection_competitor" in transitions
        assert transitions["objection_competitor"] == "handle_objection"

    def test_all_objections_handled_consistently(self):
        """Все workable возражения должны идти в handle_objection."""
        config = SALES_STATES.get("greeting", {})
        transitions = config.get("transitions", {})

        # Возражения по цене и конкуренту можно отработать
        workable_objections = ["objection_price", "objection_competitor"]
        for obj in workable_objections:
            assert transitions.get(obj) == "handle_objection", \
                f"{obj} should go to handle_objection"

        # Возражения по времени и "думать" — мягко завершаем
        unworkable_objections = ["objection_no_time", "objection_think"]
        for obj in unworkable_objections:
            assert transitions.get(obj) == "soft_close", \
                f"{obj} should go to soft_close"


# =============================================================================
# 3. ObjectionFlowManager (защита от зацикливания)
# =============================================================================

class TestObjectionFlowManager:
    """Тесты: ObjectionFlowManager защищает от зацикливания возражений."""

    @pytest.fixture
    def manager(self):
        return ObjectionFlowManager()

    def test_initial_state(self, manager):
        """Начальное состояние должно быть нулевым."""
        assert manager.objection_count == 0
        assert manager.total_objections == 0
        assert manager.last_state_before_objection is None

    def test_record_objection(self, manager):
        """Запись возражения увеличивает счётчики."""
        manager.record_objection("objection_price", "spin_situation")

        assert manager.objection_count == 1
        assert manager.total_objections == 1
        assert manager.last_state_before_objection == "spin_situation"

    def test_consecutive_limit(self, manager):
        """После MAX_CONSECUTIVE_OBJECTIONS должен вернуть should_soft_close=True."""
        for _ in range(ObjectionFlowManager.MAX_CONSECUTIVE_OBJECTIONS):
            manager.record_objection("objection_price", "handle_objection")

        assert manager.should_soft_close() is True

    def test_total_limit(self, manager):
        """После MAX_TOTAL_OBJECTIONS должен вернуть should_soft_close=True."""
        # Записываем меньше consecutive, но больше total
        for i in range(ObjectionFlowManager.MAX_TOTAL_OBJECTIONS):
            manager.record_objection("objection_price", "handle_objection")
            if i < ObjectionFlowManager.MAX_TOTAL_OBJECTIONS - 2:
                manager.reset_consecutive()  # Сбрасываем consecutive

        assert manager.should_soft_close() is True

    def test_reset_consecutive(self, manager):
        """reset_consecutive сбрасывает только счётчик последовательных."""
        manager.record_objection("objection_price", "spin_situation")
        manager.record_objection("objection_price", "handle_objection")

        manager.reset_consecutive()

        assert manager.objection_count == 0
        assert manager.total_objections == 2  # Total не сбрасывается

    def test_stats(self, manager):
        """get_stats возвращает корректную статистику."""
        manager.record_objection("objection_price", "spin_situation")

        stats = manager.get_stats()

        assert stats["consecutive_objections"] == 1
        assert stats["total_objections"] == 1
        assert stats["return_state"] == "spin_situation"


class TestObjectionFlowInStateMachine:
    """Тесты: ObjectionFlowManager интегрирован в StateMachine."""

    @pytest.fixture
    def sm(self):
        return StateMachine()

    def test_objection_flow_exists(self, sm):
        """StateMachine должен иметь objection_flow."""
        assert hasattr(sm, "objection_flow")
        assert isinstance(sm.objection_flow, ObjectionFlowManager)

    def test_objection_limit_triggers_soft_close(self, sm):
        """Превышение лимита возражений должно переводить в soft_close."""
        sm.state = "handle_objection"

        # Посылаем MAX_CONSECUTIVE_OBJECTIONS возражений
        for _ in range(ObjectionFlowManager.MAX_CONSECUTIVE_OBJECTIONS):
            result = sm.process("objection_price")

        assert result["next_state"] == "soft_close"
        assert result["action"] == "objection_limit_reached"

    def test_positive_intent_resets_consecutive(self, sm):
        """Положительный интент сбрасывает consecutive counter."""
        sm.state = "handle_objection"
        sm.objection_flow.record_objection("objection_price", "handle_objection")

        # Клиент согласился
        sm.process("agreement")

        assert sm.objection_flow.objection_count == 0

    def test_objection_stats_in_result(self, sm):
        """Результат process должен содержать objection_flow stats."""
        result = sm.process("greeting")

        assert "objection_flow" in result


# =============================================================================
# 4. Унификация info_provided/situation_provided
# =============================================================================

class TestInfoProvidedUnification:
    """Тесты: info_provided и situation_provided обрабатываются единообразно."""

    @pytest.fixture
    def sm(self):
        return StateMachine()

    def test_info_provided_in_spin_situation(self):
        """info_provided должен быть в transitions для spin_situation."""
        config = SALES_STATES.get("spin_situation", {})
        transitions = config.get("transitions", {})

        assert "info_provided" in transitions
        assert transitions["info_provided"] == "spin_problem"

    def test_info_provided_in_spin_problem(self):
        """info_provided должен быть в transitions для spin_problem."""
        config = SALES_STATES.get("spin_problem", {})
        transitions = config.get("transitions", {})

        assert "info_provided" in transitions
        assert transitions["info_provided"] == "spin_implication"

    def test_situation_provided_and_info_provided_same_target(self, sm):
        """situation_provided и info_provided должны вести в одно состояние."""
        sm.state = "spin_situation"

        result1 = sm.process("situation_provided", {"company_size": 10})

        sm.reset()
        sm.state = "spin_situation"

        result2 = sm.process("info_provided", {"company_size": 10})

        assert result1["next_state"] == result2["next_state"] == "spin_problem"


# =============================================================================
# 5. go_back из soft_close
# =============================================================================

class TestGoBackFromSoftClose:
    """Тесты: можно вернуться из soft_close."""

    def test_soft_close_not_final(self):
        """soft_close не должен быть финальным состоянием."""
        config = SALES_STATES.get("soft_close", {})

        assert config.get("is_final") is False

    def test_soft_close_has_transitions(self):
        """soft_close должен иметь transitions."""
        config = SALES_STATES.get("soft_close", {})
        transitions = config.get("transitions", {})

        assert len(transitions) > 0

    def test_go_back_in_soft_close_transitions(self):
        """go_back должен быть в transitions для soft_close."""
        config = SALES_STATES.get("soft_close", {})
        transitions = config.get("transitions", {})

        assert "go_back" in transitions
        assert transitions["go_back"] == "greeting"

    def test_soft_close_in_allowed_gobacks(self):
        """soft_close должен быть в ALLOWED_GOBACKS."""
        assert "soft_close" in CircularFlowManager.ALLOWED_GOBACKS
        assert CircularFlowManager.ALLOWED_GOBACKS["soft_close"] == "greeting"

    def test_go_back_from_soft_close_processing(self):
        """go_back из soft_close должен работать."""
        sm = StateMachine()
        sm.state = "soft_close"

        result = sm.process("go_back")

        assert result["next_state"] == "greeting"
        assert result["action"] == "go_back"

    def test_agreement_from_soft_close(self):
        """agreement из soft_close должен вести в spin_situation."""
        sm = StateMachine()
        sm.state = "soft_close"

        result = sm.process("agreement")

        assert result["next_state"] == "spin_situation"


# =============================================================================
# 6. question_features/question_integrations в rules SPIN-фаз
# =============================================================================

class TestQuestionIntentsInSpinRules:
    """Тесты: вопросы о функциях/интеграциях в rules SPIN-фаз."""

    @pytest.mark.parametrize("spin_state", [
        "spin_situation",
        "spin_problem",
        "spin_implication",
        "spin_need_payoff",
    ])
    def test_question_features_in_rules(self, spin_state):
        """question_features должен быть в rules для всех SPIN-фаз."""
        config = SALES_STATES.get(spin_state, {})
        rules = config.get("rules", {})

        assert "question_features" in rules, \
            f"question_features should be in {spin_state} rules"
        assert rules["question_features"] == "answer_and_continue", \
            f"question_features should return answer_and_continue in {spin_state}"

    @pytest.mark.parametrize("spin_state", [
        "spin_situation",
        "spin_problem",
        "spin_implication",
        "spin_need_payoff",
    ])
    def test_question_integrations_in_rules(self, spin_state):
        """question_integrations должен быть в rules для всех SPIN-фаз."""
        config = SALES_STATES.get(spin_state, {})
        rules = config.get("rules", {})

        assert "question_integrations" in rules, \
            f"question_integrations should be in {spin_state} rules"
        assert rules["question_integrations"] == "answer_and_continue", \
            f"question_integrations should return answer_and_continue in {spin_state}"


# =============================================================================
# 7. objection_competitor во всех SPIN-фазах
# =============================================================================

class TestObjectionCompetitorInSpinPhases:
    """Тесты: objection_competitor обрабатывается во всех SPIN-фазах."""

    @pytest.mark.parametrize("spin_state", [
        "spin_situation",
        "spin_problem",
        "spin_implication",
        "spin_need_payoff",
    ])
    def test_objection_competitor_transition_exists(self, spin_state):
        """objection_competitor должен быть в transitions для всех SPIN-фаз."""
        config = SALES_STATES.get(spin_state, {})
        transitions = config.get("transitions", {})

        assert "objection_competitor" in transitions, \
            f"objection_competitor should be in {spin_state} transitions"
        assert transitions["objection_competitor"] == "handle_objection", \
            f"objection_competitor should lead to handle_objection from {spin_state}"


# =============================================================================
# 8. soft_close rules
# =============================================================================

class TestSoftCloseRules:
    """Тесты: soft_close имеет правильные rules."""

    def test_soft_close_has_rules(self):
        """soft_close должен иметь rules."""
        config = SALES_STATES.get("soft_close", {})
        rules = config.get("rules", {})

        assert len(rules) > 0

    def test_price_question_in_soft_close_rules(self):
        """price_question должен быть в rules для soft_close."""
        config = SALES_STATES.get("soft_close", {})
        rules = config.get("rules", {})

        assert "price_question" in rules
        assert rules["price_question"] == "answer_and_offer_continue"


# =============================================================================
# Запуск тестов
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
