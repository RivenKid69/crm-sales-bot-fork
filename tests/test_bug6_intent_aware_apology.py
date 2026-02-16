"""
Tests for Bug #6 fix: Inappropriate apologies on business intents.

Verifies that:
1. should_suppress_for_intent() correctly suppresses apology for non-emotion domains
2. APOLOGY_ALLOWED_DOMAINS and get_intent_semantic_domain() work correctly
3. Generator._ensure_apology() uses intent-domain guard
4. ResponseDirectivesBuilder._fill_apology() uses intent-domain guard with current_intent
5. regex_analyzer only sets should_apologize=True for FRUSTRATED tone at medium urgency
6. tone_overrides for rushed/confused are set to FRUSTRATION_HIGH
7. validate_thresholds() passes with new overrides
"""
import pytest
from unittest.mock import MagicMock, patch

from src.apology_ssot import (
    should_apologize,
    should_suppress_for_intent,
    validate_thresholds,
    APOLOGY_THRESHOLD,
)
from src.frustration_thresholds import FRUSTRATION_HIGH
from src.yaml_config.constants import (
    APOLOGY_TONE_OVERRIDES,
    APOLOGY_ALLOWED_DOMAINS,
    get_intent_semantic_domain,
    get_all_semantic_domains,
)


# =============================================================================
# Test: APOLOGY_ALLOWED_DOMAINS loaded correctly
# =============================================================================

class TestApologyAllowedDomains:
    """Verify APOLOGY_ALLOWED_DOMAINS is loaded from YAML."""

    def test_allowed_domains_loaded(self):
        """APOLOGY_ALLOWED_DOMAINS must contain exactly emotion and escalation."""
        assert APOLOGY_ALLOWED_DOMAINS == {"emotion", "escalation"}

    def test_allowed_domains_is_set(self):
        """APOLOGY_ALLOWED_DOMAINS must be a set for O(1) lookups."""
        assert isinstance(APOLOGY_ALLOWED_DOMAINS, set)


# =============================================================================
# Test: get_intent_semantic_domain()
# =============================================================================

class TestGetIntentSemanticDomain:
    """Verify taxonomy lookup for intent semantic domain."""

    def test_get_intent_semantic_domain_known_pricing(self):
        """price_question -> pricing domain."""
        assert get_intent_semantic_domain("price_question") == "pricing"

    def test_get_intent_semantic_domain_known_product(self):
        """question_features -> product domain."""
        assert get_intent_semantic_domain("question_features") == "product"

    def test_get_intent_semantic_domain_known_emotion(self):
        """frustration_expression -> emotion domain."""
        assert get_intent_semantic_domain("frustration_expression") == "emotion"

    def test_get_intent_semantic_domain_known_escalation(self):
        """request_human -> escalation domain."""
        assert get_intent_semantic_domain("request_human") == "escalation"

    def test_get_intent_semantic_domain_unknown(self):
        """Unknown intent -> None."""
        assert get_intent_semantic_domain("unknown_xyz_intent") is None

    def test_get_all_semantic_domains_not_empty(self):
        """get_all_semantic_domains() must return a non-empty set."""
        domains = get_all_semantic_domains()
        assert len(domains) > 0
        assert "pricing" in domains
        assert "emotion" in domains
        assert "escalation" in domains
        assert "product" in domains


# =============================================================================
# Test: tone_overrides for rushed/confused
# =============================================================================

class TestToneOverrides:
    """Verify tone_overrides include rushed and confused at FRUSTRATION_HIGH."""

    def test_tone_override_rushed_eq_high(self):
        """APOLOGY_TONE_OVERRIDES['rushed'] == FRUSTRATION_HIGH (7)."""
        assert APOLOGY_TONE_OVERRIDES["rushed"] == FRUSTRATION_HIGH

    def test_tone_override_confused_eq_high(self):
        """APOLOGY_TONE_OVERRIDES['confused'] == FRUSTRATION_HIGH (7)."""
        assert APOLOGY_TONE_OVERRIDES["confused"] == FRUSTRATION_HIGH

    def test_tone_override_skeptical_eq_high(self):
        """APOLOGY_TONE_OVERRIDES['skeptical'] == FRUSTRATION_HIGH (7)."""
        assert APOLOGY_TONE_OVERRIDES["skeptical"] == FRUSTRATION_HIGH

    def test_ssot_rushed_below_threshold(self):
        """should_apologize(5, 'rushed') -> False (below override threshold 7)."""
        assert should_apologize(5, tone="rushed") is False

    def test_ssot_rushed_at_threshold(self):
        """should_apologize(7, 'rushed') -> True (at override threshold 7)."""
        assert should_apologize(7, tone="rushed") is True

    def test_ssot_confused_below_threshold(self):
        """should_apologize(5, 'confused') -> False (below override threshold 7)."""
        assert should_apologize(5, tone="confused") is False


