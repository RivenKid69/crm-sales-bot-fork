"""
Тесты для ConfidenceRouter — graceful degradation на основе confidence и gap.
"""
import pytest
from unittest.mock import patch, MagicMock
import tempfile
import json
from pathlib import Path

from classifier.confidence_router import (
    ConfidenceRouter,
    RouterDecision,
    RouterResult,
    DisambiguationOption,
    get_confidence_router,
)
from constants.intent_labels import INTENT_LABELS


class TestRouterDecisions:
    """Тесты решений роутера."""

    def test_execute_high_confidence_high_gap(self):
        """EXECUTE при высоком confidence и большом gap."""
        router = ConfidenceRouter()

        result = router.route({
            "intent": "price_question",
            "confidence": 0.90,
            "alternatives": [
                {"intent": "pricing_details", "confidence": 0.20}
            ]
        })

        assert result.decision == RouterDecision.EXECUTE
        assert result.intent == "price_question"
        assert result.confidence == 0.90
        assert result.gap == 0.70  # 0.90 - 0.20

    def test_confirm_high_confidence_low_gap(self):
        """CONFIRM при высоком confidence но маленьком gap."""
        router = ConfidenceRouter()

        result = router.route({
            "intent": "price_question",
            "confidence": 0.88,
            "alternatives": [
                {"intent": "pricing_details", "confidence": 0.78}
            ]
        })

        assert result.decision == RouterDecision.CONFIRM
        assert result.gap == pytest.approx(0.10, abs=0.001)  # 0.88 - 0.78 < 0.20
        assert result.confirm_question is not None

    def test_execute_medium_confidence_high_gap(self):
        """EXECUTE при среднем confidence но большом gap."""
        router = ConfidenceRouter()

        result = router.route({
            "intent": "objection_competitor",
            "confidence": 0.70,
            "alternatives": [
                {"intent": "comparison", "confidence": 0.30}
            ]
        })

        assert result.decision == RouterDecision.EXECUTE
        assert result.gap == pytest.approx(0.40, abs=0.001)  # > 0.20

    def test_confirm_medium_confidence_low_gap(self):
        """CONFIRM при среднем confidence и маленьком gap."""
        router = ConfidenceRouter()

        result = router.route({
            "intent": "request_brevity",
            "confidence": 0.68,
            "alternatives": [
                {"intent": "objection_think", "confidence": 0.55}
            ]
        })

        assert result.decision == RouterDecision.CONFIRM
        assert result.gap == pytest.approx(0.13, abs=0.001)  # < 0.20

    def test_disambiguate_low_confidence(self):
        """DISAMBIGUATE при низком confidence."""
        router = ConfidenceRouter()

        result = router.route({
            "intent": "unclear",
            "confidence": 0.50,
            "alternatives": [
                {"intent": "agreement", "confidence": 0.40},
                {"intent": "objection_think", "confidence": 0.35}
            ]
        })

        assert result.decision == RouterDecision.DISAMBIGUATE
        assert len(result.options) >= 2  # Минимум top-1 + альтернативы + "Другое"

    def test_fallback_very_low_confidence(self):
        """FALLBACK при очень низком confidence."""
        router = ConfidenceRouter()

        result = router.route({
            "intent": "unclear",
            "confidence": 0.25,  # < 0.30
            "alternatives": []
        })

        assert result.decision == RouterDecision.FALLBACK

    def test_execute_no_alternatives(self):
        """EXECUTE если нет alternatives (gap = 1.0)."""
        router = ConfidenceRouter()

        result = router.route({
            "intent": "greeting",
            "confidence": 0.95,
            "alternatives": []
        })

        assert result.decision == RouterDecision.EXECUTE
        assert result.gap == 1.0


