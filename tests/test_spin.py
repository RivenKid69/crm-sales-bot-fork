"""
Тесты для SPIN-методологии продаж
"""

import pytest
import sys
sys.path.insert(0, 'src')

from classifier import HybridClassifier, DataExtractor
from state_machine import StateMachine, SPIN_PHASES, SPIN_STATES


class TestSPINStateMachine:
    """Тесты для SPIN state machine"""

    def setup_method(self):
        self.sm = StateMachine()

    def test_initial_state_is_greeting(self):
        """Начальное состояние — greeting"""
        assert self.sm.state == "greeting"
        assert self.sm.spin_phase is None

    def test_greeting_to_spin_situation_on_interest(self):
        """При проявлении интереса переходим в spin_situation"""
        result = self.sm.process("agreement", {})
        assert result["next_state"] == "spin_situation"
        assert result["spin_phase"] == "situation"

    def test_spin_situation_to_problem_with_data(self):
        """С данными о размере переходим из situation в problem"""
        # Сначала переходим в spin_situation
        self.sm.process("agreement", {})

        # Теперь предоставляем данные о ситуации
        result = self.sm.process("info_provided", {"company_size": 10})

        assert result["next_state"] == "spin_problem"
        assert result["spin_phase"] == "problem"
        assert result["collected_data"]["company_size"] == 10

    def test_spin_problem_to_implication_with_pain(self):
        """С болью переходим из problem в implication"""
        # Setup: переходим в spin_problem
        self.sm.process("agreement", {})
        self.sm.process("info_provided", {"company_size": 10})

        # Предоставляем информацию о боли
        result = self.sm.process("info_provided", {"pain_point": "теряем клиентов"})

        assert result["next_state"] == "spin_implication"
        assert result["spin_phase"] == "implication"
        assert result["collected_data"]["pain_point"] == "теряем клиентов"

    def test_spin_implication_to_need_payoff_on_agreement(self):
        """При согласии переходим из implication в need_payoff"""
        # Setup: переходим в spin_implication
        self.sm.process("agreement", {})
        self.sm.process("info_provided", {"company_size": 10})
        self.sm.process("info_provided", {"pain_point": "теряем клиентов"})

        # Клиент соглашается с последствиями
        result = self.sm.process("agreement", {})

        assert result["next_state"] == "spin_need_payoff"
        assert result["spin_phase"] == "need_payoff"

    def test_spin_need_payoff_to_presentation_on_agreement(self):
        """При согласии переходим из need_payoff в presentation"""
        # Setup: полный SPIN flow
        self.sm.process("agreement", {})
        self.sm.process("info_provided", {"company_size": 10})
        self.sm.process("info_provided", {"pain_point": "теряем клиентов"})
        self.sm.process("agreement", {})

        # Клиент подтверждает ценность
        result = self.sm.process("agreement", {})

        assert result["next_state"] == "presentation"
        assert result["spin_phase"] is None  # presentation не SPIN фаза

    def test_full_spin_flow(self):
        """Полный SPIN flow: greeting → S → P → I → N → presentation"""
        states = []
        phases = []

        # Greeting
        result = self.sm.process("greeting", {})
        states.append(result["next_state"])
        phases.append(result["spin_phase"])

        # Interest → Situation
        result = self.sm.process("price_question", {})
        states.append(result["next_state"])
        phases.append(result["spin_phase"])

        # Situation → Problem
        result = self.sm.process("info_provided", {"company_size": 15})
        states.append(result["next_state"])
        phases.append(result["spin_phase"])

        # Problem → Implication
        result = self.sm.process("info_provided", {"pain_point": "путаница в остатках"})
        states.append(result["next_state"])
        phases.append(result["spin_phase"])

        # Implication → Need-Payoff
        result = self.sm.process("implication_acknowledged", {"pain_impact": "теряем ~5 клиентов"})
        states.append(result["next_state"])
        phases.append(result["spin_phase"])

        # Need-Payoff → Presentation
        result = self.sm.process("need_expressed", {"desired_outcome": "автоматизация"})
        states.append(result["next_state"])
        phases.append(result["spin_phase"])

        # Проверяем последовательность
        assert "spin_situation" in states
        assert "spin_problem" in states
        assert "spin_implication" in states
        assert "spin_need_payoff" in states
        assert "presentation" in states

    def test_rejection_at_any_spin_phase_goes_to_soft_close(self):
        """Отказ на любой фазе SPIN → soft_close"""
        # Переходим в spin_situation
        self.sm.process("agreement", {})

        # Отказ
        result = self.sm.process("rejection", {})

        assert result["next_state"] == "soft_close"
        # soft_close не финальное — клиент может передумать и вернуться


