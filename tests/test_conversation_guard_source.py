# tests/test_conversation_guard_source.py

"""
Tests for ConversationGuardSource.

Test categories:
1. Unit tests: Guard returns each tier → correct proposals
2. Conflict resolution tests: Guard vs other sources
3. Integration tests: Feature flag toggle, degradation logic
"""

import pytest
from typing import Dict, Any, Optional, List
from unittest.mock import Mock, MagicMock, patch

from src.blackboard.blackboard import DialogueBlackboard
from src.blackboard.enums import Priority, ProposalType
from src.blackboard.sources.conversation_guard_ks import ConversationGuardSource, TIER_MAP


# =============================================================================
# Mock Implementations
# =============================================================================

class MockStateMachine:
    """Mock StateMachine implementing IStateMachine protocol."""

    def __init__(self, state: str = "greeting", collected_data: Optional[Dict[str, Any]] = None):
        self._state = state
        self._collected_data = collected_data or {}
        self._current_phase = None
        self._last_action = None
        self._intent_tracker = None
        self._state_before_objection = None
        self.circular_flow = Mock()
        self.circular_flow.get_stats.return_value = {}

    @property
    def state(self) -> str:
        return self._state

    @state.setter
    def state(self, value: str) -> None:
        self._state = value

    @property
    def collected_data(self) -> Dict[str, Any]:
        return self._collected_data

    @collected_data.setter
    def collected_data(self, value):
        self._collected_data = value

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

    @property
    def state_before_objection(self) -> Optional[str]:
        return self._state_before_objection

    @state_before_objection.setter
    def state_before_objection(self, value: Optional[str]) -> None:
        self._state_before_objection = value

    def update_data(self, data: Dict[str, Any]) -> None:
        self._collected_data.update(data)

    def is_final(self) -> bool:
        return self._state in ("closed", "rejected", "soft_close")

    def transition_to(self, **kwargs):
        next_state = kwargs.get("next_state", self._state)
        self._state = next_state

    def sync_phase_from_state(self) -> None:
        pass


class MockIntentTracker:
    """Mock IntentTracker implementing IIntentTracker protocol."""

    def __init__(self, turn_number: int = 0):
        self._turn_number = turn_number
        self._prev_intent = None
        self._intents = []
        self._objection_consecutive = 0
        self._objection_total = 0

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

    def advance_turn(self) -> None:
        self._turn_number += 1

    def objection_consecutive(self) -> int:
        return self._objection_consecutive

    def objection_total(self) -> int:
        return self._objection_total

    def total_count(self, intent: str) -> int:
        return sum(1 for i, _ in self._intents if i == intent)

    def category_total(self, category: str) -> int:
        return 0

    def get_intents_by_category(self, category: str) -> list:
        return []


class MockFlowConfig:
    """Mock FlowConfig implementing IFlowConfig protocol."""

    def __init__(self, states: Optional[Dict[str, Dict[str, Any]]] = None):
        self._states = states or {
            "greeting": {"goal": "Greet user"},
            "spin_situation": {
                "goal": "Gather situation",
                "phase": "situation",
                "required_data": ["company_name"],
                "transitions": {"data_complete": "spin_problem"},
            },
            "spin_problem": {
                "goal": "Identify problems",
                "phase": "problem",
                "required_data": ["problem"],
            },
            "spin_implication": {
                "goal": "Explore implications",
                "phase": "implication",
            },
            "close": {"goal": "Close deal", "is_final": True},
            "soft_close": {"goal": "Graceful exit", "is_final": True},
            "_limits": {"max_consecutive_objections": 3, "max_total_objections": 5},
        }

    @property
    def states(self) -> Dict[str, Dict[str, Any]]:
        return self._states

    def to_dict(self) -> Dict[str, Any]:
        return {"states": self._states}

    @property
    def phase_mapping(self) -> Dict[str, str]:
        mapping = {}
        for state_name, state_config in self._states.items():
            phase = state_config.get("phase") or state_config.get("spin_phase")
            if phase:
                mapping[phase] = state_name
        return mapping

    @property
    def state_to_phase(self) -> Dict[str, str]:
        result = {v: k for k, v in self.phase_mapping.items()}
        for state_name, state_config in self._states.items():
            explicit_phase = state_config.get("phase") or state_config.get("spin_phase")
            if explicit_phase:
                result[state_name] = explicit_phase
        return result

    def get_phase_for_state(self, state_name: str) -> Optional[str]:
        return self.state_to_phase.get(state_name)

    def is_phase_state(self, state_name: str) -> bool:
        return self.get_phase_for_state(state_name) is not None

    def get_state_on_enter_flags(self, state_name: str) -> Dict[str, Any]:
        config = self._states.get(state_name, {})
        on_enter = config.get("on_enter", {})
        if isinstance(on_enter, dict):
            return on_enter.get("set_flags", {})
        return {}

    @property
    def skip_map(self) -> Dict[str, str]:
        return {
            "greeting": "spin_situation",
            "spin_situation": "spin_problem",
            "spin_problem": "spin_implication",
            "spin_implication": "close",
        }

    @property
    def constants(self) -> Dict[str, Any]:
        return {}