class TestDisambiguationOptions:
    """Тесты формирования опций для disambiguation."""

    def test_options_include_top_intent(self):
        """Опции включают top интент."""
        router = ConfidenceRouter()

        result = router.route({
            "intent": "price_question",
            "confidence": 0.50,
            "alternatives": [
                {"intent": "pricing_details", "confidence": 0.40}
            ]
        })

        intents = [o.intent for o in result.options]
        assert "price_question" in intents

    def test_options_include_alternatives(self):
        """Опции включают alternatives."""
        router = ConfidenceRouter()

        result = router.route({
            "intent": "request_brevity",
            "confidence": 0.45,
            "alternatives": [
                {"intent": "objection_think", "confidence": 0.40},
                {"intent": "objection_no_time", "confidence": 0.30}
            ]
        })

        intents = [o.intent for o in result.options]
        assert "objection_think" in intents or "objection_no_time" in intents

    def test_options_include_other(self):
        """Опции всегда включают 'Другое'."""
        router = ConfidenceRouter()

        result = router.route({
            "intent": "unclear",
            "confidence": 0.40,
            "alternatives": []
        })

        intents = [o.intent for o in result.options]
        assert "other" in intents

    def test_options_no_duplicates(self):
        """Опции не содержат дубликатов."""
        router = ConfidenceRouter()

        result = router.route({
            "intent": "agreement",
            "confidence": 0.50,
            "alternatives": [
                {"intent": "agreement", "confidence": 0.50},  # Дубликат
                {"intent": "demo_request", "confidence": 0.40}
            ]
        })

        intents = [o.intent for o in result.options]
        assert len(intents) == len(set(intents))  # Все уникальные

    def test_options_have_labels(self):
        """Все опции имеют человекочитаемые labels."""
        router = ConfidenceRouter()

        result = router.route({
            "intent": "price_question",
            "confidence": 0.45,
            "alternatives": [
                {"intent": "pricing_details", "confidence": 0.35}
            ]
        })

        for option in result.options:
            assert option.label is not None
            assert len(option.label) > 0


class TestConfirmQuestion:
    """Тесты формирования уточняющих вопросов."""

    def test_confirm_question_for_demo(self):
        """Уточняющий вопрос для demo_request."""
        router = ConfidenceRouter()

        result = router.route({
            "intent": "demo_request",
            "confidence": 0.87,
            "alternatives": [
                {"intent": "agreement", "confidence": 0.80}
            ]
        })

        assert result.decision == RouterDecision.CONFIRM
        assert "демо" in result.confirm_question.lower()

    def test_confirm_question_for_price(self):
        """Уточняющий вопрос для price_question."""
        router = ConfidenceRouter()

        result = router.route({
            "intent": "price_question",
            "confidence": 0.86,
            "alternatives": [
                {"intent": "pricing_details", "confidence": 0.82}
            ]
        })

        assert result.decision == RouterDecision.CONFIRM
        assert "стоимость" in result.confirm_question.lower() or "цен" in result.confirm_question.lower()


class TestIntentLabels:
    """Тесты маппинга интентов на labels."""

    def test_all_main_intents_have_labels(self):
        """Все основные интенты имеют labels."""
        main_intents = [
            "price_question", "question_features", "objection_price",
            "demo_request", "callback_request", "agreement", "rejection",
            "request_brevity", "objection_competitor"
        ]

        for intent in main_intents:
            assert intent in INTENT_LABELS
            assert len(INTENT_LABELS[intent]) > 0

    def test_labels_are_human_readable(self):
        """Labels человекочитаемые (на русском, кроме брендов)."""
        # Brand names legitimately in Latin script
        brand_exceptions = {"question_whatsapp_business"}
        # Проверяем что labels содержат русские буквы
        for intent, label in INTENT_LABELS.items():
            if intent in brand_exceptions:
                continue
            assert any(ord(c) >= 0x0400 and ord(c) <= 0x04FF for c in label), \
                f"Label for {intent} should be in Russian"


class TestCustomThresholds:
    """Тесты кастомных порогов."""

    def test_custom_high_threshold(self):
        """Кастомный high_confidence threshold."""
        router = ConfidenceRouter(high_confidence=0.95)

        # 0.90 теперь не high confidence
        result = router.route({
            "intent": "greeting",
            "confidence": 0.90,
            "alternatives": [{"intent": "small_talk", "confidence": 0.20}]
        })

        # С gap 0.70 > 0.20 должен быть EXECUTE (medium confidence + high gap)
        assert result.decision == RouterDecision.EXECUTE

    def test_custom_gap_threshold(self):
        """Кастомный gap_threshold."""
        router = ConfidenceRouter(gap_threshold=0.30)

        # 0.15 gap теперь маленький (< 0.30)
        result = router.route({
            "intent": "greeting",
            "confidence": 0.90,
            "alternatives": [{"intent": "small_talk", "confidence": 0.75}]
        })

        assert result.decision == RouterDecision.CONFIRM

    def test_custom_min_threshold(self):
        """Кастомный min_confidence threshold."""
        router = ConfidenceRouter(min_confidence=0.40)

        # 0.35 теперь ниже минимума
        result = router.route({
            "intent": "unclear",
            "confidence": 0.35,
            "alternatives": []
        })

        assert result.decision == RouterDecision.FALLBACK


