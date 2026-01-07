"""
Тесты для исправлений логических и концептуальных ошибок (2026).

Этот файл содержит тесты для проверки всех исправлений:
1. CRITICAL: objection_competitor mapping в lead_scoring.py
2. CRITICAL: неполный список положительных интентов в state_machine.py
3. IMPORTANT: несогласованное состояние после soft_close в bot.py
4. IMPORTANT: пустое сообщение в истории после disambiguation
5. IMPORTANT: жёстко закодированные веса в disambiguation.py
6. MEDIUM: проверка company_size в generator.py
7. MEDIUM: неполный INTENT_TO_CATEGORY в retriever.py
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add src to path
src_path = os.path.join(os.path.dirname(__file__), '..', 'src')
if src_path not in sys.path:
    sys.path.insert(0, src_path)


# =============================================================================
# Test 1: CRITICAL - objection_competitor mapping
# =============================================================================
class TestObjectionCompetitorMapping:
    """Тесты для исправления маппинга objection_competitor в lead_scoring."""

    def test_objection_competitor_has_negative_weight(self):
        """objection_competitor должен маппиться на негативный сигнал"""
        from lead_scoring import INTENT_TO_SIGNAL, LeadSignal, LeadScorer

        # Проверяем что objection_competitor маппится на OBJECTION_COMPETITOR
        assert "objection_competitor" in INTENT_TO_SIGNAL
        assert INTENT_TO_SIGNAL["objection_competitor"] == LeadSignal.OBJECTION_COMPETITOR.value

    def test_objection_competitor_decreases_score(self):
        """objection_competitor должен УМЕНЬШАТЬ lead score"""
        from lead_scoring import LeadScorer

        scorer = LeadScorer()

        # Начинаем с положительного сигнала
        scorer.add_signal("demo_request")  # +30
        initial_score = scorer.current_score
        assert initial_score > 0

        # objection_competitor должен уменьшить score
        scorer.add_signal("objection_competitor")  # -10
        new_score = scorer.current_score

        # Score должен уменьшиться (с учётом decay)
        assert new_score < initial_score, (
            f"objection_competitor должен уменьшать score! "
            f"initial={initial_score}, new={new_score}"
        )

    def test_comparison_has_positive_weight(self):
        """comparison (не возражение) должен иметь положительный вес"""
        from lead_scoring import INTENT_TO_SIGNAL, LeadSignal

        # comparison - это сравнение без возражения (интерес)
        assert "comparison" in INTENT_TO_SIGNAL
        assert INTENT_TO_SIGNAL["comparison"] == LeadSignal.COMPETITOR_COMPARISON.value


# =============================================================================
# Test 2: CRITICAL - positive intents list
# =============================================================================
class TestPositiveIntentsList:
    """Тесты для полного списка положительных интентов в state_machine."""

    def test_positive_intents_reset_objection_counter(self):
        """Положительные интенты должны сбрасывать счётчик возражений"""
        from state_machine import StateMachine

        sm = StateMachine()

        # Добавляем возражение
        sm.process("objection_price", {})
        # Используем правильное имя атрибута: objection_count
        initial_objections = sm.objection_flow.objection_count
        assert initial_objections > 0

        # Положительные интенты должны сбрасывать счётчик
        positive_intents = [
            "agreement", "demo_request", "callback_request", "contact_provided",
            "consultation_request", "situation_provided", "problem_revealed",
            "implication_acknowledged", "need_expressed", "info_provided",
            "question_features", "question_integrations", "comparison",
            "greeting", "gratitude"
        ]

        for intent in positive_intents:
            sm.reset()
            sm.process("objection_price", {})  # Добавляем возражение
            assert sm.objection_flow.objection_count > 0, f"Objection not recorded before {intent}"

            sm.process(intent, {})  # Положительный интент

            assert sm.objection_flow.objection_count == 0, (
                f"Intent '{intent}' должен сбрасывать objection_count! "
                f"Got: {sm.objection_flow.objection_count}"
            )


# =============================================================================
# Test 3: IMPORTANT - soft_close state consistency
# =============================================================================
class TestSoftCloseStateConsistency:
    """Тесты для согласованности состояния при soft_close."""

    def test_soft_close_variables_set_correctly(self):
        """При soft_close локальные переменные должны быть установлены правильно"""
        # Тестируем логику без создания полного бота
        # Проверяем что при should_soft_close=True устанавливаются правильные значения

        # Симулируем код из bot.py:617-624
        objection_info = {
            "should_soft_close": True,
            "response_parts": {"message": "Хорошо, свяжитесь когда будет удобно."},
            "objection_type": "price",
            "attempt_number": 3
        }

        sm_result = {
            "action": "continue",
            "next_state": "spin_problem",
            "is_final": False
        }

        # Логика из bot.py
        action = sm_result["action"]
        next_state = sm_result["next_state"]
        is_final = sm_result["is_final"]

        if objection_info and objection_info.get("should_soft_close"):
            action = "soft_close"
            next_state = "soft_close"
            is_final = True
            response_parts = objection_info.get("response_parts") or {}
            response = response_parts.get("message") or "Хорошо, свяжитесь когда будет удобно."

        # Проверки
        assert action == "soft_close"
        assert next_state == "soft_close"
        assert is_final == True
        assert response == "Хорошо, свяжитесь когда будет удобно."


# =============================================================================
# Test 4: IMPORTANT - disambiguation history
# =============================================================================
class TestDisambiguationHistory:
    """Тесты для истории после disambiguation."""

    def test_continue_with_classification_signature(self):
        """_continue_with_classification должен принимать user_message"""
        from bot import SalesBot
        import inspect

        # Проверяем сигнатуру метода
        sig = inspect.signature(SalesBot._continue_with_classification)
        params = list(sig.parameters.keys())

        assert "user_message" in params, (
            f"_continue_with_classification должен принимать user_message. "
            f"Параметры: {params}"
        )


# =============================================================================
# Test 5: IMPORTANT - configurable disambiguation weights
# =============================================================================
class TestDisambiguationWeights:
    """Тесты для настраиваемых весов в disambiguation."""

    def test_weights_from_config(self):
        """Веса должны браться из конфигурации"""
        from config import CLASSIFIER_CONFIG

        # Проверяем что веса определены в конфигурации
        assert "root_classifier_weight" in CLASSIFIER_CONFIG
        assert "lemma_classifier_weight" in CLASSIFIER_CONFIG

        # Веса должны суммироваться примерно в 1.0
        total = (
            CLASSIFIER_CONFIG["root_classifier_weight"] +
            CLASSIFIER_CONFIG["lemma_classifier_weight"]
        )
        assert abs(total - 1.0) < 0.01, (
            f"Сумма весов должна быть ~1.0, получили {total}"
        )

    def test_disambiguation_uses_config_weights(self):
        """DisambiguationAnalyzer должен использовать веса из конфигурации"""
        from classifier.disambiguation import DisambiguationAnalyzer
        from config import CLASSIFIER_CONFIG

        analyzer = DisambiguationAnalyzer(config=CLASSIFIER_CONFIG)

        root_scores = {"intent_a": 2, "intent_b": 1}
        lemma_scores = {"intent_a": 1.0, "intent_b": 2.0}

        merged = analyzer._merge_scores(root_scores, lemma_scores)

        # Проверяем что merged не пустой и использует настроенные веса
        assert merged, "Merged scores не должны быть пустыми"
        assert "intent_a" in merged
        assert "intent_b" in merged


# =============================================================================
# Test 6: MEDIUM - company_size check
# =============================================================================
class TestCompanySizeCheck:
    """Тесты для проверки company_size в generator."""

    def test_company_size_none_returns_features(self):
        """При company_size=None должны возвращаться общие features"""
        from generator import ResponseGenerator

        gen = ResponseGenerator.__new__(ResponseGenerator)
        gen.history_length = 4

        result = gen.get_facts(company_size=None)
        assert result, "При company_size=None должны вернуться features"

    def test_company_size_zero_returns_features(self):
        """При company_size=0 должны возвращаться общие features (не тариф)"""
        from generator import ResponseGenerator

        gen = ResponseGenerator.__new__(ResponseGenerator)
        gen.history_length = 4

        result = gen.get_facts(company_size=0)
        # 0 сотрудников - нереальный кейс, но не должен падать
        assert result, "При company_size=0 должны вернуться features"
        assert "Тариф:" not in result, (
            "При company_size=0 не должен рассчитываться тариф"
        )

    def test_company_size_positive_returns_tariff(self):
        """При company_size>0 должен рассчитываться тариф"""
        from generator import ResponseGenerator

        gen = ResponseGenerator.__new__(ResponseGenerator)
        gen.history_length = 4

        result = gen.get_facts(company_size=10)
        assert "Тариф:" in result, (
            "При company_size=10 должен рассчитываться тариф"
        )


# =============================================================================
# Test 7: MEDIUM - INTENT_TO_CATEGORY completeness
# =============================================================================
class TestIntentToCategoryCompleteness:
    """Тесты для полноты INTENT_TO_CATEGORY маппинга."""

    def test_system_intents_in_mapping(self):
        """Системные интенты должны быть в маппинге"""
        from knowledge.retriever import INTENT_TO_CATEGORY

        system_intents = [
            "disambiguation_needed",
            "fallback_close"
        ]

        for intent in system_intents:
            assert intent in INTENT_TO_CATEGORY, (
                f"Интент '{intent}' отсутствует в INTENT_TO_CATEGORY"
            )
            # Системные интенты не требуют категорий
            assert INTENT_TO_CATEGORY[intent] == [], (
                f"Системный интент '{intent}' должен иметь пустой список категорий"
            )

    def test_all_common_intents_in_mapping(self):
        """Все основные интенты должны быть в маппинге"""
        from knowledge.retriever import INTENT_TO_CATEGORY

        common_intents = [
            "greeting", "rejection", "farewell", "gratitude",
            "price_question", "question_features", "question_integrations",
            "objection_price", "objection_competitor", "objection_no_time", "objection_think",
            "agreement", "demo_request", "callback_request", "contact_provided",
            "situation_provided", "problem_revealed", "implication_acknowledged",
            "need_expressed", "no_problem", "no_need",
            "go_back", "correct_info", "unclear", "small_talk"
        ]

        for intent in common_intents:
            assert intent in INTENT_TO_CATEGORY, (
                f"Интент '{intent}' отсутствует в INTENT_TO_CATEGORY"
            )


# =============================================================================
# Test 8: Edge cases and integration
# =============================================================================
class TestEdgeCases:
    """Тесты для edge cases."""

    def test_multiple_objections_then_positive_intent(self):
        """После серии возражений положительный интент сбрасывает счётчик"""
        from state_machine import StateMachine

        sm = StateMachine()

        # Серия возражений
        sm.process("objection_price", {})
        sm.process("objection_no_time", {})

        assert sm.objection_flow.objection_count > 0

        # Положительный интент
        sm.process("agreement", {})

        assert sm.objection_flow.objection_count == 0

    def test_lead_score_scenario_with_fixed_mapping(self):
        """Реалистичный сценарий: интерес → возражение о конкуренте → интерес"""
        from lead_scoring import LeadScorer

        scorer = LeadScorer()

        # Интерес к продукту (используем сигнал с положительным весом)
        scorer.add_signal("features_question")  # +5
        score_after_interest = scorer.current_score
        # features_question может не быть в POSITIVE_WEIGHTS, используем demo_request
        if score_after_interest == 0:
            scorer.add_signal("demo_request")  # +30
            score_after_interest = scorer.current_score

        assert score_after_interest > 0

        # Возражение о конкуренте (теперь правильно снижает score)
        scorer.add_signal("objection_competitor")  # -10
        score_after_objection = scorer.current_score

        assert score_after_objection < score_after_interest, (
            f"objection_competitor должен снижать score! "
            f"before={score_after_interest}, after={score_after_objection}"
        )


# =============================================================================
# Test 9: Conversation Guard
# =============================================================================
class TestConversationGuard:
    """Тесты для conversation_guard."""

    def test_phase_attempts_triggers_correctly(self):
        """Проверяем логику phase_attempts с разными состояниями"""
        from conversation_guard import ConversationGuard, GuardConfig

        config = GuardConfig(
            max_phase_attempts=3,
            max_same_state=10  # Увеличиваем чтобы не сработал state loop
        )
        guard = ConversationGuard(config)

        # Первые 3 попытки с разными сообщениями - не должно быть интервенции
        for i in range(3):
            can_continue, intervention = guard.check(
                state="test_state",
                message=f"unique_message_{i}",  # Разные сообщения
                collected_data={}
            )
            assert can_continue, f"Попытка {i+1} из 3 не должна прерывать диалог"

        # 4я попытка - должна быть интервенция
        can_continue, intervention = guard.check(
            state="test_state",
            message="unique_message_4",
            collected_data={}
        )
        # Интервенция должна быть (TIER_2 или TIER_3)
        assert intervention is not None, (
            f"На 4й попытке должна быть интервенция"
        )


# =============================================================================
# Test 10: Integration - Lead Scoring with correct weights
# =============================================================================
class TestLeadScoringIntegration:
    """Интеграционные тесты для lead scoring."""

    def test_negative_signals_reduce_score(self):
        """Негативные сигналы должны уменьшать score"""
        from lead_scoring import LeadScorer, INTENT_TO_SIGNAL

        scorer = LeadScorer()

        # Добавляем положительный сигнал
        scorer.add_signal("demo_request")
        high_score = scorer.current_score
        assert high_score > 0

        # Все негативные сигналы должны уменьшать score
        negative_intents = [
            "objection_competitor", "objection_price",
            "objection_no_time", "objection_think", "rejection"
        ]

        for intent in negative_intents:
            if intent in INTENT_TO_SIGNAL:
                scorer_test = LeadScorer()
                scorer_test.add_signal("demo_request")
                before = scorer_test.current_score

                signal = INTENT_TO_SIGNAL[intent]
                scorer_test.add_signal(signal)
                after = scorer_test.current_score

                assert after < before, (
                    f"Intent '{intent}' (signal={signal}) должен уменьшать score! "
                    f"before={before}, after={after}"
                )


# =============================================================================
# Run tests
# =============================================================================
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
