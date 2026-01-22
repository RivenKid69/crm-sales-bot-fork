# src/blackboard/enums.py

"""
Enums for Dialogue Blackboard System.

This module defines the enumeration types used throughout the Blackboard architecture:
- Priority: Priority levels for proposals (conflict resolution)
- ProposalType: Types of proposals that Knowledge Sources can make
"""

from enum import IntEnum, Enum, auto


class Priority(IntEnum):
    """
    Priority levels for proposals.
    Lower numeric value = higher priority.

    Usage:
        CRITICAL - blocking actions (rejection, escalation)
        HIGH - important actions (price questions, objection handling)
        NORMAL - standard actions (intent processing, data collection)
        LOW - fallback actions (continue, default transitions)
    """
    CRITICAL = 0  # Highest priority - blocks everything
    HIGH = 1      # High priority - important actions
    NORMAL = 2    # Normal priority - standard processing
    LOW = 3       # Low priority - fallbacks

    def __lt__(self, other):
        if isinstance(other, Priority):
            return self.value < other.value
        return NotImplemented

    def __le__(self, other):
        if isinstance(other, Priority):
            return self.value <= other.value
        return NotImplemented

    def __gt__(self, other):
        if isinstance(other, Priority):
            return self.value > other.value
        return NotImplemented

    def __ge__(self, other):
        if isinstance(other, Priority):
            return self.value >= other.value
        return NotImplemented


class ProposalType(Enum):
    """
    Types of proposals that Knowledge Sources can make.

    ACTION - propose to execute an action (generate response, handle objection)
    TRANSITION - propose to transition to another state
    DATA_UPDATE - propose to update collected_data
    FLAG_SET - propose to set a flag (for on_enter actions)
    """
    ACTION = auto()
    TRANSITION = auto()
    DATA_UPDATE = auto()
    FLAG_SET = auto()
