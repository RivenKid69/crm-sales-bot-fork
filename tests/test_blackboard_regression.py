# tests/test_blackboard_regression.py

"""
Regression tests for the Blackboard system.

Stage 13: Regression Tests (Section 19 from Plan)

These tests ensure Blackboard produces EXPECTED behavior.
They verify that the system works as DESIGNED, not comparing with legacy.

Test Scenarios:
1. Core scenarios with expected outcomes
2. Edge cases that must be handled correctly
3. Boundary conditions for limits
"""

import pytest
import json
from pathlib import Path
from typing import Dict, Any, Optional, List
from unittest.mock import Mock
from dataclasses import dataclass, field

from src.blackboard.orchestrator import DialogueOrchestrator
from src.blackboard.models import ResolvedDecision
from src.blackboard.enums import Priority, ProposalType
from src.blackboard.source_registry import SourceRegistry
from src.blackboard.knowledge_source import KnowledgeSource


# =============================================================================
# Mock Implementations
# =============================================================================

@dataclass
class IntentRecord:
    """Record of an intent."""
    intent: str
    state: str


class MockIntentTracker:
    """Mock IntentTracker for regression testing."""

    def __init__(
        self,
        turn_number: int = 0,
        objection_consecutive: int = 0,
        objection_total: int = 0
    ):
        self._turn_number = turn_number
        self._prev_intent = None
        self._intents: List[IntentRecord] = []
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
            self._prev_intent = self._intents[-1].intent
        self._intents.append(IntentRecord(intent=intent, state=state))
        self._turn_number += 1

    def objection_consecutive(self) -> int:
        return self._objection_consecutive

    def objection_total(self) -> int:
        return self._objection_total

    def total_count(self, intent: str) -> int:
        return sum(1 for r in self._intents if r.intent == intent)

    def category_total(self, category: str) -> int:
        return sum(1 for r in self._intents if category in r.intent)

    def get_intents_by_category(self, category: str) -> List[IntentRecord]:
        return [r for r in self._intents if category in r.intent]


class MockCircularFlow:
    """Mock CircularFlowManager."""

    def get_stats(self) -> Dict[str, Any]:
        return {"loops": 0, "max_loops": 3}


class RegressionStateMachine:
    """State Machine for regression testing."""

    def __init__(
        self,
        state: str = "greeting",
        collected_data: Optional[Dict[str, Any]] = None,
        objection_consecutive: int = 0,
        objection_total: int = 0
    ):
        self._state = state
        self._collected_data = collected_data or {}
        self._current_phase = None
        self._last_action = None
        self._intent_tracker = MockIntentTracker(
            objection_consecutive=objection_consecutive,
            objection_total=objection_total
        )
        self._state_before_objection = None
        self.circular_flow = MockCircularFlow()

    @property
    def state(self) -> str:
        return self._state

    @state.setter
    def state(self, value: str) -> None:
        self._state = value

    @property
    def collected_data(self) -> Dict[str, Any]:
        return self._collected_data

    @property
    def current_phase(self) -> Optional[str]:
        return self._current_phase

    @current_phase.setter
    def current_phase(self, value: Optional[str]) -> None:
        self._current_phase = value

    @property
    def last_action(self) -> Optional[str]:
        return self._last_action

    @last_action.setter
    def last_action(self, value: Optional[str]) -> None:
        self._last_action = value

    def update_data(self, data: Dict[str, Any]) -> None:
        self._collected_data.update(data)

    def transition_to(
        self,
        next_state: str,
        action: Optional[str] = None,
        phase: Optional[str] = None,
        source: str = "test",
        validate: bool = True,
    ) -> None:
        """Atomic state transition (mirrors real StateMachine.transition_to)."""
        self._state = next_state
        if action is not None:
            self._last_action = action
        if phase is not None:
            self._current_phase = phase

    def is_final(self) -> bool:
        return self._state in ("soft_close", "closed", "rejected")


