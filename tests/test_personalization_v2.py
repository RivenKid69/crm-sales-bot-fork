"""
Tests for Personalization v2 components.

Tests:
- AdaptiveStyleSelector: style selection based on behavioral signals
- IndustryDetectorV2: keyword and semantic industry detection
- EffectiveActionTracker: session memory for action effectiveness
- PersonalizationEngineV2: full personalization pipeline
"""

import pytest
from unittest.mock import MagicMock, patch

# Import components
from src.personalization.result import (
    StyleParameters,
    IndustryContext,
    BusinessContext,
    PersonalizationResult,
)
from src.personalization.style_selector import (
    AdaptiveStyleSelector,
    BehavioralSignals,
)
from src.personalization.industry_detector import (
    IndustryDetectorV2,
    IndustryDetectionResult,
)
from src.personalization.action_tracker import (
    EffectiveActionTracker,
    ActionOutcome,
)
from src.personalization.engine import PersonalizationEngineV2

# =============================================================================
# AdaptiveStyleSelector Tests
# =============================================================================

class TestAdaptiveStyleSelector:
    """Tests for AdaptiveStyleSelector."""

    def test_high_engagement_style(self):
        """High engagement should lead to assertive pitch and direct CTA."""
        selector = AdaptiveStyleSelector()
        signals = BehavioralSignals(
            engagement_level="high",
            engagement_score=0.8,
            momentum_direction="positive",
            frustration_level=0,
        )

        style = selector.select_style(signals)

        assert style.pitch_intensity == "assertive"
        assert style.cta_approach == "direct"
        assert style.verbosity == "normal"

    def test_low_engagement_style(self):
        """Low engagement should lead to concise verbosity and no CTA."""
        selector = AdaptiveStyleSelector()
        signals = BehavioralSignals(
            engagement_level="low",
            engagement_score=0.2,
            momentum_direction="neutral",
            frustration_level=0,
        )

        style = selector.select_style(signals)

        assert style.verbosity == "concise"
        assert style.cta_approach == "none"
        assert style.pitch_intensity == "soft"

    def test_high_frustration_empathy(self):
        """High frustration should trigger high empathy."""
        selector = AdaptiveStyleSelector()
        signals = BehavioralSignals(
            engagement_level="medium",
            frustration_level=7,
            momentum_direction="negative",
        )

        style = selector.select_style(signals)

        assert style.empathy_level == "high"
        assert "извинись" in style.style_instruction.lower() or "предложи" in style.style_instruction.lower()

    def test_positive_momentum_tactics(self):
        """Positive momentum should suggest next step."""
        selector = AdaptiveStyleSelector()
        signals = BehavioralSignals(
            engagement_level="medium",
            momentum=0.5,
            momentum_direction="positive",
            frustration_level=0,
        )

        style = selector.select_style(signals)

        assert style.question_style == "leading"
        assert "следующий шаг" in style.tactical_instruction.lower() or style.tactical_instruction == ""

    def test_negative_momentum_tactics(self):
        """Negative momentum should simplify approach."""
        selector = AdaptiveStyleSelector()
        signals = BehavioralSignals(
            engagement_level="medium",
            momentum=-0.5,
            momentum_direction="negative",
            frustration_level=2,
        )

        style = selector.select_style(signals)

        assert style.pitch_intensity == "soft"
        assert style.question_style == "closed"

    def test_breakthrough_window_cta(self):
        """Recent breakthrough should enable direct CTA."""
        selector = AdaptiveStyleSelector()
        signals = BehavioralSignals(
            engagement_level="medium",
            has_breakthrough=True,
            turns_since_breakthrough=2,
            frustration_level=0,
        )

        style = selector.select_style(signals)

        assert style.cta_approach == "direct"

    def test_stuck_pattern_offers_choices(self):
        """Stuck pattern should trigger offer choices."""
        selector = AdaptiveStyleSelector()
        signals = BehavioralSignals(
            engagement_level="low",
            is_stuck=True,
            frustration_level=3,
        )

        style = selector.select_style(signals)

        assert "вариант" in style.style_instruction.lower()

    def test_from_envelope_method(self):
        """Test creating signals from envelope-like object."""
        selector = AdaptiveStyleSelector()

        # Mock envelope
        envelope = MagicMock()
        envelope.engagement_level = "high"
        envelope.engagement_score = 0.9
        envelope.engagement_trend = "improving"
        envelope.momentum = 0.6
        envelope.momentum_direction = "positive"
        envelope.is_progressing = True
        envelope.is_regressing = False
        envelope.frustration_level = 0
        envelope.has_breakthrough = False
        envelope.turns_since_breakthrough = None
        envelope.is_stuck = False
        envelope.has_oscillation = False

        style = selector.select_style_from_envelope(envelope)

        assert style.pitch_intensity == "assertive"
        assert style.cta_approach == "direct"

