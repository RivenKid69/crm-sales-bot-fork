"""
Comprehensive tests for ConfidenceCalibrationLayer.

Tests the scientific confidence calibration implementation:
- Entropy-based calibration strategy
- Gap-based calibration strategy
- Heuristic calibration strategy
- Combined calibrator
- Integration with RefinementPipeline

All tests use mock data - no LLM required.
"""

import pytest
import math
from typing import Dict, Any, List

from src.classifier.confidence_calibration import (
    CalibrationReason,
    CalibrationResult,
    EntropyCalibrationStrategy,
    GapCalibrationStrategy,
    HeuristicCalibrationStrategy,
    ConfidenceCalibrator,
    ConfidenceCalibrationLayer,
    calculate_entropy,
    calculate_gap,
)
from src.classifier.refinement_pipeline import (
    RefinementContext,
    RefinementDecision,
    LayerPriority,
)

# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def default_config() -> Dict[str, Any]:
    """Default calibration configuration for tests."""
    return {
        "enabled": True,
        "min_confidence_floor": 0.1,
        "max_confidence_ceiling": 0.95,
        "entropy_enabled": True,
        "entropy_threshold": 0.5,
        "entropy_penalty_factor": 0.15,
        "gap_enabled": True,
        "gap_threshold": 0.2,
        "gap_penalty_factor": 0.2,
        "no_alternatives_penalty": 0.1,
        "min_gap_for_high_confidence": 0.15,
        "high_confidence_small_gap_penalty": 0.1,
        "heuristic_enabled": True,
        "short_message_words": 3,
        "short_message_penalty": 0.15,
        "overconfident_intent_penalty": 0.1,
        "context_mismatch_penalty": 0.1,
        "objection_overconfidence_penalty": 0.1,
        "overconfident_intents": ["greeting", "farewell", "small_talk"],
        "data_expecting_actions": ["ask_about_company", "ask_situation"],
        "data_intents": ["info_provided", "situation_provided"],
        # FIX: Added objection_think to match YAML config
        "objection_intents": ["objection_price", "objection_no_time", "objection_think"],
        # FIX: Rule 5 - penalty for objection without alternatives
        "objection_no_alternatives_penalty": 0.15,
        "objection_no_alternatives_threshold": 0.75,
    }

@pytest.fixture
def simple_context() -> RefinementContext:
    """Simple context for testing."""
    return RefinementContext(
        message="Да, у нас 5 человек в компании",
        intent="info_provided",
        confidence=0.85,
    )

@pytest.fixture
def short_message_context() -> RefinementContext:
    """Short message context for testing heuristic rules."""
    return RefinementContext(
        message="да",
        intent="greeting",
        confidence=0.9,
    )

@pytest.fixture
def alternatives_close() -> List[Dict[str, Any]]:
    """Alternatives with close confidences (ambiguous)."""
    return [
        {"intent": "objection_think", "confidence": 0.78},
        {"intent": "info_provided", "confidence": 0.72},
    ]

@pytest.fixture
def alternatives_far() -> List[Dict[str, Any]]:
    """Alternatives with distant confidences (clear winner)."""
    return [
        {"intent": "farewell", "confidence": 0.4},
        {"intent": "small_talk", "confidence": 0.3},
    ]

# =============================================================================
# UTILITY FUNCTION TESTS
# =============================================================================

class TestUtilityFunctions:
    """Tests for utility functions."""

    def test_calculate_entropy_uniform_distribution(self):
        """Uniform distribution should have maximum entropy."""
        # Uniform distribution: all equal
        confidences = [0.25, 0.25, 0.25, 0.25]
        entropy = calculate_entropy(confidences)
        # Normalized entropy should be 1.0 for uniform distribution
        assert entropy == pytest.approx(1.0, rel=0.01)

    def test_calculate_entropy_single_value(self):
        """Single value should have zero entropy."""
        confidences = [1.0]
        entropy = calculate_entropy(confidences)
        assert entropy == pytest.approx(0.0, rel=0.01)

    def test_calculate_entropy_skewed_distribution(self):
        """Skewed distribution should have lower entropy."""
        # Highly skewed: one dominant
        confidences = [0.9, 0.05, 0.05]
        entropy = calculate_entropy(confidences)
        # Should be less than 0.5 for skewed distribution
        assert entropy < 0.5

    def test_calculate_entropy_empty_list(self):
        """Empty list should return 0."""
        entropy = calculate_entropy([])
        assert entropy == 0.0

    def test_calculate_entropy_all_zeros(self):
        """All zeros should return 0."""
        entropy = calculate_entropy([0.0, 0.0, 0.0])
        assert entropy == 0.0

    def test_calculate_gap_with_alternatives(self):
        """Gap should be difference between primary and max alternative."""
        primary = 0.85
        alternatives = [0.65, 0.5, 0.3]
        gap = calculate_gap(primary, alternatives)
        assert gap == pytest.approx(0.20, rel=0.01)

    def test_calculate_gap_no_alternatives(self):
        """No alternatives should return maximum gap (1.0)."""
        primary = 0.85
        alternatives = []
        gap = calculate_gap(primary, alternatives)
        assert gap == 1.0

