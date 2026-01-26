"""
Integration tests for pre_intervention_triggered propagation through system.

These tests verify that the pre_intervention_triggered flag is correctly
propagated from FrustrationIntensityCalculator through all system components:
- ContextEnvelope
- PolicyContext / FallbackContext / PersonalizationContext
- Condition functions
- ConversationGuard
- apology_ssot
"""
import pytest

from src.context_envelope import ContextEnvelope, ContextEnvelopeBuilder
from src.conditions.policy.context import PolicyContext
from src.conditions.fallback.context import FallbackContext
from src.conditions.personalization.context import PersonalizationContext
from src.conditions.policy.conditions import has_guard_intervention, has_pre_intervention
from src.conditions.fallback.conditions import needs_immediate_escalation, should_offer_graceful_exit
from src.conditions.personalization.conditions import needs_soft_approach, should_be_conservative
from src.conversation_guard import ConversationGuard, GuardConfig
from src.apology_ssot import should_offer_exit


class TestContextEnvelopePropagation:
    """Test pre_intervention propagation through ContextEnvelope."""

    def test_envelope_receives_pre_intervention_from_tone_info(self):
        """ContextEnvelope should receive pre_intervention_triggered from tone_info."""
        # Use builder without state_machine/context_window (they have defaults)
        builder = ContextEnvelopeBuilder(
            tone_info={"frustration_level": 5, "pre_intervention_triggered": True},
            guard_info={},
        )
        envelope = builder.build()
        assert envelope.pre_intervention_triggered is True

    def test_envelope_defaults_to_false(self):
        """ContextEnvelope should default pre_intervention_triggered to False."""
        builder = ContextEnvelopeBuilder(
            tone_info={"frustration_level": 3},
            guard_info={},
        )
        envelope = builder.build()
        assert envelope.pre_intervention_triggered is False

    def test_envelope_for_policy_includes_pre_intervention(self):
        """for_policy() should include pre_intervention_triggered."""
        envelope = ContextEnvelope()
        envelope.pre_intervention_triggered = True
        policy_dict = envelope.for_policy()
        assert "pre_intervention_triggered" in policy_dict
        assert policy_dict["pre_intervention_triggered"] is True

    def test_envelope_to_dict_includes_pre_intervention(self):
        """to_dict() should include pre_intervention_triggered."""
        envelope = ContextEnvelope()
        envelope.pre_intervention_triggered = True
        result = envelope.to_dict()
        assert "pre_intervention_triggered" in result
        assert result["pre_intervention_triggered"] is True


class TestPolicyContextPropagation:
    """Test pre_intervention propagation through PolicyContext."""

    def test_policy_context_from_envelope(self):
        """PolicyContext should receive pre_intervention from envelope."""
        envelope = ContextEnvelope()
        envelope.pre_intervention_triggered = True
        ctx = PolicyContext.from_envelope(envelope)
        assert ctx.pre_intervention_triggered is True

    def test_policy_context_test_context_factory(self):
        """create_test_context should support pre_intervention_triggered."""
        ctx = PolicyContext.create_test_context(pre_intervention_triggered=True)
        assert ctx.pre_intervention_triggered is True

    def test_has_guard_intervention_with_pre_intervention(self):
        """has_guard_intervention should return True with pre_intervention."""
        ctx = PolicyContext.create_test_context(
            guard_intervention=None,  # No guard intervention
            pre_intervention_triggered=True,
        )
        assert has_guard_intervention(ctx) is True

    def test_has_guard_intervention_without_pre_intervention(self):
        """has_guard_intervention should return False without either flag."""
        ctx = PolicyContext.create_test_context(
            guard_intervention=None,
            pre_intervention_triggered=False,
        )
        assert has_guard_intervention(ctx) is False

    def test_has_pre_intervention_condition(self):
        """has_pre_intervention should return True when flag is set."""
        ctx = PolicyContext.create_test_context(pre_intervention_triggered=True)
        assert has_pre_intervention(ctx) is True

    def test_has_pre_intervention_false(self):
        """has_pre_intervention should return False when flag is not set."""
        ctx = PolicyContext.create_test_context(pre_intervention_triggered=False)
        assert has_pre_intervention(ctx) is False


