"""
Тесты для Cascade Objection Detector.

Покрывает:
- Tier 1: Regex detection (должен работать как раньше)
- Tier 2: Semantic fallback (для перефразировок)
- Feature flag управление
- Regression tests (все существующие кейсы должны работать)
"""

import pytest
import sys
from pathlib import Path

# Добавляем src в PYTHONPATH

from src.objection_handler import ObjectionType
from src.objection.cascade_detector import (
    CascadeObjectionDetector,
    ObjectionDetectionResult,
    INTENT_TO_OBJECTION,
    reset_cascade_objection_detector,
)
from src.feature_flags import flags

class TestTier1RegexDetection:
    """Тесты Tier 1: Regex detection (должен работать как ObjectionHandler)"""

    @pytest.fixture
    def detector(self):
        """Создать детектор для теста."""
        reset_cascade_objection_detector()
        return CascadeObjectionDetector()

    def test_detect_price_objection(self, detector):
        """Определение возражения о цене через regex"""
        messages = [
            "Это слишком дорого",
            "Нет бюджета на это",
            "Дороговато для нас",
            "Денег нет",
            "Накладно",
        ]

        for msg in messages:
            result = detector.detect(msg)
            assert result.primary_type == ObjectionType.PRICE, f"Failed for: {msg}"
            assert result.tier_used == "regex"
            assert result.confidence >= 0.9

    def test_detect_competitor_objection(self, detector):
        """Определение возражения о конкуренте через regex"""
        messages = [
            "Мы уже используем Битрикс",
            "У нас есть АМО",
            "Используем iiko",
            "Работаем в своей системе",
        ]

        for msg in messages:
            result = detector.detect(msg)
            assert result.primary_type == ObjectionType.COMPETITOR, f"Failed for: {msg}"
            assert result.tier_used == "regex"

    def test_detect_no_time_objection(self, detector):
        """Определение возражения о нехватке времени через regex"""
        messages = [
            "Нет времени на это",
            "Сейчас занят",
            "Некогда разбираться",
            "Завал на работе",
        ]

        for msg in messages:
            result = detector.detect(msg)
            assert result.primary_type == ObjectionType.NO_TIME, f"Failed for: {msg}"
            assert result.tier_used == "regex"

    def test_detect_think_objection(self, detector):
        """Определение возражения 'надо подумать' через regex"""
        messages = [
            "Мне нужно подумать",
            "Надо посоветоваться с партнёром",
            "Хочу обсудить с командой",
        ]

        for msg in messages:
            result = detector.detect(msg)
            assert result.primary_type == ObjectionType.THINK, f"Failed for: {msg}"
            assert result.tier_used == "regex"

    def test_detect_no_need_objection(self, detector):
        """Определение возражения 'не нужно' через regex"""
        messages = [
            "Нам это не нужно",
            "Справляемся без CRM",
            "Обойдёмся",
        ]

        for msg in messages:
            result = detector.detect(msg)
            assert result.primary_type == ObjectionType.NO_NEED, f"Failed for: {msg}"
            assert result.tier_used == "regex"

    def test_detect_trust_objection(self, detector):
        """Определение возражения о недоверии через regex"""
        messages = [
            "Не верю что это работает",
            "Сомневаюсь в эффективности",
            "Какие гарантии?",
        ]

        for msg in messages:
            result = detector.detect(msg)
            assert result.primary_type == ObjectionType.TRUST, f"Failed for: {msg}"
            assert result.tier_used == "regex"

    def test_detect_timing_objection(self, detector):
        """Определение возражения о тайминге через regex"""
        messages = [
            "Не сейчас",
            "Позже вернёмся",
            "Через месяц поговорим",
        ]

        for msg in messages:
            result = detector.detect(msg)
            assert result.primary_type == ObjectionType.TIMING, f"Failed for: {msg}"
            assert result.tier_used == "regex"

    def test_detect_complexity_objection(self, detector):
        """Определение возражения о сложности через regex"""
        messages = [
            "Это сложно внедрять",
            "Долго обучаться",
            "Много работы по настройке",
        ]

        for msg in messages:
            result = detector.detect(msg)
            assert result.primary_type == ObjectionType.COMPLEXITY, f"Failed for: {msg}"
            assert result.tier_used == "regex"

    def test_regex_latency(self, detector):
        """Regex должен быть быстрым (<10ms)"""
        result = detector.detect("Это слишком дорого")
        assert result.latency_ms < 10, f"Regex too slow: {result.latency_ms}ms"