def create_blackboard(
    state: str = "spin_situation",
    collected_data: Optional[Dict[str, Any]] = None,
    states: Optional[Dict[str, Dict[str, Any]]] = None,
    intent: str = "info_provided",
    extracted_data: Optional[Dict[str, Any]] = None,
    user_message: str = "test message",
    frustration_level: int = 0,
) -> DialogueBlackboard:
    """Helper to create a blackboard with turn started."""
    sm = MockStateMachine(state=state, collected_data=collected_data or {})
    flow_config = MockFlowConfig(states=states)
    tracker = MockIntentTracker()

    bb = DialogueBlackboard(
        state_machine=sm,
        flow_config=flow_config,
        intent_tracker=tracker,
    )
    bb.begin_turn(
        intent=intent,
        extracted_data=extracted_data or {},
        user_message=user_message,
        frustration_level=frustration_level,
    )
    return bb


def create_mock_guard(tier_return=None, can_continue=True):
    """Create a mock ConversationGuard that returns specified tier."""
    guard = Mock()
    guard.check = Mock(return_value=(can_continue, tier_return))
    return guard


def create_mock_fallback_handler(skip_target="spin_problem"):
    """Create a mock FallbackHandler with a skip target."""
    handler = Mock()
    handler._find_valid_skip_target = Mock(return_value=skip_target)
    handler.get_fallback = Mock(return_value=Mock(
        message="Fallback message",
        options=[{"label": "Option 1"}],
    ))
    handler.generate_options_menu = Mock(return_value=Mock(
        message="Options menu",
    ))
    return handler


# =============================================================================
# Unit Tests: ConversationGuardSource
# =============================================================================

class TestConversationGuardSourceInit:
    """Test ConversationGuardSource initialization."""

    def test_init_default(self):
        source = ConversationGuardSource()
        assert source.name == "ConversationGuardSource"
        assert source._enabled is True
        assert source._guard is None

    def test_init_with_guard(self):
        guard = create_mock_guard()
        source = ConversationGuardSource(guard=guard)
        assert source._guard is guard

    def test_init_with_fallback_handler(self):
        handler = create_mock_fallback_handler()
        source = ConversationGuardSource(fallback_handler=handler)
        assert source._fallback_handler is handler

    def test_init_disabled(self):
        source = ConversationGuardSource(enabled=False)
        assert source._enabled is False


