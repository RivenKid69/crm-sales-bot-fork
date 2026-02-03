"""
Tests for Apology System SSoT.

Follows the same pattern as test_frustration_thresholds.py:
- SSoT consistency tests
- Helper function unit tests
- Integration tests
- E2E tests

SSoT: src/apology_ssot.py
"""
import pytest
from unittest.mock import MagicMock, patch

from src.apology_ssot import (
    APOLOGY_THRESHOLD,
    EXIT_OFFER_THRESHOLD,
    APOLOGY_MARKERS,
    should_apologize,
    should_offer_exit,
    get_apology_instruction,
    get_exit_instruction,
    build_apology_prefix,
    build_exit_suffix,
    has_apology,
    validate_thresholds,
)
from src.frustration_thresholds import (
    FRUSTRATION_WARNING,
    FRUSTRATION_HIGH,
)


class TestApologySSoTConsistency:
    """SSoT consistency tests - thresholds match frustration_thresholds."""

    def test_apology_threshold_equals_frustration_warning(self):
        """APOLOGY_THRESHOLD uses FRUSTRATION_WARNING from SSoT."""
        assert APOLOGY_THRESHOLD == FRUSTRATION_WARNING

    def test_exit_threshold_equals_frustration_high(self):
        """EXIT_OFFER_THRESHOLD uses FRUSTRATION_HIGH from SSoT."""
        assert EXIT_OFFER_THRESHOLD == FRUSTRATION_HIGH

    def test_threshold_ordering(self):
        """Apology threshold < Exit threshold (apologize before offering exit)."""
        assert APOLOGY_THRESHOLD < EXIT_OFFER_THRESHOLD

    def test_validate_thresholds_passes(self):
        """validate_thresholds() returns True for correct configuration."""
        assert validate_thresholds() is True

    def test_apology_markers_not_empty(self):
        """APOLOGY_MARKERS list is not empty."""
        assert len(APOLOGY_MARKERS) > 0
        assert all(isinstance(m, str) for m in APOLOGY_MARKERS)


class TestApologyHelperFunctions:
    """Unit tests for helper functions."""

    def test_should_apologize_false_below_threshold(self):
        """should_apologize returns False below threshold."""
        assert should_apologize(APOLOGY_THRESHOLD - 1) is False

    def test_should_apologize_true_at_threshold(self):
        """should_apologize returns True at threshold."""
        assert should_apologize(APOLOGY_THRESHOLD) is True

    def test_should_apologize_true_above_threshold(self):
        """should_apologize returns True above threshold."""
        assert should_apologize(APOLOGY_THRESHOLD + 1) is True

    def test_should_apologize_false_at_zero(self):
        """should_apologize returns False at zero frustration."""
        assert should_apologize(0) is False

    def test_should_offer_exit_false_below_threshold(self):
        """should_offer_exit returns False below threshold."""
        assert should_offer_exit(EXIT_OFFER_THRESHOLD - 1) is False

    def test_should_offer_exit_true_at_threshold(self):
        """should_offer_exit returns True at threshold."""
        assert should_offer_exit(EXIT_OFFER_THRESHOLD) is True

    def test_should_offer_exit_true_above_threshold(self):
        """should_offer_exit returns True above threshold."""
        assert should_offer_exit(EXIT_OFFER_THRESHOLD + 1) is True

    def test_get_apology_instruction_not_empty(self):
        """get_apology_instruction returns non-empty string."""
        instruction = get_apology_instruction()
        assert instruction
        assert isinstance(instruction, str)
        # Should mention apology in Russian
        assert "извинен" in instruction.lower() or "обязательно" in instruction.lower()

    def test_get_exit_instruction_not_empty(self):
        """get_exit_instruction returns non-empty string."""
        instruction = get_exit_instruction()
        assert instruction
        assert isinstance(instruction, str)
        # Should mention exit in Russian
        assert "заверш" in instruction.lower() or "неудобно" in instruction.lower()


