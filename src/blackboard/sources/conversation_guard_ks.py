# src/blackboard/sources/conversation_guard_ks.py

"""
ConversationGuard Knowledge Source for Dialogue Blackboard System.

Wraps ConversationGuard as a Blackboard Knowledge Source, replacing the
external guard→fallback→defense-in-depth chain in bot.py.

Tier → Proposal Mapping:
    TIER_1 (rephrase)  → guard_rephrase     NORMAL  combinable=True   no transition
    TIER_2 (options)   → guard_offer_options HIGH    combinable=False  no transition
    TIER_3 (skip)      → guard_skip_phase   HIGH    combinable=True   skip_target
    TIER_4 (close)     → guard_soft_close   CRITICAL combinable=True  soft_close

Idempotency note: Guard.check() mutates internal detection state
(turn_count, history). This is acceptable — same pattern as
IntentTracker.record() in begin_turn(). Guard detection state is
orthogonal to state machine state. Guard is called exactly once
per turn by Orchestrator (orchestrator.py:269 loop).

Dual ownership: bot.py holds self.guard for record_progress() calls;
this KS holds the same instance for check() calls. Same pattern as
state_machine shared between bot.py and Orchestrator.
"""

from typing import Optional, Dict, Any, TYPE_CHECKING
import logging

from ..knowledge_source import KnowledgeSource
from ..enums import Priority
from src.feature_flags import flags

if TYPE_CHECKING:
    from ..blackboard import DialogueBlackboard
    from ..models import ContextSnapshot
    from src.conversation_guard import ConversationGuard
    from src.fallback_handler import FallbackHandler

logger = logging.getLogger(__name__)


# Tier → proposal mapping (constant, not per-instance)
TIER_MAP = {
    "fallback_tier_1": {
        "action": "guard_rephrase",
        "priority": Priority.NORMAL,
        "combinable": True,
        "has_transition": False,
    },
    "fallback_tier_2": {
        "action": "guard_offer_options",
        "priority": Priority.HIGH,
        "combinable": False,
        "has_transition": False,
    },
    "fallback_tier_3": {
        "action": "guard_skip_phase",
        "priority": Priority.HIGH,
        "combinable": True,
        "has_transition": True,
    },
    "soft_close": {
        "action": "guard_soft_close",
        "priority": Priority.CRITICAL,
        "combinable": True,
        "has_transition": True,
    },
}


class ConversationGuardSource(KnowledgeSource):
    """
    Wraps ConversationGuard as a Blackboard Knowledge Source.

    Replaces external guard→fallback→defense-in-depth chain in bot.py.

    Priority: 7 in registry order
        - After GoBackGuardSource (5) — go_back limits checked first
        - Before DisambiguationSource (8) — frustrated user needs escape, not more questions

    Thread Safety:
        Thread-safe — reads context from blackboard, delegates detection to Guard.
    """

    def __init__(
        self,
        name: str = "ConversationGuardSource",
        guard: Optional['ConversationGuard'] = None,
        fallback_handler: Optional['FallbackHandler'] = None,
        enabled: bool = True,
    ):
        super().__init__(name)
        self._enabled = enabled
        self._guard = guard
        self._fallback_handler = fallback_handler

        if guard is None:
            logger.warning(
                "ConversationGuardSource created without guard instance — "
                "will be inactive until guard is set"
            )

    def should_contribute(self, blackboard: 'DialogueBlackboard') -> bool:
        """
        Quick O(1) gate check.

        Returns False if:
        - Source is disabled
        - Feature flag conversation_guard_in_pipeline is off
        - Guard instance is not set
        """
        if not self._enabled:
            return False
        if not flags.is_enabled("conversation_guard_in_pipeline"):
            return False
        if self._guard is None:
            return False
        return True

    def contribute(self, blackboard: 'DialogueBlackboard') -> None:
        """
        Run ConversationGuard.check() and map tier to proposals.

        Reads user_message, frustration_level, collected_data, state,
        current_intent from blackboard context.
        """
        if not self._enabled or self._guard is None:
            return

        ctx = blackboard.get_context()

        # Read from ContextSnapshot
        state = ctx.state
        user_message = ctx.user_message
        frustration_level = ctx.frustration_level
        collected_data = dict(ctx.collected_data)
        current_intent = ctx.current_intent

        # Call guard detection
        can_continue, tier = self._guard.check(
            state=state,
            message=user_message,
            collected_data=collected_data,
            frustration_level=frustration_level,
            last_intent=current_intent,
        )

        if tier is None:
            # No intervention needed
            return

        # Map tier to proposal spec
        spec = TIER_MAP.get(tier)
        if spec is None:
            logger.warning(f"ConversationGuardSource: unknown tier '{tier}'")
            return

        action = spec["action"]
        priority = spec["priority"]
        combinable = spec["combinable"]
        has_transition = spec["has_transition"]

        # TIER_3 degradation: if no valid skip target, degrade to TIER_2 behavior
        skip_target = None
        if tier == "fallback_tier_3":
            skip_target = self._get_skip_target(ctx, collected_data)
            if skip_target is None:
                # Degrade to guard_offer_options (TIER_2 behavior)
                action = "guard_offer_options"
                priority = Priority.HIGH
                combinable = False
                has_transition = False
                tier = "fallback_tier_2"  # Update tier for metadata
                logger.info(
                    "ConversationGuardSource: TIER_3 degraded to TIER_2 "
                    "(no valid skip target)"
                )

        # TIER_4 transition target
        if tier == "soft_close":
            skip_target = "soft_close"

        # Propose action
        metadata = {
            "tier": tier,
            "can_continue": can_continue,
            "from_state": state,
            "frustration_level": frustration_level,
        }
        if skip_target:
            metadata["to_state"] = skip_target

        blackboard.propose_action(
            action=action,
            priority=priority,
            combinable=combinable,
            reason_code=f"conversation_guard_{tier}",
            source_name=self.name,
            metadata=metadata,
        )

        # Propose transition if needed
        if has_transition and skip_target:
            blackboard.propose_transition(
                next_state=skip_target,
                priority=priority,
                reason_code=f"conversation_guard_{tier}_transition",
                source_name=self.name,
                metadata=metadata,
            )

        self._log_contribution(
            action=action,
            transition=skip_target if has_transition and skip_target else None,
            reason=f"guard_{tier}: state={state}, frustration={frustration_level}"
        )

    def _get_skip_target(
        self,
        ctx: 'ContextSnapshot',
        collected_data: Dict[str, Any],
    ) -> Optional[str]:
        """
        Determine valid skip target for TIER_3.

        Uses FallbackHandler._find_valid_skip_target() if available,
        which walks the skip_map chain and validates required_data.

        Returns None if no valid target found (triggers degradation to TIER_2).
        """
        if self._fallback_handler is None:
            return None

        return self._fallback_handler._find_valid_skip_target(
            current_state=ctx.state,
            collected_data=collected_data,
        )
