"""
Тесты для Lead Scoring модуля.

Покрывает:
- Базовый скоринг
- Температуры лидов
- Decay сигналов
- Рекомендации по пропуску фаз
- Интеграцию с интентами
"""

import pytest
import sys
from pathlib import Path

# Добавляем src в PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from lead_scoring import (
    LeadScorer,
    LeadTemperature,
    LeadSignal,
    LeadScore,
    get_signal_from_intent,
    INTENT_TO_SIGNAL,
)


class TestLeadScorerBasics:
    """Тесты базовой функциональности скоринга"""

    def test_initial_score_is_zero(self):
        """Начальный score должен быть 0"""
        scorer = LeadScorer()
        score = scorer.get_score()

        assert score.score == 0
        assert score.temperature == LeadTemperature.COLD

    def test_reset_clears_score(self):
        """Reset должен обнулять score"""
        scorer = LeadScorer()
        scorer.add_signal("demo_request")
        assert scorer.current_score > 0

        scorer.reset()
        assert scorer.current_score == 0
        assert len(scorer.signals_history) == 0

    def test_add_positive_signal_increases_score(self):
        """Положительные сигналы должны увеличивать score"""
        scorer = LeadScorer()

        score = scorer.add_signal("demo_request")
        assert score.score == 30  # Demo request weight

    def test_add_negative_signal_decreases_score(self):
        """Негативные сигналы должны уменьшать score"""
        scorer = LeadScorer()
        scorer.add_signal("demo_request")  # +30
        initial = scorer.current_score

        scorer.add_signal("objection_price")  # -15
        assert scorer.current_score < initial

    def test_score_capped_at_100(self):
        """Score не должен превышать 100"""
        scorer = LeadScorer()

        # Добавляем много сигналов
        for _ in range(10):
            scorer.add_signal("demo_request")

        assert scorer.current_score <= 100

    def test_score_cannot_go_below_zero(self):
        """Score не должен быть отрицательным"""
        scorer = LeadScorer()

        # Добавляем только негативные сигналы
        for _ in range(10):
            scorer.add_signal("objection_price")

        assert scorer.current_score >= 0

    def test_unknown_signal_ignored(self):
        """Неизвестные сигналы должны игнорироваться"""
        scorer = LeadScorer()

        scorer.add_signal("unknown_signal_xyz")
        assert scorer.current_score == 0
        assert len(scorer.signals_history) == 0


class TestLeadTemperature:
    """Тесты определения температуры лида"""

    def test_cold_temperature_for_low_score(self):
        """Низкий score = COLD температура"""
        scorer = LeadScorer()
        score = scorer.get_score()

        assert score.temperature == LeadTemperature.COLD
        assert score.recommended_path == "full_spin"

    def test_warm_temperature(self):
        """Score 30-49 = WARM температура"""
        scorer = LeadScorer()
        scorer.add_signal("demo_request")  # +30

        score = scorer.get_score()
        assert score.temperature == LeadTemperature.WARM
        assert score.recommended_path == "short_spin"

    def test_hot_temperature(self):
        """Score 50-69 = HOT температура"""
        scorer = LeadScorer()
        scorer.add_signal("demo_request")  # +30
        scorer.add_signal("callback_request")  # +25

        score = scorer.get_score()
        assert score.temperature == LeadTemperature.HOT
        assert score.recommended_path == "direct_present"

    def test_very_hot_temperature(self):
        """Score 70+ = VERY_HOT температура"""
        # Используем decay_factor=1.0 для точного расчёта
        scorer = LeadScorer(decay_factor=1.0)
        scorer.add_signal("demo_request")  # +30
        scorer.add_signal("contact_provided")  # +35 = 65

        # 65 это ещё HOT, добавляем ещё сигнал для VERY_HOT
        scorer.add_signal("features_question")  # +5 = 70

        score = scorer.get_score()
        assert score.temperature == LeadTemperature.VERY_HOT
        assert score.recommended_path == "direct_close"


