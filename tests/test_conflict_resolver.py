# tests/test_conflict_resolver.py

"""
Tests for ConflictResolver class.

Tests cover:
- Basic resolution (no proposals, single proposals)
- Priority-based resolution
- Combinable flag behavior (core feature!)
- Reason codes aggregation
- Resolution trace
- Fallback transitions
"""

import pytest
from src.blackboard.conflict_resolver import ConflictResolver
from src.blackboard.models import Proposal
from src.blackboard.enums import Priority, ProposalType


class TestConflictResolver:
    """Test suite for ConflictResolver class."""

    @pytest.fixture
    def resolver(self):
        """Create a ConflictResolver instance."""
        return ConflictResolver(default_action="continue")

    # === Basic resolution tests ===

    def test_no_proposals_returns_defaults(self, resolver):
        """No proposals should return default action and current state."""
        decision = resolver.resolve([], "spin_situation")

        assert decision.action == "continue"
        assert decision.next_state == "spin_situation"

    def test_single_action_proposal(self, resolver):
        """Single action proposal should win."""
        proposals = [
            Proposal(
                type=ProposalType.ACTION,
                value="answer_with_pricing",
                priority=Priority.HIGH,
                source_name="TestSource",
                reason_code="test",
            )
        ]

        decision = resolver.resolve(proposals, "spin_situation")

        assert decision.action == "answer_with_pricing"
        assert decision.next_state == "spin_situation"

    def test_single_transition_proposal(self, resolver):
        """Single transition proposal should win."""
        proposals = [
            Proposal(
                type=ProposalType.TRANSITION,
                value="spin_problem",
                priority=Priority.NORMAL,
                source_name="TestSource",
                reason_code="test",
            )
        ]

        decision = resolver.resolve(proposals, "spin_situation")

        assert decision.action == "continue"
        assert decision.next_state == "spin_problem"

    # === Priority tests ===

    def test_higher_priority_action_wins(self, resolver):
        """Higher priority action should win over lower."""
        proposals = [
            Proposal(
                type=ProposalType.ACTION,
                value="low_priority_action",
                priority=Priority.LOW,
                source_name="Source1",
                reason_code="low",
            ),
            Proposal(
                type=ProposalType.ACTION,
                value="high_priority_action",
                priority=Priority.HIGH,
                source_name="Source2",
                reason_code="high",
            ),
        ]

        decision = resolver.resolve(proposals, "state")

        assert decision.action == "high_priority_action"
        assert len(decision.rejected_proposals) == 1
        assert decision.rejected_proposals[0].value == "low_priority_action"

    def test_critical_beats_high(self, resolver):
        """CRITICAL priority should beat HIGH."""
        proposals = [
            Proposal(
                type=ProposalType.ACTION,
                value="high_action",
                priority=Priority.HIGH,
                source_name="Source1",
                reason_code="high",
            ),
            Proposal(
                type=ProposalType.ACTION,
                value="critical_action",
                priority=Priority.CRITICAL,
                source_name="Source2",
                reason_code="critical",
            ),
        ]

        decision = resolver.resolve(proposals, "state")

        assert decision.action == "critical_action"

    def test_higher_priority_transition_wins(self, resolver):
        """Higher priority transition should win over lower."""
        proposals = [
            Proposal(
                type=ProposalType.TRANSITION,
                value="low_state",
                priority=Priority.LOW,
                source_name="Source1",
                reason_code="low",
            ),
            Proposal(
                type=ProposalType.TRANSITION,
                value="high_state",
                priority=Priority.HIGH,
                source_name="Source2",
                reason_code="high",
            ),
        ]

        decision = resolver.resolve(proposals, "current")

        assert decision.next_state == "high_state"

    def test_priority_order(self, resolver):
        """Test full priority order: CRITICAL > HIGH > NORMAL > LOW."""
        proposals = [
            Proposal(
                type=ProposalType.ACTION,
                value="low_action",
                priority=Priority.LOW,
                source_name="S1",
                reason_code="low",
            ),
            Proposal(
                type=ProposalType.ACTION,
                value="normal_action",
                priority=Priority.NORMAL,
                source_name="S2",
                reason_code="normal",
            ),
            Proposal(
                type=ProposalType.ACTION,
                value="high_action",
                priority=Priority.HIGH,
                source_name="S3",
                reason_code="high",
            ),
            Proposal(
                type=ProposalType.ACTION,
                value="critical_action",
                priority=Priority.CRITICAL,
                source_name="S4",
                reason_code="critical",
            ),
        ]

        decision = resolver.resolve(proposals, "state")

        assert decision.action == "critical_action"
        assert len(decision.rejected_proposals) == 3

    # === Combinable flag tests (CRITICAL) ===

    def test_combinable_true_merges_action_and_transition(self, resolver):
        """combinable=True should allow action + transition merge."""
        proposals = [
            Proposal(
                type=ProposalType.ACTION,
                value="answer_with_pricing",
                priority=Priority.HIGH,
                source_name="PriceSource",
                reason_code="price",
                combinable=True,  # KEY!
            ),
            Proposal(
                type=ProposalType.TRANSITION,
                value="spin_problem",
                priority=Priority.NORMAL,
                source_name="DataSource",
                reason_code="data_complete",
            ),
        ]

        decision = resolver.resolve(proposals, "spin_situation")

        # BOTH should be applied
        assert decision.action == "answer_with_pricing"
        assert decision.next_state == "spin_problem"
        assert "price" in decision.reason_codes
        assert "data_complete" in decision.reason_codes

    def test_combinable_false_blocks_transitions(self, resolver):
        """combinable=False should block all transitions."""
        proposals = [
            Proposal(
                type=ProposalType.ACTION,
                value="handle_rejection",
                priority=Priority.HIGH,
                source_name="RejectionSource",
                reason_code="rejection",
                combinable=False,  # BLOCKING!
            ),
            Proposal(
                type=ProposalType.TRANSITION,
                value="spin_problem",
                priority=Priority.NORMAL,
                source_name="DataSource",
                reason_code="data_complete",
            ),
        ]

        decision = resolver.resolve(proposals, "spin_situation")

        # Action wins, transition is BLOCKED
        assert decision.action == "handle_rejection"
        assert decision.next_state == "spin_situation"  # NO TRANSITION!
        assert len(decision.rejected_proposals) == 1
        assert decision.rejected_proposals[0].value == "spin_problem"

    def test_combinable_false_blocks_multiple_transitions(self, resolver):
        """combinable=False should block ALL transitions."""
        proposals = [
            Proposal(
                type=ProposalType.ACTION,
                value="escalate_to_human",
                priority=Priority.CRITICAL,
                source_name="EscalationSource",
                reason_code="escalation",
                combinable=False,
            ),
            Proposal(
                type=ProposalType.TRANSITION,
                value="spin_problem",
                priority=Priority.NORMAL,
                source_name="DataSource",
                reason_code="data_complete",
            ),
            Proposal(
                type=ProposalType.TRANSITION,
                value="soft_close",
                priority=Priority.HIGH,
                source_name="OtherSource",
                reason_code="other",
            ),
        ]

        decision = resolver.resolve(proposals, "spin_situation")

        assert decision.action == "escalate_to_human"
        assert decision.next_state == "spin_situation"
        assert len(decision.rejected_proposals) == 2  # Both transitions rejected

    def test_default_combinable_is_true(self, resolver):
        """Default combinable should be True for actions."""
        proposals = [
            Proposal(
                type=ProposalType.ACTION,
                value="some_action",
                priority=Priority.HIGH,
                source_name="Source1",
                reason_code="test",
                # combinable not specified - should default to True
            ),
            Proposal(
                type=ProposalType.TRANSITION,
                value="next_state",
                priority=Priority.NORMAL,
                source_name="Source2",
                reason_code="transition",
            ),
        ]

        decision = resolver.resolve(proposals, "current")

        # Should merge because combinable defaults to True
        assert decision.action == "some_action"
        assert decision.next_state == "next_state"

    # === The Core Problem Test ===

    def test_price_question_with_data_complete_both_applied(self, resolver):
        """
        THIS IS THE CORE TEST.

        Scenario: User asks price question while providing final required data.
        Expected: Answer price question AND transition to next phase.

        This was the bug in legacy system where price_question early-returned
        and blocked the data_complete transition.
        """
        proposals = [
            # PriceQuestionSource proposes action with combinable=True
            Proposal(
                type=ProposalType.ACTION,
                value="answer_with_pricing",
                priority=Priority.HIGH,
                source_name="PriceQuestionSource",
                reason_code="price_question_priority",
                combinable=True,
            ),
            # DataCollectorSource proposes transition (data is complete)
            Proposal(
                type=ProposalType.TRANSITION,
                value="spin_problem",
                priority=Priority.NORMAL,
                source_name="DataCollectorSource",
                reason_code="data_complete",
            ),
        ]

        decision = resolver.resolve(proposals, "spin_situation")

        # CRITICAL ASSERTIONS:
        assert decision.action == "answer_with_pricing", \
            "Bot should answer the price question"
        assert decision.next_state == "spin_problem", \
            "Bot should ALSO transition to next phase (NOT stay in spin_situation)"
        assert "price_question_priority" in decision.reason_codes
        assert "data_complete" in decision.reason_codes
        assert len(decision.rejected_proposals) == 0, \
            "Nothing should be rejected when combinable=True"

    # === Reason codes tests ===

    def test_reason_codes_include_winners(self, resolver):
        """reason_codes should include winning action and transition codes."""
        proposals = [
            Proposal(
                type=ProposalType.ACTION,
                value="action",
                priority=Priority.HIGH,
                source_name="S1",
                reason_code="reason_action",
                combinable=True,
            ),
            Proposal(
                type=ProposalType.TRANSITION,
                value="state",
                priority=Priority.NORMAL,
                source_name="S2",
                reason_code="reason_transition",
            ),
        ]

        decision = resolver.resolve(proposals, "current")

        assert "reason_action" in decision.reason_codes
        assert "reason_transition" in decision.reason_codes

    def test_reason_codes_exclude_losers(self, resolver):
        """reason_codes should not include rejected proposals' codes."""
        proposals = [
            Proposal(
                type=ProposalType.ACTION,
                value="winner",
                priority=Priority.HIGH,
                source_name="S1",
                reason_code="winner_reason",
            ),
            Proposal(
                type=ProposalType.ACTION,
                value="loser",
                priority=Priority.LOW,
                source_name="S2",
                reason_code="loser_reason",
            ),
        ]

        decision = resolver.resolve(proposals, "current")

        assert "winner_reason" in decision.reason_codes
        assert "loser_reason" not in decision.reason_codes

    # === Resolution trace tests ===

    def test_resolution_trace_populated(self, resolver):
        """resolution_trace should contain debug information."""
        proposals = [
            Proposal(
                type=ProposalType.ACTION,
                value="action",
                priority=Priority.HIGH,
                source_name="Source",
                reason_code="reason",
                combinable=True,
            ),
        ]

        decision = resolver.resolve(proposals, "state")

        assert "action_proposals_count" in decision.resolution_trace
        assert "merge_decision" in decision.resolution_trace

    def test_resolution_trace_blocking_reason(self, resolver):
        """resolution_trace should include blocking_reason when applicable."""
        proposals = [
            Proposal(
                type=ProposalType.ACTION,
                value="blocking_action",
                priority=Priority.HIGH,
                source_name="Source",
                reason_code="block",
                combinable=False,
            ),
            Proposal(
                type=ProposalType.TRANSITION,
                value="state",
                priority=Priority.NORMAL,
                source_name="Source2",
                reason_code="trans",
            ),
        ]

        decision = resolver.resolve(proposals, "current")

        assert decision.resolution_trace["blocking_reason"] is not None
        assert "blocking_action" in decision.resolution_trace["blocking_reason"]

    def test_resolution_trace_merge_decision_values(self, resolver):
        """resolution_trace should show correct merge_decision."""
        # Test MERGED
        proposals_merged = [
            Proposal(
                type=ProposalType.ACTION,
                value="action",
                priority=Priority.HIGH,
                source_name="S1",
                reason_code="a",
                combinable=True,
            ),
            Proposal(
                type=ProposalType.TRANSITION,
                value="state",
                priority=Priority.NORMAL,
                source_name="S2",
                reason_code="t",
            ),
        ]
        decision = resolver.resolve(proposals_merged, "current")
        assert decision.resolution_trace["merge_decision"] == "MERGED"

        # Test BLOCKED
        proposals_blocked = [
            Proposal(
                type=ProposalType.ACTION,
                value="action",
                priority=Priority.HIGH,
                source_name="S1",
                reason_code="a",
                combinable=False,
            ),
            Proposal(
                type=ProposalType.TRANSITION,
                value="state",
                priority=Priority.NORMAL,
                source_name="S2",
                reason_code="t",
            ),
        ]
        decision = resolver.resolve(proposals_blocked, "current")
        assert decision.resolution_trace["merge_decision"] == "BLOCKED"

        # Test ACTION_ONLY
        proposals_action = [
            Proposal(
                type=ProposalType.ACTION,
                value="action",
                priority=Priority.HIGH,
                source_name="S1",
                reason_code="a",
                combinable=True,
            ),
        ]
        decision = resolver.resolve(proposals_action, "current")
        assert decision.resolution_trace["merge_decision"] == "ACTION_ONLY"

        # Test TRANSITION_ONLY
        proposals_transition = [
            Proposal(
                type=ProposalType.TRANSITION,
                value="state",
                priority=Priority.NORMAL,
                source_name="S1",
                reason_code="t",
            ),
        ]
        decision = resolver.resolve(proposals_transition, "current")
        assert decision.resolution_trace["merge_decision"] == "TRANSITION_ONLY"

        # Test NO_PROPOSALS
        decision = resolver.resolve([], "current")
        assert decision.resolution_trace["merge_decision"] == "NO_PROPOSALS"

    # === Fallback transition tests ===

    def test_resolve_with_fallback_applies_fallback(self, resolver):
        """resolve_with_fallback should apply fallback when no transition."""
        proposals = [
            Proposal(
                type=ProposalType.ACTION,
                value="some_action",
                priority=Priority.NORMAL,
                source_name="Source",
                reason_code="reason",
                combinable=True,
            ),
            # No transition proposal
        ]

        decision = resolver.resolve_with_fallback(
            proposals=proposals,
            current_state="spin_situation",
            fallback_transition="spin_problem",  # "any" transition
        )

        assert decision.next_state == "spin_problem"
        assert "fallback_any_transition" in decision.reason_codes

    def test_resolve_with_fallback_no_fallback_if_transition_exists(self, resolver):
        """resolve_with_fallback should not apply fallback if transition exists."""
        proposals = [
            Proposal(
                type=ProposalType.TRANSITION,
                value="explicit_state",
                priority=Priority.NORMAL,
                source_name="Source",
                reason_code="explicit",
            ),
        ]

        decision = resolver.resolve_with_fallback(
            proposals=proposals,
            current_state="current",
            fallback_transition="fallback_state",
        )

        assert decision.next_state == "explicit_state"
        assert "fallback_any_transition" not in decision.reason_codes

    def test_resolve_with_fallback_blocked_by_non_combinable(self, resolver):
        """resolve_with_fallback should not apply fallback if action blocks it."""
        proposals = [
            Proposal(
                type=ProposalType.ACTION,
                value="blocking_action",
                priority=Priority.HIGH,
                source_name="Source",
                reason_code="blocking",
                combinable=False,  # Blocks fallback
            ),
        ]

        decision = resolver.resolve_with_fallback(
            proposals=proposals,
            current_state="current",
            fallback_transition="fallback_state",
        )

        assert decision.next_state == "current"  # Fallback not applied

    def test_resolve_with_fallback_no_fallback_provided(self, resolver):
        """resolve_with_fallback should work without fallback."""
        proposals = [
            Proposal(
                type=ProposalType.ACTION,
                value="action",
                priority=Priority.NORMAL,
                source_name="Source",
                reason_code="reason",
            ),
        ]

        decision = resolver.resolve_with_fallback(
            proposals=proposals,
            current_state="current",
            fallback_transition=None,
        )

        assert decision.next_state == "current"
        assert "fallback_any_transition" not in decision.reason_codes

    # === Data and flags passthrough ===

    def test_resolve_passes_data_updates(self, resolver):
        """resolve should pass data_updates to decision."""
        proposals = []
        data_updates = {"new_field": "value"}

        decision = resolver.resolve(
            proposals=proposals,
            current_state="state",
            data_updates=data_updates,
        )

        assert decision.data_updates == data_updates

    def test_resolve_passes_flags_to_set(self, resolver):
        """resolve should pass flags_to_set to decision."""
        proposals = []
        flags = {"flag1": True}

        decision = resolver.resolve(
            proposals=proposals,
            current_state="state",
            flags_to_set=flags,
        )

        assert decision.flags_to_set == flags