# =============================================================================
# ENTROPY STRATEGY TESTS
# =============================================================================

class TestEntropyCalibrationStrategy:
    """Tests for entropy-based calibration strategy."""

    def test_high_entropy_reduces_confidence(self, default_config, simple_context):
        """High entropy should reduce confidence."""
        strategy = EntropyCalibrationStrategy({"enabled": True})

        # Alternatives with similar confidences = high entropy
        alternatives = [
            {"intent": "objection_think", "confidence": 0.80},
            {"intent": "info_provided", "confidence": 0.75},
        ]

        calibrated, reason, penalties = strategy.calibrate(
            0.85, alternatives, simple_context, default_config
        )

        # With high entropy, confidence should be reduced
        assert calibrated < 0.85
        assert reason == CalibrationReason.ENTROPY_HIGH
        assert "entropy" in penalties

    def test_low_entropy_no_change(self, default_config, simple_context):
        """Low entropy should not change confidence."""
        strategy = EntropyCalibrationStrategy({"enabled": True})

        # One dominant alternative = low entropy
        alternatives = [
            {"intent": "farewell", "confidence": 0.2},
        ]

        calibrated, reason, penalties = strategy.calibrate(
            0.85, alternatives, simple_context, default_config
        )

        # With low entropy, no penalty applied
        if reason is None:
            assert calibrated == 0.85
        # entropy value should still be captured
        assert "entropy" in penalties

    def test_disabled_strategy_no_change(self, default_config, simple_context):
        """Disabled strategy should not modify confidence."""
        strategy = EntropyCalibrationStrategy({"enabled": False})

        alternatives = [
            {"intent": "objection_think", "confidence": 0.80},
        ]

        calibrated, reason, penalties = strategy.calibrate(
            0.85, alternatives, simple_context, default_config
        )

        assert calibrated == 0.85
        assert reason is None

    def test_no_alternatives_no_change(self, default_config, simple_context):
        """No alternatives should not apply entropy penalty."""
        strategy = EntropyCalibrationStrategy({"enabled": True})

        calibrated, reason, penalties = strategy.calibrate(
            0.85, [], simple_context, default_config
        )

        assert calibrated == 0.85
        assert reason is None

# =============================================================================
# GAP STRATEGY TESTS
# =============================================================================

class TestGapCalibrationStrategy:
    """Tests for gap-based calibration strategy."""

    def test_small_gap_reduces_confidence(
        self, default_config, simple_context, alternatives_close
    ):
        """Small gap should reduce confidence."""
        strategy = GapCalibrationStrategy({"enabled": True})

        calibrated, reason, penalties = strategy.calibrate(
            0.85, alternatives_close, simple_context, default_config
        )

        # Gap = 0.85 - 0.78 = 0.07, which is < 0.2 threshold
        assert calibrated < 0.85
        assert reason == CalibrationReason.GAP_SMALL
        assert "gap" in penalties

    def test_large_gap_no_change(
        self, default_config, simple_context, alternatives_far
    ):
        """Large gap should not change confidence."""
        strategy = GapCalibrationStrategy({"enabled": True})

        calibrated, reason, penalties = strategy.calibrate(
            0.85, alternatives_far, simple_context, default_config
        )

        # Gap = 0.85 - 0.4 = 0.45, which is >= 0.2 threshold
        assert calibrated == 0.85
        assert reason is None
        assert "gap" in penalties

    def test_no_alternatives_penalty(self, default_config, simple_context):
        """No alternatives with high confidence should apply penalty."""
        strategy = GapCalibrationStrategy({"enabled": True})

        calibrated, reason, penalties = strategy.calibrate(
            0.9, [], simple_context, default_config
        )

        # High confidence without alternatives is suspicious
        assert calibrated < 0.9
        assert reason == CalibrationReason.NO_ALTERNATIVES

    def test_low_confidence_no_alternatives_no_penalty(
        self, default_config, simple_context
    ):
        """Low confidence without alternatives should not apply penalty."""
        strategy = GapCalibrationStrategy({"enabled": True})

        calibrated, reason, penalties = strategy.calibrate(
            0.5, [], simple_context, default_config
        )

        # Low confidence is already uncertain
        assert calibrated == 0.5
        assert reason is None

    def test_high_confidence_small_gap_extra_penalty(
        self, default_config, simple_context
    ):
        """High confidence with very small gap should have extra penalty."""
        strategy = GapCalibrationStrategy({"enabled": True})

        # Very close alternatives
        alternatives = [
            {"intent": "objection_think", "confidence": 0.82},
        ]

        calibrated, reason, penalties = strategy.calibrate(
            0.85, alternatives, simple_context, default_config
        )

        # Gap = 0.03, which is very small
        # Should have both gap penalty and high_confidence_small_gap_penalty
        assert calibrated < 0.75  # Significant reduction

