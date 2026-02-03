"""
Tests for ConversationGuard module.

Tests cover:
- Normal conversation flow
- Loop detection (message and state)
- Timeout detection
- Max turns limit
- Phase exhaustion detection
- Progress tracking
- Frustration level handling
- Configuration variants
"""

import sys
import time
from pathlib import Path

import pytest

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from conversation_guard import ConversationGuard, GuardConfig, GuardState


class TestGuardConfig:
    """Tests for GuardConfig dataclass"""

    def test_default_config(self):
        """Default config has reasonable values"""
        config = GuardConfig.default()
        assert config.max_turns == 25
        assert config.max_phase_attempts == 3
        assert config.max_same_state == 4
        assert config.max_same_message == 3  # Raised from 2 to 3
        assert config.timeout_seconds == 1800

    def test_strict_config(self):
        """Strict config has lower limits"""
        config = GuardConfig.strict()
        assert config.max_turns < GuardConfig.default().max_turns
        assert config.max_phase_attempts < GuardConfig.default().max_phase_attempts
        assert config.timeout_seconds < GuardConfig.default().timeout_seconds

    def test_relaxed_config(self):
        """Relaxed config has higher limits"""
        config = GuardConfig.relaxed()
        assert config.max_turns > GuardConfig.default().max_turns
        assert config.max_phase_attempts > GuardConfig.default().max_phase_attempts
        assert config.timeout_seconds > GuardConfig.default().timeout_seconds

    def test_custom_config(self):
        """Custom config can be created"""
        config = GuardConfig(
            max_turns=10,
            max_phase_attempts=2,
            timeout_seconds=60
        )
        assert config.max_turns == 10
        assert config.max_phase_attempts == 2
        assert config.timeout_seconds == 60


class TestConversationGuardBasic:
    """Basic tests for ConversationGuard"""

    def test_initialization(self):
        """Guard initializes correctly"""
        guard = ConversationGuard()
        assert guard.turn_count == 0
        assert guard.state_history == []
        assert guard.phase_attempts == {}

    def test_reset(self):
        """Reset clears all state"""
        guard = ConversationGuard()
        guard.check("state1", "message1", {})
        guard.check("state2", "message2", {})

        guard.reset()

        assert guard.turn_count == 0
        assert guard.state_history == []
        assert guard.phase_attempts == {}

    def test_normal_conversation(self):
        """Normal conversation proceeds without intervention"""
        guard = ConversationGuard()

        # Simulate normal flow
        states = ["greeting", "spin_situation", "spin_problem", "presentation", "close"]
        for i, state in enumerate(states):
            can_continue, intervention = guard.check(state, f"message {i}", {})
            assert can_continue is True
            assert intervention is None

    def test_turn_count_increments(self):
        """Turn count increments correctly"""
        guard = ConversationGuard()

        for i in range(5):
            guard.check("state", f"message {i}", {})
            assert guard.turn_count == i + 1

    def test_state_history_recorded(self):
        """State history is recorded correctly"""
        guard = ConversationGuard()

        guard.check("greeting", "hello", {})
        guard.check("spin_situation", "10 people", {})
        guard.check("spin_problem", "we lose clients", {})

        assert guard.state_history == ["greeting", "spin_situation", "spin_problem"]

    def test_phase_attempts_counted(self):
        """Phase attempts are counted correctly"""
        guard = ConversationGuard()

        guard.check("spin_situation", "msg1", {})
        guard.check("spin_situation", "msg2", {})
        guard.check("spin_problem", "msg3", {})
        guard.check("spin_situation", "msg4", {})

        assert guard.phase_attempts["spin_situation"] == 3
        assert guard.phase_attempts["spin_problem"] == 1


