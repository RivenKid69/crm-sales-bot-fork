"""
Tests for 7 Interconnected Guard/Fallback/FSM Bug Fixes.

Covers:
- Fix 1: Classification before guard check (current intent, not stale)
- Fix 2: Validate required_data before tier_3 skip (no blind defaults)
- Fix 3: Tier 2 self-loop breaker (consecutive tier_2 escalation)
- Fix 4: soft_close no longer regresses to presentation on price/comparison
- Fix 5: Disambiguation paths return visited_states/initial_state
- Fix 6: _continue_with_classification() handles skip action + record_progress

Test strategy:
- Unit tests for each fix in isolation
- Integration tests for the dependency chain (Fix 1 → Fix 2 → Fix 3)
- Regression tests for currently-passing behaviors
"""

import sys
import time
from pathlib import Path
from typing import Dict, Any, Optional, List
from unittest.mock import Mock, MagicMock, patch, PropertyMock
from dataclasses import dataclass

import pytest

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from conversation_guard import ConversationGuard, GuardConfig, GuardState
from fallback_handler import FallbackHandler, FallbackResponse, FallbackStats


# =============================================================================
# Helpers
# =============================================================================

def _make_mock_flow(states: Optional[Dict[str, Dict]] = None, skip_map: Optional[Dict[str, str]] = None):
    """Create a mock FlowConfig with given states and skip_map."""
    flow = Mock()
    flow.states = states or {}
    flow.skip_map = skip_map or {}
    flow.name = "test_flow"
    flow.version = "1.0"
    return flow


# =============================================================================
# Fix 1: Classification Before Guard Check
# =============================================================================

class TestFix1ClassificationBeforeGuard:
    """Fix 1: Guard now uses current turn's classified intent, not self.last_intent."""

    def test_guard_config_unchanged(self):
        """GuardConfig still works with default values after fix."""
        config = GuardConfig.default()
        assert config.max_turns == 25
        assert config.max_same_state == 4

    def test_guard_uses_passed_intent_for_engagement_check(self):
        """Guard._is_engagement_intent uses the intent passed to check(), not stale data."""
        guard = ConversationGuard()
        # Simulate several turns in same state to trigger state_loop check
        for _ in range(3):
            guard.check("some_state", "msg", {}, frustration_level=0, last_intent="unclear")
        # 4th turn with informative intent should NOT trigger tier_3
        can_continue, intervention = guard.check(
            "some_state", "msg4", {}, frustration_level=0, last_intent="price_question"
        )
        # price_question is engagement → guard should NOT return TIER_3
        assert can_continue is True
        # intervention should be None because engagement intent suppresses state_loop
        assert intervention is None or intervention != "fallback_tier_3"

    def test_guard_triggers_tier3_with_unclear_intent(self):
        """Guard triggers state_loop (tier_3) when intent is unclear and state loops.

        NOTE: Must use different messages to avoid message_loop (tier_2) firing first.
        Guard priority: message_loop(tier_2) > state_loop(tier_3).
        """
        guard = ConversationGuard()
        for i in range(3):
            guard.check("some_state", f"msg_{i}", {}, frustration_level=0, last_intent="unclear")
        can_continue, intervention = guard.check(
            "some_state", "msg_3", {}, frustration_level=0, last_intent="unclear"
        )
        assert intervention == "fallback_tier_3"


# =============================================================================
# Fix 2: Validate required_data Before Tier 3 Skip
# =============================================================================

