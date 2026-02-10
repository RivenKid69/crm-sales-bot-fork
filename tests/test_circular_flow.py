"""
Тесты для Circular Flow модуля.

Покрывает:
- CircularFlowManager
- Интеграцию с StateMachine
- Обработку go_back и correct_info интентов
- Защиту от злоупотреблений
"""

import pytest
import sys
from pathlib import Path

# Добавляем src в PYTHONPATH

from src.state_machine import StateMachine, CircularFlowManager
from src.yaml_config.constants import GO_BACK_INTENTS, SPIN_PHASES, ALLOWED_GOBACKS
from src.feature_flags import flags

@pytest.fixture(autouse=False)
def enable_circular_flow():
    """Fixture для включения circular_flow feature flag на время теста"""
    flags.set_override("circular_flow", True)
    yield
    flags.clear_override("circular_flow")

class TestCircularFlowManagerBasics:
    """Тесты базовой функциональности CircularFlowManager"""

    def test_initial_state(self):
        """Начальное состояние"""
        manager = CircularFlowManager()

        assert manager.goback_count == 0
        assert len(manager.goback_history) == 0

    def test_reset(self):
        """Reset очищает состояние"""
        manager = CircularFlowManager()

        # Выполняем несколько возвратов
        manager.go_back("spin_problem")
        manager.go_back("spin_implication")

        manager.reset()

        assert manager.goback_count == 0
        assert len(manager.goback_history) == 0

    def test_max_gobacks_constant(self):
        """MAX_GOBACKS определена"""
        manager = CircularFlowManager()
        assert manager.MAX_GOBACKS == 2

class TestCanGoBack:
    """Тесты проверки возможности возврата"""

    def test_can_go_back_from_spin_problem(self):
        """Можно вернуться из spin_problem"""
        manager = CircularFlowManager()
        assert manager.can_go_back("spin_problem")

    def test_can_go_back_from_spin_implication(self):
        """Можно вернуться из spin_implication"""
        manager = CircularFlowManager()
        assert manager.can_go_back("spin_implication")

    def test_can_go_back_from_presentation(self):
        """Можно вернуться из presentation"""
        manager = CircularFlowManager()
        assert manager.can_go_back("presentation")

    def test_cannot_go_back_from_greeting(self):
        """Нельзя вернуться из greeting"""
        manager = CircularFlowManager()
        assert not manager.can_go_back("greeting")

    def test_cannot_go_back_from_spin_situation(self):
        """Нельзя вернуться из spin_situation (первая фаза)"""
        manager = CircularFlowManager()
        assert not manager.can_go_back("spin_situation")

    def test_cannot_go_back_after_max(self):
        """Нельзя вернуться после достижения лимита"""
        manager = CircularFlowManager()

        # Выполняем максимум возвратов
        manager.go_back("spin_problem")
        manager.go_back("spin_implication")

        # Третий возврат должен быть заблокирован
        assert not manager.can_go_back("presentation")