class TestSkipPhases:
    """Тесты рекомендаций по пропуску фаз"""

    def test_cold_lead_no_skip(self):
        """COLD лид не пропускает фазы"""
        scorer = LeadScorer()
        score = scorer.get_score()

        assert len(score.skip_phases) == 0
        assert not scorer.should_skip_phase("spin_situation")
        assert not scorer.should_skip_phase("spin_problem")

    def test_warm_lead_skips_implication_and_need(self):
        """WARM лид пропускает I и N фазы"""
        scorer = LeadScorer()
        scorer.add_signal("demo_request")

        score = scorer.get_score()
        assert score.temperature == LeadTemperature.WARM
        assert "spin_implication" in score.skip_phases
        assert "spin_need_payoff" in score.skip_phases
        assert "spin_situation" not in score.skip_phases

    def test_hot_lead_skips_most_spin(self):
        """HOT лид пропускает P, I, N фазы"""
        scorer = LeadScorer()
        scorer.add_signal("demo_request")
        scorer.add_signal("callback_request")

        score = scorer.get_score()
        assert score.temperature == LeadTemperature.HOT
        assert "spin_problem" in score.skip_phases
        assert "spin_implication" in score.skip_phases
        assert "spin_need_payoff" in score.skip_phases

    def test_should_skip_phase_method(self):
        """Метод should_skip_phase корректно работает"""
        scorer = LeadScorer()
        scorer.add_signal("demo_request")

        assert not scorer.should_skip_phase("spin_situation")
        assert scorer.should_skip_phase("spin_implication")


class TestDecayMechanism:
    """Тесты механизма затухания сигналов"""

    def test_decay_reduces_score(self):
        """Decay должен уменьшать влияние старых сигналов"""
        scorer = LeadScorer(decay_factor=0.5)
        scorer.add_signal("demo_request")  # Ход 1: +30

        # Переходим к следующему ходу
        scorer.end_turn()

        # Добавляем ещё один сигнал в НОВОМ ходу — decay применяется
        scorer.add_signal("features_question")  # Ход 2: decay + 5

        # Score должен быть: 30 * 0.5 + 5 = 20
        assert scorer.current_score == 20

    def test_no_decay_with_factor_1(self):
        """Decay factor = 1.0 не уменьшает score"""
        scorer = LeadScorer(decay_factor=1.0)
        scorer.add_signal("demo_request")  # +30
        scorer.end_turn()
        scorer.add_signal("features_question")  # +5

        assert scorer.current_score == 35  # Без decay

    def test_decay_accumulates(self):
        """Decay накапливается с каждым ходом"""
        scorer = LeadScorer(decay_factor=0.9)

        scorer.add_signal("demo_request")  # Ход 1: +30
        scorer.end_turn()
        scorer.add_signal("features_question")  # Ход 2: 30*0.9 + 5 = 32
        scorer.end_turn()
        scorer.add_signal("integrations_question")  # Ход 3: 32*0.9 + 5 = 33.8

        assert 30 < scorer.current_score < 35

    def test_multiple_signals_same_turn_no_extra_decay(self):
        """Несколько сигналов в одном ходе не применяют decay дважды"""
        scorer = LeadScorer(decay_factor=0.9)

        # Все сигналы в одном ходу
        scorer.add_signal("demo_request")  # +30
        scorer.add_signal("features_question")  # +5 (без дополнительного decay)

        # Score = 30 + 5 = 35 (decay применился только один раз в начале)
        assert scorer.current_score == 35


class TestSignalsHistory:
    """Тесты истории сигналов"""

    def test_signals_recorded_in_history(self):
        """Сигналы записываются в историю"""
        scorer = LeadScorer()
        scorer.add_signal("demo_request")
        scorer.add_signal("callback_request")

        assert "demo_request" in scorer.signals_history
        assert "callback_request" in scorer.signals_history

    def test_history_limited_to_max_length(self):
        """История ограничена максимальной длиной"""
        scorer = LeadScorer()

        for i in range(30):
            scorer.add_signal("features_question")

        assert len(scorer.signals_history) <= scorer.MAX_HISTORY_LENGTH

    def test_get_score_returns_recent_signals(self):
        """get_score возвращает последние 5 сигналов"""
        scorer = LeadScorer()

        for i in range(10):
            scorer.add_signal("features_question")

        score = scorer.get_score()
        assert len(score.signals) == 5


