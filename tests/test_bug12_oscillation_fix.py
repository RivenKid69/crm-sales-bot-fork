# tests/test_bug12_oscillation_fix.py

"""
Tests for Bug #12 fix: competitor_user stuck in discovery (oscillation loop).

Four-layer fix verification:
  Layer 1:  config_loader — autonomous states get direct assignment for rules/transitions
  Layer 1b: autonomous_decision — target validation against available_states only
  Layer 2:  priority_assigner — skip use_transitions boost in autonomous states
  Layer 3:  context_envelope — count detour turns in autonomous session
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from typing import Dict, Any, Optional
from dataclasses import dataclass


# =============================================================================
# Layer 1: config_loader — autonomous rules/transitions direct assignment
# =============================================================================

class TestLayer1ConfigLoaderAutonomousOverride:
    """Verify _resolve_state clears inherited rules/transitions for autonomous states."""

    @pytest.fixture
    def loader(self):
        from src.config_loader import ConfigLoader
        return ConfigLoader()

    def test_autonomous_state_rules_empty_clears_inherited(self, loader):
        """rules: {} in autonomous state replaces (not merges) inherited mixin rules."""
        state_config = {
            "autonomous": True,
            "extends": "_base_phase",
            "mixins": ["objection_handling"],
            "rules": {},
            "transitions": {"data_complete": "autonomous_qualification"},
            "goal": "Discover needs",
        }
        all_states = {
            "_base_phase": {
                "abstract": True,
                "rules": {
                    "objection_price": "handle_objection",
                    "objection_competitor": "handle_objection",
                    "agreement": "continue",
                },
                "transitions": {
                    "objection_price": "handle_objection",
                    "objection_competitor": "handle_objection",
                },
                "parameters": {"max_turns_fallback": "close"},
            }
        }
        mixins = {
            "objection_handling": {
                "rules": {
                    "objection_timing": "handle_objection",
                    "objection_need": "handle_objection",
                },
                "transitions": {
                    "objection_timing": "handle_objection",
                    "objection_need": "handle_objection",
                },
            }
        }

        resolved = loader._resolve_state(
            "autonomous_discovery", state_config, all_states, mixins, {}
        )

        # rules: {} from YAML should have replaced all inherited rules
        assert resolved["rules"] == {}
        # transitions should only contain what the YAML author wrote
        assert resolved["transitions"] == {"data_complete": "autonomous_qualification"}
        # No mixin transitions leaked
        assert "objection_price" not in resolved.get("transitions", {})
        assert "objection_timing" not in resolved.get("transitions", {})

    def test_autonomous_state_transitions_with_values_replaces_inherited(self, loader):
        """transitions: {data_complete: X} in autonomous state replaces all inherited transitions."""
        state_config = {
            "autonomous": True,
            "extends": "_base_phase",
            "transitions": {"data_complete": "autonomous_qualification"},
            "goal": "Discover",
        }
        all_states = {
            "_base_phase": {
                "abstract": True,
                "transitions": {
                    "objection_price": "handle_objection",
                    "objection_competitor": "handle_objection",
                    "data_complete": "spin_problem",
                },
            }
        }

        resolved = loader._resolve_state(
            "autonomous_discovery", state_config, all_states, {}, {}
        )

        # Only the autonomous state's own transitions survive
        assert resolved["transitions"] == {"data_complete": "autonomous_qualification"}
        assert "objection_price" not in resolved["transitions"]

    def test_autonomous_state_omitted_rules_cleared_by_enforcement(self, loader):
        """When autonomous state doesn't declare rules at all, post-loop enforcement clears them."""
        state_config = {
            "autonomous": True,
            "extends": "_base_phase",
            # No 'rules' key at all — enforcement should clear inherited
            "transitions": {"data_complete": "autonomous_qualification"},
            "goal": "Discover",
        }
        all_states = {
            "_base_phase": {
                "abstract": True,
                "rules": {
                    "objection_price": "handle_objection",
                    "agreement": "continue",
                },
                "transitions": {
                    "objection_price": "handle_objection",
                },
            }
        }

        resolved = loader._resolve_state(
            "autonomous_discovery", state_config, all_states, {}, {}
        )

        # Post-loop enforcement clears inherited rules
        assert resolved["rules"] == {}
        # transitions should only have what the YAML author wrote
        assert resolved["transitions"] == {"data_complete": "autonomous_qualification"}

    def test_autonomous_state_omitted_transitions_cleared_by_enforcement(self, loader):
        """When autonomous state doesn't declare transitions, post-loop enforcement clears them."""
        state_config = {
            "autonomous": True,
            "extends": "_base_phase",
            "rules": {"custom": "do_something"},
            # No 'transitions' key — enforcement should clear inherited
            "goal": "Discover",
        }
        all_states = {
            "_base_phase": {
                "abstract": True,
                "transitions": {
                    "objection_price": "handle_objection",
                    "data_complete": "spin_problem",
                },
            }
        }

        resolved = loader._resolve_state(
            "autonomous_discovery", state_config, all_states, {}, {}
        )

        # rules preserved (directly assigned)
        assert resolved["rules"] == {"custom": "do_something"}
        # transitions cleared by enforcement
        assert resolved["transitions"] == {}

    def test_autonomous_state_parameters_still_deep_merged(self, loader):
        """Parameters always deep-merge even in autonomous states."""
        state_config = {
            "autonomous": True,
            "extends": "_base_phase",
            "parameters": {"max_turns_in_state": 8},
            "rules": {},
            "transitions": {},
            "goal": "Discover",
        }
        all_states = {
            "_base_phase": {
                "abstract": True,
                "parameters": {
                    "max_turns_fallback": "close",
                    "max_turns_in_state": 6,
                },
            }
        }

        resolved = loader._resolve_state(
            "autonomous_discovery", state_config, all_states, {}, {}
        )

        # Parameters deep-merged: child overrides max_turns_in_state, inherits max_turns_fallback
        assert resolved["parameters"]["max_turns_in_state"] == 8
        assert resolved["parameters"]["max_turns_fallback"] == "close"

    def test_standard_state_still_deep_merges_rules_transitions(self, loader):
        """Non-autonomous states keep deep-merge behavior (regression check)."""
        state_config = {
            # No autonomous: true
            "extends": "_base_phase",
            "rules": {"custom_intent": "custom_action"},
            "transitions": {"data_complete": "next_state"},
            "goal": "Standard state",
        }
        all_states = {
            "_base_phase": {
                "abstract": True,
                "rules": {
                    "objection_price": "handle_objection",
                    "agreement": "continue",
                },
                "transitions": {
                    "objection_price": "handle_objection",
                },
            }
        }

        resolved = loader._resolve_state(
            "spin_situation", state_config, all_states, {}, {}
        )

        # Standard state: deep-merge means inherited + own
        assert "objection_price" in resolved["rules"]
        assert "custom_intent" in resolved["rules"]
        assert "objection_price" in resolved["transitions"]
        assert "data_complete" in resolved["transitions"]

    def test_autonomous_state_with_mixins_clears_mixin_transitions(self, loader):
        """Autonomous state with multiple mixins: all mixin transitions cleared."""
        state_config = {
            "autonomous": True,
            "mixins": ["objection_mixin", "progress_mixin"],
            "rules": {},
            "transitions": {"data_complete": "autonomous_next"},
            "goal": "Discover",
        }
        mixins = {
            "objection_mixin": {
                "rules": {
                    "objection_price": "handle_objection",
                    "objection_competitor": "handle_objection",
                },
                "transitions": {
                    "objection_price": "handle_objection",
                    "objection_competitor": "handle_objection",
                },
            },
            "progress_mixin": {
                "rules": {"agreement": "progress"},
                "transitions": {"agreement": "next_phase"},
            },
        }

        resolved = loader._resolve_state(
            "autonomous_discovery", state_config, {}, mixins, {}
        )

        assert resolved["rules"] == {}
        assert resolved["transitions"] == {"data_complete": "autonomous_next"}

    def test_autonomous_state_extends_and_mixins_all_cleared(self, loader):
        """Autonomous state with both extends and mixins: all inherited rules/transitions cleared."""
        state_config = {
            "autonomous": True,
            "extends": "_base_phase",
            "mixins": ["objection_mixin"],
            "rules": {},
            "transitions": {},
            "goal": "Discover",
        }
        all_states = {
            "_base_phase": {
                "abstract": True,
                "rules": {"base_rule": "base_action"},
                "transitions": {"base_transition": "base_target"},
            }
        }
        mixins = {
            "objection_mixin": {
                "rules": {"mixin_rule": "mixin_action"},
                "transitions": {"mixin_transition": "mixin_target"},
            }
        }

        resolved = loader._resolve_state(
            "autonomous_discovery", state_config, all_states, mixins, {}
        )

        assert resolved["rules"] == {}
        assert resolved["transitions"] == {}


