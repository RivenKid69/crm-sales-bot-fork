# tests/test_blackboard_conflict_resolver.py

"""
Tests for Blackboard Stage 4: ConflictResolver.

These tests verify:
1. ResolutionTrace dataclass - creation, to_dict
2. ConflictResolver - conflict resolution between proposals
3. Priority-based resolution
4. Combinable flag handling (blocking vs merging)
5. Fallback transition support
"""

import pytest

from src.blackboard.models import Proposal, ResolvedDecision
from src.blackboard.enums import Priority, ProposalType
from src.blackboard.conflict_resolver import ResolutionTrace, ConflictResolver

# =============================================================================
# Test ResolutionTrace Dataclass
# =============================================================================

class TestResolutionTrace:
    """Test ResolutionTrace dataclass functionality."""

    def test_resolution_trace_creation_default(self):
        """Test default ResolutionTrace creation."""
        trace = ResolutionTrace()

        assert trace.action_proposals == []
        assert trace.transition_proposals == []
        assert trace.action_ranking == []
        assert trace.transition_ranking == []
        assert trace.winning_action is None
        assert trace.winning_transition is None
        assert trace.merge_decision == ""
        assert trace.blocking_reason is None

    def test_resolution_trace_with_proposals(self):
        """Test ResolutionTrace with proposals."""
        action = Proposal(
            type=ProposalType.ACTION,
            value="answer",
            priority=Priority.HIGH,
            source_name="Source1",
            reason_code="TEST",
        )
        transition = Proposal(
            type=ProposalType.TRANSITION,
            value="next_state",
            priority=Priority.NORMAL,
            source_name="Source2",
            reason_code="TEST",
        )

        trace = ResolutionTrace(
            action_proposals=[action],
            transition_proposals=[transition],
            action_ranking=[("answer", Priority.HIGH, "Source1")],
            transition_ranking=[("next_state", Priority.NORMAL, "Source2")],
            winning_action=action,
            winning_transition=transition,
            merge_decision="MERGED",
        )

        assert len(trace.action_proposals) == 1
        assert len(trace.transition_proposals) == 1
        assert trace.winning_action == action
        assert trace.winning_transition == transition
        assert trace.merge_decision == "MERGED"

    def test_resolution_trace_to_dict(self):
        """Test to_dict method."""
        action = Proposal(
            type=ProposalType.ACTION,
            value="answer",
            priority=Priority.HIGH,
            source_name="Source1",
            reason_code="TEST",
        )

        trace = ResolutionTrace(
            action_proposals=[action],
            transition_proposals=[],
            action_ranking=[("answer", Priority.HIGH, "Source1")],
            transition_ranking=[],
            winning_action=action,
            winning_transition=None,
            merge_decision="ACTION_ONLY",
            blocking_reason=None,
        )

        d = trace.to_dict()

        assert d["action_proposals_count"] == 1
        assert d["transition_proposals_count"] == 0
        assert d["action_ranking"] == [("answer", Priority.HIGH, "Source1")]
        assert d["transition_ranking"] == []
        assert "answer" in d["winning_action"]  # str representation
        assert d["winning_transition"] is None
        assert d["merge_decision"] == "ACTION_ONLY"
        assert d["blocking_reason"] is None

    def test_resolution_trace_to_dict_with_blocking(self):
        """Test to_dict with blocking reason."""
        trace = ResolutionTrace(
            blocking_reason="Action 'reject' blocks all transitions"
        )

        d = trace.to_dict()
        assert d["blocking_reason"] == "Action 'reject' blocks all transitions"

# =============================================================================
# Test ConflictResolver Initialization
# =============================================================================

class TestConflictResolverInit:
    """Test ConflictResolver initialization."""

    def test_init_default(self):
        """Test default initialization."""
        resolver = ConflictResolver()
        assert resolver._default_action == "continue"

    def test_init_custom_default_action(self):
        """Test initialization with custom default action."""
        resolver = ConflictResolver(default_action="wait")
        assert resolver._default_action == "wait"

# =============================================================================
# Test ConflictResolver.resolve() - Basic Resolution
# =============================================================================