class TestConflictResolverEdgeCases:
    """Edge case tests for ConflictResolver."""

    @pytest.fixture
    def resolver(self):
        return ConflictResolver(default_action="default_action")

    def test_same_priority_first_wins(self, resolver):
        """When two proposals have same priority, first one wins."""
        proposals = [
            Proposal(
                type=ProposalType.ACTION,
                value="first_action",
                priority=Priority.NORMAL,
                source_name="Source1",
                reason_code="first",
            ),
            Proposal(
                type=ProposalType.ACTION,
                value="second_action",
                priority=Priority.NORMAL,
                source_name="Source2",
                reason_code="second",
            ),
        ]

        decision = resolver.resolve(proposals, "state")

        # After sorting by priority (which is same), order is preserved
        assert decision.action == "first_action"

    def test_many_proposals_performance(self, resolver):
        """Resolver should handle many proposals efficiently."""
        proposals = [
            Proposal(
                type=ProposalType.ACTION if i % 2 == 0 else ProposalType.TRANSITION,
                value=f"value_{i}",
                priority=Priority(i % 4),
                source_name=f"Source{i}",
                reason_code=f"reason_{i}",
            )
            for i in range(100)
        ]

        # Should not raise or take too long
        decision = resolver.resolve(proposals, "state")

        # CRITICAL priority wins (index 0, 4, 8, ... have priority 0)
        assert decision.action == "value_0"

    def test_custom_default_action(self):
        """Custom default action should be used when no action proposals."""
        resolver = ConflictResolver(default_action="custom_default")

        decision = resolver.resolve([], "state")

        assert decision.action == "custom_default"

    def test_transition_only_uses_default_action(self, resolver):
        """When only transition exists, default action should be used."""
        proposals = [
            Proposal(
                type=ProposalType.TRANSITION,
                value="new_state",
                priority=Priority.NORMAL,
                source_name="Source",
                reason_code="trans",
            ),
        ]

        decision = resolver.resolve(proposals, "current")

        assert decision.action == "default_action"
        assert decision.next_state == "new_state"
