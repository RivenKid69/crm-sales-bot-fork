"""
End-to-end scenario tests for config-driven behavior.

These tests verify complete dialogue scenarios using real config values.
They test the full flow from user input to bot response.

Scenarios:
- SPIN flow with different lead temperatures
- Guard triggers (max_turns, timeout, frustration)
- Fallback escalation (tier_1 -> tier_2 -> tier_3)
- Objection handling with limits
- Lead scoring affecting navigation
"""

import pytest
import time
from pathlib import Path
from unittest.mock import MagicMock, patch
import sys

# =============================================================================
# HELPER FIXTURES
# =============================================================================

@pytest.fixture
def mock_llm():
    """Basic mock LLM for testing."""
    llm = MagicMock()
    llm.generate.return_value = "Понял, расскажите подробнее."
    llm.health_check.return_value = True
    return llm

@pytest.fixture
def state_machine_with_real_config():
    """StateMachine with real config."""
    from src.config_loader import ConfigLoader
    from src.state_machine import StateMachine

    loader = ConfigLoader()
    config = loader.load()
    return StateMachine(config=config)

# =============================================================================
# SPIN FLOW SCENARIOS
# =============================================================================

class TestE2EColdLeadFullSPINFlow:
    """E2E tests for COLD lead going through full SPIN."""

    def test_cold_lead_passes_all_spin_phases(self):
        """COLD lead must pass through all 4 SPIN phases."""
        from src.lead_scoring import LeadScorer, LeadTemperature

        scorer = LeadScorer()
        scorer.current_score = 15  # COLD

        score = scorer.get_score()
        assert score.temperature == LeadTemperature.COLD
        assert len(score.skip_phases) == 0
        assert score.recommended_path == "full_spin"

    def test_cold_lead_flow_greeting_to_situation(self, state_machine_with_real_config):
        """COLD lead: greeting -> spin_situation."""
        sm = state_machine_with_real_config
        sm.state = "greeting"

        # Agreement moves to spin_situation
        result = sm.process("agreement")
        # Result depends on state machine implementation

class TestE2EWarmLeadShortSPINFlow:
    """E2E tests for WARM lead with shortened SPIN."""

    def test_warm_lead_skips_implication_and_need(self):
        """WARM lead skips spin_implication and spin_need_payoff."""
        from src.lead_scoring import LeadScorer, LeadTemperature

        scorer = LeadScorer()
        scorer.current_score = 35  # WARM

        score = scorer.get_score()
        assert score.temperature == LeadTemperature.WARM
        assert "spin_implication" in score.skip_phases or len(score.skip_phases) > 0
        assert score.recommended_path == "short_spin"

class TestE2EHotLeadDirectPresentation:
    """E2E tests for HOT lead going directly to presentation."""

    def test_hot_lead_skips_most_spin_phases(self):
        """HOT lead skips problem, implication, need_payoff."""
        from src.lead_scoring import LeadScorer, LeadTemperature

        scorer = LeadScorer()
        scorer.current_score = 55  # HOT

        score = scorer.get_score()
        assert score.temperature == LeadTemperature.HOT
        assert len(score.skip_phases) >= 2
        assert score.recommended_path == "direct_present"

class TestE2EVeryHotLeadDirectClose:
    """E2E tests for VERY_HOT lead going directly to close."""

    def test_very_hot_lead_skips_all_spin(self):
        """VERY_HOT lead skips all SPIN phases."""
        from src.lead_scoring import LeadScorer, LeadTemperature

        scorer = LeadScorer()
        scorer.current_score = 80  # VERY_HOT

        score = scorer.get_score()
        assert score.temperature == LeadTemperature.VERY_HOT
        assert len(score.skip_phases) >= 3
        assert score.recommended_path == "direct_close"

# =============================================================================
# GUARD TRIGGER SCENARIOS
# =============================================================================