class TestConflictResolverResolve:
    """Test ConflictResolver.resolve() method."""

    def test_resolve_empty_proposals(self):
        """Test resolution with no proposals."""
        resolver = ConflictResolver()

        decision = resolver.resolve(
            proposals=[],
            current_state="spin_situation",
        )

        assert decision.action == "continue"  # Default action
        assert decision.next_state == "spin_situation"  # Stays in current state
        assert decision.reason_codes == []
        assert decision.rejected_proposals == []
        assert decision.resolution_trace["merge_decision"] == "NO_PROPOSALS"

    def test_resolve_single_action(self):
        """Test resolution with single action proposal."""
        resolver = ConflictResolver()

        action = Proposal(
            type=ProposalType.ACTION,
            value="answer_question",
            priority=Priority.NORMAL,
            source_name="IntentHandler",
            reason_code="INTENT_QUESTION",
        )

        decision = resolver.resolve(
            proposals=[action],
            current_state="spin_situation",
        )

        assert decision.action == "answer_question"
        assert decision.next_state == "spin_situation"  # No transition
        assert decision.reason_codes == ["INTENT_QUESTION"]
        assert decision.rejected_proposals == []
        assert decision.resolution_trace["merge_decision"] == "ACTION_ONLY"

    def test_resolve_single_transition(self):
        """Test resolution with single transition proposal."""
        resolver = ConflictResolver()

        transition = Proposal(
            type=ProposalType.TRANSITION,
            value="spin_problem",
            priority=Priority.NORMAL,
            source_name="DataCollector",
            reason_code="DATA_COMPLETE",
        )

        decision = resolver.resolve(
            proposals=[transition],
            current_state="spin_situation",
        )

        assert decision.action == "continue"  # Default action
        assert decision.next_state == "spin_problem"
        assert decision.reason_codes == ["DATA_COMPLETE"]
        assert decision.rejected_proposals == []
        assert decision.resolution_trace["merge_decision"] == "TRANSITION_ONLY"

# =============================================================================
# Test ConflictResolver - Combinable Actions (MERGED)
# =============================================================================

class TestConflictResolverCombinable:
    """Test combinable action handling."""

    def test_resolve_combinable_action_with_transition_merged(self):
        """Test that combinable action merges with transition."""
        resolver = ConflictResolver()

        action = Proposal(
            type=ProposalType.ACTION,
            value="answer_with_pricing",
            priority=Priority.HIGH,
            source_name="PriceHandler",
            reason_code="PRICE_QUESTION",
            combinable=True,
        )

        transition = Proposal(
            type=ProposalType.TRANSITION,
            value="spin_problem",
            priority=Priority.NORMAL,
            source_name="DataCollector",
            reason_code="DATA_COMPLETE",
        )

        decision = resolver.resolve(
            proposals=[action, transition],
            current_state="spin_situation",
        )

        # Both action and transition should be applied
        assert decision.action == "answer_with_pricing"
        assert decision.next_state == "spin_problem"
        assert "PRICE_QUESTION" in decision.reason_codes
        assert "DATA_COMPLETE" in decision.reason_codes
        assert decision.rejected_proposals == []
        assert decision.resolution_trace["merge_decision"] == "MERGED"

    def test_resolve_default_combinable_true(self):
        """Test that default combinable=True allows merging."""
        resolver = ConflictResolver()

        # Action without explicit combinable (defaults to True)
        action = Proposal(
            type=ProposalType.ACTION,
            value="handle_objection",
            priority=Priority.HIGH,
            source_name="ObjectionHandler",
            reason_code="OBJECTION",
        )

        transition = Proposal(
            type=ProposalType.TRANSITION,
            value="presentation",
            priority=Priority.NORMAL,
            source_name="FlowManager",
            reason_code="FLOW_NEXT",
        )

        decision = resolver.resolve(
            proposals=[action, transition],
            current_state="spin_need_payoff",
        )

        assert decision.action == "handle_objection"
        assert decision.next_state == "presentation"
        assert decision.resolution_trace["merge_decision"] == "MERGED"

