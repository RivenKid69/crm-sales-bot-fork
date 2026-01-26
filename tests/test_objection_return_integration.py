# tests/test_objection_return_integration.py

"""
Integration Tests for ObjectionReturnSource - Phase Preservation.

These tests verify the complete flow of:
1. Entering handle_objection from a phase state
2. Successfully handling objection with positive intent
3. Returning to the previous phase state

Tests the interaction between:
- ObjectionReturnSource
- TransitionResolverSource
- ConflictResolver
- DialogueBlackboard

This fixes the bug where:
    bant_budget → handle_objection → close (phase lost!)

Correct behavior:
    bant_budget → handle_objection → bant_budget (phase preserved!)
"""

import pytest
from typing import Dict, Any, Optional

from src.blackboard.sources.objection_return import ObjectionReturnSource
from src.blackboard.sources.transition_resolver import TransitionResolverSource
from src.blackboard.blackboard import DialogueBlackboard
from src.blackboard.conflict_resolver import ConflictResolver
from src.blackboard.enums import Priority


# =============================================================================
# Mock Implementations for Integration Testing
# =============================================================================

class MockStateMachine:
    """Mock StateMachine implementing IStateMachine protocol."""

    def __init__(
        self,
        state: str = "greeting",
        collected_data: Optional[Dict[str, Any]] = None,
        state_before_objection: Optional[str] = None
    ):
        self._state = state
        self._collected_data = collected_data or {}
        self._intent_tracker = None
        self._state_before_objection = state_before_objection

    @property
    def state(self) -> str:
        return self._state

    @state.setter
    def state(self, value: str) -> None:
        self._state = value

    @property
    def collected_data(self) -> Dict[str, Any]:
        return self._collected_data


class MockIntentTracker:
    """Mock IntentTracker implementing IIntentTracker protocol."""

    def __init__(
        self,
        turn_number: int = 0,
        objection_consecutive: int = 0,
        objection_total: int = 0
    ):
        self._turn_number = turn_number
        self._prev_intent = None
        self._intents = []
        self._objection_consecutive = objection_consecutive
        self._objection_total = objection_total

    @property
    def turn_number(self) -> int:
        return self._turn_number

    @property
    def prev_intent(self) -> Optional[str]:
        return self._prev_intent

    def record(self, intent: str, state: str) -> None:
        if self._intents:
            self._prev_intent = self._intents[-1][0]
        self._intents.append((intent, state))
        self._turn_number += 1

        if "objection" in intent:
            self._objection_consecutive += 1
            self._objection_total += 1
        else:
            self._objection_consecutive = 0

    def objection_consecutive(self) -> int:
        return self._objection_consecutive

    def objection_total(self) -> int:
        return self._objection_total

    def total_count(self, intent: str) -> int:
        return sum(1 for i, _ in self._intents if i == intent)

    def category_total(self, category: str) -> int:
        return 0


class MockFlowConfig:
    """Mock FlowConfig with handle_objection transitions."""

    def __init__(
        self,
        states: Optional[Dict[str, Dict[str, Any]]] = None,
        variables: Optional[Dict[str, Any]] = None
    ):
        self._states = states or {
            "greeting": {"goal": "Greet user"},
            "bant_budget": {
                "goal": "Qualify budget",
                "phase": "budget",
                "transitions": {
                    "objection_price": "handle_objection",
                }
            },
            "bant_authority": {
                "goal": "Qualify authority",
                "phase": "authority",
            },
            "handle_objection": {
                "goal": "Handle objection",
                "transitions": {
                    # YAML transitions that would lose the phase:
                    "agreement": "close",
                    "interest": "close",
                    "objection_price": "handle_objection",
                }
            },
            "close": {"goal": "Close the deal", "is_final": True},
            "soft_close": {"goal": "Soft close", "is_final": True},
        }
        # Default entry_state for testing fallback behavior
        self.variables = variables if variables is not None else {
            "entry_state": "bant_budget"
        }

    @property
    def states(self) -> Dict[str, Dict[str, Any]]:
        return self._states

    def to_dict(self) -> Dict[str, Any]:
        return {"states": self._states}

    @property
    def phase_mapping(self) -> Dict[str, str]:
        """Get phase -> state mapping."""
        mapping = {}
        for state_name, state_config in self._states.items():
            phase = state_config.get("phase") or state_config.get("spin_phase")
            if phase:
                mapping[phase] = state_name
        return mapping

    @property
    def state_to_phase(self) -> Dict[str, str]:
        """Get complete state -> phase mapping."""
        result = {v: k for k, v in self.phase_mapping.items()}
        for state_name, state_config in self._states.items():
            explicit_phase = state_config.get("phase") or state_config.get("spin_phase")
            if explicit_phase:
                result[state_name] = explicit_phase
        return result

    def get_phase_for_state(self, state_name: str) -> Optional[str]:
        """Get phase name for a state."""
        return self.state_to_phase.get(state_name)


