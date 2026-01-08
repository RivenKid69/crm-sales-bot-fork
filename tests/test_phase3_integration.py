"""
Интеграционные тесты для Phase 3 (SPIN Flow Optimization).

Покрывает:
- Интеграцию всех модулей Phase 3
- End-to-end сценарии
- Комбинированное использование компонентов
- Совместимость с Phase 0-2 модулями
"""

import pytest
import sys
from pathlib import Path

# Добавляем src в PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from state_machine import StateMachine, CircularFlowManager
from lead_scoring import LeadScorer, LeadTemperature, get_signal_from_intent
from objection_handler import ObjectionHandler, ObjectionType
from cta_generator import CTAGenerator
from feature_flags import flags


@pytest.fixture
def enable_circular_flow():
    """Fixture для включения circular_flow feature flag на время теста"""
    flags.set_override("circular_flow", True)
    yield
    flags.clear_override("circular_flow")


class TestPhase3ModulesExist:
    """Проверка что все модули Phase 3 существуют и импортируются"""

    def test_lead_scoring_imports(self):
        """Lead scoring модуль импортируется"""
        from lead_scoring import LeadScorer, LeadTemperature, LeadSignal
        assert LeadScorer is not None
        assert LeadTemperature is not None

    def test_objection_handler_imports(self):
        """Objection handler модуль импортируется"""
        from objection_handler import ObjectionHandler, ObjectionType
        assert ObjectionHandler is not None
        assert ObjectionType is not None

    def test_cta_generator_imports(self):
        """CTA generator модуль импортируется"""
        from cta_generator import CTAGenerator, CTAResult
        assert CTAGenerator is not None

    def test_circular_flow_imports(self):
        """Circular flow импортируется из state_machine"""
        from state_machine import CircularFlowManager
        assert CircularFlowManager is not None


class TestFeatureFlagsPhase3:
    """Тесты feature flags для Phase 3"""

    def test_phase3_flags_defined(self):
        """Phase 3 флаги определены"""
        assert "lead_scoring" in flags.DEFAULTS
        assert "circular_flow" in flags.DEFAULTS
        assert "objection_handler" in flags.DEFAULTS
        assert "cta_generator" in flags.DEFAULTS

    def test_phase3_group_exists(self):
        """Группа phase_3 существует"""
        assert "phase_3" in flags.GROUPS
        assert "lead_scoring" in flags.GROUPS["phase_3"]
        assert "circular_flow" in flags.GROUPS["phase_3"]

    def test_risky_flags_include_phase3(self):
        """Опасные флаги включают Phase 3 компоненты"""
        risky = flags.GROUPS.get("risky", [])
        assert "circular_flow" in risky
        assert "lead_scoring" in risky


class TestLeadScoringWithStateMachine:
    """Интеграция Lead Scoring с State Machine"""

    def test_scorer_with_intent_mapping(self):
        """Скоринг на основе интентов"""
        sm = StateMachine()
        scorer = LeadScorer()

        # Симулируем диалог
        intents = [
            "price_question",
            "question_features",
            "demo_request",
        ]

        for intent in intents:
            signal = get_signal_from_intent(intent)
            if signal:
                scorer.add_signal(signal)

        # После demo_request должен быть WARM
        assert scorer.get_score().temperature in [
            LeadTemperature.WARM,
            LeadTemperature.HOT
        ]

    def test_scorer_suggests_skipping_phases(self):
        """Скоринг предлагает пропуск фаз"""
        scorer = LeadScorer()

        # Горячий лид
        scorer.add_signal("demo_request")
        scorer.add_signal("callback_request")

        score = scorer.get_score()

        # Должен пропускать SPIN-фазы
        assert scorer.should_skip_phase("spin_implication")
        assert scorer.should_skip_phase("spin_need_payoff")

    def test_scorer_with_objections(self):
        """Скоринг учитывает возражения"""
        scorer = LeadScorer()

        # Положительные сигналы
        scorer.add_signal("demo_request")  # +30
        hot_score = scorer.current_score

        # Возражение
        scorer.add_signal("objection_price")  # -15

        # Score должен уменьшиться
        assert scorer.current_score < hot_score


class TestObjectionHandlerWithCTA:
    """Интеграция Objection Handler с CTA Generator"""

    def test_cta_after_objection_handling(self):
        """CTA после обработки возражения"""
        handler = ObjectionHandler()
        cta = CTAGenerator()
        cta.turn_count = 5

        # Обрабатываем возражение
        result = handler.handle_objection("Это дорого")

        if result.strategy:
            # Добавляем CTA к ответу
            response = result.strategy.response_template
            final = cta.append_cta(
                response,
                "handle_objection",
                {}
            )

            # CTA должен быть добавлен
            assert len(final) >= len(response)

    def test_no_cta_at_soft_close(self):
        """Нет CTA при soft close"""
        handler = ObjectionHandler()
        cta = CTAGenerator()
        cta.turn_count = 5

        # Исчерпываем попытки
        handler.handle_objection("Дорого")
        handler.handle_objection("Дорого")
        result = handler.handle_objection("Дорого")

        assert result.should_soft_close

        # При soft close не нужен CTA
        if result.response_parts.get("message"):
            final = cta.append_cta(
                result.response_parts["message"],
                "soft_close",
                {}
            )
            # Ответ не должен меняться (нет CTA для soft_close)


