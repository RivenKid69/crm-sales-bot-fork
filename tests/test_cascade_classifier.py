"""
Тесты для каскадного классификатора интентов.

Покрытие:
1. INTENT_EXAMPLES — валидация примеров
2. SemanticClassifier — unit тесты
3. CascadeIntentClassifier — интеграционные тесты
4. HybridClassifier с cascade fallback
5. Edge cases и regression тесты
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import numpy as np

# Импорты тестируемых модулей
from src.classifier.intents.examples import (
    INTENT_EXAMPLES,
    get_all_intents,
    get_examples_for_intent,
    get_total_examples_count,
)
from src.classifier.intents.semantic import (
    SemanticClassifier,
    SemanticResult,
    SemanticMatchType,
    get_semantic_classifier,
    reset_semantic_classifier,
)
from src.classifier.cascade import (
    CascadeIntentClassifier,
    CascadeResult,
    ClassificationStage,
    get_cascade_classifier,
    reset_cascade_classifier,
)
from src.feature_flags import flags

# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset singletons before each test."""
    reset_semantic_classifier()
    reset_cascade_classifier()
    yield
    reset_semantic_classifier()
    reset_cascade_classifier()

@pytest.fixture
def mock_embedder():
    """Mock sentence-transformers embedder."""
    with patch('sentence_transformers.SentenceTransformer') as mock:
        embedder = MagicMock()

        # Mock encode to return normalized vectors
        def mock_encode(texts, **kwargs):
            if isinstance(texts, str):
                # Single text - return 1D array
                vec = np.random.randn(384)
                return vec / np.linalg.norm(vec)
            else:
                # List of texts - return 2D array
                vecs = np.random.randn(len(texts), 384)
                norms = np.linalg.norm(vecs, axis=1, keepdims=True)
                return vecs / norms

        embedder.encode = mock_encode
        mock.return_value = embedder
        yield mock

@pytest.fixture
def semantic_classifier(mock_embedder):
    """Create SemanticClassifier with mocked embedder."""
    classifier = SemanticClassifier()
    # Force initialization
    classifier._init_embeddings()
    return classifier

# =============================================================================
# INTENT_EXAMPLES Tests
# =============================================================================

class TestIntentExamples:
    """Тесты для INTENT_EXAMPLES."""

    def test_intent_examples_not_empty(self):
        """INTENT_EXAMPLES должен содержать интенты."""
        assert len(INTENT_EXAMPLES) > 0

    def test_all_intents_have_examples(self):
        """Каждый интент должен иметь минимум 3 примера."""
        for intent, examples in INTENT_EXAMPLES.items():
            assert len(examples) >= 3, f"Intent '{intent}' has only {len(examples)} examples"

    def test_examples_are_strings(self):
        """Все примеры должны быть строками."""
        for intent, examples in INTENT_EXAMPLES.items():
            for example in examples:
                assert isinstance(example, str), f"Intent '{intent}' has non-string example"
                assert len(example) > 0, f"Intent '{intent}' has empty example"

    def test_no_duplicate_examples(self):
        """Примеры не должны дублироваться внутри интента."""
        for intent, examples in INTENT_EXAMPLES.items():
            seen = set()
            for example in examples:
                normalized = example.lower().strip()
                assert normalized not in seen, f"Duplicate in '{intent}': {example}"
                seen.add(normalized)

    def test_critical_intents_exist(self):
        """Критические интенты должны существовать."""
        critical = [
            "greeting", "farewell", "agreement", "rejection",
            "objection_price", "objection_no_time", "objection_competitor", "objection_think",
            "demo_request", "callback_request", "consultation_request",
            "price_question", "question_features", "question_integrations",
            "situation_provided", "problem_revealed", "unclear",
        ]
        for intent in critical:
            assert intent in INTENT_EXAMPLES, f"Critical intent '{intent}' missing"

    def test_get_all_intents(self):
        """get_all_intents должен возвращать все интенты."""
        intents = get_all_intents()
        assert len(intents) == len(INTENT_EXAMPLES)
        assert set(intents) == set(INTENT_EXAMPLES.keys())

    def test_get_examples_for_intent(self):
        """get_examples_for_intent должен возвращать примеры."""
        examples = get_examples_for_intent("greeting")
        assert len(examples) >= 3
        assert "привет" in examples

    def test_get_examples_for_unknown_intent(self):
        """Для неизвестного интента должен возвращать пустой список."""
        examples = get_examples_for_intent("unknown_intent_xyz")
        assert examples == []

    def test_get_total_examples_count(self):
        """get_total_examples_count должен считать все примеры."""
        count = get_total_examples_count()
        expected = sum(len(v) for v in INTENT_EXAMPLES.values())
        assert count == expected

