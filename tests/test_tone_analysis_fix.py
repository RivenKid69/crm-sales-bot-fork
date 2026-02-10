"""
Тесты для проверки исправления tone_analysis.

Проверяют что:
1. Флаг tone_analysis включен по умолчанию
2. Bot._analyze_tone() вызывает реальный анализатор
3. Агрессивные сообщения из e2e симуляции детектируются корректно
4. frustration_level накапливается правильно

BUG FIX: tone_analysis был выключен в settings.yaml, что приводило к:
- frustration_level: 0 во ВСЕХ 2336 turns
- detected_tone: "neutral" даже при агрессивных сообщениях
"""

import pytest
import sys
import os

# Добавляем src в путь

from src.feature_flags import FeatureFlags, flags
from src.tone_analyzer import ToneAnalyzer, Tone, Style, CascadeToneAnalyzer

class TestToneAnalysisFlagEnabled:
    """Проверка что флаг tone_analysis включен"""

    def test_default_flag_is_true(self):
        """Дефолтное значение tone_analysis должно быть True"""
        ff = FeatureFlags()
        assert ff.DEFAULTS.get("tone_analysis") is True, \
            "tone_analysis должен быть True по умолчанию"

    def test_flag_property_returns_true(self):
        """Property tone_analysis должен возвращать True"""
        ff = FeatureFlags()
        # Убедимся что нет override
        ff.clear_all_overrides()
        assert ff.tone_analysis is True, \
            "flags.tone_analysis должен быть True"

    def test_is_enabled_returns_true(self):
        """is_enabled('tone_analysis') должен возвращать True"""
        ff = FeatureFlags()
        ff.clear_all_overrides()
        assert ff.is_enabled("tone_analysis") is True

class TestAggressiveMessagesDetection:
    """Тесты на детекцию агрессивных сообщений из e2e симуляции"""

    def setup_method(self):
        """Создаём новый анализатор для каждого теста"""
        self.analyzer = ToneAnalyzer()

    def test_detect_frustrated_stop_annoying(self):
        """'Хватит водить за нос!' - должен быть FRUSTRATED"""
        result = self.analyzer.analyze("Хватит водить за нос! Дайте конкретику или уходите!")
        assert result.tone == Tone.FRUSTRATED, \
            f"Ожидался FRUSTRATED, получен {result.tone.value}"
        assert result.frustration_level > 0, \
            "frustration_level должен быть > 0"

    def test_detect_frustrated_stop_water(self):
        """'хватит воды!' - должен быть FRUSTRATED"""
        result = self.analyzer.analyze("хватит воды! Либо дайте решение, либо уходите!")
        assert result.tone == Tone.FRUSTRATED, \
            f"Ожидался FRUSTRATED, получен {result.tone.value}"

    def test_detect_frustrated_not_priority(self):
        """'не грузите меня' - должен быть RUSHED или FRUSTRATED"""
        result = self.analyzer.analyze("не грузите меня, просто скажите суть")
        assert result.tone in [Tone.FRUSTRATED, Tone.RUSHED], \
            f"Ожидался FRUSTRATED/RUSHED, получен {result.tone.value}"

    def test_detect_frustrated_empty_words(self):
        """'Хочу решение, а не пустые слова!' - FRUSTRATED"""
        result = self.analyzer.analyze("Хочу решение, а не пустые слова!")
        assert result.tone == Tone.FRUSTRATED, \
            f"Ожидался FRUSTRATED, получен {result.tone.value}"

    def test_detect_rushed_no_time(self):
        """'Нет времени ждать!' - RUSHED или FRUSTRATED"""
        result = self.analyzer.analyze("Нет времени ждать!")
        assert result.tone in [Tone.RUSHED, Tone.FRUSTRATED], \
            f"Ожидался RUSHED/FRUSTRATED, получен {result.tone.value}"

    def test_detect_skeptic_why_change(self):
        """'зачем менять, если работает?' - SKEPTICAL"""
        result = self.analyzer.analyze("а зачем менять, если всё работает?")
        assert result.tone in [Tone.SKEPTICAL, Tone.NEUTRAL], \
            f"Ожидался SKEPTICAL/NEUTRAL, получен {result.tone.value}"