# =============================================================================
# IndustryDetectorV2 Tests
# =============================================================================

class TestIndustryDetectorV2:
    """Tests for IndustryDetectorV2."""

    def test_keyword_detection_retail(self):
        """Detect retail from business_type keyword."""
        detector = IndustryDetectorV2()

        result = detector.detect(
            collected_data={"business_type": "магазин одежды"},
            messages=None,
        )

        assert result.industry == "retail"
        assert result.confidence > 0.5
        assert result.method == "keyword"

    def test_keyword_detection_services(self):
        """Detect services from business_type keyword."""
        detector = IndustryDetectorV2()

        result = detector.detect(
            collected_data={"business_type": "салон красоты"},
            messages=None,
        )

        assert result.industry == "services"
        assert result.confidence > 0.5

    def test_keyword_detection_horeca(self):
        """Detect horeca from business_type keyword."""
        detector = IndustryDetectorV2()

        result = detector.detect(
            collected_data={"business_type": "ресторан"},
            messages=None,
        )

        assert result.industry == "horeca"

    def test_keyword_detection_b2b(self):
        """Detect b2b from business_type keyword."""
        detector = IndustryDetectorV2()

        result = detector.detect(
            collected_data={"business_type": "оптовая торговля"},
            messages=None,
        )

        assert result.industry == "b2b"

    def test_keyword_detection_from_pain(self):
        """Detect industry from pain_point."""
        detector = IndustryDetectorV2()

        result = detector.detect(
            collected_data={
                "business_type": "компания",
                "pain_point": "пересортица и недостачи",
            },
            messages=None,
        )

        assert result.industry == "retail"

    def test_no_detection_unknown_business(self):
        """No detection for unknown business type."""
        detector = IndustryDetectorV2()

        result = detector.detect(
            collected_data={"business_type": "что-то непонятное"},
            messages=None,
        )

        assert result.industry is None or result.confidence < 0.3

    def test_get_industry_context(self):
        """Get context for detected industry."""
        detector = IndustryDetectorV2()

        context = detector.get_industry_context("retail")

        assert "магазин" in context["keywords"] or "розница" in context["keywords"]
        assert len(context["pain_examples"]) > 0

    def test_confidence_accumulation(self):
        """Confidence should increase with repeated detection."""
        detector = IndustryDetectorV2()

        # First detection
        result1 = detector.detect(
            collected_data={"business_type": "магазин"},
            previous_confidence=0.0,
            previous_industry=None,
        )

        # Second detection with same industry
        result2 = detector.detect(
            collected_data={"business_type": "розничная торговля"},
            previous_confidence=result1.confidence,
            previous_industry=result1.industry,
        )

        # Confidence should be at least as high
        assert result2.confidence >= result1.confidence

# =============================================================================
# EffectiveActionTracker Tests
# =============================================================================