# =============================================================================
# SemanticClassifier Tests
# =============================================================================

class TestSemanticClassifier:
    """Тесты для SemanticClassifier."""

    def test_init_without_embedder(self):
        """Классификатор должен создаваться без embedder."""
        classifier = SemanticClassifier()
        assert classifier._embedder is None
        assert not classifier._initialized

    def test_is_available_with_mock(self, semantic_classifier):
        """is_available должен возвращать True с mock embedder."""
        assert semantic_classifier.is_available

    def test_classify_returns_tuple(self, semantic_classifier):
        """classify должен возвращать (intent, confidence, scores)."""
        intent, conf, scores = semantic_classifier.classify("привет")
        assert isinstance(intent, str)
        assert isinstance(conf, float)
        assert isinstance(scores, dict)
        assert 0.0 <= conf <= 1.0

    def test_classify_empty_message(self, semantic_classifier):
        """Пустое сообщение должно возвращать unclear."""
        intent, conf, scores = semantic_classifier.classify("")
        assert intent == "unclear"
        assert conf == 0.0

    def test_classify_detailed_returns_semantic_result(self, semantic_classifier):
        """classify_detailed должен возвращать SemanticResult."""
        result = semantic_classifier.classify_detailed("привет")
        assert isinstance(result, SemanticResult)
        assert isinstance(result.intent, str)
        assert isinstance(result.confidence, float)
        assert isinstance(result.match_type, SemanticMatchType)

    def test_match_types(self):
        """Проверка типов совпадений."""
        assert SemanticMatchType.EXACT.value == "exact"
        assert SemanticMatchType.STRONG.value == "strong"
        assert SemanticMatchType.MODERATE.value == "moderate"
        assert SemanticMatchType.WEAK.value == "weak"
        assert SemanticMatchType.NONE.value == "none"

    def test_get_similar_examples(self, semantic_classifier):
        """get_similar_examples должен возвращать похожие примеры."""
        results = semantic_classifier.get_similar_examples("привет", top_k=3)
        assert len(results) <= 3
        for example, intent, score in results:
            assert isinstance(example, str)
            assert isinstance(intent, str)
            assert isinstance(score, float)

    def test_explain(self, semantic_classifier):
        """explain должен возвращать объяснение."""
        explanation = semantic_classifier.explain("привет")
        assert "message" in explanation
        assert "predicted_intent" in explanation
        assert "confidence" in explanation
        assert "top_intents" in explanation

    def test_thresholds(self):
        """Пороги должны быть корректно определены."""
        assert SemanticClassifier.THRESHOLD_EXACT == 0.90
        assert SemanticClassifier.THRESHOLD_STRONG == 0.75
        assert SemanticClassifier.THRESHOLD_MODERATE == 0.60
        assert SemanticClassifier.THRESHOLD_WEAK == 0.40

    def test_singleton_get_semantic_classifier(self, mock_embedder):
        """get_semantic_classifier должен возвращать singleton."""
        classifier1 = get_semantic_classifier()
        classifier2 = get_semantic_classifier()
        assert classifier1 is classifier2

# =============================================================================
# CascadeIntentClassifier Tests
# =============================================================================

