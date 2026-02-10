# tests/test_secondary_intent_detection.py

"""
Tests for SecondaryIntentDetectionLayer.

These tests verify the architectural solution for the "Lost Question" bug:
- Detection of secondary intents in composite messages
- Preservation of primary intent (non-destructive)
- Pattern matching for various question types
- Integration with refinement pipeline
"""

import pytest
from typing import Dict, Any

from src.classifier.secondary_intent_detection import (
    SecondaryIntentDetectionLayer,
    SecondaryIntentPattern,
    DEFAULT_SECONDARY_INTENT_PATTERNS,
)
from src.classifier.refinement_pipeline import (
    RefinementContext,
    RefinementDecision,
)

# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def layer():
    """Create a SecondaryIntentDetectionLayer instance."""
    return SecondaryIntentDetectionLayer()

@pytest.fixture
def make_context():
    """Factory for creating RefinementContext."""
    def _make(
        message: str,
        intent: str = "info_provided",
        confidence: float = 0.85,
        state: str = "bant_budget",
        phase: str = "budget",
        last_action: str = "ask_about_budget",
        **kwargs
    ) -> RefinementContext:
        return RefinementContext(
            message=message,
            intent=intent,
            confidence=confidence,
            state=state,
            phase=phase,
            last_action=last_action,
            **kwargs
        )
    return _make

@pytest.fixture
def make_result():
    """Factory for creating classification result dicts."""
    def _make(
        intent: str = "info_provided",
        confidence: float = 0.85,
        **kwargs
    ) -> Dict[str, Any]:
        return {
            "intent": intent,
            "confidence": confidence,
            "extracted_data": kwargs.get("extracted_data", {}),
            **kwargs
        }
    return _make

# =============================================================================
# BASIC FUNCTIONALITY TESTS
# =============================================================================

class TestSecondaryIntentDetectionBasics:
    """Test basic functionality of SecondaryIntentDetectionLayer."""

    def test_layer_initialization(self, layer):
        """Test layer initializes correctly with default patterns."""
        assert layer.name == "secondary_intent_detection"
        assert layer.enabled is True
        assert len(layer._patterns) > 0
        assert "price_question" in layer._patterns

    def test_layer_has_default_patterns(self, layer):
        """Test all default patterns are loaded."""
        expected_intents = [
            "price_question",
            "question_features",
            "question_integrations",
            "demo_request",
            "callback_request",
            "request_brevity",
        ]
        for intent in expected_intents:
            assert intent in layer._patterns, f"Missing pattern: {intent}"

    def test_short_message_skipped(self, layer, make_context, make_result):
        """Test very short messages are skipped."""
        ctx = make_context(message="да")  # Too short
        result = make_result()

        refined = layer.refine("да", result, ctx)

        # Should pass through without detecting secondary intents
        assert refined.decision == RefinementDecision.PASS_THROUGH

# =============================================================================
# PRICE QUESTION DETECTION TESTS
# =============================================================================

class TestPriceQuestionDetection:
    """Test detection of price_question as secondary intent."""

    @pytest.mark.parametrize("message,expected_detected", [
        # Clear price questions
        ("100 человек. Сколько стоит?", True),
        ("5 магазинов. Какая цена?", True),
        ("Бюджет 500к. Давайте по ценам", True),
        ("Расскажите про стоимость", True),
        ("А какой прайс?", True),
        ("Тарифы какие?", True),
        # Messages without price questions
        ("100 человек работает", False),
        ("Нам нужна интеграция", False),
        ("Хорошо, продолжайте", False),
    ])
    def test_price_question_detection(
        self, layer, make_context, make_result, message, expected_detected
    ):
        """Test price question detection in various messages."""
        ctx = make_context(message=message)
        result = make_result()

        refined = layer.refine(message, result, ctx)

        if expected_detected:
            assert refined.decision == RefinementDecision.REFINED
            assert "price_question" in refined.secondary_signals
        else:
            # Either pass through or no price question in secondary
            if refined.decision == RefinementDecision.REFINED:
                assert "price_question" not in refined.secondary_signals

    def test_primary_intent_preserved_with_price_question(
        self, layer, make_context, make_result
    ):
        """Test that primary intent is NOT changed when price_question detected."""
        message = "100 человек. Сколько стоит?"
        ctx = make_context(message=message, intent="info_provided")
        result = make_result(intent="info_provided", confidence=0.85)

        refined = layer.refine(message, result, ctx)

        # Primary intent must be preserved
        assert refined.intent == "info_provided"
        assert refined.confidence == 0.85

        # But secondary intent should be detected
        assert "price_question" in refined.secondary_signals

    def test_price_not_detected_when_primary(self, layer, make_context, make_result):
        """Test price_question not in secondary if it's already primary."""
        message = "Сколько стоит?"
        ctx = make_context(message=message, intent="price_question")
        result = make_result(intent="price_question")

        refined = layer.refine(message, result, ctx)

        # Should not duplicate price_question in secondary
        if refined.decision == RefinementDecision.REFINED:
            # price_question should NOT be in secondary (it's primary)
            assert "price_question" not in refined.secondary_signals

