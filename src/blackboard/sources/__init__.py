# src/blackboard/sources/__init__.py

"""
Knowledge Sources for Dialogue Blackboard System.

This package contains the built-in Knowledge Sources that contribute
proposals to the Blackboard during dialogue processing.

Each source has a single responsibility:
- PriceQuestionSource: Handles price-related questions with combinable actions
- DataCollectorSource: Tracks data completeness and proposes transitions
- ObjectionGuardSource: Monitors objection limits per persona (Этап 7)
- ObjectionReturnSource: Returns to previous phase after objection handling
- IntentProcessorSource: Maps intents to actions via rules (Этап 7)
- TransitionResolverSource: Handles intent-based state transitions (Этап 8)
- EscalationSource: Detects escalation triggers for human handoff (Этап 8)
"""

from .price_question import PriceQuestionSource
from .data_collector import DataCollectorSource
from .objection_guard import ObjectionGuardSource
from .objection_return import ObjectionReturnSource
from .intent_processor import IntentProcessorSource
from .transition_resolver import TransitionResolverSource
from .escalation import EscalationSource

__all__ = [
    "PriceQuestionSource",
    "DataCollectorSource",
    "ObjectionGuardSource",
    "ObjectionReturnSource",
    "IntentProcessorSource",
    "TransitionResolverSource",
    "EscalationSource",
]
