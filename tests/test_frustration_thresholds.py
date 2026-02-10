"""
Tests for Frustration Thresholds Consistency.

This test suite verifies that:
1. All frustration thresholds are consistent across the system
2. ConversationGuard triggers intervention at the correct threshold
3. Fallback conditions use the same thresholds as guard
4. No hardcoded values bypass the centralized thresholds

Part of the fix for: Guard Check не вмешивается при высокой фрустрации
Root cause: threshold mismatch (guard used 7, conditions used 5)
"""

import pytest

class TestFrustrationThresholdsConsistency:
    """Test that all frustration thresholds are consistent."""

    def test_thresholds_module_imports(self):
        """Test that frustration_thresholds module imports correctly."""
        from src.frustration_thresholds import (
            FRUSTRATION_ELEVATED,
            FRUSTRATION_MODERATE,
            FRUSTRATION_WARNING,
            FRUSTRATION_HIGH,
            FRUSTRATION_CRITICAL,
            FRUSTRATION_MAX,
            FRUSTRATION_THRESHOLDS,
        )

        # Verify all thresholds are integers
        assert isinstance(FRUSTRATION_ELEVATED, int)
        assert isinstance(FRUSTRATION_MODERATE, int)
        assert isinstance(FRUSTRATION_WARNING, int)
        assert isinstance(FRUSTRATION_HIGH, int)
        assert isinstance(FRUSTRATION_CRITICAL, int)
        assert isinstance(FRUSTRATION_MAX, int)

        # Verify dictionary contains all keys
        assert "elevated" in FRUSTRATION_THRESHOLDS
        assert "moderate" in FRUSTRATION_THRESHOLDS
        assert "warning" in FRUSTRATION_THRESHOLDS
        assert "high" in FRUSTRATION_THRESHOLDS
        assert "critical" in FRUSTRATION_THRESHOLDS

    def test_threshold_ordering(self):
        """Test that thresholds are in correct order."""
        from src.frustration_thresholds import (
            FRUSTRATION_ELEVATED,
            FRUSTRATION_MODERATE,
            FRUSTRATION_WARNING,
            FRUSTRATION_HIGH,
            FRUSTRATION_CRITICAL,
            FRUSTRATION_MAX,
        )

        # Must be: 0 <= elevated < moderate < warning < high < critical <= max
        assert 0 <= FRUSTRATION_ELEVATED
        assert FRUSTRATION_ELEVATED < FRUSTRATION_MODERATE
        assert FRUSTRATION_MODERATE < FRUSTRATION_WARNING
        assert FRUSTRATION_WARNING < FRUSTRATION_HIGH
        assert FRUSTRATION_HIGH < FRUSTRATION_CRITICAL
        assert FRUSTRATION_CRITICAL <= FRUSTRATION_MAX

    def test_yaml_config_consistency(self):
        """Test that YAML config values match centralized thresholds."""
        from src.yaml_config.constants import (
            FRUSTRATION_THRESHOLDS as YAML_THRESHOLDS,
            GUARD_CONFIG,
        )
        from src.frustration_thresholds import (
            FRUSTRATION_WARNING,
            FRUSTRATION_HIGH,
            FRUSTRATION_CRITICAL,
        )

        # YAML frustration thresholds must match centralized values
        assert YAML_THRESHOLDS.get("warning") == FRUSTRATION_WARNING
        assert YAML_THRESHOLDS.get("high") == FRUSTRATION_HIGH
        assert YAML_THRESHOLDS.get("critical") == FRUSTRATION_CRITICAL

        # Guard config must use same high threshold
        assert GUARD_CONFIG.get("high_frustration_threshold") == FRUSTRATION_HIGH

    def test_guard_config_uses_centralized_threshold(self):
        """Test that GuardConfig uses centralized FRUSTRATION_HIGH."""
        from src.conversation_guard import GuardConfig
        from src.frustration_thresholds import FRUSTRATION_HIGH

        config = GuardConfig()
        assert config.high_frustration_threshold == FRUSTRATION_HIGH

    def test_markers_uses_centralized_thresholds(self):
        """Test that markers.py imports from centralized module."""
        from src.tone_analyzer.markers import (
            FRUSTRATION_THRESHOLDS,
            MAX_FRUSTRATION,
        )
        from src.frustration_thresholds import (
            FRUSTRATION_THRESHOLDS as CENTRAL_THRESHOLDS,
            FRUSTRATION_MAX,
        )

        # Must be same object (imported from same source)
        assert FRUSTRATION_THRESHOLDS == CENTRAL_THRESHOLDS
        assert MAX_FRUSTRATION == FRUSTRATION_MAX

