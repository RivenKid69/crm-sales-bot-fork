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
from src.yaml_config.constants import (
    OBJECTION_INTENTS,
    MAX_TOTAL_OBJECTIONS,
    OBJECTION_RETURN_TRIGGERS,
)

if TYPE_CHECKING:
    from ..blackboard import DialogueBlackboard

logger = logging.getLogger(__name__)


# Threshold for forcing exit from handle_objection when stuck in objection loop
# If client gives N+ consecutive objections without positive response AND we came
# from a non-phase state (greeting), force exit to entry_state
OBJECTION_LOOP_ESCAPE_THRESHOLD = 3

# Phase-origin escape threshold: lower threshold for phase-origin states
# When saved_state HAS a phase (came from real flow state like bant_budget)
# and consecutive >= threshold, allow early escape back to phase state.
# Lower than OBJECTION_LOOP_ESCAPE_THRESHOLD because:
# - Phase-origin means dialog already started → more value to preserve
# - Busy personas (max_turns=8) exhaust turns before standard threshold (3)
PHASE_ORIGIN_ESCAPE_THRESHOLD = 2

# Total-based escape threshold: fire escape before objection_limit_reached
# objection_limit_reached fires at total >= MAX_TOTAL_OBJECTIONS (default: 5)
# We fire escape at total >= MAX_TOTAL_OBJECTIONS - 1 (default: 4) to ensure
# escape gets priority over limit when meta-intents break consecutive streak.
#
# FIX: Without this, meta-intents like request_brevity reset consecutive streak
# to 0 but total keeps accumulating. When total reaches MAX_TOTAL_OBJECTIONS,
# objection_limit_reached fires → soft_close with 0% coverage.
# With this threshold, escape fires one step earlier → entry_state.
OBJECTION_TOTAL_ESCAPE_THRESHOLD = MAX_TOTAL_OBJECTIONS - 1