class RegressionFlowConfig:
    """Flow configuration for regression testing."""

    def __init__(self, states: Optional[Dict[str, Dict[str, Any]]] = None):
        self._states = states or {
            "spin_situation": {
                "goal": "Understand situation",
                "phase": "situation",
                "required_data": ["company_size"],
                "is_final": False,
                "transitions": {
                    "data_complete": "spin_problem",
                    "rejection": "soft_close",
                },
                "rules": {},
            },
            "spin_problem": {
                "goal": "Identify problems",
                "phase": "problem",
                "required_data": [],
                "is_final": False,
                "transitions": {},
                "rules": {},
            },
            "soft_close": {
                "goal": "Graceful exit",
                "is_final": True,
                "transitions": {},
                "rules": {},
            },
            "_limits": {
                "max_consecutive_objections": 3,
                "max_total_objections": 5,
            },
        }
        self._constants = {
            "persona_limits": {
                "aggressive": {"consecutive": 5, "total": 8},
                "busy": {"consecutive": 2, "total": 4},
                "default": {"consecutive": 3, "total": 5},
            }
        }

    @property
    def states(self) -> Dict[str, Dict[str, Any]]:
        return self._states

    @property
    def constants(self) -> Dict[str, Any]:
        return self._constants

    def get_state_on_enter_flags(self, state_name: str) -> Dict[str, Any]:
        state_config = self._states.get(state_name, {})
        on_enter = state_config.get("on_enter", {})
        if isinstance(on_enter, dict):
            return on_enter.get("set_flags", {})
        return {}

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
        """
        Get complete state -> phase mapping.

        This is the CANONICAL source of truth for state -> phase resolution.
        Includes both reverse mapping from phase_mapping AND explicit phases
        from state configs (explicit phases have higher priority).
        """
        # Start with reverse mapping from phase_mapping
        result = {v: k for k, v in self.phase_mapping.items()}

        # Override with explicit phases from state configs (higher priority)
        for state_name, state_config in self._states.items():
            explicit_phase = state_config.get("phase") or state_config.get("spin_phase")
            if explicit_phase:
                result[state_name] = explicit_phase

        return result

    def get_phase_for_state(self, state_name: str) -> Optional[str]:
        """Get phase name for a state."""
        # Delegate to state_to_phase which contains the complete mapping
        return self.state_to_phase.get(state_name)

    def is_phase_state(self, state_name: str) -> bool:
        """Check if a state is a phase state."""
        return self.get_phase_for_state(state_name) is not None


# =============================================================================
# Regression Test Scenarios
# =============================================================================