class TestMessageLoopDetection:
    """Tests for message loop detection"""

    def test_detects_exact_message_repeat(self):
        """Detects when user sends same message 3 times (raised from 2 to 3)"""
        guard = ConversationGuard()

        guard.check("state1", "same message", {})
        guard.check("state1", "same message", {})
        can_continue, intervention = guard.check("state1", "same message", {})

        assert can_continue is True
        assert intervention == "fallback_tier_2"

    def test_case_insensitive_comparison(self):
        """Message comparison is case-insensitive"""
        guard = ConversationGuard()

        guard.check("state1", "Same Message", {})
        guard.check("state1", "same message", {})
        can_continue, intervention = guard.check("state1", "same message", {})

        assert intervention == "fallback_tier_2"

    def test_whitespace_normalized(self):
        """Whitespace is normalized in message comparison"""
        guard = ConversationGuard()

        guard.check("state1", "  same message  ", {})
        guard.check("state1", "same message", {})
        can_continue, intervention = guard.check("state1", "same message", {})

        assert intervention == "fallback_tier_2"

    def test_different_messages_no_intervention(self):
        """Different messages don't trigger intervention"""
        guard = ConversationGuard()

        guard.check("state1", "message one", {})
        can_continue, intervention = guard.check("state1", "message two", {})

        assert intervention is None


class TestStateLoopDetection:
    """Tests for state loop detection"""

    def test_detects_state_loop(self):
        """Detects when stuck in same state"""
        config = GuardConfig(max_same_state=3)
        guard = ConversationGuard(config)

        for i in range(3):
            can_continue, intervention = guard.check(
                "spin_situation",
                f"message {i}",
                {}
            )

        assert intervention == "fallback_tier_3"

    def test_state_change_resets_count(self):
        """Changing state resets the count"""
        config = GuardConfig(max_same_state=3)
        guard = ConversationGuard(config)

        guard.check("spin_situation", "msg1", {})
        guard.check("spin_situation", "msg2", {})
        guard.check("spin_problem", "msg3", {})  # State change
        can_continue, intervention = guard.check("spin_situation", "msg4", {})

        assert intervention is None  # Count reset


class TestTimeoutDetection:
    """Tests for timeout detection"""

    def test_detects_timeout(self):
        """Detects conversation timeout"""
        config = GuardConfig(timeout_seconds=0)  # Immediate timeout
        guard = ConversationGuard(config)

        guard.check("state1", "msg1", {})  # Start timer
        time.sleep(0.01)  # Wait a bit
        can_continue, intervention = guard.check("state2", "msg2", {})

        assert can_continue is False
        assert intervention == "soft_close"

    def test_no_timeout_within_limit(self):
        """No timeout if within time limit"""
        config = GuardConfig(timeout_seconds=3600)  # 1 hour
        guard = ConversationGuard(config)

        guard.check("state1", "msg1", {})
        can_continue, intervention = guard.check("state2", "msg2", {})

        assert can_continue is True
        assert intervention is None


class TestMaxTurnsLimit:
    """Tests for max turns limit"""

    def test_detects_max_turns(self):
        """Detects when max turns exceeded"""
        config = GuardConfig(max_turns=3)
        guard = ConversationGuard(config)

        for i in range(3):
            guard.check(f"state{i}", f"msg{i}", {})

        can_continue, intervention = guard.check("state4", "msg4", {})

        assert can_continue is False
        assert intervention == "soft_close"

    def test_allows_up_to_max_turns(self):
        """Allows conversation up to max turns"""
        config = GuardConfig(max_turns=5)
        guard = ConversationGuard(config)

        for i in range(5):
            can_continue, intervention = guard.check(f"state{i}", f"msg{i}", {})
            assert can_continue is True