class TestConversationGuardSourceShouldContribute:
    """Test should_contribute() gating logic."""

    def test_returns_false_when_disabled(self):
        guard = create_mock_guard()
        source = ConversationGuardSource(guard=guard, enabled=False)
        bb = create_blackboard()
        assert source.should_contribute(bb) is False

    @patch("src.blackboard.sources.conversation_guard_ks.flags")
    def test_returns_false_when_flag_off(self, mock_flags):
        mock_flags.is_enabled = Mock(return_value=False)
        guard = create_mock_guard()
        source = ConversationGuardSource(guard=guard)
        bb = create_blackboard()
        assert source.should_contribute(bb) is False

    @patch("src.blackboard.sources.conversation_guard_ks.flags")
    def test_returns_false_without_guard(self, mock_flags):
        mock_flags.is_enabled = Mock(return_value=True)
        source = ConversationGuardSource(guard=None)
        bb = create_blackboard()
        assert source.should_contribute(bb) is False

    @patch("src.blackboard.sources.conversation_guard_ks.flags")
    def test_returns_true_when_all_conditions_met(self, mock_flags):
        mock_flags.is_enabled = Mock(return_value=True)
        guard = create_mock_guard()
        source = ConversationGuardSource(guard=guard)
        bb = create_blackboard()
        assert source.should_contribute(bb) is True


class TestConversationGuardSourceContribute:
    """Test contribute() — tier → proposal mapping."""

    def _make_source_and_bb(self, tier_return, can_continue=True,
                             skip_target="spin_problem", **bb_kwargs):
        """Helper to create source and blackboard for contribute tests."""
        guard = create_mock_guard(tier_return=tier_return, can_continue=can_continue)
        handler = create_mock_fallback_handler(skip_target=skip_target)
        source = ConversationGuardSource(guard=guard, fallback_handler=handler)
        bb = create_blackboard(**bb_kwargs)
        return source, bb

    def test_no_intervention_no_proposals(self):
        """Guard returns None → no proposals."""
        source, bb = self._make_source_and_bb(tier_return=None)
        source.contribute(bb)
        assert len(bb.get_action_proposals()) == 0
        assert len(bb.get_transition_proposals()) == 0

    def test_tier_1_rephrase(self):
        """TIER_1 → guard_rephrase, NORMAL, combinable=True, no transition."""
        source, bb = self._make_source_and_bb(tier_return="fallback_tier_1")
        source.contribute(bb)

        actions = bb.get_action_proposals()
        assert len(actions) == 1
        assert actions[0].value == "guard_rephrase"
        assert actions[0].priority == Priority.NORMAL
        assert actions[0].combinable is True
        assert actions[0].source_name == "ConversationGuardSource"

        transitions = bb.get_transition_proposals()
        assert len(transitions) == 0

    def test_tier_2_options(self):
        """TIER_2 → guard_offer_options, HIGH, combinable=False, no transition."""
        source, bb = self._make_source_and_bb(tier_return="fallback_tier_2")
        source.contribute(bb)

        actions = bb.get_action_proposals()
        assert len(actions) == 1
        assert actions[0].value == "guard_offer_options"
        assert actions[0].priority == Priority.HIGH
        assert actions[0].combinable is False

        transitions = bb.get_transition_proposals()
        assert len(transitions) == 0

    def test_tier_3_skip_with_valid_target(self):
        """TIER_3 + valid skip target → guard_skip_phase, HIGH, transition."""
        source, bb = self._make_source_and_bb(
            tier_return="fallback_tier_3",
            skip_target="spin_problem",
        )
        source.contribute(bb)

        actions = bb.get_action_proposals()
        assert len(actions) == 1
        assert actions[0].value == "guard_skip_phase"
        assert actions[0].priority == Priority.HIGH
        assert actions[0].combinable is True
        assert actions[0].metadata["to_state"] == "spin_problem"

        transitions = bb.get_transition_proposals()
        assert len(transitions) == 1
        assert transitions[0].value == "spin_problem"
        assert transitions[0].priority == Priority.HIGH

    def test_tier_3_degradation_no_skip_target(self):
        """TIER_3 without valid skip target → degrades to TIER_2 behavior."""
        source, bb = self._make_source_and_bb(
            tier_return="fallback_tier_3",
            skip_target=None,
        )
        source.contribute(bb)

        actions = bb.get_action_proposals()
        assert len(actions) == 1
        assert actions[0].value == "guard_offer_options"
        assert actions[0].priority == Priority.HIGH
        assert actions[0].combinable is False

        transitions = bb.get_transition_proposals()
        assert len(transitions) == 0

    def test_tier_4_soft_close(self):
        """TIER_4 → guard_soft_close, CRITICAL, transition to soft_close."""
        source, bb = self._make_source_and_bb(
            tier_return="soft_close",
            can_continue=False,
        )
        source.contribute(bb)

        actions = bb.get_action_proposals()
        assert len(actions) == 1
        assert actions[0].value == "guard_soft_close"
        assert actions[0].priority == Priority.CRITICAL
        assert actions[0].combinable is True
        assert actions[0].metadata["can_continue"] is False

        transitions = bb.get_transition_proposals()
        assert len(transitions) == 1
        assert transitions[0].value == "soft_close"
        assert transitions[0].priority == Priority.CRITICAL

    def test_frustration_level_read_from_context(self):
        """Verify frustration_level is read from ContextSnapshot, not envelope."""
        guard = create_mock_guard(tier_return="fallback_tier_2")
        handler = create_mock_fallback_handler()
        source = ConversationGuardSource(guard=guard, fallback_handler=handler)
        bb = create_blackboard(frustration_level=7)
        source.contribute(bb)

        # Verify guard.check was called with the correct frustration_level
        guard.check.assert_called_once()
        call_kwargs = guard.check.call_args
        assert call_kwargs[1]["frustration_level"] == 7

    def test_user_message_read_from_context(self):
        """Verify user_message is read from ContextSnapshot."""
        guard = create_mock_guard(tier_return="fallback_tier_1")
        handler = create_mock_fallback_handler()
        source = ConversationGuardSource(guard=guard, fallback_handler=handler)
        bb = create_blackboard(user_message="I'm frustrated")
        source.contribute(bb)

        guard.check.assert_called_once()
        call_kwargs = guard.check.call_args
        assert call_kwargs[1]["message"] == "I'm frustrated"

    def test_metadata_includes_tier_and_can_continue(self):
        """Verify metadata contains tier and can_continue."""
        source, bb = self._make_source_and_bb(
            tier_return="fallback_tier_2",
            can_continue=True,
        )
        source.contribute(bb)

        actions = bb.get_action_proposals()
        assert actions[0].metadata["tier"] == "fallback_tier_2"
        assert actions[0].metadata["can_continue"] is True


