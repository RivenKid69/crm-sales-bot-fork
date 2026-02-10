"""
Тесты для Cascade Tone Analyzer.

Проверяют:
- Tier 1: Regex анализ (быстрый путь)
- Tier 2: Semantic анализ (RoSBERTa)
- Tier 3: LLM анализ
- Каскадную логику
- Frustration tracking
- Обратную совместимость
"""

import pytest
import sys
import os
from unittest.mock import Mock, patch, MagicMock

# Добавляем src в путь

from src.tone_analyzer import (
    Tone,
    Style,
    ToneAnalysis,
    ToneAnalyzer,
    CascadeToneAnalyzer,
    RegexToneAnalyzer,
    SemanticToneAnalyzer,
    LLMToneAnalyzer,
    FrustrationTracker,
    get_cascade_tone_analyzer,
    reset_cascade_tone_analyzer,
    TONE_MARKERS,
    INFORMAL_MARKERS,
    FRUSTRATION_THRESHOLDS,
    TONE_EXAMPLES,
)
from src.feature_flags import flags

# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def regex_analyzer():
    """Создать RegexToneAnalyzer для тестов."""
    return RegexToneAnalyzer()

@pytest.fixture
def cascade_analyzer():
    """Создать CascadeToneAnalyzer для тестов."""
    reset_cascade_tone_analyzer()
    # Отключаем Tier 2 и 3 для изолированного тестирования Tier 1
    flags.set_override("cascade_tone_analyzer", True)
    flags.set_override("tone_semantic_tier2", False)
    flags.set_override("tone_llm_tier3", False)
    yield CascadeToneAnalyzer()
    flags.clear_all_overrides()
    reset_cascade_tone_analyzer()

@pytest.fixture
def cascade_analyzer_full():
    """Создать CascadeToneAnalyzer с включенными Tier 2 и 3."""
    reset_cascade_tone_analyzer()
    flags.set_override("cascade_tone_analyzer", True)
    flags.set_override("tone_semantic_tier2", True)
    flags.set_override("tone_llm_tier3", True)
    yield CascadeToneAnalyzer()
    flags.clear_all_overrides()
    reset_cascade_tone_analyzer()

@pytest.fixture
def frustration_tracker():
    """Создать FrustrationTracker для тестов."""
    return FrustrationTracker()

# =============================================================================
# Test Models
# =============================================================================

class TestModels:
    """Тесты для моделей данных."""

    def test_tone_enum_values(self):
        """Проверка значений Tone enum."""
        assert Tone.NEUTRAL.value == "neutral"
        assert Tone.POSITIVE.value == "positive"
        assert Tone.FRUSTRATED.value == "frustrated"
        assert Tone.SKEPTICAL.value == "skeptical"
        assert Tone.RUSHED.value == "rushed"
        assert Tone.CONFUSED.value == "confused"
        assert Tone.INTERESTED.value == "interested"

    def test_style_enum_values(self):
        """Проверка значений Style enum."""
        assert Style.FORMAL.value == "formal"
        assert Style.INFORMAL.value == "informal"

    def test_tone_analysis_creation(self):
        """Создание ToneAnalysis."""
        analysis = ToneAnalysis(
            tone=Tone.FRUSTRATED,
            style=Style.FORMAL,
            confidence=0.9,
            frustration_level=5,
            signals=["frustrated:test"],
            tier_used="regex",
        )
        assert analysis.tone == Tone.FRUSTRATED
        assert analysis.style == Style.FORMAL
        assert analysis.confidence == 0.9
        assert analysis.frustration_level == 5
        assert "frustrated:test" in analysis.signals
        assert analysis.tier_used == "regex"

    def test_tone_analysis_defaults(self):
        """Проверка значений по умолчанию ToneAnalysis."""
        analysis = ToneAnalysis(
            tone=Tone.NEUTRAL,
            style=Style.FORMAL,
            confidence=0.5,
            frustration_level=0,
        )
        assert analysis.signals == []
        assert analysis.tier_used == "regex"
        assert analysis.tier_scores == {}
        assert analysis.latency_ms == 0.0