class TestBlackboardRegression:
    """
    Regression tests ensuring Blackboard produces EXPECTED behavior.

    NOTE: Эти тесты НЕ сравнивают с legacy системой (она удалена).
    Они проверяют что Blackboard работает как ЗАДУМАНО.
    """

    @pytest.fixture
    def regression_scenarios(self):
        """
        Load regression test scenarios.

        Each scenario defines:
        - Initial conditions (state, collected_data, objection counts)
        - Input (intent, extracted_data)
        - Expected output (action, state, reason_codes)
        """
        scenarios_file = Path(__file__).parent / "fixtures" / "regression_scenarios.json"

        if scenarios_file.exists():
            with open(scenarios_file) as f:
                return json.load(f)

        # Default scenarios if file doesn't exist
        return [
            {
                "name": "price_question_with_data_complete",
                "description": "Price question with data completing in same turn",
                "initial_state": "spin_situation",
                "collected_data": {"company_size": "15"},  # Data already collected
                "intent": "price_question",
                "extracted_data": {},
                "expected_action": "answer_with_pricing",
                "expected_state": "spin_problem",
                "expected_reason_codes": ["price_question_priority", "data_complete"],
            },
            {
                "name": "objection_within_limits",
                "description": "Objection that is within persona limits",
                "initial_state": "spin_problem",
                "collected_data": {"company_size": "50"},
                "intent": "objection_price",
                "extracted_data": {},
                "objection_consecutive": 1,
                "objection_total": 2,
                "expected_action_not": "objection_limit_reached",
                "expected_state_not": "soft_close",
            },
            {
                "name": "objection_exceeds_limits",
                "description": "Objection that exceeds persona limits",
                "initial_state": "spin_problem",
                "collected_data": {"company_size": "50"},
                "intent": "objection_price",
                "extracted_data": {},
                "objection_consecutive": 3,
                "objection_total": 5,
                "expected_action": "objection_limit_reached",
                "expected_state": "soft_close",
            },
            {
                "name": "data_complete_transition",
                "description": "Transition when all required data is collected",
                "initial_state": "spin_situation",
                "collected_data": {"company_size": "50"},
                "intent": "info_provided",
                "extracted_data": {},
                "expected_state": "spin_problem",
                "expected_reason_codes": ["data_complete"],
            },
            {
                "name": "no_data_no_transition",
                "description": "No transition when data is incomplete",
                "initial_state": "spin_situation",
                "collected_data": {},  # No data
                "intent": "info_provided",
                "extracted_data": {},
                "expected_state": "spin_situation",
                "expected_reason_codes_not": ["data_complete"],
            },
        ]

    def test_regression_scenarios(self, regression_scenarios):
        """Run all regression scenarios."""
        for scenario in regression_scenarios:
            self._run_scenario(scenario)

    def _run_scenario(self, scenario: Dict[str, Any]) -> None:
        """Run a single regression scenario."""
        from src.blackboard.source_registry import register_builtin_sources

        SourceRegistry.reset()
        # Re-register sources after reset
        register_builtin_sources()

        # Setup state machine
        sm = RegressionStateMachine(
            state=scenario["initial_state"],
            collected_data=scenario.get("collected_data", {}),
            objection_consecutive=scenario.get("objection_consecutive", 0),
            objection_total=scenario.get("objection_total", 0),
        )

        # Setup flow config
        fc = RegressionFlowConfig()

        # Create orchestrator
        orchestrator = DialogueOrchestrator(
            state_machine=sm,
            flow_config=fc,
            enable_validation=True,
        )

        # Execute
        decision = orchestrator.process_turn(
            intent=scenario["intent"],
            extracted_data=scenario.get("extracted_data", {}),
        )

        # Verify
        scenario_name = scenario["name"]

        if "expected_action" in scenario:
            assert decision.action == scenario["expected_action"], \
                f"Scenario '{scenario_name}': expected action {scenario['expected_action']}, got {decision.action}"

        if "expected_state" in scenario:
            assert decision.next_state == scenario["expected_state"], \
                f"Scenario '{scenario_name}': expected state {scenario['expected_state']}, got {decision.next_state}"

        if "expected_action_not" in scenario:
            assert decision.action != scenario["expected_action_not"], \
                f"Scenario '{scenario_name}': action should NOT be {scenario['expected_action_not']}"

        if "expected_state_not" in scenario:
            assert decision.next_state != scenario["expected_state_not"], \
                f"Scenario '{scenario_name}': state should NOT be {scenario['expected_state_not']}"

        if "expected_reason_codes" in scenario:
            for code in scenario["expected_reason_codes"]:
                assert code in decision.reason_codes, \
                    f"Scenario '{scenario_name}': expected reason code {code} not found in {decision.reason_codes}"

        if "expected_reason_codes_not" in scenario:
            for code in scenario["expected_reason_codes_not"]:
                assert code not in decision.reason_codes, \
                    f"Scenario '{scenario_name}': unexpected reason code {code} found in {decision.reason_codes}"


# =============================================================================
# Edge Case Regression Tests
# =============================================================================