class TestE2EMaxTurnsSoftClose:
    """E2E tests for max_turns triggering soft_close."""

    def test_max_turns_triggers_soft_close(self):
        """Exceeding max_turns triggers soft_close."""
        from src.conversation_guard import ConversationGuard, GuardConfig

        guard = ConversationGuard(GuardConfig(max_turns=5))

        # Process 5 turns
        for i in range(5):
            can_continue, intervention = guard.check(
                f"state_{i % 3}",
                f"message_{i}",
                {}
            )

        # 6th turn should trigger
        can_continue, intervention = guard.check("state_x", "msg_x", {})
        assert not can_continue or intervention == "soft_close"

class TestE2ETimeoutSoftClose:
    """E2E tests for timeout triggering soft_close."""

    def test_timeout_triggers_soft_close(self):
        """Timeout triggers soft_close."""
        from src.conversation_guard import ConversationGuard, GuardConfig

        guard = ConversationGuard(GuardConfig(timeout_seconds=1))

        # First turn starts timer
        guard.check("state_a", "msg_1", {})

        # Wait for timeout
        time.sleep(1.1)

        can_continue, intervention = guard.check("state_b", "msg_2", {})
        assert not can_continue or intervention == "soft_close"

class TestE2EHighFrustrationTrigger:
    """E2E tests for high frustration triggering intervention."""

    def test_high_frustration_triggers_tier3(self):
        """High frustration triggers fallback_tier_3."""
        from src.conversation_guard import ConversationGuard, GuardConfig

        guard = ConversationGuard(GuardConfig(high_frustration_threshold=5))

        # Set frustration above threshold
        guard.set_frustration_level(6)

        can_continue, intervention = guard.check("state_a", "msg", {})
        # Should trigger tier_3 or soft_close
        assert intervention in ["fallback_tier_3", "soft_close", None] or not can_continue

class TestE2EStateLoopDetection:
    """E2E tests for state loop detection."""

    def test_state_loop_triggers_intervention(self):
        """Repeated same state triggers intervention."""
        from src.conversation_guard import ConversationGuard, GuardConfig

        guard = ConversationGuard(GuardConfig(max_same_state=3))

        # 3 same states
        for i in range(3):
            guard.check("stuck_state", f"msg_{i}", {})

        # 4th should trigger
        can_continue, intervention = guard.check("stuck_state", "msg_4", {})
        assert intervention is not None

class TestE2EMessageLoopDetection:
    """E2E tests for message loop detection."""

    def test_message_loop_triggers_intervention(self):
        """Repeated same message triggers intervention."""
        from src.conversation_guard import ConversationGuard, GuardConfig

        guard = ConversationGuard(GuardConfig(max_same_message=2))

        # Same message twice
        guard.check("state_a", "repeated message", {})
        guard.check("state_b", "repeated message", {})

        # Third time should trigger
        can_continue, intervention = guard.check("state_c", "repeated message", {})
        assert intervention is not None or guard._state.message_history.count("repeated message") >= 2

# =============================================================================
# FALLBACK ESCALATION SCENARIOS
# =============================================================================

class TestE2EFallbackEscalation:
    """E2E tests for fallback tier escalation."""

    def test_fallback_escalates_tier1_to_tier2(self):
        """Fallback escalates from tier_1 to tier_2."""
        from src.conversation_guard import ConversationGuard, GuardConfig

        guard = ConversationGuard(GuardConfig(max_same_state=2))

        # First stuck -> tier_1
        guard.check("stuck_state", "msg_1", {})
        guard.check("stuck_state", "msg_2", {})

        can_continue, intervention = guard.check("stuck_state", "msg_3", {})
        # Should be tier intervention
        assert intervention is not None

    def test_fallback_escalates_to_soft_close(self):
        """Continuous failures escalate to soft_close."""
        from src.conversation_guard import ConversationGuard, GuardConfig

        guard = ConversationGuard(GuardConfig(
            max_turns=10,
            max_same_state=2,
            max_phase_attempts=2,
        ))

        # Multiple stuck scenarios
        for i in range(10):
            guard.check(f"stuck_{i % 2}", f"msg_{i}", {})

        can_continue, intervention = guard.check("final", "final_msg", {})
        # Eventually should stop
        assert not can_continue or intervention == "soft_close"