# =============================================================================
# FEATURE/INTEGRATION QUESTION DETECTION TESTS
# =============================================================================

class TestFeatureQuestionDetection:
    """Test detection of question_features and question_integrations."""

    @pytest.mark.parametrize("message,expected_intent", [
        ("100 человек. Какие функции есть?", "question_features"),
        ("Бюджет 500к. Что система умеет?", "question_features"),
        ("Нас 50. Какие возможности?", "question_features"),
        ("10 касс. А интеграция с Каспи есть?", "question_integrations"),
        ("Работаем с 1С. Можно подключить?", "question_integrations"),
    ])
    def test_feature_integration_detection(
        self, layer, make_context, make_result, message, expected_intent
    ):
        """Test detection of feature and integration questions."""
        ctx = make_context(message=message, intent="info_provided")
        result = make_result(intent="info_provided")

        refined = layer.refine(message, result, ctx)

        assert refined.decision == RefinementDecision.REFINED
        assert expected_intent in refined.secondary_signals

# =============================================================================
# DEMO/CALLBACK DETECTION TESTS
# =============================================================================

class TestDemoCallbackDetection:
    """Test detection of demo_request and callback_request."""

    @pytest.mark.parametrize("message,expected_intent", [
        ("100 человек. Можно демо посмотреть?", "demo_request"),
        ("Покажите как это работает", "demo_request"),
        ("Можно попробовать?", "demo_request"),
        ("Перезвоните завтра", "callback_request"),
        ("Свяжитесь со мной позже", "callback_request"),
    ])
    def test_demo_callback_detection(
        self, layer, make_context, make_result, message, expected_intent
    ):
        """Test detection of demo and callback requests."""
        ctx = make_context(message=message, intent="info_provided")
        result = make_result(intent="info_provided")

        refined = layer.refine(message, result, ctx)

        assert refined.decision == RefinementDecision.REFINED
        assert expected_intent in refined.secondary_signals

# =============================================================================
# MULTIPLE SECONDARY INTENTS TESTS
# =============================================================================

class TestMultipleSecondaryIntents:
    """Test detection of multiple secondary intents in one message."""

    def test_multiple_intents_detected(self, layer, make_context, make_result):
        """Test that multiple secondary intents can be detected."""
        message = "100 человек. Сколько стоит и какие функции?"
        ctx = make_context(message=message, intent="info_provided")
        result = make_result(intent="info_provided")

        refined = layer.refine(message, result, ctx)

        assert refined.decision == RefinementDecision.REFINED
        # Should detect both price and features
        assert "price_question" in refined.secondary_signals
        assert "question_features" in refined.secondary_signals

    def test_intents_ordered_by_priority(self, layer, make_context, make_result):
        """Test that secondary intents are ordered by priority."""
        message = "Покажите демо и скажите цену"
        ctx = make_context(message=message, intent="info_provided")
        result = make_result(intent="info_provided")

        refined = layer.refine(message, result, ctx)

        assert refined.decision == RefinementDecision.REFINED
        # price_question has priority 100, demo_request has 95
        # So price_question should come first
        if len(refined.secondary_signals) >= 2:
            assert refined.secondary_signals[0] == "price_question"

# =============================================================================
# URGENCY SIGNAL DETECTION TESTS
# =============================================================================