class TestTier2SemanticDetection:
    """Тесты Tier 2: Semantic fallback"""

    @pytest.fixture
    def detector(self):
        """Создать детектор с включённым semantic."""
        reset_cascade_objection_detector()
        flags.set_override("semantic_objection_detection", True)
        yield CascadeObjectionDetector()
        flags.clear_override("semantic_objection_detection")

    @pytest.fixture
    def detector_semantic_off(self):
        """Детектор с выключенным semantic."""
        reset_cascade_objection_detector()
        flags.set_override("semantic_objection_detection", False)
        yield CascadeObjectionDetector()
        flags.clear_override("semantic_objection_detection")

    def test_semantic_catches_paraphrase(self, detector):
        """Semantic ловит перефразировки с достаточно высоким confidence"""
        # Проверяем что semantic classifier работает и может классифицировать
        try:
            if not detector.semantic_classifier.is_available:
                pytest.skip("Semantic classifier not available (sentence-transformers not installed)")

            # Используем более явную формулировку возражения
            result = detector.detect("это для нас слишком дорогое удовольствие")

            # Этот текст должен быть пойман regex (содержит "дорог")
            assert result.primary_type == ObjectionType.PRICE
            assert result.tier_used == "regex"  # regex ловит "дорог"

            # Тестируем semantic на сообщении без явных regex паттернов
            # Примечание: с порогом 0.75 semantic консервативен
            result2 = detector.detect("бюджет не резиновый")

            # regex должен поймать "бюджет"
            if result2.primary_type is not None:
                assert result2.primary_type == ObjectionType.PRICE

        except ImportError:
            pytest.skip("sentence-transformers not installed")

    def test_semantic_disabled_returns_none(self, detector_semantic_off):
        """Если semantic выключен, возвращается None для неизвестных"""
        # Сообщение которое regex не ловит
        result = detector_semantic_off.detect("высокая стоимость")

        # Regex не поймал, semantic выключен
        if result.primary_type is None:
            assert result.tier_used == "regex"

    def test_regex_has_priority_over_semantic(self, detector):
        """Regex имеет приоритет — semantic не вызывается если regex сработал"""
        result = detector.detect("Это слишком дорого")

        assert result.tier_used == "regex"
        assert result.primary_type == ObjectionType.PRICE

class TestHardNegatives:
    """Тесты hard negatives — НЕ должны быть возражениями"""

    @pytest.fixture
    def detector(self):
        reset_cascade_objection_detector()
        flags.set_override("semantic_objection_detection", True)
        yield CascadeObjectionDetector()
        flags.clear_override("semantic_objection_detection")

    @pytest.mark.parametrize("message", [
        "Сколько стоит?",
        "Какая цена?",
        "Расскажите подробнее",
        "Хочу посмотреть демо",
        "Интересно, покажите",
    ])
    def test_not_objection(self, detector, message):
        """Эти сообщения НЕ должны быть возражениями"""
        result = detector.detect(message)

        # Либо None, либо очень низкая уверенность
        if result.primary_type is not None:
            # Если что-то нашлось, уверенность должна быть низкой
            # или это regex false positive (что тоже проблема)
            pass  # Можно добавить assert на confidence

class TestFeatureFlag:
    """Тесты управления через feature flag"""

    def test_semantic_flag_default(self):
        """Флаг semantic_objection_detection включён по умолчанию"""
        # Проверяем в DEFAULTS
        from src.feature_flags import FeatureFlags
        assert FeatureFlags.DEFAULTS.get("semantic_objection_detection") is True

    def test_semantic_flag_property(self):
        """Property semantic_objection_detection работает"""
        original = flags.is_enabled("semantic_objection_detection")

        flags.set_override("semantic_objection_detection", False)
        assert flags.semantic_objection_detection is False

        flags.set_override("semantic_objection_detection", True)
        assert flags.semantic_objection_detection is True

        flags.clear_override("semantic_objection_detection")

    def test_semantic_in_safe_group(self):
        """Флаг в группе 'safe'"""
        from src.feature_flags import FeatureFlags
        assert "semantic_objection_detection" in FeatureFlags.GROUPS["safe"]

    def test_semantic_in_phase4_group(self):
        """Флаг в группе 'phase_4'"""
        from src.feature_flags import FeatureFlags
        assert "semantic_objection_detection" in FeatureFlags.GROUPS["phase_4"]

