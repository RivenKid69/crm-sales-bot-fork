"""
Comprehensive Tests for Frustration Intensity Calculator.

This test suite verifies:
1. Intensity-based frustration calculation
2. Signal count multipliers
3. Consecutive turn bonus
4. Pre-intervention logic
5. Urgency levels
6. Integration with FrustrationTracker
7. Integration with RegexToneAnalyzer
8. YAML configuration loading

Part of the fix for: Guard Check doesn't intervene at high frustration
Root cause: Only ONE signal per tone counted, RUSHED weight too low (1)
Solution: Intensity-based calculation, RUSHED weight increased to 2
"""

import pytest
from unittest.mock import MagicMock, patch

class TestFrustrationIntensityCalculator:
    """Test FrustrationIntensityCalculator core functionality."""

    def test_import(self):
        """Test module imports correctly."""
        from src.tone_analyzer.frustration_intensity import (
            FrustrationIntensityCalculator,
            IntensityConfig,
            IFrustrationIntensityCalculator,
            FrustrationIntensityRegistry,
        )
        assert FrustrationIntensityCalculator is not None

    def test_default_config(self):
        """Test default configuration values."""
        from src.tone_analyzer.frustration_intensity import IntensityConfig

        config = IntensityConfig()

        # Base weights
        assert config.base_weights["frustrated"] == 3
        assert config.base_weights["rushed"] == 2  # Updated from 1
        assert config.base_weights["skeptical"] == 1
        assert config.base_weights["confused"] == 1

        # Intensity multipliers
        assert config.intensity_multipliers[1] == 1.0
        assert config.intensity_multipliers[2] == 1.5
        assert config.intensity_multipliers[3] == 2.0

        # Consecutive turn settings
        assert config.consecutive_turn_multiplier == 1.2
        assert config.consecutive_turn_threshold == 2

    def test_calculate_single_signal(self):
        """Test calculation with single signal (no intensity multiplier)."""
        from src.tone_analyzer.frustration_intensity import FrustrationIntensityCalculator
        from src.tone_analyzer.models import Tone

        calculator = FrustrationIntensityCalculator()

        # Single RUSHED signal = base weight (2) * 1.0 = 2
        delta = calculator.calculate(Tone.RUSHED, signal_count=1)
        assert delta == 2

        # Single FRUSTRATED signal = base weight (3) * 1.0 = 3
        calculator2 = FrustrationIntensityCalculator()
        delta2 = calculator2.calculate(Tone.FRUSTRATED, signal_count=1)
        assert delta2 == 3

    def test_calculate_multiple_signals_intensity(self):
        """Test calculation with multiple signals (intensity multiplier)."""
        from src.tone_analyzer.frustration_intensity import FrustrationIntensityCalculator
        from src.tone_analyzer.models import Tone

        calculator = FrustrationIntensityCalculator()

        # 2 RUSHED signals = base weight (2) * 1.5 = 3
        delta = calculator.calculate(Tone.RUSHED, signal_count=2)
        assert delta == 3

        # 3 RUSHED signals = base weight (2) * 2.0 = 4
        calculator2 = FrustrationIntensityCalculator()
        delta2 = calculator2.calculate(Tone.RUSHED, signal_count=3)
        assert delta2 == 4

    def test_original_bug_scenario(self):
        """
        Test the original bug scenario.

        Original bug:
        - "быстрее, не тяни, некогда" (3 RUSHED signals) = +1 per turn
        - After 4 turns: frustration = 4
        - Threshold = 7, so 4 < 7 = no intervention

        Fixed:
        - 3 RUSHED signals = base(2) * intensity(2.0) = +4 per turn
        - After 2 turns: frustration = 8
        - Threshold = 7, so 8 >= 7 = intervention triggered!
        """
        from src.tone_analyzer.frustration_intensity import FrustrationIntensityCalculator
        from src.tone_analyzer.models import Tone
        from src.frustration_thresholds import FRUSTRATION_HIGH

        calculator = FrustrationIntensityCalculator()

        # Simulate 2 turns of "быстрее, не тяни, некогда" (3 RUSHED signals each)
        turn1_delta = calculator.calculate(Tone.RUSHED, signal_count=3)
        turn2_delta = calculator.calculate(Tone.RUSHED, signal_count=3)

        # With consecutive turn bonus (1.2x on turn 2):
        # Turn 1: 2 * 2.0 = 4
        # Turn 2: 2 * 2.0 * 1.2 = 4.8 -> 4 (int)
        total_frustration = turn1_delta + turn2_delta

        # Should exceed HIGH threshold (7)
        assert total_frustration >= FRUSTRATION_HIGH, (
            f"Total frustration {total_frustration} should be >= {FRUSTRATION_HIGH}"
        )

    def test_consecutive_turn_multiplier(self):
        """Test consecutive turn multiplier for repeated negative tones."""
        from src.tone_analyzer.frustration_intensity import FrustrationIntensityCalculator
        from src.tone_analyzer.models import Tone

        calculator = FrustrationIntensityCalculator()

        # Turn 1: no consecutive bonus
        delta1 = calculator.calculate(Tone.FRUSTRATED, signal_count=1)
        assert delta1 == 3  # base weight

        # Turn 2: still no bonus (need 2+ consecutive)
        delta2 = calculator.calculate(Tone.FRUSTRATED, signal_count=1)
        assert delta2 == 3

        # Turn 3: consecutive bonus kicks in (1.2x)
        delta3 = calculator.calculate(Tone.FRUSTRATED, signal_count=1)
        expected = int(3 * 1.2)  # 3.6 -> 3
        assert delta3 >= 3  # At least base weight

    def test_decay_for_positive_tones(self):
        """Test frustration decay for positive tones."""
        from src.tone_analyzer.frustration_intensity import FrustrationIntensityCalculator
        from src.tone_analyzer.models import Tone

        calculator = FrustrationIntensityCalculator()

        # POSITIVE tone should decrease frustration
        delta = calculator.calculate(Tone.POSITIVE, signal_count=1)
        assert delta < 0  # Negative delta = decay

        # INTERESTED tone should decrease frustration
        calculator2 = FrustrationIntensityCalculator()
        delta2 = calculator2.calculate(Tone.INTERESTED, signal_count=1)
        assert delta2 < 0

    def test_should_pre_intervene_rushed_high_intensity(self):
        """Test pre-intervention for RUSHED with high intensity."""
        from src.tone_analyzer.frustration_intensity import FrustrationIntensityCalculator
        from src.tone_analyzer.models import Tone

        calculator = FrustrationIntensityCalculator()

        # RUSHED with 2+ signals should trigger pre-intervention
        assert calculator.should_pre_intervene(Tone.RUSHED, signal_count=2, current_frustration=0)
        assert calculator.should_pre_intervene(Tone.RUSHED, signal_count=3, current_frustration=0)

        # RUSHED with 1 signal should NOT trigger pre-intervention
        assert not calculator.should_pre_intervene(Tone.RUSHED, signal_count=1, current_frustration=0)

    def test_should_pre_intervene_warning_level(self):
        """Test pre-intervention at WARNING level."""
        from src.tone_analyzer.frustration_intensity import FrustrationIntensityCalculator
        from src.tone_analyzer.models import Tone
        from src.frustration_thresholds import FRUSTRATION_WARNING

        calculator = FrustrationIntensityCalculator()

        # At WARNING level with any negative tone should trigger
        assert calculator.should_pre_intervene(
            Tone.FRUSTRATED, signal_count=1, current_frustration=FRUSTRATION_WARNING
        )
        assert calculator.should_pre_intervene(
            Tone.SKEPTICAL, signal_count=1, current_frustration=FRUSTRATION_WARNING
        )

        # Below WARNING should NOT trigger (unless RUSHED with high intensity)
        assert not calculator.should_pre_intervene(
            Tone.FRUSTRATED, signal_count=1, current_frustration=FRUSTRATION_WARNING - 1
        )

    def test_get_intervention_urgency(self):
        """Test intervention urgency levels."""
        from src.tone_analyzer.frustration_intensity import FrustrationIntensityCalculator
        from src.tone_analyzer.models import Tone
        from src.frustration_thresholds import (
            FRUSTRATION_ELEVATED,
            FRUSTRATION_WARNING,
            FRUSTRATION_HIGH,
            FRUSTRATION_CRITICAL,
        )

        calculator = FrustrationIntensityCalculator()

        # Critical frustration = critical urgency
        assert calculator.get_intervention_urgency(Tone.NEUTRAL, 1, FRUSTRATION_CRITICAL) == "critical"

        # High frustration = high urgency
        assert calculator.get_intervention_urgency(Tone.NEUTRAL, 1, FRUSTRATION_HIGH) == "high"

        # RUSHED with 3 signals = high urgency even at low frustration
        assert calculator.get_intervention_urgency(Tone.RUSHED, 3, 0) == "high"

        # WARNING level = medium urgency
        assert calculator.get_intervention_urgency(Tone.NEUTRAL, 1, FRUSTRATION_WARNING) == "medium"

        # Low frustration = none
        assert calculator.get_intervention_urgency(Tone.NEUTRAL, 1, 0) == "none"