class TestUrgencyDetection:
    """Test detection of urgency signals (request_brevity)."""

    @pytest.mark.parametrize("message", [
        "100 человек. Давайте по делу",
        "Короче, сколько стоит?",
        "Быстрее, не тяни",
        "Конкретно скажите цену",
    ])
    def test_urgency_detection(self, layer, make_context, make_result, message):
        """Test detection of urgency/brevity requests."""
        ctx = make_context(message=message, intent="info_provided")
        result = make_result(intent="info_provided")

        refined = layer.refine(message, result, ctx)

        assert refined.decision == RefinementDecision.REFINED
        assert "request_brevity" in refined.secondary_signals

# =============================================================================
# CONFIDENCE TESTS
# =============================================================================

class TestSecondaryIntentConfidence:
    """Test confidence values for secondary intent detection."""

    def test_confidence_metadata_present(self, layer, make_context, make_result):
        """Test that confidence values are stored in metadata."""
        message = "100 человек. Сколько стоит?"
        ctx = make_context(message=message, intent="info_provided")
        result = make_result(intent="info_provided")

        refined = layer.refine(message, result, ctx)

        assert refined.decision == RefinementDecision.REFINED
        assert "secondary_intent_confidences" in refined.metadata
        assert "price_question" in refined.metadata["secondary_intent_confidences"]

    def test_pattern_match_higher_confidence(self, layer, make_context, make_result):
        """Test that pattern match gives higher confidence than keyword-only."""
        # Pattern match: "сколько стоит" is a full pattern
        message_pattern = "Сколько стоит система?"
        ctx1 = make_context(message=message_pattern, intent="info_provided")
        result1 = make_result(intent="info_provided")
        refined1 = layer.refine(message_pattern, result1, ctx1)

        # Keyword-only: just "цена" without pattern
        message_keyword = "Цена важна для нас"
        ctx2 = make_context(message=message_keyword, intent="info_provided")
        result2 = make_result(intent="info_provided")
        refined2 = layer.refine(message_keyword, result2, ctx2)

        # Both should detect price_question
        assert "price_question" in refined1.secondary_signals
        assert "price_question" in refined2.secondary_signals

        # Pattern match should have higher confidence
        conf1 = refined1.metadata["secondary_intent_confidences"]["price_question"]
        conf2 = refined2.metadata["secondary_intent_confidences"]["price_question"]
        assert conf1 > conf2

# =============================================================================
# EDGE CASES TESTS
# =============================================================================

class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_message(self, layer, make_context, make_result):
        """Test handling of empty message."""
        ctx = make_context(message="")
        result = make_result()

        refined = layer.refine("", result, ctx)

        # Should pass through (too short)
        assert refined.decision == RefinementDecision.PASS_THROUGH

    def test_unicode_message(self, layer, make_context, make_result):
        """Test handling of unicode/emoji in message."""
        message = "100 👨‍👩‍👧‍👦 человек. Сколько стоит? 💰"
        ctx = make_context(message=message, intent="info_provided")
        result = make_result(intent="info_provided")

        refined = layer.refine(message, result, ctx)

        assert refined.decision == RefinementDecision.REFINED
        assert "price_question" in refined.secondary_signals

    def test_case_insensitive(self, layer, make_context, make_result):
        """Test that pattern matching is case-insensitive."""
        messages = [
            "СКОЛЬКО СТОИТ?",
            "Сколько Стоит?",
            "сколько стоит?",
        ]

        for message in messages:
            ctx = make_context(message=message, intent="info_provided")
            result = make_result(intent="info_provided")
            refined = layer.refine(message, result, ctx)

            assert "price_question" in refined.secondary_signals

    def test_layer_disabled(self, layer, make_context, make_result):
        """Test that disabled layer passes through."""
        layer._enabled = False

        message = "100 человек. Сколько стоит?"
        ctx = make_context(message=message, intent="info_provided")
        result = make_result(intent="info_provided")

        refined = layer.refine(message, result, ctx)

        assert refined.decision == RefinementDecision.PASS_THROUGH

        # Re-enable for other tests
        layer._enabled = True

# =============================================================================
# STATISTICS TESTS
# =============================================================================