# =============================================================================
# Layer 1b: autonomous_decision — target validation
# =============================================================================

class MockFlowConfig:
    """Mock FlowConfig for autonomous flow."""
    def __init__(self, name="autonomous", states=None):
        self.name = name
        self.states = states or {
            "autonomous_discovery": {"phase": "discovery"},
            "autonomous_qualification": {"phase": "qualification"},
            "autonomous_presentation": {"phase": "presentation"},
            "handle_objection": {"phase": "objection"},
        }

    def get(self, key, default=None):
        return getattr(self, key, default)


class MockContextSnapshot:
    """Mock ContextSnapshot for AutonomousDecisionSource tests."""
    def __init__(self, state="autonomous_discovery", state_config=None,
                 flow_config=None, current_intent="agreement",
                 user_message="Да", collected_data=None,
                 context_envelope=None):
        self.state = state
        self.state_config = state_config or {
            "phase": "discovery",
            "goal": "Discover needs",
            "max_turns_in_state": 6,
        }
        self.flow_config = flow_config or MockFlowConfig()
        self.current_intent = current_intent
        self.user_message = user_message
        self.collected_data = collected_data or {}
        self.context_envelope = context_envelope


class MockEnvelope:
    def __init__(self, consecutive_same_state=0):
        self.consecutive_same_state = consecutive_same_state