# =============================================================================
# Test ConflictResolver - Blocking Actions
# =============================================================================

class TestConflictResolverBlocking:
    """Test blocking action handling."""

    def test_resolve_blocking_action_blocks_transitions(self):
        """Test that combinable=False blocks all transitions."""
        resolver = ConflictResolver()

        action = Proposal(
            type=ProposalType.ACTION,
            value="reject",
            priority=Priority.CRITICAL,
            source_name="ObjectionGuard",
            reason_code="OBJECTION_LIMIT",
            combinable=False,  # Blocking action!
        )

        transition = Proposal(
            type=ProposalType.TRANSITION,
            value="spin_problem",
            priority=Priority.NORMAL,
            source_name="DataCollector",
            reason_code="DATA_COMPLETE",
        )

        decision = resolver.resolve(
            proposals=[action, transition],
            current_state="spin_situation",
        )

        # Action should be applied but transition should be BLOCKED
        assert decision.action == "reject"
        assert decision.next_state == "spin_situation"  # No transition!
        assert decision.reason_codes == ["OBJECTION_LIMIT"]  # Only action reason
        assert len(decision.rejected_proposals) == 1
        assert decision.rejected_proposals[0] == transition
        assert decision.resolution_trace["merge_decision"] == "BLOCKED"
        assert decision.resolution_trace["blocking_reason"] is not None

    def test_resolve_blocking_action_blocks_multiple_transitions(self):
        """Test that blocking action blocks all transitions."""
        resolver = ConflictResolver()

        action = Proposal(
            type=ProposalType.ACTION,
            value="escalate",
            priority=Priority.CRITICAL,
            source_name="EscalationHandler",
            reason_code="ESCALATION",
            combinable=False,
        )

        transition1 = Proposal(
            type=ProposalType.TRANSITION,
            value="state1",
            priority=Priority.HIGH,
            source_name="Source1",
            reason_code="REASON1",
        )

        transition2 = Proposal(
            type=ProposalType.TRANSITION,
            value="state2",
            priority=Priority.NORMAL,
            source_name="Source2",
            reason_code="REASON2",
        )

        decision = resolver.resolve(
            proposals=[action, transition1, transition2],
            current_state="current",
        )

        assert decision.next_state == "current"
        assert len(decision.rejected_proposals) == 2  # Both transitions rejected
        assert decision.resolution_trace["merge_decision"] == "BLOCKED"

# =============================================================================
# Test ConflictResolver - Priority Resolution
# =============================================================================

class TestConflictResolverPriority:
    """Test priority-based resolution."""

    def test_resolve_actions_by_priority(self):
        """Test that highest priority action wins."""
        resolver = ConflictResolver()

        low_action = Proposal(
            type=ProposalType.ACTION,
            value="continue",
            priority=Priority.LOW,
            source_name="Default",
            reason_code="DEFAULT",
        )

        high_action = Proposal(
            type=ProposalType.ACTION,
            value="handle_objection",
            priority=Priority.HIGH,
            source_name="ObjectionHandler",
            reason_code="OBJECTION",
        )

        normal_action = Proposal(
            type=ProposalType.ACTION,
            value="collect_data",
            priority=Priority.NORMAL,
            source_name="DataCollector",
            reason_code="DATA",
        )

        decision = resolver.resolve(
            proposals=[low_action, high_action, normal_action],
            current_state="current",
        )

        assert decision.action == "handle_objection"
        assert decision.reason_codes == ["OBJECTION"]
        # Other actions should be rejected
        assert len(decision.rejected_proposals) == 2

    def test_resolve_transitions_by_priority(self):
        """Test that highest priority transition wins."""
        resolver = ConflictResolver()

        low_transition = Proposal(
            type=ProposalType.TRANSITION,
            value="fallback_state",
            priority=Priority.LOW,
            source_name="Default",
            reason_code="FALLBACK",
        )

        high_transition = Proposal(
            type=ProposalType.TRANSITION,
            value="important_state",
            priority=Priority.HIGH,
            source_name="Important",
            reason_code="IMPORTANT",
        )

        decision = resolver.resolve(
            proposals=[low_transition, high_transition],
            current_state="current",
        )

        assert decision.next_state == "important_state"
        assert decision.reason_codes == ["IMPORTANT"]
        assert len(decision.rejected_proposals) == 1

    def test_resolve_critical_action_wins(self):
        """Test that CRITICAL priority always wins."""
        resolver = ConflictResolver()

        critical = Proposal(
            type=ProposalType.ACTION,
            value="reject",
            priority=Priority.CRITICAL,
            source_name="Guard",
            reason_code="CRITICAL_REASON",
        )

        high = Proposal(
            type=ProposalType.ACTION,
            value="answer",
            priority=Priority.HIGH,
            source_name="Handler",
            reason_code="HIGH_REASON",
        )

        decision = resolver.resolve(
            proposals=[high, critical],  # Critical comes second
            current_state="current",
        )

        assert decision.action == "reject"
        assert decision.reason_codes == ["CRITICAL_REASON"]