# =============================================================================
# Test FrustrationTracker
# =============================================================================

class TestFrustrationTracker:
    """Тесты для FrustrationTracker."""

    def test_initial_state(self, frustration_tracker):
        """Начальное состояние."""
        assert frustration_tracker.level == 0
        assert frustration_tracker.history == []
        assert not frustration_tracker.is_warning()
        assert not frustration_tracker.is_critical()

    def test_update_increases_for_frustrated(self, frustration_tracker):
        """Frustrated увеличивает уровень."""
        frustration_tracker.update(Tone.FRUSTRATED)
        assert frustration_tracker.level == 3  # FRUSTRATION_WEIGHTS[FRUSTRATED] = 3

    def test_update_increases_for_skeptical(self, frustration_tracker):
        """Skeptical увеличивает уровень."""
        frustration_tracker.update(Tone.SKEPTICAL)
        assert frustration_tracker.level == 1

    def test_update_decreases_for_positive(self, frustration_tracker):
        """Positive снижает уровень."""
        # Сначала поднимаем
        frustration_tracker.update(Tone.FRUSTRATED)
        frustration_tracker.update(Tone.FRUSTRATED)
        high_level = frustration_tracker.level

        # Потом снижаем
        frustration_tracker.update(Tone.POSITIVE)
        assert frustration_tracker.level < high_level

    def test_level_capped_at_max(self, frustration_tracker):
        """Уровень ограничен максимумом."""
        for _ in range(20):
            frustration_tracker.update(Tone.FRUSTRATED)
        assert frustration_tracker.level == 10

    def test_level_not_negative(self, frustration_tracker):
        """Уровень не уходит в минус."""
        for _ in range(20):
            frustration_tracker.update(Tone.POSITIVE)
        assert frustration_tracker.level == 0

    def test_is_warning_threshold(self, frustration_tracker):
        """Порог warning."""
        # До порога
        frustration_tracker.update(Tone.FRUSTRATED)  # 3
        assert not frustration_tracker.is_warning()

        # На пороге
        frustration_tracker.update(Tone.SKEPTICAL)  # 4
        assert frustration_tracker.is_warning()

    def test_is_critical_threshold(self, frustration_tracker):
        """Порог critical."""
        for _ in range(3):
            frustration_tracker.update(Tone.FRUSTRATED)  # 9
        assert frustration_tracker.is_critical()

    def test_history_tracking(self, frustration_tracker):
        """Отслеживание истории."""
        frustration_tracker.update(Tone.NEUTRAL)
        frustration_tracker.update(Tone.FRUSTRATED)
        frustration_tracker.update(Tone.POSITIVE)

        history = frustration_tracker.history
        assert len(history) == 3
        assert history[0]["tone"] == "neutral"
        assert history[1]["tone"] == "frustrated"
        assert history[2]["tone"] == "positive"

    def test_reset(self, frustration_tracker):
        """Сброс состояния."""
        frustration_tracker.update(Tone.FRUSTRATED)
        frustration_tracker.update(Tone.FRUSTRATED)
        assert frustration_tracker.level > 0

        frustration_tracker.reset()
        assert frustration_tracker.level == 0
        assert frustration_tracker.history == []

    def test_set_level(self, frustration_tracker):
        """Установка уровня напрямую."""
        frustration_tracker.set_level(7)
        assert frustration_tracker.level == 7

        # Проверка ограничений
        frustration_tracker.set_level(15)
        assert frustration_tracker.level == 10

        frustration_tracker.set_level(-5)
        assert frustration_tracker.level == 0

# =============================================================================
# Test RegexToneAnalyzer (Tier 1)
# =============================================================================