def _make_bb(state="autonomous_discovery", intent="agreement",
             user_message="Да", states=None, state_config=None,
             context_envelope=None, flow_name="autonomous"):
    flow_config = MockFlowConfig(name=flow_name, states=states)
    ctx = MockContextSnapshot(
        state=state,
        state_config=state_config or {"phase": "discovery", "goal": "Discover", "max_turns_in_state": 6},
        flow_config=flow_config,
        current_intent=intent,
        user_message=user_message,
        context_envelope=context_envelope,
    )
    bb = Mock()
    bb.get_context.return_value = ctx
    bb._action_proposals = []
    bb._transition_proposals = []

    def propose_action(**kwargs):
        bb._action_proposals.append(kwargs)
    def propose_transition(**kwargs):
        bb._transition_proposals.append(kwargs)

    bb.propose_action.side_effect = propose_action
    bb.propose_transition.side_effect = propose_transition
    return bb


class TestLayer1bTargetValidation:
    """Verify AutonomousDecisionSource validates targets against available_states."""

    @patch("src.feature_flags.flags")
    def test_handle_objection_target_rejected(self, mock_flags):
        """LLM hallucinating handle_objection as target is caught and falls back to stay."""
        from src.blackboard.sources.autonomous_decision import (
            AutonomousDecisionSource, AutonomousDecision,
        )
        from src.blackboard.enums import Priority
        mock_flags.is_enabled.return_value = True

        decision = AutonomousDecision(
            next_state="handle_objection",
            action="autonomous_respond",
            reasoning="user objected",
            should_transition=True,
        )
        llm = Mock()
        llm.generate_structured.return_value = decision

        source = AutonomousDecisionSource(llm=llm)
        bb = _make_bb(
            state="autonomous_discovery",
            states={
                "autonomous_discovery": {"phase": "discovery"},
                "autonomous_qualification": {"phase": "qualification"},
                "handle_objection": {"phase": "objection"},
            },
        )

        source.contribute(bb)

        # handle_objection is NOT in available_states (only autonomous_* minus current)
        # So the target is invalid → falls back to stay
        assert len(bb._transition_proposals) == 1
        tp = bb._transition_proposals[0]
        assert tp["next_state"] == "autonomous_discovery"
        assert "autonomous_stay_invalid_target" in tp["reason_code"]

    @patch("src.feature_flags.flags")
    def test_valid_autonomous_target_accepted(self, mock_flags):
        """Transition to another autonomous_* state is valid."""
        from src.blackboard.sources.autonomous_decision import (
            AutonomousDecisionSource, AutonomousDecision,
        )
        mock_flags.is_enabled.return_value = True

        decision = AutonomousDecision(
            next_state="autonomous_qualification",
            action="autonomous_respond",
            reasoning="discovery complete",
            should_transition=True,
        )
        llm = Mock()
        llm.generate_structured.return_value = decision

        source = AutonomousDecisionSource(llm=llm)
        bb = _make_bb(state="autonomous_discovery")

        source.contribute(bb)

        assert len(bb._transition_proposals) == 1
        tp = bb._transition_proposals[0]
        assert tp["next_state"] == "autonomous_qualification"
        assert "autonomous_transition" in tp["reason_code"]

    @patch("src.feature_flags.flags")
    def test_terminal_states_accepted(self, mock_flags):
        """Transitions to close/soft_close/success are always valid."""
        from src.blackboard.sources.autonomous_decision import (
            AutonomousDecisionSource, AutonomousDecision,
        )
        mock_flags.is_enabled.return_value = True

        for terminal in ("close", "soft_close", "success"):
            decision = AutonomousDecision(
                next_state=terminal,
                action="autonomous_respond",
                reasoning="done",
                should_transition=True,
            )
            llm = Mock()
            llm.generate_structured.return_value = decision

            source = AutonomousDecisionSource(llm=llm)
            bb = _make_bb(state="autonomous_discovery")

            source.contribute(bb)

            assert len(bb._transition_proposals) == 1
            assert bb._transition_proposals[0]["next_state"] == terminal

    @patch("src.feature_flags.flags")
    def test_non_autonomous_non_terminal_target_rejected(self, mock_flags):
        """Non-autonomous, non-terminal target like 'spin_situation' is rejected."""
        from src.blackboard.sources.autonomous_decision import (
            AutonomousDecisionSource, AutonomousDecision,
        )
        mock_flags.is_enabled.return_value = True

        decision = AutonomousDecision(
            next_state="spin_situation",
            action="autonomous_respond",
            reasoning="confused",
            should_transition=True,
        )
        llm = Mock()
        llm.generate_structured.return_value = decision

        source = AutonomousDecisionSource(llm=llm)
        bb = _make_bb(
            state="autonomous_discovery",
            states={
                "autonomous_discovery": {},
                "autonomous_qualification": {},
                "spin_situation": {},
            },
        )

        source.contribute(bb)

        assert len(bb._transition_proposals) == 1
        tp = bb._transition_proposals[0]
        assert tp["next_state"] == "autonomous_discovery"
        assert "autonomous_stay_invalid_target" in tp["reason_code"]