def create_test_setup(
    state: str = "greeting",
    collected_data: Optional[Dict[str, Any]] = None,
    states: Optional[Dict[str, Dict[str, Any]]] = None,
    intent: str = "greeting",
    state_before_objection: Optional[str] = None,
    variables: Optional[Dict[str, Any]] = None,
):
    """Create a complete test setup with blackboard, sources, and resolver."""
    sm = MockStateMachine(
        state=state,
        collected_data=collected_data or {},
        state_before_objection=state_before_objection
    )
    flow_config = MockFlowConfig(states=states, variables=variables)
    tracker = MockIntentTracker()

    bb = DialogueBlackboard(
        state_machine=sm,
        flow_config=flow_config,
        intent_tracker=tracker,
    )
    bb.begin_turn(intent=intent, extracted_data={})

    objection_return_source = ObjectionReturnSource()
    transition_resolver_source = TransitionResolverSource()
    conflict_resolver = ConflictResolver()

    return {
        "blackboard": bb,
        "state_machine": sm,
        "flow_config": flow_config,
        "objection_return_source": objection_return_source,
        "transition_resolver_source": transition_resolver_source,
        "conflict_resolver": conflict_resolver,
    }


# =============================================================================
# Integration Tests: Phase Preservation
# =============================================================================

class TestPhasePreservationIntegration:
    """
    Integration tests for phase preservation when handling objections.

    These tests verify that ObjectionReturnSource correctly wins over
    TransitionResolverSource when returning from handle_objection.
    """

    def test_objection_return_wins_over_yaml_transition(self):
        """
        CRITICAL: ObjectionReturnSource (HIGH) should win over TransitionResolverSource (NORMAL).

        Scenario:
            1. Client in bant_budget, raises objection
            2. Transition to handle_objection, save bant_budget
            3. Bot handles objection, client says "agreement"
            4. YAML says: agreement → close (would lose phase)
            5. ObjectionReturnSource says: agreement → bant_budget (HIGH priority)
            6. ObjectionReturnSource WINS → phase preserved
        """
        setup = create_test_setup(
            state="handle_objection",
            intent="agreement",
            state_before_objection="bant_budget"
        )

        bb = setup["blackboard"]
        objection_return = setup["objection_return_source"]
        transition_resolver = setup["transition_resolver_source"]
        resolver = setup["conflict_resolver"]

        # Both sources contribute
        objection_return.contribute(bb)
        transition_resolver.contribute(bb)

        # Get all proposals
        proposals = bb.get_proposals()

        # Verify we have competing proposals
        transition_proposals = [p for p in proposals if p.value in ["bant_budget", "close"]]
        assert len(transition_proposals) >= 1, "Should have at least ObjectionReturn proposal"

        # Resolve conflict
        decision = resolver.resolve(
            proposals=proposals,
            current_state="handle_objection"
        )

        # ObjectionReturnSource should WIN because HIGH > NORMAL
        assert decision.next_state == "bant_budget", \
            f"Expected bant_budget but got {decision.next_state}. " \
            f"Phase was lost! ObjectionReturnSource should have won."

    def test_yaml_transition_wins_when_no_saved_state(self):
        """
        When no _state_before_objection is saved, YAML transitions should work.

        Scenario:
            1. Client in handle_objection (no saved state)
            2. Client says "agreement"
            3. YAML says: agreement → close
            4. ObjectionReturnSource has no proposal (no saved state)
            5. TransitionResolver WINS → close
        """
        setup = create_test_setup(
            state="handle_objection",
            intent="agreement",
            state_before_objection=None  # No saved state!
        )

        bb = setup["blackboard"]
        objection_return = setup["objection_return_source"]
        transition_resolver = setup["transition_resolver_source"]
        resolver = setup["conflict_resolver"]

        # Both sources contribute
        objection_return.contribute(bb)
        transition_resolver.contribute(bb)

        proposals = bb.get_proposals()

        decision = resolver.resolve(
            proposals=proposals,
            current_state="handle_objection"
        )

        # Should go to close (YAML transition) when no saved state
        assert decision.next_state == "close"

    def test_objection_continues_in_handle_objection(self):
        """
        When client raises another objection, stay in handle_objection.

        Scenario:
            1. Client in handle_objection with saved state
            2. Client raises objection_price again
            3. ObjectionReturnSource: no proposal (not positive intent)
            4. TransitionResolver: objection_price → handle_objection
            5. Stay in handle_objection
        """
        setup = create_test_setup(
            state="handle_objection",
            intent="objection_price",
            state_before_objection="bant_budget"
        )

        bb = setup["blackboard"]
        objection_return = setup["objection_return_source"]
        transition_resolver = setup["transition_resolver_source"]
        resolver = setup["conflict_resolver"]

        objection_return.contribute(bb)
        transition_resolver.contribute(bb)

        proposals = bb.get_proposals()

        decision = resolver.resolve(
            proposals=proposals,
            current_state="handle_objection"
        )

        # Should stay in handle_objection
        assert decision.next_state == "handle_objection"