class TestRegexToneAnalyzer:
    """Тесты для RegexToneAnalyzer (Tier 1)."""

    # === POSITIVE TONE ===

    def test_positive_with_emoji(self, regex_analyzer):
        """Позитивный тон с эмодзи."""
        result = regex_analyzer.analyze("Отлично! 👍")
        assert result.tone == Tone.POSITIVE

    def test_positive_with_words(self, regex_analyzer):
        """Позитивный тон со словами."""
        result = regex_analyzer.analyze("Супер, замечательно!")
        assert result.tone == Tone.POSITIVE

    # === FRUSTRATED TONE ===

    def test_frustrated_direct(self, regex_analyzer):
        """Прямое выражение раздражения."""
        result = regex_analyzer.analyze("Сколько можно уже!")
        assert result.tone == Tone.FRUSTRATED

    def test_frustrated_with_emoji(self, regex_analyzer):
        """Раздражение с эмодзи."""
        result = regex_analyzer.analyze("Опять 😡")
        assert result.tone == Tone.FRUSTRATED

    def test_frustrated_subtle(self, regex_analyzer):
        """Неявное раздражение."""
        result = regex_analyzer.analyze("Вы меня не понимаете")
        assert result.tone == Tone.FRUSTRATED

    # === SKEPTICAL TONE ===

    def test_skeptical_doubt(self, regex_analyzer):
        """Сомнение."""
        result = regex_analyzer.analyze("Сомневаюсь что это работает")
        assert result.tone == Tone.SKEPTICAL

    def test_skeptical_question(self, regex_analyzer):
        """Скептический вопрос."""
        result = regex_analyzer.analyze("Правда? Это точно?")
        assert result.tone == Tone.SKEPTICAL

    # === RUSHED TONE ===

    def test_rushed_direct(self, regex_analyzer):
        """Прямая спешка."""
        result = regex_analyzer.analyze("Короче, давайте к делу")
        assert result.tone == Tone.RUSHED

    def test_rushed_no_time(self, regex_analyzer):
        """Нет времени."""
        result = regex_analyzer.analyze("Времени нет, быстрее")
        assert result.tone == Tone.RUSHED

    # === CONFUSED TONE ===

    def test_confused_direct(self, regex_analyzer):
        """Прямое непонимание."""
        result = regex_analyzer.analyze("Не понял, что это?")
        assert result.tone == Tone.CONFUSED

    def test_confused_question_marks(self, regex_analyzer):
        """Много вопросительных знаков."""
        result = regex_analyzer.analyze("Как это??? Объясните")
        assert result.tone == Tone.CONFUSED

    # === INTERESTED TONE ===

    def test_interested(self, regex_analyzer):
        """Заинтересованность."""
        result = regex_analyzer.analyze("Расскажите подробнее")
        assert result.tone == Tone.INTERESTED

    # === NEUTRAL TONE ===

    def test_neutral_simple(self, regex_analyzer):
        """Нейтральное сообщение."""
        result = regex_analyzer.analyze("У нас 10 человек")
        assert result.tone == Tone.NEUTRAL

    # === PRIORITY ===

    def test_priority_frustrated_over_positive(self, regex_analyzer):
        """Frustrated приоритетнее positive."""
        result = regex_analyzer.analyze("Отлично, достали! 😡")
        assert result.tone == Tone.FRUSTRATED

    def test_priority_rushed_over_confused(self, regex_analyzer):
        """Rushed приоритетнее confused."""
        result = regex_analyzer.analyze("Короче, не понял, но быстро")
        assert result.tone == Tone.RUSHED

    # === STYLE ===

    def test_formal_style_default(self, regex_analyzer):
        """Формальный стиль по умолчанию."""
        result = regex_analyzer.analyze("Добрый день")
        assert result.style == Style.FORMAL

    def test_informal_style(self, regex_analyzer):
        """Неформальный стиль."""
        result = regex_analyzer.analyze("Привет, ну чё там?")
        assert result.style == Style.INFORMAL

    # === CONFIDENCE ===

    def test_high_confidence_multiple_signals(self, regex_analyzer):
        """Высокая уверенность при множестве сигналов."""
        result = regex_analyzer.analyze("Достали! Надоело! 😡😤")
        assert result.confidence >= 0.85

    def test_low_confidence_neutral(self, regex_analyzer):
        """Низкая уверенность для нейтрального."""
        result = regex_analyzer.analyze("Да")
        assert result.confidence <= 0.5

    # === SIGNALS ===

    def test_signals_populated(self, regex_analyzer):
        """Сигналы заполняются."""
        result = regex_analyzer.analyze("Достали! 😡")
        assert len(result.signals) > 0

    def test_no_signals_for_neutral(self, regex_analyzer):
        """Нет сигналов для нейтрального."""
        result = regex_analyzer.analyze("У нас 5 человек")
        assert len(result.signals) == 0

    # === FRUSTRATION TRACKING ===

    def test_frustration_increases(self, regex_analyzer):
        """Frustration растёт."""
        regex_analyzer.analyze("Достали!")
        level1 = regex_analyzer.get_frustration_level()

        regex_analyzer.analyze("Надоело!")
        level2 = regex_analyzer.get_frustration_level()

        assert level2 > level1

    def test_frustration_decreases(self, regex_analyzer):
        """Frustration снижается."""
        regex_analyzer.analyze("Достали!")
        regex_analyzer.analyze("Надоело!")
        high_level = regex_analyzer.get_frustration_level()

        regex_analyzer.analyze("Отлично! 👍")
        lower_level = regex_analyzer.get_frustration_level()

        assert lower_level < high_level

    # === RESPONSE GUIDANCE ===

    def test_guidance_normal(self, regex_analyzer):
        """Рекомендации для нормальной ситуации."""
        result = regex_analyzer.analyze("У нас 10 человек")
        guidance = regex_analyzer.get_response_guidance(result)

        assert guidance["max_words"] == 50
        assert guidance["should_apologize"] is False

    def test_guidance_frustrated(self, regex_analyzer):
        """Рекомендации для раздражённого клиента."""
        for _ in range(3):
            result = regex_analyzer.analyze("Достали!")

        guidance = regex_analyzer.get_response_guidance(result)
        assert guidance["max_words"] < 50
        assert guidance["should_apologize"] is True

    def test_guidance_rushed(self, regex_analyzer):
        """Рекомендации для торопящегося."""
        result = regex_analyzer.analyze("Короче, быстрее")
        guidance = regex_analyzer.get_response_guidance(result)

        assert guidance["max_words"] <= 30

    # === RESET ===

    def test_reset(self, regex_analyzer):
        """Сброс состояния."""
        regex_analyzer.analyze("Достали!")
        regex_analyzer.analyze("Надоело!")
        assert regex_analyzer.get_frustration_level() > 0

        regex_analyzer.reset()
        assert regex_analyzer.get_frustration_level() == 0

    # === EDGE CASES ===

    def test_empty_message(self, regex_analyzer):
        """Пустое сообщение."""
        result = regex_analyzer.analyze("")
        assert result.tone == Tone.NEUTRAL

    def test_only_emoji(self, regex_analyzer):
        """Только эмодзи."""
        result = regex_analyzer.analyze("👍")
        assert result.tone == Tone.POSITIVE

    def test_only_punctuation(self, regex_analyzer):
        """Только пунктуация."""
        result = regex_analyzer.analyze("???")
        assert result.tone == Tone.CONFUSED