class TestNextPhase:
    """Тесты получения следующей фазы"""

    def test_get_next_phase_cold_lead(self):
        """COLD лид идёт по полному пути"""
        scorer = LeadScorer()

        next_phase = scorer.get_next_phase("spin_situation")
        assert next_phase == "spin_problem"

        next_phase = scorer.get_next_phase("spin_problem")
        assert next_phase == "spin_implication"

    def test_get_next_phase_warm_lead_skips(self):
        """WARM лид пропускает I и N"""
        scorer = LeadScorer()
        scorer.add_signal("demo_request")

        # После problem сразу presentation (пропуская I и N)
        next_phase = scorer.get_next_phase("spin_problem")
        assert next_phase == "presentation"

    def test_get_next_phase_hot_lead(self):
        """HOT лид идёт сразу к presentation"""
        scorer = LeadScorer()
        scorer.add_signal("demo_request")
        scorer.add_signal("callback_request")

        next_phase = scorer.get_next_phase("spin_situation")
        assert next_phase == "presentation"

    def test_get_next_phase_invalid_state(self):
        """Для неизвестного состояния возвращает None"""
        scorer = LeadScorer()
        next_phase = scorer.get_next_phase("unknown_state")
        assert next_phase is None


class TestIsReadyForClose:
    """Тесты готовности к закрытию"""

    def test_not_ready_for_close_cold(self):
        """COLD лид не готов к закрытию"""
        scorer = LeadScorer()
        assert not scorer.is_ready_for_close()

    def test_not_ready_for_close_warm(self):
        """WARM лид не готов к закрытию"""
        scorer = LeadScorer()
        scorer.add_signal("demo_request")
        assert not scorer.is_ready_for_close()

    def test_ready_for_close_very_hot(self):
        """VERY_HOT лид готов к закрытию"""
        scorer = LeadScorer(decay_factor=1.0)  # Без decay для точного теста
        scorer.add_signal("demo_request")      # +30
        scorer.add_signal("contact_provided")  # +35 = 65
        scorer.add_signal("features_question") # +5 = 70 (VERY_HOT threshold)
        assert scorer.is_ready_for_close()


class TestIntentMapping:
    """Тесты маппинга интентов на сигналы"""

    def test_get_signal_from_intent_demo(self):
        """demo_request маппится на сигнал"""
        signal = get_signal_from_intent("demo_request")
        assert signal == LeadSignal.DEMO_REQUEST.value

    def test_get_signal_from_intent_callback(self):
        """callback_request маппится на сигнал"""
        signal = get_signal_from_intent("callback_request")
        assert signal == LeadSignal.CALLBACK_REQUEST.value

    def test_get_signal_from_intent_contact(self):
        """contact_provided маппится на сигнал"""
        signal = get_signal_from_intent("contact_provided")
        assert signal == LeadSignal.CONTACT_PROVIDED.value

    def test_get_signal_from_intent_question(self):
        """question_features маппится на сигнал"""
        signal = get_signal_from_intent("question_features")
        assert signal == LeadSignal.FEATURES_QUESTION.value

    def test_get_signal_from_intent_objection(self):
        """Возражения маппятся на сигналы"""
        signal = get_signal_from_intent("objection_price")
        assert signal == LeadSignal.OBJECTION_PRICE.value

        signal = get_signal_from_intent("objection_no_time")
        assert signal == LeadSignal.OBJECTION_NO_TIME.value

    def test_get_signal_from_unknown_intent(self):
        """Неизвестный интент возвращает None"""
        signal = get_signal_from_intent("unknown_intent_xyz")
        assert signal is None

    def test_all_mapped_intents_have_weights(self):
        """Все замапленные интенты имеют веса"""
        scorer = LeadScorer()
        all_weights = {**scorer.POSITIVE_WEIGHTS, **scorer.NEGATIVE_WEIGHTS}

        for intent, signal in INTENT_TO_SIGNAL.items():
            assert signal in all_weights, f"Signal {signal} for intent {intent} has no weight"


class TestAddSignals:
    """Тесты добавления нескольких сигналов"""

    def test_add_signals_batch(self):
        """add_signals добавляет несколько сигналов"""
        scorer = LeadScorer()

        signals = ["features_question", "integrations_question", "demo_request"]
        score = scorer.add_signals(signals)

        assert len(scorer.signals_history) == 3
        assert score.score > 0