class TestApologyDetection:
    """Tests for has_apology() function."""

    def test_has_apology_detects_izvinite(self):
        """Detects 'Извините' as apology."""
        assert has_apology("Извините за неудобства.") is True

    def test_has_apology_detects_proshu_prosh(self):
        """Detects 'Прошу прощения' as apology."""
        assert has_apology("Прошу прощения за задержку.") is True

    def test_has_apology_detects_sorry(self):
        """Detects 'Сорри' as apology."""
        assert has_apology("Сорри за это.") is True

    def test_has_apology_detects_ponimayu(self):
        """Detects 'Понимаю, это может' as apology."""
        assert has_apology("Понимаю, это может раздражать.") is True

    def test_has_apology_detects_ponimayu_vashu(self):
        """Detects 'Понимаю вашу' as apology."""
        assert has_apology("Понимаю вашу фрустрацию.") is True

    def test_has_apology_false_for_regular_text(self):
        """Returns False for text without apology."""
        assert has_apology("Давайте разберёмся с вопросом.") is False

    def test_has_apology_case_insensitive(self):
        """Detection is case insensitive."""
        assert has_apology("ИЗВИНИТЕ за неудобства") is True
        assert has_apology("извините за неудобства") is True


class TestPhraseBuilders:
    """Tests for phrase builder functions."""

    def test_build_apology_prefix_calls_variations(self):
        """build_apology_prefix calls variations.get_apology()."""
        mock_variations = MagicMock()
        mock_variations.get_apology.return_value = "Извините за неудобства."

        result = build_apology_prefix(mock_variations)

        assert result == "Извините за неудобства."
        mock_variations.get_apology.assert_called_once()

    def test_build_exit_suffix_calls_variations(self):
        """build_exit_suffix calls variations.get_exit_offer()."""
        mock_variations = MagicMock()
        mock_variations.get_exit_offer.return_value = "Если неудобно — можем позже."

        result = build_exit_suffix(mock_variations)

        assert result == "Если неудобно — можем позже."
        mock_variations.get_exit_offer.assert_called_once()


class TestResponseDirectivesApology:
    """Integration with ResponseDirectives."""

    def test_directives_has_should_apologize_field(self):
        """ResponseDirectives has should_apologize field."""
        from src.response_directives import ResponseDirectives

        directives = ResponseDirectives()
        assert hasattr(directives, "should_apologize")
        assert directives.should_apologize is False

    def test_directives_has_should_offer_exit_field(self):
        """ResponseDirectives has should_offer_exit field."""
        from src.response_directives import ResponseDirectives

        directives = ResponseDirectives()
        assert hasattr(directives, "should_offer_exit")
        assert directives.should_offer_exit is False

    def test_get_instruction_includes_apology_when_flag_set(self):
        """get_instruction() includes apology text when should_apologize=True."""
        from src.response_directives import ResponseDirectives

        directives = ResponseDirectives(should_apologize=True)
        instruction = directives.get_instruction()

        assert instruction
        assert "извинен" in instruction.lower() or "обязательно" in instruction.lower()

    def test_get_instruction_includes_exit_when_flag_set(self):
        """get_instruction() includes exit offer when should_offer_exit=True."""
        from src.response_directives import ResponseDirectives

        directives = ResponseDirectives(should_offer_exit=True)
        instruction = directives.get_instruction()

        assert instruction
        assert "заверш" in instruction.lower() or "неудобно" in instruction.lower()

    def test_get_instruction_includes_both_when_both_flags_set(self):
        """get_instruction() includes both apology and exit when both flags set."""
        from src.response_directives import ResponseDirectives

        directives = ResponseDirectives(should_apologize=True, should_offer_exit=True)
        instruction = directives.get_instruction()

        # Should have both instructions
        assert "извинен" in instruction.lower() or "обязательно" in instruction.lower()
        assert "заверш" in instruction.lower() or "неудобно" in instruction.lower()

    def test_to_dict_includes_apology_section(self):
        """to_dict() includes apology section."""
        from src.response_directives import ResponseDirectives

        directives = ResponseDirectives(should_apologize=True, should_offer_exit=True)
        data = directives.to_dict()

        assert "apology" in data
        assert data["apology"]["should_apologize"] is True
        assert data["apology"]["should_offer_exit"] is True