class TestEdgeCaseRegression:
    """Regression tests for edge cases."""

    def test_empty_proposals_uses_default(self):
        """When no sources propose anything, default action should be used."""
        SourceRegistry.reset()

        sm = RegressionStateMachine(state="spin_situation")
        fc = RegressionFlowConfig()

        orchestrator = DialogueOrchestrator(
            state_machine=sm,
            flow_config=fc,
        )

        # Clear all sources
        orchestrator._sources.clear()

        decision = orchestrator.process_turn(
            intent="unknown_intent",
            extracted_data={},
        )

        # Should use default action
        assert decision.action == "continue"
        # Should stay in current state
        assert decision.next_state == "spin_situation"

    def test_multiple_blocking_actions_highest_priority_wins(self):
        """When multiple blocking actions exist, highest priority wins."""
        SourceRegistry.reset()

        sm = RegressionStateMachine(state="spin_situation")
        fc = RegressionFlowConfig()

        orchestrator = DialogueOrchestrator(
            state_machine=sm,
            flow_config=fc,
        )

        orchestrator._sources.clear()

        class HighBlockingSource(KnowledgeSource):
            def should_contribute(self, bb):
                return True

            def contribute(self, bb):
                bb.propose_action(
                    action="high_blocking",
                    priority=Priority.HIGH,
                    combinable=False,
                    source_name=self.name,
                    reason_code="high_blocking",
                )

        class NormalBlockingSource(KnowledgeSource):
            def should_contribute(self, bb):
                return True

            def contribute(self, bb):
                bb.propose_action(
                    action="normal_blocking",
                    priority=Priority.NORMAL,
                    combinable=False,
                    source_name=self.name,
                    reason_code="normal_blocking",
                )

        orchestrator.add_source(NormalBlockingSource("NormalBlockingSource"))
        orchestrator.add_source(HighBlockingSource("HighBlockingSource"))

        decision = orchestrator.process_turn(
            intent="test",
            extracted_data={},
        )

        # High priority blocking should win
        assert decision.action == "high_blocking"

    def test_critical_priority_always_wins(self):
        """CRITICAL priority should always win over other priorities."""
        SourceRegistry.reset()

        sm = RegressionStateMachine(state="spin_situation")
        fc = RegressionFlowConfig()

        orchestrator = DialogueOrchestrator(
            state_machine=sm,
            flow_config=fc,
        )

        orchestrator._sources.clear()

        class CriticalSource(KnowledgeSource):
            def should_contribute(self, bb):
                return True

            def contribute(self, bb):
                bb.propose_action(
                    action="critical_action",
                    priority=Priority.CRITICAL,
                    source_name=self.name,
                    reason_code="critical",
                )

        class HighSource(KnowledgeSource):
            def should_contribute(self, bb):
                return True

            def contribute(self, bb):
                bb.propose_action(
                    action="high_action",
                    priority=Priority.HIGH,
                    source_name=self.name,
                    reason_code="high",
                )

        orchestrator.add_source(HighSource("HighSource"))
        orchestrator.add_source(CriticalSource("CriticalSource"))

        decision = orchestrator.process_turn(
            intent="test",
            extracted_data={},
        )

        assert decision.action == "critical_action"

    def test_final_state_is_final_flag_correct(self):
        """Verify is_final flag is correctly set for final states."""
        SourceRegistry.reset()

        sm = RegressionStateMachine(state="spin_situation")
        fc = RegressionFlowConfig()

        orchestrator = DialogueOrchestrator(
            state_machine=sm,
            flow_config=fc,
        )

        orchestrator._sources.clear()

        # Source that transitions to a final state
        class SoftCloseSource(KnowledgeSource):
            def should_contribute(self, bb):
                return True

            def contribute(self, bb):
                bb.propose_transition(
                    next_state="soft_close",
                    priority=Priority.HIGH,
                    source_name=self.name,
                    reason_code="final_transition",
                )

        orchestrator.add_source(SoftCloseSource("SoftCloseSource"))

        decision = orchestrator.process_turn(
            intent="test",
            extracted_data={},
        )

        sm_result = decision.to_sm_result()

        # When transitioning to a final state, is_final should be True
        assert decision.next_state == "soft_close"
        assert sm_result["is_final"] is True


# =============================================================================
# Boundary Condition Tests
# =============================================================================

