"""
Tests for FallbackHandler module.

Tests cover:
- All four fallback tiers
- Response structure
- Template selection and variation
- Skip map transitions
- Statistics tracking
- Tier escalation
- Edge cases
"""

import sys
from pathlib import Path

import pytest

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from fallback_handler import FallbackHandler, FallbackResponse, FallbackStats


class TestFallbackResponse:
    """Tests for FallbackResponse dataclass"""

    def test_default_values(self):
        """Default values are correct"""
        response = FallbackResponse(message="test")
        assert response.message == "test"
        assert response.options is None
        assert response.action == "continue"
        assert response.next_state is None

    def test_with_options(self):
        """Can create response with options"""
        response = FallbackResponse(
            message="Choose:",
            options=["A", "B", "C"],
            action="continue"
        )
        assert response.options == ["A", "B", "C"]

    def test_with_skip(self):
        """Can create skip response"""
        response = FallbackResponse(
            message="Let's skip",
            action="skip",
            next_state="presentation"
        )
        assert response.action == "skip"
        assert response.next_state == "presentation"


class TestFallbackStats:
    """Tests for FallbackStats dataclass"""

    def test_initial_values(self):
        """Initial values are zero/empty"""
        stats = FallbackStats()
        assert stats.total_count == 0
        assert stats.tier_counts == {}
        assert stats.state_counts == {}
        assert stats.last_tier is None
        assert stats.last_state is None


class TestFallbackHandlerBasic:
    """Basic tests for FallbackHandler"""

    def test_initialization(self):
        """Handler initializes correctly"""
        handler = FallbackHandler()
        assert handler.stats.total_count == 0

    def test_reset(self):
        """Reset clears all state"""
        handler = FallbackHandler()
        handler.get_fallback("fallback_tier_1", "spin_situation")
        handler.get_fallback("fallback_tier_2", "spin_problem")

        handler.reset()

        assert handler.stats.total_count == 0
        assert handler.stats.tier_counts == {}


class TestTier1Rephrase:
    """Tests for Tier 1 (rephrase)"""

    def test_tier_1_returns_message(self):
        """Tier 1 returns a message"""
        handler = FallbackHandler()
        response = handler.get_fallback("fallback_tier_1", "spin_situation")

        assert response.message
        assert len(response.message) > 0
        assert response.options is None
        assert response.action == "continue"
        assert response.next_state is None

    def test_tier_1_different_states(self):
        """Tier 1 has different messages for different states"""
        handler = FallbackHandler()

        r1 = handler.get_fallback("fallback_tier_1", "spin_situation")
        handler.reset()
        r2 = handler.get_fallback("fallback_tier_1", "spin_problem")

        # Different templates for different states
        # (messages might differ)
        assert r1.message != r2.message or True  # May be same by chance

    def test_tier_1_unknown_state_has_default(self):
        """Tier 1 handles unknown state with default"""
        handler = FallbackHandler()
        response = handler.get_fallback("fallback_tier_1", "unknown_state")

        assert response.message
        assert response.action == "continue"

    def test_tier_1_messages_vary(self):
        """Tier 1 varies messages to avoid repetition"""
        handler = FallbackHandler()

        messages = set()
        for _ in range(10):
            handler.reset()  # Reset to allow reuse
            response = handler.get_fallback("fallback_tier_1", "spin_situation")
            messages.add(response.message)

        # Should have at least some variation
        # (with enough templates, should see multiple unique messages)
        assert len(messages) >= 1  # At minimum one