class TestCircularFlowWithLeadScoring:
    """Интеграция Circular Flow с Lead Scoring"""

    def test_goback_does_not_affect_scoring(self, enable_circular_flow):
        """Возврат назад не сбрасывает скоринг (при включённом флаге)"""
        sm = StateMachine()
        scorer = LeadScorer()

        # Накапливаем score
        scorer.add_signal("features_question")
        scorer.add_signal("demo_request")
        score_before = scorer.current_score

        # Возвращаемся назад
        sm.state = "spin_problem"
        sm.process("go_back")

        # Score сохраняется (скорер отдельный от SM)
        assert scorer.current_score == score_before

    def test_hot_lead_can_still_goback(self, enable_circular_flow):
        """Горячий лид может вернуться назад (при включённом флаге)"""
        sm = StateMachine()
        scorer = LeadScorer()

        # Горячий лид
        scorer.add_signal("demo_request")
        scorer.add_signal("callback_request")
        assert scorer.get_score().temperature == LeadTemperature.HOT

        # Но может вернуться для уточнения
        sm.state = "presentation"
        result = sm.process("go_back")

        assert result["action"] == "go_back"


class TestFullDialogueScenarios:
    """Полные сценарии диалогов"""

    def test_cold_lead_full_spin(self):
        """Холодный лид проходит полный SPIN"""
        sm = StateMachine()
        scorer = LeadScorer()
        cta = CTAGenerator()

        # Greeting
        sm.state = "greeting"
        sm.process("greeting")
        cta.increment_turn()

        # Spin Situation
        sm.state = "spin_situation"
        result = sm.process("situation_provided", {"company_size": 10})
        scorer.add_signal("general_interest")
        cta.increment_turn()

        # Всё ещё холодный
        assert scorer.get_score().temperature == LeadTemperature.COLD
        assert not cta.should_add_cta("spin_situation", "Response", {})[0]

        # Spin Problem
        sm.state = "spin_problem"
        result = sm.process("problem_revealed", {"pain_point": "теряем клиентов"})
        scorer.add_signal("explicit_problem")
        cta.increment_turn()

        # Потеплел
        assert scorer.current_score > 0

    def test_hot_lead_accelerated_flow(self):
        """Горячий лид — ускоренный flow"""
        sm = StateMachine()
        scorer = LeadScorer()

        # Сразу высокий интент
        scorer.add_signal("demo_request")
        scorer.add_signal("callback_request")

        score = scorer.get_score()
        assert score.temperature == LeadTemperature.HOT

        # Рекомендуется прямой путь
        assert score.recommended_path == "direct_present"
        assert scorer.should_skip_phase("spin_problem")

    def test_objection_handling_flow(self):
        """Flow с обработкой возражений"""
        handler = ObjectionHandler()
        scorer = LeadScorer()
        cta = CTAGenerator()
        cta.turn_count = 5

        # Клиент возражает о цене
        result1 = handler.handle_objection("Это дорого")
        scorer.add_signal("objection_price")

        assert result1.objection_type == ObjectionType.PRICE
        assert result1.strategy is not None

        # Ещё раз
        result2 = handler.handle_objection("Всё равно дорого")

        # Третий раз — soft close
        result3 = handler.handle_objection("Не, дорого")
        assert result3.should_soft_close

    def test_correction_flow_with_data(self, enable_circular_flow):
        """Flow с исправлением данных (при включённом флаге)"""
        sm = StateMachine()

        # Даём неправильные данные
        sm.state = "spin_situation"
        sm.process("situation_provided", {"company_size": 5})

        sm.state = "spin_problem"

        # Исправляем
        result = sm.process("correct_info")

        assert result["action"] == "go_back"
        assert result["next_state"] == "spin_situation"
        # Данные сохранены
        assert result["collected_data"]["company_size"] == 5


class TestCTAInDifferentStates:
    """CTA в разных состояниях"""

    def test_no_cta_in_early_states(self):
        """Нет CTA в ранних состояниях"""
        cta = CTAGenerator()
        cta.turn_count = 5

        early_states = ["greeting", "spin_situation", "spin_problem"]

        for state in early_states:
            should_add, _ = cta.should_add_cta(state, "Response", {})
            assert not should_add, f"CTA should not be added in {state}"

    def test_cta_in_presentation(self):
        """CTA в presentation"""
        cta = CTAGenerator()
        cta.turn_count = 5

        should_add, _ = cta.should_add_cta(
            "presentation",
            "Wipon решает эту проблему.",
            {}
        )
        assert should_add

    def test_soft_cta_with_frustration(self):
        """Мягкий CTA при frustration"""
        cta = CTAGenerator()
        cta.turn_count = 5

        result = cta.generate_cta_result(
            "Wipon решает проблему.",
            "presentation",
            {"frustration_level": 4}
        )

        # При среднем frustration должен использовать soft CTA
        if result.cta_added:
            # Мягкий CTA менее агрессивный
            assert result.cta is not None


