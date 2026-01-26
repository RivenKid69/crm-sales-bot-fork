# src/blackboard/sources/escalation.py

"""
Escalation Knowledge Source for Dialogue Blackboard System.

This source detects situations requiring human intervention and proposes
escalation actions that BLOCK other processing (combinable=False).
"""

from typing import Optional, Set, TYPE_CHECKING
import logging

from ..knowledge_source import KnowledgeSource
from ..enums import Priority

# FIX: Import categories from centralized constants (Single Source of Truth)
# This ensures EscalationSource stays synchronized with constants.yaml
from src.yaml_config.constants import INTENT_CATEGORIES

if TYPE_CHECKING:
    from ..blackboard import DialogueBlackboard

logger = logging.getLogger(__name__)


def _get_category_intents(category: str) -> Set[str]:
    """
    Get intents for a category from INTENT_CATEGORIES.

    Falls back to empty set if category not found.
    """
    intents = INTENT_CATEGORIES.get(category, [])
    return set(intents) if intents else set()


class EscalationSource(KnowledgeSource):
    """
    Knowledge Source for human escalation triggers.

    Responsibility:
        - Detect situations requiring human intervention
        - Propose escalation action when triggers are met
        - Block all other processing (combinable=False)

    Escalation triggers:
        1. Explicit request: user asks for human/manager
        2. Frustration threshold: repeated failures or angry sentiment
        3. Repeated misunderstandings: multiple "unclear" intents
        4. Sensitive topics: legal, compliance, complaints
        5. High-value lead: detected enterprise/large deal

    Based on enterprise chatbot best practices:
    - Human escalation is critical for user satisfaction
    - Should be triggered proactively, not just reactively

    FIX: Intent categories are now loaded from constants.yaml (Single Source of Truth)
    instead of being hardcoded. This ensures synchronization across the system.
    Categories used: escalation, frustration, sensitive (defined in constants.yaml)
    """

    # FIX: Load from constants.yaml instead of hardcoding
    # This ensures synchronization with IntentTracker category_streak
    EXPLICIT_ESCALATION_INTENTS: Set[str] = _get_category_intents("escalation")
    FRUSTRATION_INTENTS: Set[str] = _get_category_intents("frustration")
    SENSITIVE_INTENTS: Set[str] = _get_category_intents("sensitive")

    # Fallback values if categories are missing from YAML (for backwards compatibility)
    _FALLBACK_ESCALATION = {
        "request_human", "speak_to_manager", "talk_to_person", "need_help",
        "not_a_bot", "real_person", "human_please", "escalate",
    }
    _FALLBACK_FRUSTRATION = {
        "frustrated", "angry", "complaint", "this_is_useless",
        "not_helpful", "waste_of_time",
    }
    _FALLBACK_SENSITIVE = {
        "legal_question", "compliance_question", "formal_complaint",
        "refund_request", "contract_dispute", "data_deletion", "gdpr_request",
    }

    @classmethod
    def _ensure_intents_loaded(cls) -> None:
        """Ensure intent sets are populated, using fallbacks if needed."""
        if not cls.EXPLICIT_ESCALATION_INTENTS:
            logger.warning("escalation category not found in constants.yaml, using fallback")
            cls.EXPLICIT_ESCALATION_INTENTS = cls._FALLBACK_ESCALATION

        if not cls.FRUSTRATION_INTENTS:
            logger.warning("frustration category not found in constants.yaml, using fallback")
            cls.FRUSTRATION_INTENTS = cls._FALLBACK_FRUSTRATION

        if not cls.SENSITIVE_INTENTS:
            logger.warning("sensitive category not found in constants.yaml, using fallback")
            cls.SENSITIVE_INTENTS = cls._FALLBACK_SENSITIVE

    def __init__(
        self,
        frustration_threshold: int = 3,
        misunderstanding_threshold: int = 4,
        high_value_threshold: int = 100,  # company_size threshold
        name: str = "EscalationSource"
    ):
        """
        Initialize the escalation source.

        Args:
            frustration_threshold: Number of frustration signals to trigger escalation
            misunderstanding_threshold: Number of "unclear" intents to trigger escalation
            high_value_threshold: Company size to consider high-value lead
            name: Source name for logging
        """
        super().__init__(name)

        # FIX: Ensure intent categories are loaded from constants.yaml
        self._ensure_intents_loaded()

        self._frustration_threshold = frustration_threshold
        self._misunderstanding_threshold = misunderstanding_threshold
        self._high_value_threshold = high_value_threshold

    def _get_escalation_state(self, ctx) -> str:
        """
        Determine escalation state for current flow.

        Resolution order:
        1. entry_points.escalation (if defined and exists in states)
        2. Fallback to 'soft_close' (exists in all flows via _base/states.yaml)

        Args:
            ctx: ContextSnapshot from blackboard

        Returns:
            State name to use for escalation transition
        """
        flow_config = ctx.flow_config
        entry_points = flow_config.get("entry_points", {})
        states = flow_config.get("states", {})

        # Try entry_points.escalation first
        escalation_state = entry_points.get("escalation")
        if escalation_state and escalation_state in states:
            return escalation_state

        # Fallback to soft_close (exists in all flows)
        if "soft_close" in states:
            return "soft_close"

        # Ultimate fallback (log warning)
        logger.warning(
            f"No escalation state found. entry_points.escalation={escalation_state}, "
            f"soft_close exists={('soft_close' in states)}, available states={list(states.keys())[:5]}"
        )
        return "soft_close"

    def should_contribute(self, blackboard: 'DialogueBlackboard') -> bool:
        """
        Quick check: any escalation signals present?
        """
        if not self._enabled:
            return False

        intent = blackboard.current_intent

        # Always check for explicit escalation requests
        if intent in self.EXPLICIT_ESCALATION_INTENTS:
            return True

        # Always check for sensitive topics
        if intent in self.SENSITIVE_INTENTS:
            return True

        # Always check for frustration signals
        if intent in self.FRUSTRATION_INTENTS:
            return True

        # Check for repeated misunderstandings
        ctx = blackboard.get_context()
        unclear_count = ctx.intent_tracker.total_count("unclear")
        if unclear_count >= self._misunderstanding_threshold - 1:  # About to exceed
            return True

        return False

    def contribute(self, blackboard: 'DialogueBlackboard') -> None:
        """
        Check escalation triggers and propose if needed.

        Priority order:
        1. Explicit request -> immediate escalation
        2. Sensitive topic -> immediate escalation
        3. Frustration threshold -> escalation
        4. Misunderstanding threshold -> escalation
        5. High-value lead + complex question -> optional escalation
        """
        ctx = blackboard.get_context()
        intent = ctx.current_intent

        escalation_reason = None
        escalation_priority = Priority.HIGH

        # Check explicit escalation request
        if intent in self.EXPLICIT_ESCALATION_INTENTS:
            escalation_reason = "explicit_request"
            escalation_priority = Priority.CRITICAL  # Highest priority

        # Check sensitive topics
        elif intent in self.SENSITIVE_INTENTS:
            escalation_reason = "sensitive_topic"
            escalation_priority = Priority.CRITICAL

        # Check frustration signals
        elif intent in self.FRUSTRATION_INTENTS:
            frustration_count = ctx.intent_tracker.category_total("frustration")
            if frustration_count >= self._frustration_threshold:
                escalation_reason = "frustration_threshold"

        # Check repeated misunderstandings
        if not escalation_reason:
            unclear_count = ctx.intent_tracker.total_count("unclear")
            if unclear_count >= self._misunderstanding_threshold:
                escalation_reason = "misunderstanding_threshold"

        # Check high-value lead with complex question
        if not escalation_reason:
            company_size = ctx.collected_data.get("company_size")
            if company_size and isinstance(company_size, int):
                if company_size >= self._high_value_threshold:
                    # High-value lead - check if complex question
                    complex_intents = {"custom_integration", "enterprise_features", "sla_question"}
                    if intent in complex_intents:
                        escalation_reason = "high_value_complex"

        if not escalation_reason:
            self._log_contribution(reason="No escalation triggers met")
            return

        # Propose BLOCKING escalation action
        blackboard.propose_action(
            action="escalate_to_human",
            priority=escalation_priority,
            combinable=False,  # BLOCKING: stops all other processing
            reason_code=f"escalation_{escalation_reason}",
            source_name=self.name,
            metadata={
                "trigger": escalation_reason,
                "intent": intent,
                "turn_number": ctx.turn_number,
            }
        )

        # Determine escalation state dynamically based on flow config
        escalation_state = self._get_escalation_state(ctx)

        # Propose transition to escalation state
        blackboard.propose_transition(
            next_state=escalation_state,
            priority=escalation_priority,
            reason_code=f"escalation_{escalation_reason}",
            source_name=self.name,
            metadata={
                "trigger": escalation_reason,
                "resolved_state": escalation_state,
            }
        )

        self._log_contribution(
            action="escalate_to_human",
            transition=escalation_state,
            reason=f"Escalation triggered: {escalation_reason}"
        )

        logger.info(
            f"Human escalation triggered: reason={escalation_reason}, "
            f"intent={intent}, turn={ctx.turn_number}, state={escalation_state}"
        )