class TestResponseDirectivesBuilder:
    """Integration with ResponseDirectivesBuilder."""

    def test_builder_fills_apology_from_envelope_at_warning(self):
        """Builder sets should_apologize=True at warning level."""
        from src.response_directives import ResponseDirectivesBuilder
        from src.context_envelope import ContextEnvelope

        envelope = ContextEnvelope(frustration_level=APOLOGY_THRESHOLD)
        builder = ResponseDirectivesBuilder(envelope)
        directives = builder.build()

        assert directives.should_apologize is True

    def test_builder_fills_apology_false_below_warning(self):
        """Builder sets should_apologize=False below warning level."""
        from src.response_directives import ResponseDirectivesBuilder
        from src.context_envelope import ContextEnvelope

        envelope = ContextEnvelope(frustration_level=APOLOGY_THRESHOLD - 1)
        builder = ResponseDirectivesBuilder(envelope)
        directives = builder.build()

        assert directives.should_apologize is False

    def test_builder_fills_exit_from_envelope_at_high(self):
        """Builder sets should_offer_exit=True at high level."""
        from src.response_directives import ResponseDirectivesBuilder
        from src.context_envelope import ContextEnvelope

        envelope = ContextEnvelope(frustration_level=EXIT_OFFER_THRESHOLD)
        builder = ResponseDirectivesBuilder(envelope)
        directives = builder.build()

        assert directives.should_offer_exit is True

    def test_builder_fills_exit_false_below_high(self):
        """Builder sets should_offer_exit=False below high level."""
        from src.response_directives import ResponseDirectivesBuilder
        from src.context_envelope import ContextEnvelope

        envelope = ContextEnvelope(frustration_level=EXIT_OFFER_THRESHOLD - 1)
        builder = ResponseDirectivesBuilder(envelope)
        directives = builder.build()

        assert directives.should_offer_exit is False


class TestGeneratorApology:
    """Integration with Generator - uses method inspection to avoid loading embeddings."""

    def test_generator_class_has_ensure_apology_method(self):
        """Generator class has _ensure_apology method defined."""
        from src.generator import ResponseGenerator

        # Check method exists on class (without instantiation)
        assert hasattr(ResponseGenerator, "_ensure_apology")

    def test_generator_class_has_has_apology_method(self):
        """Generator class has _has_apology method defined."""
        from src.generator import ResponseGenerator

        # Check method exists on class (without instantiation)
        assert hasattr(ResponseGenerator, "_has_apology")

    def test_has_apology_detection_via_ssot(self):
        """has_apology from SSoT works correctly."""
        from src.apology_ssot import has_apology

        # Test detection
        assert has_apology("Извините за неудобства.") is True
        assert has_apology("Давайте разберёмся.") is False

    def test_apology_instruction_in_directives(self):
        """Apology instruction appears in directives when flag set."""
        from src.response_directives import ResponseDirectives

        directives = ResponseDirectives(should_apologize=True)
        instruction = directives.get_instruction()

        # Should have apology instruction
        assert "извинен" in instruction.lower() or "обязательно" in instruction.lower()

    def test_exit_instruction_in_directives(self):
        """Exit instruction appears in directives when flag set."""
        from src.response_directives import ResponseDirectives

        directives = ResponseDirectives(should_offer_exit=True)
        instruction = directives.get_instruction()

        # Should have exit instruction
        assert "заверш" in instruction.lower() or "неудобно" in instruction.lower()

    def test_apology_flow_through_builder(self):
        """Full flow: envelope → builder → directives with apology."""
        from src.context_envelope import ContextEnvelope
        from src.response_directives import ResponseDirectivesBuilder

        # Create envelope with high frustration
        envelope = ContextEnvelope(frustration_level=FRUSTRATION_HIGH)

        # Build directives
        builder = ResponseDirectivesBuilder(envelope)
        directives = builder.build()

        # Should have both flags
        assert directives.should_apologize is True
        assert directives.should_offer_exit is True

        # Instruction should mention both
        instruction = directives.get_instruction()
        assert instruction  # Not empty


