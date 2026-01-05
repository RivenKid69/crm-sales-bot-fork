"""
Тесты для модуля метрик (metrics.py).
"""

import pytest
import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from metrics import ConversationMetrics, ConversationOutcome, TurnRecord, AggregatedMetrics


class TestConversationMetricsBasic:
    """Базовые тесты ConversationMetrics"""

    def test_create_metrics(self):
        """Создание метрик"""
        metrics = ConversationMetrics()
        assert metrics is not None
        assert metrics.turns == 0

    def test_create_metrics_with_id(self):
        """Создание метрик с conversation_id"""
        metrics = ConversationMetrics(conversation_id="test_123")
        assert metrics.conversation_id == "test_123"

    def test_reset(self):
        """Сброс метрик"""
        metrics = ConversationMetrics()
        metrics.record_turn("greeting", "greeting")
        metrics.record_turn("spin_situation", "company_size")

        metrics.reset()

        assert metrics.turns == 0
        assert len(metrics.intents_sequence) == 0
        assert len(metrics.turn_records) == 0


class TestRecordTurn:
    """Тесты для record_turn"""

    def test_record_single_turn(self):
        """Запись одного хода"""
        metrics = ConversationMetrics()
        metrics.record_turn("greeting", "greeting")

        assert metrics.turns == 1
        assert metrics.phase_turns["greeting"] == 1
        assert metrics.intents_sequence == ["greeting"]

    def test_record_multiple_turns(self):
        """Запись нескольких ходов"""
        metrics = ConversationMetrics()
        metrics.record_turn("greeting", "greeting")
        metrics.record_turn("spin_situation", "company_size")
        metrics.record_turn("spin_problem", "pain_point")

        assert metrics.turns == 3
        assert metrics.phase_turns["greeting"] == 1
        assert metrics.phase_turns["spin_situation"] == 1
        assert metrics.phase_turns["spin_problem"] == 1
        assert metrics.intents_sequence == ["greeting", "company_size", "pain_point"]

    def test_record_turn_with_tone(self):
        """Запись хода с тоном"""
        metrics = ConversationMetrics()
        metrics.record_turn("greeting", "greeting", tone="neutral")
        metrics.record_turn("spin_situation", "company_size", tone="positive")

        assert len(metrics.tone_history) == 2
        assert metrics.tone_history[0]["tone"] == "neutral"
        assert metrics.tone_history[1]["tone"] == "positive"

    def test_record_turn_with_fallback(self):
        """Запись хода с fallback"""
        metrics = ConversationMetrics()
        metrics.record_turn("spin_situation", "unclear", fallback_used=True, fallback_tier="tier_1")

        assert metrics.fallback_count == 1
        assert metrics.fallback_by_tier["tier_1"] == 1

    def test_same_state_multiple_times(self):
        """Один state несколько раз"""
        metrics = ConversationMetrics()
        metrics.record_turn("spin_situation", "company_size")
        metrics.record_turn("spin_situation", "unclear")
        metrics.record_turn("spin_situation", "company_size")

        assert metrics.phase_turns["spin_situation"] == 3
        assert metrics.turns == 3


class TestRecordTurnTiming:
    """Тесты для измерения времени"""

    def test_response_time_measurement(self):
        """Измерение времени ответа"""
        metrics = ConversationMetrics()

        metrics.start_turn_timer()
        time.sleep(0.05)  # 50ms
        metrics.record_turn("greeting", "greeting")

        assert len(metrics.turn_records) == 1
        record = metrics.turn_records[0]
        assert record.response_time_ms is not None
        assert record.response_time_ms >= 50  # Минимум 50ms

    def test_multiple_timed_turns(self):
        """Несколько ходов с таймингом"""
        metrics = ConversationMetrics()

        for i in range(3):
            metrics.start_turn_timer()
            time.sleep(0.02)
            metrics.record_turn(f"state_{i}", f"intent_{i}")

        avg_time = metrics.get_average_response_time_ms()
        assert avg_time is not None
        assert avg_time >= 20


class TestRecordObjection:
    """Тесты для record_objection"""

    def test_record_single_objection(self):
        """Запись одного возражения"""
        metrics = ConversationMetrics()
        metrics.record_turn("presentation", "interest")
        metrics.record_objection("price")

        assert len(metrics.objections) == 1
        assert metrics.objections[0]["type"] == "price"
        assert metrics.objections[0]["resolved"] is False

    def test_record_resolved_objection(self):
        """Запись разрешённого возражения"""
        metrics = ConversationMetrics()
        metrics.record_turn("presentation", "interest")
        metrics.record_objection("price", resolved=True, attempts=2)

        assert metrics.objections[0]["resolved"] is True
        assert metrics.objections[0]["attempts"] == 2

    def test_multiple_objections(self):
        """Несколько возражений"""
        metrics = ConversationMetrics()
        metrics.record_objection("price")
        metrics.record_objection("competitor")
        metrics.record_objection("no_time")

        assert len(metrics.objections) == 3