class TestFix2FindValidSkipTarget:
    """Fix 2: _find_valid_skip_target walks skip_map chain and validates required_data."""

    def test_no_flow_falls_back_to_skip_map(self):
        """Without flow reference, returns simple skip_map.get()."""
        handler = FallbackHandler(
            skip_map={"stateA": "stateB"},
            flow=None,
        )
        target = handler._find_valid_skip_target("stateA", {})
        assert target == "stateB"

    def test_no_flow_returns_none_for_unknown_state(self):
        """Without flow, returns None if state not in skip_map."""
        handler = FallbackHandler(
            skip_map={"stateA": "stateB"},
            flow=None,
        )
        target = handler._find_valid_skip_target("unknown", {})
        assert target is None

    def test_valid_target_no_required_data(self):
        """State with no required_data is always valid."""
        flow = _make_mock_flow(
            states={
                "stateA": {"required_data": ["field1"]},
                "stateB": {"required_data": []},
            },
            skip_map={"stateA": "stateB"},
        )
        handler = FallbackHandler(flow=flow)
        target = handler._find_valid_skip_target("stateA", {})
        assert target == "stateB"

    def test_valid_target_with_satisfied_required_data(self):
        """State with satisfied required_data is valid."""
        flow = _make_mock_flow(
            states={
                "stateA": {"required_data": []},
                "stateB": {"required_data": ["pain_point"]},
            },
            skip_map={"stateA": "stateB"},
        )
        handler = FallbackHandler(flow=flow)
        target = handler._find_valid_skip_target("stateA", {"pain_point": "losing clients"})
        assert target == "stateB"

    def test_skips_state_with_unsatisfied_required_data(self):
        """Walks past state with unsatisfied required_data to next in chain."""
        flow = _make_mock_flow(
            states={
                "stateA": {"required_data": []},
                "stateB": {"required_data": ["pain_point"]},  # NOT satisfied
                "stateC": {"required_data": []},  # Always valid
            },
            skip_map={"stateA": "stateB", "stateB": "stateC"},
        )
        handler = FallbackHandler(flow=flow)
        target = handler._find_valid_skip_target("stateA", {})
        assert target == "stateC"

    def test_returns_none_when_no_valid_target_in_chain(self):
        """Returns None if entire chain has unsatisfied required_data."""
        flow = _make_mock_flow(
            states={
                "stateA": {"required_data": []},
                "stateB": {"required_data": ["field1"]},
                "stateC": {"required_data": ["field2"]},
            },
            skip_map={"stateA": "stateB", "stateB": "stateC"},
        )
        handler = FallbackHandler(flow=flow)
        target = handler._find_valid_skip_target("stateA", {})
        assert target is None

    def test_unknown_state_config_returns_candidate(self):
        """Template var like {{entry_state}} has no state_config → accept."""
        flow = _make_mock_flow(
            states={
                "stateA": {"required_data": []},
                # "{{entry_state}}" is NOT in flow.states
            },
            skip_map={"stateA": "{{entry_state}}"},
        )
        handler = FallbackHandler(flow=flow)
        target = handler._find_valid_skip_target("stateA", {})
        assert target == "{{entry_state}}"

    def test_cycle_detection(self):
        """Cycle in skip_map doesn't cause infinite loop."""
        flow = _make_mock_flow(
            states={
                "stateA": {"required_data": ["x"]},
                "stateB": {"required_data": ["y"]},
            },
            skip_map={"stateA": "stateB", "stateB": "stateA"},
        )
        handler = FallbackHandler(flow=flow)
        target = handler._find_valid_skip_target("stateA", {})
        assert target is None  # Both have unsatisfied data, cycle detected

    def test_auto_flags_not_counted_as_collected_data(self):
        """Auto-flags from on_enter.set_flags should NOT satisfy required_data.

        The fix explicitly does NOT count auto-flags. Only REAL collected data
        from user interaction counts. This test verifies that behavior.
        """
        flow = _make_mock_flow(
            states={
                "teach_state": {"required_data": ["teach_probed"]},
                "close_state": {"required_data": []},
            },
            skip_map={"teach_state": "close_state"},
        )
        handler = FallbackHandler(flow=flow)
        # teach_probed is NOT in collected_data (it would only be an auto-flag)
        target = handler._find_valid_skip_target("teach_state", {})
        # Should skip teach_state and go to close_state
        assert target == "close_state"