# =============================================================================
# Test ConflictResolver - Data Updates and Flags
# =============================================================================

class TestConflictResolverDataAndFlags:
    """Test data updates and flags handling."""

    def test_resolve_with_data_updates(self):
        """Test that data_updates are included in decision."""
        resolver = ConflictResolver()

        action = Proposal(
            type=ProposalType.ACTION,
            value="collect",
            priority=Priority.NORMAL,
            source_name="Collector",
            reason_code="COLLECT",
        )

        decision = resolver.resolve(
            proposals=[action],
            current_state="state",
            data_updates={"company_size": "medium", "industry": "IT"},
        )

        assert decision.data_updates == {"company_size": "medium", "industry": "IT"}

    def test_resolve_with_flags(self):
        """Test that flags_to_set are included in decision."""
        resolver = ConflictResolver()

        action = Proposal(
            type=ProposalType.ACTION,
            value="handle",
            priority=Priority.NORMAL,
            source_name="Handler",
            reason_code="HANDLE",
        )

        decision = resolver.resolve(
            proposals=[action],
            current_state="state",
            flags_to_set={"_objection_handled": True, "_price_discussed": True},
        )

        assert decision.flags_to_set == {"_objection_handled": True, "_price_discussed": True}

    def test_resolve_with_none_data_and_flags(self):
        """Test that None data_updates and flags_to_set become empty dicts."""
        resolver = ConflictResolver()

        decision = resolver.resolve(
            proposals=[],
            current_state="state",
            data_updates=None,
            flags_to_set=None,
        )

        assert decision.data_updates == {}
        assert decision.flags_to_set == {}

# =============================================================================
# Test ConflictResolver.resolve_with_fallback()
# =============================================================================

