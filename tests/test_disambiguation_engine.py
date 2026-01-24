"""
Comprehensive tests for DisambiguationDecisionEngine.

Tests cover:
- Decision matrix (all confidence/gap combinations)
- Bypass conditions
- Options building
- Configuration loading
- Integration with UnifiedClassifier
- Metrics and statistics
- Edge cases and error handling
"""
import pytest
from typing import Dict, Any, List
from unittest.mock import patch, MagicMock

from src.classifier.disambiguation_engine import (
    DisambiguationDecisionEngine,
    DisambiguationDecision,
    DisambiguationConfig,
    DisambiguationResult,
    DisambiguationOption,
    get_disambiguation_engine,
    reset_disambiguation_engine,
    INTENT_LABELS,
)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def default_config():
    """Default configuration for testing."""
    return DisambiguationConfig()


@pytest.fixture
def engine(default_config):
    """Engine instance with default config."""
    return DisambiguationDecisionEngine(default_config)


@pytest.fixture
def custom_config():
    """Custom configuration for specific tests."""
    return DisambiguationConfig(
        high_confidence=0.90,
        medium_confidence=0.70,
        low_confidence=0.50,
        min_confidence=0.35,
        gap_threshold=0.25,
        max_options=4,
        min_option_confidence=0.20,
        bypass_intents=["rejection", "demo_request"],
        excluded_intents=["unclear"],
        cooldown_turns=2,
    )


@pytest.fixture
def engine_custom(custom_config):
    """Engine instance with custom config."""
    return DisambiguationDecisionEngine(custom_config)