class TestBoundaryConditions:
    """Tests for boundary conditions."""

    def test_objection_at_exact_limit(self):
        """Test behavior when exactly at objection limit."""
        SourceRegistry.reset()

        # At exact limit (3 consecutive)
        sm = RegressionStateMachine(
            state="spin_problem",
            objection_consecutive=3,
            objection_total=3,
        )
        fc = RegressionFlowConfig()

        orchestrator = DialogueOrchestrator(
            state_machine=sm,
            flow_config=fc,
        )

        from src.blackboard.sources.objection_guard import ObjectionGuardSource
        orchestrator._sources.clear()
        orchestrator.add_source(ObjectionGuardSource())

        decision = orchestrator.process_turn(
            intent="objection_price",
            extracted_data={},
        )

        # At limit should trigger soft_close
        assert decision.action == "objection_limit_reached"
        assert decision.next_state == "soft_close"

    def test_objection_just_under_limit(self):
        """Test behavior when just under objection limit."""
        SourceRegistry.reset()

        # Just under limit (2 consecutive, limit is 3)
        sm = RegressionStateMachine(
            state="spin_problem",
            objection_consecutive=2,
            objection_total=2,
        )
        fc = RegressionFlowConfig()

        orchestrator = DialogueOrchestrator(
            state_machine=sm,
            flow_config=fc,
        )

        from src.blackboard.sources.objection_guard import ObjectionGuardSource
        orchestrator._sources.clear()
        orchestrator.add_source(ObjectionGuardSource())

        decision = orchestrator.process_turn(
            intent="objection_price",
            extracted_data={},
        )

        # Under limit should NOT trigger soft_close
        assert decision.action != "objection_limit_reached"

    def test_persona_limit_applies_to_objection_no_time(self):
        """Busy persona limit should apply to objection_no_time intents."""
        SourceRegistry.reset()

        sm = RegressionStateMachine(
            state="spin_problem",
            collected_data={"persona": "busy"},
            objection_consecutive=2,
            objection_total=2,
        )
        fc = RegressionFlowConfig()

        orchestrator = DialogueOrchestrator(
            state_machine=sm,
            flow_config=fc,
        )

        from src.blackboard.sources.objection_guard import ObjectionGuardSource
        orchestrator._sources.clear()
        orchestrator.add_source(ObjectionGuardSource())

        decision = orchestrator.process_turn(
            intent="objection_no_time",
            extracted_data={},
        )

        assert decision.action == "objection_limit_reached"
        assert decision.next_state == "soft_close"
        assert sm.collected_data.get("_objection_limit_final") is True

    def test_empty_collected_data(self):
        """Test behavior with empty collected_data."""
        SourceRegistry.reset()

        sm = RegressionStateMachine(
            state="spin_situation",
            collected_data={},
        )
        fc = RegressionFlowConfig()

        orchestrator = DialogueOrchestrator(
            state_machine=sm,
            flow_config=fc,
        )

        decision = orchestrator.process_turn(
            intent="info_provided",
            extracted_data={},
        )

        # Should not crash, should continue normally
        assert decision is not None
        # Should stay in current state (data not complete)
        assert decision.next_state == "spin_situation" or "data_complete" not in decision.reason_codes

    def test_unknown_state_handling(self):
        """Test graceful handling of unknown state."""
        SourceRegistry.reset()

        sm = RegressionStateMachine(state="unknown_state")
        fc = RegressionFlowConfig()

        orchestrator = DialogueOrchestrator(
            state_machine=sm,
            flow_config=fc,
        )

        # Should not crash
        decision = orchestrator.process_turn(
            intent="test",
            extracted_data={},
        )

        assert decision is not None


# =============================================================================
# Determinism Tests
# =============================================================================