class TestFrustrationAccumulation:
    """Тесты накопления frustration_level"""

    def setup_method(self):
        self.analyzer = ToneAnalyzer()

    def test_frustration_increases_with_multiple_messages(self):
        """Frustration должен накапливаться при последовательных негативных сообщениях"""
        # Первое сообщение
        r1 = self.analyzer.analyze("Это раздражает!")
        level1 = r1.frustration_level

        # Второе агрессивное сообщение
        r2 = self.analyzer.analyze("Хватит уже! Надоело!")
        level2 = r2.frustration_level

        # Третье агрессивное
        r3 = self.analyzer.analyze("Сколько можно!!!")
        level3 = r3.frustration_level

        assert level2 >= level1, \
            f"frustration должен расти: {level1} -> {level2}"
        assert level3 >= level2, \
            f"frustration должен расти: {level2} -> {level3}"

    def test_frustration_resets_after_reset(self):
        """После reset() frustration должен сброситься"""
        self.analyzer.analyze("Это бесит!!!")
        self.analyzer.analyze("Хватит!")

        # Reset
        self.analyzer.reset()

        # Нейтральное сообщение
        result = self.analyzer.analyze("Сколько стоит?")
        assert result.frustration_level == 0, \
            "После reset frustration должен быть 0"

class TestBotAnalyzeToneIntegration:
    """Интеграционные тесты для Bot._analyze_tone()"""

    def test_analyze_tone_returns_real_analysis(self):
        """Bot._analyze_tone() должен возвращать реальный анализ, а не дефолт"""
        # Импортируем Bot и создаём mock LLM
        from src.bot import SalesBot
        from unittest.mock import MagicMock

        # Создаём mock LLM (бот требует llm)
        mock_llm = MagicMock()

        # Создаём бота
        bot = SalesBot(llm=mock_llm, flow_name="spin_selling")

        # Анализируем агрессивное сообщение
        result = bot._analyze_tone("Хватит водить за нос! Уходите!")

        # Проверяем что это НЕ дефолтные значения
        assert result.get("tone") != "neutral" or result.get("frustration_level", 0) > 0, \
            f"Ожидался реальный анализ, получен дефолт: {result}"

    def test_analyze_tone_not_empty_when_frustrated(self):
        """При фрустрации должны быть заполнены поля"""
        from src.bot import SalesBot
        from unittest.mock import MagicMock

        mock_llm = MagicMock()
        bot = SalesBot(llm=mock_llm, flow_name="spin_selling")
        result = bot._analyze_tone("Это бесит! Сколько можно!")

        # Либо tone не neutral, либо frustration > 0
        tone = result.get("tone", "neutral")
        frustration = result.get("frustration_level", 0)

        assert tone != "neutral" or frustration > 0, \
            f"tone={tone}, frustration={frustration} - должен быть реальный анализ"

class TestCascadeToneAnalyzerWorks:
    """Проверка что каскадный анализатор действительно работает"""

    def setup_method(self):
        self.analyzer = CascadeToneAnalyzer()

    def test_tier1_regex_detects_explicit_frustration(self):
        """Tier 1 (regex) должен детектить явную фрустрацию"""
        result = self.analyzer.analyze("Хватит! Надоело! 😡")

        assert result.tone == Tone.FRUSTRATED
        assert result.tier_used == "regex", \
            f"Ожидался tier='regex', получен '{result.tier_used}'"
        assert result.confidence >= 0.5

    def test_analysis_time_not_zero(self):
        """Время анализа должно быть > 0 (анализ выполняется)"""
        result = self.analyzer.analyze("Тестовое сообщение")

        assert result.latency_ms > 0, \
            f"latency_ms={result.latency_ms}, должно быть > 0"

    def test_signals_detected_for_frustrated(self):
        """При фрустрации должны быть сигналы"""
        result = self.analyzer.analyze("Сколько можно уже!!!")

        if result.tone == Tone.FRUSTRATED:
            assert len(result.signals) > 0, \
                "При FRUSTRATED должны быть сигналы"

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
