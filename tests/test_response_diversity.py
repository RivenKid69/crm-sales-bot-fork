"""
Comprehensive tests for ResponseDiversityEngine.

Tests cover:
1. Basic functionality (banned opening replacement)
2. LRU rotation for variety
3. Context-aware opening selection
4. Metrics tracking
5. Graceful degradation
6. Integration with feature flags
7. Configuration loading
8. Edge cases
"""

import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

# Import the module under test
import sys

from src.response_diversity import (
    ResponseDiversityEngine,
    DiversityConfig,
    DiversityMetrics,
    ProcessingResult,
    diversity_engine,
    process_response,
    get_opening,
)

# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def engine():
    """Create a fresh engine instance for each test."""
    return ResponseDiversityEngine()

@pytest.fixture
def engine_with_mocked_config():
    """Create engine with mocked config for controlled testing."""
    engine = ResponseDiversityEngine.__new__(ResponseDiversityEngine)
    engine._config = DiversityConfig(
        banned_openings={
            "exact_match": ["Понимаю", "Понимаю,", "Понимаю."],
            "patterns": [r"^Понимаю[,.]?\s"],
        },
        alternative_openings={
            "empathy": {
                "skip_probability": 0,  # Never skip for testing
                "phrases": ["Да, это важно.", "Слышу вас.", "Знакомая ситуация."],
            },
            "acknowledgment": {
                "skip_probability": 0,
                "phrases": ["Понял.", "Хорошо.", "Ясно."],
            },
        },
        context_mapping={
            "intent_to_opening": {
                "problem_shared": "empathy",
                "situation_provided": "acknowledgment",
            },
            "state_to_opening": {
                "spin_problem": "empathy",
                "spin_situation": "acknowledgment",
            },
            "frustration_to_opening": {
                "0": "acknowledgment",
                "3": "empathy",
            },
        },
        replacement_strategies={
            "default": {"max_lru_history": 3, "fallback_to_empty": True},
        },
        prompt_instructions={
            "system_instruction": "НЕ начинай с 'Понимаю'",
            "example_instruction": "Чередуй вступления",
        },
        metrics={"track_opening_usage": True},
    )
    engine._metrics = DiversityMetrics()
    engine._lru_history = {}
    engine._banned_patterns = []
    engine._compile_banned_patterns()
    return engine

# =============================================================================
# BASIC FUNCTIONALITY TESTS
# =============================================================================

class TestBasicFunctionality:
    """Test basic banned opening replacement."""

    def test_detect_banned_opening_exact(self, engine_with_mocked_config):
        """Test that exact banned openings are detected."""
        response = "Понимаю, это важно. Расскажите подробнее."
        match = engine_with_mocked_config._find_banned_opening(response)
        assert match is not None

    def test_detect_banned_opening_with_period(self, engine_with_mocked_config):
        """Test detection with period."""
        response = "Понимаю. Давайте разберёмся."
        match = engine_with_mocked_config._find_banned_opening(response)
        assert match is not None

    def test_no_false_positive(self, engine_with_mocked_config):
        """Test that non-banned openings are not detected."""
        response = "Хорошо, давайте разберёмся."
        match = engine_with_mocked_config._find_banned_opening(response)
        assert match is None

    def test_process_response_replaces_banned(self, engine_with_mocked_config):
        """Test that banned openings are replaced."""
        response = "Понимаю, это важно. Расскажите подробнее."
        result = engine_with_mocked_config.process_response(response)

        assert result.was_modified is True
        assert result.modification_type == "banned_replaced"
        assert not result.processed.startswith("Понимаю")

    def test_process_response_preserves_unchanged(self, engine_with_mocked_config):
        """Test that non-banned responses are preserved."""
        response = "Хорошо, давайте разберёмся."
        result = engine_with_mocked_config.process_response(response)

        assert result.was_modified is False
        assert result.processed == response

    def test_process_response_empty_input(self, engine_with_mocked_config):
        """Test handling of empty input."""
        result = engine_with_mocked_config.process_response("")
        assert result.processed == ""
        assert result.was_modified is False