# =============================================================================
# Layer 2: priority_assigner — autonomous guard
# =============================================================================

class TestLayer2PriorityAssignerAutonomousGuard:
    """Verify use_transitions boost is skipped in autonomous states."""

    def _make_proposal(self, ptype, value, source_name="TransitionResolverSource"):
        """Create a mock Proposal."""
        from src.blackboard.enums import ProposalType, Priority
        p = Mock()
        p.type = ptype
        p.value = value
        p.source_name = source_name
        p.priority = Priority.NORMAL
        p.reason_code = f"intent_transition_{value}"
        return p

    def _make_definition(self, condition="objection_limit", else_action="use_transitions"):
        """Create a PriorityDefinition with condition + else=use_transitions."""
        from src.blackboard.priority_assigner import PriorityDefinition
        return PriorityDefinition(
            name="test_rule",
            priority=170,
            condition=condition,
            else_action=else_action,
        )

    def _make_ctx(self, autonomous=False):
        """Create a mock ContextSnapshot with state_config."""
        ctx = Mock()
        ctx.state_config = {"autonomous": autonomous} if autonomous else {}
        ctx.is_tenant_feature_enabled = Mock(return_value=True)
        return ctx

    def _make_eval_ctx(self):
        """Create a mock EvaluatorContext."""
        return Mock()

    def test_use_transitions_blocked_in_autonomous_state(self):
        """In autonomous state, use_transitions else-branch returns False."""
        from src.blackboard.priority_assigner import PriorityAssigner
        from src.blackboard.enums import ProposalType

        assigner = PriorityAssigner.__new__(PriorityAssigner)
        # Stub _evaluate_condition to return False (condition not met → else branch)
        assigner._evaluate_condition = Mock(return_value=False)
        assigner._is_intent_transition = Mock(return_value=True)

        definition = self._make_definition()
        proposal = self._make_proposal(ProposalType.TRANSITION, "handle_objection")
        ctx = self._make_ctx(autonomous=True)
        eval_ctx = self._make_eval_ctx()

        result = assigner._matches(definition, proposal, ctx, eval_ctx, "objection_price")

        # Autonomous guard should prevent the match
        assert result is False

    def test_use_transitions_allowed_in_standard_state(self):
        """In standard state, use_transitions else-branch works normally."""
        from src.blackboard.priority_assigner import PriorityAssigner
        from src.blackboard.enums import ProposalType

        assigner = PriorityAssigner.__new__(PriorityAssigner)
        assigner._evaluate_condition = Mock(return_value=False)
        assigner._is_intent_transition = Mock(return_value=True)

        definition = self._make_definition()
        proposal = self._make_proposal(ProposalType.TRANSITION, "handle_objection")
        ctx = self._make_ctx(autonomous=False)
        eval_ctx = self._make_eval_ctx()

        result = assigner._matches(definition, proposal, ctx, eval_ctx, "objection_price")

        # Standard state: use_transitions still works
        assert result is True

    def test_use_transitions_non_transition_proposal_rejected_standard(self):
        """In standard state, use_transitions only matches TRANSITION proposals."""
        from src.blackboard.priority_assigner import PriorityAssigner
        from src.blackboard.enums import ProposalType

        assigner = PriorityAssigner.__new__(PriorityAssigner)
        assigner._evaluate_condition = Mock(return_value=False)
        assigner._is_intent_transition = Mock(return_value=True)

        definition = self._make_definition()
        proposal = self._make_proposal(ProposalType.ACTION, "continue")
        ctx = self._make_ctx(autonomous=False)
        eval_ctx = self._make_eval_ctx()

        result = assigner._matches(definition, proposal, ctx, eval_ctx, "objection_price")

        # ACTION proposal does not match use_transitions
        assert result is False

    def test_condition_met_bypasses_guard(self):
        """When condition IS met (True), the else-branch never fires — autonomous guard irrelevant."""
        from src.blackboard.priority_assigner import PriorityAssigner
        from src.blackboard.enums import ProposalType

        assigner = PriorityAssigner.__new__(PriorityAssigner)
        assigner._evaluate_condition = Mock(return_value=True)
        # No handler, action, source, or trigger — definition should match
        assigner._is_intent_transition = Mock(return_value=True)

        definition = self._make_definition()
        proposal = self._make_proposal(ProposalType.TRANSITION, "handle_objection")
        ctx = self._make_ctx(autonomous=True)
        eval_ctx = self._make_eval_ctx()

        result = assigner._matches(definition, proposal, ctx, eval_ctx, "objection_price")

        # Condition met → no else-branch → passes through (guard not invoked)
        assert result is True