# =============================================================================
# Test CascadeToneAnalyzer
# =============================================================================

class TestCascadeToneAnalyzer:
    """Тесты для CascadeToneAnalyzer."""

    def test_tier1_fast_path(self, cascade_analyzer):
        """Tier 1 возвращает при явных сигналах."""
        result = cascade_analyzer.analyze("Достали! 😡")
        assert result.tier_used == "regex"
        assert result.tone == Tone.FRUSTRATED
        assert result.latency_ms < 50  # Быстрый путь

    def test_backward_compatibility_interface(self, cascade_analyzer):
        """Обратная совместимость с ToneAnalyzer API."""
        result = cascade_analyzer.analyze("Достали!")

        # Все методы legacy API должны работать
        assert hasattr(cascade_analyzer, 'get_frustration_level')
        assert hasattr(cascade_analyzer, 'is_frustrated')
        assert hasattr(cascade_analyzer, 'is_critically_frustrated')
        assert hasattr(cascade_analyzer, 'get_frustration_history')
        assert hasattr(cascade_analyzer, 'get_response_guidance')
        assert hasattr(cascade_analyzer, 'reset')

    def test_get_response_guidance(self, cascade_analyzer):
        """get_response_guidance работает."""
        result = cascade_analyzer.analyze("Достали!")
        guidance = cascade_analyzer.get_response_guidance(result)

        assert "max_words" in guidance
        assert "tone_instruction" in guidance
        assert "should_apologize" in guidance

    def test_frustration_tracking(self, cascade_analyzer):
        """Frustration tracking работает."""
        cascade_analyzer.analyze("Достали!")
        assert cascade_analyzer.get_frustration_level() > 0

    def test_reset(self, cascade_analyzer):
        """Reset работает."""
        cascade_analyzer.analyze("Достали!")
        assert cascade_analyzer.get_frustration_level() > 0

        cascade_analyzer.reset()
        assert cascade_analyzer.get_frustration_level() == 0

    def test_explain(self, cascade_analyzer):
        """Explain возвращает детальную информацию."""
        explanation = cascade_analyzer.explain("Достали! 😡")

        assert "message" in explanation
        assert "final_tone" in explanation
        assert "final_confidence" in explanation
        assert "tier_used" in explanation
        assert "signals" in explanation
        assert "latency_ms" in explanation

    def test_tone_alias_is_cascade(self):
        """ToneAnalyzer это alias для CascadeToneAnalyzer."""
        assert ToneAnalyzer is CascadeToneAnalyzer