class TestFix2Tier3SkipValidation:
    """Fix 2: _tier_3_skip uses _find_valid_skip_target instead of blind default."""

    def test_tier_3_with_valid_target(self):
        """Tier 3 skip returns valid target from chain."""
        flow = _make_mock_flow(
            states={
                "stateA": {"required_data": []},
                "stateB": {"required_data": []},
            },
            skip_map={"stateA": "stateB"},
        )
        handler = FallbackHandler(flow=flow)
        response = handler.get_fallback(
            "fallback_tier_3", "stateA", {"collected_data": {}}
        )
        assert response.action == "skip"
        assert response.next_state == "stateB"

    def test_tier_3_no_valid_target_falls_to_tier_2(self):
        """Tier 3 with no valid target falls back to tier_2 options."""
        flow = _make_mock_flow(
            states={
                "stateA": {"required_data": []},
                "stateB": {"required_data": ["missing_field"]},
            },
            skip_map={"stateA": "stateB"},
        )
        handler = FallbackHandler(flow=flow)
        response = handler.get_fallback(
            "fallback_tier_3", "stateA", {"collected_data": {}}
        )
        # Should NOT be skip since no valid target
        assert response.action == "continue"  # tier_2 options return "continue"


# =============================================================================
# Fix 3: Tier 2 Self-Loop Breaker
# =============================================================================

class TestFix3Tier2SelfLoopBreaker:
    """Fix 3: Consecutive tier_2 in same state escalates to tier_3."""

    def test_stats_has_tier2_tracking_fields(self):
        """FallbackStats has consecutive_tier_2_count and _state fields."""
        stats = FallbackStats()
        assert stats.consecutive_tier_2_count == 0
        assert stats.consecutive_tier_2_state is None

    def test_consecutive_tier_2_increments_count(self):
        """Consecutive tier_2 fallbacks in same state increment counter."""
        handler = FallbackHandler()
        handler.get_fallback("fallback_tier_2", "stateA")
        assert handler.stats.consecutive_tier_2_count == 1
        assert handler.stats.consecutive_tier_2_state == "stateA"

        handler.get_fallback("fallback_tier_2", "stateA")
        assert handler.stats.consecutive_tier_2_count == 2

    def test_different_state_resets_counter(self):
        """Tier_2 in different state resets counter."""
        handler = FallbackHandler()
        handler.get_fallback("fallback_tier_2", "stateA")
        handler.get_fallback("fallback_tier_2", "stateA")
        assert handler.stats.consecutive_tier_2_count == 2

        handler.get_fallback("fallback_tier_2", "stateB")
        assert handler.stats.consecutive_tier_2_count == 1
        assert handler.stats.consecutive_tier_2_state == "stateB"

    def test_different_tier_resets_counter(self):
        """Non-tier_2 fallback resets the counter."""
        handler = FallbackHandler()
        handler.get_fallback("fallback_tier_2", "stateA")
        handler.get_fallback("fallback_tier_2", "stateA")
        assert handler.stats.consecutive_tier_2_count == 2

        handler.get_fallback("fallback_tier_1", "stateA")
        assert handler.stats.consecutive_tier_2_count == 0
        assert handler.stats.consecutive_tier_2_state is None

    def test_escalation_after_threshold(self):
        """After max_consecutive_tier_2 (default=3), tier_2 escalates to tier_3."""
        flow = _make_mock_flow(
            states={"stateA": {"required_data": []}, "stateB": {"required_data": []}},
            skip_map={"stateA": "stateB"},
        )
        handler = FallbackHandler(flow=flow)

        # First two tier_2 calls return normal tier_2 (options)
        r1 = handler.get_fallback("fallback_tier_2", "stateA", {"collected_data": {}})
        assert r1.action == "continue"  # tier_2 options
        r2 = handler.get_fallback("fallback_tier_2", "stateA", {"collected_data": {}})
        assert r2.action == "continue"

        # Third consecutive tier_2 in same state → escalates to tier_3 skip
        r3 = handler.get_fallback("fallback_tier_2", "stateA", {"collected_data": {}})
        assert r3.action == "skip"
        assert r3.next_state == "stateB"

    def test_escalation_resets_counter(self):
        """After escalation, counter resets to 0."""
        flow = _make_mock_flow(
            states={"stateA": {"required_data": []}, "stateB": {"required_data": []}},
            skip_map={"stateA": "stateB"},
        )
        handler = FallbackHandler(flow=flow)

        for _ in range(3):
            handler.get_fallback("fallback_tier_2", "stateA", {"collected_data": {}})

        # Counter should be reset after escalation
        assert handler.stats.consecutive_tier_2_count == 0

    def test_configurable_threshold(self):
        """Threshold is configurable via guard_config."""
        config = GuardConfig()
        config.max_consecutive_tier_2 = 2  # Lower threshold

        flow = _make_mock_flow(
            states={"stateA": {"required_data": []}, "stateB": {"required_data": []}},
            skip_map={"stateA": "stateB"},
        )
        handler = FallbackHandler(flow=flow, guard_config=config)

        handler.get_fallback("fallback_tier_2", "stateA", {"collected_data": {}})
        r2 = handler.get_fallback("fallback_tier_2", "stateA", {"collected_data": {}})
        # With threshold=2, 2nd call should escalate
        assert r2.action == "skip"

    def test_guard_config_has_max_consecutive_tier_2(self):
        """GuardConfig includes max_consecutive_tier_2 field."""
        config = GuardConfig.default()
        assert config.max_consecutive_tier_2 == 3

    def test_guard_config_strict_inherits_default_tier2(self):
        """Strict config also has max_consecutive_tier_2."""
        config = GuardConfig.strict()
        assert hasattr(config, 'max_consecutive_tier_2')
        assert config.max_consecutive_tier_2 == 3