class TestRouterStatistics:
    """Тесты статистики роутера."""

    def test_stats_initial(self):
        """Начальная статистика."""
        router = ConfidenceRouter()
        stats = router.get_stats()

        assert stats["total_routes"] == 0
        assert all(v == 0 for v in stats["decisions"].values())

    def test_stats_after_routing(self):
        """Статистика после роутинга."""
        router = ConfidenceRouter()

        # EXECUTE
        router.route({"intent": "greeting", "confidence": 0.95, "alternatives": []})

        # DISAMBIGUATE
        router.route({"intent": "unclear", "confidence": 0.50, "alternatives": []})

        stats = router.get_stats()

        assert stats["total_routes"] == 2
        assert stats["decisions"]["execute"] == 1
        assert stats["decisions"]["disambiguate"] == 1


class TestLogging:
    """Тесты логирования слепых зон."""

    def test_log_uncertain_creates_file(self):
        """Логирование создаёт файл."""
        with tempfile.TemporaryDirectory() as tmpdir:
            router = ConfidenceRouter(
                log_uncertain=True,
                log_dir=tmpdir
            )

            # Trigger DISAMBIGUATE для логирования
            router.route({
                "intent": "unclear",
                "confidence": 0.45,
                "alternatives": [],
                "_original_message": "тестовое сообщение"
            })

            # Проверяем что файл создан
            log_files = list(Path(tmpdir).glob("uncertain_*.jsonl"))
            assert len(log_files) == 1

    def test_log_entry_format(self):
        """Формат записи в логе."""
        with tempfile.TemporaryDirectory() as tmpdir:
            router = ConfidenceRouter(
                log_uncertain=True,
                log_dir=tmpdir
            )

            router.route({
                "intent": "request_brevity",
                "confidence": 0.45,
                "alternatives": [{"intent": "objection_think", "confidence": 0.40}],
                "_original_message": "хватит болтать"
            })

            log_file = list(Path(tmpdir).glob("uncertain_*.jsonl"))[0]
            with open(log_file) as f:
                entry = json.loads(f.readline())

            assert "timestamp" in entry
            assert entry["message"] == "хватит болтать"
            assert entry["top_intent"] == "request_brevity"
            assert entry["confidence"] == 0.45

    def test_no_log_for_execute(self):
        """EXECUTE не логируется."""
        with tempfile.TemporaryDirectory() as tmpdir:
            router = ConfidenceRouter(
                log_uncertain=True,
                log_dir=tmpdir
            )

            router.route({
                "intent": "greeting",
                "confidence": 0.95,
                "alternatives": []
            })

            log_files = list(Path(tmpdir).glob("uncertain_*.jsonl"))
            assert len(log_files) == 0


class TestSingleton:
    """Тесты singleton паттерна."""

    def test_get_confidence_router_returns_same_instance(self):
        """get_confidence_router возвращает один и тот же экземпляр."""
        router1 = get_confidence_router()
        router2 = get_confidence_router()

        assert router1 is router2


class TestEdgeCases:
    """Тесты граничных случаев."""

    def test_empty_alternatives(self):
        """Пустой список alternatives."""
        router = ConfidenceRouter()

        result = router.route({
            "intent": "greeting",
            "confidence": 0.90,
            "alternatives": []
        })

        assert result.gap == 1.0  # Явный лидер

    def test_missing_alternatives_key(self):
        """Отсутствующий ключ alternatives."""
        router = ConfidenceRouter()

        result = router.route({
            "intent": "greeting",
            "confidence": 0.90
        })

        assert result.gap == 1.0

    def test_missing_confidence_in_alternative(self):
        """Alternative без confidence."""
        router = ConfidenceRouter()

        result = router.route({
            "intent": "greeting",
            "confidence": 0.90,
            "alternatives": [{"intent": "small_talk"}]  # Нет confidence
        })

        assert result.gap == 0.90  # 0.90 - 0.0

    def test_zero_confidence(self):
        """Нулевой confidence."""
        router = ConfidenceRouter()

        result = router.route({
            "intent": "unclear",
            "confidence": 0.0,
            "alternatives": []
        })

        assert result.decision == RouterDecision.FALLBACK