class TestFrustrationHelperFunctions:
    """Test helper functions for frustration level checks."""

    def test_is_frustration_elevated(self):
        """Test is_frustration_elevated function."""
        from src.frustration_thresholds import (
            is_frustration_elevated,
            FRUSTRATION_ELEVATED,
        )

        # Below threshold
        assert not is_frustration_elevated(FRUSTRATION_ELEVATED - 1)
        assert not is_frustration_elevated(0)
        assert not is_frustration_elevated(1)

        # At or above threshold
        assert is_frustration_elevated(FRUSTRATION_ELEVATED)
        assert is_frustration_elevated(FRUSTRATION_ELEVATED + 1)
        assert is_frustration_elevated(10)

    def test_is_frustration_moderate(self):
        """Test is_frustration_moderate function."""
        from src.frustration_thresholds import (
            is_frustration_moderate,
            FRUSTRATION_MODERATE,
        )

        # Below threshold
        assert not is_frustration_moderate(FRUSTRATION_MODERATE - 1)
        assert not is_frustration_moderate(0)

        # At or above threshold
        assert is_frustration_moderate(FRUSTRATION_MODERATE)
        assert is_frustration_moderate(FRUSTRATION_MODERATE + 1)

    def test_is_frustration_warning(self):
        """Test is_frustration_warning function."""
        from src.frustration_thresholds import (
            is_frustration_warning,
            FRUSTRATION_WARNING,
        )

        # Below threshold
        assert not is_frustration_warning(FRUSTRATION_WARNING - 1)

        # At or above threshold
        assert is_frustration_warning(FRUSTRATION_WARNING)
        assert is_frustration_warning(FRUSTRATION_WARNING + 1)

    def test_is_frustration_high(self):
        """Test is_frustration_high function."""
        from src.frustration_thresholds import (
            is_frustration_high,
            FRUSTRATION_HIGH,
        )

        # Below threshold - these should NOT trigger intervention
        assert not is_frustration_high(FRUSTRATION_HIGH - 1)
        assert not is_frustration_high(5)  # The old broken threshold
        assert not is_frustration_high(6)  # Also broken

        # At or above threshold - these SHOULD trigger intervention
        assert is_frustration_high(FRUSTRATION_HIGH)
        assert is_frustration_high(FRUSTRATION_HIGH + 1)
        assert is_frustration_high(10)

    def test_needs_intervention(self):
        """Test needs_intervention function matches is_frustration_high."""
        from src.frustration_thresholds import (
            needs_intervention,
            is_frustration_high,
            FRUSTRATION_HIGH,
        )

        # Must behave identically to is_frustration_high
        for level in range(11):
            assert needs_intervention(level) == is_frustration_high(level)

    def test_needs_immediate_escalation(self):
        """Test needs_immediate_escalation uses correct threshold."""
        from src.frustration_thresholds import (
            needs_immediate_escalation,
            FRUSTRATION_HIGH,
        )

        # This was the bug: condition used >= 5 instead of >= 7
        assert not needs_immediate_escalation(5)  # Should NOT escalate at 5
        assert not needs_immediate_escalation(6)  # Should NOT escalate at 6
        assert needs_immediate_escalation(FRUSTRATION_HIGH)  # SHOULD at high
        assert needs_immediate_escalation(FRUSTRATION_HIGH + 1)

    def test_can_recover(self):
        """Test can_recover function."""
        from src.frustration_thresholds import (
            can_recover,
            FRUSTRATION_WARNING,
        )

        # Can recover below warning
        assert can_recover(0)
        assert can_recover(FRUSTRATION_WARNING - 1)

        # Cannot recover at or above warning
        assert not can_recover(FRUSTRATION_WARNING)
        assert not can_recover(FRUSTRATION_WARNING + 1)

    def test_get_frustration_severity(self):
        """Test get_frustration_severity returns correct classification."""
        from src.frustration_thresholds import (
            get_frustration_severity,
            FRUSTRATION_ELEVATED,
            FRUSTRATION_MODERATE,
            FRUSTRATION_WARNING,
            FRUSTRATION_HIGH,
            FRUSTRATION_CRITICAL,
        )

        assert get_frustration_severity(0) == "normal"
        assert get_frustration_severity(1) == "normal"
        assert get_frustration_severity(FRUSTRATION_ELEVATED) == "elevated"
        assert get_frustration_severity(FRUSTRATION_MODERATE) == "moderate"
        assert get_frustration_severity(FRUSTRATION_WARNING) == "warning"
        assert get_frustration_severity(FRUSTRATION_HIGH) == "high"
        assert get_frustration_severity(FRUSTRATION_CRITICAL) == "critical"

class TestGuardInterventionTrigger:
    """Test that ConversationGuard triggers intervention correctly."""

    def test_guard_triggers_at_high_threshold(self):
        """Test that guard triggers intervention at FRUSTRATION_HIGH."""
        from src.conversation_guard import ConversationGuard
        from src.frustration_thresholds import FRUSTRATION_HIGH

        guard = ConversationGuard()

        # Simulate conversation at high frustration
        guard.set_frustration_level(FRUSTRATION_HIGH)

        can_continue, intervention = guard.check(
            state="spin_situation",
            message="тест",
            collected_data={},
            frustration_level=FRUSTRATION_HIGH,
        )

        # Should trigger intervention (TIER_3)
        assert intervention is not None
        assert intervention == guard.TIER_3

    def test_guard_no_intervention_below_threshold(self):
        """Test that guard does NOT trigger below FRUSTRATION_HIGH."""
        from src.conversation_guard import ConversationGuard
        from src.frustration_thresholds import FRUSTRATION_HIGH

        guard = ConversationGuard()

        # Frustration at 5 or 6 should NOT trigger (old bug)
        for level in [5, 6, FRUSTRATION_HIGH - 1]:
            guard.reset()
            guard.set_frustration_level(level)

            can_continue, intervention = guard.check(
                state="spin_situation",
                message="тест",
                collected_data={},
                frustration_level=level,
            )

            # No intervention expected for frustration check alone
            # (other checks might trigger, but not frustration)
            # We just verify that at level 5/6 the frustration check passes
            assert can_continue is True or intervention != guard.TIER_3