# =============================================================================
# Fix 4: soft_close No Longer Transitions to presentation
# =============================================================================

class TestFix4SoftCloseNoPresentation:
    """Fix 4: price_question/pricing_details/comparison in soft_close
    no longer transition to presentation."""

    def test_soft_close_transitions_no_price_question(self):
        """soft_close state should NOT have price_question → presentation transition."""
        import yaml

        states_path = Path(__file__).parent.parent / "src" / "yaml_config" / "flows" / "_base" / "states.yaml"
        with open(states_path) as f:
            config = yaml.safe_load(f)

        soft_close = config["states"]["soft_close"]
        transitions = soft_close.get("transitions", {})

        # These should NOT be in transitions (removed by Fix 4)
        assert "price_question" not in transitions, \
            "price_question should not be a transition in soft_close (Fix 4)"
        assert "pricing_details" not in transitions, \
            "pricing_details should not be a transition in soft_close (Fix 4)"
        assert "comparison" not in transitions, \
            "comparison should not be a transition in soft_close (Fix 4)"

    def test_soft_close_rules_still_handle_price(self):
        """soft_close rules still handle price_question with answer_with_facts."""
        import yaml

        states_path = Path(__file__).parent.parent / "src" / "yaml_config" / "flows" / "_base" / "states.yaml"
        with open(states_path) as f:
            config = yaml.safe_load(f)

        soft_close = config["states"]["soft_close"]
        rules = soft_close.get("rules", {})

        # Rules should still handle these intents
        assert rules.get("price_question") == "answer_with_facts"
        assert rules.get("pricing_details") == "answer_with_facts"
        assert rules.get("comparison") == "answer_and_continue"

    def test_soft_close_keeps_other_transitions(self):
        """soft_close still has transitions for agreement, demo_request, etc."""
        import yaml

        states_path = Path(__file__).parent.parent / "src" / "yaml_config" / "flows" / "_base" / "states.yaml"
        with open(states_path) as f:
            config = yaml.safe_load(f)

        soft_close = config["states"]["soft_close"]
        transitions = soft_close.get("transitions", {})

        # These should remain
        assert "agreement" in transitions
        assert "demo_request" in transitions
        assert "callback_request" in transitions
        assert "question_features" in transitions
        assert "question_integrations" in transitions
        assert "consultation_request" in transitions


# =============================================================================
# Fix 5: Disambiguation Data (visited_states / initial_state)
# =============================================================================