# =============================================================================
# Integration Tests: Multiple Sources
# =============================================================================

class TestMultipleSourcesInteraction:
    """Test interaction between ObjectionReturnSource and other sources."""

    def test_objection_return_source_runs_before_transition_resolver(self):
        """
        ObjectionReturnSource has priority_order 35, TransitionResolver has 50.
        ObjectionReturnSource should contribute first.
        """
        setup = create_test_setup(
            state="handle_objection",
            intent="agreement",
            state_before_objection="bant_budget"
        )

        bb = setup["blackboard"]

        # Contribute in priority order
        setup["objection_return_source"].contribute(bb)
        setup["transition_resolver_source"].contribute(bb)

        proposals = bb.get_transition_proposals()

        # First proposal should be from ObjectionReturnSource
        assert len(proposals) >= 1
        objection_return_proposal = [p for p in proposals if p.source_name == "ObjectionReturnSource"]
        assert len(objection_return_proposal) >= 1

    def test_priority_ranking_in_proposals(self):
        """Verify that ObjectionReturnSource uses HIGH priority."""
        setup = create_test_setup(
            state="handle_objection",
            intent="agreement",
            state_before_objection="bant_budget"
        )

        bb = setup["blackboard"]

        setup["objection_return_source"].contribute(bb)

        proposals = bb.get_transition_proposals()
        objection_return_proposals = [
            p for p in proposals if p.source_name == "ObjectionReturnSource"
        ]

        assert len(objection_return_proposals) == 1
        assert objection_return_proposals[0].priority == Priority.HIGH


# =============================================================================
# Integration Tests: Real Scenarios
# =============================================================================