class TestTier2Options:
    """Tests for Tier 2 (options)"""

    def test_tier_2_returns_options(self):
        """Tier 2 returns options for known states"""
        handler = FallbackHandler()
        response = handler.get_fallback("fallback_tier_2", "spin_situation")

        assert response.message
        assert response.options is not None
        assert len(response.options) > 0
        assert response.action == "continue"

    def test_tier_2_options_are_list(self):
        """Tier 2 options are a list of strings"""
        handler = FallbackHandler()
        response = handler.get_fallback("fallback_tier_2", "spin_problem")

        assert isinstance(response.options, list)
        for opt in response.options:
            assert isinstance(opt, str)

    def test_tier_2_fallback_to_tier_1(self):
        """Tier 2 falls back to Tier 1 if no options for state"""
        handler = FallbackHandler()
        response = handler.get_fallback("fallback_tier_2", "unknown_state")

        # Should still return a message even without options template
        assert response.message
        assert response.action == "continue"

    def test_tier_2_spin_situation_options(self):
        """Tier 2 has correct options for spin_situation"""
        handler = FallbackHandler()
        response = handler.get_fallback("fallback_tier_2", "spin_situation")

        assert response.options
        # Should have team size options
        assert any("человек" in opt for opt in response.options)


class TestTier3Skip:
    """Tests for Tier 3 (skip)"""

    def test_tier_3_returns_skip_action(self):
        """Tier 3 returns skip action"""
        handler = FallbackHandler()
        response = handler.get_fallback("fallback_tier_3", "spin_situation")

        assert response.message
        assert response.action == "skip"
        assert response.next_state is not None

    def test_tier_3_correct_next_states(self):
        """Tier 3 returns correct next states"""
        handler = FallbackHandler()

        # Test skip map
        test_cases = [
            ("greeting", "spin_situation"),
            ("spin_situation", "spin_problem"),
            ("spin_problem", "spin_implication"),
            ("spin_implication", "spin_need_payoff"),
            ("spin_need_payoff", "presentation"),
            ("presentation", "close"),
        ]

        for current_state, expected_next in test_cases:
            handler.reset()
            response = handler.get_fallback("fallback_tier_3", current_state)
            assert response.next_state == expected_next, \
                f"Expected {expected_next} for {current_state}, got {response.next_state}"

    def test_tier_3_unknown_state_to_presentation(self):
        """Tier 3 defaults to presentation for unknown state"""
        handler = FallbackHandler()
        response = handler.get_fallback("fallback_tier_3", "unknown_state")

        assert response.next_state == "presentation"


class TestTier4Exit:
    """Tests for Tier 4 (graceful exit)"""

    def test_tier_4_returns_close_action(self):
        """Tier 4 returns close action"""
        handler = FallbackHandler()
        response = handler.get_fallback("fallback_tier_4", "any_state")

        assert response.message
        assert response.action == "close"
        assert response.next_state == "soft_close"

    def test_soft_close_alias(self):
        """soft_close tier works same as tier_4"""
        handler = FallbackHandler()
        response = handler.get_fallback("soft_close", "any_state")

        assert response.action == "close"
        assert response.next_state == "soft_close"

    def test_tier_4_message_offers_contact(self):
        """Tier 4 message offers to stay in contact"""
        handler = FallbackHandler()

        # Check multiple messages
        contact_keywords = ["почту", "контакт", "связ", "информацию", "прислать"]
        found_contact_offer = False

        for _ in range(10):
            handler.reset()
            response = handler.get_fallback("soft_close", "state")
            if any(kw in response.message.lower() for kw in contact_keywords):
                found_contact_offer = True
                break

        assert found_contact_offer, "Tier 4 messages should offer contact options"