class TestConversationGuardSourceGetSkipTarget:
    """Test _get_skip_target() method."""

    def test_returns_none_without_fallback_handler(self):
        guard = create_mock_guard(tier_return="fallback_tier_3")
        source = ConversationGuardSource(guard=guard, fallback_handler=None)
        bb = create_blackboard()
        source.contribute(bb)

        # Should degrade to TIER_2 because _get_skip_target returns None
        actions = bb.get_action_proposals()
        assert actions[0].value == "guard_offer_options"

    def test_delegates_to_fallback_handler(self):
        guard = create_mock_guard(tier_return="fallback_tier_3")
        handler = create_mock_fallback_handler(skip_target="spin_implication")
        source = ConversationGuardSource(guard=guard, fallback_handler=handler)
        bb = create_blackboard(state="spin_problem")
        source.contribute(bb)

        handler._find_valid_skip_target.assert_called_once()
        actions = bb.get_action_proposals()
        assert actions[0].value == "guard_skip_phase"
        assert actions[0].metadata["to_state"] == "spin_implication"


# =============================================================================
# Conflict Resolution Tests
# =============================================================================

class TestConversationGuardSourceConflictResolution:
    """Test conflict resolution: Guard proposals vs other sources."""

    def _resolve(self, bb):
        """Run conflict resolution on blackboard proposals."""
        from src.blackboard.conflict_resolver import ConflictResolver
        resolver = ConflictResolver(default_action="continue_current_goal")
        proposals = bb.get_proposals()
        return resolver.resolve_with_fallback(
            proposals=proposals,
            current_state=bb.current_state,
            fallback_transition=None,
        )

    def test_tier_2_guard_vs_disambiguation(self):
        """Guard TIER_2 (priority_order=7) vs Disambiguation (priority_order=8).
        Guard should win because it has the same priority (HIGH) but
        lower priority_order → appears first in proposal list."""
        bb = create_blackboard(state="spin_situation", intent="unclear")

        # Guard TIER_2 proposal
        bb.propose_action(
            action="guard_offer_options",
            priority=Priority.HIGH,
            combinable=False,
            source_name="ConversationGuardSource",
            reason_code="conversation_guard_tier_2",
        )

        # Disambiguation proposal
        bb.propose_action(
            action="ask_clarification",
            priority=Priority.HIGH,
            combinable=False,
            source_name="DisambiguationSource",
            reason_code="disambiguation_needed",
        )

        decision = self._resolve(bb)
        assert decision.action == "guard_offer_options"

    def test_tier_1_guard_vs_transition(self):
        """Guard TIER_1 (NORMAL) vs TransitionResolver (NORMAL).
        TransitionResolver wins because its transition is higher priority
        when actions are combinable."""
        bb = create_blackboard(state="spin_situation", intent="info_provided")

        # Guard TIER_1 proposal (combinable)
        bb.propose_action(
            action="guard_rephrase",
            priority=Priority.NORMAL,
            combinable=True,
            source_name="ConversationGuardSource",
            reason_code="conversation_guard_tier_1",
        )

        # TransitionResolver proposal
        bb.propose_transition(
            next_state="spin_problem",
            priority=Priority.NORMAL,
            source_name="TransitionResolverSource",
            reason_code="data_complete",
        )

        decision = self._resolve(bb)
        # Transition should be applied (combinable=True allows it)
        assert decision.next_state == "spin_problem"

    def test_tier_4_guard_vs_any_source(self):
        """Guard TIER_4 (CRITICAL) vs any source → Guard wins."""
        bb = create_blackboard(state="spin_situation", intent="info_provided")

        # Guard TIER_4 proposal
        bb.propose_action(
            action="guard_soft_close",
            priority=Priority.CRITICAL,
            combinable=True,
            source_name="ConversationGuardSource",
            reason_code="conversation_guard_soft_close",
        )
        bb.propose_transition(
            next_state="soft_close",
            priority=Priority.CRITICAL,
            source_name="ConversationGuardSource",
            reason_code="conversation_guard_soft_close_transition",
        )

        # TransitionResolver proposal (NORMAL)
        bb.propose_transition(
            next_state="spin_problem",
            priority=Priority.NORMAL,
            source_name="TransitionResolverSource",
            reason_code="data_complete",
        )

        decision = self._resolve(bb)
        assert decision.action == "guard_soft_close"
        assert decision.next_state == "soft_close"

    def test_tier_3_guard_vs_stall_guard(self):
        """Guard TIER_3 (HIGH, priority_order=7) vs StallGuard (HIGH, priority_order=45).
        Guard wins due to lower priority_order → appears first in proposals."""
        bb = create_blackboard(state="spin_situation", intent="unclear")

        # Guard TIER_3 proposal
        bb.propose_action(
            action="guard_skip_phase",
            priority=Priority.HIGH,
            combinable=True,
            source_name="ConversationGuardSource",
            reason_code="conversation_guard_tier_3",
        )
        bb.propose_transition(
            next_state="spin_problem",
            priority=Priority.HIGH,
            source_name="ConversationGuardSource",
            reason_code="conversation_guard_tier_3_transition",
        )

        # StallGuard proposal
        bb.propose_action(
            action="stall_guard_eject",
            priority=Priority.HIGH,
            combinable=True,
            source_name="StallGuardSource",
            reason_code="max_turns_exceeded",
        )
        bb.propose_transition(
            next_state="close",
            priority=Priority.HIGH,
            source_name="StallGuardSource",
            reason_code="stall_guard_transition",
        )

        decision = self._resolve(bb)
        # Guard proposal comes first (lower priority_order)
        assert decision.action == "guard_skip_phase"