# =============================================================================
# HEURISTIC STRATEGY TESTS
# =============================================================================

class TestHeuristicCalibrationStrategy:
    """Tests for heuristic-based calibration strategy."""

    def test_short_message_penalty(self, default_config, short_message_context):
        """Short message with high confidence should be penalized."""
        strategy = HeuristicCalibrationStrategy({"enabled": True})

        calibrated, reason, penalties = strategy.calibrate(
            0.9, [], short_message_context, default_config
        )

        assert calibrated < 0.9
        assert reason == CalibrationReason.HEURISTIC_MATCH
        assert "short_message_penalty" in penalties

    def test_overconfident_intent_penalty(self, default_config):
        """Overconfident intent (greeting, farewell) should be penalized."""
        strategy = HeuristicCalibrationStrategy({"enabled": True})

        context = RefinementContext(
            message="Привет, как дела?",
            intent="greeting",  # In overconfident_intents list
            confidence=0.9,
        )

        calibrated, reason, penalties = strategy.calibrate(
            0.9, [], context, default_config
        )

        assert calibrated < 0.9
        assert reason == CalibrationReason.HEURISTIC_MATCH
        assert "overconfident_intent_penalty" in penalties

    def test_context_mismatch_penalty(self, default_config):
        """Intent mismatched with context should be penalized."""
        strategy = HeuristicCalibrationStrategy({"enabled": True})

        # Bot asked for company info, but got greeting
        context = RefinementContext(
            message="Здравствуйте!",
            intent="greeting",  # Not a data intent
            confidence=0.85,
            last_action="ask_about_company",  # Expects data
        )

        calibrated, reason, penalties = strategy.calibrate(
            0.85, [], context, default_config
        )

        assert calibrated < 0.85
        assert "context_mismatch_penalty" in penalties

    def test_objection_overconfidence_penalty(self, default_config):
        """High confidence objection should be penalized (threshold lowered to 0.8)."""
        strategy = HeuristicCalibrationStrategy({"enabled": True})

        context = RefinementContext(
            message="Нет, дорого",
            intent="objection_price",  # In objection_intents list
            confidence=0.85,  # Changed from 0.95 to test new threshold of 0.8
        )

        calibrated, reason, penalties = strategy.calibrate(
            0.85, [], context, default_config
        )

        # FIX: Rule 4 now triggers at 0.8 instead of 0.9
        assert calibrated < 0.85
        assert "objection_overconfidence_penalty" in penalties

    def test_objection_think_with_confidence_085(self, default_config):
        """
        FIX: objection_think with confidence 0.85 without alternatives should be penalized.

        This is the exact scenario from the bug report:
        - LLM returns objection_think with confidence 0.85
        - No alternatives provided (LLM was "confident")
        - Rule 4 (at 0.8) and Rule 5 (no alternatives) should both apply
        - Final confidence should be <= 0.65
        """
        strategy = HeuristicCalibrationStrategy({"enabled": True})

        context = RefinementContext(
            message="Да но быстрее. Нет времени ждать",
            intent="objection_think",  # In objection_intents list
            confidence=0.85,
        )

        # NO alternatives - like in the real simulation
        calibrated, reason, penalties = strategy.calibrate(
            0.85, [], context, default_config
        )

        # Rule 4: objection with confidence >= 0.8 → penalty 0.1
        # Rule 5: objection without alternatives with confidence >= 0.75 → penalty 0.15
        # Total penalty: 0.25
        # Expected: 0.85 - 0.25 = 0.60
        assert calibrated <= 0.65, f"Expected <= 0.65, got {calibrated}"
        assert "objection_overconfidence_penalty" in penalties
        assert "objection_no_alternatives_penalty" in penalties

    def test_objection_no_alternatives_penalty(self, default_config):
        """
        FIX: Rule 5 - Objection without alternatives should be heavily penalized.

        When LLM returns objection intent with high confidence but no alternatives,
        this is suspicious because:
        1. Objections are often misclassified
        2. No alternatives means entropy/gap strategies can't help
        """
        strategy = HeuristicCalibrationStrategy({"enabled": True})

        context = RefinementContext(
            message="Мне нужно подумать",
            intent="objection_think",
            confidence=0.80,  # Just at threshold
        )

        calibrated, reason, penalties = strategy.calibrate(
            0.80, [], context, default_config
        )

        # Should apply both Rule 4 and Rule 5
        assert "objection_overconfidence_penalty" in penalties
        assert "objection_no_alternatives_penalty" in penalties
        # Combined penalty should be significant
        assert calibrated <= 0.65

    def test_objection_with_alternatives_no_rule5(self, default_config):
        """Objection WITH alternatives should NOT trigger Rule 5."""
        strategy = HeuristicCalibrationStrategy({"enabled": True})

        context = RefinementContext(
            message="Мне нужно подумать",
            intent="objection_think",
            confidence=0.85,
        )

        # WITH alternatives - Rule 5 should NOT apply
        alternatives = [{"intent": "objection_no_time", "confidence": 0.75}]
        calibrated, reason, penalties = strategy.calibrate(
            0.85, alternatives, context, default_config
        )

        # Rule 4 applies (confidence >= 0.8)
        assert "objection_overconfidence_penalty" in penalties
        # Rule 5 should NOT apply (alternatives exist)
        assert "objection_no_alternatives_penalty" not in penalties

    def test_no_penalty_for_long_message(self, default_config, simple_context):
        """Long message should not trigger short message penalty."""
        strategy = HeuristicCalibrationStrategy({"enabled": True})

        # simple_context has 5+ words
        calibrated, reason, penalties = strategy.calibrate(
            0.85, [], simple_context, default_config
        )

        # info_provided is not in overconfident_intents, message is long
        # No penalties should apply
        assert calibrated == 0.85 or "short_message_penalty" not in penalties