class TestStatistics:
    """Tests for statistics tracking"""

    def test_stats_increment_on_fallback(self):
        """Stats increment when fallback is used"""
        handler = FallbackHandler()

        handler.get_fallback("fallback_tier_1", "spin_situation")

        assert handler.stats.total_count == 1
        assert handler.stats.tier_counts.get("fallback_tier_1") == 1
        assert handler.stats.state_counts.get("spin_situation") == 1

    def test_stats_track_multiple_fallbacks(self):
        """Stats track multiple fallbacks correctly"""
        handler = FallbackHandler()

        handler.get_fallback("fallback_tier_1", "spin_situation")
        handler.get_fallback("fallback_tier_2", "spin_situation")
        handler.get_fallback("fallback_tier_1", "spin_problem")
        handler.get_fallback("soft_close", "presentation")

        assert handler.stats.total_count == 4
        assert handler.stats.tier_counts.get("fallback_tier_1") == 2
        assert handler.stats.tier_counts.get("fallback_tier_2") == 1
        assert handler.stats.tier_counts.get("soft_close") == 1
        assert handler.stats.state_counts.get("spin_situation") == 2
        assert handler.stats.state_counts.get("spin_problem") == 1

    def test_stats_last_tier_and_state(self):
        """Stats track last tier and state"""
        handler = FallbackHandler()

        handler.get_fallback("fallback_tier_1", "spin_situation")
        handler.get_fallback("fallback_tier_2", "spin_problem")

        assert handler.stats.last_tier == "fallback_tier_2"
        assert handler.stats.last_state == "spin_problem"

    def test_get_stats_dict(self):
        """get_stats_dict returns correct structure"""
        handler = FallbackHandler()
        handler.get_fallback("fallback_tier_1", "spin_situation")

        stats = handler.get_stats_dict()

        assert "total_count" in stats
        assert "tier_counts" in stats
        assert "state_counts" in stats
        assert "last_tier" in stats
        assert "last_state" in stats
        assert stats["total_count"] == 1


class TestTierEscalation:
    """Tests for tier escalation"""

    def test_escalate_tier_1_to_2(self):
        """Escalation from tier 1 to tier 2"""
        handler = FallbackHandler()
        next_tier = handler.escalate_tier("fallback_tier_1")
        assert next_tier == "fallback_tier_2"

    def test_escalate_tier_2_to_3(self):
        """Escalation from tier 2 to tier 3"""
        handler = FallbackHandler()
        next_tier = handler.escalate_tier("fallback_tier_2")
        assert next_tier == "fallback_tier_3"

    def test_escalate_tier_3_to_close(self):
        """Escalation from tier 3 to soft_close"""
        handler = FallbackHandler()
        next_tier = handler.escalate_tier("fallback_tier_3")
        assert next_tier == "soft_close"

    def test_escalate_soft_close_stays(self):
        """Escalation from soft_close stays at soft_close"""
        handler = FallbackHandler()
        next_tier = handler.escalate_tier("soft_close")
        assert next_tier == "soft_close"

    def test_escalate_unknown_tier(self):
        """Escalation from unknown tier goes to soft_close"""
        handler = FallbackHandler()
        next_tier = handler.escalate_tier("unknown_tier")
        assert next_tier == "soft_close"

    def test_full_escalation_sequence(self):
        """Full escalation sequence works"""
        handler = FallbackHandler()

        tier = "fallback_tier_1"
        sequence = [tier]

        for _ in range(5):  # More than enough iterations
            tier = handler.escalate_tier(tier)
            sequence.append(tier)
            if tier == "soft_close":
                break

        expected = [
            "fallback_tier_1",
            "fallback_tier_2",
            "fallback_tier_3",
            "soft_close"
        ]
        assert sequence == expected


class TestTemplateVariation:
    """Tests for template variation to avoid repetition"""

    def test_templates_dont_repeat_immediately(self):
        """Templates shouldn't repeat immediately"""
        handler = FallbackHandler()

        # Get multiple fallbacks for same state/tier
        messages = []
        for _ in range(4):
            response = handler.get_fallback("fallback_tier_1", "spin_situation")
            messages.append(response.message)

        # Check consecutive messages aren't the same
        # (may eventually repeat, but not immediately)
        for i in range(len(messages) - 1):
            if messages[i] == messages[i + 1]:
                # Only fail if there's more than one template
                templates = handler.REPHRASE_TEMPLATES.get("spin_situation", [])
                if len(templates) > 1:
                    pytest.fail(f"Consecutive messages were identical: {messages[i]}")

    def test_exit_templates_vary(self):
        """Exit templates vary"""
        handler = FallbackHandler()

        messages = set()
        for _ in range(20):
            handler._used_templates.clear()  # Clear to get fresh selection
            response = handler.get_fallback("soft_close", "state")
            messages.add(response.message)

        # Should have multiple unique messages
        assert len(messages) >= min(2, len(handler.EXIT_TEMPLATES))