class TestFix5DisambiguationData:
    """Fix 5: Disambiguation return dicts include visited_states and initial_state."""

    def test_initiate_disambiguation_returns_visited_states(self):
        """_initiate_disambiguation returns visited_states and initial_state."""
        from unittest.mock import MagicMock

        # We test the structure by checking that bot.py has the right return fields
        # This is a structural test — verifying the code has the fix
        import inspect
        from bot import SalesBot

        source = inspect.getsource(SalesBot._initiate_disambiguation)
        assert '"visited_states"' in source or "'visited_states'" in source
        assert '"initial_state"' in source or "'initial_state'" in source

    def test_repeat_disambiguation_returns_visited_states(self):
        """_repeat_disambiguation_question returns visited_states and initial_state."""
        import inspect
        from bot import SalesBot

        source = inspect.getsource(SalesBot._repeat_disambiguation_question)
        assert '"visited_states"' in source or "'visited_states'" in source
        assert '"initial_state"' in source or "'initial_state'" in source

    def test_continue_with_classification_returns_visited_states(self):
        """_continue_with_classification main return includes visited_states."""
        import inspect
        from bot import SalesBot

        source = inspect.getsource(SalesBot._continue_with_classification)
        assert '"visited_states"' in source or "'visited_states'" in source
        assert '"initial_state"' in source or "'initial_state'" in source
        assert '"fallback_used"' in source or "'fallback_used'" in source
        assert '"fallback_tier"' in source or "'fallback_tier'" in source

    def test_continue_with_classification_close_return_has_data(self):
        """Close return path in _continue_with_classification includes tracking data."""
        import inspect
        from bot import SalesBot

        source = inspect.getsource(SalesBot._continue_with_classification)
        # The close return block should have visited_states
        assert source.count("visited_states") >= 2  # At least in close return and main return


# =============================================================================
# Fix 6: Skip Handling in _continue_with_classification
# =============================================================================

class TestFix6DisambiguationSkipHandling:
    """Fix 6: _continue_with_classification handles skip action from fallback."""

    def test_continue_with_classification_has_skip_handling(self):
        """_continue_with_classification has skip action handling code."""
        import inspect
        from bot import SalesBot

        source = inspect.getsource(SalesBot._continue_with_classification)
        # Should contain skip handling
        assert 'action") == "skip"' in source or "action\") == \"skip\"" in source
        assert "fallback_skip" in source
        assert "transition_to" in source

    def test_continue_with_classification_uses_current_intent_for_guard(self):
        """Guard in _continue_with_classification uses current intent (Fix 1+6)."""
        import inspect
        from bot import SalesBot

        source = inspect.getsource(SalesBot._continue_with_classification)
        # Should pass intent (not self.last_intent) to guard
        assert "last_intent=intent" in source

    def test_continue_with_classification_merges_extracted(self):
        """Fallback context in _continue_with_classification merges extracted data."""
        import inspect
        from bot import SalesBot

        source = inspect.getsource(SalesBot._continue_with_classification)
        # Should merge extracted with collected_data
        assert "**extracted" in source

    def test_continue_with_classification_records_progress(self):
        """_continue_with_classification calls guard.record_progress()."""
        import inspect
        from bot import SalesBot

        source = inspect.getsource(SalesBot._continue_with_classification)
        assert "record_progress" in source


# =============================================================================
# Integration Tests
# =============================================================================

class TestIntegrationFix1Fix2:
    """Integration: Fix 1 (intent-aware guard) + Fix 2 (validated skip)."""

    def test_engagement_intent_prevents_unnecessary_skip(self):
        """Engagement intent → guard returns TIER_2 not TIER_3 → no skip needed."""
        guard = ConversationGuard()
        # Build up to state_loop threshold
        for i in range(3):
            guard.check("same_state", f"msg{i}", {}, frustration_level=0, last_intent="unclear")

        # Now with engagement intent, guard should not trigger tier_3
        can_continue, intervention = guard.check(
            "same_state", "сколько стоит?", {}, frustration_level=0, last_intent="price_question"
        )
        assert intervention is None or intervention != "fallback_tier_3"

    def test_unclear_triggers_validated_skip(self):
        """Unclear intent → tier_3 → validated skip target (not blind default)."""
        flow = _make_mock_flow(
            states={
                "stateA": {"required_data": []},
                "stateB": {"required_data": ["need_field"]},  # NOT satisfied
                "stateC": {"required_data": []},  # Valid
            },
            skip_map={"stateA": "stateB", "stateB": "stateC"},
        )
        handler = FallbackHandler(flow=flow)

        response = handler.get_fallback(
            "fallback_tier_3", "stateA", {"collected_data": {}}
        )
        assert response.action == "skip"
        # Should skip stateB (unsatisfied) and go to stateC
        assert response.next_state == "stateC"