class TestDeterminism:
    """Tests ensuring deterministic behavior."""

    def test_same_input_produces_same_output(self):
        """Same inputs should always produce same outputs."""
        results = []

        for _ in range(5):
            SourceRegistry.reset()

            sm = RegressionStateMachine(
                state="spin_situation",
                collected_data={"company_size": "15"},
            )
            fc = RegressionFlowConfig()

            orchestrator = DialogueOrchestrator(
                state_machine=sm,
                flow_config=fc,
            )

            decision = orchestrator.process_turn(
                intent="price_question",
                extracted_data={},
            )

            results.append((decision.action, decision.next_state, tuple(sorted(decision.reason_codes))))

        # All results should be identical
        assert all(r == results[0] for r in results), \
            "Non-deterministic behavior detected"

    def test_source_order_independence(self):
        """
        Results should be deterministic regardless of source addition order.

        This tests that priority-based resolution works correctly.
        """
        results = []

        source_orders = [
            ["HighSource", "LowSource"],
            ["LowSource", "HighSource"],
        ]

        class HighSource(KnowledgeSource):
            def should_contribute(self, bb):
                return True

            def contribute(self, bb):
                bb.propose_action(
                    action="high_action",
                    priority=Priority.HIGH,
                    source_name=self.name,
                    reason_code="high",
                )

        class LowSource(KnowledgeSource):
            def should_contribute(self, bb):
                return True

            def contribute(self, bb):
                bb.propose_action(
                    action="low_action",
                    priority=Priority.LOW,
                    source_name=self.name,
                    reason_code="low",
                )

        for order in source_orders:
            SourceRegistry.reset()

            sm = RegressionStateMachine(state="spin_situation")
            fc = RegressionFlowConfig()

            orchestrator = DialogueOrchestrator(
                state_machine=sm,
                flow_config=fc,
            )

            orchestrator._sources.clear()

            for source_name in order:
                if source_name == "HighSource":
                    orchestrator.add_source(HighSource("HighSource"))
                else:
                    orchestrator.add_source(LowSource("LowSource"))

            decision = orchestrator.process_turn(
                intent="test",
                extracted_data={},
            )

            results.append(decision.action)

        # Regardless of source order, high priority should win
        assert all(r == "high_action" for r in results)


# =============================================================================
# to_sm_result() Regression Tests
# =============================================================================

class TestSmResultRegression:
    """Regression tests for to_sm_result() output format."""

    def test_sm_result_structure_unchanged(self):
        """
        Verify to_sm_result() structure remains consistent.

        This is critical for bot.py compatibility.
        """
        SourceRegistry.reset()

        sm = RegressionStateMachine(
            state="spin_situation",
            collected_data={"company_size": "15"},
        )
        fc = RegressionFlowConfig()

        orchestrator = DialogueOrchestrator(
            state_machine=sm,
            flow_config=fc,
        )

        decision = orchestrator.process_turn(
            intent="info_provided",
            extracted_data={},
        )

        sm_result = decision.to_sm_result()

        # Required fields (MUST be present)
        required_fields = [
            "action",
            "next_state",
            "prev_state",
            "goal",
            "collected_data",
            "missing_data",
            "optional_data",
            "is_final",
            "spin_phase",
            "circular_flow",
            "objection_flow",
            "reason_codes",
        ]

        for field in required_fields:
            assert field in sm_result, f"Required field '{field}' missing from sm_result"

    def test_sm_result_types_correct(self):
        """Verify to_sm_result() field types are correct."""
        SourceRegistry.reset()

        sm = RegressionStateMachine(
            state="spin_situation",
            collected_data={"company_size": "15"},
        )
        fc = RegressionFlowConfig()

        orchestrator = DialogueOrchestrator(
            state_machine=sm,
            flow_config=fc,
        )

        decision = orchestrator.process_turn(
            intent="info_provided",
            extracted_data={},
        )

        sm_result = decision.to_sm_result()

        # Type assertions
        assert isinstance(sm_result["action"], str)
        assert isinstance(sm_result["next_state"], str)
        assert isinstance(sm_result["prev_state"], str)
        assert isinstance(sm_result["goal"], str)
        assert isinstance(sm_result["collected_data"], dict)
        assert isinstance(sm_result["missing_data"], list)
        assert isinstance(sm_result["is_final"], bool)
        assert isinstance(sm_result["circular_flow"], dict)
        assert isinstance(sm_result["objection_flow"], dict)
        assert isinstance(sm_result["reason_codes"], list)

    def test_sm_result_modifiable_in_place(self):
        """Verify sm_result can be modified in-place (for DialoguePolicy)."""
        SourceRegistry.reset()

        sm = RegressionStateMachine(state="spin_situation")
        fc = RegressionFlowConfig()

        orchestrator = DialogueOrchestrator(
            state_machine=sm,
            flow_config=fc,
        )

        decision = orchestrator.process_turn(
            intent="info_provided",
            extracted_data={},
        )

        sm_result = decision.to_sm_result()

        # Modify in place (as DialoguePolicy does)
        sm_result["action"] = "modified_action"
        sm_result["next_state"] = "modified_state"
        sm_result["custom_field"] = "custom_value"

        # Changes should persist
        assert sm_result["action"] == "modified_action"
        assert sm_result["next_state"] == "modified_state"
        assert sm_result["custom_field"] == "custom_value"


