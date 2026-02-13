# src/blackboard/sources/phase_exhausted.py

"""
Phase Exhausted Knowledge Source for Dialogue Blackboard System.

Offers options menu when dialog is stuck in a phase without progress.
Replaces ConversationGuard check 6 (phase_exhausted → TIER_2) by moving
the decision inside the Blackboard pipeline (Principle 3.2).

Fires in exclusive window: [phase_exhaust_threshold, stall_soft_threshold).
Above this window, StallGuardSource handles escalation.

Priority interactions:
    - DisambiguationSource (HIGH, combinable=False) always wins
    - TransitionResolver (NORMAL transition) + PhaseExhausted (NORMAL action,
      combinable=True) → both apply; bot.py sees next_state changed →
      generates normal response, skips options
    - StallGuardSource fires at higher threshold; PhaseExhausted doesn't fire
"""

from typing import TYPE_CHECKING
import logging

from ..knowledge_source import KnowledgeSource
from ..enums import Priority
from src.feature_flags import flags

if TYPE_CHECKING:
    from ..blackboard import DialogueBlackboard

logger = logging.getLogger(__name__)


class PhaseExhaustedSource(KnowledgeSource):
    """
    Offers options menu when phase exhausted without progress.

    Priority: NORMAL (43 in registry order)
        - Before StallGuardSource (45) — options offered before forced ejection
        - After IntentProcessorSource (40) — intent processing happens first

    Fires only in exclusive window [phase_exhaust_threshold, stall_soft_threshold)
    to avoid overlap with StallGuardSource.

    Thread Safety:
        Thread-safe — only reads from configuration and context,
        proposes changes through the blackboard.
    """

    def __init__(self, name: str = "PhaseExhaustedSource", enabled: bool = True):
        super().__init__(name)
        self._enabled = enabled

    def should_contribute(self, blackboard: 'DialogueBlackboard') -> bool:
        """
        Quick check: should we offer options menu?

        Fires when:
        - Feature flag enabled
        - consecutive_same_state >= phase_exhaust_threshold
        - consecutive_same_state < stall_soft_threshold (exclusive window)
        - No progress (not is_progressing and not has_extracted_data)
        - State is not terminal (max_turns > 0)

        This is O(1) — fast checks only.
        """
        if not self._enabled or not flags.is_enabled("phase_exhausted_source"):
            return False

        ctx = blackboard.get_context()
        envelope = ctx.context_envelope
        if envelope is None:
            return False

        consecutive = getattr(envelope, 'consecutive_same_state', 0)
        max_turns = ctx.state_config.get("max_turns_in_state", 0)

        # Skip terminal/disabled states (same guard as StallGuardSource)
        if max_turns <= 0:
            return False

        phase_threshold = ctx.state_config.get("phase_exhaust_threshold", 3)

        # Only fire in exclusive window: [effective_threshold, stall_soft_threshold)
        # Above this window, StallGuardSource handles escalation
        stall_soft = max(max_turns - 1, 3)
        # Clamp phase_threshold to guarantee non-empty window [threshold, stall_soft)
        effective_threshold = min(phase_threshold, stall_soft - 1)
        if consecutive < effective_threshold or consecutive >= stall_soft:
            return False

        # Only fire when there's no progress (same condition as old Guard check 6)
        is_progressing = getattr(envelope, 'is_progressing', False)
        has_data = getattr(envelope, 'has_extracted_data', False)
        return not is_progressing and not has_data

    def contribute(self, blackboard: 'DialogueBlackboard') -> None:
        """
        Propose offer_options action.

        combinable=True allows coexistence with transitions — bot.py resolves:
        - If transition happened (next_state changed) → normal response
        - If no transition → show options menu
        """
        if not self._enabled:
            return

        ctx = blackboard.get_context()
        consecutive = getattr(ctx.context_envelope, 'consecutive_same_state', 0) if ctx.context_envelope else 0
        max_turns = ctx.state_config.get("max_turns_in_state", 0)
        phase_threshold = ctx.state_config.get("phase_exhaust_threshold", 3)
        # Use same clamping as should_contribute() for consistent logging
        stall_soft = max(max_turns - 1, 3)
        effective_threshold = min(phase_threshold, stall_soft - 1)

        logger.info(
            f"PhaseExhaustedSource: offer_options in '{ctx.state}' "
            f"(consecutive={consecutive}, threshold={effective_threshold}, max={max_turns})"
        )

        blackboard.propose_action(
            action="offer_options",
            priority=Priority.NORMAL,
            combinable=True,
            reason_code="phase_exhausted_options",
            source_name=self.name,
            metadata={
                "options_type": "phase_exhausted",
                "from_state": ctx.state,
                "consecutive_turns": consecutive,
                "phase_threshold": phase_threshold,
                "max_turns_in_state": max_turns,
            },
        )

        self._log_contribution(
            action="offer_options",
            reason=f"phase_exhausted: {consecutive}/{max_turns} turns in {ctx.state}"
        )
