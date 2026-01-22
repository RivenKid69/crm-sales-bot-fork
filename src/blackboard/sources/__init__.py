# src/blackboard/sources/__init__.py

"""
Knowledge Sources for Dialogue Blackboard System.

This package contains the built-in Knowledge Sources that contribute
proposals to the Blackboard during dialogue processing.

Each source has a single responsibility:
- PriceQuestionSource: Handles price-related questions with combinable actions
- DataCollectorSource: Tracks data completeness and proposes transitions
- ObjectionGuardSource: Monitors objection limits per persona (Этап 7)
- IntentProcessorSource: Maps intents to actions via rules (Этап 7)

Future sources (Этап 8):
- TransitionResolverSource: Handles intent-based state transitions
- EscalationSource: Detects escalation triggers for human handoff
"""

from .price_question import PriceQuestionSource
from .data_collector import DataCollectorSource
from .objection_guard import ObjectionGuardSource
from .intent_processor import IntentProcessorSource

__all__ = [
    "PriceQuestionSource",
    "DataCollectorSource",
    "ObjectionGuardSource",
    "IntentProcessorSource",
]