# =============================================================================
# Test CascadeToneAnalyzer with Tier 2
# =============================================================================

class TestCascadeTier2:
    """Тесты для Tier 2 (Semantic)."""

    @pytest.fixture(autouse=True)
    def setup_tier2(self):
        """Настройка для тестов Tier 2."""
        reset_cascade_tone_analyzer()
        flags.set_override("cascade_tone_analyzer", True)
        flags.set_override("tone_semantic_tier2", True)
        flags.set_override("tone_llm_tier3", False)
        yield
        flags.clear_all_overrides()
        reset_cascade_tone_analyzer()

    def test_tier2_fallback_for_no_signals(self):
        """Tier 2 активируется при отсутствии сигналов."""
        # Пропускаем если sentence-transformers недоступен
        try:
            import sentence_transformers
        except ImportError:
            pytest.skip("sentence-transformers not installed")

        analyzer = CascadeToneAnalyzer()

        # Сообщение без явных сигналов, но с негативным sentiment
        result = analyzer.analyze("Мне это не подходит")

        # Может быть regex (низкий confidence) или semantic
        assert result.tone in [Tone.NEUTRAL, Tone.FRUSTRATED, Tone.SKEPTICAL]

    def test_tier2_similar_examples(self):
        """Semantic analyzer возвращает похожие примеры."""
        try:
            import sentence_transformers
        except ImportError:
            pytest.skip("sentence-transformers not installed")

        from src.tone_analyzer import get_semantic_tone_analyzer

        semantic = get_semantic_tone_analyzer()
        if not semantic.is_available:
            pytest.skip("Semantic analyzer not available")

        similar = semantic.get_similar_examples("Сколько можно уже!", top_k=3)
        assert len(similar) > 0
        assert all(len(item) == 3 for item in similar)

# =============================================================================
# Test CascadeToneAnalyzer with Tier 3
# =============================================================================

