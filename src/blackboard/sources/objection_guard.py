# src/blackboard/sources/objection_guard.py

from typing import Dict, Optional, Set
import logging

from ..knowledge_source import KnowledgeSource
from ..blackboard import DialogueBlackboard
from ..enums import Priority
from src.yaml_config.constants import OBJECTION_INTENTS

logger = logging.getLogger(__name__)


class ObjectionGuardSource(KnowledgeSource):
    """
    Knowledge Source for monitoring objection limits per persona.

    Responsibility:
        - Track consecutive and total objections
        - Apply persona-specific limits
        - Propose soft_close transition when limits exceeded
        - Propose objection_limit_reached action for appropriate messaging

    Persona limits (from constants.yaml):
        aggressive:      consecutive=5, total=8
        price_sensitive: consecutive=4, total=7
        skeptical:       consecutive=4, total=6
        busy:            consecutive=2, total=4
        default:         consecutive=3, total=5

    Design decision: When limit is reached, we propose BLOCKING action
    (combinable=False) because we want to stop normal processing and
    redirect to soft close.
    """

    # Default persona limits (loaded from constants.yaml in production)
    DEFAULT_PERSONA_LIMITS: Dict[str, Dict[str, int]] = {
        "aggressive": {"consecutive": 5, "total": 8},
        "price_sensitive": {"consecutive": 4, "total": 7},
        "skeptical": {"consecutive": 4, "total": 6},
        "busy": {"consecutive": 2, "total": 4},
        "analytical": {"consecutive": 4, "total": 6},
        "friendly": {"consecutive": 4, "total": 7},
        "default": {"consecutive": 3, "total": 5},
    }

    # Intents considered as objections (single source of truth)
    # Loaded from constants.yaml via src.yaml_config.constants
    DEFAULT_OBJECTION_INTENTS: Set[str] = set(OBJECTION_INTENTS)

    def __init__(
        self,
        persona_limits: Optional[Dict[str, Dict[str, int]]] = None,
        objection_intents: Optional[Set[str]] = None,
        name: str = "ObjectionGuardSource"
    ):
        """
        Initialize the objection guard source.

        Args:
            persona_limits: Dict mapping persona -> {consecutive, total} limits.
                           Defaults to DEFAULT_PERSONA_LIMITS.
            objection_intents: Set of intents considered as objections.
                              Defaults to DEFAULT_OBJECTION_INTENTS.
            name: Source name for logging
        """
        super().__init__(name)
        self._persona_limits = persona_limits or self.DEFAULT_PERSONA_LIMITS
        if objection_intents is None:
            self._objection_intents = set(self.DEFAULT_OBJECTION_INTENTS)
        else:
            self._objection_intents = set(objection_intents)

    @property
    def persona_limits(self) -> Dict[str, Dict[str, int]]:
        """Get the persona limits configuration."""
        return self._persona_limits

    @property
    def objection_intents(self) -> Set[str]:
        """Get the set of objection intents."""
        return self._objection_intents

    def should_contribute(self, blackboard: DialogueBlackboard) -> bool:
        """
        Quick check: is current intent an objection?

        We only need to check limits when an objection is detected.
        """
        if not self._enabled:
            return False

        return blackboard.current_intent in self._objection_intents

    def contribute(self, blackboard: DialogueBlackboard) -> None:
        """
        Check objection limits and propose soft_close if exceeded.

        Algorithm:
        1. Get persona from collected_data (default: "default")
        2. Get limits for persona
        3. Get consecutive and total objection counts from IntentTracker
        4. If either limit exceeded -> propose blocking action + transition
        """
        if not self._enabled:
            return

        ctx = blackboard.get_context()

        # Get persona (default if not detected)
        persona = ctx.persona
        if persona not in self._persona_limits:
            persona = "default"

        limits = self._persona_limits[persona]
        max_consecutive = limits["consecutive"]
        max_total = limits["total"]

        # Get objection counts from IntentTracker
        consecutive = ctx.objection_consecutive
        total = ctx.objection_total

        # Check if limits exceeded
        consecutive_exceeded = consecutive >= max_consecutive
        total_exceeded = total >= max_total

        if not consecutive_exceeded and not total_exceeded:
            # Within limits - let other sources handle the objection
            self._log_contribution(
                reason=f"Within limits: consecutive={consecutive}/{max_consecutive}, "
                       f"total={total}/{max_total} (persona={persona})"
            )
            return

        # Limits exceeded - propose blocking action and transition
        exceeded_reason = []
        if consecutive_exceeded:
            exceeded_reason.append(f"consecutive={consecutive}>={max_consecutive}")
        if total_exceeded:
            exceeded_reason.append(f"total={total}>={max_total}")

        reason_str = ", ".join(exceeded_reason)

        # Propose action with CRITICAL priority
        # Use combinable=True because we WANT the soft_close transition to happen
        # The CRITICAL priority ensures this action wins over other proposals
        blackboard.propose_action(
            action="objection_limit_reached",
            priority=Priority.CRITICAL,
            combinable=True,  # Allow transition to soft_close
            reason_code="objection_limit_exceeded",
            source_name=self.name,
            metadata={
                "persona": persona,
                "consecutive": consecutive,
                "total": total,
                "max_consecutive": max_consecutive,
                "max_total": max_total,
                "exceeded": exceeded_reason,
            }
        )

        # Propose transition to soft_close with CRITICAL priority
        blackboard.propose_transition(
            next_state="soft_close",
            priority=Priority.CRITICAL,
            reason_code="objection_limit_exceeded",
            source_name=self.name,
            metadata={
                "persona": persona,
                "trigger": reason_str,
            }
        )

        # ======================================================================
        # NOT A BUG: Infinite soft_close loop prevention mechanism
        # ======================================================================
        #
        # REPORTED CONCERN:
        #   "If soft_close.is_final=false in YAML, client can continue after
        #    soft_close, but ObjectionGuard still sees consecutive >= max,
        #    proposes soft_close again → infinite loop"
        #
        # WHY THIS CANNOT HAPPEN (defense in depth):
        #
        # LAYER 1: _objection_limit_final flag (set here)
        #   - This flag OVERRIDES the YAML is_final setting
        #   - state_machine.is_final() checks this flag (state_machine.py:741-745):
        #       if self.state == "soft_close" and collected_data.get("_objection_limit_final"):
        #           is_final_flag = True  # OVERRIDE!
        #   - Even if YAML says is_final=false, this flag makes it True
        #
        # LAYER 2: _should_skip_objection_recording() (blackboard.py:208-248)
        #   - BEFORE recording intent, checks if limit already reached
        #   - If consecutive >= max OR total >= max → skip recording
        #   - Counter stays at limit, doesn't grow to 3→6→9...
        #
        # LAYER 3: Bot behavior
        #   - is_final=True → bot terminates conversation
        #   - No more turns processed → no loop possible
        #
        # HOW IT WORKS:
        #   Turn N:   3rd objection → limit reached → soft_close + flag set
        #   Turn N+1: is_final() returns True (flag override) → conversation ends
        #
        # EVEN IF CONVERSATION CONTINUES (edge case):
        #   Turn N+1: objection_price intent
        #             _should_skip_objection_recording() → True → skip record
        #             consecutive still = 3 (not 4)
        #             ObjectionGuard proposes soft_close again
        #             But flag is ALREADY set → is_final=True → ends
        #
        # This is a COMPLETE defense mechanism, not a bug.
        # ======================================================================
        blackboard.propose_data_update(
            field="_objection_limit_final",
            value=True,
            source_name=self.name,
            reason_code="objection_limit_exceeded"
        )

        self._log_contribution(
            action="objection_limit_reached",
            transition="soft_close",
            reason=f"Objection limit exceeded for persona={persona}: {reason_str}"
        )

        logger.warning(
            f"Objection limit reached: persona={persona}, {reason_str}"
        )