class TestStatistics:
    """Test statistics tracking."""

    def test_stats_tracking(self, layer, make_context, make_result):
        """Test that detection statistics are tracked."""
        # Reset stats
        layer._detections_by_intent = {}
        layer._multi_intent_count = 0

        # Detect single intent
        ctx1 = make_context(message="Сколько стоит?", intent="info_provided")
        result1 = make_result(intent="info_provided")
        layer.refine("Сколько стоит?", result1, ctx1)

        assert layer._detections_by_intent.get("price_question", 0) >= 1

        # Detect multiple intents
        ctx2 = make_context(
            message="Сколько стоит и какие функции?",
            intent="info_provided"
        )
        result2 = make_result(intent="info_provided")
        layer.refine("Сколько стоит и какие функции?", result2, ctx2)

        assert layer._multi_intent_count >= 1

    def test_get_stats(self, layer):
        """Test get_stats returns expected structure."""
        stats = layer.get_stats()

        assert "layer" in stats
        assert "enabled" in stats
        assert "detections_by_intent" in stats
        assert "multi_intent_count" in stats
        assert "patterns_count" in stats

# =============================================================================
# REAL-WORLD SCENARIO TESTS
# =============================================================================

class TestRealWorldScenarios:
    """Test real-world composite message scenarios from the bug report."""

    def test_bug_scenario_1(self, layer, make_context, make_result):
        """
        Original bug scenario:
        User: "100 человек. Давайте уже по делу — сколько стоит?"
        LLM classifies as: info_provided (data detected)
        Expected: price_question detected as secondary
        """
        message = "100 человек. Давайте уже по делу — сколько стоит?"
        ctx = make_context(message=message, intent="info_provided")
        result = make_result(intent="info_provided")

        refined = layer.refine(message, result, ctx)

        assert refined.decision == RefinementDecision.REFINED
        assert refined.intent == "info_provided"  # Primary preserved
        assert "price_question" in refined.secondary_signals
        assert "request_brevity" in refined.secondary_signals

    def test_bug_scenario_2(self, layer, make_context, make_result):
        """
        Original bug scenario:
        User: "500 тыс. максимум. Не тяни, давай по делу"
        LLM classifies as: info_provided (budget data)
        Expected: request_brevity detected, possibly implicit price question
        """
        message = "500 тыс. максимум. Не тяни, давай по делу"
        ctx = make_context(message=message, intent="info_provided")
        result = make_result(intent="info_provided")

        refined = layer.refine(message, result, ctx)

        assert refined.decision == RefinementDecision.REFINED
        assert refined.intent == "info_provided"  # Primary preserved
        assert "request_brevity" in refined.secondary_signals

    def test_bug_scenario_3(self, layer, make_context, make_result):
        """
        Composite with feature question:
        User: "У нас ресторан, 20 столов. Как насчёт интеграции с Каспи?"
        LLM classifies as: situation_provided (business info)
        Expected: question_integrations detected as secondary
        """
        message = "У нас ресторан, 20 столов. Как насчёт интеграции с Каспи?"
        ctx = make_context(message=message, intent="situation_provided")
        result = make_result(intent="situation_provided")

        refined = layer.refine(message, result, ctx)

        assert refined.decision == RefinementDecision.REFINED
        assert refined.intent == "situation_provided"  # Primary preserved
        assert "question_integrations" in refined.secondary_signals

# =============================================================================
# LOST QUESTION BUG FIX TESTS - NEW PATTERNS
# =============================================================================

class TestLostQuestionBugFixPatterns:
    """
    Tests for the "Lost Question" bug fix - new secondary intent patterns.

    Bug: Questions about data migration were being ignored because:
    1. No secondary intent patterns for question_data_migration
    2. No patterns for question_implementation, question_updates, etc.

    Fix: Added patterns in constants.yaml for these question types.
    """

    def test_data_migration_pattern_exists(self, layer):
        """Test that question_data_migration pattern is loaded from YAML."""
        # Pattern should be loaded from YAML config
        assert "question_data_migration" in layer._patterns, \
            "question_data_migration pattern should be loaded from YAML"

    def test_implementation_pattern_exists(self, layer):
        """Test that question_implementation pattern is loaded from YAML."""
        assert "question_implementation" in layer._patterns, \
            "question_implementation pattern should be loaded from YAML"

    def test_updates_pattern_exists(self, layer):
        """Test that question_updates pattern is loaded from YAML."""
        assert "question_updates" in layer._patterns, \
            "question_updates pattern should be loaded from YAML"

    def test_offline_pattern_exists(self, layer):
        """Test that question_offline pattern is loaded from YAML."""
        assert "question_offline" in layer._patterns, \
            "question_offline pattern should be loaded from YAML"

    def test_customization_pattern_exists(self, layer):
        """Test that question_customization pattern is loaded from YAML."""
        assert "question_customization" in layer._patterns, \
            "question_customization pattern should be loaded from YAML"

    def test_automation_pattern_exists(self, layer):
        """Test that question_automation pattern is loaded from YAML."""
        assert "question_automation" in layer._patterns, \
            "question_automation pattern should be loaded from YAML"

    def test_scalability_pattern_exists(self, layer):
        """Test that question_scalability pattern is loaded from YAML."""
        assert "question_scalability" in layer._patterns, \
            "question_scalability pattern should be loaded from YAML"

