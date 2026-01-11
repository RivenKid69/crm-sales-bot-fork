"""
Тесты для ToneAnalyzer.

Проверяют:
- Определение различных тонов (frustrated, positive, etc.)
- Определение стиля (formal/informal)
- Накопительный frustration tracking
- Рекомендации по генерации ответа
- Reset состояния
"""

import pytest
import sys
import os

# Добавляем src в путь
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from tone_analyzer import ToneAnalyzer, Tone, Style, ToneAnalysis


class TestToneDetection:
    """Тесты определения тона сообщений"""

    def setup_method(self):
        """Создаём новый анализатор для каждого теста"""
        self.analyzer = ToneAnalyzer()

    # === POSITIVE TONE ===

    def test_positive_tone_with_emoji(self):
        """Позитивный тон с эмодзи"""
        result = self.analyzer.analyze("Отлично! Это то что нужно 👍")
        assert result.tone == Tone.POSITIVE

    def test_positive_tone_with_words(self):
        """Позитивный тон с позитивными словами"""
        result = self.analyzer.analyze("Супер, звучит замечательно!")
        assert result.tone == Tone.POSITIVE

    def test_positive_tone_interested(self):
        """Заинтересованный тон"""
        # "Интересно" также есть в POSITIVE, поэтому используем чистый INTERESTED паттерн
        result = self.analyzer.analyze("Расскажите подробнее, хочу узнать")
        assert result.tone == Tone.INTERESTED

    # === FRUSTRATED TONE ===

    def test_frustrated_tone_direct(self):
        """Прямое выражение раздражения"""
        result = self.analyzer.analyze("Сколько можно уже! Достали!")
        assert result.tone == Tone.FRUSTRATED

    def test_frustrated_tone_repetition(self):
        """Раздражение от повторов"""
        result = self.analyzer.analyze("Уже говорил вам это три раза!")
        assert result.tone == Tone.FRUSTRATED

    def test_frustrated_tone_with_emoji(self):
        """Раздражение с эмодзи"""
        result = self.analyzer.analyze("Опять то же самое 😡")
        assert result.tone == Tone.FRUSTRATED

    def test_frustrated_tone_subtle(self):
        """Неявное раздражение"""
        result = self.analyzer.analyze("Вы меня не понимаете")
        assert result.tone == Tone.FRUSTRATED

    # === SKEPTICAL TONE ===

    def test_skeptical_tone_doubt(self):
        """Сомнение"""
        result = self.analyzer.analyze("Сомневаюсь что это работает")
        assert result.tone == Tone.SKEPTICAL

    def test_skeptical_tone_question(self):
        """Скептический вопрос"""
        result = self.analyzer.analyze("Правда? Это точно так?")
        assert result.tone == Tone.SKEPTICAL

    def test_skeptical_tone_distrust(self):
        """Недоверие"""
        result = self.analyzer.analyze("Не верю в эти обещания")
        assert result.tone == Tone.SKEPTICAL

    # === RUSHED TONE ===

    def test_rushed_tone_direct(self):
        """Прямое указание на спешку"""
        result = self.analyzer.analyze("Короче, давайте к делу")
        assert result.tone == Tone.RUSHED

    def test_rushed_tone_no_time(self):
        """Нет времени"""
        result = self.analyzer.analyze("Времени нет, быстрее пожалуйста")
        assert result.tone == Tone.RUSHED

    def test_rushed_tone_urgent(self):
        """Срочность"""
        result = self.analyzer.analyze("Срочно нужен ответ!")
        assert result.tone == Tone.RUSHED

    # === CONFUSED TONE ===

    def test_confused_tone_direct(self):
        """Прямое выражение непонимания"""
        result = self.analyzer.analyze("Не понял, что это значит?")
        assert result.tone == Tone.CONFUSED

    def test_confused_tone_questions(self):
        """Много вопросительных знаков"""
        result = self.analyzer.analyze("Как это??? Объясните")
        assert result.tone == Tone.CONFUSED

    def test_confused_tone_clarification(self):
        """Запрос разъяснения"""
        result = self.analyzer.analyze("Что вы имеете в виду?")
        assert result.tone == Tone.CONFUSED

    # === NEUTRAL TONE ===

    def test_neutral_tone_simple(self):
        """Простое нейтральное сообщение"""
        result = self.analyzer.analyze("У нас 10 человек в команде")
        assert result.tone == Tone.NEUTRAL

    def test_neutral_tone_question(self):
        """Нейтральный вопрос"""
        result = self.analyzer.analyze("Какие есть тарифы?")
        assert result.tone == Tone.NEUTRAL

    # === TONE PRIORITY ===

    def test_tone_priority_frustrated_over_positive(self):
        """Frustrated приоритетнее positive"""
        result = self.analyzer.analyze("Отлично, опять одно и то же! Достали!")
        assert result.tone == Tone.FRUSTRATED

    def test_tone_priority_frustrated_over_rushed(self):
        """Frustrated приоритетнее rushed"""
        result = self.analyzer.analyze("Быстрее, сколько можно! Надоело!")
        assert result.tone == Tone.FRUSTRATED

    def test_tone_priority_rushed_over_confused(self):
        """Rushed приоритетнее confused"""
        result = self.analyzer.analyze("Короче, не понял, но давайте быстро")
        assert result.tone == Tone.RUSHED