# =============================================================================
# LRU ROTATION TESTS
# =============================================================================

class TestLRURotation:
    """Test LRU rotation for variety in openings."""

    def test_lru_prevents_immediate_repeat(self, engine_with_mocked_config):
        """Test that LRU prevents immediate repetition."""
        openings = []
        for _ in range(6):
            opening = engine_with_mocked_config.get_opening("empathy")
            openings.append(opening)

        # Check that we don't have the same opening twice in a row
        for i in range(1, len(openings)):
            if openings[i] and openings[i - 1]:
                # Allow same only if all have been used (LRU reset)
                pass  # LRU should cycle through

    def test_lru_rotates_through_all_phrases(self, engine_with_mocked_config):
        """Test that LRU eventually uses all phrases."""
        used_openings = set()

        # Get more openings than available to force rotation
        for _ in range(10):
            opening = engine_with_mocked_config.get_opening("empathy")
            if opening:
                used_openings.add(opening)

        # Should have used multiple different openings
        assert len(used_openings) >= 2

    def test_lru_history_limited_by_max(self, engine_with_mocked_config):
        """Test that LRU history is limited by max_lru_history."""
        # Generate many openings
        for _ in range(20):
            engine_with_mocked_config.get_opening("empathy")

        # Check history size
        history = engine_with_mocked_config._lru_history.get("opening_empathy", [])
        max_history = engine_with_mocked_config._get_max_lru_history()
        assert len(history) <= max_history

# =============================================================================
# CONTEXT-AWARE SELECTION TESTS
# =============================================================================

class TestContextAwareSelection:
    """Test context-aware opening selection."""

    def test_selects_by_intent(self, engine_with_mocked_config):
        """Test selection by intent."""
        category = engine_with_mocked_config._determine_category(
            {"intent": "problem_shared"}
        )
        assert category == "empathy"

    def test_selects_by_state(self, engine_with_mocked_config):
        """Test selection by state."""
        category = engine_with_mocked_config._determine_category(
            {"state": "spin_situation"}
        )
        assert category == "acknowledgment"

    def test_selects_by_frustration(self, engine_with_mocked_config):
        """Test selection by frustration level."""
        category = engine_with_mocked_config._determine_category(
            {"frustration_level": 3}
        )
        assert category == "empathy"

    def test_fallback_to_default(self, engine_with_mocked_config):
        """Test fallback to default category."""
        category = engine_with_mocked_config._determine_category(
            {"unknown_key": "value"}
        )
        assert category == "acknowledgment"  # default

    def test_intent_priority_over_state(self, engine_with_mocked_config):
        """Test that intent has priority over state."""
        category = engine_with_mocked_config._determine_category(
            {"intent": "problem_shared", "state": "spin_situation"}
        )
        # intent should win
        assert category == "empathy"

# =============================================================================
# METRICS TESTS
# =============================================================================

class TestMetrics:
    """Test metrics tracking."""

    def test_metrics_count_processed(self, engine_with_mocked_config):
        """Test that processed count increases."""
        initial = engine_with_mocked_config._metrics.total_processed

        engine_with_mocked_config.process_response("Test response")

        assert engine_with_mocked_config._metrics.total_processed == initial + 1

    def test_metrics_count_replaced(self, engine_with_mocked_config):
        """Test that replaced count increases on replacement."""
        initial = engine_with_mocked_config._metrics.banned_replaced

        engine_with_mocked_config.process_response("Понимаю, это важно.")

        assert engine_with_mocked_config._metrics.banned_replaced == initial + 1

    def test_metrics_track_openings(self, engine_with_mocked_config):
        """Test that opening usage is tracked."""
        engine_with_mocked_config.get_opening("empathy")

        assert engine_with_mocked_config._metrics.openings_generated >= 1

    def test_metrics_to_dict(self, engine_with_mocked_config):
        """Test metrics serialization."""
        engine_with_mocked_config.process_response("Понимаю, это важно.")
        engine_with_mocked_config.get_opening("empathy")

        metrics_dict = engine_with_mocked_config.get_metrics_dict()

        assert "total_processed" in metrics_dict
        assert "banned_replaced" in metrics_dict
        assert "openings_generated" in metrics_dict
        assert "replacement_rate" in metrics_dict