class TestGoBack:
    """Тесты выполнения возврата"""

    def test_go_back_returns_previous_state(self):
        """go_back возвращает предыдущее состояние"""
        manager = CircularFlowManager()

        prev_state = manager.go_back("spin_problem")
        assert prev_state == "spin_situation"

    def test_go_back_from_spin_implication(self):
        """Возврат из spin_implication"""
        manager = CircularFlowManager()

        prev_state = manager.go_back("spin_implication")
        assert prev_state == "spin_problem"

    def test_go_back_from_spin_need_payoff(self):
        """Возврат из spin_need_payoff"""
        manager = CircularFlowManager()

        prev_state = manager.go_back("spin_need_payoff")
        assert prev_state == "spin_implication"

    def test_go_back_from_presentation(self):
        """Возврат из presentation"""
        manager = CircularFlowManager()

        prev_state = manager.go_back("presentation")
        assert prev_state == "spin_need_payoff"

    def test_go_back_from_close(self):
        """Возврат из close"""
        manager = CircularFlowManager()

        prev_state = manager.go_back("close")
        assert prev_state == "presentation"

    def test_go_back_increments_count(self):
        """go_back увеличивает счётчик"""
        manager = CircularFlowManager()

        manager.go_back("spin_problem")
        assert manager.goback_count == 1

        manager.go_back("spin_implication")
        assert manager.goback_count == 2

    def test_go_back_records_history(self):
        """go_back записывает историю"""
        manager = CircularFlowManager()

        manager.go_back("spin_problem")

        assert len(manager.goback_history) == 1
        assert manager.goback_history[0] == ("spin_problem", "spin_situation")

    def test_go_back_returns_none_when_blocked(self):
        """go_back возвращает None если заблокирован"""
        manager = CircularFlowManager()

        # Исчерпываем лимит
        manager.go_back("spin_problem")
        manager.go_back("spin_implication")

        # Третий возврат
        result = manager.go_back("presentation")
        assert result is None

    def test_go_back_from_unknown_state(self):
        """go_back из неизвестного состояния"""
        manager = CircularFlowManager()

        result = manager.go_back("unknown_state")
        assert result is None

class TestGetRemainingGobacks:
    """Тесты получения оставшихся возвратов"""

    def test_initial_remaining(self):
        """Изначально все возвраты доступны"""
        manager = CircularFlowManager()
        assert manager.get_remaining_gobacks() == 2

    def test_remaining_after_one(self):
        """После одного возврата"""
        manager = CircularFlowManager()
        manager.go_back("spin_problem")
        assert manager.get_remaining_gobacks() == 1

    def test_remaining_after_all(self):
        """После всех возвратов"""
        manager = CircularFlowManager()
        manager.go_back("spin_problem")
        manager.go_back("spin_implication")
        assert manager.get_remaining_gobacks() == 0

    def test_remaining_never_negative(self):
        """Оставшееся не может быть отрицательным"""
        manager = CircularFlowManager()

        # Пытаемся сделать больше возвратов
        for _ in range(5):
            manager.go_back("spin_problem")

        assert manager.get_remaining_gobacks() >= 0

class TestGetHistory:
    """Тесты получения истории"""

    def test_empty_history_initially(self):
        """Изначально история пуста"""
        manager = CircularFlowManager()
        assert manager.get_history() == []

    def test_history_after_gobacks(self):
        """История после возвратов"""
        manager = CircularFlowManager()
        manager.go_back("spin_problem")
        manager.go_back("spin_implication")

        history = manager.get_history()

        assert len(history) == 2
        assert ("spin_problem", "spin_situation") in history
        assert ("spin_implication", "spin_problem") in history

    def test_get_history_returns_copy(self):
        """get_history возвращает копию"""
        manager = CircularFlowManager()
        manager.go_back("spin_problem")

        history1 = manager.get_history()
        history2 = manager.get_history()

        assert history1 is not history2

class TestGetStats:
    """Тесты получения статистики"""

    def test_stats_structure(self):
        """Структура статистики"""
        manager = CircularFlowManager()

        stats = manager.get_stats()

        assert "goback_count" in stats
        assert "remaining" in stats
        assert "history" in stats

    def test_stats_values(self):
        """Значения статистики"""
        manager = CircularFlowManager()
        manager.go_back("spin_problem")

        stats = manager.get_stats()

        assert stats["goback_count"] == 1
        assert stats["remaining"] == 1
        assert len(stats["history"]) == 1

class TestStateMachineIntegration:
    """Тесты интеграции с StateMachine"""

    def test_state_machine_has_circular_flow(self):
        """StateMachine содержит CircularFlowManager"""
        sm = StateMachine()
        assert hasattr(sm, "circular_flow")
        assert isinstance(sm.circular_flow, CircularFlowManager)

    def test_state_machine_reset_resets_circular_flow(self):
        """reset StateMachine сбрасывает CircularFlowManager"""
        sm = StateMachine()

        # Устанавливаем состояние
        sm.state = "spin_problem"
        sm.circular_flow.go_back("spin_problem")

        sm.reset()

        assert sm.circular_flow.goback_count == 0

    def test_process_returns_circular_flow_stats(self):
        """process возвращает статистику circular_flow"""
        sm = StateMachine()

        result = sm.process("greeting")

        assert "circular_flow" in result
        assert "goback_count" in result["circular_flow"]