class TestBug22ToneAwareApology:
    """Tone-aware apology — skeptical users should not get apology at warning level."""

    def test_skeptical_at_warning_no_apology(self):
        """should_apologize(4, 'skeptical') == False — skeptics need facts, not apology."""
        assert should_apologize(APOLOGY_THRESHOLD, tone="skeptical") is False

    def test_skeptical_at_high_still_apologize(self):
        """should_apologize(7, 'skeptical') == True — at HIGH threshold, everyone gets apology."""
        assert should_apologize(7, tone="skeptical") is True

    def test_none_tone_backward_compat(self):
        """should_apologize(4, None) == True — backward-compatible, no tone = default behavior."""
        assert should_apologize(APOLOGY_THRESHOLD, tone=None) is True

    def test_frustrated_at_warning_still_apologize(self):
        """should_apologize(4, 'frustrated') == True — frustrated users still get apology."""
        assert should_apologize(APOLOGY_THRESHOLD, tone="frustrated") is True

    def test_yaml_tone_overrides_loaded(self):
        """Verify APOLOGY_TONE_OVERRIDES has skeptical: 7 from YAML."""
        from src.yaml_config.constants import APOLOGY_TONE_OVERRIDES
        assert "skeptical" in APOLOGY_TONE_OVERRIDES
        assert APOLOGY_TONE_OVERRIDES["skeptical"] == 7

    def test_validate_thresholds_catches_invalid_override(self):
        """Invalid YAML config raises ValueError during validation."""
        from src.yaml_config.constants import APOLOGY_TONE_OVERRIDES
        from src.apology_ssot import validate_thresholds as _validate

        original = APOLOGY_TONE_OVERRIDES.copy()
        try:
            # Inject invalid override (below APOLOGY_THRESHOLD)
            APOLOGY_TONE_OVERRIDES["test_invalid"] = 1
            with pytest.raises(ValueError, match="APOLOGY_TONE_OVERRIDES"):
                _validate()
        finally:
            # Restore original
            APOLOGY_TONE_OVERRIDES.clear()
            APOLOGY_TONE_OVERRIDES.update(original)

    def test_skeptical_below_threshold_no_apology(self):
        """should_apologize(3, 'skeptical') == False — below base threshold."""
        assert should_apologize(3, tone="skeptical") is False

    def test_unknown_tone_default_behavior(self):
        """should_apologize(4, 'unknown_tone') == True — unknown tone uses default."""
        assert should_apologize(APOLOGY_THRESHOLD, tone="unknown_tone") is True

    def test_case_insensitive_tone(self):
        """Tone matching is case-insensitive."""
        assert should_apologize(APOLOGY_THRESHOLD, tone="SKEPTICAL") is False
        assert should_apologize(APOLOGY_THRESHOLD, tone="Skeptical") is False


class TestBug22RegexAnalyzer:
    """Regex_analyzer urgency branches — Path A tests."""

    def test_medium_urgency_skeptical_no_apology(self):
        """urgency='medium' + SKEPTICAL → should_apologize=False."""
        from src.tone_analyzer.regex_analyzer import RegexToneAnalyzer
        from src.tone_analyzer.models import Tone, Style, ToneAnalysis

        analyzer = RegexToneAnalyzer()
        # Create analysis with SKEPTICAL tone and medium urgency
        analysis = ToneAnalysis(
            tone=Tone.SKEPTICAL,
            style=Style.FORMAL,
            confidence=0.85,
            frustration_level=4,
            signals=["skeptical:test"],
            tier_used="regex",
            intervention_urgency="medium",
        )
        guidance = analyzer.get_response_guidance(analysis)
        assert guidance["should_apologize"] is False

    def test_medium_urgency_frustrated_still_apologize(self):
        """urgency='medium' + FRUSTRATED → should_apologize=True."""
        from src.tone_analyzer.regex_analyzer import RegexToneAnalyzer
        from src.tone_analyzer.models import Tone, Style, ToneAnalysis

        analyzer = RegexToneAnalyzer()
        analysis = ToneAnalysis(
            tone=Tone.FRUSTRATED,
            style=Style.FORMAL,
            confidence=0.85,
            frustration_level=4,
            signals=["frustrated:test"],
            tier_used="regex",
            intervention_urgency="medium",
        )
        guidance = analyzer.get_response_guidance(analysis)
        assert guidance["should_apologize"] is True

    def test_high_urgency_skeptical_still_apologize(self):
        """urgency='high' + SKEPTICAL → should_apologize=True (high is beyond override)."""
        from src.tone_analyzer.regex_analyzer import RegexToneAnalyzer
        from src.tone_analyzer.models import Tone, Style, ToneAnalysis

        analyzer = RegexToneAnalyzer()
        analysis = ToneAnalysis(
            tone=Tone.SKEPTICAL,
            style=Style.FORMAL,
            confidence=0.90,
            frustration_level=7,
            signals=["skeptical:test"],
            tier_used="regex",
            intervention_urgency="high",
        )
        guidance = analyzer.get_response_guidance(analysis)
        assert guidance["should_apologize"] is True