class TestIntegrationFix2Fix3:
    """Integration: Fix 2 (validated skip) + Fix 3 (tier_2 escalation)."""

    def test_tier2_escalation_uses_validated_skip(self):
        """After 3 consecutive tier_2, escalation to tier_3 uses validated skip."""
        flow = _make_mock_flow(
            states={
                "stateA": {"required_data": []},
                "stateB": {"required_data": []},
            },
            skip_map={"stateA": "stateB"},
        )
        handler = FallbackHandler(flow=flow)

        # 3 consecutive tier_2 in stateA
        handler.get_fallback("fallback_tier_2", "stateA", {"collected_data": {}})
        handler.get_fallback("fallback_tier_2", "stateA", {"collected_data": {}})
        r3 = handler.get_fallback("fallback_tier_2", "stateA", {"collected_data": {}})

        # Should escalate to skip with validated target
        assert r3.action == "skip"
        assert r3.next_state == "stateB"

    def test_tier2_escalation_with_no_valid_target_goes_to_tier2(self):
        """Tier_2 escalation → tier_3 → no valid target → falls to tier_2 options."""
        flow = _make_mock_flow(
            states={
                "stateA": {"required_data": []},
                "stateB": {"required_data": ["missing"]},
            },
            skip_map={"stateA": "stateB"},
        )
        handler = FallbackHandler(flow=flow)

        handler.get_fallback("fallback_tier_2", "stateA", {"collected_data": {}})
        handler.get_fallback("fallback_tier_2", "stateA", {"collected_data": {}})
        r3 = handler.get_fallback("fallback_tier_2", "stateA", {"collected_data": {}})

        # tier_3 has no valid target → falls to tier_2 options
        assert r3.action == "continue"


class TestIntegrationGuardConfigPassing:
    """Integration: GuardConfig flows from Guard to FallbackHandler."""

    def test_guard_config_passed_to_fallback_handler(self):
        """FallbackHandler accepts guard_config and uses max_consecutive_tier_2."""
        config = GuardConfig()
        config.max_consecutive_tier_2 = 5

        handler = FallbackHandler(guard_config=config)
        assert handler._max_consecutive_tier_2 == 5

    def test_default_threshold_without_guard_config(self):
        """Without guard_config, default threshold is 3."""
        handler = FallbackHandler()
        assert handler._max_consecutive_tier_2 == 3


# =============================================================================
# Regression Tests
# =============================================================================