class TestPhaseExhaustion:
    """Tests for phase exhaustion detection.

    NOTE: Check 6 (phase_exhausted → TIER_2) was removed from ConversationGuard
    and migrated to PhaseExhaustedSource inside the Blackboard pipeline.
    These tests verify the old check 6 no longer fires from the Guard.
    """

    def test_phase_exhaustion_no_longer_fires_from_guard(self):
        """Check 6 removed: phase exhaustion no longer produces TIER_2 from guard."""
        config = GuardConfig(max_phase_attempts=2)
        guard = ConversationGuard(config)

        guard.check("spin_situation", "msg1", {})
        guard.check("spin_situation", "msg2", {})
        can_continue, intervention = guard.check("spin_situation", "msg3", {})

        assert can_continue is True
        # Old behavior was intervention == "fallback_tier_2"
        # New behavior: no intervention from guard (handled by PhaseExhaustedSource)
        assert intervention != "fallback_tier_2"

    def test_other_checks_still_work_after_check6_removal(self):
        """Verify other guard checks (timeout, max_turns, etc.) still function."""
        # Timeout still works
        config = GuardConfig(timeout_seconds=0)
        guard = ConversationGuard(config)
        import time
        time.sleep(0.01)
        can_continue, intervention = guard.check("state1", "msg", {})
        assert can_continue is False
        assert intervention == "soft_close"

    def test_allows_more_attempts_with_data_progress(self):
        """Allows more attempts if collecting data (check 6 removed, always passes now)."""
        config = GuardConfig(max_phase_attempts=2)
        guard = ConversationGuard(config)

        guard.check("spin_situation", "msg1", {})
        guard.check("spin_situation", "msg2", {"company_size": 10})
        can_continue, intervention = guard.check(
            "spin_situation",
            "msg3",
            {"company_size": 10, "industry": "retail"}
        )

        # With check 6 removed, no phase exhaustion intervention from guard
        assert intervention is None or intervention != "fallback_tier_2"


class TestFrustrationHandling:
    """Tests for frustration level handling"""

    def test_high_frustration_triggers_tier_3(self):
        """High frustration triggers skip suggestion"""
        config = GuardConfig(high_frustration_threshold=7)
        guard = ConversationGuard(config)

        can_continue, intervention = guard.check(
            "spin_situation",
            "message",
            {},
            frustration_level=8
        )

        assert can_continue is True
        assert intervention == "fallback_tier_3"

    def test_moderate_frustration_no_intervention(self):
        """Moderate frustration doesn't trigger intervention"""
        config = GuardConfig(high_frustration_threshold=7)
        guard = ConversationGuard(config)

        can_continue, intervention = guard.check(
            "spin_situation",
            "message",
            {},
            frustration_level=5
        )

        assert intervention is None

    def test_set_frustration_level(self):
        """Can set frustration level externally"""
        guard = ConversationGuard()
        guard.set_frustration_level(8)

        can_continue, intervention = guard.check("state", "msg", {})
        assert intervention == "fallback_tier_3"

    def test_frustration_level_clamped(self):
        """Frustration level is clamped to 0-10"""
        guard = ConversationGuard()

        guard.set_frustration_level(-5)
        assert guard._state.frustration_level == 0

        guard.set_frustration_level(15)
        assert guard._state.frustration_level == 10


class TestProgressTracking:
    """Tests for progress tracking"""

    def test_record_progress(self):
        """Can manually record progress"""
        guard = ConversationGuard()

        guard.check("state1", "msg1", {})
        guard.check("state2", "msg2", {})
        guard.record_progress()

        assert guard._state.last_progress_turn == 2

    def test_no_progress_triggers_tier_1(self):
        """No progress over interval triggers rephrase"""
        config = GuardConfig(
            progress_check_interval=3,
            min_unique_states_for_progress=2,
            max_same_state=10,  # Prevent state loop detection
            max_phase_attempts=10  # Prevent phase exhaustion detection
        )
        guard = ConversationGuard(config)

        # All same state = no progress
        for i in range(5):
            can_continue, intervention = guard.check(
                "spin_situation",
                f"different message {i}",
                {}
            )

        assert intervention == "fallback_tier_1"

    def test_progress_with_state_changes(self):
        """State changes count as progress"""
        config = GuardConfig(
            progress_check_interval=3,
            min_unique_states_for_progress=2
        )
        guard = ConversationGuard(config)

        guard.check("greeting", "msg1", {})
        guard.check("spin_situation", "msg2", {})
        guard.check("spin_problem", "msg3", {})
        guard.check("spin_implication", "msg4", {})
        can_continue, intervention = guard.check("presentation", "msg5", {})

        assert intervention is None  # Progress detected