class TestIntegrationWithClassification:
    """Интеграционные тесты с форматом ClassificationResult."""

    def test_llm_classification_format(self):
        """Формат результата LLM классификатора."""
        router = ConfidenceRouter()

        # Формат как возвращает LLMClassifier
        classification_result = {
            "intent": "request_brevity",
            "confidence": 0.85,
            "extracted_data": {},
            "method": "llm",
            "reasoning": "Клиент просит краткость",
            "alternatives": [
                {"intent": "objection_think", "confidence": 0.45},
                {"intent": "objection_no_time", "confidence": 0.30}
            ]
        }

        result = router.route(classification_result)

        assert result.decision == RouterDecision.EXECUTE  # 0.85 >= 0.85 и gap 0.40 >= 0.20
        assert result.classification_result == classification_result

    def test_disambiguation_needed_scenario(self):
        """Сценарий когда нужно disambiguation."""
        router = ConfidenceRouter()

        classification_result = {
            "intent": "request_brevity",
            "confidence": 0.52,
            "alternatives": [
                {"intent": "objection_think", "confidence": 0.48},
                {"intent": "objection_no_time", "confidence": 0.35}
            ]
        }

        result = router.route(classification_result)

        assert result.decision == RouterDecision.DISAMBIGUATE
        assert len(result.options) >= 3  # top + alternatives + "Другое"


class TestRealWorldScenarios:
    """Тесты на реальных сценариях из исходной проблемы."""

    def test_ne_gruzite_menya(self):
        """
        'не грузите меня, скажите суть'
        Ожидание: уточнить если confidence близок между request_brevity и objection_think
        """
        router = ConfidenceRouter()

        # Симуляция двусмысленной классификации
        result = router.route({
            "intent": "request_brevity",
            "confidence": 0.55,
            "alternatives": [
                {"intent": "objection_think", "confidence": 0.45}
            ],
            "_original_message": "не грузите меня, скажите суть"
        })

        # Gap = 0.10 < 0.20, confidence < 0.65 → DISAMBIGUATE
        assert result.decision == RouterDecision.DISAMBIGUATE

    def test_u_nas_poster(self):
        """
        'у нас Poster, зачем нам вы?'
        Ожидание: EXECUTE если уверены в objection_competitor
        """
        router = ConfidenceRouter()

        result = router.route({
            "intent": "objection_competitor",
            "confidence": 0.90,
            "alternatives": [
                {"intent": "comparison", "confidence": 0.40}
            ],
            "_original_message": "у нас Poster, зачем нам вы?"
        })

        # Gap = 0.50 > 0.20, confidence = 0.90 >= 0.85 → EXECUTE
        assert result.decision == RouterDecision.EXECUTE

    def test_hvat_boltat(self):
        """
        'хватит болтать' - новая фраза, не было в примерах
        Ожидание: если LLM выдаст низкий confidence, показать варианты
        """
        router = ConfidenceRouter()

        # Симуляция: LLM не уверен в новой фразе
        result = router.route({
            "intent": "request_brevity",
            "confidence": 0.48,
            "alternatives": [
                {"intent": "rejection", "confidence": 0.35},
                {"intent": "objection_no_time", "confidence": 0.30}
            ],
            "_original_message": "хватит болтать"
        })

        # confidence < 0.65 → DISAMBIGUATE
        assert result.decision == RouterDecision.DISAMBIGUATE

        # Проверяем что есть опция request_brevity
        intents = [o.intent for o in result.options]
        assert "request_brevity" in intents

    def test_clear_agreement(self):
        """
        'да, давайте'
        Ожидание: EXECUTE если явное согласие
        """
        router = ConfidenceRouter()

        result = router.route({
            "intent": "agreement",
            "confidence": 0.92,
            "alternatives": [
                {"intent": "demo_request", "confidence": 0.30}
            ]
        })

        assert result.decision == RouterDecision.EXECUTE