class TestRealScenarios:
    """Test real-world scenarios from bug report."""

    def test_bant_budget_to_handle_objection_and_back(self):
        """
        Full scenario from bug report:
        1. Client in bant_budget (phase: budget)
        2. Says "this is too expensive" → objection_price
        3. Transition to handle_objection, save bant_budget
        4. Bot handles objection
        5. Client says "ok, I understand" → agreement
        6. Should return to bant_budget (phase: budget) ✓
        7. NOT to close (phase lost) ✗
        """
        # Step 1-3: Enter handle_objection from bant_budget
        setup = create_test_setup(
            state="handle_objection",
            intent="agreement",
            state_before_objection="bant_budget"  # Saved from step 3
        )

        bb = setup["blackboard"]

        # Step 5-6: Handle agreement intent
        setup["objection_return_source"].contribute(bb)
        setup["transition_resolver_source"].contribute(bb)

        decision = setup["conflict_resolver"].resolve(
            proposals=bb.get_proposals(),
            current_state="handle_objection"
        )

        # Step 7: Verify return to bant_budget
        assert decision.next_state == "bant_budget", \
            f"BUG REPRODUCED: Phase lost! Got {decision.next_state} instead of bant_budget"

    def test_phases_reached_should_include_budget(self):
        """
        After objection handling, phases_reached should still include budget.

        This test verifies that the phase tracking is not broken by
        the objection return mechanism.
        """
        setup = create_test_setup(
            state="handle_objection",
            intent="agreement",
            state_before_objection="bant_budget"
        )

        bb = setup["blackboard"]
        flow_config = setup["flow_config"]

        setup["objection_return_source"].contribute(bb)

        decision = setup["conflict_resolver"].resolve(
            proposals=bb.get_proposals(),
            current_state="handle_objection"
        )

        # Get phase for the target state
        target_phase = flow_config.get_phase_for_state(decision.next_state)

        assert decision.next_state == "bant_budget"
        assert target_phase == "budget"

    def test_info_provided_intent_also_triggers_return(self):
        """
        Info provided intent should also trigger return to phase.

        Scenario:
            1. Client in bant_authority
            2. Raises objection → handle_objection
            3. Provides info → should return to bant_authority
        """
        setup = create_test_setup(
            state="handle_objection",
            intent="info_provided",
            state_before_objection="bant_authority"
        )

        bb = setup["blackboard"]

        setup["objection_return_source"].contribute(bb)
        setup["transition_resolver_source"].contribute(bb)

        decision = setup["conflict_resolver"].resolve(
            proposals=bb.get_proposals(),
            current_state="handle_objection"
        )

        assert decision.next_state == "bant_authority"


# =============================================================================
# Integration Tests: Edge Cases
# =============================================================================

class TestIntegrationEdgeCases:
    """Edge cases in integration scenarios."""

    def test_disabled_source_allows_yaml_transition(self):
        """
        When ObjectionReturnSource is disabled, YAML transitions should work.
        """
        setup = create_test_setup(
            state="handle_objection",
            intent="agreement",
            state_before_objection="bant_budget"
        )

        bb = setup["blackboard"]
        objection_return = setup["objection_return_source"]

        # Disable ObjectionReturnSource
        objection_return.disable()

        objection_return.contribute(bb)
        setup["transition_resolver_source"].contribute(bb)

        decision = setup["conflict_resolver"].resolve(
            proposals=bb.get_proposals(),
            current_state="handle_objection"
        )

        # Should go to close (YAML transition) when source is disabled
        assert decision.next_state == "close"

    def test_no_proposals_stays_in_current_state(self):
        """
        When no proposals are made, should stay in current state.
        """
        setup = create_test_setup(
            state="handle_objection",
            intent="unclear",  # Not a positive intent, not an objection
            state_before_objection="bant_budget"
        )

        bb = setup["blackboard"]

        # Neither source should contribute for "unclear" intent
        setup["objection_return_source"].contribute(bb)
        setup["transition_resolver_source"].contribute(bb)

        decision = setup["conflict_resolver"].resolve(
            proposals=bb.get_proposals(),
            current_state="handle_objection"
        )

        # Should stay in current state
        assert decision.next_state == "handle_objection"


# =============================================================================
# Integration Tests: Non-Phase State Handling (37% Zero Coverage Fix)
# =============================================================================