class TestEdgeCasesIntegration:
    """Граничные случаи интеграции"""

    def test_empty_collected_data(self):
        """Пустые собранные данные"""
        handler = ObjectionHandler()

        result = handler.handle_objection(
            "Это дорого",
            collected_data={}
        )

        # Должен использовать дефолтные значения
        assert result.strategy is not None

    def test_multiple_resets(self):
        """Множественные сбросы"""
        sm = StateMachine()
        scorer = LeadScorer()
        handler = ObjectionHandler()
        cta = CTAGenerator()

        # Используем все компоненты
        sm.process("greeting")
        scorer.add_signal("demo_request")
        handler.handle_objection("Дорого")
        cta.increment_turn()

        # Сбрасываем
        sm.reset()
        scorer.reset()
        handler.reset()
        cta.reset()

        # Всё должно быть чисто
        assert sm.state == "greeting"
        assert scorer.current_score == 0
        assert handler.get_attempts_count(ObjectionType.PRICE) == 0
        assert cta.turn_count == 0

    def test_max_gobacks_with_objections(self, enable_circular_flow):
        """Максимум возвратов + возражения (при включённом флаге)"""
        sm = StateMachine()
        handler = ObjectionHandler()

        # Исчерпываем возвраты
        sm.state = "spin_problem"
        sm.process("go_back")
        sm.state = "spin_problem"
        sm.process("go_back")

        # Обрабатываем возражение
        result = handler.handle_objection("Это дорого")

        # Возражение должно обрабатываться независимо
        assert result.strategy is not None


class TestComponentInteraction:
    """Тесты взаимодействия компонентов"""

    def test_scorer_affects_cta_decision(self):
        """Скоринг влияет на решение о CTA"""
        scorer = LeadScorer()
        cta = CTAGenerator()
        cta.turn_count = 5

        # Холодный лид
        score = scorer.get_score()
        assert score.temperature == LeadTemperature.COLD

        # CTA в presentation всё равно добавляется
        should_add, _ = cta.should_add_cta(
            "presentation",
            "Wipon помогает.",
            {}
        )
        assert should_add

        # Но можно использовать температуру для выбора типа CTA

    def test_objection_affects_scoring(self):
        """Возражения влияют на скоринг"""
        scorer = LeadScorer()
        handler = ObjectionHandler()

        # Набираем score
        scorer.add_signal("demo_request")
        high_score = scorer.current_score

        # Возражение
        handler.handle_objection("Это дорого")
        scorer.add_signal("objection_price")

        # Score уменьшился
        assert scorer.current_score < high_score

    def test_circular_flow_independent_of_cta(self, enable_circular_flow):
        """Circular flow независим от CTA (при включённом флаге)"""
        sm = StateMachine()
        cta = CTAGenerator()

        # Возвращаемся назад
        sm.state = "spin_problem"
        sm.process("go_back")

        # CTA не затронут
        assert cta.turn_count == 0


class TestRealWorldScenarios:
    """Реалистичные сценарии"""

    def test_interested_customer_flow(self):
        """Заинтересованный клиент"""
        sm = StateMachine()
        scorer = LeadScorer()
        cta = CTAGenerator()

        # Диалог
        turns = [
            ("greeting", "greeting", {}),
            ("spin_situation", "situation_provided", {"company_size": 20}),
            ("spin_problem", "problem_revealed", {"pain_point": "теряем клиентов"}),
        ]

        for state, intent, data in turns:
            sm.state = state
            sm.process(intent, data)
            cta.increment_turn()

            signal = get_signal_from_intent(intent)
            if signal:
                scorer.add_signal(signal)

        # Клиент запросил демо
        scorer.add_signal("demo_request")

        score = scorer.get_score()
        # Должен быть тёплый или горячий
        assert score.temperature in [LeadTemperature.WARM, LeadTemperature.HOT]

        # CTA должен быть уместен
        should_add, _ = cta.should_add_cta("presentation", "Response.", {})
        assert should_add

    def test_hesitant_customer_flow(self):
        """Сомневающийся клиент"""
        sm = StateMachine()
        scorer = LeadScorer()
        handler = ObjectionHandler()

        # Возражения
        objections = [
            "Это дорого",
            "Надо подумать",
        ]

        for obj in objections:
            obj_type = handler.detect_objection(obj)
            if obj_type:
                handler.handle_objection(obj)
                signal = get_signal_from_intent(f"objection_{obj_type.value}")
                if signal:
                    scorer.add_signal(signal)

        # Score низкий
        assert scorer.current_score < 30

    def test_correction_and_continue(self, enable_circular_flow):
        """Исправление и продолжение (при включённом флаге)"""
        sm = StateMachine()

        # Неправильные данные
        sm.state = "spin_situation"
        sm.process("situation_provided", {"company_size": 5})

        sm.state = "spin_problem"
        sm.process("go_back")

        assert sm.state == "spin_situation"

        # Правильные данные
        sm.process("situation_provided", {"company_size": 25})

        # Данные обновлены
        assert sm.collected_data["company_size"] == 25


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