class TestRegressionExistingBehavior:
    """Ensure existing behavior is not broken by the fixes."""

    def test_fallback_handler_init_still_works(self):
        """FallbackHandler initializes without errors."""
        handler = FallbackHandler()
        assert handler.stats.total_count == 0

    def test_fallback_handler_with_flow_still_works(self):
        """FallbackHandler with flow parameter still works."""
        flow = _make_mock_flow(
            states={"greeting": {"required_data": []}},
            skip_map={"greeting": "stateB"},
        )
        handler = FallbackHandler(flow=flow)
        assert handler._flow == flow
        assert handler._skip_map == flow.skip_map

    def test_tier_4_exit_still_works(self):
        """Tier 4 graceful exit still returns close action."""
        handler = FallbackHandler()
        response = handler.get_fallback("soft_close", "any_state")
        assert response.action == "close"
        assert response.next_state == "soft_close"

    def test_tier_1_rephrase_still_works(self):
        """Tier 1 rephrase still returns continue action."""
        handler = FallbackHandler()
        response = handler.get_fallback("fallback_tier_1", "spin_situation")
        assert response.message
        assert response.action == "continue"

    def test_tier_escalation_still_works(self):
        """Tier escalation sequence still works."""
        handler = FallbackHandler()
        assert handler.escalate_tier("fallback_tier_1") == "fallback_tier_2"
        assert handler.escalate_tier("fallback_tier_2") == "fallback_tier_3"
        assert handler.escalate_tier("fallback_tier_3") == "soft_close"

    def test_guard_still_detects_timeout(self):
        """Guard still detects timeout."""
        guard = ConversationGuard(GuardConfig(timeout_seconds=0))
        time.sleep(0.01)
        can_continue, intervention = guard.check("test", "test", {})
        assert not can_continue
        assert intervention == "soft_close"

    def test_guard_still_detects_max_turns(self):
        """Guard still detects max turns."""
        guard = ConversationGuard(GuardConfig(max_turns=2))
        guard.check("s1", "m1", {})
        guard.check("s2", "m2", {})
        can_continue, intervention = guard.check("s3", "m3", {})
        assert not can_continue
        assert intervention == "soft_close"

    def test_guard_record_progress_still_works(self):
        """Guard record_progress still works."""
        guard = ConversationGuard()
        guard.check("s1", "m1", {})
        guard.record_progress()
        assert guard._state.last_progress_turn == 1

    def test_guard_reset_still_works(self):
        """Guard reset still clears state."""
        guard = ConversationGuard()
        guard.check("s1", "m1", {})
        guard.reset()
        assert guard.turn_count == 0

    def test_fallback_stats_reset_still_works(self):
        """FallbackHandler reset clears consecutive tier_2 tracking."""
        handler = FallbackHandler()
        handler.get_fallback("fallback_tier_2", "stateA")
        handler.get_fallback("fallback_tier_2", "stateA")
        handler.reset()
        assert handler.stats.consecutive_tier_2_count == 0
        assert handler.stats.consecutive_tier_2_state is None

    def test_guard_frustration_tier3_still_works(self):
        """High frustration still triggers tier_3 for non-engagement intent."""
        guard = ConversationGuard()
        can_continue, intervention = guard.check(
            "some_state", "msg", {}, frustration_level=8, last_intent="unclear"
        )
        assert intervention == "fallback_tier_3"


# =============================================================================
# Bot Pipeline Tests (structural verification)
# =============================================================================

class TestBotPipelineOrder:
    """Verify bot.py process() has correct pipeline order after Fix 1."""

    def test_classification_before_guard_in_process(self):
        """In process(), classification comes before guard check."""
        import inspect
        from bot import SalesBot

        source = inspect.getsource(SalesBot.process)
        lines = source.split('\n')

        classify_line = None
        guard_line = None

        for i, line in enumerate(lines):
            if 'self.classifier.classify' in line and classify_line is None:
                classify_line = i
            if '_check_guard' in line and guard_line is None:
                guard_line = i

        assert classify_line is not None, "classifier.classify not found in process()"
        assert guard_line is not None, "_check_guard not found in process()"
        assert classify_line < guard_line, \
            f"Classification (line {classify_line}) should come before guard (line {guard_line})"

    def test_guard_uses_current_intent_in_process(self):
        """In process(), guard call uses `intent` not `self.last_intent`."""
        import inspect
        from bot import SalesBot

        source = inspect.getsource(SalesBot.process)
        # Find the guard call section and check it uses current intent
        # The fix changed last_intent=self.last_intent to last_intent=intent
        assert "last_intent=intent" in source

    def test_fallback_context_merges_extracted_in_process(self):
        """In process(), fallback context merges extracted data with collected_data."""
        import inspect
        from bot import SalesBot

        source = inspect.getsource(SalesBot.process)
        assert "**extracted" in source

    def test_bot_passes_guard_config_to_fallback(self):
        """SalesBot passes guard.config to FallbackHandler."""
        import inspect
        from bot import SalesBot

        source = inspect.getsource(SalesBot.__init__)
        assert "guard_config" in source


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