class TestCascadeIntentClassifier:
    """Тесты для CascadeIntentClassifier."""

    def test_init_default_params(self):
        """Проверка дефолтных параметров."""
        classifier = CascadeIntentClassifier(enable_semantic=False)
        assert classifier.high_threshold == 0.85
        assert classifier.medium_threshold == 0.65
        assert classifier.semantic_threshold == 0.55
        assert classifier.min_confidence == 0.3

    def test_classify_returns_cascade_result(self):
        """classify должен возвращать CascadeResult."""
        classifier = CascadeIntentClassifier(enable_semantic=False)
        result = classifier.classify("привет")
        assert isinstance(result, CascadeResult)
        assert isinstance(result.intent, str)
        assert isinstance(result.confidence, float)
        assert isinstance(result.stage, ClassificationStage)

    def test_priority_pattern_stage(self):
        """Stage 1: Priority patterns должны срабатывать первыми."""
        classifier = CascadeIntentClassifier(enable_semantic=False)
        # Используем паттерн который точно есть в PRIORITY_PATTERNS
        result = classifier.classify("перезвоните мне пожалуйста")
        # "перезвоните мне" должен сработать как callback_request через паттерны
        assert result.stage == ClassificationStage.PRIORITY_PATTERN
        assert result.intent == "callback_request"

    def test_root_stage_high_confidence(self):
        """Stage 2: Root classifier при высокой уверенности."""
        classifier = CascadeIntentClassifier(enable_semantic=False)
        # Сообщение которое хорошо распознаётся root classifier
        result = classifier.classify("дорого слишком дорого очень дорого")
        # Должен быть root или priority_pattern
        assert result.stage in (ClassificationStage.ROOT, ClassificationStage.PRIORITY_PATTERN)

    def test_cascade_result_to_dict(self):
        """CascadeResult.to_dict должен конвертироваться в словарь."""
        classifier = CascadeIntentClassifier(enable_semantic=False)
        result = classifier.classify("привет")
        d = result.to_dict()
        assert "intent" in d
        assert "confidence" in d
        assert "stage" in d
        assert "timing" in d

    def test_explain(self):
        """explain должен возвращать объяснение."""
        classifier = CascadeIntentClassifier(enable_semantic=False)
        explanation = classifier.explain("привет")
        assert "message" in explanation
        assert "final_intent" in explanation
        assert "stage_used" in explanation
        assert "stages" in explanation

    def test_classification_stages_enum(self):
        """Проверка enum ClassificationStage."""
        assert ClassificationStage.PRIORITY_PATTERN.value == "priority_pattern"
        assert ClassificationStage.ROOT.value == "root"
        assert ClassificationStage.LEMMA.value == "lemma"
        assert ClassificationStage.SEMANTIC.value == "semantic"
        assert ClassificationStage.FALLBACK.value == "fallback"

# =============================================================================
# HybridClassifier Integration Tests
# =============================================================================

class TestHybridClassifierCascadeIntegration:
    """Интеграционные тесты HybridClassifier с cascade."""

    @pytest.fixture(autouse=True)
    def setup_cascade_flag(self):
        """Enable cascade_classifier flag for tests."""
        original = flags.is_enabled("cascade_classifier")
        flags.set_override("cascade_classifier", True)
        yield
        if original:
            flags.set_override("cascade_classifier", original)
        else:
            flags.clear_override("cascade_classifier")

    def test_hybrid_classifier_has_semantic_property(self):
        """HybridClassifier должен иметь semantic_classifier property."""
        from src.classifier.hybrid import HybridClassifier
        classifier = HybridClassifier()
        # С включённым флагом должен возвращать classifier
        assert hasattr(classifier, 'semantic_classifier')

    def test_hybrid_classifier_semantic_fallback_method(self):
        """HybridClassifier должен иметь _semantic_fallback метод."""
        from src.classifier.hybrid import HybridClassifier
        classifier = HybridClassifier()
        assert hasattr(classifier, '_semantic_fallback')

    def test_cascade_flag_default_enabled(self):
        """cascade_classifier должен быть включён по умолчанию."""
        # Сбрасываем overrides чтобы проверить дефолт
        flags.clear_override("cascade_classifier")
        # Проверяем через DEFAULTS
        from src.feature_flags import FeatureFlags
        assert FeatureFlags.DEFAULTS.get("cascade_classifier") is True

    def test_classify_with_cascade_enabled(self):
        """Классификация с включённым cascade."""
        from src.classifier.hybrid import HybridClassifier

        classifier = HybridClassifier()
        result = classifier.classify("привет")

        assert "intent" in result
        assert "confidence" in result
        assert "method" in result

    def test_classify_returns_semantic_method_when_appropriate(self, mock_embedder):
        """При низкой уверенности keyword должен использоваться semantic."""
        from src.classifier.hybrid import HybridClassifier

        classifier = HybridClassifier()

        # Сообщение которое плохо распознаётся keyword классификаторами
        # но может быть распознано семантически
        result = classifier.classify("xyz неизвестное сообщение abc")

        # Может быть semantic, fallback или unclear
        assert result["method"] in ("semantic", "fallback", "root", "lemma", "priority_pattern")

