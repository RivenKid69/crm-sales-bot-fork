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
        - Delegate go_back logic to CircularFlowManager (SINGLE SOURCE OF TRUTH)
        - If allowed: propose "acknowledge_go_back" action with DEFERRED increment
        - If NOT allowed: block transition and propose "go_back_limit_reached" action

    Priority:
        Should run BEFORE TransitionResolverSource (priority_order < 50)
        so it can intercept and potentially block go_back transitions.

    FUNDAMENTAL ARCHITECTURE:
        CircularFlowManager is the SINGLE SOURCE OF TRUTH for go_back logic.
        This source uses CircularFlowManager's methods:
        - get_go_back_target(state, transitions): Get target state (YAML or allowed_gobacks)
        - is_limit_reached(): Check if count >= max
        - record_go_back(from, to): Called by Orchestrator after successful transition

        This eliminates code duplication and ensures consistency.

    DEFERRED INCREMENT MECHANISM:
        This source does NOT increment goback_count directly. Instead:
        1. It adds pending_goback_increment=True to the proposal metadata
        2. The Orchestrator calls circular_flow.record_go_back() in _apply_side_effects()
           ONLY IF the go_back transition actually won the conflict resolution

        This prevents incorrect counter increment when another source with higher
        priority (e.g., ObjectionGuardSource with CRITICAL) blocks the go_back.

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
        2. Check if go_back is allowed (considering both limit AND YAML transition)
        3. If allowed:
           - Propose "acknowledge_go_back" action with DEFERRED increment metadata
           - Let TransitionResolverSource handle the actual transition from YAML
           - Orchestrator will increment counter ONLY if transition actually happens
        4. If NOT allowed:
           - Propose blocking action to prevent transition
           - Explain to user that they've used all go_back chances

        FIXES APPLIED:
        - Counter is now incremented via DEFERRED mechanism.
          We add pending_goback_increment=True to metadata, and orchestrator
          increments the counter in _apply_side_effects() ONLY IF:
          1. The action "acknowledge_go_back" won the conflict resolution
          2. The state actually changed (transition happened)
          This prevents incorrect increment when higher-priority sources block go_back.

        - We now check YAML transition availability BEFORE allowing.
          If there's no go_back transition defined in YAML for the current state,
          we don't propose the action at all (no counter waste).

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
        transitions = ctx.state_config.get("transitions", {})

        # =====================================================================
        # FUNDAMENTAL FIX: Use CircularFlowManager's unified methods
        # =====================================================================
        # CircularFlowManager is now the SINGLE SOURCE OF TRUTH for go_back logic.
        # It handles both YAML transitions and allowed_gobacks map internally.
        #
        # This eliminates code duplication and ensures consistency between
        # CircularFlowManager.can_go_back() and GoBackGuardSource logic.
        # =====================================================================

        # Get target state using CircularFlowManager's unified method
        prev_state = circular_flow.get_go_back_target(current_state, transitions)

        if not prev_state:
            logger.debug(
                f"GoBackGuard: No go_back transition defined for state={current_state}"
            )
            self._log_contribution(
                reason=f"No go_back transition defined for state {current_state}"
            )
            return

        # Check if go_back is allowed (limit + target existence)
        # Note: We already know target exists, so this checks limit only
        limit_reached = circular_flow.is_limit_reached()
        remaining = circular_flow.get_remaining_gobacks()

        logger.debug(
            f"GoBackGuard check: state={current_state}, "
            f"limit_reached={limit_reached}, remaining={remaining}, "
            f"count={circular_flow.goback_count}, max={circular_flow.max_gobacks}, "
            f"prev_state={prev_state}"
        )

        if not limit_reached:
            # ALLOWED: Propose action with DEFERRED increment
            #
            # BUGFIX #1: We do NOT increment goback_count here!
            # Instead, we add pending_goback_increment=True to metadata.
            # The orchestrator will increment the counter in _apply_side_effects()
            # ONLY IF:
            # 1. This action won the conflict resolution (decision.action == "acknowledge_go_back")
            # 2. The state actually changed to prev_state (transition happened)
            #
            # This prevents counter increment when:
            # - ObjectionGuardSource (with CRITICAL priority) blocks go_back with soft_close
            # - Any other higher-priority source blocks the transition

            logger.info(
                f"GoBack allowed (deferred increment): {current_state} -> {prev_state}, "
                f"remaining={remaining}"
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
                    # DEFERRED INCREMENT: Orchestrator uses this to increment
                    # goback_count ONLY if this action wins AND transition happens
                    "pending_goback_increment": True,
                    "remaining_gobacks": remaining,
                    "goback_count_before": circular_flow.goback_count,
                }
            )

            self._log_contribution(
                action="acknowledge_go_back",
                reason=f"GoBack allowed (deferred): {current_state} -> {prev_state}"
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