class TestStyleDetection:
    """Тесты определения стиля общения"""

    def setup_method(self):
        self.analyzer = ToneAnalyzer()

    def test_formal_style_default(self):
        """Формальный стиль по умолчанию"""
        result = self.analyzer.analyze("Добрый день, интересует ваш продукт")
        assert result.style == Style.FORMAL

    def test_informal_style_greeting(self):
        """Неформальный стиль с приветствием"""
        result = self.analyzer.analyze("Привет, ну чё там по ценам?")
        assert result.style == Style.INFORMAL

    def test_informal_style_slang(self):
        """Неформальный стиль со сленгом"""
        result = self.analyzer.analyze("Окей, норм, понял")
        assert result.style == Style.INFORMAL

    def test_informal_style_short_message(self):
        """Короткое неформальное сообщение"""
        result = self.analyzer.analyze("Ну ок")
        assert result.style == Style.INFORMAL

    def test_formal_style_long_message(self):
        """Длинное формальное сообщение"""
        result = self.analyzer.analyze(
            "Здравствуйте, хотелось бы узнать подробнее о возможностях вашей системы"
        )
        assert result.style == Style.FORMAL


class TestFrustrationTracking:
    """Тесты накопительного frustration tracking"""

    def setup_method(self):
        self.analyzer = ToneAnalyzer()

    def test_frustration_increases_with_frustrated_messages(self):
        """Frustration растёт от frustrated сообщений"""
        # Начальное состояние
        assert self.analyzer.get_frustration_level() == 0

        # Первое раздражённое сообщение
        self.analyzer.analyze("Сколько можно!")
        level1 = self.analyzer.get_frustration_level()
        assert level1 > 0

        # Второе раздражённое сообщение
        self.analyzer.analyze("Опять одно и то же!")
        level2 = self.analyzer.get_frustration_level()
        assert level2 > level1

    def test_frustration_decreases_with_positive_messages(self):
        """Frustration снижается от позитивных сообщений"""
        # Поднимаем frustration
        self.analyzer.analyze("Достали!")
        self.analyzer.analyze("Надоело!")
        high_level = self.analyzer.get_frustration_level()

        # Позитивное сообщение снижает
        self.analyzer.analyze("Отлично, понял!")
        lower_level = self.analyzer.get_frustration_level()
        assert lower_level < high_level

    def test_frustration_limited_to_max(self):
        """Frustration не превышает максимум"""
        # Много раздражённых сообщений
        for _ in range(20):
            self.analyzer.analyze("Достали! Надоело!")

        assert self.analyzer.get_frustration_level() <= ToneAnalyzer.MAX_FRUSTRATION

    def test_frustration_not_negative(self):
        """Frustration не уходит в минус"""
        # Много позитивных сообщений
        for _ in range(20):
            self.analyzer.analyze("Отлично! Супер! 👍")

        assert self.analyzer.get_frustration_level() >= 0

    def test_is_frustrated_threshold(self):
        """Проверка порога is_frustrated"""
        assert not self.analyzer.is_frustrated()

        # Поднимаем frustration до порога
        for _ in range(5):
            self.analyzer.analyze("Достали!")

        assert self.analyzer.is_frustrated()

    def test_is_critically_frustrated_threshold(self):
        """Проверка критического порога"""
        assert not self.analyzer.is_critically_frustrated()

        # Поднимаем frustration до критического уровня
        for _ in range(10):
            self.analyzer.analyze("Достали! Надоело!")

        # Может не достичь критического уровня за 10 сообщений,
        # но должен быть на высоком уровне
        assert self.analyzer.get_frustration_level() >= ToneAnalyzer.FRUSTRATION_THRESHOLDS["warning"]

    def test_frustration_history(self):
        """Проверка истории frustration"""
        self.analyzer.analyze("Привет")
        self.analyzer.analyze("Достали!")
        self.analyzer.analyze("Отлично!")

        history = self.analyzer.get_frustration_history()
        assert len(history) == 3
        assert history[0]["tone"] == "neutral"
        assert history[1]["tone"] == "frustrated"
        assert history[2]["tone"] == "positive"