class TestSPINDataExtraction:
    """Тесты для извлечения SPIN-данных"""

    def setup_method(self):
        self.extractor = DataExtractor()

    def test_extract_current_tools_excel(self):
        """Извлекаем текущий инструмент: Excel"""
        result = self.extractor.extract("Мы ведём всё в Excel")
        assert result.get("current_tools") == "Excel"

    def test_extract_current_tools_1c(self):
        """Извлекаем текущий инструмент: 1С"""
        result = self.extractor.extract("Работаем в 1С")
        assert result.get("current_tools") == "1С"

    def test_extract_current_tools_manual(self):
        """Извлекаем текущий инструмент: вручную"""
        result = self.extractor.extract("Делаем всё вручную")
        assert result.get("current_tools") == "вручную"

    def test_extract_business_type_retail(self):
        """Извлекаем тип бизнеса: розница"""
        result = self.extractor.extract("У нас небольшой магазин")
        assert result.get("business_type") == "розничная торговля"

    def test_extract_business_type_restaurant(self):
        """Извлекаем тип бизнеса: общепит"""
        result = self.extractor.extract("У нас сеть ресторанов")
        assert result.get("business_type") == "общепит"

    def test_extract_pain_impact_clients_lost(self):
        """Извлекаем последствия: потерянные клиенты"""
        context = {"spin_phase": "implication"}
        result = self.extractor.extract("Теряем примерно 10 клиентов в месяц", context)
        assert "10" in result.get("pain_impact", "")

    def test_extract_pain_impact_time_spent(self):
        """Извлекаем последствия: потраченное время"""
        context = {"spin_phase": "implication"}
        result = self.extractor.extract("Тратим 3 часа каждый день", context)
        assert "3" in result.get("pain_impact", "")

    def test_extract_desired_outcome(self):
        """Извлекаем желаемый результат"""
        context = {"spin_phase": "need_payoff"}
        result = self.extractor.extract("Хотим автоматизировать процессы", context)
        assert result.get("desired_outcome") is not None
        assert result.get("value_acknowledged") == True

    def test_extract_high_interest(self):
        """Извлекаем высокий интерес"""
        result = self.extractor.extract("Очень нужно, хотим срочно")
        assert result.get("high_interest") == True


class TestSPINClassification:
    """Тесты для SPIN-классификации"""

    def setup_method(self):
        self.classifier = HybridClassifier()

    def test_situation_provided_intent_in_situation_phase(self):
        """В фазе situation информация о ситуации классифицируется как situation_provided"""
        context = {"spin_phase": "situation"}
        result = self.classifier.classify("У нас 10 человек, работаем в Excel", context)

        assert result["intent"] == "situation_provided"
        assert result["extracted_data"].get("company_size") == 10
        assert result["extracted_data"].get("current_tools") == "Excel"

    def test_problem_revealed_intent_in_problem_phase(self):
        """В фазе problem информация о боли классифицируется как problem_revealed"""
        context = {"spin_phase": "problem"}
        result = self.classifier.classify("Теряем клиентов, потому что забываем перезвонить", context)

        assert result["intent"] == "problem_revealed"
        assert result["extracted_data"].get("pain_point") is not None

    def test_implication_acknowledged_in_implication_phase(self):
        """В фазе implication осознание последствий классифицируется как implication_acknowledged"""
        context = {"spin_phase": "implication", "missing_data": ["pain_impact"]}
        result = self.classifier.classify("Да, теряем примерно 5 клиентов в месяц", context)

        assert result["intent"] == "implication_acknowledged"
        assert result["extracted_data"].get("pain_impact") is not None

    def test_need_expressed_in_need_payoff_phase(self):
        """В фазе need_payoff выражение желания классифицируется как need_expressed"""
        context = {"spin_phase": "need_payoff", "missing_data": ["desired_outcome"]}
        result = self.classifier.classify("Да, это помогло бы нам", context)

        assert result["intent"] == "need_expressed"
        assert result["extracted_data"].get("value_acknowledged") == True

    def test_question_intents_still_work_in_spin(self):
        """Вопросы о цене/функциях работают в SPIN-фазах"""
        context = {"spin_phase": "situation"}
        result = self.classifier.classify("Сколько это стоит?", context)

        assert result["intent"] == "price_question"


class TestSPINPhases:
    """Тесты для констант SPIN"""

    def test_spin_phases_order(self):
        """Проверяем порядок SPIN-фаз"""
        assert SPIN_PHASES == ["situation", "problem", "implication", "need_payoff"]

    def test_spin_states_mapping(self):
        """Проверяем маппинг фаз на состояния"""
        assert SPIN_STATES["situation"] == "spin_situation"
        assert SPIN_STATES["problem"] == "spin_problem"
        assert SPIN_STATES["implication"] == "spin_implication"
        assert SPIN_STATES["need_payoff"] == "spin_need_payoff"