class TestGetStats:
    """Tests for statistics retrieval"""

    def test_get_stats_initial(self):
        """Stats are correct initially"""
        guard = ConversationGuard()
        stats = guard.get_stats()

        assert stats["turn_count"] == 0
        assert stats["unique_states"] == 0
        assert stats["last_state"] is None
        assert stats["frustration_level"] == 0

    def test_get_stats_after_conversation(self):
        """Stats are correct after conversation"""
        guard = ConversationGuard()

        guard.check("greeting", "hello", {})
        guard.check("spin_situation", "10 people", {"company_size": 10})
        guard.set_frustration_level(3)

        stats = guard.get_stats()

        assert stats["turn_count"] == 2
        assert stats["unique_states"] == 2
        assert stats["last_state"] == "spin_situation"
        assert stats["frustration_level"] == 3
        assert stats["collected_data_count"] == 1
        assert "elapsed_seconds" in stats
        assert "phase_attempts" in stats


class TestInterventionPriority:
    """Tests for intervention priority order"""

    def test_timeout_highest_priority(self):
        """Timeout takes priority over other checks"""
        config = GuardConfig(
            timeout_seconds=0,
            max_turns=100,
            max_same_state=100
        )
        guard = ConversationGuard(config)

        guard.check("state1", "msg1", {})
        time.sleep(0.01)

        # Even with high frustration, timeout wins
        can_continue, intervention = guard.check(
            "state1",
            "msg1",  # Same message
            {},
            frustration_level=10
        )

        assert can_continue is False
        assert intervention == "soft_close"

    def test_max_turns_before_frustration(self):
        """Max turns checked before frustration"""
        config = GuardConfig(max_turns=2)
        guard = ConversationGuard(config)

        guard.check("state1", "msg1", {})
        guard.check("state2", "msg2", {})

        can_continue, intervention = guard.check(
            "state3",
            "msg3",
            {},
            frustration_level=10
        )

        assert can_continue is False
        assert intervention == "soft_close"


class TestEdgeCases:
    """Edge case tests"""

    def test_empty_message(self):
        """Handles empty message"""
        guard = ConversationGuard()
        can_continue, intervention = guard.check("state", "", {})
        assert can_continue is True

    def test_empty_state(self):
        """Handles empty state"""
        guard = ConversationGuard()
        can_continue, intervention = guard.check("", "message", {})
        assert can_continue is True

    def test_none_collected_data(self):
        """Handles various collected_data types"""
        guard = ConversationGuard()
        # Should not crash with different data types
        guard.check("state", "msg", {})
        guard.check("state", "msg", {"key": "value"})
        guard.check("state", "msg", {"a": 1, "b": 2, "c": 3})

    def test_very_long_message(self):
        """Handles very long message"""
        guard = ConversationGuard()
        long_message = "a" * 10000
        can_continue, intervention = guard.check("state", long_message, {})
        assert can_continue is True

    def test_unicode_message(self):
        """Handles unicode message"""
        guard = ConversationGuard()
        unicode_message = "Привет! Как дела? 🎉"
        can_continue, intervention = guard.check("state", unicode_message, {})
        assert can_continue is True


class TestMultipleGuardInstances:
    """Tests for multiple guard instances"""

    def test_independent_instances(self):
        """Multiple guards are independent"""
        guard1 = ConversationGuard()
        guard2 = ConversationGuard()

        guard1.check("state1", "msg1", {})
        guard1.check("state2", "msg2", {})

        assert guard1.turn_count == 2
        assert guard2.turn_count == 0

    def test_different_configs(self):
        """Guards can have different configs"""
        guard1 = ConversationGuard(GuardConfig.strict())
        guard2 = ConversationGuard(GuardConfig.relaxed())

        assert guard1.config.max_turns < guard2.config.max_turns


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