class ObjectionReturnSource(KnowledgeSource):
    """
    Knowledge Source for returning to previous phase after objection handling.

    Responsibility:
        - Detect when objection is successfully handled (return intent from SSOT)
        - Propose transition back to saved state (_state_before_objection)
        - Preserve phase continuity in sales flow

    Design:
        When entering handle_objection from a phase state (e.g., bant_budget),
        the orchestrator saves that state in _state_before_objection.

        Return intents are loaded from constants.yaml SSOT via composed category
        objection_return_triggers = positive + price_related + all_questions.
        When the client expresses any of these intents,
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

    FIX for meta-intent streak breaking (total-based escape):
        Meta-intents like request_brevity reset consecutive objection streak to 0.
        This prevents consecutive-based escape (needs 3+) from ever firing.
        Meanwhile, total objections keep accumulating. When total reaches
        max_total_objections (5), objection_limit_reached fires → soft_close → 0%.
        Fix: Also trigger escape when total approaches limit (max_total - 1 = 4).
        This fires escape one step before limit, preventing soft_close.

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

        Total escape example (meta-intent breaks consecutive streak):
                Turn 1: objection_price  → consecutive=1, total=1
                Turn 2: objection_think  → consecutive=2, total=2
                Turn 3: request_brevity  → consecutive=0, total=2 (streak broken!)
                Turn 4: objection_trust  → consecutive=1, total=3
                Turn 5: objection_price  → consecutive=2, total=4
                        → total >= 4 (OBJECTION_TOTAL_ESCAPE_THRESHOLD)
                        → Total escape fires → entry_state ✓
                        (Without fix: consecutive never reaches 3, total reaches 5
                         → objection_limit_reached → soft_close → 0% coverage)
    """

    # Return intents loaded from constants.yaml (SSOT)
    # Composed category: positive + price_related + all_questions
    # Defined in constants.yaml → composed_categories → objection_return_triggers
    DEFAULT_RETURN_INTENTS: Set[str] = set(OBJECTION_RETURN_TRIGGERS)

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
                           Defaults to OBJECTION_RETURN_TRIGGERS from constants.yaml (SSOT).
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
           OR current intent is an objection AND we're stuck in loop
           (either consecutive >= threshold OR total approaching limit)

        The "stuck in loop" case handles personas like tire_kicker and aggressive
        who NEVER give positive intents and would otherwise get stuck in
        handle_objection until objection_limit_reached (soft_close).

        The "total approaching limit" case handles the meta-intent streak breaking
        bug where request_brevity resets consecutive streak but total keeps growing.

        This is O(1) - fast checks only.
        """
        if not self._enabled:
            return False

        # Check current state
        if blackboard.current_state != self.OBJECTION_STATE:
            return False

        # Check if we have a saved state to return to
        ctx = blackboard.get_context()
        saved_state = ctx.state_before_objection
        if not saved_state:
            return False

        # CASE 1: Positive/return intent triggers return to saved state
        if blackboard.current_intent in self._return_intents:
            return True

        # CASE 2: Objection-based escape - force exit when stuck
        # This fixes the zero phase coverage bug for tire_kicker/aggressive personas
        # who express only objection intents and never reach any phase.
        if blackboard.current_intent in OBJECTION_INTENTS:
            tracker = ctx.intent_tracker
            if tracker:
                # Check if saved state has no phase (came from greeting)
                # If we came from a phase state, we should wait for positive intent
                phase = ctx.state_to_phase.get(saved_state)

                # Only trigger escape if came from non-phase state
                if phase is None:
                    consecutive = tracker.objection_consecutive()
                    total = tracker.objection_total()

                    # CASE 2a: Consecutive-based escape (original)
                    # N+ consecutive objections without positive response
                    if consecutive >= OBJECTION_LOOP_ESCAPE_THRESHOLD:
                        return True

                    # CASE 2b: Total-based escape (FIX for meta-intent streak breaking)
                    # Meta-intents like request_brevity break consecutive streak
                    # but total keeps accumulating. Fire escape when total approaches
                    # limit to prevent objection_limit_reached → soft_close → 0% coverage.
                    if total >= OBJECTION_TOTAL_ESCAPE_THRESHOLD:
                        return True

                # CASE 3: Phase-origin early return
                # When saved_state HAS a phase (came from real flow state like bant_budget)
                # and consecutive >= PHASE_ORIGIN_ESCAPE_THRESHOLD, allow escape.
                # Lower threshold than non-phase origin because:
                # - Phase-origin means dialog already started → more value to preserve
                # - Busy personas (max_turns=8) exhaust turns before standard threshold (3)
                if phase is not None:
                    consecutive = tracker.objection_consecutive()
                    if consecutive >= PHASE_ORIGIN_ESCAPE_THRESHOLD:
                        return True

        return False

    def contribute(self, blackboard: 'DialogueBlackboard') -> None:
        """
        Propose transition back to saved state or force exit from objection loop.

        Algorithm:
        1. Verify all conditions (re-check for safety)
        2. Get saved state from _state_before_objection
        3. Check for objection escape conditions (stuck with no positive intent)
        4. Validate that target state exists
        5. Propose transition with appropriate priority
        6. Log contribution for debugging/monitoring

        Three modes of operation:
        A) POSITIVE INTENT → return to saved state (normal flow)
        B) CONSECUTIVE ESCAPE → force exit to entry_state when 3+ consecutive
        C) TOTAL ESCAPE → force exit when total approaching limit (meta-intent fix)

        Mode B fixes the zero phase coverage bug for tire_kicker/aggressive personas
        who express only objection intents (90%/70% probability) and never give
        positive responses.

        Mode C fixes the meta-intent streak breaking bug where request_brevity
        resets consecutive streak to 0 but total keeps accumulating. Without this,
        objection_limit_reached fires at total=max_total → soft_close → 0% coverage.
        With this, escape fires at total=max_total-1 → entry_state.
        """
        if not self._enabled:
            return

        # Re-check conditions for safety (in case called without should_contribute)
        if blackboard.current_state != self.OBJECTION_STATE:
            return

        ctx = blackboard.get_context()

        # Get the saved state from context snapshot
        saved_state = ctx.state_before_objection

        if not saved_state:
            self._log_contribution(
                reason="No saved state to return to"
            )
            return

        # Validate target state exists in flow config
        if ctx.valid_states and saved_state not in ctx.valid_states:
            logger.warning(
                f"ObjectionReturnSource: saved state '{saved_state}' "
                f"not found in flow config"
            )
            self._log_contribution(
                reason=f"Target state '{saved_state}' not in flow config"
            )
            return

        # Get phase info for metadata
        phase = ctx.state_to_phase.get(saved_state)

        # ====================================================================
        # CHECK FOR OBJECTION ESCAPE CONDITIONS
        # ====================================================================
        # FIX: Zero phase coverage bug for tire_kicker/aggressive personas
        #
        # Problem chain:
        #   1. Client starts with objection in greeting state
        #   2. _state_before_objection = "greeting" (no phase)
        #   3. Client keeps giving objection intents (90% probability for tire_kicker)
        #   4. ObjectionReturnSource only triggered on POSITIVE intent
        #   5. No positive intent → stuck in handle_objection → handle_objection loop
        #   6. Eventually objection_limit_reached → soft_close with 0% coverage
        #
        # Solution (two escape paths):
        #   A) Consecutive escape: N+ consecutive objections from non-phase state
        #      → force exit to entry_state (original fix)
        #   B) Total escape: total approaching limit from non-phase state
        #      → force exit to entry_state (new fix for meta-intent streak breaking)
        #
        # Case B fixes the secondary bug where meta-intents (request_brevity)
        # reset consecutive streak to 0 but total keeps accumulating.
        # Without this fix, consecutive never reaches 3 but total reaches 5
        # → objection_limit_reached → soft_close → 0% coverage.
        # ====================================================================
        is_objection_loop_escape = False
        is_phase_origin_escape = False
        consecutive_objections = 0
        total_objections = 0
        escape_trigger = None  # "consecutive", "total", or "phase_origin"

        if blackboard.current_intent in OBJECTION_INTENTS and phase is not None:
            # CASE C: Phase-origin early return → back to saved phase state (HIGH priority)
            tracker = ctx.intent_tracker
            if tracker:
                consecutive_objections = tracker.objection_consecutive()
                if consecutive_objections >= PHASE_ORIGIN_ESCAPE_THRESHOLD:
                    is_phase_origin_escape = True
                    escape_trigger = "phase_origin"
                    logger.info(
                        f"ObjectionReturnSource: phase-origin escape triggered",
                        extra={
                            "consecutive_objections": consecutive_objections,
                            "threshold": PHASE_ORIGIN_ESCAPE_THRESHOLD,
                            "saved_state": saved_state,
                            "target_phase": phase,
                            "current_intent": blackboard.current_intent,
                        }
                    )

        if blackboard.current_intent in OBJECTION_INTENTS and phase is None:
            tracker = ctx.intent_tracker
            if tracker:
                consecutive_objections = tracker.objection_consecutive()
                total_objections = tracker.objection_total()

                # CASE A: Consecutive-based escape (original)
                if consecutive_objections >= OBJECTION_LOOP_ESCAPE_THRESHOLD:
                    is_objection_loop_escape = True
                    escape_trigger = "consecutive"
                    logger.info(
                        f"ObjectionReturnSource: consecutive objection escape triggered",
                        extra={
                            "consecutive_objections": consecutive_objections,
                            "threshold": OBJECTION_LOOP_ESCAPE_THRESHOLD,
                            "saved_state": saved_state,
                            "current_intent": blackboard.current_intent,
                        }
                    )

                # CASE B: Total-based escape (FIX for meta-intent streak breaking)
                elif total_objections >= OBJECTION_TOTAL_ESCAPE_THRESHOLD:
                    is_objection_loop_escape = True
                    escape_trigger = "total"
                    logger.info(
                        f"ObjectionReturnSource: total objection escape triggered",
                        extra={
                            "total_objections": total_objections,
                            "threshold": OBJECTION_TOTAL_ESCAPE_THRESHOLD,
                            "consecutive_objections": consecutive_objections,
                            "saved_state": saved_state,
                            "current_intent": blackboard.current_intent,
                        }
                    )

        # Check if we should handle this as positive intent return
        is_positive_return = blackboard.current_intent in self._return_intents

        # If neither condition is met, delegate to other sources
        if not is_positive_return and not is_objection_loop_escape and not is_phase_origin_escape:
            self._log_contribution(
                reason=f"Intent {blackboard.current_intent} not in return_intents "
                       f"and not objection loop escape"
            )
            return

        # ====================================================================
        # HANDLE PHASE-ORIGIN ESCAPE (CASE C)
        # ====================================================================
        # When saved_state HAS a phase and consecutive objections >= threshold,
        # return to saved phase state with HIGH priority.
        if is_phase_origin_escape and phase is not None:
            blackboard.propose_transition(
                next_state=saved_state,
                priority=Priority.HIGH,
                reason_code="objection_phase_origin_escape",
                source_name=self.name,
                metadata={
                    "from_state": self.OBJECTION_STATE,
                    "to_state": saved_state,
                    "trigger_intent": ctx.current_intent,
                    "target_phase": phase,
                    "mechanism": "phase_origin_escape",
                    "consecutive_objections": consecutive_objections,
                }
            )
            self._log_contribution(
                transition=saved_state,
                reason=f"Phase-origin escape: {consecutive_objections} consecutive "
                       f"objections → return to {saved_state} (phase: {phase})"
            )
            return

        # ====================================================================
        # HANDLE NON-PHASE STATES (greeting, handle_objection)
        # ====================================================================
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
        # ENHANCEMENT: Objection loop escape also uses this path to force exit
        #   to entry_state when client gives N+ consecutive objections.
        #
        # Affected personas: skeptic, tire_kicker, competitor_user, aggressive
        #   (all express objections BEFORE entering a phase, so _state_before_objection
        #   gets saved as "greeting" which has no phase)
        if phase is None:
            # Get entry_state from flow config as fallback destination
            entry_state = None
            flow_dict = ctx.flow_config
            if isinstance(flow_dict, dict):
                variables = flow_dict.get("variables", {})
                if isinstance(variables, dict):
                    entry_state = variables.get("entry_state")

            # Backward-compatible fallback for tests/flows where ContextSnapshot.flow_config
            # omits variables in to_dict(), but FlowConfig object still has .variables.
            if not entry_state:
                flow_obj = getattr(blackboard, "_flow_config", None)
                flow_vars = getattr(flow_obj, "variables", None)
                if isinstance(flow_vars, dict):
                    entry_state = flow_vars.get("entry_state")

            if entry_state and entry_state in ctx.valid_states:
                # Determine reason for transition
                if is_objection_loop_escape and escape_trigger == "total":
                    reason_code = "objection_total_escape_to_entry_state"
                    mechanism = "objection_total_escape"
                    reason_str = (
                        f"Total objection escape: {total_objections} total "
                        f"objections (threshold: {OBJECTION_TOTAL_ESCAPE_THRESHOLD}) "
                        f"from non-phase state '{saved_state}' "
                        f"(consecutive: {consecutive_objections}, broken by meta-intents)"
                    )
                elif is_objection_loop_escape:
                    reason_code = "objection_loop_escape_to_entry_state"
                    mechanism = "objection_loop_escape"
                    reason_str = (
                        f"Objection loop escape: {consecutive_objections} consecutive "
                        f"objections from non-phase state '{saved_state}'"
                    )
                else:
                    reason_code = "objection_return_to_entry_state"
                    mechanism = "objection_return_fallback"
                    reason_str = f"Fallback to entry_state: saved_state '{saved_state}' has no phase"

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
                    reason_code=reason_code,
                    source_name=self.name,
                    metadata={
                        "from_state": self.OBJECTION_STATE,
                        "to_state": entry_state,
                        "trigger_intent": ctx.current_intent,
                        "original_saved_state": saved_state,
                        "reason": "saved_state_has_no_phase",
                        "mechanism": mechanism,
                        "is_objection_loop_escape": is_objection_loop_escape,
                        "escape_trigger": escape_trigger,
                        "consecutive_objections": consecutive_objections,
                        "total_objections": total_objections,
                    }
                )
                self._log_contribution(
                    transition=entry_state,
                    reason=reason_str
                )
                logger.debug(
                    f"ObjectionReturnSource: proposing entry_state",
                    extra={
                        "saved_state": saved_state,
                        "entry_state": entry_state,
                        "reason": "no_phase",
                        "priority": "NORMAL",
                        "mechanism": mechanism,
                        "is_objection_loop_escape": is_objection_loop_escape,
                        "escape_trigger": escape_trigger,
                        "consecutive_objections": consecutive_objections,
                        "total_objections": total_objections,
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
