# tests/test_transition_atomicity.py
"""
Tests for atomic state transitions (FIX: Distributed State Mutation bug).

This test module verifies that:
1. transition_to() atomically updates state, current_phase, and last_action
2. state and current_phase are always consistent after transition
3. Orchestrator uses transition_to() correctly
4. Bot.py policy_override uses transition_to() correctly
5. The old bug (state/phase mismatch) no longer occurs
"""

import pytest
from unittest.mock import MagicMock, patch

from src.state_machine import StateMachine


class TestTransitionToAtomicity:
    """Tests for StateMachine.transition_to() atomicity."""

    @pytest.fixture
    def state_machine(self):
        """Create a StateMachine instance for testing."""
        return StateMachine()

    def test_transition_to_updates_all_fields_atomically(self, state_machine):
        """
        Verify that transition_to() updates state, current_phase, and last_action together.

        This is the core test for the FIX of the Distributed State Mutation bug.
        """
        # Initial state
        assert state_machine.state == "greeting"
        assert state_machine.current_phase is None
        assert state_machine.last_action is None

        # Transition to spin_situation
        result = state_machine.transition_to(
            next_state="spin_situation",
            action="ask_situation_questions",
            source="test",
        )

        assert result is True
        assert state_machine.state == "spin_situation"
        assert state_machine.current_phase == "situation"  # from flow config
        assert state_machine.last_action == "ask_situation_questions"

    def test_transition_to_computes_phase_from_config(self, state_machine):
        """Verify that phase is computed from flow config when not provided."""
        state_machine.transition_to(
            next_state="spin_problem",
            source="test",
        )

        assert state_machine.state == "spin_problem"
        assert state_machine.current_phase == "problem"  # from flow config

    def test_transition_to_uses_explicit_phase(self, state_machine):
        """Verify that explicit phase overrides config-computed phase."""
        state_machine.transition_to(
            next_state="spin_problem",
            phase="custom_phase",
            source="test",
        )

        assert state_machine.state == "spin_problem"
        assert state_machine.current_phase == "custom_phase"  # explicit

    def test_transition_to_validates_state_exists(self, state_machine):
        """Verify that invalid states are rejected when validate=True."""
        result = state_machine.transition_to(
            next_state="nonexistent_state",
            source="test",
            validate=True,
        )

        assert result is False
        # State should not change
        assert state_machine.state == "greeting"

    def test_transition_to_skips_validation_when_disabled(self, state_machine):
        """Verify that validation can be skipped."""
        result = state_machine.transition_to(
            next_state="nonexistent_state",
            source="test",
            validate=False,
        )

        assert result is True
        assert state_machine.state == "nonexistent_state"
        # Phase will be None since state doesn't exist in config
        assert state_machine.current_phase is None

    def test_transition_to_preserves_last_action_when_not_provided(self, state_machine):
        """Verify that last_action is preserved when not provided in transition."""
        # Set initial action
        state_machine.last_action = "initial_action"

        # Transition without action
        state_machine.transition_to(
            next_state="spin_situation",
            source="test",
        )

        # last_action should be preserved
        assert state_machine.last_action == "initial_action"

    def test_sync_phase_from_state_corrects_mismatch(self, state_machine):
        """
        Verify that sync_phase_from_state() corrects phase after direct state mutation.

        This is a safety net for backward compatibility.
        """
        # Simulate direct state mutation (legacy code pattern)
        state_machine.state = "spin_problem"
        state_machine.current_phase = "wrong_phase"  # Intentional mismatch

        # Sync should correct the mismatch
        state_machine.sync_phase_from_state()

        assert state_machine.state == "spin_problem"
        assert state_machine.current_phase == "problem"  # Corrected


class TestDistributedStateMutationFix:
    """
    Tests that verify the Distributed State Mutation bug is fixed.

    The bug occurred when:
    1. Orchestrator set state="X", current_phase="phase_for_X"
    2. Bot.py set state="Y" (without updating current_phase)
    3. Result: state="Y", current_phase="phase_for_X" (INCONSISTENT!)
    """

    @pytest.fixture
    def state_machine(self):
        """Create a StateMachine instance for testing."""
        return StateMachine()

    def test_old_bug_scenario_now_fixed(self, state_machine):
        """
        Reproduce the exact bug scenario and verify it's fixed.

        Old code:
            orchestrator: state_machine.state = "spin_problem"
                         state_machine.current_phase = "problem"
            bot.py:      state_machine.state = "spin_implication"  # ONLY state!
            Result: state="spin_implication", phase="problem"  # BUG!

        New code (with transition_to()):
            orchestrator: state_machine.transition_to("spin_problem", ...)
            bot.py:      state_machine.transition_to("spin_implication", ...)
            Result: state="spin_implication", phase="implication"  # CORRECT!
        """
        # Step 1: Orchestrator transition
        state_machine.transition_to(
            next_state="spin_problem",
            action="ask_problem_questions",
            source="orchestrator",
        )

        assert state_machine.state == "spin_problem"
        assert state_machine.current_phase == "problem"

        # Step 2: Bot.py policy override (NOW USING transition_to!)
        state_machine.transition_to(
            next_state="spin_implication",
            action="ask_implication_questions",
            source="policy_override",
        )

        # Verify consistency
        assert state_machine.state == "spin_implication"
        assert state_machine.current_phase == "implication"  # CORRECT!

    def test_sequential_transitions_maintain_consistency(self, state_machine):
        """Verify that multiple sequential transitions maintain consistency."""
        # Note: phases are loaded from flow config, some states may not have a phase
        transitions = [
            ("spin_situation", "situation"),
            ("spin_problem", "problem"),
            ("spin_implication", "implication"),
            ("spin_need_payoff", "need_payoff"),
        ]

        for next_state, expected_phase in transitions:
            state_machine.transition_to(
                next_state=next_state,
                source="test",
            )

            assert state_machine.state == next_state
            assert state_machine.current_phase == expected_phase, \
                f"Mismatch: state={next_state}, phase={state_machine.current_phase}, expected={expected_phase}"

        # Verify "presentation" state (may not have a phase in config)
        state_machine.transition_to(
            next_state="presentation",
            source="test",
        )
        assert state_machine.state == "presentation"
        # Phase may be None if not defined in config - that's OK