class TestGoBackIntentHandling:
    """Тесты обработки go_back интента"""

    def test_go_back_intent_defined(self):
        """go_back интент определён"""
        assert "go_back" in GO_BACK_INTENTS

    def test_correct_info_intent_defined(self):
        """correct_info интент определён"""
        assert "correct_info" in GO_BACK_INTENTS

    @pytest.mark.skip(reason="StateMachine.process() is deprecated. go_back is tested via DialogueOrchestrator in test_blackboard_bugfixes.py")
    def test_go_back_intent_triggers_goback(self, enable_circular_flow):
        """go_back интент триггерит возврат (при включённом флаге)"""
        sm = StateMachine()

        # Переходим в spin_problem
        sm.state = "spin_problem"

        # Обрабатываем go_back
        result = sm.process("go_back")

        assert result["action"] == "go_back"
        assert result["next_state"] == "spin_situation"

    @pytest.mark.skip(reason="StateMachine.process() is deprecated. go_back is tested via DialogueOrchestrator in test_blackboard_bugfixes.py")
    def test_correct_info_intent_triggers_goback(self, enable_circular_flow):
        """correct_info интент триггерит возврат (при включённом флаге)"""
        sm = StateMachine()

        # Переходим в spin_implication
        sm.state = "spin_implication"

        # Обрабатываем correct_info
        result = sm.process("correct_info")

        assert result["action"] == "go_back"
        assert result["next_state"] == "spin_problem"

    def test_go_back_blocked_after_limit(self, enable_circular_flow):
        """go_back блокируется после лимита (при включённом флаге)"""
        sm = StateMachine()

        # Исчерпываем лимит
        sm.state = "spin_problem"
        sm.process("go_back")

        sm.state = "spin_problem"
        sm.process("go_back")

        # Третий раз — не работает
        sm.state = "spin_problem"
        result = sm.process("go_back")

        # Должен продолжить обычную обработку
        assert result["action"] != "go_back"

    def test_go_back_from_greeting_ignored(self, enable_circular_flow):
        """go_back из greeting игнорируется (при включённом флаге)"""
        sm = StateMachine()
        sm.state = "greeting"

        result = sm.process("go_back")

        # go_back не возможен из greeting
        assert result["action"] != "go_back"

    def test_go_back_disabled_by_default(self):
        """go_back не работает когда feature flag выключен (по умолчанию)"""
        # Убеждаемся что флаг выключен
        flags.clear_override("circular_flow")

        sm = StateMachine()
        sm.state = "spin_problem"

        result = sm.process("go_back")

        # go_back НЕ должен сработать, так как флаг выключен
        assert result["action"] != "go_back"

class TestAllowedGobacks:
    """Тесты разрешённых переходов"""

    def test_all_spin_phases_have_goback(self):
        """Все SPIN-фазы (кроме situation) имеют возврат"""
        # ALLOWED_GOBACKS is now loaded from yaml_config/constants.yaml
        assert "spin_problem" in ALLOWED_GOBACKS
        assert "spin_implication" in ALLOWED_GOBACKS
        assert "spin_need_payoff" in ALLOWED_GOBACKS

    def test_goback_chain(self):
        """Цепочка возвратов правильная"""
        # ALLOWED_GOBACKS is now loaded from yaml_config/constants.yaml
        chain = []
        state = "presentation"

        while state in ALLOWED_GOBACKS:
            next_state = ALLOWED_GOBACKS[state]
            chain.append((state, next_state))
            state = next_state

        # Проверяем цепочку
        expected = [
            ("presentation", "spin_need_payoff"),
            ("spin_need_payoff", "spin_implication"),
            ("spin_implication", "spin_problem"),
            ("spin_problem", "spin_situation"),
        ]

        assert chain == expected