class TestFallbackConditionsUseCentralizedThresholds:
    """Test that fallback conditions use centralized thresholds."""

    def test_needs_immediate_escalation_uses_high_threshold(self):
        """Test that fallback needs_immediate_escalation uses FRUSTRATION_HIGH."""
        from src.conditions.fallback.conditions import needs_immediate_escalation
        from src.conditions.fallback.context import FallbackContext
        from src.frustration_thresholds import FRUSTRATION_HIGH

        # At level 5 (old broken threshold) - should NOT escalate
        ctx_5 = FallbackContext(
            state="spin_situation",
            frustration_level=5,
            consecutive_fallbacks=0,
            total_fallbacks=0,
        )
        assert not needs_immediate_escalation(ctx_5)

        # At level 6 - should NOT escalate
        ctx_6 = FallbackContext(
            state="spin_situation",
            frustration_level=6,
            consecutive_fallbacks=0,
            total_fallbacks=0,
        )
        assert not needs_immediate_escalation(ctx_6)

        # At FRUSTRATION_HIGH - SHOULD escalate
        ctx_high = FallbackContext(
            state="spin_situation",
            frustration_level=FRUSTRATION_HIGH,
            consecutive_fallbacks=0,
            total_fallbacks=0,
        )
        assert needs_immediate_escalation(ctx_high)

    def test_can_recover_uses_warning_threshold(self):
        """Test that fallback can_recover uses FRUSTRATION_WARNING."""
        from src.conditions.fallback.conditions import can_recover
        from src.conditions.fallback.context import FallbackContext
        from src.frustration_thresholds import FRUSTRATION_WARNING

        # Below warning - can recover
        ctx_low = FallbackContext(
            state="spin_situation",
            frustration_level=FRUSTRATION_WARNING - 1,
            total_fallbacks=0,
            engagement_level="high",
        )
        assert can_recover(ctx_low)

        # At warning - cannot recover
        ctx_warning = FallbackContext(
            state="spin_situation",
            frustration_level=FRUSTRATION_WARNING,
            total_fallbacks=0,
            engagement_level="high",
        )
        assert not can_recover(ctx_warning)

class TestValidateThresholds:
    """Test the validation function."""

    def test_validate_thresholds_succeeds(self):
        """Test that validate_thresholds succeeds when config is consistent."""
        from src.frustration_thresholds import validate_thresholds

        # Should not raise
        result = validate_thresholds()
        assert result is True

class TestIntegration:
    """Integration tests for the complete frustration handling flow."""

    def test_frustration_flow_consistency(self):
        """Test that frustration flows consistently through the system."""
        from src.frustration_thresholds import (
            FRUSTRATION_HIGH,
            is_frustration_high,
            needs_intervention,
            needs_immediate_escalation,
        )
        from src.conversation_guard import GuardConfig

        config = GuardConfig()

        # All should use the same threshold
        test_level = FRUSTRATION_HIGH

        assert is_frustration_high(test_level)
        assert needs_intervention(test_level)
        assert needs_immediate_escalation(test_level)
        assert config.high_frustration_threshold == test_level

    def test_old_bug_scenario(self):
        """
        Reproduce the original bug scenario.

        Original issue:
        - frustration_level: 5 appeared 52 times
        - frustration_level: 6 appeared 28 times
        - intervention_triggered: false at frustration >= 5

        Root cause: guard used threshold 7, but conditions used 5.

        After fix: both should use FRUSTRATION_HIGH (7).
        """
        from src.frustration_thresholds import FRUSTRATION_HIGH

        # The bug was that at level 5 or 6, intervention did not trigger
        # because guard threshold was 7 but some conditions used 5
        frustration_levels_from_bug = [5, 6]

        for level in frustration_levels_from_bug:
            # This should be False now (level < 7)
            from src.frustration_thresholds import is_frustration_high
            intervention_triggered = is_frustration_high(level)

            # At level 5 and 6, intervention should NOT trigger
            # This matches what guard does (threshold 7)
            assert not intervention_triggered, (
                f"Level {level} should NOT trigger intervention "
                f"(threshold is {FRUSTRATION_HIGH})"
            )

        # At level 7+, intervention SHOULD trigger
        assert is_frustration_high(7)
        assert is_frustration_high(8)