class TestSPINEdgeCases:
    """Тесты для граничных случаев SPIN"""

    def setup_method(self):
        self.sm = StateMachine()
        self.classifier = HybridClassifier()

    def test_skip_implication_on_high_interest(self):
        """При высоком интересе через agreement можно пропустить implication"""
        # Setup: переходим в spin_problem
        self.sm.process("agreement", {})
        self.sm.process("info_provided", {"company_size": 10})

        # Переходим в spin_problem
        self.sm.update_data({"pain_point": "теряем клиентов"})
        self.sm.state = "spin_problem"

        # Клиент уже готов (high_interest) и соглашается
        self.sm.update_data({"high_interest": True})
        result = self.sm.process("agreement", {})

        # agreement из spin_problem с high_interest ведёт в presentation
        # (пропускаем I и N фазы)
        assert result["next_state"] == "presentation"

    def test_price_question_deflects_in_spin(self):
        """Вопрос о цене в SPIN-фазе мягко отклоняется через deflect_and_continue"""
        # Переходим в spin_situation
        self.sm.process("agreement", {})

        # Спрашиваем о цене
        result = self.sm.process("price_question", {})

        # Должен остаться в spin_situation и мягко перенаправить разговор
        # (rules имеют приоритет над QUESTION_INTENTS)
        assert result["action"] == "deflect_and_continue"
        assert result["next_state"] == "spin_situation"

    def test_combined_situation_data(self):
        """Одно сообщение может содержать несколько данных о ситуации"""
        context = {"spin_phase": "situation"}
        result = self.classifier.classify(
            "У нас магазин, 5 продавцов, ведём всё в Excel",
            context
        )

        extracted = result["extracted_data"]
        assert extracted.get("company_size") == 5
        assert extracted.get("current_tools") == "Excel"
        assert extracted.get("business_type") == "розничная торговля"


class TestNoProblemNoNeedIntents:
    """Тесты для интентов no_problem и no_need (проблема #1)"""

    def setup_method(self):
        self.sm = StateMachine()
        self.classifier = HybridClassifier()

    def test_no_problem_in_spin_problem_transitions_to_implication(self):
        """При 'нет' в фазе problem (no_problem) переходим в implication"""
        # Setup: переходим в spin_problem
        self.sm.process("agreement", {})
        self.sm.process("info_provided", {"company_size": 10})
        assert self.sm.state == "spin_problem"

        # Клиент говорит "нет проблем"
        result = self.sm.process("no_problem", {})

        # Должен перейти в spin_implication (чтобы показать скрытые последствия)
        assert result["next_state"] == "spin_implication"
        assert result["spin_phase"] == "implication"

    def test_no_need_in_spin_need_payoff_transitions_to_soft_close(self):
        """При 'нет' в фазе need_payoff (no_need) переходим в soft_close"""
        # Setup: полный путь до spin_need_payoff
        self.sm.process("agreement", {})
        self.sm.process("info_provided", {"company_size": 10})
        self.sm.process("info_provided", {"pain_point": "теряем клиентов"})
        self.sm.process("implication_acknowledged", {"pain_impact": "5 клиентов"})
        assert self.sm.state == "spin_need_payoff"

        # Клиент не видит ценности
        result = self.sm.process("no_need", {})

        # Должен перейти в soft_close (мягкое завершение)
        assert result["next_state"] == "soft_close"

    def test_no_problem_classified_correctly_in_problem_phase(self):
        """Классификатор возвращает no_problem при 'нет' в фазе problem"""
        context = {"spin_phase": "problem"}
        result = self.classifier.classify("нет", context)

        assert result["intent"] == "no_problem"

    def test_no_need_classified_correctly_in_need_payoff_phase(self):
        """Классификатор возвращает no_need при 'нет' в фазе need_payoff"""
        context = {"spin_phase": "need_payoff"}
        result = self.classifier.classify("нет", context)

        assert result["intent"] == "no_need"


