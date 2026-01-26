# src/blackboard/sources/objection_return.py

"""
Objection Return Knowledge Source for Dialogue Blackboard System.

This source handles returning to the previous phase after successfully
handling an objection. It addresses the bug where the bot gets stuck
in handle_objection without returning to the sales flow phases.

Root Cause Fixed:
    - _state_before_objection was being saved but NEVER USED for transitions
    - handle_objection had hardcoded transitions (agreement → close)
    - Phase was lost because handle_objection has no phase field

Solution:
    This Knowledge Source proposes transitions back to _state_before_objection
    when a positive intent is detected in handle_objection state.

Architecture:
    - Follows Blackboard pattern (Knowledge Source)
    - Uses Plugin Architecture (registered via SourceRegistry)
    - Configuration-driven (enabled/disabled via constants.yaml)
    - Priority-based resolution (HIGH priority to win over YAML transitions)

Part of the fundamental fix for the Objection Stuck bug.
"""

from typing import Optional, Set, TYPE_CHECKING
import logging

from ..knowledge_source import KnowledgeSource
from ..enums import Priority
from src.yaml_config.constants import POSITIVE_INTENTS, QUESTION_INTENTS

if TYPE_CHECKING:
    from ..blackboard import DialogueBlackboard

logger = logging.getLogger(__name__)


# Question intents that also trigger return (after refinement from objection_think)
# FIX: Root Cause #4 - ObjectionReturnSource only worked for POSITIVE_INTENTS
# Skeptic personas get objection_think refined to question_features, which needs
# to trigger return to continue the sales flow.
QUESTION_RETURN_INTENTS: Set[str] = {
    "question_features",
    "question_pricing",
    "question_implementation",
    "question_integration",
    "question_demo",
    "comparison",
}