class TestConflictResolverFallback:
    """Test resolve_with_fallback method."""

    def test_fallback_not_applied_when_transition_exists(self):
        """Test that fallback is not applied when normal transition exists."""
        resolver = ConflictResolver()

        transition = Proposal(
            type=ProposalType.TRANSITION,
            value="normal_next",
            priority=Priority.NORMAL,
            source_name="Normal",
            reason_code="NORMAL",
        )

        decision = resolver.resolve_with_fallback(
            proposals=[transition],
            current_state="current",
            fallback_transition="fallback_state",
        )

        assert decision.next_state == "normal_next"
        assert "fallback_any_transition" not in decision.reason_codes

    def test_fallback_applied_when_no_transition(self):
        """Test that fallback is applied when no transition proposed."""
        resolver = ConflictResolver()

        action = Proposal(
            type=ProposalType.ACTION,
            value="answer",
            priority=Priority.NORMAL,
            source_name="Handler",
            reason_code="ANSWER",
            combinable=True,
        )

        decision = resolver.resolve_with_fallback(
            proposals=[action],
            current_state="current",
            fallback_transition="fallback_state",
        )

        assert decision.next_state == "fallback_state"
        assert "fallback_any_transition" in decision.reason_codes
        assert decision.resolution_trace.get("fallback_applied") is True

    def test_fallback_not_applied_when_action_blocks(self):
        """Test that fallback is not applied when action is blocking."""
        resolver = ConflictResolver()

        action = Proposal(
            type=ProposalType.ACTION,
            value="reject",
            priority=Priority.CRITICAL,
            source_name="Guard",
            reason_code="REJECT",
            combinable=False,  # Blocking action
        )

        decision = resolver.resolve_with_fallback(
            proposals=[action],
            current_state="current",
            fallback_transition="fallback_state",
        )

        # Fallback should NOT be applied because action is blocking
        assert decision.next_state == "current"
        assert "fallback_any_transition" not in decision.reason_codes

    def test_fallback_not_applied_when_none(self):
        """Test that None fallback is handled gracefully."""
        resolver = ConflictResolver()

        decision = resolver.resolve_with_fallback(
            proposals=[],
            current_state="current",
            fallback_transition=None,
        )

        assert decision.next_state == "current"

    def test_fallback_with_data_and_flags(self):
        """Test fallback with data_updates and flags_to_set."""
        resolver = ConflictResolver()

        action = Proposal(
            type=ProposalType.ACTION,
            value="process",
            priority=Priority.NORMAL,
            source_name="Processor",
            reason_code="PROCESS",
            combinable=True,
        )

        decision = resolver.resolve_with_fallback(
            proposals=[action],
            current_state="current",
            fallback_transition="next",
            data_updates={"key": "value"},
            flags_to_set={"flag": True},
        )

        assert decision.next_state == "next"
        assert decision.data_updates == {"key": "value"}
        assert decision.flags_to_set == {"flag": True}

# =============================================================================
# Test ConflictResolver - Complex Scenarios
# =============================================================================

class TestConflictResolverComplexScenarios:
    """Test complex resolution scenarios."""

    def test_scenario_price_question_with_phase_transition(self):
        """
        Scenario: Price question occurs while data collection is complete.
        Expected: Answer price question AND transition to next phase.
        """
        resolver = ConflictResolver()

        price_action = Proposal(
            type=ProposalType.ACTION,
            value="answer_with_pricing",
            priority=Priority.HIGH,
            source_name="PriceQuestionHandler",
            reason_code="PRICE_QUESTION",
            combinable=True,  # Critical: must be combinable
        )

        phase_transition = Proposal(
            type=ProposalType.TRANSITION,
            value="spin_problem",
            priority=Priority.NORMAL,
            source_name="DataCompletionChecker",
            reason_code="DATA_COMPLETE",
        )

        decision = resolver.resolve(
            proposals=[price_action, phase_transition],
            current_state="spin_situation",
        )

        # Both should be applied
        assert decision.action == "answer_with_pricing"
        assert decision.next_state == "spin_problem"
        assert len(decision.reason_codes) == 2

    def test_scenario_objection_limit_reached(self):
        """
        Scenario: Objection limit reached - must reject and NOT transition.
        Expected: Reject action blocks transition.
        """
        resolver = ConflictResolver()

        reject_action = Proposal(
            type=ProposalType.ACTION,
            value="reject_lead",
            priority=Priority.CRITICAL,
            source_name="ObjectionGuard",
            reason_code="OBJECTION_LIMIT_EXCEEDED",
            combinable=False,  # Critical: must block transitions
        )

        normal_transition = Proposal(
            type=ProposalType.TRANSITION,
            value="presentation",
            priority=Priority.NORMAL,
            source_name="FlowManager",
            reason_code="FLOW_NEXT",
        )

        decision = resolver.resolve(
            proposals=[reject_action, normal_transition],
            current_state="spin_need_payoff",
        )

        # Only reject action should be applied
        assert decision.action == "reject_lead"
        assert decision.next_state == "spin_need_payoff"  # No transition
        assert decision.reason_codes == ["OBJECTION_LIMIT_EXCEEDED"]
        assert len(decision.rejected_proposals) == 1

    def test_scenario_multiple_actions_different_priorities(self):
        """
        Scenario: Multiple actions with different priorities compete.
        Expected: Highest priority wins, others rejected.
        """
        resolver = ConflictResolver()

        fallback = Proposal(
            type=ProposalType.ACTION,
            value="continue",
            priority=Priority.LOW,
            source_name="Default",
            reason_code="DEFAULT",
        )

        intent_action = Proposal(
            type=ProposalType.ACTION,
            value="answer_features",
            priority=Priority.NORMAL,
            source_name="IntentHandler",
            reason_code="INTENT_FEATURES",
        )

        objection_action = Proposal(
            type=ProposalType.ACTION,
            value="handle_objection",
            priority=Priority.HIGH,
            source_name="ObjectionHandler",
            reason_code="OBJECTION_DETECTED",
        )

        decision = resolver.resolve(
            proposals=[fallback, intent_action, objection_action],
            current_state="presentation",
        )

        assert decision.action == "handle_objection"
        assert len(decision.rejected_proposals) == 2

    def test_scenario_only_low_priority_actions(self):
        """
        Scenario: Only low priority actions available.
        Expected: Lowest priority still wins if it's the only one.
        """
        resolver = ConflictResolver()

        action = Proposal(
            type=ProposalType.ACTION,
            value="continue",
            priority=Priority.LOW,
            source_name="Default",
            reason_code="DEFAULT",
        )

        decision = resolver.resolve(
            proposals=[action],
            current_state="state",
        )

        assert decision.action == "continue"
        assert decision.rejected_proposals == []