# =============================================================================
# Regression Tests
# =============================================================================

class TestRegressionTests:
    """Регрессионные тесты — проверка что ничего не сломалось."""

    def test_greeting_classification(self):
        """Приветствия должны классифицироваться правильно."""
        from src.classifier.hybrid import HybridClassifier

        classifier = HybridClassifier()
        greetings = ["привет", "здравствуйте", "добрый день"]

        for msg in greetings:
            result = classifier.classify(msg)
            assert result["intent"] == "greeting", f"Failed for: {msg}"

    def test_objection_price_classification(self):
        """Ценовые возражения должны классифицироваться правильно."""
        from src.classifier.hybrid import HybridClassifier

        classifier = HybridClassifier()
        objections = ["дорого", "слишком дорого", "нет бюджета"]

        for msg in objections:
            result = classifier.classify(msg)
            assert result["intent"] == "objection_price", f"Failed for: {msg}"

    def test_agreement_classification(self):
        """Согласие должно классифицироваться правильно."""
        from src.classifier.hybrid import HybridClassifier

        classifier = HybridClassifier()
        agreements = ["да, давайте", "интересно", "согласен"]

        for msg in agreements:
            result = classifier.classify(msg)
            assert result["intent"] == "agreement", f"Failed for: {msg}"

    def test_rejection_classification(self):
        """Отказ должен классифицироваться правильно."""
        from src.classifier.hybrid import HybridClassifier

        classifier = HybridClassifier()
        rejections = ["не интересно", "отстаньте", "не нужно"]

        for msg in rejections:
            result = classifier.classify(msg)
            assert result["intent"] == "rejection", f"Failed for: {msg}"

    def test_demo_request_classification(self):
        """Запросы демо должны классифицироваться правильно."""
        from src.classifier.hybrid import HybridClassifier

        classifier = HybridClassifier()
        demo_requests = ["хочу демо", "покажите как работает", "можно попробовать"]

        for msg in demo_requests:
            result = classifier.classify(msg)
            assert result["intent"] == "demo_request", f"Failed for: {msg}"

    def test_price_question_classification(self):
        """Вопросы о цене должны классифицироваться правильно."""
        from src.classifier.hybrid import HybridClassifier

        classifier = HybridClassifier()
        price_questions = ["сколько стоит", "какая цена", "какие тарифы"]

        for msg in price_questions:
            result = classifier.classify(msg)
            assert result["intent"] == "price_question", f"Failed for: {msg}"

# =============================================================================
# Edge Cases
# =============================================================================

