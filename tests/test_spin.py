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
        assert result["is_final"] == True


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
        """При высоком интересе можно пропустить implication"""
        # Setup: переходим в spin_problem
        self.sm.process("agreement", {})
        self.sm.process("info_provided", {"company_size": 10})

        # Клиент уже готов (high_interest) и говорит о боли
        self.sm.update_data({"high_interest": True})
        result = self.sm.process("info_provided", {"pain_point": "теряем клиентов"})

        # Должен перейти в need_payoff, пропуская implication
        # (или в presentation если всё собрано)
        assert result["next_state"] in ["spin_need_payoff", "presentation"]

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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