class TestGetSummary:
    """Тесты получения сводки"""

    def test_get_summary_structure(self):
        """get_summary возвращает правильную структуру"""
        scorer = LeadScorer()
        scorer.add_signal("demo_request")
        scorer.add_signal("callback_request")

        summary = scorer.get_summary()

        assert "score" in summary
        assert "temperature" in summary
        assert "signals_count" in summary
        assert "recent_signals" in summary
        assert "recommended_path" in summary
        assert "skip_phases" in summary

    def test_get_summary_values(self):
        """get_summary содержит правильные значения"""
        scorer = LeadScorer()
        scorer.add_signal("demo_request")

        summary = scorer.get_summary()

        assert summary["score"] == 30
        assert summary["temperature"] == "warm"
        assert summary["signals_count"] == 1
        assert "demo_request" in summary["recent_signals"]


class TestLeadSignalEnum:
    """Тесты enum LeadSignal"""

    def test_positive_signals_exist(self):
        """Положительные сигналы определены"""
        assert LeadSignal.DEMO_REQUEST.value == "demo_request"
        assert LeadSignal.CALLBACK_REQUEST.value == "callback_request"
        assert LeadSignal.CONTACT_PROVIDED.value == "contact_provided"

    def test_negative_signals_exist(self):
        """Негативные сигналы определены"""
        assert LeadSignal.OBJECTION_PRICE.value == "objection_price"
        assert LeadSignal.OBJECTION_COMPETITOR.value == "objection_competitor"
        assert LeadSignal.FRUSTRATION.value == "frustration"


class TestEdgeCases:
    """Тесты граничных случаев"""

    def test_rapid_scoring_changes(self):
        """Быстрые изменения score корректно обрабатываются"""
        scorer = LeadScorer()

        # Много положительных
        for _ in range(5):
            scorer.add_signal("demo_request")

        high_score = scorer.current_score

        # Много негативных
        for _ in range(10):
            scorer.add_signal("rejection_soft")

        # Score должен уменьшиться, но не уйти в минус
        assert scorer.current_score >= 0
        assert scorer.current_score < high_score

    def test_empty_signals_history_ok(self):
        """Пустая история сигналов корректно обрабатывается"""
        scorer = LeadScorer()
        score = scorer.get_score()

        assert score.signals == []
        assert score.score == 0

    def test_multiple_same_signals(self):
        """Несколько одинаковых сигналов накапливаются"""
        scorer = LeadScorer()

        scorer.add_signal("demo_request")
        score1 = scorer.current_score

        scorer.add_signal("demo_request")
        score2 = scorer.current_score

        # С учётом decay
        assert score2 > score1


class TestIntegrationScenarios:
    """Интеграционные сценарии"""

    def test_cold_to_hot_progression(self):
        """Прогрессия от COLD к HOT"""
        scorer = LeadScorer()

        # Начало — COLD
        assert scorer.get_score().temperature == LeadTemperature.COLD

        # Вопрос о функциях
        scorer.add_signal("features_question")
        assert scorer.get_score().temperature == LeadTemperature.COLD

        # Запрос демо
        scorer.add_signal("demo_request")
        assert scorer.get_score().temperature == LeadTemperature.WARM

        # Запрос callback
        scorer.add_signal("callback_request")
        assert scorer.get_score().temperature == LeadTemperature.HOT

    def test_hot_to_warm_after_objection(self):
        """Возражение снижает температуру"""
        scorer = LeadScorer(decay_factor=1.0)  # Без decay для предсказуемости

        # Горячий лид
        scorer.add_signal("demo_request")    # +30
        scorer.add_signal("callback_request") # +25 = 55 (HOT)
        assert scorer.get_score().temperature == LeadTemperature.HOT

        # Возражение о цене
        scorer.add_signal("objection_price")  # -15 = 40 (WARM)

        # Температура должна понизиться до WARM
        new_temp = scorer.get_score().temperature
        assert new_temp == LeadTemperature.WARM

    def test_typical_sales_conversation(self):
        """Типичный диалог продажи"""
        scorer = LeadScorer()

        # Клиент задаёт вопросы
        scorer.add_signal("features_question")
        scorer.add_signal("integrations_question")
        scorer.add_signal("price_question")

        # Обсуждает проблему
        scorer.add_signal("explicit_problem")

        # Запрашивает демо
        scorer.add_signal("demo_request")

        # Оставляет контакт
        scorer.add_signal("contact_provided")

        score = scorer.get_score()
        assert score.temperature == LeadTemperature.VERY_HOT
        assert scorer.is_ready_for_close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