class TestFrustrationTrackerIntensity:
    """Test FrustrationTracker with intensity-based updates."""

    def test_update_with_signal_count(self):
        """Test update with signal count parameter."""
        from src.tone_analyzer.frustration_tracker import FrustrationTracker
        from src.tone_analyzer.models import Tone

        tracker = FrustrationTracker()

        # Update with 3 signals should use intensity calculation
        old_level = tracker.level
        tracker.update(Tone.RUSHED, signal_count=3)

        # Should increase significantly (intensity-based)
        assert tracker.level > old_level + 1  # More than single signal

    def test_pre_intervention_triggered(self):
        """Test pre_intervention_triggered property."""
        from src.tone_analyzer.frustration_tracker import FrustrationTracker
        from src.tone_analyzer.models import Tone

        tracker = FrustrationTracker()

        # Initially not triggered
        assert not tracker.pre_intervention_triggered

        # RUSHED with high intensity should trigger pre-intervention
        tracker.update(Tone.RUSHED, signal_count=3)
        assert tracker.pre_intervention_triggered

    def test_should_offer_exit(self):
        """Test should_offer_exit method."""
        from src.tone_analyzer.frustration_tracker import FrustrationTracker
        from src.tone_analyzer.models import Tone

        tracker = FrustrationTracker()

        # Initially should not offer exit
        assert not tracker.should_offer_exit()

        # After RUSHED with high intensity = should offer exit
        tracker.update(Tone.RUSHED, signal_count=3)
        assert tracker.should_offer_exit()

    def test_get_intervention_urgency(self):
        """Test get_intervention_urgency method."""
        from src.tone_analyzer.frustration_tracker import FrustrationTracker
        from src.tone_analyzer.models import Tone

        tracker = FrustrationTracker()

        # Initially none
        assert tracker.get_intervention_urgency() == "none"

        # After FRUSTRATED = increases urgency
        tracker.update(Tone.FRUSTRATED, signal_count=3)
        urgency = tracker.get_intervention_urgency()
        assert urgency in ["low", "medium", "high", "critical"]

    def test_backward_compatibility_single_signal(self):
        """Test backward compatibility with single signal (default)."""
        from src.tone_analyzer.frustration_tracker import FrustrationTracker
        from src.tone_analyzer.models import Tone

        tracker = FrustrationTracker()

        # Update without signal_count should use default (1)
        tracker.update(Tone.FRUSTRATED)

        # Should increase by base weight (3 for FRUSTRATED)
        assert tracker.level == 3

    def test_reset_clears_all_state(self):
        """Test reset clears all state including intensity tracking."""
        from src.tone_analyzer.frustration_tracker import FrustrationTracker
        from src.tone_analyzer.models import Tone

        tracker = FrustrationTracker()

        # Build up state
        tracker.update(Tone.RUSHED, signal_count=3)
        tracker.update(Tone.FRUSTRATED, signal_count=2)

        # Reset
        tracker.reset()

        # All state should be cleared
        assert tracker.level == 0
        assert not tracker.pre_intervention_triggered
        assert tracker.consecutive_negative_turns == 0
        assert len(tracker.history) == 0