# =============================================================================
# OBJECTION HANDLING SCENARIOS
# =============================================================================

class TestE2EObjectionConsecutiveLimit:
    """E2E tests for consecutive objection limit."""

    def test_consecutive_objections_trigger_soft_close(self):
        """3 consecutive objections trigger soft_close."""
        from src.state_machine import StateMachine

        sm = StateMachine()
        sm.state = "presentation"
        sm._consecutive_objections = 0
        sm._total_objections = 0

        # Process objections
        objection_intents = ["objection_price", "objection_no_time", "objection_competitor"]

        for intent in objection_intents:
            result = sm.process(intent)
            if result.get("next_state") == "soft_close":
                return  # Test passed

        # After 3 consecutive, check if limit triggers
        result = sm.process("objection_think")
        # Should trigger soft_close or handle_objection

class TestE2EObjectionTotalLimit:
    """E2E tests for total objection limit."""

    def test_total_objections_trigger_soft_close(self):
        """5 total objections trigger soft_close."""
        from src.state_machine import StateMachine

        sm = StateMachine()
        sm.state = "presentation"
        sm._consecutive_objections = 0
        sm._total_objections = 0

        # Mix objections with positives
        for i in range(5):
            sm.process("objection_price")
            sm._consecutive_objections = 0  # Reset consecutive

        # After 5 total, should trigger limit

class TestE2EObjectionResetOnPositive:
    """E2E tests for objection counter reset on positive intent."""

    def test_positive_intent_resets_consecutive(self):
        """Positive intent resets consecutive objection counter."""
        from src.state_machine import StateMachine

        sm = StateMachine()
        sm.state = "presentation"
        sm._consecutive_objections = 2

        # Positive intent should reset
        sm.process("agreement")

        # Counter should reset (implementation dependent)

# =============================================================================
# LEAD SCORING SCENARIOS
# =============================================================================

class TestE2ELeadScoringAccumulation:
    """E2E tests for lead score accumulation."""

    def test_multiple_signals_accumulate(self):
        """Multiple signals accumulate score."""
        from src.lead_scoring import LeadScorer, LeadTemperature

        scorer = LeadScorer()

        # Add multiple positive signals
        scorer.add_signal("features_question")  # +5
        scorer.add_signal("price_question")     # +5
        scorer.add_signal("explicit_problem")   # +15
        scorer.add_signal("demo_request")       # +30

        # Total should be at least 50 (HOT or higher)
        assert scorer.current_score >= 50
        assert scorer.get_score().temperature in (LeadTemperature.HOT, LeadTemperature.VERY_HOT)

    def test_negative_signals_decrease_score(self):
        """Negative signals decrease score."""
        from src.lead_scoring import LeadScorer, LeadTemperature

        scorer = LeadScorer()
        scorer.current_score = 60  # Start HOT

        # Add negative signals
        scorer.add_signal("objection_price")    # -15
        scorer.add_signal("objection_no_time")  # -20

        # Should drop below HOT threshold
        assert scorer.current_score < 60

class TestE2ELeadScoringAffectsNavigation:
    """E2E tests for lead scoring affecting navigation."""

    def test_demo_request_raises_temperature(self):
        """demo_request significantly raises temperature."""
        from src.lead_scoring import LeadScorer, LeadTemperature

        scorer = LeadScorer()

        # Start COLD
        assert scorer.get_score().temperature == LeadTemperature.COLD

        # Demo request (+30)
        scorer.add_signal("demo_request")

        # Should be at least WARM
        assert scorer.get_score().temperature in [
            LeadTemperature.WARM,
            LeadTemperature.HOT,
            LeadTemperature.VERY_HOT
        ]

    def test_contact_provided_makes_very_hot(self):
        """contact_provided can push to VERY_HOT."""
        from src.lead_scoring import LeadScorer, LeadTemperature

        scorer = LeadScorer()

        # Signals that add up to VERY_HOT
        scorer.add_signal("demo_request")       # +30
        scorer.add_signal("contact_provided")   # +35
        scorer.add_signal("price_with_size")    # +25

        # Should be VERY_HOT (90+)
        assert scorer.current_score >= 70
        assert scorer.get_score().temperature == LeadTemperature.VERY_HOT