class TestRecordFallback:
    """Тесты для record_fallback"""

    def test_record_fallback_without_tier(self):
        """Запись fallback без tier"""
        metrics = ConversationMetrics()
        metrics.record_fallback()

        assert metrics.fallback_count == 1
        assert len(metrics.fallback_by_tier) == 0

    def test_record_fallback_with_tier(self):
        """Запись fallback с tier"""
        metrics = ConversationMetrics()
        metrics.record_fallback("tier_1")
        metrics.record_fallback("tier_2")
        metrics.record_fallback("tier_1")

        assert metrics.fallback_count == 3
        assert metrics.fallback_by_tier["tier_1"] == 2
        assert metrics.fallback_by_tier["tier_2"] == 1


class TestRecordLeadScore:
    """Тесты для record_lead_score"""

    def test_record_lead_score(self):
        """Запись lead score"""
        metrics = ConversationMetrics()
        metrics.record_lead_score(30, "warm", "explicit_interest")

        assert len(metrics.lead_score_history) == 1
        assert metrics.lead_score_history[0]["score"] == 30
        assert metrics.lead_score_history[0]["temperature"] == "warm"
        assert metrics.lead_score_history[0]["signal"] == "explicit_interest"

    def test_final_lead_score(self):
        """Получение финального lead score"""
        metrics = ConversationMetrics()
        metrics.record_lead_score(20, "cold")
        metrics.record_lead_score(40, "warm")
        metrics.record_lead_score(60, "hot")

        assert metrics.get_final_lead_score() == 60


class TestRecordCollectedData:
    """Тесты для record_collected_data"""

    def test_record_data(self):
        """Запись собранных данных"""
        metrics = ConversationMetrics()
        metrics.record_collected_data("company_size", 10)
        metrics.record_collected_data("pain_point", "Потеря клиентов")

        assert metrics.collected_data["company_size"] == 10
        assert metrics.collected_data["pain_point"] == "Потеря клиентов"

    def test_overwrite_data(self):
        """Перезапись данных"""
        metrics = ConversationMetrics()
        metrics.record_collected_data("company_size", 5)
        metrics.record_collected_data("company_size", 10)

        assert metrics.collected_data["company_size"] == 10


class TestOutcome:
    """Тесты для outcome"""

    def test_set_outcome(self):
        """Установка outcome"""
        metrics = ConversationMetrics()
        metrics.set_outcome(ConversationOutcome.SUCCESS)

        assert metrics.outcome == ConversationOutcome.SUCCESS
        assert metrics.end_time is not None

    def test_determine_outcome_success(self):
        """Определение outcome = success"""
        metrics = ConversationMetrics()
        metrics.record_turn("close", "contact_provided")

        assert metrics._determine_outcome() == "success"

    def test_determine_outcome_rejected(self):
        """Определение outcome = rejected"""
        metrics = ConversationMetrics()
        metrics.record_turn("presentation", "rejection")

        assert metrics._determine_outcome() == "rejected"

    def test_determine_outcome_demo(self):
        """Определение outcome = demo_scheduled"""
        metrics = ConversationMetrics()
        metrics.record_turn("close", "demo_request")

        assert metrics._determine_outcome() == "demo_scheduled"

    def test_determine_outcome_abandoned(self):
        """Определение outcome = abandoned"""
        metrics = ConversationMetrics()
        metrics.record_turn("spin_situation", "company_size")

        assert metrics._determine_outcome() == "abandoned"


class TestDuration:
    """Тесты для длительности"""

    def test_duration_without_end(self):
        """Длительность без завершения"""
        metrics = ConversationMetrics()
        assert metrics.get_duration_seconds() is None

    def test_duration_with_end(self):
        """Длительность с завершением"""
        metrics = ConversationMetrics()
        time.sleep(0.05)
        metrics.set_outcome(ConversationOutcome.SUCCESS)

        duration = metrics.get_duration_seconds()
        assert duration is not None
        assert duration >= 0.05