class TestEffectiveActionTracker:
    """Tests for EffectiveActionTracker."""

    def test_record_success(self):
        """Record successful action outcome."""
        tracker = EffectiveActionTracker()

        tracker.record_outcome(
            action="spin_problem",
            turn_type="PROGRESS",
            intent="pain_shared",
        )

        stats = tracker.get_action_stats()
        assert "spin_problem" in stats
        assert stats["spin_problem"]["successes"] == 1

    def test_record_failure(self):
        """Record failed action outcome."""
        tracker = EffectiveActionTracker()

        tracker.record_outcome(
            action="spin_problem",
            turn_type="REGRESS",
            intent="objection_price",
        )

        stats = tracker.get_action_stats()
        assert stats["spin_problem"]["successes"] == 0
        assert stats["spin_problem"]["attempts"] == 1

    def test_effective_actions_threshold(self):
        """Actions with >50% success rate are effective."""
        tracker = EffectiveActionTracker()

        # 3 successes, 1 failure = 75% success rate
        for _ in range(3):
            tracker.record_outcome("spin_problem", "PROGRESS", "positive")
        tracker.record_outcome("spin_problem", "REGRESS", "objection")

        effective = tracker.get_effective_actions()
        assert "spin_problem" in effective

    def test_ineffective_actions_threshold(self):
        """Actions with <30% success rate are ineffective."""
        tracker = EffectiveActionTracker()

        # 0 successes, 3 failures = 0% success rate
        for _ in range(3):
            tracker.record_outcome("deflect", "REGRESS", "objection")

        ineffective = tracker.get_ineffective_actions()
        assert "deflect" in ineffective

    def test_tactical_recommendation(self):
        """Generate tactical recommendation from stats."""
        tracker = EffectiveActionTracker()

        # Make spin_problem effective
        for _ in range(3):
            tracker.record_outcome("spin_problem", "PROGRESS", "positive")

        # Make deflect ineffective
        for _ in range(3):
            tracker.record_outcome("deflect", "REGRESS", "objection")

        recommendation = tracker.get_tactical_recommendation()

        assert "эффективно" in recommendation.lower() or "избегай" in recommendation.lower()

    def test_reset(self):
        """Reset clears all stats."""
        tracker = EffectiveActionTracker()

        tracker.record_outcome("test", "PROGRESS", "positive")
        tracker.reset()

        assert tracker.total_turns == 0
        assert len(tracker.get_action_stats()) == 0

    def test_overall_success_rate(self):
        """Calculate overall success rate."""
        tracker = EffectiveActionTracker()

        tracker.record_outcome("action1", "PROGRESS", "positive")
        tracker.record_outcome("action1", "PROGRESS", "positive")
        tracker.record_outcome("action2", "REGRESS", "objection")
        tracker.record_outcome("action2", "REGRESS", "objection")

        # 2 successes out of 4 = 50%
        assert tracker.overall_success_rate == 0.5

# =============================================================================
# PersonalizationEngineV2 Tests
# =============================================================================

