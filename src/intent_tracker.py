"""
IntentTracker - единый источник истории интентов.

Отслеживает:
- Текущий и предыдущий интент
- Streak (подряд идущие одинаковые интенты)
- Totals (общее количество по интентам и категориям)
- Сериализация для контекста/логов

Контракт timing: record(intent, state) вызывается в начале apply_rules()
до вычисления условий.

Part of Phase 3: IntentTracker + RuleResolver (ARCHITECTURE_UNIFIED_PLAN.md)
"""

from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, field
from datetime import datetime

# CRITICAL FIX: Import INTENT_CATEGORIES from yaml_config/constants.py
# which loads them from constants.yaml (single source of truth)
# This ensures IntentTracker uses the complete, up-to-date list of intents
# including all 19 objection types, 24 positive signals, 18 questions, etc.
from src.yaml_config.constants import INTENT_CATEGORIES


@dataclass
class IntentRecord:
    """
    Record of a single intent occurrence.

    Attributes:
        intent: The intent name
        state: State when intent occurred
        timestamp: When the intent was recorded
        turn_number: Turn number when recorded
    """
    intent: str
    state: str
    timestamp: datetime = field(default_factory=datetime.now)
    turn_number: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "intent": self.intent,
            "state": self.state,
            "timestamp": self.timestamp.isoformat(),
            "turn_number": self.turn_number
        }