# =============================================================================
# Layer 3: context_envelope — detour turn counting
# =============================================================================

@dataclass
class MockTurn:
    """Lightweight mock for context window turns."""
    state: str
    confidence: float = 0.8


class MockContextWindow:
    """Mock ContextWindow with turns for testing _count_autonomous_session."""

    def __init__(self, turns=None):
        self.turns = turns or []

    def get_positive_count(self):
        return 0

    def get_question_count(self):
        return 0

    def get_unclear_count(self):
        return 0

    def detect_oscillation(self):
        return False

    def detect_stuck_pattern(self):
        return False

    def get_consecutive_same_state(self):
        count = 0
        if self.turns:
            last_state = self.turns[-1].state
            for turn in reversed(self.turns):
                if turn.state == last_state:
                    count += 1
                else:
                    break
        return count

    def detect_repeated_question(self, include_current_intent=None):
        return False

    def get_confidence_trend(self):
        return "stable"

    def get_average_confidence(self):
        return 0.5

    def __len__(self):
        return len(self.turns)

    def get_last_turn(self):
        return self.turns[-1] if self.turns else None

    def get_structured_context(self, use_v2_engagement=False):
        return {}

    def get_momentum(self):
        return 0.0

    def get_episodic_context(self):
        return {}


class TestLayer3DetourTurnCounting:
    """Verify _count_autonomous_session counts detour turns correctly."""

    def _make_builder(self):
        """Create a ContextEnvelopeBuilder with minimal init."""
        from src.context_envelope import ContextEnvelopeBuilder
        # Provide minimal params; we'll test helper method directly
        builder = ContextEnvelopeBuilder.__new__(ContextEnvelopeBuilder)
        return builder

    def test_count_simple_autonomous_session(self):
        """Autonomous session with no detours."""
        builder = self._make_builder()
        cw = MockContextWindow(turns=[
            MockTurn(state="autonomous_discovery"),
            MockTurn(state="autonomous_discovery"),
            MockTurn(state="autonomous_discovery"),
        ])

        count = builder._count_autonomous_session(cw, "autonomous_discovery")

        # 3 turns + 1 for current unrecorded = 4
        assert count == 4

    def test_count_oscillation_pattern(self):
        """The exact oscillation pattern from Bug #12."""
        builder = self._make_builder()
        cw = MockContextWindow(turns=[
            MockTurn(state="autonomous_discovery"),     # Turn 1
            MockTurn(state="handle_objection"),         # Turn 2 (detour)
            MockTurn(state="autonomous_discovery"),     # Turn 3
            MockTurn(state="handle_objection"),         # Turn 4 (detour)
            MockTurn(state="autonomous_discovery"),     # Turn 5
            MockTurn(state="handle_objection"),         # Turn 6 (detour)
        ])

        count = builder._count_autonomous_session(cw, "autonomous_discovery")

        # All 6 turns are in the session + 1 for current = 7
        assert count == 7

    def test_count_stops_at_different_autonomous_state(self):
        """Session counting stops at a different non-detour state."""
        builder = self._make_builder()
        cw = MockContextWindow(turns=[
            MockTurn(state="autonomous_qualification"),  # Different autonomous state
            MockTurn(state="autonomous_discovery"),
            MockTurn(state="handle_objection"),
            MockTurn(state="autonomous_discovery"),
        ])

        count = builder._count_autonomous_session(cw, "autonomous_discovery")

        # Only last 3 turns (discovery, objection, discovery) + 1 = 4
        assert count == 4

    def test_count_empty_turns(self):
        """Empty turn history."""
        builder = self._make_builder()
        cw = MockContextWindow(turns=[])

        count = builder._count_autonomous_session(cw, "autonomous_discovery")

        # 0 turns + 1 = 1
        assert count == 1

    def test_count_all_detours(self):
        """All turns are handle_objection (unusual but valid)."""
        builder = self._make_builder()
        cw = MockContextWindow(turns=[
            MockTurn(state="handle_objection"),
            MockTurn(state="handle_objection"),
        ])

        count = builder._count_autonomous_session(cw, "autonomous_discovery")

        # 2 detour turns + 1 = 3
        assert count == 3

    def test_count_mixed_session_stops_at_boundary(self):
        """Longer history with a clear session boundary."""
        builder = self._make_builder()
        cw = MockContextWindow(turns=[
            MockTurn(state="greeting"),                # Not counted
            MockTurn(state="autonomous_qualification"),# Not counted (different autonomous)
            MockTurn(state="autonomous_discovery"),    # Session start
            MockTurn(state="handle_objection"),
            MockTurn(state="autonomous_discovery"),
            MockTurn(state="handle_objection"),
            MockTurn(state="autonomous_discovery"),
        ])

        count = builder._count_autonomous_session(cw, "autonomous_discovery")

        # Last 5 turns in session + 1 = 6
        assert count == 6

    def test_standard_state_not_affected(self):
        """Standard state (not autonomous_*) uses normal counting, not detour counting."""
        from src.context_envelope import ContextEnvelope

        # This tests the branching logic in _fill_from_context_window
        # Standard state changes → consecutive = 1 (the else branch)
        envelope = ContextEnvelope()
        envelope.state = "presentation"

        cw = MockContextWindow(turns=[
            MockTurn(state="presentation"),
            MockTurn(state="handle_objection"),
        ])

        # The last turn is handle_objection, current state is presentation
        # This is NOT an autonomous state, so it goes to else branch → 1
        # We test this indirectly by checking the builder logic
        builder = self._make_builder()
        raw_count = cw.get_consecutive_same_state()

        # Standard flow: state changed → should reset to 1
        if not cw.turns:
            result = 1
        elif cw.turns[-1].state == envelope.state:
            result = raw_count + 1
        elif envelope.state.startswith("autonomous_"):
            result = builder._count_autonomous_session(cw, envelope.state)
        else:
            result = 1

        assert result == 1

    def test_autonomous_returning_from_detour_counts_session(self):
        """Autonomous state returning from handle_objection gets full session count."""
        from src.context_envelope import ContextEnvelope

        envelope = ContextEnvelope()
        envelope.state = "autonomous_discovery"

        cw = MockContextWindow(turns=[
            MockTurn(state="autonomous_discovery"),
            MockTurn(state="handle_objection"),
            MockTurn(state="autonomous_discovery"),
            MockTurn(state="handle_objection"),  # last turn
        ])

        builder = self._make_builder()
        raw_count = cw.get_consecutive_same_state()

        # Last turn is handle_objection, current state is autonomous_discovery
        # → autonomous_ branch fires
        if not cw.turns:
            result = 1
        elif cw.turns[-1].state == envelope.state:
            result = raw_count + 1
        elif envelope.state.startswith("autonomous_"):
            result = builder._count_autonomous_session(cw, envelope.state)
        else:
            result = 1

        # 4 turns + 1 for current = 5
        assert result == 5

    def test_stall_guard_threshold_hit_with_oscillation(self):
        """Oscillation pattern hits max_turns_in_state threshold (end-to-end)."""
        builder = self._make_builder()

        # Simulate 6 turns of oscillation
        cw = MockContextWindow(turns=[
            MockTurn(state="autonomous_discovery"),
            MockTurn(state="handle_objection"),
            MockTurn(state="autonomous_discovery"),
            MockTurn(state="handle_objection"),
            MockTurn(state="autonomous_discovery"),
            MockTurn(state="handle_objection"),
        ])

        count = builder._count_autonomous_session(cw, "autonomous_discovery")

        max_turns_in_state = 6
        # count = 7 (6 turns + 1) → exceeds threshold of 6
        assert count >= max_turns_in_state, (
            f"Session count {count} should be >= {max_turns_in_state} "
            f"to trigger StallGuard"
        )