class ObjectionReturnSource(KnowledgeSource):
    """
    Knowledge Source for returning to previous phase after objection handling.

    Responsibility:
        - Detect when objection is successfully handled (positive intent OR question)
        - Propose transition back to saved state (_state_before_objection)
        - Preserve phase continuity in sales flow

    Design:
        When entering handle_objection from a phase state (e.g., bant_budget),
        the orchestrator saves that state in _state_before_objection.

        When the client shows agreement, interest, OR asks a question
        (positive intent or question intent after refinement),
        this source proposes returning to that saved state with HIGH priority.

        This wins over YAML transitions (NORMAL priority) like:
            agreement: close  # Would lose phase forever

        The result is phase preservation:
            bant_budget → handle_objection → bant_budget (via this source)

        Instead of phase loss:
            bant_budget → handle_objection → close (via YAML)

    FIX for handle_objection stuck:
        Skeptic personas express uncertainty like "не уверен нужно ли" which gets
        classified as objection_think. After ObjectionRefinementLayer Rule 5,
        this becomes question_features. Now ObjectionReturnSource also triggers
        on question intents, allowing return from handle_objection.

    Priority: HIGH
        - Must win over TransitionResolverSource (NORMAL priority YAML transitions)
        - Must NOT win over ObjectionGuardSource (CRITICAL priority limit exceeded)

    Thread Safety:
        This class is thread-safe as it only reads from configuration
        and proposes changes through the blackboard.

    Example:
        Turn 1: State=bant_budget, Intent=objection_price
                → Transition to handle_objection
                → _state_before_objection = "bant_budget"

        Turn 2: State=handle_objection, Intent=agreement
                → ObjectionReturnSource proposes: handle_objection → bant_budget
                → TransitionResolver proposes: handle_objection → close
                → HIGH > NORMAL, ObjectionReturnSource wins
                → Final transition: handle_objection → bant_budget ✓

        Turn 2 (alternative): State=handle_objection, Intent=question_features
                (after refinement from objection_think via uncertainty pattern)
                → ObjectionReturnSource proposes: handle_objection → bant_budget
                → Final transition: handle_objection → bant_budget ✓
    """

    # Positive intents that trigger return to previous phase
    # Loaded from constants.yaml via POSITIVE_INTENTS
    # FIX: Now also includes question intents for skeptic persona handling
    DEFAULT_RETURN_INTENTS: Set[str] = set(POSITIVE_INTENTS) | QUESTION_RETURN_INTENTS

    # State that handles objections
    OBJECTION_STATE: str = "handle_objection"

    def __init__(
        self,
        return_intents: Optional[Set[str]] = None,
        enabled: bool = True,
        name: str = "ObjectionReturnSource"
    ):
        """
        Initialize the objection return source.

        Args:
            return_intents: Set of intents that trigger return to previous state.
                           Defaults to POSITIVE_INTENTS from constants.yaml.
            enabled: Whether this source is enabled (default True)
            name: Source name for logging
        """
        super().__init__(name)

        if return_intents is None:
            self._return_intents = set(self.DEFAULT_RETURN_INTENTS)
        else:
            self._return_intents = set(return_intents)

        self._enabled = enabled

        logger.debug(
            f"ObjectionReturnSource initialized",
            extra={
                "return_intents_count": len(self._return_intents),
                "enabled": self._enabled,
            }
        )

    @property
    def return_intents(self) -> Set[str]:
        """Get the set of intents that trigger return."""
        return self._return_intents

    def should_contribute(self, blackboard: 'DialogueBlackboard') -> bool:
        """
        Quick check: should we propose a return transition?

        Conditions (ALL must be true):
        1. Source is enabled
        2. Current state is handle_objection
        3. _state_before_objection is set in state machine
        4. Current intent is a positive/return intent

        This is O(1) - fast checks only.
        """
        if not self._enabled:
            return False

        # Check current state
        if blackboard.current_state != self.OBJECTION_STATE:
            return False

        # Check if we have a saved state to return to
        state_machine = blackboard._state_machine
        saved_state = getattr(state_machine, '_state_before_objection', None)
        if not saved_state:
            return False

        # Check if current intent triggers return
        if blackboard.current_intent not in self._return_intents:
            return False

        return True

    def contribute(self, blackboard: 'DialogueBlackboard') -> None:
        """
        Propose transition back to saved state.

        Algorithm:
        1. Verify all conditions (re-check for safety)
        2. Get saved state from _state_before_objection
        3. Validate that target state exists
        4. Propose transition with HIGH priority
        5. Log contribution for debugging/monitoring
        """
        if not self._enabled:
            return

        # Re-check conditions for safety (in case called without should_contribute)
        if blackboard.current_state != self.OBJECTION_STATE:
            return

        if blackboard.current_intent not in self._return_intents:
            self._log_contribution(
                reason=f"Intent {blackboard.current_intent} not in return_intents"
            )
            return

        state_machine = blackboard._state_machine
        ctx = blackboard.get_context()

        # Get the saved state
        saved_state = getattr(state_machine, '_state_before_objection', None)

        if not saved_state:
            self._log_contribution(
                reason="No saved state to return to"
            )
            return

        # Validate target state exists in flow config
        flow_config = blackboard._flow_config
        if hasattr(flow_config, 'states') and saved_state not in flow_config.states:
            logger.warning(
                f"ObjectionReturnSource: saved state '{saved_state}' "
                f"not found in flow config"
            )
            self._log_contribution(
                reason=f"Target state '{saved_state}' not in flow config"
            )
            return

        # Get phase info for metadata
        phase = None
        if hasattr(flow_config, 'get_phase_for_state'):
            phase = flow_config.get_phase_for_state(saved_state)

        # FIX: Don't return to non-phase states (like greeting, handle_objection)
        # Route to entry_state instead to start the sales phases.
        #
        # Bug history:
        #   - Commit 293109e: ObjectionReturnSource was proposing HIGH priority back to
        #     "greeting" (no phase), causing greeting ↔ handle_objection loop.
        #   - Commit e41667b: Changed to LOW priority fallback to entry_state, but this
        #     lost to TransitionResolver's NORMAL (agreement → close), causing 0% coverage.
        #
        # Solution (current):
        #   Propose entry_state with NORMAL priority. Both sources have equal priority,
        #   but ObjectionReturnSource runs first (priority_order 35 < 50), so its
        #   proposal wins. This routes the dialog to the first phase instead of closing.
        #
        # Affected personas: skeptic, tire_kicker, competitor_user, aggressive
        #   (all express objections BEFORE entering a phase, so _state_before_objection
        #   gets saved as "greeting" which has no phase)
        if phase is None:
            # Get entry_state from flow config as fallback destination
            entry_state = None
            if hasattr(flow_config, 'variables'):
                entry_state = flow_config.variables.get("entry_state")
            elif hasattr(flow_config, 'get_variable'):
                entry_state = flow_config.get_variable("entry_state")

            if entry_state and entry_state in flow_config.states:
                # FIX: Propose entry_state with NORMAL priority (not LOW)
                # When objecting BEFORE entering any phase (e.g., from greeting),
                # we should route to entry_state rather than closing the dialog.
                #
                # Bug fixed: Priority.LOW lost to TransitionResolver's NORMAL
                # (agreement → close), causing 0% phase coverage for personas
                # who object early (skeptic, tire_kicker, competitor_user, aggressive).
                #
                # With NORMAL priority, both sources have equal priority.
                # ObjectionReturnSource runs before TransitionResolverSource
                # (priority_order 35 < 50), so its proposal wins on equal priority.
                blackboard.propose_transition(
                    next_state=entry_state,
                    priority=Priority.NORMAL,  # FIX: NORMAL instead of LOW
                    reason_code="objection_return_to_entry_state",
                    source_name=self.name,
                    metadata={
                        "from_state": self.OBJECTION_STATE,
                        "to_state": entry_state,
                        "trigger_intent": ctx.current_intent,
                        "original_saved_state": saved_state,
                        "reason": "saved_state_has_no_phase",
                        "mechanism": "objection_return_fallback",
                    }
                )
                self._log_contribution(
                    transition=entry_state,
                    reason=f"Fallback to entry_state: saved_state '{saved_state}' has no phase"
                )
                logger.debug(
                    f"ObjectionReturnSource: proposing entry_state fallback",
                    extra={
                        "saved_state": saved_state,
                        "entry_state": entry_state,
                        "reason": "no_phase",
                        "priority": "NORMAL",  # FIX: Changed from LOW
                    }
                )
            else:
                # No entry_state available - delegate to TransitionResolver
                self._log_contribution(
                    reason=f"Saved state '{saved_state}' has no phase, no entry_state fallback. "
                           f"Delegating to TransitionResolver."
                )
                logger.debug(
                    f"ObjectionReturnSource: no fallback available",
                    extra={
                        "saved_state": saved_state,
                        "reason": "no_phase_no_entry_state",
                        "will_delegate_to": "TransitionResolverSource",
                    }
                )
            return

        # Propose transition with HIGH priority
        # This wins over NORMAL priority YAML transitions
        blackboard.propose_transition(
            next_state=saved_state,
            priority=Priority.HIGH,
            reason_code="objection_return_to_phase",
            source_name=self.name,
            metadata={
                "from_state": self.OBJECTION_STATE,
                "to_state": saved_state,
                "trigger_intent": ctx.current_intent,
                "target_phase": phase,
                "mechanism": "objection_return",
            }
        )

        self._log_contribution(
            transition=saved_state,
            reason=f"Return to saved state after positive intent: "
                   f"{ctx.current_intent} → {saved_state} (phase: {phase})"
        )

        logger.info(
            f"ObjectionReturnSource: proposing return transition",
            extra={
                "from_state": self.OBJECTION_STATE,
                "to_state": saved_state,
                "intent": ctx.current_intent,
                "phase": phase,
            }
        )
