# src/blackboard/sources/disambiguation.py

"""
Disambiguation Knowledge Source for Dialogue Blackboard System.

Detects when the classifier signals disambiguation_needed and proposes
a blocking "ask_clarification" action on the Blackboard.

combinable=False ensures that no transitions are applied while the bot
is asking the user to clarify their intent.
"""

from typing import TYPE_CHECKING
import logging

from ..knowledge_source import KnowledgeSource
from ..enums import Priority
from src.blackboard.sources.pilot_survey_answer_gate import (
    latest_pilot_survey_signal,
    should_defer_to_pilot_router,
)

if TYPE_CHECKING:
    from ..blackboard import DialogueBlackboard

logger = logging.getLogger(__name__)


class DisambiguationSource(KnowledgeSource):
    """
    Knowledge Source for disambiguation.

    Responsibility:
        - Detect intent == "disambiguation_needed"
        - Propose "ask_clarification" action with HIGH priority, combinable=False
        - Pass disambiguation options/question in metadata for bot.py response path

    combinable=False blocks ALL transitions via ConflictResolver,
    keeping the bot in the current state while asking the clarification question.
    CRITICAL-priority actions (escalation, rejection) still win over HIGH.
    """

    def __init__(self, name: str = "DisambiguationSource"):
        super().__init__(name)

    def should_contribute(self, blackboard: 'DialogueBlackboard') -> bool:
        if not self._enabled:
            return False
        return blackboard.current_intent == "disambiguation_needed"

    def contribute(self, blackboard: 'DialogueBlackboard') -> None:
        if not self._enabled:
            return

        ctx = blackboard.get_context()
        pilot_signal = latest_pilot_survey_signal(blackboard, ctx)
        if pilot_signal and should_defer_to_pilot_router(blackboard.current_intent, pilot_signal):
            self._log_contribution(
                reason=(
                    "pilot_survey authoritative routing: "
                    f"skip disambiguation for intent={blackboard.current_intent}, "
                    f"routing_state={pilot_signal.get('routing_state')}"
                )
            )
            return

        envelope = ctx.context_envelope

        # Read typed fields from ContextEnvelope (populated by Builder from classification_result)
        options = []
        question = ""
        if envelope is not None:
            options = envelope.disambiguation_options
            question = envelope.disambiguation_question

        if not options:
            logger.warning(
                "DisambiguationSource: empty disambiguation_options on envelope, "
                "skipping ask_clarification proposal",
            )
            return

        blackboard.propose_action(
            action="ask_clarification",
            priority=Priority.HIGH,
            combinable=False,
            reason_code="disambiguation_needed",
            source_name=self.name,
            metadata={
                "disambiguation_options": options,
                "disambiguation_question": question,
            },
        )

        self._log_contribution(
            action="ask_clarification",
            reason=f"disambiguation_needed ({len(options)} options)",
        )