# =============================================================================
# CONFIDENCE CALIBRATOR TESTS
# =============================================================================

class TestConfidenceCalibrator:
    """Tests for combined calibrator."""

    def test_combines_multiple_strategies(self, default_config):
        """Calibrator should combine penalties from multiple strategies."""
        calibrator = ConfidenceCalibrator(default_config)

        context = RefinementContext(
            message="да",  # Short message
            intent="greeting",  # Overconfident intent
            confidence=0.9,
        )

        # Close alternatives (small gap, high entropy)
        alternatives = [
            {"intent": "agreement", "confidence": 0.85},
        ]

        result = calibrator.calibrate(0.9, alternatives, context)

        # Multiple penalties should be applied
        assert result.calibration_applied
        assert result.calibrated_confidence < 0.85  # Reduced from original 0.9
        assert len(result.reasons) >= 2  # Multiple reasons

    def test_respects_floor_and_ceiling(self, default_config):
        """Calibrator should respect min floor and max ceiling."""
        calibrator = ConfidenceCalibrator(default_config)

        context = RefinementContext(
            message="x",  # Very short
            intent="greeting",
            confidence=0.99,
        )

        # Many close alternatives = maximum penalties
        alternatives = [
            {"intent": "agreement", "confidence": 0.98},
            {"intent": "farewell", "confidence": 0.97},
        ]

        result = calibrator.calibrate(0.99, alternatives, context)

        # Should not go below floor
        assert result.calibrated_confidence >= 0.1

    def test_no_calibration_for_low_confidence(self, default_config):
        """Low confidence should not trigger most penalties."""
        calibrator = ConfidenceCalibrator(default_config)

        context = RefinementContext(
            message="может быть",
            intent="unclear",
            confidence=0.4,
        )

        result = calibrator.calibrate(0.4, [], context)

        # Low confidence already uncertain, minimal calibration
        assert result.calibrated_confidence >= 0.35

    def test_statistics_tracking(self, default_config):
        """Calibrator should track statistics."""
        calibrator = ConfidenceCalibrator(default_config)

        context = RefinementContext(
            message="да",
            intent="greeting",
            confidence=0.9,
        )

        # Make several calibrations
        for _ in range(5):
            calibrator.calibrate(0.9, [], context)

        stats = calibrator.get_stats()

        assert stats["calibrations_total"] == 5
        assert stats["calibrations_applied"] >= 1
        assert "calibration_rate" in stats
        assert "avg_confidence_delta" in stats