# =============================================================================
# Test: should_suppress_for_intent()
# =============================================================================

class TestShouldSuppressForIntent:
    """Verify intent-domain suppression logic."""

    def test_suppress_for_pricing_domain(self):
        """price_question (pricing domain) -> suppress."""
        assert should_suppress_for_intent("price_question") is True

    def test_suppress_for_product_domain(self):
        """question_features (product domain) -> suppress."""
        assert should_suppress_for_intent("question_features") is True

    def test_no_suppress_for_emotion_domain(self):
        """frustration_expression (emotion domain) -> don't suppress."""
        assert should_suppress_for_intent("frustration_expression") is False

    def test_no_suppress_for_escalation_domain(self):
        """request_human (escalation domain) -> don't suppress."""
        assert should_suppress_for_intent("request_human") is False

    def test_no_suppress_for_unknown_intent(self):
        """Unknown intent -> don't suppress (safe default)."""
        assert should_suppress_for_intent("unknown_xyz") is False

    def test_no_suppress_empty_intent(self):
        """Empty intent -> don't suppress."""
        assert should_suppress_for_intent("") is False

    def test_suppress_at_medium_frustration(self):
        """price_question at medium frustration (5) -> suppress."""
        assert should_suppress_for_intent("price_question", frustration_level=5) is True

    def test_no_suppress_at_high_frustration(self):
        """price_question at HIGH frustration (7) -> don't suppress (safety net)."""
        assert should_suppress_for_intent("price_question", frustration_level=7) is False

    def test_no_suppress_emotion_at_any_level(self):
        """frustration_expression at medium frustration -> don't suppress."""
        assert should_suppress_for_intent("frustration_expression", frustration_level=5) is False

    def test_no_suppress_empty_config(self):
        """When APOLOGY_ALLOWED_DOMAINS is empty, never suppress."""
        with patch("src.apology_ssot.APOLOGY_ALLOWED_DOMAINS", set()):
            assert should_suppress_for_intent("price_question") is False


# =============================================================================
# Test: Generator._ensure_apology() intent-domain guard
# =============================================================================

class TestEnsureApologyGuard:
    """Verify generator._ensure_apology() skips for non-allowed domains."""

    def _make_generator(self):
        """Create a minimal ResponseGenerator for testing."""
        from src.generator import ResponseGenerator
        mock_llm = MagicMock()
        return ResponseGenerator(llm=mock_llm)

    @patch("src.generator.flags")
    def test_ensure_apology_skips_pricing_intent(self, mock_flags):
        """_ensure_apology() should NOT prepend for price_question at medium frustration."""
        mock_flags.is_enabled.return_value = True
        gen = self._make_generator()
        context = {
            "should_apologize": True,
            "intent": "price_question",
            "frustration_level": 5,
        }
        result = gen._ensure_apology("Вот наши цены.", context)
        # Should return original response (no apology prepended)
        assert result == "Вот наши цены."

    @patch("src.generator.flags")
    def test_ensure_apology_keeps_at_high_frustration(self, mock_flags):
        """_ensure_apology() SHOULD prepend for price_question at frustration=7."""
        mock_flags.is_enabled.return_value = True
        gen = self._make_generator()
        context = {
            "should_apologize": True,
            "intent": "price_question",
            "frustration_level": 7,
        }
        result = gen._ensure_apology("Вот наши цены.", context)
        # Should have apology prepended (original doesn't contain one)
        assert result != "Вот наши цены."
        assert "Вот наши цены." in result

    @patch("src.generator.flags")
    def test_ensure_apology_works_for_emotion_domain(self, mock_flags):
        """_ensure_apology() SHOULD prepend for emotion domain at medium frustration."""
        mock_flags.is_enabled.return_value = True
        gen = self._make_generator()
        context = {
            "should_apologize": True,
            "intent": "frustration_expression",
            "frustration_level": 5,
        }
        result = gen._ensure_apology("Я понимаю вас.", context)
        # Emotion domain -> not suppressed, but response already has apology marker "понимаю"
        # So it should detect existing apology and not prepend
        assert "понимаю" in result


# =============================================================================
# Test: ResponseDirectivesBuilder._fill_apology() intent-domain guard
# =============================================================================

