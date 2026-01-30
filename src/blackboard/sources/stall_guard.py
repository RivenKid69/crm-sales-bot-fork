# src/blackboard/sources/stall_guard.py

"""
Universal Stall Guard Knowledge Source for Dialogue Blackboard System.

Safety net: forces state transition when dialog is stuck in any state
for longer than max_turns_in_state.

Works for ANY state, ANY intent — no per-intent configuration needed.
New states automatically get protection via _base_phase inheritance.

Context-aware: for detour states (handle_objection), prefers returning
to saved origin state over generic fallback — preserving conversation context.

Defense-in-depth position:
- Softer mechanisms (is_stalled → nudge_progress) fire first at threshold=3
- Meta-intent escape transitions (A6) fire at turn 3 for greeting
- StallGuardSource fires later as hard ejection at per-state threshold
- Existing escape hatches (objection_loop_escape, turn_number_gte_3) remain
  as faster-exit mechanisms for specific cases

Root Causes Fixed:
    RC1: Greeting stuck — TTL at turn 4 (backup after A6 meta-intent transitions)
    RC2: handle_objection meta-intents — context-aware return to _state_before_objection
    RC3: Presentation stuck — TTL at turn 5 (after is_stalled nudge at turn 3)
    RC4: repair_overlay next_state=None — proposes real next_state via Proposal
"""

from typing import Optional, TYPE_CHECKING
import logging

from ..knowledge_source import KnowledgeSource
from ..enums import Priority
from src.feature_flags import flags

if TYPE_CHECKING:
    from ..blackboard import DialogueBlackboard
    from ..models import ContextSnapshot

logger = logging.getLogger(__name__)


class StallGuardSource(KnowledgeSource):
    """
    Universal safety net: forces state transition when dialog is stuck
    in any state for longer than max_turns_in_state.

    Priority: HIGH (45 in registry order)
        - After ObjectionReturnSource (35) — precise return on positive intents first
        - Before TransitionResolverSource (50) — safety net wins over YAML transitions
        - HIGH priority beats NORMAL from TransitionResolver

    Thread Safety:
        Thread-safe — only reads from configuration and context,
        proposes changes through the blackboard.
    """

    # Follow ObjectionReturnSource pattern — class constant for state name
    OBJECTION_STATE = "handle_objection"

    def __init__(self, name: str = "StallGuardSource", enabled: bool = True):
        super().__init__(name)
        self._enabled = enabled

    def should_contribute(self, blackboard: 'DialogueBlackboard') -> bool:
        """
        Quick check: should we force a state transition?

        Conditions (ALL must be true):
        1. Source is enabled (self._enabled)
        2. Feature flag universal_stall_guard is enabled
        3. Current state has max_turns_in_state > 0
        4. Consecutive turns in same state >= max_turns_in_state

        This is O(1) — fast checks only.
        """
        # Pattern: self._enabled first (base class contract)
        if not self._enabled:
            return False
        # Pattern: feature flag check (same as other flag-gated sources)
        if not flags.is_enabled("universal_stall_guard"):
            return False

        ctx = blackboard.get_context()
        max_turns = ctx.state_config.get("max_turns_in_state", 0)
        if max_turns <= 0:
            return False

        consecutive = self._get_consecutive_same_state(ctx)
        return consecutive >= max_turns

    def contribute(self, blackboard: 'DialogueBlackboard') -> None:
        """
        Propose forced transition to escape stalled state.

        Algorithm:
        1. Get context snapshot (immutable)
        2. Determine fallback state (context-aware for detour states)
        3. Propose transition with HIGH priority
        """
        if not self._enabled:
            return

        ctx = blackboard.get_context()
        fallback = self._get_fallback_state(ctx, blackboard)

        consecutive = self._get_consecutive_same_state(ctx)
        max_turns = ctx.state_config.get("max_turns_in_state", 0)

        logger.info(
            f"StallGuardSource: ejecting from '{ctx.state}' → '{fallback}' "
            f"(consecutive={consecutive}, max={max_turns})"
        )

        # Pattern: exact propose_transition signature from blackboard.py
        blackboard.propose_transition(
            next_state=fallback,
            priority=Priority.HIGH,
            reason_code="max_turns_in_state_exceeded",
            source_name=self.name,
            metadata={
                "from_state": ctx.state,
                "to_state": fallback,
                "consecutive_turns": consecutive,
                "max_turns_in_state": max_turns,
                "mechanism": "stall_guard",
            },
        )

        self._log_contribution(
            transition=fallback,
            reason=f"TTL exceeded: {consecutive}/{max_turns} turns in {ctx.state}"
        )

    def _get_consecutive_same_state(self, ctx: 'ContextSnapshot') -> int:
        """Read from context envelope (immutable snapshot)."""
        envelope = ctx.context_envelope
        if envelope is None:
            return 0
        return getattr(envelope, 'consecutive_same_state', 0)

    def _get_fallback_state(self, ctx: 'ContextSnapshot', blackboard: 'DialogueBlackboard') -> str:
        """
        Determine where to eject the dialog.

        Priority order:
        1. Saved return state (from detour states like handle_objection)
           → preserves conversation context (RC2 fix)
        2. YAML-configured max_turns_fallback (already template-resolved
           by ConfigLoader at load time — no runtime template resolution needed)
        3. Default: "close"
        """
        # Priority 1: saved return state for detour states (RC2 fix)
        saved_return = self._get_saved_return_state(ctx, blackboard)
        if saved_return:
            return saved_return

        # Priority 2: YAML fallback (templates already resolved by ConfigLoader)
        return ctx.state_config.get("max_turns_fallback", "close")

    def _get_saved_return_state(
        self, ctx: 'ContextSnapshot', blackboard: 'DialogueBlackboard'
    ) -> Optional[str]:
        """
        Check if current state is a detour with a saved origin state.

        Currently: handle_objection saves _state_before_objection when entered.
        When StallGuardSource ejects from handle_objection, it returns to
        the saved origin state instead of generic entry_state — preserving
        the conversation context that would otherwise be lost.

        Access pattern: blackboard._state_machine (private) — same pattern
        used by ObjectionReturnSource (objection_return.py lines 215, 283).
        """
        if ctx.state != self.OBJECTION_STATE:
            return None

        state_machine = getattr(blackboard, '_state_machine', None)
        if not state_machine:
            return None

        saved = getattr(state_machine, '_state_before_objection', None)
        if saved:
            logger.debug(
                f"StallGuardSource: found saved return state '{saved}' "
                f"for {self.OBJECTION_STATE}"
            )
        return saved