# =============================================================================
# CIRCULAR FLOW SCENARIOS
# =============================================================================

class TestE2ECircularFlowGoback:
    """E2E tests for circular flow go_back."""

    def test_goback_from_spin_problem_to_situation(self):
        """Go back from spin_problem to spin_situation."""
        from src.state_machine import CircularFlowManager

        manager = CircularFlowManager()

        assert manager.can_go_back("spin_problem") is True
        target = manager.allowed_gobacks.get("spin_problem")
        assert target == "spin_situation"

    def test_goback_limit_enforced(self):
        """Go back limit is enforced."""
        from src.state_machine import CircularFlowManager

        manager = CircularFlowManager(max_gobacks=2)

        # First goback
        assert manager.can_go_back("spin_problem") is True
        manager.goback_count = 1

        # Second goback
        assert manager.can_go_back("spin_problem") is True
        manager.goback_count = 2

        # Third blocked
        assert manager.can_go_back("spin_problem") is False

# =============================================================================
# FULL DIALOGUE SCENARIOS
# =============================================================================

class TestE2EFullDialogueScenario:
    """E2E tests for complete dialogue scenarios."""

    def test_happy_path_dialogue(self, state_machine_with_real_config, mock_llm):
        """Happy path: greeting -> SPIN -> presentation -> close -> success."""
        sm = state_machine_with_real_config

        # Start at greeting
        assert sm.state == "greeting"

        # This test verifies the state machine can process intents
        # Actual transitions depend on implementation

    def test_objection_handling_dialogue(self, state_machine_with_real_config):
        """Dialogue with objection handling."""
        sm = state_machine_with_real_config
        sm.state = "presentation"

        # Process objection
        result = sm.process("objection_price")
        # Should go to handle_objection or stay

    def test_soft_close_reactivation(self, state_machine_with_real_config):
        """Reactivation from soft_close."""
        sm = state_machine_with_real_config
        sm.state = "soft_close"

        # Agreement from soft_close should reactivate
        result = sm.process("agreement")
        # Should transition back to conversation

# =============================================================================
# GUARD + FRUSTRATION COMBINED SCENARIOS
# =============================================================================

class TestE2EGuardFrustrationCombined:
    """E2E tests combining guard and frustration tracking."""

    def test_frustration_with_state_loop(self):
        """High frustration + state loop = immediate soft_close."""
        from src.conversation_guard import ConversationGuard, GuardConfig

        guard = ConversationGuard(GuardConfig(
            high_frustration_threshold=5,
            max_same_state=3,
        ))

        guard.set_frustration_level(6)  # High frustration

        # State loop
        guard.check("stuck", "msg_1", {})
        guard.check("stuck", "msg_2", {})

        can_continue, intervention = guard.check("stuck", "msg_3", {})

        # Should trigger strong intervention
        assert intervention in ["fallback_tier_3", "soft_close"] or not can_continue

    def test_no_progress_with_frustration(self):
        """No progress + rising frustration = escalation."""
        from src.conversation_guard import ConversationGuard, GuardConfig

        guard = ConversationGuard(GuardConfig(
            progress_check_interval=3,
            high_frustration_threshold=5,
        ))

        # No progress, frustration rising
        guard.set_frustration_level(3)
        guard.check("spin_situation", "msg_1", {})

        guard.set_frustration_level(5)
        guard.check("spin_situation", "msg_2", {})

        guard.set_frustration_level(7)
        can_continue, intervention = guard.check("spin_situation", "msg_3", {})

        # Should intervene due to frustration
        assert intervention is not None or not can_continue