# =============================================================================
# Feature Flag & Integration Tests
# =============================================================================

class TestConversationGuardSourceFeatureFlag:
    """Test feature flag gating."""

    @patch("src.blackboard.sources.conversation_guard_ks.flags")
    def test_flag_off_skips_contribution(self, mock_flags):
        mock_flags.is_enabled = Mock(return_value=False)
        guard = create_mock_guard(tier_return="fallback_tier_2")
        source = ConversationGuardSource(guard=guard)
        bb = create_blackboard()

        assert source.should_contribute(bb) is False
        # contribute() should not be called, but even if called, guard check won't run

    @patch("src.blackboard.sources.conversation_guard_ks.flags")
    def test_flag_on_enables_contribution(self, mock_flags):
        mock_flags.is_enabled = Mock(return_value=True)
        guard = create_mock_guard(tier_return="fallback_tier_1")
        handler = create_mock_fallback_handler()
        source = ConversationGuardSource(guard=guard, fallback_handler=handler)
        bb = create_blackboard()

        assert source.should_contribute(bb) is True
        source.contribute(bb)
        assert len(bb.get_action_proposals()) == 1


class TestConversationGuardSourceContextSnapshot:
    """Test that ContextSnapshot properly carries user_message and frustration_level."""

    def test_user_message_in_context_snapshot(self):
        """user_message passed to begin_turn appears in ContextSnapshot."""
        bb = create_blackboard(user_message="Tell me about pricing")
        ctx = bb.get_context()
        assert ctx.user_message == "Tell me about pricing"

    def test_frustration_level_in_context_snapshot(self):
        """frustration_level passed to begin_turn appears in ContextSnapshot."""
        bb = create_blackboard(frustration_level=8)
        ctx = bb.get_context()
        assert ctx.frustration_level == 8

    def test_default_values(self):
        """Default values for user_message and frustration_level."""
        sm = MockStateMachine(state="greeting")
        flow = MockFlowConfig()
        tracker = MockIntentTracker()
        bb = DialogueBlackboard(state_machine=sm, flow_config=flow, intent_tracker=tracker)
        bb.begin_turn(intent="greeting", extracted_data={})
        ctx = bb.get_context()
        assert ctx.user_message == ""
        assert ctx.frustration_level == 0


