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
from src.yaml_config.constants import POSITIVE_INTENTS

if TYPE_CHECKING:
    from ..blackboard import DialogueBlackboard

logger = logging.getLogger(__name__)


class ObjectionReturnSource(KnowledgeSource):
    """
    Knowledge Source for returning to previous phase after objection handling.

    Responsibility:
        - Detect when objection is successfully handled (positive intent)
        - Propose transition back to saved state (_state_before_objection)
        - Preserve phase continuity in sales flow

    Design:
        When entering handle_objection from a phase state (e.g., bant_budget),
        the orchestrator saves that state in _state_before_objection.

        When the client shows agreement or interest (positive intent),
        this source proposes returning to that saved state with HIGH priority.

        This wins over YAML transitions (NORMAL priority) like:
            agreement: close  # Would lose phase forever

        The result is phase preservation:
            bant_budget → handle_objection → bant_budget (via this source)

        Instead of phase loss:
            bant_budget → handle_objection → close (via YAML)

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
    """

    # Positive intents that trigger return to previous phase
    # Loaded from constants.yaml via POSITIVE_INTENTS
    DEFAULT_RETURN_INTENTS: Set[str] = set(POSITIVE_INTENTS)

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