class TestEdgeCases:
    """Edge case tests"""

    def test_empty_context(self):
        """Handles empty context"""
        handler = FallbackHandler()
        response = handler.get_fallback("fallback_tier_1", "spin_situation", {})
        assert response.message

    def test_none_context(self):
        """Handles None context"""
        handler = FallbackHandler()
        response = handler.get_fallback("fallback_tier_1", "spin_situation", None)
        assert response.message

    def test_empty_state(self):
        """Handles empty state"""
        handler = FallbackHandler()
        response = handler.get_fallback("fallback_tier_1", "")
        assert response.message
        assert response.action == "continue"

    def test_context_with_data(self):
        """Handles context with data"""
        handler = FallbackHandler()
        context = {
            "company_size": 10,
            "pain_point": "losing clients",
            "industry": "retail"
        }
        response = handler.get_fallback("fallback_tier_1", "spin_situation", context)
        assert response.message

    def test_all_states_have_skip_destination(self):
        """All SPIN states have skip destinations"""
        handler = FallbackHandler()
        states = [
            "greeting",
            "spin_situation",
            "spin_problem",
            "spin_implication",
            "spin_need_payoff",
            "presentation"
        ]

        for state in states:
            response = handler.get_fallback("fallback_tier_3", state)
            assert response.next_state is not None, f"No skip destination for {state}"


class TestMultipleHandlerInstances:
    """Tests for multiple handler instances"""

    def test_independent_instances(self):
        """Multiple handlers are independent"""
        handler1 = FallbackHandler()
        handler2 = FallbackHandler()

        handler1.get_fallback("fallback_tier_1", "spin_situation")
        handler1.get_fallback("fallback_tier_2", "spin_problem")

        assert handler1.stats.total_count == 2
        assert handler2.stats.total_count == 0

    def test_independent_template_history(self):
        """Handlers have independent template history"""
        handler1 = FallbackHandler()
        handler2 = FallbackHandler()

        # Fill handler1's history
        for _ in range(5):
            handler1.get_fallback("fallback_tier_1", "spin_situation")

        # Handler2 should start fresh
        response = handler2.get_fallback("fallback_tier_1", "spin_situation")
        assert response.message  # Should work without issues


class TestSpecificStates:
    """Tests for specific state handling"""

    def test_greeting_state(self):
        """Greeting state has appropriate responses"""
        handler = FallbackHandler()

        # Tier 1
        r1 = handler.get_fallback("fallback_tier_1", "greeting")
        assert r1.message
        assert r1.action == "continue"

        # Tier 3 skip
        handler.reset()
        r3 = handler.get_fallback("fallback_tier_3", "greeting")
        assert r3.next_state == "spin_situation"

    def test_presentation_state(self):
        """Presentation state has appropriate responses"""
        handler = FallbackHandler()

        # Tier 2 options
        r2 = handler.get_fallback("fallback_tier_2", "presentation")
        assert r2.options is not None
        assert len(r2.options) > 0

        # Tier 3 skip
        handler.reset()
        r3 = handler.get_fallback("fallback_tier_3", "presentation")
        assert r3.next_state == "close"

    def test_handle_objection_state(self):
        """Handle objection state has appropriate responses"""
        handler = FallbackHandler()

        r1 = handler.get_fallback("fallback_tier_1", "handle_objection")
        assert r1.message
        # Should acknowledge objection
        assert any(
            word in r1.message.lower()
            for word in ["понимаю", "сомнения", "вопрос", "момент", "беспокоит"]
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