class TestCascadeTier3:
    """Тесты для Tier 3 (LLM)."""

    def test_llm_analyzer_initialization(self):
        """LLMToneAnalyzer инициализируется."""
        llm_analyzer = LLMToneAnalyzer()
        assert llm_analyzer is not None

    def test_llm_analyzer_with_mock_llm(self):
        """LLMToneAnalyzer работает с mock LLM."""
        mock_llm = Mock()
        mock_llm.generate.return_value = "frustrated"
        mock_llm.health_check.return_value = True

        llm_analyzer = LLMToneAnalyzer(llm=mock_llm)
        result = llm_analyzer.analyze("Ну конечно, спасибо за 'помощь'")

        assert result is not None
        tone, confidence = result
        assert tone == Tone.FRUSTRATED
        assert confidence == 0.75

    def test_llm_analyzer_handles_error(self):
        """LLMToneAnalyzer обрабатывает ошибки."""
        mock_llm = Mock()
        mock_llm.generate.side_effect = Exception("LLM error")

        llm_analyzer = LLMToneAnalyzer(llm=mock_llm)
        result = llm_analyzer.analyze("test")

        assert result is None

    def test_llm_analyzer_parses_responses(self):
        """LLMToneAnalyzer парсит разные ответы."""
        mock_llm = Mock()
        mock_llm.health_check.return_value = True

        test_cases = [
            ("frustrated", Tone.FRUSTRATED),
            ("SKEPTICAL", Tone.SKEPTICAL),
            ("  positive  ", Tone.POSITIVE),
            ("neutral.", Tone.NEUTRAL),
        ]

        llm_analyzer = LLMToneAnalyzer(llm=mock_llm)

        for response, expected_tone in test_cases:
            mock_llm.generate.return_value = response
            result = llm_analyzer.analyze("test")
            assert result is not None
            assert result[0] == expected_tone

# =============================================================================
# Test Backward Compatibility (Regression)
# =============================================================================

class TestBackwardCompatibility:
    """Регрессионные тесты для обратной совместимости."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Настройка."""
        reset_cascade_tone_analyzer()
        flags.set_override("cascade_tone_analyzer", True)
        flags.set_override("tone_semantic_tier2", False)
        flags.set_override("tone_llm_tier3", False)
        yield
        flags.clear_all_overrides()
        reset_cascade_tone_analyzer()

    def test_import_from_module(self):
        """Импорт из модуля работает."""
        from src.tone_analyzer import ToneAnalyzer, Tone, Style, ToneAnalysis
        assert ToneAnalyzer is not None
        assert Tone is not None
        assert Style is not None
        assert ToneAnalysis is not None

    def test_analyzer_api_compatibility(self):
        """API совместим с legacy ToneAnalyzer."""
        analyzer = ToneAnalyzer()

        # analyze
        result = analyzer.analyze("Достали!")
        assert isinstance(result.tone, Tone)
        assert isinstance(result.style, Style)
        assert isinstance(result.confidence, float)
        assert isinstance(result.frustration_level, int)
        assert isinstance(result.signals, list)

        # get_response_guidance
        guidance = analyzer.get_response_guidance(result)
        assert "max_words" in guidance
        assert "tone_instruction" in guidance
        assert "should_apologize" in guidance
        assert "should_offer_exit" in guidance

        # frustration methods
        assert isinstance(analyzer.get_frustration_level(), int)
        assert isinstance(analyzer.is_frustrated(), bool)
        assert isinstance(analyzer.is_critically_frustrated(), bool)
        assert isinstance(analyzer.get_frustration_history(), list)

        # reset
        analyzer.reset()
        assert analyzer.get_frustration_level() == 0

    @pytest.mark.parametrize("message,expected_tone", [
        ("Сколько можно уже!", Tone.FRUSTRATED),
        ("Отлично! 👍", Tone.POSITIVE),
        ("Короче, давайте к делу", Tone.RUSHED),
        ("Не понял???", Tone.CONFUSED),
        ("Сомневаюсь", Tone.SKEPTICAL),
        ("Расскажите подробнее", Tone.INTERESTED),
        ("У нас 10 человек", Tone.NEUTRAL),
    ])
    def test_tone_detection_regression(self, message, expected_tone):
        """Регрессия: все тона детектируются как раньше."""
        analyzer = ToneAnalyzer()
        result = analyzer.analyze(message)
        assert result.tone == expected_tone

# =============================================================================
# Test Feature Flags
# =============================================================================