@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset singleton before each test."""
    reset_disambiguation_engine()
    yield
    reset_disambiguation_engine()


# =============================================================================
# TEST: DisambiguationConfig
# =============================================================================

class TestDisambiguationConfig:
    """Tests for DisambiguationConfig dataclass."""

    def test_default_values(self):
        """Default config has expected values."""
        config = DisambiguationConfig()

        assert config.high_confidence == 0.85
        assert config.medium_confidence == 0.65
        assert config.low_confidence == 0.45
        assert config.min_confidence == 0.30
        assert config.gap_threshold == 0.20
        assert config.max_options == 3
        assert config.min_option_confidence == 0.25
        assert config.cooldown_turns == 3
        assert "rejection" in config.bypass_intents
        assert "unclear" in config.excluded_intents

    def test_from_config_dict(self):
        """Config created from dict correctly."""
        config_dict = {
            "high_confidence": 0.90,
            "gap_threshold": 0.30,
            "max_options": 5,
            "bypass_disambiguation_intents": ["custom_bypass"],
            "excluded_intents": ["custom_excluded"],
        }

        config = DisambiguationConfig.from_config(config_dict)

        assert config.high_confidence == 0.90
        assert config.gap_threshold == 0.30
        assert config.max_options == 5
        assert config.bypass_intents == ["custom_bypass"]
        assert config.excluded_intents == ["custom_excluded"]

    def test_from_config_with_legacy_keys(self):
        """Config handles legacy key names."""
        config_dict = {
            "max_score_gap": 0.25,  # Legacy key name
        }

        config = DisambiguationConfig.from_config(config_dict)

        assert config.gap_threshold == 0.25


# =============================================================================
# TEST: Decision Matrix
# =============================================================================

class TestDecisionMatrix:
    """Tests for the decision matrix logic."""

    # High confidence tests

    def test_high_confidence_large_gap_executes(self, engine):
        """High confidence + large gap -> EXECUTE."""
        classification = {
            "intent": "demo_request",
            "confidence": 0.90,
            "alternatives": [{"intent": "callback_request", "confidence": 0.60}],
        }

        result = engine.analyze(classification, {})

        # Gap is 0.30 (>= 0.20), confidence is 0.90 (>= 0.85)
        # But demo_request is in bypass_intents, so always EXECUTE
        assert result.decision == DisambiguationDecision.EXECUTE
        assert result.needs_disambiguation is False

    def test_high_confidence_large_gap_non_bypass_executes(self, engine):
        """High confidence + large gap + non-bypass intent -> EXECUTE."""
        classification = {
            "intent": "price_question",
            "confidence": 0.90,
            "alternatives": [{"intent": "pricing_details", "confidence": 0.60}],
        }

        result = engine.analyze(classification, {})

        # Gap is 0.30 (>= 0.20), confidence is 0.90 (>= 0.85)
        assert result.decision == DisambiguationDecision.EXECUTE
        assert result.needs_disambiguation is False

    def test_high_confidence_small_gap_confirms(self, engine):
        """High confidence + small gap -> CONFIRM."""
        classification = {
            "intent": "price_question",
            "confidence": 0.88,
            "alternatives": [{"intent": "pricing_details", "confidence": 0.80}],
        }

        result = engine.analyze(classification, {})

        # Gap is 0.08 (< 0.20), confidence is 0.88 (>= 0.85)
        assert result.decision == DisambiguationDecision.CONFIRM
        assert result.needs_disambiguation is True
        assert result.confirm_question != ""

    # Medium confidence tests

    def test_medium_confidence_large_gap_executes(self, engine):
        """Medium confidence + large gap -> EXECUTE."""
        classification = {
            "intent": "question_features",
            "confidence": 0.75,
            "alternatives": [{"intent": "comparison", "confidence": 0.45}],
        }

        result = engine.analyze(classification, {})

        # Gap is 0.30 (>= 0.20), confidence is 0.75 (>= 0.65)
        assert result.decision == DisambiguationDecision.EXECUTE
        assert result.needs_disambiguation is False

    def test_medium_confidence_small_gap_confirms(self, engine):
        """Medium confidence + small gap -> CONFIRM."""
        classification = {
            "intent": "question_features",
            "confidence": 0.70,
            "alternatives": [{"intent": "comparison", "confidence": 0.60}],
        }

        result = engine.analyze(classification, {})

        # Gap is 0.10 (< 0.20), confidence is 0.70 (>= 0.65)
        assert result.decision == DisambiguationDecision.CONFIRM
        assert result.needs_disambiguation is True

    # Low confidence tests

    def test_low_confidence_disambiguates(self, engine):
        """Low confidence -> DISAMBIGUATE regardless of gap."""
        classification = {
            "intent": "agreement",
            "confidence": 0.50,
            "alternatives": [
                {"intent": "situation_provided", "confidence": 0.45},
                {"intent": "info_provided", "confidence": 0.40},
            ],
        }

        result = engine.analyze(classification, {})

        # Confidence is 0.50 (< 0.65, >= 0.45)
        assert result.decision == DisambiguationDecision.DISAMBIGUATE
        assert result.needs_disambiguation is True
        assert len(result.options) > 0

    def test_very_low_confidence_disambiguates(self, engine):
        """Very low confidence -> DISAMBIGUATE."""
        classification = {
            "intent": "unclear",
            "confidence": 0.35,
            "alternatives": [],
        }

        result = engine.analyze(classification, {})

        # Confidence is 0.35 (< 0.45, >= 0.30)
        assert result.decision == DisambiguationDecision.DISAMBIGUATE
        assert result.needs_disambiguation is True

    # Fallback tests

    def test_below_minimum_confidence_fallback(self, engine):
        """Below minimum confidence -> FALLBACK."""
        classification = {
            "intent": "unclear",
            "confidence": 0.20,
            "alternatives": [],
        }

        result = engine.analyze(classification, {})

        # Confidence is 0.20 (< 0.30)
        assert result.decision == DisambiguationDecision.FALLBACK
        assert result.needs_disambiguation is False


# =============================================================================
# TEST: Bypass Conditions
# =============================================================================

class TestBypassConditions:
    """Tests for bypass conditions."""

    def test_bypass_intent_always_executes(self, engine):
        """Bypass intents always return EXECUTE."""
        for bypass_intent in ["rejection", "contact_provided", "demo_request"]:
            classification = {
                "intent": bypass_intent,
                "confidence": 0.50,  # Would normally DISAMBIGUATE
                "alternatives": [],
            }

            result = engine.analyze(classification, {})

            assert result.decision == DisambiguationDecision.EXECUTE
            assert "Bypass intent" in result.reasoning

    def test_in_disambiguation_mode_executes(self, engine):
        """Already in disambiguation mode -> EXECUTE."""
        classification = {
            "intent": "agreement",
            "confidence": 0.50,
            "alternatives": [],
        }
        context = {"in_disambiguation": True}

        result = engine.analyze(classification, context)

        assert result.decision == DisambiguationDecision.EXECUTE
        assert "Already in disambiguation" in result.reasoning

    def test_cooldown_active_executes(self, engine):
        """Cooldown active -> EXECUTE."""
        classification = {
            "intent": "agreement",
            "confidence": 0.50,
            "alternatives": [],
        }
        context = {"turns_since_last_disambiguation": 1}  # < 3 (cooldown)

        result = engine.analyze(classification, context)

        assert result.decision == DisambiguationDecision.EXECUTE
        assert "Cooldown active" in result.reasoning

    def test_cooldown_expired_allows_disambiguation(self, engine):
        """Cooldown expired -> normal analysis."""
        classification = {
            "intent": "agreement",
            "confidence": 0.50,
            "alternatives": [],
        }
        context = {"turns_since_last_disambiguation": 5}  # > 3 (cooldown)

        result = engine.analyze(classification, context)

        # Normal analysis proceeds
        assert result.decision == DisambiguationDecision.DISAMBIGUATE

    def test_very_high_confidence_executes(self, engine):
        """Very high confidence (0.95+) -> EXECUTE."""
        classification = {
            "intent": "agreement",
            "confidence": 0.96,
            "alternatives": [{"intent": "info_provided", "confidence": 0.95}],  # Small gap
        }

        result = engine.analyze(classification, {})

        assert result.decision == DisambiguationDecision.EXECUTE
        assert "Very high confidence" in result.reasoning


# =============================================================================
# TEST: Gap Calculation
# =============================================================================

class TestGapCalculation:
    """Tests for gap calculation logic."""

    def test_gap_with_alternatives(self, engine):
        """Gap calculated correctly with alternatives."""
        classification = {
            "intent": "price_question",
            "confidence": 0.80,
            "alternatives": [
                {"intent": "pricing_details", "confidence": 0.60},
                {"intent": "comparison", "confidence": 0.40},
            ],
        }

        result = engine.analyze(classification, {})

        # Gap = 0.80 - 0.60 = 0.20
        assert result.gap == pytest.approx(0.20)

    def test_gap_without_alternatives_conservative(self, engine):
        """Without alternatives, gap is conservative (capped)."""
        classification = {
            "intent": "price_question",
            "confidence": 0.80,
            "alternatives": [],
        }

        result = engine.analyze(classification, {})

        # Gap capped at min(confidence, 0.5) = 0.5
        assert result.gap == 0.5

    def test_gap_without_alternatives_low_confidence(self, engine):
        """Without alternatives + low confidence -> small gap."""
        classification = {
            "intent": "unclear",
            "confidence": 0.40,
            "alternatives": [],
        }

        result = engine.analyze(classification, {})

        # Gap = min(0.40, 0.5) = 0.40
        assert result.gap == 0.40


# =============================================================================
# TEST: Options Building
# =============================================================================

class TestOptionsBuilding:
    """Tests for options building logic."""

    def test_options_include_top_intent(self, engine):
        """Options include top intent."""
        classification = {
            "intent": "price_question",
            "confidence": 0.50,
            "alternatives": [
                {"intent": "pricing_details", "confidence": 0.45},
            ],
        }

        result = engine.analyze(classification, {})

        intent_list = [o.intent for o in result.options]
        assert "price_question" in intent_list

    def test_options_include_alternatives(self, engine):
        """Options include alternatives with sufficient confidence."""
        classification = {
            "intent": "price_question",
            "confidence": 0.50,
            "alternatives": [
                {"intent": "pricing_details", "confidence": 0.45},
            ],
        }

        result = engine.analyze(classification, {})

        intent_list = [o.intent for o in result.options]
        assert "pricing_details" in intent_list
        # Note: max_options=3 means top + (max_options-1) alternatives + "other"
        # So with 1 alternative we get: price_question, pricing_details, other

    def test_options_exclude_low_confidence_alternatives(self, engine):
        """Options exclude alternatives with low confidence."""
        classification = {
            "intent": "price_question",
            "confidence": 0.50,
            "alternatives": [
                {"intent": "pricing_details", "confidence": 0.10},  # Below min_option_confidence
            ],
        }

        result = engine.analyze(classification, {})

        intent_list = [o.intent for o in result.options]
        assert "pricing_details" not in intent_list

    def test_options_exclude_excluded_intents(self, engine):
        """Options exclude intents in excluded_intents list."""
        classification = {
            "intent": "unclear",  # In excluded_intents
            "confidence": 0.50,
            "alternatives": [
                {"intent": "small_talk", "confidence": 0.45},  # Also excluded
                {"intent": "agreement", "confidence": 0.40},
            ],
        }

        result = engine.analyze(classification, {})

        intent_list = [o.intent for o in result.options]
        assert "unclear" not in intent_list
        assert "small_talk" not in intent_list
        assert "agreement" in intent_list

    def test_options_always_include_other(self, engine):
        """Options always include 'Other' option."""
        classification = {
            "intent": "price_question",
            "confidence": 0.50,
            "alternatives": [],
        }

        result = engine.analyze(classification, {})

        intent_list = [o.intent for o in result.options]
        assert "other" in intent_list

    def test_options_respect_max_options(self, engine):
        """Options respect max_options limit."""
        classification = {
            "intent": "price_question",
            "confidence": 0.50,
            "alternatives": [
                {"intent": "pricing_details", "confidence": 0.45},
                {"intent": "comparison", "confidence": 0.40},
                {"intent": "question_features", "confidence": 0.35},
                {"intent": "demo_request", "confidence": 0.30},
            ],
        }

        result = engine.analyze(classification, {})

        # max_options is 3, plus "other" = 4 total... actually max_options - 1 alternatives + top + other
        # Let me check the logic...
        # Actually options = top + (max_options - 1) alternatives + other
        assert len(result.options) <= engine.config.max_options + 1

    def test_options_have_labels(self, engine):
        """Options have human-readable labels."""
        classification = {
            "intent": "price_question",
            "confidence": 0.50,
            "alternatives": [],
        }

        result = engine.analyze(classification, {})

        for option in result.options:
            assert option.label != ""
            assert option.label != option.intent or option.intent == "other"


# =============================================================================
# TEST: Confirm Question
# =============================================================================

class TestConfirmQuestion:
    """Tests for confirm question building."""

    def test_confirm_question_for_known_intent(self, engine):
        """Confirm question uses template for known intents."""
        classification = {
            "intent": "demo_request",
            "confidence": 0.88,
            "alternatives": [{"intent": "callback_request", "confidence": 0.80}],
        }

        # demo_request is bypass, so use different intent
        classification = {
            "intent": "price_question",
            "confidence": 0.88,
            "alternatives": [{"intent": "pricing_details", "confidence": 0.80}],
        }

        result = engine.analyze(classification, {})

        assert result.decision == DisambiguationDecision.CONFIRM
        assert "стоимость" in result.confirm_question.lower()

    def test_confirm_question_for_unknown_intent(self, engine):
        """Confirm question uses generic template for unknown intents."""
        classification = {
            "intent": "some_custom_intent",
            "confidence": 0.88,
            "alternatives": [{"intent": "another_intent", "confidence": 0.80}],
        }

        result = engine.analyze(classification, {})

        assert result.decision == DisambiguationDecision.CONFIRM
        assert "Правильно ли я понял" in result.confirm_question


# =============================================================================
# TEST: DisambiguationResult
# =============================================================================

class TestDisambiguationResult:
    """Tests for DisambiguationResult dataclass."""

    def test_disambiguation_triggered_property(self):
        """disambiguation_triggered property works correctly."""
        result_confirm = DisambiguationResult(
            decision=DisambiguationDecision.CONFIRM,
            needs_disambiguation=True,
            intent="test",
            confidence=0.8,
        )
        assert result_confirm.disambiguation_triggered is True

        result_disambiguate = DisambiguationResult(
            decision=DisambiguationDecision.DISAMBIGUATE,
            needs_disambiguation=True,
            intent="test",
            confidence=0.5,
        )
        assert result_disambiguate.disambiguation_triggered is True

        result_execute = DisambiguationResult(
            decision=DisambiguationDecision.EXECUTE,
            needs_disambiguation=False,
            intent="test",
            confidence=0.9,
        )
        assert result_execute.disambiguation_triggered is False

        result_fallback = DisambiguationResult(
            decision=DisambiguationDecision.FALLBACK,
            needs_disambiguation=False,
            intent="test",
            confidence=0.2,
        )
        assert result_fallback.disambiguation_triggered is False

    def test_to_classification_result_when_needed(self):
        """to_classification_result returns data when disambiguation needed."""
        result = DisambiguationResult(
            decision=DisambiguationDecision.DISAMBIGUATE,
            needs_disambiguation=True,
            intent="price_question",
            confidence=0.50,
            options=[
                DisambiguationOption("price_question", "Узнать цену", 0.50),
                DisambiguationOption("other", "Другое", 0.0),
            ],
            question="Уточните, пожалуйста:",
            gap=0.15,
        )

        classification = result.to_classification_result()

        assert classification["intent"] == "disambiguation_needed"
        assert classification["original_intent"] == "price_question"
        assert len(classification["disambiguation_options"]) == 2
        assert classification["disambiguation_question"] == "Уточните, пожалуйста:"

    def test_to_classification_result_when_not_needed(self):
        """to_classification_result returns empty dict when not needed."""
        result = DisambiguationResult(
            decision=DisambiguationDecision.EXECUTE,
            needs_disambiguation=False,
            intent="price_question",
            confidence=0.90,
        )

        classification = result.to_classification_result()

        assert classification == {}


# =============================================================================
# TEST: Statistics
# =============================================================================

class TestStatistics:
    """Tests for statistics tracking."""

    def test_stats_tracking(self, engine):
        """Engine tracks statistics correctly."""
        # Execute classification
        engine.analyze({"intent": "test", "confidence": 0.95, "alternatives": []}, {})
        engine.analyze({"intent": "test", "confidence": 0.50, "alternatives": []}, {})
        engine.analyze({"intent": "test", "confidence": 0.20, "alternatives": []}, {})

        stats = engine.get_stats()

        assert stats["total_analyses"] == 3
        assert stats["decisions"]["execute"] >= 1
        assert stats["decisions"]["disambiguate"] >= 1
        assert stats["decisions"]["fallback"] >= 1


# =============================================================================
# TEST: Error Handling
# =============================================================================

class TestErrorHandling:
    """Tests for error handling."""

    def test_handles_missing_intent(self, engine):
        """Engine handles missing intent gracefully."""
        classification = {
            "confidence": 0.50,
            "alternatives": [],
        }

        result = engine.analyze(classification, {})

        # Should not raise, defaults to "unclear"
        assert result.intent == "unclear"

    def test_handles_missing_confidence(self, engine):
        """Engine handles missing confidence gracefully."""
        classification = {
            "intent": "test",
            "alternatives": [],
        }

        result = engine.analyze(classification, {})

        # Should not raise, defaults to 0.0
        assert result.confidence == 0.0

    def test_handles_missing_alternatives(self, engine):
        """Engine handles missing alternatives gracefully."""
        classification = {
            "intent": "test",
            "confidence": 0.50,
        }

        result = engine.analyze(classification, {})

        # Should not raise
        assert result is not None

    def test_handles_none_context(self, engine):
        """Engine handles None context gracefully."""
        classification = {
            "intent": "test",
            "confidence": 0.50,
            "alternatives": [],
        }

        result = engine.analyze(classification, None)

        assert result is not None


# =============================================================================
# TEST: Singleton Factory
# =============================================================================

class TestSingletonFactory:
    """Tests for singleton factory function."""

    def test_returns_same_instance(self):
        """get_disambiguation_engine returns same instance."""
        engine1 = get_disambiguation_engine()
        engine2 = get_disambiguation_engine()

        assert engine1 is engine2

    def test_reset_creates_new_instance(self):
        """reset_disambiguation_engine creates new instance."""
        engine1 = get_disambiguation_engine()
        reset_disambiguation_engine()
        engine2 = get_disambiguation_engine()

        assert engine1 is not engine2

    def test_custom_config_used(self):
        """Custom config is used when provided."""
        config = {
            "high_confidence": 0.99,
            "gap_threshold": 0.50,
        }

        engine = get_disambiguation_engine(config)

        assert engine.config.high_confidence == 0.99
        assert engine.config.gap_threshold == 0.50


# =============================================================================
# TEST: Integration with Classification
# =============================================================================

class TestIntegration:
    """Integration tests with classification pipeline."""

    def test_full_classification_flow(self, engine):
        """Full flow from classification to disambiguation result."""
        # Simulated LLM classification result
        classification = {
            "intent": "price_question",
            "confidence": 0.55,
            "extracted_data": {"product_type": "crm"},
            "method": "llm",
            "alternatives": [
                {"intent": "pricing_details", "confidence": 0.50},
                {"intent": "comparison", "confidence": 0.40},
            ],
        }

        result = engine.analyze(classification, {
            "state": "spin_situation",
            "spin_phase": "situation",
        })

        assert result.decision == DisambiguationDecision.DISAMBIGUATE
        assert result.needs_disambiguation is True
        assert len(result.options) >= 2  # At least top + other

        # Verify classification result format
        class_result = result.to_classification_result()
        assert class_result["intent"] == "disambiguation_needed"
        assert class_result["original_intent"] == "price_question"

    def test_hybrid_classifier_result_format(self, engine):
        """Works with HybridClassifier result format."""
        classification = {
            "intent": "agreement",
            "confidence": 0.60,
            "extracted_data": {},
            "method": "hybrid",
            "all_scores": {
                "agreement": 0.60,
                "situation_provided": 0.55,
                "info_provided": 0.50,
            },
            # HybridClassifier may not provide alternatives in same format
            "alternatives": [],
        }

        result = engine.analyze(classification, {})

        # Should handle gracefully
        assert result is not None
        assert result.decision in DisambiguationDecision


# =============================================================================
# TEST: YAML Config Loading
# =============================================================================

class TestYAMLConfigLoading:
    """Tests for YAML configuration loading."""

    def test_loads_from_yaml_config(self):
        """Engine loads config from YAML when available."""
        # This test verifies the config loading chain
        # Actual YAML config should be loaded in production

        reset_disambiguation_engine()

        # Get engine - should load from YAML/config
        engine = get_disambiguation_engine()

        # Verify some config was loaded
        assert engine.config is not None
        assert engine.config.high_confidence > 0
        assert engine.config.gap_threshold > 0