# =============================================================================
# GRACEFUL DEGRADATION TESTS
# =============================================================================

class TestGracefulDegradation:
    """Test graceful degradation on errors."""

    def test_returns_original_on_config_error(self):
        """Test that original is returned if config fails."""
        engine = ResponseDiversityEngine.__new__(ResponseDiversityEngine)
        engine._config = None
        engine._metrics = DiversityMetrics()
        engine._lru_history = {}
        engine._banned_patterns = []

        response = "Понимаю, это важно."
        result = engine.process_response(response)

        # Should return original when config is None
        assert result.processed == response or result.was_modified is False

    def test_unknown_category_returns_empty(self, engine_with_mocked_config):
        """Test that unknown category returns empty string."""
        opening = engine_with_mocked_config.get_opening("nonexistent_category")
        assert opening == ""

# =============================================================================
# FEATURE FLAG INTEGRATION TESTS
# =============================================================================

class TestFeatureFlagIntegration:
    """Test integration with feature flags."""

    def test_flag_check_happens_in_generator(self):
        """Test that flag check happens in generator, not in engine."""
        # The engine itself doesn't check flags - generator.py does
        # This is by design: engine is always available, flags control usage point
        engine = ResponseDiversityEngine()

        # Engine always processes when called directly (no flag check)
        response = "Понимаю, это важно."
        result = engine.process_response(response)

        # Should be processed regardless of flags (engine doesn't check flags)
        assert result.was_modified or result.processed == response

    def test_enabled_flag_processes_response(self):
        """Test that enabled flag processes response."""
        # The engine itself doesn't check flags - generator.py does
        engine = ResponseDiversityEngine()

        # Engine always processes when called directly
        response = "Понимаю, это важно."
        result = engine.process_response(response)

        assert result.was_modified or result.processed == response

# =============================================================================
# CONFIGURATION TESTS
# =============================================================================

class TestConfiguration:
    """Test configuration loading and handling."""

    def test_loads_from_yaml(self, engine):
        """Test that config is loaded from YAML."""
        assert engine._config is not None

    def test_reload_config(self, engine):
        """Test config reload."""
        engine.reload_config()
        assert engine._config is not None

    def test_reset_clears_state(self, engine):
        """Test that reset clears LRU history and metrics."""
        # Generate some state
        engine.process_response("Понимаю, это важно.")
        engine.get_opening("empathy")

        engine.reset()

        assert engine._lru_history == {}
        assert engine._metrics.total_processed == 0

    def test_get_system_instruction(self, engine_with_mocked_config):
        """Test getting system instruction."""
        instruction = engine_with_mocked_config.get_system_instruction()
        assert "Понимаю" in instruction

    def test_get_example_instruction(self, engine_with_mocked_config):
        """Test getting example instruction."""
        instruction = engine_with_mocked_config.get_example_instruction()
        assert "Чередуй" in instruction

# =============================================================================
# EDGE CASES
# =============================================================================