class TestNonPhaseStateIntegration:
    """
    Integration tests for the 37% zero phase coverage bug fix.

    Root Cause (commit 293109e):
        ObjectionReturnSource was proposing HIGH priority transitions back to
        saved states like "greeting" which have NO phase. This won over
        TransitionResolver's NORMAL priority (e.g., agreement → close).

    Problem:
        Personas (skeptic, tire_kicker, competitor_user, aggressive) that
        express objections BEFORE entering a SPIN phase get stuck in
        greeting ↔ handle_objection loop.

        phases_reached = [] → coverage = 0.0

    Solution:
        ObjectionReturnSource now checks if saved_state has a phase.
        If not, it does NOT propose a transition, letting TransitionResolver
        handle the flow (e.g., agreement → close).
    """

    def test_greeting_state_transition_resolver_wins(self):
        """
        CRITICAL: TransitionResolver should win when saved_state is 'greeting'.

        Scenario (skeptic persona):
            1. greeting + objection → handle_objection (save greeting)
            2. handle_objection + agreement → ?
            3. ObjectionReturnSource: entry_state fallback (LOW priority)
            4. TransitionResolver: agreement → close (NORMAL priority)
            5. NORMAL > LOW → close wins (correct!)

        Without fix:
            3. ObjectionReturnSource: greeting (HIGH) ← BUG
            5. Result: greeting (WRONG! Loop continues)
        """
        setup = create_test_setup(
            state="handle_objection",
            intent="agreement",
            state_before_objection="greeting"  # Non-phase state!
        )

        bb = setup["blackboard"]
        objection_return = setup["objection_return_source"]
        transition_resolver = setup["transition_resolver_source"]
        resolver = setup["conflict_resolver"]

        # Both sources contribute
        objection_return.contribute(bb)
        transition_resolver.contribute(bb)

        proposals = bb.get_proposals()

        # ObjectionReturnSource proposes entry_state fallback with NORMAL priority
        # FIX: Changed from LOW to NORMAL so entry_state wins over TransitionResolver
        objection_proposals = [
            p for p in proposals if p.source_name == "ObjectionReturnSource"
        ]
        assert len(objection_proposals) == 1, \
            "ObjectionReturnSource should propose entry_state fallback"
        assert objection_proposals[0].priority == Priority.NORMAL, \
            "Fallback should be NORMAL priority to win over TransitionResolver"

        # TransitionResolver proposes close with NORMAL priority
        transition_proposals = [
            p for p in proposals if p.source_name == "TransitionResolverSource"
        ]
        assert len(transition_proposals) == 1
        assert transition_proposals[0].priority == Priority.NORMAL

        # Resolve conflict
        decision = resolver.resolve(
            proposals=proposals,
            current_state="handle_objection"
        )

        # ObjectionReturnSource should WIN (runs first due to priority_order 35 < 50)
        # FIX: This is the CORRECT behavior - dialog goes to entry_state, not close
        assert decision.next_state == "bant_budget", \
            f"Expected 'bant_budget' (entry_state) but got '{decision.next_state}'. " \
            "ObjectionReturnSource runs first and wins on equal NORMAL priority."

    def test_skeptic_persona_full_flow(self):
        """
        Full skeptic persona scenario that caused 0% phase coverage.

        Persona behavior:
            - Immediately doubts: "не уверен что мне это нужно"
            - Classifier: objection_think
            - This happens BEFORE entering any SPIN phase

        Expected flow with fix:
            1. greeting → objection_think → handle_objection (save "greeting")
            2. Bot handles objection
            3. Client: "ладно, может быть интересно" → agreement
            4. ObjectionReturnSource: entry_state fallback (LOW)
            5. TransitionResolver: agreement → close (NORMAL)
            6. NORMAL wins → close (no more loop!)

        The key is: no greeting ↔ handle_objection loop!
        """
        setup = create_test_setup(
            state="handle_objection",
            intent="agreement",
            state_before_objection="greeting"
        )

        bb = setup["blackboard"]

        setup["objection_return_source"].contribute(bb)
        setup["transition_resolver_source"].contribute(bb)

        decision = setup["conflict_resolver"].resolve(
            proposals=bb.get_proposals(),
            current_state="handle_objection"
        )

        # Should NOT go back to greeting (that would cause the loop)
        assert decision.next_state != "greeting", \
            "BUG DETECTED: Still returning to greeting! Loop will occur."

        # FIX: Should go to entry_state (bant_budget), not close
        # ObjectionReturnSource now uses NORMAL priority and wins (runs first)
        assert decision.next_state == "bant_budget", \
            "With fix: entry_state wins, conversation continues to phases"

    def test_tire_kicker_persona_scenario(self):
        """
        tire_kicker persona: "Просто смотрю" → objection_no_need

        Same problem as skeptic - objection before entering phase.
        FIX: entry_state fallback (NORMAL) wins over TransitionResolver (NORMAL)
        because ObjectionReturnSource runs first (priority_order 35 < 50).
        """
        setup = create_test_setup(
            state="handle_objection",
            intent="agreement",  # Changed from interest (not in POSITIVE_INTENTS)
            state_before_objection="greeting"
        )

        bb = setup["blackboard"]

        setup["objection_return_source"].contribute(bb)
        setup["transition_resolver_source"].contribute(bb)

        decision = setup["conflict_resolver"].resolve(
            proposals=bb.get_proposals(),
            current_state="handle_objection"
        )

        # Should NOT return to greeting
        assert decision.next_state != "greeting"
        # FIX: Goes to entry_state (bant_budget), not close
        assert decision.next_state == "bant_budget"

    def test_competitor_user_persona_scenario(self):
        """
        competitor_user persona: "У нас уже есть решение" → objection_competitor

        Same problem - objection before entering phase.
        FIX: entry_state wins with NORMAL priority.
        """
        setup = create_test_setup(
            state="handle_objection",
            intent="agreement",
            state_before_objection="greeting"
        )

        bb = setup["blackboard"]

        setup["objection_return_source"].contribute(bb)
        setup["transition_resolver_source"].contribute(bb)

        decision = setup["conflict_resolver"].resolve(
            proposals=bb.get_proposals(),
            current_state="handle_objection"
        )

        assert decision.next_state != "greeting"
        # FIX: Goes to entry_state (bant_budget), not close
        assert decision.next_state == "bant_budget"

    def test_phase_state_still_returns_correctly(self):
        """
        Verify: When saved_state HAS a phase, return still works.

        This test ensures the fix doesn't break the normal case.
        """
        setup = create_test_setup(
            state="handle_objection",
            intent="agreement",
            state_before_objection="bant_budget"  # Has phase: budget
        )

        bb = setup["blackboard"]

        setup["objection_return_source"].contribute(bb)
        setup["transition_resolver_source"].contribute(bb)

        decision = setup["conflict_resolver"].resolve(
            proposals=bb.get_proposals(),
            current_state="handle_objection"
        )

        # Should return to bant_budget (phase preserved)
        assert decision.next_state == "bant_budget"

    def test_multiple_objection_returns_to_phase(self):
        """
        Client raises objection, handles it, raises another, handles it.
        Each time should return to the PHASE state.
        """
        # First objection from bant_budget
        setup = create_test_setup(
            state="handle_objection",
            intent="agreement",
            state_before_objection="bant_budget"
        )

        bb = setup["blackboard"]

        setup["objection_return_source"].contribute(bb)
        setup["transition_resolver_source"].contribute(bb)

        decision = setup["conflict_resolver"].resolve(
            proposals=bb.get_proposals(),
            current_state="handle_objection"
        )

        assert decision.next_state == "bant_budget"

        # Second objection from same phase
        setup2 = create_test_setup(
            state="handle_objection",
            intent="info_provided",
            state_before_objection="bant_budget"
        )

        bb2 = setup2["blackboard"]

        setup2["objection_return_source"].contribute(bb2)
        setup2["transition_resolver_source"].contribute(bb2)

        decision2 = setup2["conflict_resolver"].resolve(
            proposals=bb2.get_proposals(),
            current_state="handle_objection"
        )

        assert decision2.next_state == "bant_budget"

    def test_different_phase_states_return_correctly(self):
        """
        Test that all phase states return correctly.
        """
        phase_states = ["bant_budget", "bant_authority"]

        for phase_state in phase_states:
            setup = create_test_setup(
                state="handle_objection",
                intent="agreement",
                state_before_objection=phase_state
            )

            bb = setup["blackboard"]

            setup["objection_return_source"].contribute(bb)
            setup["transition_resolver_source"].contribute(bb)

            decision = setup["conflict_resolver"].resolve(
                proposals=bb.get_proposals(),
                current_state="handle_objection"
            )

            assert decision.next_state == phase_state, \
                f"Failed for phase_state: {phase_state}"