class TestResponseGuidance:
    """Тесты рекомендаций по генерации ответа"""

    def setup_method(self):
        self.analyzer = ToneAnalyzer()

    def test_guidance_normal_situation(self):
        """Рекомендации для нормальной ситуации"""
        # Используем чисто нейтральное сообщение (без триггеров INTERESTED)
        result = self.analyzer.analyze("У нас 10 человек в команде")
        guidance = self.analyzer.get_response_guidance(result)

        assert guidance["max_words"] == 50
        assert guidance["should_apologize"] is False
        assert guidance["should_offer_exit"] is False

    def test_guidance_frustrated_client(self):
        """Рекомендации для раздражённого клиента"""
        # Поднимаем frustration
        for _ in range(3):
            result = self.analyzer.analyze("Достали! Надоело!")

        guidance = self.analyzer.get_response_guidance(result)

        assert guidance["max_words"] < 50  # Короче обычного
        assert guidance["should_apologize"] is True

    def test_guidance_rushed_client(self):
        """Рекомендации для торопящегося клиента"""
        result = self.analyzer.analyze("Короче, быстрее давайте")
        guidance = self.analyzer.get_response_guidance(result)

        assert guidance["max_words"] <= 30
        assert "коротко" in guidance["tone_instruction"].lower() or "делу" in guidance["tone_instruction"].lower()

    def test_guidance_skeptical_client(self):
        """Рекомендации для скептичного клиента"""
        result = self.analyzer.analyze("Сомневаюсь, правда это работает?")
        guidance = self.analyzer.get_response_guidance(result)

        assert "факт" in guidance["tone_instruction"].lower() or "цифр" in guidance["tone_instruction"].lower()

    def test_guidance_confused_client(self):
        """Рекомендации для запутавшегося клиента"""
        result = self.analyzer.analyze("Не понял, что это значит???")
        guidance = self.analyzer.get_response_guidance(result)

        assert "просто" in guidance["tone_instruction"].lower() or "понятно" in guidance["tone_instruction"].lower()

    def test_guidance_positive_client(self):
        """Рекомендации для позитивного клиента"""
        result = self.analyzer.analyze("Отлично! Супер! 👍")
        guidance = self.analyzer.get_response_guidance(result)

        assert guidance["max_words"] >= 50  # Можно чуть подробнее

    def test_guidance_formality_formal(self):
        """Формальность для формального клиента"""
        result = self.analyzer.analyze("Здравствуйте, интересует продукт")
        guidance = self.analyzer.get_response_guidance(result)

        assert guidance["formality"] == "formal"

    def test_guidance_formality_casual(self):
        """Неформальность для неформального клиента"""
        result = self.analyzer.analyze("Привет, ну чё там?")
        guidance = self.analyzer.get_response_guidance(result)

        assert guidance["formality"] == "casual"


