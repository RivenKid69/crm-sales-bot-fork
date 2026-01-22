# src/blackboard/sources/price_question.py

"""
Price Question Knowledge Source for Dialogue Blackboard System.

This source handles price-related questions and ensures they are answered
WITHOUT blocking data_complete transitions (combinable=True).
"""

from typing import Set, Optional, TYPE_CHECKING
import logging

from ..knowledge_source import KnowledgeSource
from ..enums import Priority

if TYPE_CHECKING:
    from ..blackboard import DialogueBlackboard

logger = logging.getLogger(__name__)


class PriceQuestionSource(KnowledgeSource):
    """
    Knowledge Source for handling price-related questions.

    Responsibility:
        - Detect price-related intents
        - Propose "answer_with_pricing" action
        - Always combinable=True (allows state transitions to proceed)

    Intents handled:
        - price_question
        - pricing_details
        - cost_inquiry
        - discount_request
        - payment_terms
        - pricing_comparison
        - budget_question

    This source addresses the core problem: price questions should be answered
    WITHOUT blocking data_complete transitions.
    """

    # Default price-related intents (can be overridden from config)
    DEFAULT_PRICE_INTENTS: Set[str] = {
        "price_question",
        "pricing_details",
        "cost_inquiry",
        "discount_request",
        "payment_terms",
        "pricing_comparison",
        "budget_question",
    }

    def __init__(
        self,
        price_intents: Optional[Set[str]] = None,
        name: str = "PriceQuestionSource"
    ):
        """
        Initialize the price question source.

        Args:
            price_intents: Set of intents considered price-related.
                           Defaults to DEFAULT_PRICE_INTENTS.
            name: Source name for logging
        """
        super().__init__(name)
        self._price_intents = price_intents or self.DEFAULT_PRICE_INTENTS.copy()

    @property
    def price_intents(self) -> Set[str]:
        """Get the set of price-related intents."""
        return self._price_intents

    def add_price_intent(self, intent: str) -> None:
        """Add an intent to the price intents set."""
        self._price_intents.add(intent)

    def remove_price_intent(self, intent: str) -> None:
        """Remove an intent from the price intents set."""
        self._price_intents.discard(intent)

    def should_contribute(self, blackboard: 'DialogueBlackboard') -> bool:
        """
        Quick check: is current intent price-related?

        O(1) check against price intents set.

        Args:
            blackboard: The dialogue blackboard

        Returns:
            True if current intent is price-related, False otherwise
        """
        if not self._enabled:
            return False

        return blackboard.current_intent in self._price_intents

    def contribute(self, blackboard: 'DialogueBlackboard') -> None:
        """
        Propose answer_with_pricing action for price questions.

        Key design decision: combinable=True
        This allows the action to coexist with transitions (e.g., data_complete).
        The bot will answer the price question AND transition to the next phase.

        Args:
            blackboard: The dialogue blackboard to contribute to
        """
        if not self._enabled:
            return

        ctx = blackboard.get_context()
        intent = ctx.current_intent

        if intent not in self._price_intents:
            self._log_contribution(reason="Intent not price-related")
            return

        # Determine specific action based on intent
        if intent == "discount_request":
            action = "handle_discount_request"
        elif intent == "payment_terms":
            action = "explain_payment_terms"
        elif intent == "pricing_comparison":
            action = "compare_pricing"
        elif intent == "budget_question":
            action = "discuss_budget"
        else:
            action = "answer_with_pricing"

        # Check if we have pricing data available
        has_pricing = bool(ctx.collected_data.get("pricing_tier"))

        # Propose action with HIGH priority (but combinable!)
        blackboard.propose_action(
            action=action,
            priority=Priority.HIGH,
            combinable=True,  # KEY: Allows coexistence with transitions
            reason_code="price_question_priority",
            source_name=self.name,
            metadata={
                "original_intent": intent,
                "has_pricing_data": has_pricing,
            }
        )

        self._log_contribution(
            action=action,
            reason=f"Price intent detected: {intent}"
        )