class TestFallbackContextPropagation:
    """Test pre_intervention propagation through FallbackContext."""

    def test_fallback_context_test_context_factory(self):
        """create_test_context should support pre_intervention_triggered."""
        ctx = FallbackContext.create_test_context(pre_intervention_triggered=True)
        assert ctx.pre_intervention_triggered is True

    def test_needs_immediate_escalation_with_pre_intervention(self):
        """needs_immediate_escalation should return True with pre_intervention."""
        ctx = FallbackContext.create_test_context(
            frustration_level=3,  # Below HIGH threshold (7)
            pre_intervention_triggered=True,
        )
        assert needs_immediate_escalation(ctx) is True

    def test_needs_immediate_escalation_without_flags(self):
        """needs_immediate_escalation should use normal logic without flags."""
        ctx = FallbackContext.create_test_context(
            frustration_level=3,  # Below HIGH threshold
            pre_intervention_triggered=False,
            consecutive_fallbacks=1,  # Not enough for escalation
        )
        assert needs_immediate_escalation(ctx) is False

    def test_should_offer_graceful_exit_with_pre_intervention(self):
        """should_offer_graceful_exit should return True with pre_intervention."""
        ctx = FallbackContext.create_test_context(
            frustration_level=2,  # Well below WARNING threshold
            pre_intervention_triggered=True,
        )
        assert should_offer_graceful_exit(ctx) is True


class TestPersonalizationContextPropagation:
    """Test pre_intervention propagation through PersonalizationContext."""

    def test_personalization_context_test_context_factory(self):
        """create_test_context should support pre_intervention_triggered."""
        ctx = PersonalizationContext.create_test_context(pre_intervention_triggered=True)
        assert ctx.pre_intervention_triggered is True

    def test_should_skip_cta_with_pre_intervention(self):
        """should_skip_cta should return True with pre_intervention."""
        ctx = PersonalizationContext.create_test_context(
            frustration_level=0,  # Low frustration
            pre_intervention_triggered=True,
        )
        assert ctx.should_skip_cta() is True

    def test_should_skip_cta_without_flags(self):
        """should_skip_cta should use normal logic without flags."""
        ctx = PersonalizationContext.create_test_context(
            frustration_level=0,
            pre_intervention_triggered=False,
        )
        assert ctx.should_skip_cta() is False

    def test_needs_soft_approach_with_pre_intervention(self):
        """needs_soft_approach should return True with pre_intervention."""
        ctx = PersonalizationContext.create_test_context(
            frustration_level=0,
            momentum_direction="positive",
            engagement_level="high",
            pre_intervention_triggered=True,
        )
        assert needs_soft_approach(ctx) is True

    def test_should_be_conservative_with_pre_intervention(self):
        """should_be_conservative should return True with pre_intervention."""
        ctx = PersonalizationContext.create_test_context(
            frustration_level=0,
            momentum_direction="positive",
            engagement_level="high",
            total_objections=0,
            pre_intervention_triggered=True,
        )
        assert should_be_conservative(ctx) is True


class TestConversationGuardPropagation:
    """Test pre_intervention handling in ConversationGuard."""

    def test_guard_check_with_pre_intervention(self):
        """ConversationGuard.check() should respond to pre_intervention."""
        guard = ConversationGuard(GuardConfig())
        can_continue, intervention = guard.check(
            state="presentation",
            message="test",
            collected_data={},
            frustration_level=3,  # Below threshold
            pre_intervention_triggered=True,
        )
        # Should return tier_3 (high frustration handling)
        assert intervention == "fallback_tier_3"

    def test_guard_check_without_pre_intervention(self):
        """ConversationGuard.check() should work normally without pre_intervention."""
        guard = ConversationGuard(GuardConfig())
        can_continue, intervention = guard.check(
            state="presentation",
            message="test",
            collected_data={},
            frustration_level=3,
            pre_intervention_triggered=False,
        )
        # Normal check - no intervention
        assert intervention is None