class TestPhaseDistribution:
    """Тесты для распределения по фазам"""

    def test_phase_distribution_empty(self):
        """Распределение при 0 ходах"""
        metrics = ConversationMetrics()
        dist = metrics.get_phase_distribution()
        assert dist == {}

    def test_phase_distribution(self):
        """Расчёт распределения"""
        metrics = ConversationMetrics()
        metrics.record_turn("greeting", "greeting")
        metrics.record_turn("spin_situation", "company_size")
        metrics.record_turn("spin_situation", "unclear")
        metrics.record_turn("spin_problem", "pain_point")

        dist = metrics.get_phase_distribution()
        assert dist["greeting"] == 25.0
        assert dist["spin_situation"] == 50.0
        assert dist["spin_problem"] == 25.0


class TestDominantTone:
    """Тесты для dominant tone"""

    def test_no_tone(self):
        """Нет данных о тоне"""
        metrics = ConversationMetrics()
        assert metrics.get_dominant_tone() is None

    def test_single_tone(self):
        """Один тон"""
        metrics = ConversationMetrics()
        metrics.record_turn("greeting", "greeting", tone="neutral")
        assert metrics.get_dominant_tone() == "neutral"

    def test_dominant_tone(self):
        """Преобладающий тон"""
        metrics = ConversationMetrics()
        metrics.record_turn("s1", "i1", tone="neutral")
        metrics.record_turn("s2", "i2", tone="positive")
        metrics.record_turn("s3", "i3", tone="positive")
        metrics.record_turn("s4", "i4", tone="positive")

        assert metrics.get_dominant_tone() == "positive"


class TestGetSummary:
    """Тесты для get_summary"""

    def test_summary_structure(self):
        """Структура summary"""
        metrics = ConversationMetrics(conversation_id="test")
        metrics.record_turn("greeting", "greeting", tone="neutral")
        metrics.record_objection("price")
        metrics.set_outcome(ConversationOutcome.SUCCESS)

        summary = metrics.get_summary()

        assert "conversation_id" in summary
        assert "created_at" in summary
        assert "total_turns" in summary
        assert "phase_distribution" in summary
        assert "intents_sequence" in summary
        assert "objection_count" in summary
        assert "fallback_count" in summary
        assert "tone_history" in summary
        assert "outcome" in summary

    def test_summary_values(self):
        """Значения в summary"""
        metrics = ConversationMetrics(conversation_id="summary_test")
        metrics.record_turn("greeting", "greeting")
        metrics.record_turn("spin_situation", "company_size")
        metrics.record_objection("price")
        metrics.record_fallback("tier_1")

        summary = metrics.get_summary()

        assert summary["conversation_id"] == "summary_test"
        assert summary["total_turns"] == 2
        assert summary["objection_count"] == 1
        assert summary["fallback_count"] == 1


class TestToLogDict:
    """Тесты для to_log_dict"""

    def test_log_dict_is_compact(self):
        """to_log_dict возвращает компактный dict"""
        metrics = ConversationMetrics(conversation_id="log_test")
        metrics.record_turn("greeting", "greeting")
        metrics.record_turn("spin_situation", "company_size")

        log_dict = metrics.to_log_dict()

        # Должен быть компактным
        assert "turn_records" not in log_dict
        assert "intents_sequence" not in log_dict

        # Но содержать ключевые метрики
        assert log_dict["conversation_id"] == "log_test"
        assert log_dict["total_turns"] == 2


class TestTurnRecord:
    """Тесты для TurnRecord dataclass"""

    def test_turn_record_creation(self):
        """Создание TurnRecord"""
        record = TurnRecord(
            turn_number=1,
            state="greeting",
            intent="greeting"
        )

        assert record.turn_number == 1
        assert record.state == "greeting"
        assert record.intent == "greeting"
        assert record.timestamp is not None

    def test_turn_record_with_all_fields(self):
        """TurnRecord со всеми полями"""
        record = TurnRecord(
            turn_number=5,
            state="spin_situation",
            intent="company_size",
            tone="positive",
            response_time_ms=150.0,
            fallback_used=True,
            fallback_tier="tier_1"
        )

        assert record.tone == "positive"
        assert record.response_time_ms == 150.0
        assert record.fallback_used is True
        assert record.fallback_tier == "tier_1"


class TestConversationOutcome:
    """Тесты для ConversationOutcome enum"""

    def test_outcome_values(self):
        """Значения enum"""
        assert ConversationOutcome.SUCCESS.value == "success"
        assert ConversationOutcome.DEMO_SCHEDULED.value == "demo_scheduled"
        assert ConversationOutcome.SOFT_CLOSE.value == "soft_close"
        assert ConversationOutcome.REJECTED.value == "rejected"
        assert ConversationOutcome.ABANDONED.value == "abandoned"
        assert ConversationOutcome.TIMEOUT.value == "timeout"
        assert ConversationOutcome.ERROR.value == "error"