# =============================================================================
# Test Resolution Trace Details
# =============================================================================

class TestResolutionTraceDetails:
    """Test that resolution trace contains expected details."""

    def test_trace_contains_rankings(self):
        """Test that trace contains action and transition rankings."""
        resolver = ConflictResolver()

        action1 = Proposal(
            type=ProposalType.ACTION,
            value="action1",
            priority=Priority.HIGH,
            source_name="Source1",
            reason_code="CODE1",
        )

        action2 = Proposal(
            type=ProposalType.ACTION,
            value="action2",
            priority=Priority.LOW,
            source_name="Source2",
            reason_code="CODE2",
        )

        decision = resolver.resolve(
            proposals=[action2, action1],  # Reverse order
            current_state="state",
        )

        trace = decision.resolution_trace

        # Rankings should be sorted by priority
        assert len(trace["action_ranking"]) == 2
        # HIGH priority should come first
        assert trace["action_ranking"][0][0] == "action1"
        assert trace["action_ranking"][1][0] == "action2"

    def test_trace_contains_counts(self):
        """Test that trace contains proposal counts."""
        resolver = ConflictResolver()

        proposals = [
            Proposal(type=ProposalType.ACTION, value="a1", priority=Priority.NORMAL,
                     source_name="S1", reason_code="C1"),
            Proposal(type=ProposalType.ACTION, value="a2", priority=Priority.LOW,
                     source_name="S2", reason_code="C2"),
            Proposal(type=ProposalType.TRANSITION, value="t1", priority=Priority.NORMAL,
                     source_name="S3", reason_code="C3"),
        ]

        decision = resolver.resolve(proposals, current_state="state")

        trace = decision.resolution_trace
        assert trace["action_proposals_count"] == 2
        assert trace["transition_proposals_count"] == 1

# =============================================================================
# Test Package Imports
# =============================================================================

class TestConflictResolverImports:
    """Test that ConflictResolver can be imported from blackboard package."""

    def test_import_resolution_trace_from_package(self):
        """Verify ResolutionTrace can be imported from src.blackboard."""
        from src.blackboard import ResolutionTrace

        assert ResolutionTrace is not None

    def test_import_conflict_resolver_from_package(self):
        """Verify ConflictResolver can be imported from src.blackboard."""
        from src.blackboard import ConflictResolver

        assert ConflictResolver is not None

    def test_all_exports_in_dunder_all(self):
        """Verify __all__ contains resolver exports."""
        import src.blackboard as bb

        assert "ResolutionTrace" in bb.__all__
        assert "ConflictResolver" in bb.__all__

# =============================================================================
# Criteria Verification (from Architectural Plan Stage 4)
# =============================================================================