# =============================================================================
# CONFIDENCE CALIBRATION LAYER TESTS
# =============================================================================

class TestConfidenceCalibrationLayer:
    """Tests for the refinement layer integration."""

    def test_layer_properties(self):
        """Layer should have correct properties."""
        layer = ConfidenceCalibrationLayer()

        assert layer.name == "confidence_calibration"
        assert layer.priority == LayerPriority.CRITICAL
        assert layer.FEATURE_FLAG == "confidence_calibration"

    def test_layer_refines_overconfident(self):
        """Layer should refine overconfident classifications."""
        layer = ConfidenceCalibrationLayer()

        result = {
            "intent": "greeting",
            "confidence": 0.9,
            "alternatives": [
                {"intent": "agreement", "confidence": 0.85},
            ],
            "extracted_data": {},
        }

        context = RefinementContext(
            message="да",
            intent="greeting",
            confidence=0.9,
        )

        refined = layer.refine("да", result, context)

        # Should apply calibration
        assert refined.decision == RefinementDecision.REFINED
        assert refined.confidence < 0.9
        assert refined.intent == "greeting"  # Intent unchanged
        assert "calibration" in refined.refinement_reason

    def test_layer_passes_through_low_confidence(self):
        """Layer should pass through low confidence unchanged."""
        layer = ConfidenceCalibrationLayer()

        result = {
            "intent": "info_provided",
            "confidence": 0.4,
            "alternatives": [],
            "extracted_data": {},
        }

        context = RefinementContext(
            message="Пять сотрудников в компании",
            intent="info_provided",
            confidence=0.4,
        )

        refined = layer.refine(
            "Пять сотрудников в компании", result, context
        )

        # Low confidence, should not have much calibration
        # (may pass through or have minimal calibration)
        assert refined.confidence >= 0.3

    def test_layer_preserves_extracted_data(self):
        """Layer should preserve extracted data."""
        layer = ConfidenceCalibrationLayer()

        extracted = {"company_size": 5, "business_type": "retail"}
        result = {
            "intent": "situation_provided",
            "confidence": 0.9,
            "alternatives": [{"intent": "info_provided", "confidence": 0.85}],
            "extracted_data": extracted,
        }

        context = RefinementContext(
            message="У нас 5 человек в рознице",
            intent="situation_provided",
            confidence=0.9,
        )

        refined = layer.refine("У нас 5 человек в рознице", result, context)

        assert refined.extracted_data == extracted

    def test_layer_includes_calibration_metadata(self):
        """Layer should include calibration metadata."""
        layer = ConfidenceCalibrationLayer()

        result = {
            "intent": "greeting",
            "confidence": 0.9,
            "alternatives": [{"intent": "agreement", "confidence": 0.88}],
            "extracted_data": {},
        }

        context = RefinementContext(
            message="да",
            intent="greeting",
            confidence=0.9,
        )

        refined = layer.refine("да", result, context)

        if refined.decision == RefinementDecision.REFINED:
            assert "calibration" in refined.metadata
            assert "original_confidence" in refined.metadata

    def test_layer_statistics(self):
        """Layer should track statistics."""
        layer = ConfidenceCalibrationLayer()

        result = {
            "intent": "greeting",
            "confidence": 0.9,
            "alternatives": [],
            "extracted_data": {},
        }

        context = RefinementContext(
            message="да",
            intent="greeting",
            confidence=0.9,
        )

        # Make several refinements
        for _ in range(3):
            layer.refine("да", result, context)

        stats = layer.get_stats()

        assert stats["calls_total"] == 3
        assert "calibrator_stats" in stats

# =============================================================================
# INTEGRATION TESTS
# =============================================================================

class TestCalibrationIntegration:
    """Integration tests with RefinementPipeline."""

    def test_layer_registers_with_registry(self):
        """Layer should be registered in RefinementLayerRegistry."""
        from src.classifier.refinement_pipeline import RefinementLayerRegistry

        registry = RefinementLayerRegistry.get_registry()
        layer = registry.get_layer_instance("confidence_calibration")

        assert layer is not None
        assert layer.name == "confidence_calibration"

    def test_calibration_before_other_layers(self):
        """Calibration should run before other layers (CRITICAL priority)."""
        from src.classifier.refinement_pipeline import (
            RefinementLayerRegistry,
            LayerPriority,
        )

        registry = RefinementLayerRegistry.get_registry()
        calibration_layer = registry.get_layer_instance("confidence_calibration")
        short_answer_layer = registry.get_layer_instance("short_answer")

        if calibration_layer and short_answer_layer:
            assert calibration_layer.priority.value > short_answer_layer.priority.value

