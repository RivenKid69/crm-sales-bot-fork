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

        Two-tier threshold:
        - Hard (unconditional): consecutive >= max_turns_in_state
        - Soft (conditional): consecutive >= max(max_turns - 1, 3),
          only when NOT progressing AND no data extracted this turn.

        This is O(1) — fast checks only.
        """
        if not self._enabled:
            return False
        if not flags.is_enabled("universal_stall_guard"):
            return False

        ctx = blackboard.get_context()
        max_turns = ctx.state_config.get("max_turns_in_state", 0)
        if max_turns <= 0:
            return False

        consecutive = self._get_consecutive_same_state(ctx)

        # Hard threshold: unconditional (existing behavior)
        if consecutive >= max_turns:
            # Exemption: clear positive signals must NOT trigger stall eject
            # (contact_provided/demo_request/callback_request are progress, not stalls)
            progress_intents = {"contact_provided", "demo_request", "callback_request", "payment_confirmation"}
            if ctx.current_intent in progress_intents:
                return False
            return True

        # Soft threshold: max_turns - 1, but at least 3.
        # Only when NOT progressing AND no data extracted this turn.
        soft_threshold = max(max_turns - 1, 3)
        if consecutive >= soft_threshold:
            envelope = ctx.context_envelope
            is_progressing = getattr(envelope, 'is_progressing', False) if envelope else False
            has_data = getattr(envelope, 'has_extracted_data', False) if envelope else False
            return not is_progressing and not has_data

        return False

    def contribute(self, blackboard: 'DialogueBlackboard') -> None:
        """
        Propose forced transition (and optionally action) to escape stalled state.

        Two-tier: hard (HIGH) at max_turns, soft (NORMAL) below.
        With stall_guard_dual_proposal flag, also proposes action
        to prevent blocking by other sources, ConversationGuard preemption,
        DialoguePolicy override, and self-loop fallback.
        """
        if not self._enabled:
            return

        ctx = blackboard.get_context()
        fallback = self._get_fallback_state(ctx, blackboard)
        consecutive = self._get_consecutive_same_state(ctx)
        max_turns = ctx.state_config.get("max_turns_in_state", 0)

        # Two-tier: hard (HIGH) at max_turns, soft (NORMAL) below
        if consecutive >= max_turns:
            priority = Priority.HIGH
            reason_code = "max_turns_in_state_exceeded"
            mechanism = "stall_guard_hard"
            action_name = "stall_guard_eject"
        else:
            priority = Priority.NORMAL
            reason_code = "stall_soft_progression"
            mechanism = "stall_guard_soft"
            action_name = "stall_guard_nudge"

        logger.info(
            f"StallGuardSource: {mechanism} from '{ctx.state}' → '{fallback}' "
            f"(consecutive={consecutive}, max={max_turns})"
        )

        # Dual propose — action + transition (gated by feature flag)
        # Pattern follows ObjectionGuardSource: combinable=True allows own transition through.
        # Priority matches transition priority for consistent resolution.
        if flags.is_enabled("stall_guard_dual_proposal"):
            blackboard.propose_action(
                action=action_name,
                priority=priority,
                combinable=True,
                reason_code=reason_code,
                source_name=self.name,
                metadata={
                    "from_state": ctx.state,
                    "to_state": fallback,
                    "consecutive_turns": consecutive,
                    "max_turns_in_state": max_turns,
                    "mechanism": mechanism,
                },
            )

        blackboard.propose_transition(
            next_state=fallback,
            priority=priority,
            reason_code=reason_code,
            source_name=self.name,
            metadata={
                "from_state": ctx.state,
                "to_state": fallback,
                "consecutive_turns": consecutive,
                "max_turns_in_state": max_turns,
                "mechanism": mechanism,
            },
        )

        self._log_contribution(
            transition=fallback,
            reason=f"{mechanism}: {consecutive}/{max_turns} turns in {ctx.state}"
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
        2. Terminal states present — eject to soft_close, not close
           (autonomous_closing has terminal_states; max_turns_fallback resolves to "close"
           via {{next_phase_state}} template, which is wrong here)
        3. YAML-configured max_turns_fallback (already template-resolved
           by ConfigLoader at load time — no runtime template resolution needed)
        4. Default: "close"
        """
        # Priority 1: saved return state for detour states (RC2 fix)
        saved_return = self._get_saved_return_state(ctx)
        if saved_return:
            return saved_return

        # Priority 2: if state has terminal_states — eject to soft_close (not close)
        # max_turns_fallback for autonomous_closing resolves to "close" from {{next_phase_state}},
        # but with terminal states present we should soft-close instead
        if ctx.state_config.get("terminal_states"):
            return "soft_close"

        # Priority 3: YAML fallback (templates already resolved by ConfigLoader)
        return ctx.state_config.get("max_turns_fallback", "close")

    def _get_saved_return_state(
        self, ctx: 'ContextSnapshot'
    ) -> Optional[str]:
        """
        Check if current state is a detour with a saved origin state.

        Currently: handle_objection saves _state_before_objection when entered.
        When StallGuardSource ejects from handle_objection, it returns to
        the saved origin state instead of generic entry_state — preserving
        the conversation context that would otherwise be lost.

        Access pattern: uses ctx.state_before_objection from ContextSnapshot
        (encapsulation-safe — no private-attr access).
        """
        if ctx.state != self.OBJECTION_STATE:
            return None

        saved = ctx.state_before_objection
        if saved:
            logger.debug(
                f"StallGuardSource: found saved return state '{saved}' "
                f"for {self.OBJECTION_STATE}"
            )
        return saved