# =============================================================================
# Phase Consistency Tests
# =============================================================================

class TestPhaseConsistency:
    """
    Regression tests for state_to_phase and get_phase_for_state consistency.

    BUG FIX: Prior to this fix, state_to_phase only contained reverse mapping
    from phase_mapping, while get_phase_for_state checked explicit phases first.
    This caused inconsistent results when:
    - A state had explicit phase in state config
    - A state had phase mapping that differed from explicit phase

    The fix ensures state_to_phase is the CANONICAL source of truth and includes
    both explicit phases and reverse mapping (with explicit having priority).
    """

    def test_state_to_phase_includes_explicit_phases(self):
        """state_to_phase should include explicit phases from state configs."""
        states = {
            "spin_situation": {"phase": "situation", "goal": "Gather situation"},
            "spin_problem": {"phase": "problem", "goal": "Find problems"},
            "greeting": {"goal": "Welcome user"},  # No phase
        }
        fc = RegressionFlowConfig(states=states)

        state_to_phase = fc.state_to_phase

        # Explicit phases should be in state_to_phase
        assert state_to_phase.get("spin_situation") == "situation"
        assert state_to_phase.get("spin_problem") == "problem"
        # Non-phase state should not be in mapping
        assert state_to_phase.get("greeting") is None

    def test_state_to_phase_and_get_phase_for_state_consistent(self):
        """state_to_phase and get_phase_for_state should return same values."""
        states = {
            "spin_situation": {"phase": "situation", "goal": "Gather situation"},
            "spin_problem": {"spin_phase": "problem", "goal": "Find problems"},  # spin_phase variant
            "bant_budget": {"goal": "Check budget"},  # No explicit phase
            "greeting": {"goal": "Welcome user"},  # No phase
        }
        fc = RegressionFlowConfig(states=states)

        # For all states, state_to_phase and get_phase_for_state should match
        for state_name in states.keys():
            from_property = fc.state_to_phase.get(state_name)
            from_method = fc.get_phase_for_state(state_name)
            assert from_property == from_method, (
                f"Inconsistency for {state_name}: "
                f"state_to_phase={from_property}, get_phase_for_state={from_method}"
            )

    def test_explicit_phase_overrides_mapping(self):
        """
        When a state has both explicit phase AND is in phase_mapping,
        explicit phase should take priority.

        This is the core bug scenario that was fixed.
        """
        # Create a config where:
        # - phase_mapping says: mapped_phase -> my_state
        # - state config says: my_state.phase = explicit_phase
        states = {
            "my_state": {
                "phase": "explicit_phase",  # Explicit phase
                "goal": "Test state",
            }
        }

        class ConflictingFlowConfig(RegressionFlowConfig):
            """FlowConfig with conflicting mapping."""

            def __init__(self):
                super().__init__(states=states)

            @property
            def phase_mapping(self) -> Dict[str, str]:
                # This mapping conflicts with explicit phase in state config
                return {"mapped_phase": "my_state"}

        fc = ConflictingFlowConfig()

        # Both should return explicit_phase (explicit has priority)
        assert fc.state_to_phase.get("my_state") == "explicit_phase"
        assert fc.get_phase_for_state("my_state") == "explicit_phase"

    def test_mapping_only_states(self):
        """States with only mapping (no explicit phase) should still work."""
        # BANT-style flow where phases are defined only in mapping
        states = {
            "bant_budget": {"goal": "Check budget"},
            "bant_authority": {"goal": "Check authority"},
        }

        class MappingOnlyFlowConfig(RegressionFlowConfig):
            """FlowConfig with only mapping, no explicit phases."""

            def __init__(self):
                super().__init__(states=states)

            @property
            def phase_mapping(self) -> Dict[str, str]:
                return {
                    "budget": "bant_budget",
                    "authority": "bant_authority",
                }

        fc = MappingOnlyFlowConfig()

        # Should resolve from mapping
        assert fc.state_to_phase.get("bant_budget") == "budget"
        assert fc.state_to_phase.get("bant_authority") == "authority"
        assert fc.get_phase_for_state("bant_budget") == "budget"
        assert fc.get_phase_for_state("bant_authority") == "authority"

    def test_mixed_explicit_and_mapping(self):
        """
        Mixed flow with some explicit phases and some mapping-only.

        This is the real-world scenario (SPIN has explicit, BANT uses mapping).
        """
        states = {
            # SPIN-style with explicit phase
            "spin_situation": {"phase": "situation", "goal": "Gather situation"},
            # BANT-style without explicit phase (uses mapping)
            "bant_budget": {"goal": "Check budget"},
            # Non-phase state
            "greeting": {"goal": "Welcome"},
        }

        class MixedFlowConfig(RegressionFlowConfig):
            """FlowConfig with mixed explicit and mapping phases."""

            def __init__(self):
                super().__init__(states=states)

            @property
            def phase_mapping(self) -> Dict[str, str]:
                return {"budget": "bant_budget"}

        fc = MixedFlowConfig()

        # Explicit phase
        assert fc.state_to_phase.get("spin_situation") == "situation"
        assert fc.get_phase_for_state("spin_situation") == "situation"

        # Mapping phase
        assert fc.state_to_phase.get("bant_budget") == "budget"
        assert fc.get_phase_for_state("bant_budget") == "budget"

        # No phase
        assert fc.state_to_phase.get("greeting") is None
        assert fc.get_phase_for_state("greeting") is None

    def test_spin_phase_key_supported(self):
        """spin_phase key should be supported as alias for phase."""
        states = {
            "old_style_state": {"spin_phase": "legacy_phase", "goal": "Test"},
        }
        fc = RegressionFlowConfig(states=states)

        assert fc.state_to_phase.get("old_style_state") == "legacy_phase"
        assert fc.get_phase_for_state("old_style_state") == "legacy_phase"

    def test_nonexistent_state_returns_none(self):
        """Getting phase for nonexistent state should return None."""
        fc = RegressionFlowConfig(states={
            "existing": {"phase": "test_phase", "goal": "Test"},
        })

        assert fc.get_phase_for_state("nonexistent") is None
        assert fc.state_to_phase.get("nonexistent") is None

    def test_is_phase_state_consistent(self):
        """is_phase_state should be consistent with get_phase_for_state."""
        states = {
            "phase_state": {"phase": "test_phase", "goal": "Test"},
            "non_phase_state": {"goal": "Test"},
        }
        fc = RegressionFlowConfig(states=states)

        # Phase state
        assert fc.is_phase_state("phase_state") is True
        assert fc.get_phase_for_state("phase_state") is not None

        # Non-phase state
        assert fc.is_phase_state("non_phase_state") is False
        assert fc.get_phase_for_state("non_phase_state") is None

        # Nonexistent state
        assert fc.is_phase_state("nonexistent") is False
        assert fc.get_phase_for_state("nonexistent") is None