class TestRegexToneAnalyzerIntensity:
    """Test RegexToneAnalyzer with intensity-based updates."""

    def test_counts_all_signals(self):
        """Test that analyzer counts ALL signals, not just one per tone."""
        from src.tone_analyzer.regex_analyzer import RegexToneAnalyzer

        analyzer = RegexToneAnalyzer()

        # Message with multiple RUSHED signals
        result = analyzer.analyze("быстрее, не тяни, некогда")

        # Should have multiple signals counted
        rushed_signals = [s for s in result.signals if "rushed" in s.lower()]
        assert len(rushed_signals) >= 2, f"Expected 2+ RUSHED signals, got {len(rushed_signals)}"

    def test_analysis_includes_intensity_fields(self):
        """Test that ToneAnalysis includes intensity-based fields."""
        from src.tone_analyzer.regex_analyzer import RegexToneAnalyzer

        analyzer = RegexToneAnalyzer()
        result = analyzer.analyze("быстрее, не тяни, некогда")

        # Should have intensity-based fields
        assert hasattr(result, 'signal_count')
        assert hasattr(result, 'pre_intervention_triggered')
        assert hasattr(result, 'intervention_urgency')
        assert hasattr(result, 'should_offer_exit')

    def test_rushed_high_intensity_triggers_pre_intervention(self):
        """Test RUSHED with high intensity triggers pre-intervention."""
        from src.tone_analyzer.regex_analyzer import RegexToneAnalyzer

        analyzer = RegexToneAnalyzer()
        result = analyzer.analyze("быстрее, не тяни, некогда, времени нет")

        # Should trigger pre-intervention
        assert result.pre_intervention_triggered or result.should_offer_exit

    def test_response_guidance_includes_urgency(self):
        """Test response guidance includes urgency-based recommendations."""
        from src.tone_analyzer.regex_analyzer import RegexToneAnalyzer

        analyzer = RegexToneAnalyzer()
        result = analyzer.analyze("быстрее, не тяни, некогда")
        guidance = analyzer.get_response_guidance(result)

        # Should have urgency-based guidance
        assert "intervention_urgency" in guidance
        assert "pre_intervention_triggered" in guidance

    def test_response_guidance_shortens_for_rushed(self):
        """Test response guidance shortens responses for RUSHED users."""
        from src.tone_analyzer.regex_analyzer import RegexToneAnalyzer

        analyzer = RegexToneAnalyzer()
        result = analyzer.analyze("быстрее")
        guidance = analyzer.get_response_guidance(result)

        # RUSHED should get shorter max_words
        assert guidance["max_words"] <= 35