class TestConversationGuardTier2Escalation:
    """Test TIER_2 self-loop escalation moved into ConversationGuard."""

    def test_escalation_after_threshold(self):
        """After max_consecutive_tier_2 in same state, escalate to TIER_3."""
        from src.conversation_guard import ConversationGuard, GuardConfig

        config = GuardConfig(max_consecutive_tier_2=2)
        guard = ConversationGuard(config=config)

        # First TIER_2 in state
        result = guard._apply_tier_2_escalation("spin_situation", guard.TIER_2)
        assert result == guard.TIER_2
        assert guard._state.consecutive_tier_2_count == 1

        # Second TIER_2 in same state — should escalate
        result = guard._apply_tier_2_escalation("spin_situation", guard.TIER_2)
        assert result == guard.TIER_3
        assert guard._state.consecutive_tier_2_count == 0  # reset after escalation

    def test_reset_on_state_change(self):
        """Consecutive count resets when state changes."""
        from src.conversation_guard import ConversationGuard, GuardConfig

        config = GuardConfig(max_consecutive_tier_2=3)
        guard = ConversationGuard(config=config)

        guard._apply_tier_2_escalation("spin_situation", guard.TIER_2)
        assert guard._state.consecutive_tier_2_count == 1

        # Different state resets count
        guard._apply_tier_2_escalation("spin_problem", guard.TIER_2)
        assert guard._state.consecutive_tier_2_count == 1
        assert guard._state.consecutive_tier_2_state == "spin_problem"

    def test_reset_on_non_tier_2(self):
        """Consecutive count resets when non-TIER_2 result."""
        from src.conversation_guard import ConversationGuard, GuardConfig

        config = GuardConfig(max_consecutive_tier_2=3)
        guard = ConversationGuard(config=config)

        guard._apply_tier_2_escalation("spin_situation", guard.TIER_2)
        assert guard._state.consecutive_tier_2_count == 1

        # TIER_1 resets
        guard._apply_tier_2_escalation("spin_situation", guard.TIER_1)
        assert guard._state.consecutive_tier_2_count == 0
        assert guard._state.consecutive_tier_2_state is None


