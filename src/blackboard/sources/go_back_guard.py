# src/blackboard/sources/go_back_guard.py

"""
Go Back Guard Knowledge Source for Dialogue Blackboard System.

This source integrates CircularFlowManager with the blackboard pipeline,
enforcing go_back limits and tracking go_back history.

FIX: Previously, go_back was handled via YAML transitions but CircularFlowManager
was never invoked in the blackboard pipeline. This source ensures:
1. max_gobacks limit is enforced
2. goback_count is properly incremented
3. If limit reached, alternative action is proposed instead of transition
"""

from typing import Set, Optional, TYPE_CHECKING
import logging

from ..knowledge_source import KnowledgeSource
from ..enums import Priority

if TYPE_CHECKING:
    from ..blackboard import DialogueBlackboard

logger = logging.getLogger(__name__)


class GoBackGuardSource(KnowledgeSource):
    """
    Knowledge Source for enforcing go_back limits via CircularFlowManager.

    Responsibility:
        - Intercept go_back intents before TransitionResolverSource
        - Check if go_back is allowed (via CircularFlowManager.can_go_back)
        - If allowed: execute go_back (increment counter) and allow transition
        - If NOT allowed: block transition and propose alternative action

    Priority:
        Should run BEFORE TransitionResolverSource (priority_order < 50)
        so it can intercept and potentially block go_back transitions.

    Integration with CircularFlowManager:
        - Uses state_machine.circular_flow.can_go_back() to check limits
        - Uses state_machine.circular_flow.go_back() to execute and track

    Why this source exists:
        The YAML transition for go_back (go_back: "{{prev_phase_state}}")
        was being processed by TransitionResolverSource, but CircularFlowManager
        was never consulted. This caused:
        - max_gobacks limit to be ignored
        - goback_count to always remain 0
    """

    # Intents that trigger go_back behavior
    GO_BACK_INTENTS: Set[str] = {
        "go_back",
        "correct_info",  # Often used to go back and correct information
    }

    def __init__(
        self,
        go_back_intents: Optional[Set[str]] = None,
        name: str = "GoBackGuardSource"
    ):
        """
        Initialize the go back guard source.

        Args:
            go_back_intents: Set of intents considered go_back triggers.
                            Defaults to GO_BACK_INTENTS.
            name: Source name for logging
        """
        super().__init__(name)
        self._go_back_intents = go_back_intents or self.GO_BACK_INTENTS.copy()

    @property
    def go_back_intents(self) -> Set[str]:
        """Get the set of go_back intents."""
        return self._go_back_intents

    def should_contribute(self, blackboard: 'DialogueBlackboard') -> bool:
        """
        Quick check: is current intent a go_back trigger?

        Args:
            blackboard: The dialogue blackboard

        Returns:
            True if current intent triggers go_back logic, False otherwise
        """
        if not self._enabled:
            return False

        return blackboard.current_intent in self._go_back_intents

    def contribute(self, blackboard: 'DialogueBlackboard') -> None:
        """
        Check go_back limits and propose appropriate action.

        Algorithm:
        1. Get CircularFlowManager from state_machine
        2. Check if go_back limit is reached (count >= max)
        3. If limit NOT reached:
           - Increment counter and record history
           - Propose "acknowledge_go_back" action (combinable=True)
           - Let TransitionResolverSource handle the actual transition from YAML
        4. If limit reached:
           - Propose blocking action to prevent transition
           - Explain to user that they've used all go_back chances

        FIX: We now check ONLY the goback count limit, not allowed_gobacks map.
        The actual go_back target comes from YAML transitions ({{prev_phase_state}}),
        not from CircularFlowManager.allowed_gobacks which only has SPIN states.

        Args:
            blackboard: The dialogue blackboard to contribute to
        """
        if not self._enabled:
            return

        ctx = blackboard.get_context()
        intent = ctx.current_intent

        if intent not in self._go_back_intents:
            self._log_contribution(reason="Intent not go_back related")
            return

        # Get CircularFlowManager from state_machine
        state_machine = blackboard._state_machine
        circular_flow = getattr(state_machine, 'circular_flow', None)

        if circular_flow is None:
            logger.warning("CircularFlowManager not available on state_machine")
            self._log_contribution(reason="CircularFlowManager not available")
            return

        current_state = ctx.state

        # ======================================================================
        # KNOWN BUG #2: Inconsistency with CircularFlowManager.can_go_back()
        # ======================================================================
        #
        # PROBLEM:
        #   CircularFlowManager.can_go_back() checks TWO conditions:
        #     1. goback_count >= max_gobacks
        #     2. current_state in allowed_gobacks
        #
        #   But GoBackGuardSource checks ONLY the first condition.
        #   This causes counter to increment even when:
        #     - State has no go_back transition in YAML (prev_state = None)
        #     - State is not in allowed_gobacks map
        #
        # EXAMPLE:
        #   1. User says "go_back" in "presentation" state
        #   2. "presentation" has no go_back transition in YAML
        #   3. GoBackGuardSource: limit not reached → count += 1
        #   4. prev_state = None (no transition defined)
        #   5. TransitionResolverSource: no go_back transition → stays in presentation
        #   6. RESULT: count=1 but no go_back happened!
        #
        # THE COMMENT BELOW EXPLAINS WHY allowed_gobacks IS NOT CHECKED:
        #   "go_back target comes from YAML transitions, not allowed_gobacks"
        #   This is correct reasoning, BUT the counter still shouldn't increment
        #   if there's no go_back transition defined.
        #
        # FIX REQUIRED:
        #   Before incrementing counter, check:
        #     prev_state = transitions.get("go_back")
        #     if not prev_state:
        #         return  # No go_back defined for this state
        #
        # SEVERITY: MEDIUM - wastes go_back quota in states without go_back
        # ======================================================================
        #
        # Original comment (reasoning is correct, but implementation is buggy):
        # FIX: Check ONLY the limit, not allowed_gobacks map
        # The go_back target is defined in YAML transitions, not in allowed_gobacks
        limit_reached = circular_flow.goback_count >= circular_flow.max_gobacks
        remaining = circular_flow.get_remaining_gobacks()

        logger.debug(
            f"GoBackGuard check: state={current_state}, "
            f"limit_reached={limit_reached}, remaining={remaining}, "
            f"count={circular_flow.goback_count}, max={circular_flow.max_gobacks}"
        )

        if not limit_reached:
            # ALLOWED: Increment counter and let transition happen
            # Get prev_state from YAML transitions (via flow config)
            transitions = ctx.state_config.get("transitions", {})
            prev_state = transitions.get("go_back")

            # ======================================================================
            # KNOWN BUG #1: Counter increments BEFORE conflict resolution
            # ======================================================================
            #
            # PROBLEM:
            #   goback_count is incremented here, but the actual go_back transition
            #   is decided later by ConflictResolver. If a higher-priority source
            #   (e.g., ObjectionGuardSource with CRITICAL) proposes soft_close,
            #   the go_back transition WON'T happen, but counter is ALREADY incremented.
            #
            # EXAMPLE:
            #   1. User says "go_back" while at objection limit
            #   2. GoBackGuardSource: count=0 → count=1, proposes acknowledge_go_back
            #   3. ObjectionGuardSource: proposes soft_close (CRITICAL priority)
            #   4. ConflictResolver: CRITICAL wins → transition to soft_close
            #   5. RESULT: count=1 but go_back never happened!
            #
            # THE OLD COMMENT BELOW IS INCORRECT:
            #   It claims "GoBackGuardSource OWNS the go_back logic" but this ignores
            #   that other sources can propose BLOCKING transitions with higher priority.
            #
            # FIX REQUIRED:
            #   Option A: Increment counter in _apply_side_effects() AFTER resolution
            #   Option B: Check if go_back transition actually won in commit phase
            #   Option C: GoBackGuardSource proposes blocking action (combinable=False)
            #             but this would break other valid transitions
            #
            # SEVERITY: MEDIUM - can waste go_back quota without actual go_back
            # ======================================================================
            #
            # OLD COMMENT (kept for reference, but INCORRECT reasoning):
            # This might look like a race condition because we increment goback_count
            # BEFORE the conflict resolver decides whether the transition actually happens.
            # However, this is correct because:
            #
            # 1. Single-threaded execution: Orchestrator calls sources sequentially
            #    (orchestrator.py:259), so no concurrent access to circular_flow
            #
            # 2. GoBackGuardSource OWNS the go_back logic: We check the limit (line 141)
            #    and increment (below) in the same synchronous contribute() call.
            #    The count is already updated when we create proposals.
            #
            # 3. Deterministic flow: If limit is not reached, we WILL allow go_back.
            #    The proposal we create (combinable=True) doesn't block the transition.
            #    TransitionResolverSource handles the actual YAML transition separately.
            #
            # 4. No external record_goback() call: CircularFlowManager.go_back() is NOT
            #    called from the blackboard pipeline. This source manages the count directly.
            #
            # Timeline per turn:
            #   count=N → check limit → increment to N+1 → create proposal → resolution
            # Next turn sees count=N+1 immediately.
            #
            # BUG #2 MANIFESTATION:
            # Counter increments UNCONDITIONALLY here, but history only appends
            # if prev_state is defined. This means:
            #   - State without go_back in YAML: count increases, history unchanged
            #   - Counter and history become inconsistent
            circular_flow.goback_count += 1
            if prev_state:  # BUG: This check should be BEFORE incrementing counter!
                circular_flow.goback_history.append((current_state, prev_state))

            logger.info(
                f"GoBack executed: {current_state} -> {prev_state}, "
                f"remaining={circular_flow.get_remaining_gobacks()}"
            )

            # Propose acknowledgment action (combinable with transition)
            blackboard.propose_action(
                action="acknowledge_go_back",
                priority=Priority.NORMAL,
                combinable=True,  # Allow transition to proceed
                reason_code="go_back_allowed",
                source_name=self.name,
                metadata={
                    "from_state": current_state,
                    "to_state": prev_state,
                    "remaining_gobacks": circular_flow.get_remaining_gobacks(),
                    "goback_count": circular_flow.goback_count,
                }
            )

            self._log_contribution(
                action="acknowledge_go_back",
                reason=f"GoBack allowed: {current_state} -> {prev_state}"
            )
        else:
            # LIMIT REACHED: Block transition and explain
            self._propose_limit_reached_action(blackboard, current_state, circular_flow)

    def _propose_limit_reached_action(
        self,
        blackboard: 'DialogueBlackboard',
        current_state: str,
        circular_flow
    ) -> None:
        """
        Propose blocking action when go_back limit is reached.

        This action:
        - Has combinable=False to BLOCK the go_back transition
        - Explains to user that they can't go back anymore

        Args:
            blackboard: The blackboard to propose to
            current_state: Current state
            circular_flow: CircularFlowManager instance
        """
        logger.info(
            f"GoBack BLOCKED: limit reached for state={current_state}, "
            f"count={circular_flow.goback_count}, max={circular_flow.max_gobacks}"
        )

        # Propose blocking action with HIGH priority
        # combinable=False ensures the transition is blocked
        blackboard.propose_action(
            action="go_back_limit_reached",
            priority=Priority.HIGH,
            combinable=False,  # BLOCK the transition!
            reason_code="go_back_limit_reached",
            source_name=self.name,
            metadata={
                "current_state": current_state,
                "goback_count": circular_flow.goback_count,
                "max_gobacks": circular_flow.max_gobacks,
                "history": circular_flow.get_history(),
            }
        )

        self._log_contribution(
            action="go_back_limit_reached",
            reason=f"GoBack blocked: limit {circular_flow.max_gobacks} reached"
        )