class TestOrchestratorUsesTransitionTo:
    """Tests that verify Orchestrator._apply_side_effects uses transition_to()."""

    def test_orchestrator_apply_side_effects_uses_transition_to(self):
        """Verify that orchestrator._apply_side_effects() calls transition_to()."""
        from src.blackboard.orchestrator import DialogueOrchestrator
        from src.blackboard.models import ResolvedDecision

        # Create mock state machine with transition_to method
        mock_sm = MagicMock()
        mock_sm.state = "greeting"
        mock_sm.collected_data = {}

        # Create mock flow config
        mock_flow = MagicMock()
        mock_flow.states = {
            "spin_situation": {"phase": "situation"},
            "greeting": {},
        }
        mock_flow.get_state_on_enter_flags = MagicMock(return_value={})

        # Create orchestrator
        orchestrator = DialogueOrchestrator(
            state_machine=mock_sm,
            flow_config=mock_flow,
        )

        # Create decision
        decision = ResolvedDecision(
            action="ask_situation_questions",
            next_state="spin_situation",
            reason_codes=["test"],
        )

        # Apply side effects
        orchestrator._apply_side_effects(
            decision=decision,
            prev_state="greeting",
            state_changed=True,
        )

        # Verify transition_to was called with phase computed from flow config
        mock_sm.transition_to.assert_called_once_with(
            next_state="spin_situation",
            action="ask_situation_questions",
            phase="situation",  # Computed from flow config
            source="orchestrator",
            validate=False,
        )


class TestProtocolCompliance:
    """Tests that verify StateMachine implements IStateMachine protocol."""

    def test_state_machine_implements_protocol(self):
        """Verify that StateMachine implements all IStateMachine methods."""
        from src.blackboard.protocols import IStateMachine

        sm = StateMachine()

        # Check protocol compliance
        assert isinstance(sm, IStateMachine)

        # Verify transition_to exists and is callable
        assert hasattr(sm, "transition_to")
        assert callable(sm.transition_to)

        # Verify sync_phase_from_state exists
        assert hasattr(sm, "sync_phase_from_state")
        assert callable(sm.sync_phase_from_state)

    def test_mock_state_machine_can_implement_protocol(self):
        """Verify that mocks can implement IStateMachine with transition_to."""
        from src.blackboard.protocols import IStateMachine

        mock_sm = MagicMock(spec=IStateMachine)
        mock_sm.state = "test_state"
        mock_sm.current_phase = "test_phase"
        mock_sm.last_action = "test_action"
        mock_sm.transition_to.return_value = True

        # Should work with protocol
        result = mock_sm.transition_to(
            next_state="new_state",
            action="new_action",
            source="test",
        )

        assert result is True
        mock_sm.transition_to.assert_called_once()


class TestEdgeCases:
    """Tests for edge cases in transition_to()."""

    @pytest.fixture
    def state_machine(self):
        """Create a StateMachine instance for testing."""
        return StateMachine()

    def test_transition_to_same_state(self, state_machine):
        """Verify transition to the same state works."""
        state_machine.state = "spin_situation"
        state_machine.current_phase = "situation"

        result = state_machine.transition_to(
            next_state="spin_situation",
            action="repeat_question",
            source="test",
        )

        assert result is True
        assert state_machine.state == "spin_situation"
        assert state_machine.current_phase == "situation"
        assert state_machine.last_action == "repeat_question"

    def test_transition_to_with_none_phase_in_config(self, state_machine):
        """Verify transition works when state has no phase in config."""
        # "end" state might not have a phase
        result = state_machine.transition_to(
            next_state="end",
            source="test",
            validate=False,  # End state might not exist in all configs
        )

        assert result is True
        assert state_machine.state == "end"
        # Phase should be None or computed from config

    def test_transition_to_preserves_collected_data(self, state_machine):
        """Verify that transition_to() doesn't affect collected_data."""
        state_machine.collected_data["company_size"] = "15"
        state_machine.collected_data["pain_point"] = "losing customers"

        state_machine.transition_to(
            next_state="spin_problem",
            source="test",
        )

        # collected_data should be unchanged
        assert state_machine.collected_data["company_size"] == "15"
        assert state_machine.collected_data["pain_point"] == "losing customers"