class TestPersonalizationEngineV2:
    """Tests for PersonalizationEngineV2."""

    def test_full_personalization(self):
        """Test full personalization pipeline."""
        engine = PersonalizationEngineV2()

        # Mock envelope
        envelope = MagicMock()
        envelope.engagement_level = "high"
        envelope.engagement_score = 0.8
        envelope.engagement_trend = "improving"
        envelope.momentum = 0.5
        envelope.momentum_direction = "positive"
        envelope.is_progressing = True
        envelope.is_regressing = False
        envelope.frustration_level = 0
        envelope.has_breakthrough = False
        envelope.turns_since_breakthrough = None
        envelope.is_stuck = False
        envelope.has_oscillation = False

        collected_data = {
            "business_type": "магазин",
            "company_size": 10,
            "pain_point": "потеря клиентов",
        }

        # Mock action tracker
        tracker = MagicMock()
        tracker.get_effective_actions.return_value = ["spin_problem"]
        tracker.get_ineffective_actions.return_value = []
        tracker.get_tactical_recommendation.return_value = "Эффективно: вопросы о проблемах"

        with patch("src.personalization.engine.flags") as mock_flags:
            mock_flags.personalization_v2 = True
            mock_flags.personalization_adaptive_style = True
            mock_flags.personalization_semantic_industry = False
            mock_flags.personalization_session_memory = True

            result = engine.personalize(
                envelope=envelope,
                collected_data=collected_data,
                action_tracker=tracker,
            )

        assert result.personalization_applied
        assert result.industry_context.industry == "retail"
        assert result.business_context.size_category == "small"
        assert result.style.pitch_intensity == "assertive"

    def test_prompt_variables(self):
        """Test conversion to prompt variables."""
        result = PersonalizationResult(
            personalization_applied=True,
            style=StyleParameters(
                verbosity="normal",
                style_instruction="Be empathetic",
                tactical_instruction="Suggest next step",
            ),
            industry_context=IndustryContext(
                industry="retail",
                confidence=0.8,
                pain_examples=["пересортица", "недостачи"],
            ),
            business_context=BusinessContext(
                size_category="small",
                size_label="растущая команда",
                value_prop="видите работу каждого",
            ),
            effective_actions_hint="Эффективно: spin_problem",
        )

        variables = result.to_prompt_variables()

        assert "adaptive_style_instruction" in variables
        assert variables["industry"] == "retail"
        assert variables["bc_size_label"] == "растущая команда"
        assert variables["bc_value_prop"] == "видите работу каждого"
        assert "пересортица" in variables["ic_pain_examples"]

    def test_legacy_objection_counter(self):
        """Test legacy get_objection_counter method."""
        counter = PersonalizationEngineV2.get_objection_counter(
            collected_data={"company_size": 5},
            objection_type="price",
        )

        assert counter  # Should return some counter
        assert isinstance(counter, str)

    def test_business_context_by_size(self):
        """Test business context selection by company size."""
        engine = PersonalizationEngineV2()

        # Micro (1-5)
        result_micro = engine._build_business_context({"company_size": 3})
        assert result_micro.size_category == "micro"
        assert "небольшая" in result_micro.size_label.lower()

        # Small (6-15)
        result_small = engine._build_business_context({"company_size": 10})
        assert result_small.size_category == "small"

        # Medium (16-50)
        result_medium = engine._build_business_context({"company_size": 30})
        assert result_medium.size_category == "medium"

        # Large (50+)
        result_large = engine._build_business_context({"company_size": 100})
        assert result_large.size_category == "large"

    def test_reset(self):
        """Test engine reset."""
        engine = PersonalizationEngineV2()
        engine._industry_cache = {"industry": "retail", "confidence": 0.8}

        engine.reset()

        assert engine._industry_cache["industry"] is None
        assert engine._industry_cache["confidence"] == 0.0

# =============================================================================
# Integration Tests
# =============================================================================

class TestPersonalizationIntegration:
    """Integration tests for personalization components."""

    def test_style_affects_result(self):
        """Style from selector should affect final result."""
        engine = PersonalizationEngineV2()

        # High frustration envelope
        envelope = MagicMock()
        envelope.engagement_level = "low"
        envelope.engagement_score = 0.2
        envelope.engagement_trend = "declining"
        envelope.momentum = -0.5
        envelope.momentum_direction = "negative"
        envelope.is_progressing = False
        envelope.is_regressing = True
        envelope.frustration_level = 8
        envelope.has_breakthrough = False
        envelope.turns_since_breakthrough = None
        envelope.is_stuck = True
        envelope.has_oscillation = False

        with patch("src.personalization.engine.flags") as mock_flags:
            mock_flags.personalization_v2 = True
            mock_flags.personalization_adaptive_style = True
            mock_flags.personalization_semantic_industry = False
            mock_flags.personalization_session_memory = False

            result = engine.personalize(
                envelope=envelope,
                collected_data={},
            )

        # High frustration should lead to high empathy
        assert result.style.empathy_level == "high"
        # Low engagement should lead to concise
        assert result.style.verbosity == "concise"

    def test_industry_in_result(self):
        """Detected industry should appear in result."""
        engine = PersonalizationEngineV2()

        with patch("src.personalization.engine.flags") as mock_flags:
            mock_flags.personalization_v2 = True
            mock_flags.personalization_adaptive_style = False
            mock_flags.personalization_semantic_industry = False
            mock_flags.personalization_session_memory = False

            result = engine.personalize(
                envelope=None,
                collected_data={"business_type": "ресторан"},
            )

        assert result.industry_context.industry == "horeca"
        assert "заказы" in result.industry_context.pain_examples or "очереди" in result.industry_context.pain_examples