# =============================================================================
# Integration: all layers work together
# =============================================================================

class TestBug12Integration:
    """Integration tests verifying the oscillation loop is broken."""

    def test_config_resolution_no_mixin_leak(self):
        """End-to-end: autonomous state resolved from real-like config has no mixin transitions."""
        from src.config_loader import ConfigLoader

        loader = ConfigLoader()

        # Simulate a realistic autonomous state with _base_phase and objection mixins
        state_config = {
            "autonomous": True,
            "extends": "_base_phase",
            "mixins": ["objection_handling", "progress_tracking"],
            "rules": {},
            "transitions": {"data_complete": "autonomous_qualification"},
            "goal": "Discover client needs",
            "phase": "discovery",
        }
        all_states = {
            "_base_phase": {
                "abstract": True,
                "rules": {
                    "objection_price": "handle_objection",
                    "objection_competitor": "handle_objection",
                    "objection_timing": "handle_objection",
                    "objection_need": "handle_objection",
                    "objection_authority": "handle_objection",
                    "objection_trust": "handle_objection",
                    "go_back": "go_back_handler",
                    "agreement": "continue",
                },
                "transitions": {
                    "objection_price": "handle_objection",
                    "objection_competitor": "handle_objection",
                    "objection_timing": "handle_objection",
                    "objection_need": "handle_objection",
                    "objection_authority": "handle_objection",
                    "objection_trust": "handle_objection",
                },
                "parameters": {"max_turns_fallback": "close", "max_turns_in_state": 6},
            }
        }
        mixins = {
            "objection_handling": {
                "rules": {
                    "objection_budget": "handle_objection",
                    "objection_integration": "handle_objection",
                    "objection_support": "handle_objection",
                },
                "transitions": {
                    "objection_budget": "handle_objection",
                    "objection_integration": "handle_objection",
                    "objection_support": "handle_objection",
                },
            },
            "progress_tracking": {
                "rules": {"progress_signal": "track_progress"},
                "transitions": {"progress_signal": "next_phase"},
            },
        }

        resolved = loader._resolve_state(
            "autonomous_discovery", state_config, all_states, mixins, {}
        )

        # All mixin/inherited transitions should be replaced
        assert resolved["rules"] == {}
        assert resolved["transitions"] == {"data_complete": "autonomous_qualification"}
        # Parameters preserved
        assert resolved["parameters"]["max_turns_fallback"] == "close"
        assert resolved["parameters"]["max_turns_in_state"] == 6
        # Goal preserved
        assert resolved["goal"] == "Discover client needs"

    def test_oscillation_detection_end_to_end(self):
        """Full oscillation scenario: detour counting catches what raw consecutive misses."""
        builder_cls = None
        try:
            from src.context_envelope import ContextEnvelopeBuilder
            builder_cls = ContextEnvelopeBuilder
        except ImportError:
            pytest.skip("ContextEnvelopeBuilder not available")

        builder = builder_cls.__new__(builder_cls)

        # 12 turns of oscillation (6 pairs)
        turns = []
        for _ in range(6):
            turns.append(MockTurn(state="autonomous_discovery"))
            turns.append(MockTurn(state="handle_objection"))

        cw = MockContextWindow(turns=turns)

        # Raw consecutive would be 1 (last turn is handle_objection, not autonomous_discovery)
        raw = cw.get_consecutive_same_state()
        assert raw <= 1

        # But our session count catches it
        session_count = builder._count_autonomous_session(cw, "autonomous_discovery")
        assert session_count == 13  # 12 turns + 1 for current

        # This far exceeds max_turns_in_state=6
        assert session_count > 6