class TestBug22ResponseVariations:
    """No anglicisms in APOLOGIES list."""

    def test_no_anglicisms_in_apologies(self):
        """No 'сорри' in APOLOGIES list."""
        from src.response_variations import ResponseVariations
        for phrase in ResponseVariations.APOLOGIES:
            assert "сорри" not in phrase.lower(), f"Anglicism found: {phrase}"


class TestFeatureFlag:
    """Tests for apology_system feature flag."""

    def test_flag_exists_in_defaults(self):
        """apology_system flag exists in DEFAULTS."""
        from src.feature_flags import FeatureFlags

        assert "apology_system" in FeatureFlags.DEFAULTS

    def test_flag_default_is_true(self):
        """apology_system flag defaults to True."""
        from src.feature_flags import FeatureFlags

        assert FeatureFlags.DEFAULTS["apology_system"] is True

    def test_flag_in_phase_2_group(self):
        """apology_system is in phase_2 group."""
        from src.feature_flags import FeatureFlags

        assert "apology_system" in FeatureFlags.GROUPS["phase_2"]

    def test_flag_in_safe_group(self):
        """apology_system is in safe group."""
        from src.feature_flags import FeatureFlags

        assert "apology_system" in FeatureFlags.GROUPS["safe"]


class TestApologyPhraseRotation:
    """Tests for apology phrase rotation (LRU)."""

    def test_apology_phrases_rotate(self):
        """Apologies use LRU rotation, don't repeat same phrase immediately."""
        from src.response_variations import ResponseVariations

        variations = ResponseVariations()
        phrases = []

        # Get several apologies
        for _ in range(len(ResponseVariations.APOLOGIES)):
            phrase = variations.get_apology()
            phrases.append(phrase)

        # Should have used different phrases (at least 2 unique)
        unique_phrases = set(phrases)
        assert len(unique_phrases) >= 2

    def test_exit_phrases_rotate(self):
        """Exit offers use LRU rotation."""
        from src.response_variations import ResponseVariations

        variations = ResponseVariations()
        phrases = []

        # Get several exit offers
        for _ in range(len(ResponseVariations.EXIT_OFFERS)):
            phrase = variations.get_exit_offer()
            phrases.append(phrase)

        # Should have used different phrases (at least 2 unique)
        unique_phrases = set(phrases)
        assert len(unique_phrases) >= 2


class TestIntegrationEndToEnd:
    """End-to-end integration tests."""

    def test_full_flow_apology_at_warning_level(self):
        """Full flow: warning frustration → apology instruction generated."""
        from src.context_envelope import ContextEnvelope
        from src.response_directives import build_response_directives

        # Create envelope with warning-level frustration
        envelope = ContextEnvelope(frustration_level=FRUSTRATION_WARNING)

        # Build directives
        directives = build_response_directives(envelope)

        # Should have apology flag set
        assert directives.should_apologize is True

        # Instruction should mention apology
        instruction = directives.get_instruction()
        assert "извинен" in instruction.lower() or "обязательно" in instruction.lower()

    def test_full_flow_exit_at_high_level(self):
        """Full flow: high frustration → exit offer instruction generated."""
        from src.context_envelope import ContextEnvelope
        from src.response_directives import build_response_directives

        # Create envelope with high-level frustration
        envelope = ContextEnvelope(frustration_level=FRUSTRATION_HIGH)

        # Build directives
        directives = build_response_directives(envelope)

        # Should have both flags set
        assert directives.should_apologize is True
        assert directives.should_offer_exit is True

        # Instruction should mention both
        instruction = directives.get_instruction()
        assert "извинен" in instruction.lower() or "обязательно" in instruction.lower()
        assert "заверш" in instruction.lower() or "неудобно" in instruction.lower()

    def test_full_flow_no_apology_at_low_level(self):
        """Full flow: low frustration → no apology."""
        from src.context_envelope import ContextEnvelope
        from src.response_directives import build_response_directives

        # Create envelope with low frustration
        envelope = ContextEnvelope(frustration_level=1)

        # Build directives
        directives = build_response_directives(envelope)

        # Should NOT have apology flags
        assert directives.should_apologize is False
        assert directives.should_offer_exit is False
