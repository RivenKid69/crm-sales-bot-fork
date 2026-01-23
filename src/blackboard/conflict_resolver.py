# src/blackboard/conflict_resolver.py

"""
ConflictResolver for Dialogue Blackboard System.

This module resolves conflicts between proposals from multiple Knowledge Sources.
It implements priority-based resolution with support for combinable/blocking actions.
"""

from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
import logging

from .models import Proposal, ResolvedDecision
from .enums import Priority, ProposalType

logger = logging.getLogger(__name__)


@dataclass
class ResolutionTrace:
    """
    Detailed trace of the resolution process for debugging.

    Attributes:
        action_proposals: All action proposals received
        transition_proposals: All transition proposals received
        action_ranking: Actions sorted by priority
        transition_ranking: Transitions sorted by priority
        winning_action: Selected action proposal
        winning_transition: Selected transition proposal (may be None)
        merge_decision: Whether action and transition were merged
        blocking_reason: If action blocked transition, why
    """
    action_proposals: List[Proposal] = field(default_factory=list)
    transition_proposals: List[Proposal] = field(default_factory=list)
    action_ranking: List[Tuple[str, Priority, str]] = field(default_factory=list)
    transition_ranking: List[Tuple[str, Priority, str]] = field(default_factory=list)
    winning_action: Optional[Proposal] = None
    winning_transition: Optional[Proposal] = None
    merge_decision: str = ""
    blocking_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging/serialization."""
        return {
            "action_proposals_count": len(self.action_proposals),
            "transition_proposals_count": len(self.transition_proposals),
            "action_ranking": self.action_ranking,
            "transition_ranking": self.transition_ranking,
            "winning_action": str(self.winning_action) if self.winning_action else None,
            "winning_transition": str(self.winning_transition) if self.winning_transition else None,
            "merge_decision": self.merge_decision,
            "blocking_reason": self.blocking_reason,
            # Include winning action metadata for deferred side effects
            # (e.g., GoBackGuardSource needs this for deferred goback_count increment)
            "winning_action_metadata": self.winning_action.metadata if self.winning_action else {},
        }


class ConflictResolver:
    """
    Resolves conflicts between proposals from multiple Knowledge Sources.

    Core Algorithm:
        1. Separate proposals by type (ACTION vs TRANSITION)
        2. Sort each list by priority (CRITICAL > HIGH > NORMAL > LOW)
        3. Select winning action (highest priority)
        4. Check combinable flag:
           - If combinable=False: action BLOCKS all transitions
           - If combinable=True: action can MERGE with transition
        5. Select winning transition (if not blocked)
        6. Return ResolvedDecision with both action and next_state

    Key Innovation:
        The combinable flag allows actions like "answer_with_pricing" to coexist
        with transitions like "data_complete -> spin_problem". This solves the
        core problem where price questions blocked phase progression.

    Priority Semantics:
        CRITICAL (0): Blocking actions (rejection, escalation) - always wins
        HIGH (1): Important actions (price questions, objection handling)
        NORMAL (2): Standard processing (intent rules, data collection)
        LOW (3): Fallback actions (continue, default behavior)
    """

    def __init__(self, default_action: str = "continue"):
        """
        Initialize the conflict resolver.

        Args:
            default_action: Action to use when no action proposals exist
        """
        self._default_action = default_action

    def resolve(
        self,
        proposals: List[Proposal],
        current_state: str,
        data_updates: Optional[Dict[str, Any]] = None,
        flags_to_set: Optional[Dict[str, Any]] = None
    ) -> ResolvedDecision:
        """
        Resolve conflicts between proposals and produce final decision.

        Args:
            proposals: List of all proposals from Knowledge Sources
            current_state: Current dialogue state (used if no transition)
            data_updates: Data updates to include in decision
            flags_to_set: Flags to include in decision

        Returns:
            ResolvedDecision with final action, next_state, and metadata
        """
        trace = ResolutionTrace()

        # Step 1: Separate proposals by type
        action_proposals = [p for p in proposals if p.type == ProposalType.ACTION]
        transition_proposals = [p for p in proposals if p.type == ProposalType.TRANSITION]

        trace.action_proposals = action_proposals
        trace.transition_proposals = transition_proposals

        logger.debug(
            f"Resolving conflicts: {len(action_proposals)} actions, "
            f"{len(transition_proposals)} transitions"
        )

        # Step 2: Sort by priority (lower value = higher priority)
        # Use priority_rank as tie-breaker within the same Priority enum.
        #
        # NOTE ON TIE-BREAKING DETERMINISM:
        # When two proposals have the same (priority, priority_rank), the result
        # depends on their order in the input list. This is NOT a bug because:
        #
        # 1. Python list.sort() is STABLE - equal elements preserve relative order
        # 2. Proposal order is DETERMINISTIC:
        #    - Sources are created via SourceRegistry.create_sources() which sorts
        #      by priority_order (see source_registry.py:187-190)
        #    - Orchestrator iterates sources in fixed order (orchestrator.py:259)
        #    - Each source adds proposals in deterministic code order
        # 3. Therefore: same input → same source order → same proposal order → same result
        #
        # The behavior "different input order → different result" is EXPECTED for
        # stable sort. This is by design, not a bug. If explicit ordering is needed
        # for equal priorities, set distinct priority_rank values in Knowledge Sources.
        default_rank = 10_000
        def _sort_key(p: Proposal):
            rank = p.priority_rank if p.priority_rank is not None else default_rank
            return (p.priority.value, rank)

        action_proposals.sort(key=_sort_key)
        transition_proposals.sort(key=_sort_key)

        # Record rankings for trace
        trace.action_ranking = [
            (p.value, p.priority, p.source_name) for p in action_proposals
        ]
        trace.transition_ranking = [
            (p.value, p.priority, p.source_name) for p in transition_proposals
        ]

        # Step 3: Select winning action
        winning_action: Optional[Proposal] = None
        if action_proposals:
            winning_action = action_proposals[0]
            trace.winning_action = winning_action

            logger.debug(
                f"Winning action: {winning_action.value} "
                f"(priority={winning_action.priority.name}, "
                f"combinable={winning_action.combinable}, "
                f"source={winning_action.source_name})"
            )

        # Step 4: Check combinable flag and decide on transition
        winning_transition: Optional[Proposal] = None
        rejected_proposals: List[Proposal] = []

        if winning_action and not winning_action.combinable:
            # BLOCKING action - reject all transitions
            trace.blocking_reason = (
                f"Action '{winning_action.value}' has combinable=False, "
                f"blocking {len(transition_proposals)} transition(s)"
            )
            trace.merge_decision = "BLOCKED"

            rejected_proposals.extend(transition_proposals)
            rejected_proposals.extend(action_proposals[1:])  # Non-winning actions

            logger.debug(
                f"Blocking action detected: {winning_action.value}. "
                f"Transitions blocked: {[p.value for p in transition_proposals]}"
            )
        else:
            # COMBINABLE action (or no action) - can merge with transition
            if transition_proposals:
                winning_transition = transition_proposals[0]
                trace.winning_transition = winning_transition
                trace.merge_decision = "MERGED" if winning_action else "TRANSITION_ONLY"

                rejected_proposals.extend(transition_proposals[1:])  # Non-winning transitions

                logger.debug(
                    f"Winning transition: {winning_transition.value} "
                    f"(priority={winning_transition.priority.name}, "
                    f"source={winning_transition.source_name})"
                )
            else:
                trace.merge_decision = "ACTION_ONLY" if winning_action else "NO_PROPOSALS"

            if winning_action:
                rejected_proposals.extend(action_proposals[1:])  # Non-winning actions

        # Step 5: Build reason codes
        reason_codes: List[str] = []
        if winning_action:
            reason_codes.append(winning_action.reason_code)
        if winning_transition:
            reason_codes.append(winning_transition.reason_code)

        # Step 6: Construct final decision
        final_action = winning_action.value if winning_action else self._default_action
        next_state = winning_transition.value if winning_transition else current_state

        decision = ResolvedDecision(
            action=final_action,
            next_state=next_state,
            reason_codes=reason_codes,
            rejected_proposals=rejected_proposals,
            resolution_trace=trace.to_dict(),
            data_updates=data_updates or {},
            flags_to_set=flags_to_set or {},
        )

        logger.info(
            f"Conflict resolved: action='{final_action}', next_state='{next_state}', "
            f"merge={trace.merge_decision}, rejected={len(rejected_proposals)}"
        )

        return decision

    def resolve_with_fallback(
        self,
        proposals: List[Proposal],
        current_state: str,
        fallback_transition: Optional[str] = None,
        data_updates: Optional[Dict[str, Any]] = None,
        flags_to_set: Optional[Dict[str, Any]] = None
    ) -> ResolvedDecision:
        """
        Resolve conflicts with a fallback transition (e.g., "any" transition).

        This method first tries normal resolution. If no transition is selected
        and a fallback is provided, it applies the fallback transition.

        Args:
            proposals: List of all proposals from Knowledge Sources
            current_state: Current dialogue state
            fallback_transition: Fallback transition target (e.g., from "any" trigger)
            data_updates: Data updates to include in decision
            flags_to_set: Flags to include in decision

        Returns:
            ResolvedDecision with final action, next_state, and metadata
        """
        decision = self.resolve(
            proposals=proposals,
            current_state=current_state,
            data_updates=data_updates,
            flags_to_set=flags_to_set,
        )

        # Apply fallback if no transition was selected and fallback is available
        if decision.next_state == current_state and fallback_transition:
            # ======================================================================
            # NOT A BUG: Fallback correctly respects blocking actions
            # ======================================================================
            #
            # REPORTED CONCERN:
            #   "If blocking action was rejected and didn't become decision.action,
            #    the check might miss it and incorrectly apply fallback"
            #
            # WHY THIS IS CORRECT:
            #
            # 1. HOW resolve() WORKS:
            #    - Sorts proposals by priority (CRITICAL > HIGH > NORMAL > LOW)
            #    - Selects WINNING action (highest priority)
            #    - If winning action has combinable=False → ALL transitions blocked
            #    - decision.action = winning_action.value
            #
            # 2. THE CHECK HERE:
            #    - Looks for proposal where: p.value == decision.action AND not p.combinable
            #    - This finds the WINNING action that blocked transitions
            #    - If found → action_blocked = True → NO fallback
            #
            # 3. WHY REJECTED PROPOSALS DON'T MATTER:
            #    - A rejected blocking action LOST to a higher-priority action
            #    - The higher-priority action made the decision
            #    - If higher-priority action is combinable → transitions allowed
            #    - If higher-priority action is blocking → we catch it here
            #
            # EXAMPLE WALKTHROUGH:
            #   proposals = [
            #     ACTION("block_action", CRITICAL, combinable=False)  # Only proposal
            #   ]
            #   resolve():
            #     winning_action = "block_action" (only one)
            #     combinable=False → transitions blocked
            #     decision.action = "block_action"
            #     decision.next_state = current_state (no transition)
            #
            #   resolve_with_fallback():
            #     next_state == current_state? Yes
            #     fallback available? Yes
            #     action_blocked = any(ACTION, not combinable, value=="block_action")
            #                    = True (found the blocking proposal!)
            #     → Fallback NOT applied ✓
            #
            # EDGE CASE: Multiple blocking actions
            #   Only the WINNING one matters. If it's blocking, we block.
            #   If a lower-priority blocking action lost, its intent is irrelevant.
            #
            # This logic is CORRECT and well-tested.
            # ======================================================================
            action_blocked = any(
                p.type == ProposalType.ACTION and not p.combinable
                for p in proposals
                if p.value == decision.action
            )

            if not action_blocked:
                logger.debug(
                    f"Applying fallback transition: {fallback_transition}"
                )
                decision.next_state = fallback_transition
                decision.reason_codes.append("fallback_any_transition")
                decision.resolution_trace["fallback_applied"] = True

        return decision