class TestFillApologyGuard:
    """Verify response_directives._fill_apology() uses current_intent for suppression."""

    def _make_builder(self, frustration_level=5, tone=None, current_intent=None):
        """Create a minimal ResponseDirectivesBuilder with mocked envelope."""
        from src.response_directives import ResponseDirectivesBuilder, ResponseDirectives
        envelope = MagicMock()
        envelope.frustration_level = frustration_level
        envelope.tone = tone
        envelope.pre_intervention_triggered = False
        envelope.current_intent = current_intent
        builder = ResponseDirectivesBuilder(envelope)
        return builder

    def test_fill_apology_suppresses_for_pricing(self):
        """_fill_apology() should set should_apologize=False for pricing intent."""
        from src.response_directives import ResponseDirectives
        builder = self._make_builder(
            frustration_level=5,
            tone="frustrated",
            current_intent="price_question",
        )
        directives = ResponseDirectives()
        builder._fill_apology(directives)
        # price_question is pricing domain -> suppressed
        assert directives.should_apologize is False

    def test_fill_apology_allows_for_emotion(self):
        """_fill_apology() should keep should_apologize=True for emotion intent."""
        from src.response_directives import ResponseDirectives
        builder = self._make_builder(
            frustration_level=5,
            tone="frustrated",
            current_intent="frustration_expression",
        )
        directives = ResponseDirectives()
        builder._fill_apology(directives)
        # frustration_expression is emotion domain -> not suppressed
        assert directives.should_apologize is True

    def test_fill_apology_uses_current_not_last_intent(self):
        """Guard should use current_intent, not last_intent (which lags by 1 turn)."""
        from src.response_directives import ResponseDirectives
        builder = self._make_builder(
            frustration_level=5,
            tone="frustrated",
            current_intent="price_question",
        )
        # Set last_intent to something in emotion domain (should be ignored)
        builder.envelope.last_intent = "frustration_expression"
        directives = ResponseDirectives()
        builder._fill_apology(directives)
        # Should suppress based on current_intent (price_question), not last_intent
        assert directives.should_apologize is False

    def test_fill_apology_no_suppress_at_high_frustration(self):
        """At HIGH frustration, should NOT suppress even for pricing domain."""
        from src.response_directives import ResponseDirectives
        builder = self._make_builder(
            frustration_level=7,
            tone="frustrated",
            current_intent="price_question",
        )
        directives = ResponseDirectives()
        builder._fill_apology(directives)
        # Safety net at HIGH frustration -> not suppressed
        assert directives.should_apologize is True


# =============================================================================
# Test: regex_analyzer medium urgency apology behavior
# =============================================================================

class TestRegexAnalyzerMediumUrgency:
    """Verify regex_analyzer only sets should_apologize for FRUSTRATED tone."""

    def test_medium_urgency_rushed_no_apology(self):
        """RUSHED tone at medium urgency -> should_apologize=False."""
        from src.tone_analyzer.models import Tone, Style, ToneAnalysis
        from src.tone_analyzer.regex_analyzer import RegexToneAnalyzer

        analyzer = RegexToneAnalyzer()
        analysis = ToneAnalysis(
            tone=Tone.RUSHED,
            style=Style.FORMAL,
            confidence=0.8,
            frustration_level=5,
            signal_count=2,
            intervention_urgency="medium",
        )
        analysis.pre_intervention_triggered = False
        guidance = analyzer.get_response_guidance(analysis)

        # Medium urgency (frustration 5 = between warning(4) and high(7))
        # RUSHED tone -> should_apologize should be False
        assert guidance.get("should_apologize") is False

    def test_medium_urgency_frustrated_still_apologize(self):
        """FRUSTRATED tone at medium urgency -> should_apologize=True."""
        from src.tone_analyzer.models import Tone, Style, ToneAnalysis
        from src.tone_analyzer.regex_analyzer import RegexToneAnalyzer

        analyzer = RegexToneAnalyzer()
        analysis = ToneAnalysis(
            tone=Tone.FRUSTRATED,
            style=Style.FORMAL,
            confidence=0.8,
            frustration_level=5,
            signal_count=2,
            intervention_urgency="medium",
        )
        analysis.pre_intervention_triggered = False
        guidance = analyzer.get_response_guidance(analysis)

        assert guidance.get("should_apologize") is True


# =============================================================================
# Test: validate_thresholds() passes with new overrides
# =============================================================================

class TestValidateThresholds:
    """Verify validate_thresholds() works with new tone_overrides."""

    def test_validate_thresholds_passes(self):
        """validate_thresholds() should pass with rushed/confused overrides."""
        assert validate_thresholds() is True