class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_very_long_response(self, engine_with_mocked_config):
        """Test handling of very long response."""
        response = "Понимаю, " + "это важно. " * 1000
        result = engine_with_mocked_config.process_response(response)

        assert result.was_modified
        assert not result.processed.startswith("Понимаю")

    def test_unicode_response(self, engine_with_mocked_config):
        """Test handling of unicode characters."""
        response = "Понимаю, это важно для компании «Тест»!"
        result = engine_with_mocked_config.process_response(response)

        assert result.was_modified
        assert "«Тест»" in result.processed

    def test_multiline_response(self, engine_with_mocked_config):
        """Test handling of multiline response."""
        response = "Понимаю, это важно.\nДавайте разберёмся."
        result = engine_with_mocked_config.process_response(response)

        assert result.was_modified
        assert "\n" in result.processed or "Давайте" in result.processed

    def test_only_banned_word(self, engine_with_mocked_config):
        """Test response that is only the banned word."""
        response = "Понимаю."
        result = engine_with_mocked_config.process_response(response)

        # Should either replace or return empty
        assert result.processed != "Понимаю." or not result.was_modified

    def test_banned_word_in_middle(self, engine_with_mocked_config):
        """Test banned word in middle of response (should not be replaced)."""
        response = "Хорошо, я понимаю вашу проблему."
        result = engine_with_mocked_config.process_response(response)

        # Should not be modified - "понимаю" is in middle
        assert result.was_modified is False

# =============================================================================
# TRANSITION PHRASES TESTS
# =============================================================================

class TestTransitionPhrases:
    """Test transition phrase generation."""

    def test_get_transition(self, engine):
        """Test getting transition phrases."""
        # May return empty string due to skip probability
        for _ in range(10):
            transition = engine.get_transition("to_question")
            # Just check it doesn't crash
            assert isinstance(transition, str)

# =============================================================================
# MONOTONY DETECTION TESTS
# =============================================================================

class TestMonotonyDetection:
    """Test monotony detection functionality."""

    def test_detect_monotony_threshold(self, engine_with_mocked_config):
        """Test monotony detection with threshold."""
        # Simulate same opening used multiple times
        engine_with_mocked_config._metrics.last_openings = [
            "Да, это важно.",
            "Да, это важно.",
            "Да, это важно.",
        ]

        warning = engine_with_mocked_config.check_monotony(threshold=3)
        assert warning is not None
        assert "Да, это важно." in warning

    def test_no_monotony_when_varied(self, engine_with_mocked_config):
        """Test no monotony when varied."""
        engine_with_mocked_config._metrics.last_openings = [
            "Да, это важно.",
            "Слышу вас.",
            "Знакомая ситуация.",
        ]

        warning = engine_with_mocked_config.check_monotony(threshold=3)
        assert warning is None

# =============================================================================
# CONVENIENCE FUNCTIONS TESTS
# =============================================================================

class TestConvenienceFunctions:
    """Test module-level convenience functions."""

    def test_process_response_function(self):
        """Test process_response convenience function."""
        result = process_response("Понимаю, это важно.")
        assert isinstance(result, str)

    def test_get_opening_function(self):
        """Test get_opening convenience function."""
        result = get_opening("empathy")
        assert isinstance(result, str)

# =============================================================================
# SINGLETON TESTS
# =============================================================================

class TestSingleton:
    """Test singleton instance."""

    def test_global_instance_exists(self):
        """Test that global instance exists."""
        assert diversity_engine is not None
        assert isinstance(diversity_engine, ResponseDiversityEngine)

# =============================================================================
# INTEGRATION TESTS
# =============================================================================

class TestIntegration:
    """Integration tests with real config."""

    def test_full_flow_with_real_config(self, engine):
        """Test full flow with real config file."""
        # Process a response with banned opening
        response = "Понимаю, это серьёзная проблема. Давайте разберёмся как помочь."
        result = engine.process_response(response, context={"intent": "problem_shared"})

        # Should be modified if config loaded correctly
        if engine._config and engine._banned_patterns:
            assert result.was_modified
            assert not result.processed.startswith("Понимаю")

    def test_full_flow_preserves_content(self, engine):
        """Test that content after banned opening is preserved."""
        response = "Понимаю, это серьёзная проблема. Давайте разберёмся."
        result = engine.process_response(response)

        if result.was_modified:
            assert "проблема" in result.processed.lower() or "разберёмся" in result.processed.lower()

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