class TestEdgeCases:
    """Тесты граничных случаев"""

    @pytest.mark.skip(reason="StateMachine.process() is deprecated. go_back is tested via DialogueOrchestrator in test_blackboard_bugfixes.py")
    def test_multiple_gobacks_same_state(self, enable_circular_flow):
        """Несколько возвратов из одного состояния (при включённом флаге)"""
        sm = StateMachine()

        # Первый возврат
        sm.state = "spin_problem"
        sm.process("go_back")
        assert sm.state == "spin_situation"

        # Возвращаемся в spin_problem и снова назад
        sm.state = "spin_problem"
        sm.process("go_back")

        # Лимит должен быть исчерпан
        sm.state = "spin_problem"
        result = sm.process("go_back")
        assert result["action"] != "go_back"

    def test_go_back_preserves_collected_data(self, enable_circular_flow):
        """go_back сохраняет собранные данные (при включённом флаге)"""
        sm = StateMachine()

        # Собираем данные
        sm.collected_data = {"company_size": 15, "pain_point": "проблема"}
        sm.state = "spin_problem"

        # Возвращаемся назад
        result = sm.process("go_back")

        # Данные сохранены
        assert result["collected_data"]["company_size"] == 15
        assert result["collected_data"]["pain_point"] == "проблема"

    def test_handle_objection_goback(self):
        """Возврат из handle_objection"""
        manager = CircularFlowManager()

        prev_state = manager.go_back("handle_objection")
        assert prev_state == "presentation"

class TestIntegrationScenarios:
    """Интеграционные сценарии"""

    @pytest.mark.skip(reason="StateMachine.process() is deprecated. go_back is tested via DialogueOrchestrator in test_blackboard_bugfixes.py")
    def test_typical_correction_flow(self, enable_circular_flow):
        """Типичный flow исправления (при включённом флаге)"""
        sm = StateMachine()

        # Клиент даёт неправильную информацию
        sm.state = "spin_situation"
        sm.process("situation_provided", {"company_size": 5})

        # Переходим в spin_problem
        sm.state = "spin_problem"

        # Клиент хочет исправить
        result = sm.process("correct_info")

        assert result["action"] == "go_back"
        assert result["next_state"] == "spin_situation"
        assert sm.circular_flow.goback_count == 1

    @pytest.mark.skip(reason="StateMachine.process() is deprecated. go_back is tested via DialogueOrchestrator in test_blackboard_bugfixes.py")
    def test_goback_then_continue_normally(self, enable_circular_flow):
        """Возврат и продолжение нормально (при включённом флаге)"""
        sm = StateMachine()

        # Переходим в spin_problem
        sm.state = "spin_problem"

        # Возвращаемся
        sm.process("go_back")
        assert sm.state == "spin_situation"

        # Продолжаем нормально
        result = sm.process("situation_provided")
        # Должен продолжить обычную обработку

    @pytest.mark.skip(reason="StateMachine.process() is deprecated. go_back is tested via DialogueOrchestrator in test_blackboard_bugfixes.py")
    def test_full_flow_with_gobacks(self, enable_circular_flow):
        """Полный flow с возвратами (при включённом флаге)"""
        sm = StateMachine()

        # Greeting -> spin_situation
        sm.state = "greeting"
        sm.process("greeting")

        # spin_situation -> spin_problem
        sm.state = "spin_situation"
        sm.process("situation_provided", {"company_size": 10})

        sm.state = "spin_problem"

        # Возврат
        sm.process("go_back")
        assert sm.state == "spin_situation"

        # Снова вперёд
        sm.state = "spin_problem"

        # Второй возврат
        sm.process("correct_info")
        assert sm.state == "spin_situation"

        # Третий возврат — заблокирован
        sm.state = "spin_problem"
        result = sm.process("go_back")
        assert result["action"] != "go_back"

        # Проверяем статистику
        assert sm.circular_flow.goback_count == 2

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