class TestAggregatedMetrics:
    """Тесты для AggregatedMetrics"""

    def test_create_aggregated(self):
        """Создание AggregatedMetrics"""
        agg = AggregatedMetrics()
        assert agg.count == 0

    def test_add_conversation(self):
        """Добавление диалога"""
        agg = AggregatedMetrics()
        metrics = ConversationMetrics()
        agg.add(metrics)
        assert agg.count == 1

    def test_clear(self):
        """Очистка"""
        agg = AggregatedMetrics()
        agg.add(ConversationMetrics())
        agg.add(ConversationMetrics())
        agg.clear()
        assert agg.count == 0

    def test_success_rate(self):
        """Расчёт success rate"""
        agg = AggregatedMetrics()

        # Успешный диалог
        m1 = ConversationMetrics()
        m1.record_turn("close", "contact_provided")
        agg.add(m1)

        # Неуспешный диалог
        m2 = ConversationMetrics()
        m2.record_turn("spin_situation", "unclear")
        agg.add(m2)

        rate = agg.get_success_rate()
        assert rate == 50.0

    def test_success_rate_empty(self):
        """Success rate при 0 диалогах"""
        agg = AggregatedMetrics()
        assert agg.get_success_rate() == 0.0

    def test_average_turns(self):
        """Среднее количество ходов"""
        agg = AggregatedMetrics()

        m1 = ConversationMetrics()
        m1.record_turn("s1", "i1")
        m1.record_turn("s2", "i2")
        agg.add(m1)

        m2 = ConversationMetrics()
        m2.record_turn("s1", "i1")
        m2.record_turn("s2", "i2")
        m2.record_turn("s3", "i3")
        m2.record_turn("s4", "i4")
        agg.add(m2)

        avg = agg.get_average_turns()
        assert avg == 3.0  # (2 + 4) / 2

    def test_average_fallback_rate(self):
        """Средний процент fallback"""
        agg = AggregatedMetrics()

        m1 = ConversationMetrics()
        m1.record_turn("s1", "i1")
        m1.record_turn("s2", "i2")
        m1.record_fallback()  # 1 fallback из 2 ходов = 50%
        agg.add(m1)

        m2 = ConversationMetrics()
        m2.record_turn("s1", "i1")
        m2.record_turn("s2", "i2")
        m2.record_turn("s3", "i3")
        m2.record_turn("s4", "i4")  # 0 fallback из 4 ходов = 0%
        agg.add(m2)

        avg_rate = agg.get_average_fallback_rate()
        assert avg_rate == 25.0  # (50 + 0) / 2

    def test_outcome_distribution(self):
        """Распределение итогов"""
        agg = AggregatedMetrics()

        m1 = ConversationMetrics()
        m1.record_turn("close", "contact_provided")  # success
        agg.add(m1)

        m2 = ConversationMetrics()
        m2.record_turn("presentation", "rejection")  # rejected
        agg.add(m2)

        m3 = ConversationMetrics()
        m3.record_turn("close", "contact_provided")  # success
        agg.add(m3)

        dist = agg.get_outcome_distribution()
        assert dist["success"] == 2
        assert dist["rejected"] == 1

    def test_aggregated_summary(self):
        """Сводка агрегированных метрик"""
        agg = AggregatedMetrics()

        for _ in range(5):
            m = ConversationMetrics()
            m.record_turn("greeting", "greeting")
            agg.add(m)

        summary = agg.get_summary()

        assert "total_conversations" in summary
        assert "success_rate" in summary
        assert "average_turns" in summary
        assert "average_fallback_rate" in summary
        assert "outcome_distribution" in summary

        assert summary["total_conversations"] == 5


class TestMetricsThreadSafety:
    """Тесты потокобезопасности"""

    def test_concurrent_recording(self):
        """Одновременная запись из нескольких потоков"""
        import threading

        metrics = ConversationMetrics()
        errors = []

        def record_turns(thread_id):
            try:
                for i in range(20):
                    metrics.record_turn(f"state_{thread_id}", f"intent_{i}")
                    time.sleep(0.001)
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=record_turns, args=(i,))
            for i in range(5)
        ]

        for t in threads:
            t.start()

        for t in threads:
            t.join()

        assert len(errors) == 0, f"Errors during concurrent recording: {errors}"
        assert metrics.turns == 100  # 5 threads * 20 turns


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