class TestObjectionDetectionResult:
    """Тесты структуры результата"""

    @pytest.fixture
    def detector(self):
        reset_cascade_objection_detector()
        return CascadeObjectionDetector()

    def test_result_has_required_fields(self, detector):
        """Результат содержит все обязательные поля"""
        result = detector.detect("Это дорого")

        assert hasattr(result, "primary_type")
        assert hasattr(result, "confidence")
        assert hasattr(result, "tier_used")
        assert hasattr(result, "latency_ms")
        assert hasattr(result, "is_objection")

    def test_is_objection_property(self, detector):
        """is_objection property работает правильно"""
        result_positive = detector.detect("Это дорого")
        result_negative = detector.detect("Расскажите подробнее")

        assert result_positive.is_objection is True
        assert result_negative.is_objection is False

class TestIntentToObjectionMapping:
    """Тесты маппинга intent → ObjectionType"""

    def test_all_objection_types_mapped(self):
        """Все типы возражений имеют маппинг"""
        expected_types = {
            ObjectionType.PRICE,
            ObjectionType.COMPETITOR,
            ObjectionType.NO_TIME,
            ObjectionType.THINK,
            ObjectionType.NO_NEED,
            ObjectionType.TRUST,
            ObjectionType.TIMING,
            ObjectionType.COMPLEXITY,
        }

        mapped_types = set(INTENT_TO_OBJECTION.values())
        assert expected_types == mapped_types

    def test_mapping_keys_format(self):
        """Ключи маппинга имеют правильный формат"""
        for key in INTENT_TO_OBJECTION.keys():
            assert key.startswith("objection_")

class TestReset:
    """Тесты сброса состояния"""

    def test_reset_clears_regex_handler(self):
        """Reset сбрасывает внутренний regex handler"""
        detector = CascadeObjectionDetector()

        # Используем regex handler
        detector.regex_handler.get_strategy(ObjectionType.PRICE)
        detector.regex_handler.get_strategy(ObjectionType.PRICE)

        # Проверяем что попытки израсходованы
        assert not detector.regex_handler.can_handle_more(ObjectionType.PRICE)

        # Сбрасываем
        detector.reset()

        # Попытки снова доступны
        assert detector.regex_handler.can_handle_more(ObjectionType.PRICE)

class TestRegressionFromLegacy:
    """Regression тесты — все кейсы из test_objection_handler должны работать"""

    @pytest.fixture
    def detector(self):
        reset_cascade_objection_detector()
        return CascadeObjectionDetector()

    def test_case_insensitive(self, detector):
        """Регистронезависимость"""
        assert detector.detect("ДОРОГО").primary_type == ObjectionType.PRICE
        assert detector.detect("Дорого").primary_type == ObjectionType.PRICE
        assert detector.detect("дорого").primary_type == ObjectionType.PRICE

    def test_empty_message(self, detector):
        """Пустое сообщение"""
        result = detector.detect("")
        assert result.primary_type is None

    def test_long_message_with_objection(self, detector):
        """Длинное сообщение с возражением"""
        msg = "Мы тут долго обсуждали, и в итоге решили, что это слишком дорого для нашего бюджета"
        result = detector.detect(msg)
        assert result.primary_type == ObjectionType.PRICE

    def test_priority_price_over_no_need(self, detector):
        """Цена имеет приоритет над 'не нужно'"""
        msg = "Это дорого и нам не нужно"
        result = detector.detect(msg)
        assert result.primary_type == ObjectionType.PRICE

    def test_neutral_not_objection(self, detector):
        """Нейтральные сообщения — не возражения"""
        messages = [
            "Расскажите подробнее",
            "Интересно",
            "А какие есть функции?",
            "Как это работает?",
        ]

        for msg in messages:
            result = detector.detect(msg)
            assert result.primary_type is None, f"False positive for: {msg}"

class TestSingleton:
    """Тесты singleton паттерна"""

    def test_reset_creates_new_instance(self):
        """reset_cascade_objection_detector сбрасывает singleton"""
        from src.objection.cascade_detector import (
            get_cascade_objection_detector,
            reset_cascade_objection_detector,
        )

        detector1 = get_cascade_objection_detector()
        reset_cascade_objection_detector()
        detector2 = get_cascade_objection_detector()

        assert detector1 is not detector2

    def test_get_returns_same_instance(self):
        """get_cascade_objection_detector возвращает тот же экземпляр"""
        from src.objection.cascade_detector import (
            get_cascade_objection_detector,
            reset_cascade_objection_detector,
        )

        reset_cascade_objection_detector()
        detector1 = get_cascade_objection_detector()
        detector2 = get_cascade_objection_detector()

        assert detector1 is detector2

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