class TestDataMigrationSecondaryDetection:
    """
    Tests for detecting question_data_migration as secondary intent.

    Bug scenario:
    - Bot: "Какой у вас бюджет?"
    - User: "100 человек. Как перенесёте данные?"
    - Old behavior: Bot ignores question, asks about budget again
    - New behavior: Bot detects question_data_migration, responds to question
    """

    def test_data_migration_detected_in_composite(self, layer, make_context, make_result):
        """
        Scenario: "100 человек. Как перенесёте данные?"
        Primary: info_provided (100 человек = data)
        Expected secondary: question_data_migration
        """
        message = "100 человек. Как перенесёте данные?"
        ctx = make_context(message=message, intent="info_provided")
        result = make_result(intent="info_provided")

        refined = layer.refine(message, result, ctx)

        assert refined.decision == RefinementDecision.REFINED
        assert refined.intent == "info_provided"  # Primary preserved
        assert "question_data_migration" in refined.secondary_signals, \
            f"question_data_migration should be detected, got {refined.secondary_signals}"

    def test_data_migration_detected_with_import(self, layer, make_context, make_result):
        """
        Scenario: "Да, интересно. А можно импортировать данные из Excel?"
        Primary: agreement
        Expected secondary: question_data_migration
        """
        message = "Да, интересно. А можно импортировать данные из Excel?"
        ctx = make_context(message=message, intent="agreement")
        result = make_result(intent="agreement")

        refined = layer.refine(message, result, ctx)

        assert refined.decision == RefinementDecision.REFINED
        assert "question_data_migration" in refined.secondary_signals

    def test_data_migration_detected_with_migration_word(self, layer, make_context, make_result):
        """
        Scenario: "Хорошо. Как работает миграция?"
        Primary: agreement
        Expected secondary: question_data_migration
        """
        message = "Хорошо. Как работает миграция?"
        ctx = make_context(message=message, intent="agreement")
        result = make_result(intent="agreement")

        refined = layer.refine(message, result, ctx)

        assert refined.decision == RefinementDecision.REFINED
        assert "question_data_migration" in refined.secondary_signals

class TestImplementationSecondaryDetection:
    """Tests for detecting question_implementation as secondary intent."""

    def test_implementation_detected_in_composite(self, layer, make_context, make_result):
        """
        Scenario: "Берём. Как происходит внедрение?"
        Primary: agreement / ready_to_buy
        Expected secondary: question_implementation
        """
        message = "Берём. Как происходит внедрение?"
        ctx = make_context(message=message, intent="agreement")
        result = make_result(intent="agreement")

        refined = layer.refine(message, result, ctx)

        assert refined.decision == RefinementDecision.REFINED
        assert "question_implementation" in refined.secondary_signals, \
            f"question_implementation should be detected, got {refined.secondary_signals}"

    def test_implementation_with_training_question(self, layer, make_context, make_result):
        """
        Scenario: "Хорошо, подходит. Есть ли обучение при внедрении?"
        """
        message = "Хорошо, подходит. Есть ли обучение при внедрении?"
        ctx = make_context(message=message, intent="agreement")
        result = make_result(intent="agreement")

        refined = layer.refine(message, result, ctx)

        assert refined.decision == RefinementDecision.REFINED
        assert "question_implementation" in refined.secondary_signals

class TestOfflineSecondaryDetection:
    """Tests for detecting question_offline as secondary intent."""

    def test_offline_detected(self, layer, make_context, make_result):
        """
        Scenario: "Окей. А работает ли без интернета?"
        """
        message = "Окей. А работает ли без интернета?"
        ctx = make_context(message=message, intent="agreement")
        result = make_result(intent="agreement")

        refined = layer.refine(message, result, ctx)

        assert refined.decision == RefinementDecision.REFINED
        assert "question_offline" in refined.secondary_signals