class TestYAMLConfiguration:
    """Test YAML configuration loading."""

    def test_intensity_config_loaded(self):
        """Test intensity config loads from YAML."""
        from src.yaml_config.constants import FRUSTRATION_INTENSITY_CONFIG

        assert FRUSTRATION_INTENSITY_CONFIG is not None
        assert "base_weights" in FRUSTRATION_INTENSITY_CONFIG
        assert "intensity_multipliers" in FRUSTRATION_INTENSITY_CONFIG

    def test_rushed_weight_updated(self):
        """Test RUSHED weight is updated from 1 to 2."""
        from src.yaml_config.constants import FRUSTRATION_WEIGHTS

        # Base weights should have RUSHED at 2
        assert FRUSTRATION_WEIGHTS.get("rushed", 1) == 2

    def test_intensity_multipliers_configured(self):
        """Test intensity multipliers are configured."""
        from src.yaml_config.constants import FRUSTRATION_INTENSITY_CONFIG

        multipliers = FRUSTRATION_INTENSITY_CONFIG.get("intensity_multipliers", {})

        # Should have multipliers for 1, 2, 3+ signals
        assert 1 in multipliers or "1" in multipliers
        assert 2 in multipliers or "2" in multipliers
        assert 3 in multipliers or "3" in multipliers

class TestIntegrationScenarios:
    """Integration tests for complete frustration handling flow."""

    def test_rushed_user_gets_fast_intervention(self):
        """
        Test that RUSHED user gets intervention faster.

        Scenario:
        - User says "быстрее, не тяни, некогда" (3 RUSHED signals)
        - With intensity calculation: +4 per turn
        - After 2 turns: frustration = 8
        - Threshold = 7, so intervention should trigger
        """
        from src.tone_analyzer.regex_analyzer import RegexToneAnalyzer
        from src.frustration_thresholds import FRUSTRATION_HIGH

        analyzer = RegexToneAnalyzer()

        # Turn 1
        result1 = analyzer.analyze("быстрее, не тяни, некогда")

        # Turn 2
        result2 = analyzer.analyze("быстрее, давай уже")

        # Should reach HIGH threshold after 2 turns
        assert result2.frustration_level >= FRUSTRATION_HIGH - 2, (
            f"Frustration {result2.frustration_level} should be near HIGH threshold {FRUSTRATION_HIGH}"
        )

        # Or pre-intervention should be triggered
        assert result1.pre_intervention_triggered or result2.pre_intervention_triggered

    def test_single_rushed_signal_doesnt_over_escalate(self):
        """Test single RUSHED signal doesn't over-escalate."""
        from src.tone_analyzer.regex_analyzer import RegexToneAnalyzer
        from src.frustration_thresholds import FRUSTRATION_WARNING

        analyzer = RegexToneAnalyzer()

        # Single "быстрее" = 1 signal
        result = analyzer.analyze("быстрее")

        # Should not immediately trigger warning
        assert result.frustration_level < FRUSTRATION_WARNING

        # Should not offer exit for single signal
        assert not result.should_offer_exit

    def test_positive_tone_reduces_frustration(self):
        """Test positive tone reduces accumulated frustration."""
        from src.tone_analyzer.regex_analyzer import RegexToneAnalyzer

        analyzer = RegexToneAnalyzer()

        # Build up frustration
        analyzer.analyze("быстрее, не тяни, некогда")
        high_level = analyzer.get_frustration_level()

        # Positive response
        result = analyzer.analyze("отлично, супер!")

        # Should reduce frustration
        assert result.frustration_level < high_level

    def test_old_bug_no_longer_occurs(self):
        """
        Verify the original bug no longer occurs.

        Original bug:
        - 4 turns of "быстрее, не тяни, некогда"
        - frustration_level: 5 (max reached was 5)
        - intervention_triggered: false

        After fix:
        - 2 turns should be enough to trigger intervention
        """
        from src.tone_analyzer.regex_analyzer import RegexToneAnalyzer
        from src.frustration_thresholds import FRUSTRATION_HIGH

        analyzer = RegexToneAnalyzer()

        # Simulate the bug scenario - 4 turns
        for _ in range(4):
            result = analyzer.analyze("быстрее, не тяни, некогда")

        # Should now reach HIGH threshold
        assert result.frustration_level >= FRUSTRATION_HIGH, (
            f"After 4 turns of explicit frustration, level {result.frustration_level} "
            f"should be >= HIGH threshold {FRUSTRATION_HIGH}"
        )

        # Or pre-intervention should have been triggered earlier
        assert result.pre_intervention_triggered or result.should_offer_exit