class TestDialoguePolicyGuardBypass:
    """Test that DialoguePolicy bypasses guard actions."""

    def test_guard_actions_bypass_policy(self):
        """Guard actions should not be overridden by policy."""
        from src.dialogue_policy import DialoguePolicy

        policy = DialoguePolicy(trace_enabled=False)

        guard_actions = [
            "guard_rephrase", "guard_offer_options",
            "guard_skip_phase", "guard_soft_close",
        ]

        for action in guard_actions:
            sm_result = {"action": action, "next_state": "spin_situation"}
            # Create a minimal envelope mock
            envelope = Mock()
            result = policy.maybe_override(sm_result, envelope)
            assert result is None, f"Policy should bypass {action}"


class TestTierMapCompleteness:
    """Test that TIER_MAP covers all tiers."""

    def test_all_tiers_mapped(self):
        """TIER_MAP covers all expected tiers."""
        from src.conversation_guard import ConversationGuard

        expected_tiers = [
            ConversationGuard.TIER_1,
            ConversationGuard.TIER_2,
            ConversationGuard.TIER_3,
            ConversationGuard.TIER_4,
        ]

        for tier in expected_tiers:
            assert tier in TIER_MAP, f"Tier {tier} not in TIER_MAP"

    def test_tier_map_actions_unique(self):
        """Each tier maps to a unique action."""
        actions = [spec["action"] for spec in TIER_MAP.values()]
        assert len(actions) == len(set(actions))

    def test_tier_map_priorities(self):
        """Verify expected priority mapping."""
        assert TIER_MAP["fallback_tier_1"]["priority"] == Priority.NORMAL
        assert TIER_MAP["fallback_tier_2"]["priority"] == Priority.HIGH
        assert TIER_MAP["fallback_tier_3"]["priority"] == Priority.HIGH
        assert TIER_MAP["soft_close"]["priority"] == Priority.CRITICAL

    def test_tier_map_combinable(self):
        """Verify expected combinable mapping."""
        assert TIER_MAP["fallback_tier_1"]["combinable"] is True
        assert TIER_MAP["fallback_tier_2"]["combinable"] is False
        assert TIER_MAP["fallback_tier_3"]["combinable"] is True
        assert TIER_MAP["soft_close"]["combinable"] is True


class TestFeatureFlagRegistration:
    """Test that the feature flag is properly registered."""

    def test_flag_exists_in_defaults(self):
        from src.feature_flags import FeatureFlags
        assert "conversation_guard_in_pipeline" in FeatureFlags.DEFAULTS

    def test_flag_default_false(self):
        from src.feature_flags import FeatureFlags
        assert FeatureFlags.DEFAULTS["conversation_guard_in_pipeline"] is False

    def test_flag_property(self):
        from src.feature_flags import flags
        # Should not raise
        _ = flags.conversation_guard_in_pipeline


class TestSourceRegistration:
    """Test that ConversationGuardSource is registered in SourceRegistry."""

    def test_source_registered(self):
        from src.blackboard.source_registry import SourceRegistry
        reg = SourceRegistry.get_registration("ConversationGuardSource")
        assert reg is not None
        assert reg.priority_order == 7
        assert reg.enabled_by_default is True

    def test_source_order_between_goback_and_disambiguation(self):
        from src.blackboard.source_registry import SourceRegistry
        guard_reg = SourceRegistry.get_registration("ConversationGuardSource")
        goback_reg = SourceRegistry.get_registration("GoBackGuardSource")
        disamb_reg = SourceRegistry.get_registration("DisambiguationSource")

        assert goback_reg.priority_order < guard_reg.priority_order < disamb_reg.priority_order