class TestSpinPhaseNotSkipped:
    """Тесты что spin_implication и spin_need_payoff не пропускаются (проблема #2)"""

    def setup_method(self):
        self.sm = StateMachine()

    def test_unclear_in_spin_implication_stays_in_phase(self):
        """При unclear в spin_implication остаёмся в фазе"""
        # Setup: переходим в spin_implication
        self.sm.process("agreement", {})
        self.sm.process("info_provided", {"company_size": 10})
        self.sm.process("info_provided", {"pain_point": "теряем клиентов"})
        assert self.sm.state == "spin_implication"

        # Клиент даёт неясный ответ
        result = self.sm.process("unclear", {})

        # Должен остаться в spin_implication и переспросить
        assert result["next_state"] == "spin_implication"
        assert result["action"] == "probe_implication"

    def test_unclear_in_spin_need_payoff_stays_in_phase(self):
        """При unclear в spin_need_payoff остаёмся в фазе"""
        # Setup: полный путь до spin_need_payoff
        self.sm.process("agreement", {})
        self.sm.process("info_provided", {"company_size": 10})
        self.sm.process("info_provided", {"pain_point": "теряем клиентов"})
        self.sm.process("implication_acknowledged", {"pain_impact": "5 клиентов"})
        assert self.sm.state == "spin_need_payoff"

        # Клиент даёт неясный ответ
        result = self.sm.process("unclear", {})

        # Должен остаться в spin_need_payoff и переспросить
        assert result["next_state"] == "spin_need_payoff"
        assert result["action"] == "probe_need_payoff"

    def test_small_talk_in_spin_implication_stays_in_phase(self):
        """При small_talk в spin_implication остаёмся в фазе"""
        # Setup: переходим в spin_implication
        self.sm.process("agreement", {})
        self.sm.process("info_provided", {"company_size": 10})
        self.sm.process("info_provided", {"pain_point": "теряем клиентов"})
        assert self.sm.state == "spin_implication"

        # Клиент отклоняется на small talk
        result = self.sm.process("small_talk", {})

        # Должен остаться в spin_implication
        assert result["next_state"] == "spin_implication"
        assert result["action"] == "small_talk_and_continue"

    def test_gratitude_in_spin_need_payoff_stays_in_phase(self):
        """При gratitude в spin_need_payoff остаёмся в фазе"""
        # Setup: полный путь до spin_need_payoff
        self.sm.process("agreement", {})
        self.sm.process("info_provided", {"company_size": 10})
        self.sm.process("info_provided", {"pain_point": "теряем клиентов"})
        self.sm.process("implication_acknowledged", {"pain_impact": "5 клиентов"})
        assert self.sm.state == "spin_need_payoff"

        # Клиент выражает благодарность
        result = self.sm.process("gratitude", {})

        # Должен остаться в spin_need_payoff
        assert result["next_state"] == "spin_need_payoff"
        assert result["action"] == "acknowledge_and_continue"


class TestProbedFlagsSet:
    """Тесты что probed-флаги устанавливаются при входе в SPIN-фазы"""

    def setup_method(self):
        self.sm = StateMachine()

    def test_implication_probed_set_on_entering_spin_implication(self):
        """implication_probed устанавливается при входе в spin_implication"""
        # Setup: переходим в spin_implication
        self.sm.process("agreement", {})
        self.sm.process("info_provided", {"company_size": 10})

        # До перехода флаг не установлен
        assert "implication_probed" not in self.sm.collected_data

        # Переходим в spin_implication
        result = self.sm.process("info_provided", {"pain_point": "теряем клиентов"})

        # Флаг должен быть установлен
        assert result["next_state"] == "spin_implication"
        assert self.sm.collected_data.get("implication_probed") == True

    def test_need_payoff_probed_set_on_entering_spin_need_payoff(self):
        """need_payoff_probed устанавливается при входе в spin_need_payoff"""
        # Setup: полный путь до spin_implication
        self.sm.process("agreement", {})
        self.sm.process("info_provided", {"company_size": 10})
        self.sm.process("info_provided", {"pain_point": "теряем клиентов"})
        assert self.sm.state == "spin_implication"

        # До перехода флаг не установлен
        assert "need_payoff_probed" not in self.sm.collected_data

        # Переходим в spin_need_payoff
        result = self.sm.process("implication_acknowledged", {"pain_impact": "5 клиентов"})

        # Флаг должен быть установлен
        assert result["next_state"] == "spin_need_payoff"
        assert self.sm.collected_data.get("need_payoff_probed") == True

    def test_implication_probed_allows_data_complete_transition(self):
        """После установки implication_probed можно перейти по data_complete"""
        # Setup: переходим в spin_implication
        self.sm.process("agreement", {})
        self.sm.process("info_provided", {"company_size": 10})
        self.sm.process("info_provided", {"pain_point": "теряем клиентов"})
        assert self.sm.state == "spin_implication"

        # Флаг установлен
        assert self.sm.collected_data.get("implication_probed") == True

        # Теперь любой интент без явного правила перейдёт по data_complete
        # (потому что implication_probed в required_data и он установлен)
        result = self.sm.process("agreement", {})

        assert result["next_state"] == "spin_need_payoff"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