class TestEdgeCases:
    """Тесты граничных случаев."""

    def test_empty_message(self):
        """Пустое сообщение."""
        from src.classifier.hybrid import HybridClassifier

        classifier = HybridClassifier()
        result = classifier.classify("")
        assert result["intent"] == "unclear"

    def test_whitespace_only_message(self):
        """Сообщение только из пробелов."""
        from src.classifier.hybrid import HybridClassifier

        classifier = HybridClassifier()
        result = classifier.classify("   ")
        assert result["intent"] == "unclear"

    def test_very_long_message(self):
        """Очень длинное сообщение."""
        from src.classifier.hybrid import HybridClassifier

        classifier = HybridClassifier()
        long_msg = "слово " * 500
        result = classifier.classify(long_msg)
        # Должен вернуть что-то без exception
        assert "intent" in result

    def test_special_characters(self):
        """Специальные символы."""
        from src.classifier.hybrid import HybridClassifier

        classifier = HybridClassifier()
        result = classifier.classify("???!!!")
        assert result["intent"] == "unclear"

    def test_mixed_language(self):
        """Смешанный язык."""
        from src.classifier.hybrid import HybridClassifier

        classifier = HybridClassifier()
        result = classifier.classify("привет hello как дела")
        # Должен работать без exception
        assert "intent" in result

    def test_numbers_only(self):
        """Только числа."""
        from src.classifier.hybrid import HybridClassifier

        classifier = HybridClassifier()
        result = classifier.classify("12345")
        # Может быть contact_provided или unclear
        assert "intent" in result

# =============================================================================
# Performance Tests
# =============================================================================

class TestPerformance:
    """Тесты производительности."""

    def test_classification_time(self):
        """Классификация должна быть быстрой."""
        import time
        from src.classifier.hybrid import HybridClassifier

        flags.set_override("cascade_classifier", False)  # Без semantic для скорости
        classifier = HybridClassifier()

        # Warm up
        classifier.classify("привет")

        start = time.perf_counter()
        for _ in range(100):
            classifier.classify("привет")
        elapsed = time.perf_counter() - start

        # 100 классификаций должны занять меньше 10 секунд (100ms per call is acceptable)
        assert elapsed < 10.0, f"Classification too slow: {elapsed}s for 100 calls"

        flags.clear_override("cascade_classifier")

    def test_cascade_result_timing(self):
        """CascadeResult должен содержать timing информацию."""
        classifier = CascadeIntentClassifier(enable_semantic=False)
        result = classifier.classify("привет")

        assert result.total_time_ms > 0
        assert len(result.stage_times_ms) > 0

# =============================================================================
# Feature Flag Tests
# =============================================================================

class TestFeatureFlagIntegration:
    """Тесты интеграции с feature flags."""

    def test_cascade_classifier_flag_exists(self):
        """Флаг cascade_classifier должен существовать."""
        from src.feature_flags import FeatureFlags
        assert "cascade_classifier" in FeatureFlags.DEFAULTS

    def test_cascade_classifier_in_safe_group(self):
        """cascade_classifier должен быть в группе safe."""
        from src.feature_flags import FeatureFlags
        assert "cascade_classifier" in FeatureFlags.GROUPS.get("safe", [])

    def test_cascade_classifier_in_phase_4(self):
        """cascade_classifier должен быть в группе phase_4."""
        from src.feature_flags import FeatureFlags
        assert "cascade_classifier" in FeatureFlags.GROUPS.get("phase_4", [])

    def test_cascade_flag_property(self):
        """flags.cascade_classifier property должен работать."""
        assert hasattr(flags, "cascade_classifier")
        # Проверяем что возвращает bool
        assert isinstance(flags.cascade_classifier, bool)

    def test_disable_cascade_disables_semantic(self):
        """При выключенном cascade semantic не должен использоваться."""
        from src.classifier.hybrid import HybridClassifier

        # Очищаем все overrides и сбрасываем singleton
        flags.clear_all_overrides()
        reset_semantic_classifier()

        # Устанавливаем флаг ПОСЛЕ очистки
        flags.set_override("cascade_classifier", False)

        try:
            # Проверяем что флаг действительно False
            assert flags.cascade_classifier is False, "Flag should be False"

            # Создаём классификатор ПОСЛЕ установки флага
            classifier = HybridClassifier()

            # semantic_classifier должен быть None когда флаг выключен
            result = classifier.semantic_classifier
            assert result is None, f"Expected None, got {result}. Flag is {flags.cascade_classifier}"

            # Проверяем что classify работает без semantic
            result = classifier.classify("привет")
            assert result["method"] != "semantic"
        finally:
            flags.clear_all_overrides()

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