@dataclass
class IntentTracker:
    """
    Tracks intent history for the conversation.

    Provides:
    - Current and previous intent tracking
    - Streak counting (consecutive same intents)
    - Total counting (by intent and category)
    - State-aware tracking
    - Serialization for context/logs

    Example:
        tracker = IntentTracker()
        tracker.record("price_question", "spin_situation")
        tracker.record("price_question", "spin_situation")

        assert tracker.streak_count("price_question") == 2
        assert tracker.total_count("price_question") == 2
        assert tracker.category_total("question") == 2
    """

    # Current streak tracking
    _current_streak_intent: Optional[str] = None
    _current_streak_count: int = 0

    # History
    _history: List[IntentRecord] = field(default_factory=list)

    # Totals by intent
    _intent_totals: Dict[str, int] = field(default_factory=dict)

    # Totals by category
    _category_totals: Dict[str, int] = field(default_factory=dict)

    # Category streaks (consecutive intents in same category)
    _category_streak_counts: Dict[str, int] = field(default_factory=dict)
    _last_category: Optional[str] = None

    # Turn tracking
    _turn_number: int = 0

    @property
    def last_intent(self) -> Optional[str]:
        """Get the last recorded intent."""
        if not self._history:
            return None
        return self._history[-1].intent

    @property
    def prev_intent(self) -> Optional[str]:
        """Get the intent before the last one."""
        if len(self._history) < 2:
            return None
        return self._history[-2].intent

    @property
    def last_state(self) -> Optional[str]:
        """Get the state when last intent was recorded."""
        if not self._history:
            return None
        return self._history[-1].state

    @property
    def history_length(self) -> int:
        """Get the number of recorded intents."""
        return len(self._history)

    @property
    def turn_number(self) -> int:
        """Get current turn number."""
        return self._turn_number

    def record(self, intent: str, state: str) -> None:
        """
        Record an intent occurrence.

        This should be called at the start of apply_rules(),
        BEFORE evaluating any conditions.

        Args:
            intent: The intent name
            state: Current state when intent occurred
        """
        # Create record
        record = IntentRecord(
            intent=intent,
            state=state,
            turn_number=self._turn_number
        )
        self._history.append(record)

        # Update intent totals
        self._intent_totals[intent] = self._intent_totals.get(intent, 0) + 1

        # Update streak
        if intent == self._current_streak_intent:
            self._current_streak_count += 1
        else:
            self._current_streak_intent = intent
            self._current_streak_count = 1

        # Update category tracking
        self._update_categories(intent)

        # Increment turn number
        self._turn_number += 1

    def _update_categories(self, intent: str) -> None:
        """Update category totals and streaks for an intent."""
        # Find all categories this intent belongs to
        intent_categories = self._get_categories_for_intent(intent)

        # Update totals for matching categories
        for category in intent_categories:
            self._category_totals[category] = self._category_totals.get(category, 0) + 1

        # Update category streaks
        # Reset all category streaks first, then increment matching ones
        for category in INTENT_CATEGORIES.keys():
            if category in intent_categories:
                # Intent is in this category - increment or start streak
                self._category_streak_counts[category] = \
                    self._category_streak_counts.get(category, 0) + 1
            else:
                # Intent not in this category - reset streak
                self._category_streak_counts[category] = 0

    def _get_categories_for_intent(self, intent: str) -> Set[str]:
        """Get all categories an intent belongs to."""
        categories = set()
        for category, intents in INTENT_CATEGORIES.items():
            if intent in intents:
                categories.add(category)
        return categories

    def streak_count(self, intent: str) -> int:
        """
        Get consecutive count for a specific intent.

        Returns how many times this intent has been recorded
        consecutively (including the current one if it matches).

        Args:
            intent: Intent name to check

        Returns:
            Consecutive count (0 if intent is not current streak)
        """
        if intent == self._current_streak_intent:
            return self._current_streak_count
        return 0

    def total_count(self, intent: str) -> int:
        """
        Get total count for a specific intent.

        Args:
            intent: Intent name to check

        Returns:
            Total number of times this intent has been recorded
        """
        return self._intent_totals.get(intent, 0)

    def category_streak(self, category: str) -> int:
        """
        Get consecutive count for an intent category.

        Args:
            category: Category name to check

        Returns:
            Consecutive count of intents in this category
        """
        return self._category_streak_counts.get(category, 0)

    def category_total(self, category: str) -> int:
        """
        Get total count for an intent category.

        Args:
            category: Category name to check

        Returns:
            Total number of intents in this category
        """
        return self._category_totals.get(category, 0)

    def get_history(self, limit: int = 0) -> List[IntentRecord]:
        """
        Get intent history.

        Args:
            limit: Maximum number of records to return (0 = all)

        Returns:
            List of IntentRecord (most recent last)
        """
        if limit <= 0:
            return list(self._history)
        return list(self._history[-limit:])

    def get_recent_intents(self, limit: int = 5) -> List[str]:
        """
        Get list of recent intent names.

        Args:
            limit: Maximum number of intents to return

        Returns:
            List of intent names (most recent last)
        """
        records = self.get_history(limit)
        return [r.intent for r in records]

    def get_intents_by_category(self, category: str) -> List[IntentRecord]:
        """
        Get all records for intents in a specific category.

        Args:
            category: Category name

        Returns:
            List of IntentRecord for intents in this category
        """
        category_intents = set(INTENT_CATEGORIES.get(category, []))
        return [r for r in self._history if r.intent in category_intents]

    def get_state_history(self) -> List[str]:
        """Get list of states from history."""
        return [r.state for r in self._history]

    def reset(self) -> None:
        """Reset all tracking data."""
        self._current_streak_intent = None
        self._current_streak_count = 0
        self._history.clear()
        self._intent_totals.clear()
        self._category_totals.clear()
        self._category_streak_counts.clear()
        self._last_category = None
        self._turn_number = 0

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert tracker state to dictionary.

        Useful for logging, serialization, and context envelope.

        Returns:
            Dictionary with tracker state
        """
        return {
            "last_intent": self.last_intent,
            "prev_intent": self.prev_intent,
            "last_state": self.last_state,
            "current_streak": {
                "intent": self._current_streak_intent,
                "count": self._current_streak_count
            },
            "turn_number": self._turn_number,
            "history_length": len(self._history),
            "intent_totals": dict(self._intent_totals),
            "category_totals": dict(self._category_totals),
            "category_streaks": dict(self._category_streak_counts),
            "recent_intents": self.get_recent_intents(5),
        }

    def to_compact_dict(self) -> Dict[str, Any]:
        """
        Convert to compact dictionary (for logging).

        Returns:
            Minimal dictionary with key tracking info
        """
        return {
            "last": self.last_intent,
            "prev": self.prev_intent,
            "streak": (self._current_streak_intent, self._current_streak_count),
            "turn": self._turn_number,
            "objections": self.category_total("objection"),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "IntentTracker":
        """
        Create IntentTracker from dictionary.

        Useful for restoring state from serialized data.

        Args:
            data: Dictionary with tracker state

        Returns:
            New IntentTracker with restored state
        """
        tracker = cls()

        # Restore streak
        if "current_streak" in data:
            streak = data["current_streak"]
            tracker._current_streak_intent = streak.get("intent")
            tracker._current_streak_count = streak.get("count", 0)

        # Restore turn number
        tracker._turn_number = data.get("turn_number", 0)

        # Restore totals
        tracker._intent_totals = dict(data.get("intent_totals", {}))
        tracker._category_totals = dict(data.get("category_totals", {}))
        tracker._category_streak_counts = dict(data.get("category_streaks", {}))

        # Note: History is not restored (too verbose for serialization)
        # If full history is needed, store it separately

        return tracker

    # Backwards compatibility methods (for ObjectionFlowManager replacement)

    def objection_consecutive(self) -> int:
        """
        Get consecutive objection count.

        Replaces ObjectionFlowManager.consecutive_objections.
        """
        return self.category_streak("objection")

    def objection_total(self) -> int:
        """
        Get total objection count.

        Replaces ObjectionFlowManager.total_objections.
        """
        return self.category_total("objection")

    def is_objection(self, intent: str) -> bool:
        """Check if intent is an objection."""
        return intent in INTENT_CATEGORIES.get("objection", [])

    def is_positive(self, intent: str) -> bool:
        """Check if intent is positive."""
        return intent in INTENT_CATEGORIES.get("positive", [])

    def is_question(self, intent: str) -> bool:
        """Check if intent is a question."""
        return intent in INTENT_CATEGORIES.get("question", [])

    def is_spin_progress(self, intent: str) -> bool:
        """Check if intent indicates SPIN progress."""
        return intent in INTENT_CATEGORIES.get("spin_progress", [])

    def __repr__(self) -> str:
        return (
            f"IntentTracker(last={self.last_intent!r}, "
            f"streak={self._current_streak_count}, "
            f"turn={self._turn_number})"
        )


# Export all public components
__all__ = [
    "IntentTracker",
    "IntentRecord",
    "INTENT_CATEGORIES",
]
