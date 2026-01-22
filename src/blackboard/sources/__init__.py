# src/blackboard/sources/__init__.py

"""
Knowledge Sources for Dialogue Blackboard System.

This package contains the built-in Knowledge Sources that contribute
proposals to the Blackboard during dialogue processing.

Each source has a single responsibility:
- PriceQuestionSource: Handles price-related questions with combinable actions
- DataCollectorSource: Tracks data completeness and proposes transitions

Future sources (Этапы 7, 8):
- ObjectionGuardSource: Monitors objection limits per persona
- IntentProcessorSource: Maps intents to actions via rules
- TransitionResolverSource: Handles intent-based state transitions
- EscalationSource: Detects escalation triggers for human handoff
"""

from .price_question import PriceQuestionSource
from .data_collector import DataCollectorSource

__all__ = [
    "PriceQuestionSource",
    "DataCollectorSource",
]