class TestStage4ResolverCriteriaVerification:
    """
    Verification tests from the plan's CRITERION OF COMPLETION for Stage 4.
    """

    def test_criterion_resolver_import(self):
        """
        Plan criterion: from src.blackboard import ConflictResolver, ResolutionTrace
        """
        from src.blackboard import ConflictResolver, ResolutionTrace

        assert ConflictResolver is not None
        assert ResolutionTrace is not None

    def test_criterion_resolver_returns_resolved_decision(self):
        """
        Plan criterion: Resolver returns ResolvedDecision object.
        """
        from src.blackboard import ConflictResolver, Proposal, Priority, ProposalType, ResolvedDecision

        resolver = ConflictResolver()
        proposal = Proposal(
            type=ProposalType.ACTION,
            value="test",
            priority=Priority.NORMAL,
            source_name="TestSource",
            reason_code="TEST",
        )

        decision = resolver.resolve([proposal], current_state="state")

        assert isinstance(decision, ResolvedDecision)

    def test_criterion_combinable_true_merges(self):
        """
        Plan criterion: combinable=True allows action+transition merge.
        """
        from src.blackboard import ConflictResolver, Proposal, Priority, ProposalType

        resolver = ConflictResolver()

        action = Proposal(
            type=ProposalType.ACTION,
            value="answer",
            priority=Priority.HIGH,
            source_name="S1",
            reason_code="C1",
            combinable=True,
        )

        transition = Proposal(
            type=ProposalType.TRANSITION,
            value="next",
            priority=Priority.NORMAL,
            source_name="S2",
            reason_code="C2",
        )

        decision = resolver.resolve([action, transition], current_state="current")

        assert decision.action == "answer"
        assert decision.next_state == "next"
        assert decision.resolution_trace["merge_decision"] == "MERGED"

    def test_criterion_combinable_false_blocks(self):
        """
        Plan criterion: combinable=False blocks all transitions.
        """
        from src.blackboard import ConflictResolver, Proposal, Priority, ProposalType

        resolver = ConflictResolver()

        action = Proposal(
            type=ProposalType.ACTION,
            value="reject",
            priority=Priority.CRITICAL,
            source_name="S1",
            reason_code="C1",
            combinable=False,
        )

        transition = Proposal(
            type=ProposalType.TRANSITION,
            value="next",
            priority=Priority.NORMAL,
            source_name="S2",
            reason_code="C2",
        )

        decision = resolver.resolve([action, transition], current_state="current")

        assert decision.action == "reject"
        assert decision.next_state == "current"  # Blocked!
        assert decision.resolution_trace["merge_decision"] == "BLOCKED"
        assert len(decision.rejected_proposals) == 1

    def test_criterion_priority_resolution(self):
        """
        Plan criterion: Higher priority wins (CRITICAL > HIGH > NORMAL > LOW).
        """
        from src.blackboard import ConflictResolver, Proposal, Priority, ProposalType

        resolver = ConflictResolver()

        proposals = [
            Proposal(type=ProposalType.ACTION, value="low", priority=Priority.LOW,
                     source_name="S1", reason_code="C1"),
            Proposal(type=ProposalType.ACTION, value="critical", priority=Priority.CRITICAL,
                     source_name="S2", reason_code="C2"),
            Proposal(type=ProposalType.ACTION, value="normal", priority=Priority.NORMAL,
                     source_name="S3", reason_code="C3"),
        ]

        decision = resolver.resolve(proposals, current_state="state")

        assert decision.action == "critical"

    def test_criterion_fallback_transition(self):
        """
        Plan criterion: resolve_with_fallback applies fallback when no transition.
        """
        from src.blackboard import ConflictResolver, Proposal, Priority, ProposalType

        resolver = ConflictResolver()

        action = Proposal(
            type=ProposalType.ACTION,
            value="process",
            priority=Priority.NORMAL,
            source_name="S1",
            reason_code="C1",
            combinable=True,
        )

        decision = resolver.resolve_with_fallback(
            proposals=[action],
            current_state="current",
            fallback_transition="any_target",
        )

        assert decision.next_state == "any_target"
        assert "fallback_any_transition" in decision.reason_codes