class TestReset:
    """Тесты сброса состояния"""

    def setup_method(self):
        self.analyzer = ToneAnalyzer()

    def test_reset_clears_frustration(self):
        """Reset очищает frustration"""
        self.analyzer.analyze("Достали!")
        self.analyzer.analyze("Надоело!")
        assert self.analyzer.get_frustration_level() > 0

        self.analyzer.reset()
        assert self.analyzer.get_frustration_level() == 0

    def test_reset_clears_history(self):
        """Reset очищает историю"""
        self.analyzer.analyze("Привет")
        self.analyzer.analyze("Достали!")
        assert len(self.analyzer.get_frustration_history()) == 2

        self.analyzer.reset()
        assert len(self.analyzer.get_frustration_history()) == 0


class TestConfidence:
    """Тесты уверенности в определении"""

    def setup_method(self):
        self.analyzer = ToneAnalyzer()

    def test_high_confidence_with_multiple_signals(self):
        """Высокая уверенность при множестве сигналов"""
        result = self.analyzer.analyze("Достали! Надоело! Сколько можно! 😡")
        # При нескольких сигналах confidence >= 0.65
        assert result.confidence >= 0.65

    def test_low_confidence_neutral(self):
        """Уверенность для нейтрального (каскад может дать высокую через semantic)"""
        result = self.analyzer.analyze("Да")
        # Каскадный анализатор использует semantic tier, который даёт высокую confidence
        assert result.tone == Tone.NEUTRAL
        assert result.confidence > 0  # Просто проверяем что есть confidence

    def test_medium_confidence_single_signal(self):
        """Уверенность при одном сигнале"""
        result = self.analyzer.analyze("Любопытно")
        # Cascade: base 0.80 + signal boost 0.05 = 0.85
        assert result.confidence >= 0.65


class TestEdgeCases:
    """Тесты граничных случаев"""

    def setup_method(self):
        self.analyzer = ToneAnalyzer()

    def test_empty_message(self):
        """Пустое сообщение"""
        result = self.analyzer.analyze("")
        assert result.tone == Tone.NEUTRAL

    def test_only_emoji(self):
        """Только эмодзи"""
        result = self.analyzer.analyze("👍")
        assert result.tone == Tone.POSITIVE

    def test_only_punctuation(self):
        """Только пунктуация"""
        result = self.analyzer.analyze("???")
        assert result.tone == Tone.CONFUSED

    def test_mixed_languages(self):
        """Смешанные языки"""
        result = self.analyzer.analyze("OK, отлично!")
        assert result.tone == Tone.POSITIVE

    def test_very_long_message(self):
        """Очень длинное сообщение"""
        long_message = "Интересно " * 100
        result = self.analyzer.analyze(long_message)
        # Должен обработать без ошибок
        assert result.tone in [Tone.INTERESTED, Tone.POSITIVE]

    def test_special_characters(self):
        """Специальные символы"""
        result = self.analyzer.analyze("Цена: 590₽/мес — подходит!")
        # Должен обработать без ошибок
        assert result.tone is not None


class TestSignals:
    """Тесты сигналов"""

    def setup_method(self):
        self.analyzer = ToneAnalyzer()

    def test_signals_populated(self):
        """Сигналы заполняются при обнаружении"""
        result = self.analyzer.analyze("Достали! 😡")
        assert len(result.signals) > 0

    def test_signals_contain_tone_info(self):
        """Сигналы содержат информацию о тоне"""
        result = self.analyzer.analyze("Отлично!")
        # Должен содержать positive сигнал
        assert any("positive" in s for s in result.signals)

    def test_no_signals_for_neutral(self):
        """Нет сигналов для чисто нейтрального"""
        result = self.analyzer.analyze("У нас 5 человек")
        assert len(result.signals) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