class TestToneAnalysisModel:
    """Test ToneAnalysis model with new fields."""

    def test_new_fields_exist(self):
        """Test ToneAnalysis has new intensity-based fields."""
        from src.tone_analyzer.models import ToneAnalysis, Tone, Style

        analysis = ToneAnalysis(
            tone=Tone.RUSHED,
            style=Style.INFORMAL,
            confidence=0.9,
            frustration_level=5,
        )

        # New fields should have defaults
        assert hasattr(analysis, 'signal_count')
        assert hasattr(analysis, 'pre_intervention_triggered')
        assert hasattr(analysis, 'intervention_urgency')
        assert hasattr(analysis, 'should_offer_exit')
        assert hasattr(analysis, 'consecutive_negative_turns')

    def test_new_fields_defaults(self):
        """Test default values for new fields."""
        from src.tone_analyzer.models import ToneAnalysis, Tone, Style

        analysis = ToneAnalysis(
            tone=Tone.NEUTRAL,
            style=Style.FORMAL,
            confidence=0.5,
            frustration_level=0,
        )

        assert analysis.signal_count == 1
        assert analysis.pre_intervention_triggered is False
        assert analysis.intervention_urgency == "none"
        assert analysis.should_offer_exit is False
        assert analysis.consecutive_negative_turns == 0

class TestRegistry:
    """Test FrustrationIntensityRegistry."""

    def test_default_registered(self):
        """Test default calculator is registered."""
        from src.tone_analyzer.frustration_intensity import FrustrationIntensityRegistry

        calculator = FrustrationIntensityRegistry.get()
        assert calculator is not None

    def test_list_registered(self):
        """Test list_registered returns registered calculators."""
        from src.tone_analyzer.frustration_intensity import FrustrationIntensityRegistry

        registered = FrustrationIntensityRegistry.list_registered()
        assert "default" in registered

    def test_register_custom(self):
        """Test registering custom calculator."""
        from src.tone_analyzer.frustration_intensity import (
            FrustrationIntensityRegistry,
            FrustrationIntensityCalculator,
        )

        class CustomCalculator(FrustrationIntensityCalculator):
            pass

        FrustrationIntensityRegistry.register("custom", CustomCalculator)
        assert "custom" in FrustrationIntensityRegistry.list_registered()

class TestConvenienceFunctions:
    """Test convenience functions."""

    def test_calculate_frustration_delta(self):
        """Test calculate_frustration_delta function."""
        from src.tone_analyzer.frustration_intensity import calculate_frustration_delta
        from src.tone_analyzer.models import Tone

        delta = calculate_frustration_delta(Tone.RUSHED, signal_count=3)
        assert delta > 0

    def test_should_pre_intervene(self):
        """Test should_pre_intervene function."""
        from src.tone_analyzer.frustration_intensity import should_pre_intervene
        from src.tone_analyzer.models import Tone

        result = should_pre_intervene(Tone.RUSHED, signal_count=3, current_frustration=0)
        assert result is True

    def test_get_intervention_urgency(self):
        """Test get_intervention_urgency function."""
        from src.tone_analyzer.frustration_intensity import get_intervention_urgency
        from src.tone_analyzer.models import Tone

        urgency = get_intervention_urgency(Tone.RUSHED, signal_count=3, current_frustration=0)
        assert urgency == "high"
