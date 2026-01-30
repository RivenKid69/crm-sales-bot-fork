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
        envelope = ctx.context_envelope

        # Extract options/question from classification result (via context_envelope)
        classification_result = {}
        if envelope is not None:
            classification_result = getattr(envelope, 'classification_result', None) or {}

        options = classification_result.get("disambiguation_options", [])
        question = classification_result.get("disambiguation_question", "")

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