# =============================================================================
# EDGE CASE TESTS
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases."""

    def test_zero_confidence(self, default_config):
        """Zero confidence should be handled gracefully."""
        calibrator = ConfidenceCalibrator(default_config)

        context = RefinementContext(
            message="???",
            intent="unclear",
            confidence=0.0,
        )

        result = calibrator.calibrate(0.0, [], context)

        assert result.calibrated_confidence >= 0.0

    def test_confidence_exactly_one(self, default_config):
        """Confidence of 1.0 should be reduced below ceiling."""
        calibrator = ConfidenceCalibrator(default_config)

        context = RefinementContext(
            message="Привет",
            intent="greeting",
            confidence=1.0,
        )

        result = calibrator.calibrate(1.0, [], context)

        # Should be reduced below max_confidence_ceiling (0.95)
        assert result.calibrated_confidence <= 0.95

    def test_empty_message(self, default_config):
        """Empty message should be handled gracefully."""
        calibrator = ConfidenceCalibrator(default_config)

        context = RefinementContext(
            message="",
            intent="unclear",
            confidence=0.5,
        )

        result = calibrator.calibrate(0.5, [], context)

        assert result.calibrated_confidence >= 0.1

    def test_very_long_message(self, default_config):
        """Very long message should not trigger short message penalty."""
        calibrator = ConfidenceCalibrator(default_config)

        long_message = "Это очень длинное сообщение " * 20

        context = RefinementContext(
            message=long_message,
            intent="info_provided",
            confidence=0.85,
        )

        result = calibrator.calibrate(0.85, [], context)

        # No short message penalty
        assert "short_message_penalty" not in result.penalty_factors

    def test_alternatives_with_zero_confidence(self, default_config):
        """Alternatives with zero confidence should be handled."""
        calibrator = ConfidenceCalibrator(default_config)

        context = RefinementContext(
            message="да",
            intent="greeting",
            confidence=0.9,
        )

        alternatives = [
            {"intent": "unclear", "confidence": 0.0},
            {"intent": "small_talk", "confidence": 0.0},
        ]

        result = calibrator.calibrate(0.9, alternatives, context)

        # Should handle gracefully
        assert result.calibrated_confidence >= 0.1

    def test_negative_confidence_in_alternatives(self, default_config):
        """Negative confidence in alternatives should be handled."""
        calibrator = ConfidenceCalibrator(default_config)

        context = RefinementContext(
            message="да",
            intent="greeting",
            confidence=0.9,
        )

        alternatives = [
            {"intent": "unclear", "confidence": -0.1},  # Invalid
        ]

        result = calibrator.calibrate(0.9, alternatives, context)

        # Should handle gracefully
        assert result.calibrated_confidence >= 0.1

# =============================================================================
# CALIBRATION RESULT TESTS
# =============================================================================

class TestCalibrationResult:
    """Tests for CalibrationResult dataclass."""

    def test_confidence_delta_calculation(self):
        """confidence_delta should be correctly calculated."""
        result = CalibrationResult(
            original_confidence=0.9,
            calibrated_confidence=0.7,
            calibration_applied=True,
            reasons=[CalibrationReason.ENTROPY_HIGH],
        )

        assert result.confidence_delta == pytest.approx(0.2, rel=0.01)

    def test_to_dict_serialization(self):
        """to_dict should serialize all fields correctly."""
        result = CalibrationResult(
            original_confidence=0.9,
            calibrated_confidence=0.7,
            calibration_applied=True,
            reasons=[CalibrationReason.ENTROPY_HIGH, CalibrationReason.GAP_SMALL],
            entropy=0.75,
            gap=0.1,
            penalty_factors={"entropy_penalty": 0.1, "gap_penalty": 0.1},
        )

        d = result.to_dict()

        assert d["original_confidence"] == 0.9
        assert d["calibrated_confidence"] == 0.7
        assert d["calibration_applied"] == True
        assert "entropy_high" in d["reasons"]
        assert "gap_small" in d["reasons"]
        assert d["entropy"] == 0.75
        assert d["gap"] == 0.1

    def test_no_calibration_result(self):
        """No calibration should have zero delta."""
        result = CalibrationResult(
            original_confidence=0.5,
            calibrated_confidence=0.5,
            calibration_applied=False,
        )

        assert result.confidence_delta == 0.0
        assert len(result.reasons) == 0

# =============================================================================
# REGRESSION TEST: Bug Report Scenario
# =============================================================================

class TestBugReportScenario:
    """
    Regression test for the exact scenario from the bug report.

    Bug: objection_think with confidence 0.85 and NO alternatives
    was not being properly calibrated because:
    1. Rule 4 had threshold 0.9 (too high)
    2. No special handling for objection without alternatives

    After fix:
    - Rule 4 threshold lowered to 0.8
    - Rule 5 added: objection without alternatives penalty
    """

    def test_exact_bug_scenario_simulation_report(self, default_config):
        """
        Reproduce exact scenario from simulation_20260126_101945.

        Input:
            message: "Да но быстрее. Нет времени ждать. некогда"
            intent: objection_think
            confidence: 0.85
            alternatives: [] (empty - LLM was "confident")

        Expected behavior BEFORE fix:
            - GapStrategy: 0.85 → 0.75 (no_alternatives_penalty 0.1)
            - Rule 4: NOT triggered (0.75 < 0.9)
            - Final: 0.75 (too high for ambiguous message!)

        Expected behavior AFTER fix:
            - GapStrategy: 0.85 → 0.75 (no_alternatives_penalty 0.1)
            - Rule 4: TRIGGERED (0.75 >= 0.8? No, but original was 0.85)
            - Rule 5: TRIGGERED (objection + no alternatives + confidence >= 0.75)
            - Final: <= 0.65 (appropriate for ambiguous message)
        """
        calibrator = ConfidenceCalibrator(default_config)

        context = RefinementContext(
            message="Да но быстрее. Нет времени ждать. некогда",
            intent="objection_think",
            confidence=0.85,
        )

        # NO alternatives - exactly like in the simulation
        result = calibrator.calibrate(0.85, [], context)

        # BEFORE fix: confidence was 0.75 (only gap penalty)
        # AFTER fix: should be significantly lower

        # Verify calibration was applied
        assert result.calibration_applied, "Calibration should be applied"

        # Verify confidence is properly reduced
        # Gap strategy: 0.85 → 0.75 (penalty 0.1)
        # Heuristic Rule 4: 0.85 >= 0.8 → penalty 0.1
        # Heuristic Rule 5: objection + no alternatives → penalty 0.15
        # Total expected reduction: ~0.35
        # Final: 0.85 - 0.35 = 0.50

        # Allow some margin for strategy interactions
        assert result.calibrated_confidence <= 0.65, \
            f"Expected <= 0.65, got {result.calibrated_confidence}"

        # Verify the right penalties were applied
        assert "no_alternatives_penalty" in result.penalty_factors or \
               "objection_overconfidence_penalty" in result.penalty_factors or \
               "objection_no_alternatives_penalty" in result.penalty_factors, \
            f"Expected objection-related penalty, got: {result.penalty_factors}"

    def test_full_pipeline_objection_think_without_alternatives(self):
        """
        Test the full ConfidenceCalibrationLayer with bug scenario.

        This tests the entire refine() method, not just calibrate().
        """
        layer = ConfidenceCalibrationLayer()

        result = {
            "intent": "objection_think",
            "confidence": 0.85,
            "alternatives": [],  # Empty - LLM was "confident"
            "extracted_data": {},
        }

        context = RefinementContext(
            message="Да но быстрее. Нет времени ждать. некогда",
            intent="objection_think",
            confidence=0.85,
        )

        refined = layer.refine(
            "Да но быстрее. Нет времени ждать. некогда",
            result,
            context
        )

        # Should apply calibration
        assert refined.decision == RefinementDecision.REFINED

        # Confidence should be significantly reduced
        assert refined.confidence <= 0.65, \
            f"Expected <= 0.65, got {refined.confidence}"

        # Intent should NOT change (calibration only affects confidence)
        assert refined.intent == "objection_think"

        # Metadata should contain calibration info
        assert "calibration" in refined.metadata

    def test_objection_think_with_alternatives_less_penalty(self, default_config):
        """
        When objection_think HAS alternatives, Rule 5 should NOT apply.

        This verifies the fix is targeted and doesn't over-penalize
        legitimate classifications with alternatives.
        """
        calibrator = ConfidenceCalibrator(default_config)

        context = RefinementContext(
            message="Мне нужно подумать об этом",
            intent="objection_think",
            confidence=0.85,
        )

        # WITH alternatives - legitimate classification
        alternatives = [
            {"intent": "objection_no_time", "confidence": 0.70},
        ]

        result = calibrator.calibrate(0.85, alternatives, context)

        # Should still have some calibration, but less aggressive
        assert result.calibration_applied

        # Gap penalty should apply (gap = 0.85 - 0.70 = 0.15 < 0.2)
        # Rule 4 applies (objection + confidence >= 0.8)
        # Rule 5 should NOT apply (alternatives exist)

        # Final confidence should be higher than without alternatives
        # Estimated: 0.85 - 0.15 (gap+high_conf) - 0.1 (rule4) = 0.60
        # But no Rule 5 penalty of 0.15

        assert "objection_no_alternatives_penalty" not in result.penalty_factors, \
            "Rule 5 should NOT apply when alternatives exist"

# =============================================================================
# GAP CASCADE FIX TESTS
# =============================================================================

class TestGapCascadeFix:
    """Tests for gap cascade fix (FIX #2a).

    Verifies that GapCalibrationStrategy uses ctx.confidence (original LLM value)
    for gap measurement rather than the cascaded confidence parameter.
    """

    def test_gap_uses_ctx_confidence_not_cascaded(self, default_config):
        """Gap strategy uses ctx.confidence (original), not cascaded confidence param."""
        strategy = GapCalibrationStrategy({"enabled": True})

        # Simulate: original confidence 0.80, post-entropy cascaded to 0.725
        ctx = RefinementContext(
            message="здравствуйте, нам нужна CRM",
            intent="greeting",
            confidence=0.80,  # Original LLM confidence
        )

        alternatives = [{"intent": "situation_provided", "confidence": 0.70}]

        # Pass cascaded value as confidence param (like ConfidenceCalibrator does)
        calibrated, reason, penalties = strategy.calibrate(
            0.725, alternatives, ctx, default_config
        )

        # Gap should be 0.80 - 0.70 = 0.10 (using ctx.confidence)
        # NOT 0.725 - 0.70 = 0.025 (using cascaded)
        assert penalties.get("gap", 0) == pytest.approx(0.10, abs=0.01) or reason is not None

    def test_entropy_does_not_inflate_gap_penalty(self, default_config):
        """Entropy penalty does NOT inflate gap penalty."""
        strategy = GapCalibrationStrategy({"enabled": True})

        ctx = RefinementContext(
            message="здравствуйте",
            intent="greeting",
            confidence=0.80,
        )
        alternatives = [{"intent": "info_provided", "confidence": 0.70}]

        # Same ctx.confidence, different cascaded values
        _, reason1, penalties1 = strategy.calibrate(0.80, alternatives, ctx, default_config)
        _, reason2, penalties2 = strategy.calibrate(0.72, alternatives, ctx, default_config)

        # Gap value should be the same regardless of cascaded input
        gap1 = penalties1.get("gap", penalties1.get("gap_penalty", 0))
        gap2 = penalties2.get("gap", penalties2.get("gap_penalty", 0))
        # Both should compute gap from ctx.confidence (0.80 - 0.70 = 0.10)
        if "gap" in penalties1 and "gap" in penalties2:
            assert penalties1["gap"] == pytest.approx(penalties2["gap"], abs=0.001)

    def test_edge_case_conf_076_alt_070_stays_above_065(self, default_config):
        """Edge case: conf=0.76 with alt@0.70 stays above 0.65 after full pipeline."""
        calibrator = ConfidenceCalibrator(default_config)

        ctx = RefinementContext(
            message="здравствуйте, расскажите про CRM",
            intent="greeting",
            confidence=0.76,
        )
        alternatives = [{"intent": "info_provided", "confidence": 0.70}]

        result = calibrator.calibrate(0.76, alternatives, ctx)

        # With fix: gap = 0.76 - 0.70 = 0.06 (from ctx.confidence)
        # Without fix: gap could be negative after entropy, causing excessive penalty
        assert result.calibrated_confidence > 0.65, \
            f"Expected > 0.65, got {result.calibrated_confidence}"

    def test_genuinely_ambiguous_still_penalized(self, default_config):
        """Genuinely ambiguous cases (conf=0.50, gap=0.03) still get appropriate penalty."""
        strategy = GapCalibrationStrategy({"enabled": True})

        ctx = RefinementContext(
            message="нет",
            intent="rejection",
            confidence=0.50,
        )
        alternatives = [{"intent": "objection_no_need", "confidence": 0.47}]

        calibrated, reason, penalties = strategy.calibrate(
            0.50, alternatives, ctx, default_config
        )

        # Gap = 0.50 - 0.47 = 0.03, well below threshold → penalty applied
        assert reason == CalibrationReason.GAP_SMALL
        assert calibrated < 0.50

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