class TestApologySSoTPropagation:
    """Test pre_intervention handling in apology_ssot."""

    def test_should_offer_exit_with_pre_intervention(self):
        """should_offer_exit should return True with pre_intervention."""
        result = should_offer_exit(
            frustration_level=3,  # Below exit threshold (7)
            pre_intervention_triggered=True,
        )
        assert result is True

    def test_should_offer_exit_without_pre_intervention(self):
        """should_offer_exit should use normal logic without pre_intervention."""
        result = should_offer_exit(
            frustration_level=3,
            pre_intervention_triggered=False,
        )
        assert result is False

    def test_should_offer_exit_high_frustration_no_pre_intervention(self):
        """should_offer_exit should return True at high frustration."""
        result = should_offer_exit(
            frustration_level=7,  # At exit threshold
            pre_intervention_triggered=False,
        )
        assert result is True


class TestEndToEndScenario:
    """Test complete end-to-end scenarios."""

    def test_pre_intervention_triggers_all_protective_measures(self):
        """When pre_intervention is triggered, all protective measures activate."""
        # Simulate FrustrationIntensityCalculator setting pre_intervention
        tone_info = {
            "frustration_level": 5,  # WARNING level
            "pre_intervention_triggered": True,
            "tone": "RUSHED",
        }

        # Build envelope (without mocks - builder has defaults)
        builder = ContextEnvelopeBuilder(
            tone_info=tone_info,
            guard_info={},
        )
        envelope = builder.build()

        # Verify envelope received the flag
        assert envelope.pre_intervention_triggered is True

        # Create contexts from envelope
        policy_ctx = PolicyContext.from_envelope(envelope)
        assert policy_ctx.pre_intervention_triggered is True
        assert has_guard_intervention(policy_ctx) is True

        # Fallback context
        fallback_ctx = FallbackContext.create_test_context(
            frustration_level=envelope.frustration_level,
            pre_intervention_triggered=envelope.pre_intervention_triggered,
        )
        assert needs_immediate_escalation(fallback_ctx) is True
        assert should_offer_graceful_exit(fallback_ctx) is True

        # Personalization context
        pers_ctx = PersonalizationContext.create_test_context(
            frustration_level=envelope.frustration_level,
            pre_intervention_triggered=envelope.pre_intervention_triggered,
        )
        assert pers_ctx.should_skip_cta() is True
        assert needs_soft_approach(pers_ctx) is True
        assert should_be_conservative(pers_ctx) is True

        # Guard check
        guard = ConversationGuard(GuardConfig())
        _, intervention = guard.check(
            state="presentation",
            message="test",
            collected_data={},
            frustration_level=envelope.frustration_level,
            pre_intervention_triggered=envelope.pre_intervention_triggered,
        )
        assert intervention == "fallback_tier_3"

        # Apology SSoT
        assert should_offer_exit(
            envelope.frustration_level,
            envelope.pre_intervention_triggered
        ) is True

    def test_without_pre_intervention_normal_behavior(self):
        """Without pre_intervention, system uses normal frustration thresholds."""
        tone_info = {
            "frustration_level": 5,  # WARNING level but no pre_intervention
            "pre_intervention_triggered": False,
        }

        builder = ContextEnvelopeBuilder(
            tone_info=tone_info,
            guard_info={},
        )
        envelope = builder.build()

        assert envelope.pre_intervention_triggered is False

        # Policy context - no guard intervention at level 5
        policy_ctx = PolicyContext.from_envelope(envelope)
        # guard_intervention is None and pre_intervention_triggered is False
        # So has_guard_intervention should check only guard_intervention
        assert policy_ctx.guard_intervention is None
        assert policy_ctx.pre_intervention_triggered is False

        # Fallback - frustration 5 is below HIGH threshold (7)
        fallback_ctx = FallbackContext.create_test_context(
            frustration_level=5,
            pre_intervention_triggered=False,
        )
        assert needs_immediate_escalation(fallback_ctx) is False

        # Personalization - frustration 5 is below NO_CTA threshold (7)
        pers_ctx = PersonalizationContext.create_test_context(
            frustration_level=5,
            pre_intervention_triggered=False,
        )
        assert pers_ctx.should_skip_cta() is False

        # Guard - frustration 5 is below high_frustration_threshold (7)
        guard = ConversationGuard(GuardConfig())
        _, intervention = guard.check(
            state="presentation",
            message="test",
            collected_data={},
            frustration_level=5,
            pre_intervention_triggered=False,
        )
        assert intervention is None

        # Apology - frustration 5 is below exit threshold (7)
        assert should_offer_exit(5, False) is False