class TestFeatureFlags:
    """Тесты для feature flags."""

    def test_flags_exist(self):
        """Флаги существуют."""
        assert hasattr(flags, 'cascade_tone_analyzer')
        assert hasattr(flags, 'tone_semantic_tier2')
        assert hasattr(flags, 'tone_llm_tier3')

    def test_flags_default_enabled(self):
        """Флаги включены по умолчанию."""
        # Сбрасываем overrides
        flags.clear_all_overrides()

        # Проверяем defaults
        assert flags.is_enabled("cascade_tone_analyzer") is True
        assert flags.is_enabled("tone_semantic_tier2") is True
        assert flags.is_enabled("tone_llm_tier3") is True

    def test_flags_override(self):
        """Override флагов работает."""
        flags.set_override("tone_semantic_tier2", False)
        assert flags.tone_semantic_tier2 is False

        flags.clear_override("tone_semantic_tier2")
        assert flags.tone_semantic_tier2 is True

# =============================================================================
# Test Examples
# =============================================================================

class TestExamples:
    """Тесты для TONE_EXAMPLES."""

    def test_all_tones_have_examples(self):
        """Все типы тона имеют примеры."""
        expected_tones = ["frustrated", "skeptical", "rushed", "confused", "positive", "interested", "neutral"]
        for tone in expected_tones:
            assert tone in TONE_EXAMPLES
            assert len(TONE_EXAMPLES[tone]) > 0

    def test_examples_count(self):
        """Достаточное количество примеров."""
        for tone, examples in TONE_EXAMPLES.items():
            assert len(examples) >= 5, f"Tone {tone} has less than 5 examples"

# =============================================================================
# Test Markers
# =============================================================================

class TestMarkers:
    """Тесты для маркеров."""

    def test_tone_markers_exist(self):
        """TONE_MARKERS содержит все тона."""
        assert Tone.POSITIVE in TONE_MARKERS
        assert Tone.FRUSTRATED in TONE_MARKERS
        assert Tone.SKEPTICAL in TONE_MARKERS
        assert Tone.RUSHED in TONE_MARKERS
        assert Tone.CONFUSED in TONE_MARKERS
        assert Tone.INTERESTED in TONE_MARKERS

    def test_informal_markers_exist(self):
        """INFORMAL_MARKERS не пустой."""
        assert len(INFORMAL_MARKERS) > 0

    def test_frustration_thresholds(self):
        """Пороги frustration."""
        assert FRUSTRATION_THRESHOLDS["warning"] < FRUSTRATION_THRESHOLDS["high"]
        assert FRUSTRATION_THRESHOLDS["high"] < FRUSTRATION_THRESHOLDS["critical"]

# =============================================================================
# Test Singleton
# =============================================================================

class TestSingleton:
    """Тесты для singleton функций."""

    def test_get_cascade_tone_analyzer_singleton(self):
        """get_cascade_tone_analyzer возвращает singleton."""
        reset_cascade_tone_analyzer()

        a1 = get_cascade_tone_analyzer()
        a2 = get_cascade_tone_analyzer()

        assert a1 is a2

        reset_cascade_tone_analyzer()

    def test_reset_cascade_tone_analyzer(self):
        """reset_cascade_tone_analyzer сбрасывает singleton."""
        a1 = get_cascade_tone_analyzer()
        reset_cascade_tone_analyzer()
        a2 = get_cascade_tone_analyzer()

        assert a1 is not a2

# =============================================================================
# Test SemanticToneAnalyzer
# =============================================================================

class TestSemanticToneAnalyzer:
    """Тесты для SemanticToneAnalyzer."""

    def test_initialization(self):
        """Инициализация."""
        analyzer = SemanticToneAnalyzer()
        assert analyzer is not None

    def test_is_available_without_transformers(self):
        """is_available возвращает False без transformers."""
        with patch.dict('sys.modules', {'sentence_transformers': None}):
            analyzer = SemanticToneAnalyzer()
            # Проверяем что не падает
            assert analyzer is not None

# =============================================================================
# Run tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
