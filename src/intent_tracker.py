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

    # Objection handling lifecycle:
    # pending objections are marked as handled when the next non-objection intent appears.
    _pending_objections: int = 0
    _objections_handled: int = 0

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

        # Track handled objections across all dialog flows.
        if self.is_objection(intent):
            self._pending_objections += 1
        elif self._pending_objections > 0:
            self._objections_handled += self._pending_objections
            self._pending_objections = 0

    def advance_turn(self) -> None:
        """Advance turn counter unconditionally.

        Called once per turn by blackboard.begin_turn(), independent of record().
        Decoupled from record() so that skip logic (e.g. objection limit)
        cannot freeze the conversation-global turn counter.
        """
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
        self._pending_objections = 0
        self._objections_handled = 0

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
            "pending_objections": self._pending_objections,
            "objections_handled": self._objections_handled,
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
            "pending_objections": self._pending_objections,
            "objections_handled": self._objections_handled,
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
        tracker._pending_objections = int(data.get("pending_objections", 0))
        tracker._objections_handled = int(data.get("objections_handled", 0))

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

    def objection_handled_total(self) -> int:
        """Get total objections marked as handled."""
        return self._objections_handled

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

    # ==========================================================================
    # НОВЫЕ HELPER-МЕТОДЫ для 150+ интентов (26 категорий из constants.yaml)
    # ==========================================================================

    def is_in_category(self, intent: str, category: str) -> bool:
        """
        Universal method to check if intent belongs to a category.

        Args:
            intent: Intent name to check
            category: Category name (e.g., 'equipment_questions', 'tariff_questions')

        Returns:
            True if intent belongs to category
        """
        return intent in INTENT_CATEGORIES.get(category, [])

    # --- Вопросы об оборудовании (12 интентов) ---
    def is_equipment_question(self, intent: str) -> bool:
        """Check if intent is an equipment question."""
        return self.is_in_category(intent, "equipment_questions")

    def equipment_questions_total(self) -> int:
        """Get total count of equipment questions."""
        return self.category_total("equipment_questions")

    def equipment_questions_streak(self) -> int:
        """Get consecutive count of equipment questions."""
        return self.category_streak("equipment_questions")

    # --- Вопросы о тарифах (8 интентов) ---
    def is_tariff_question(self, intent: str) -> bool:
        """Check if intent is a tariff question."""
        return self.is_in_category(intent, "tariff_questions")

    def tariff_questions_total(self) -> int:
        """Get total count of tariff questions."""
        return self.category_total("tariff_questions")

    def tariff_questions_streak(self) -> int:
        """Get consecutive count of tariff questions."""
        return self.category_streak("tariff_questions")

    # --- Вопросы о ТИС (10 интентов) ---
    def is_tis_question(self, intent: str) -> bool:
        """Check if intent is a TIS question."""
        return self.is_in_category(intent, "tis_questions")

    def tis_questions_total(self) -> int:
        """Get total count of TIS questions."""
        return self.category_total("tis_questions")

    def tis_questions_streak(self) -> int:
        """Get consecutive count of TIS questions."""
        return self.category_streak("tis_questions")

    # --- Бизнес-сценарии (18 интентов) ---
    def is_business_scenario(self, intent: str) -> bool:
        """Check if intent is a business scenario question."""
        return self.is_in_category(intent, "business_scenarios")

    def business_scenarios_total(self) -> int:
        """Get total count of business scenario questions."""
        return self.category_total("business_scenarios")

    def business_scenarios_streak(self) -> int:
        """Get consecutive count of business scenario questions."""
        return self.category_streak("business_scenarios")

    # --- Технические проблемы (6 интентов) ---
    def is_technical_problem(self, intent: str) -> bool:
        """Check if intent is a technical problem."""
        return self.is_in_category(intent, "technical_problems")

    def technical_problems_total(self) -> int:
        """Get total count of technical problems."""
        return self.category_total("technical_problems")

    def technical_problems_streak(self) -> int:
        """Get consecutive count of technical problems."""
        return self.category_streak("technical_problems")

    # --- Разговорные/эмоциональные (10 интентов) ---
    def is_conversational(self, intent: str) -> bool:
        """Check if intent is conversational/emotional."""
        return self.is_in_category(intent, "conversational")

    def conversational_total(self) -> int:
        """Get total count of conversational intents."""
        return self.category_total("conversational")

    def conversational_streak(self) -> int:
        """Get consecutive count of conversational intents."""
        return self.category_streak("conversational")

    # --- Информативные интенты ---
    def is_informative(self, intent: str) -> bool:
        """Check if intent is informative (client providing data, not stuck)."""
        return self.is_in_category(intent, "informative")

    def informative_total(self) -> int:
        """Get total count of informative intents."""
        return self.category_total("informative")

    # --- Этапы покупки (8 интентов) ---
    def is_purchase_stage(self, intent: str) -> bool:
        """Check if intent is a purchase stage action."""
        return self.is_in_category(intent, "purchase_stages")

    def purchase_stages_total(self) -> int:
        """Get total count of purchase stage intents."""
        return self.category_total("purchase_stages")

    # --- Управление диалогом (8 интентов) ---
    def is_dialogue_control(self, intent: str) -> bool:
        """Check if intent is dialogue control."""
        return self.is_in_category(intent, "dialogue_control")

    def dialogue_control_total(self) -> int:
        """Get total count of dialogue control intents."""
        return self.category_total("dialogue_control")

    # --- Price-related (требуют ответа с ценой) ---
    def is_price_related(self, intent: str) -> bool:
        """Check if intent is price-related (requires price answer)."""
        return self.is_in_category(intent, "price_related")

    def price_related_total(self) -> int:
        """Get total count of price-related intents."""
        return self.category_total("price_related")

    # --- Негативные сигналы ---
    def is_negative(self, intent: str) -> bool:
        """Check if intent is negative (rejection/objection)."""
        return self.is_in_category(intent, "negative")

    def negative_total(self) -> int:
        """Get total count of negative intents."""
        return self.category_total("negative")

    def negative_streak(self) -> int:
        """Get consecutive count of negative intents."""
        return self.category_streak("negative")

    # --- Exit интенты (rejection/farewell) ---
    def is_exit(self, intent: str) -> bool:
        """Check if intent is an exit intent (rejection/farewell)."""
        return self.is_in_category(intent, "exit")

    def exit_total(self) -> int:
        """Get total count of exit intents."""
        return self.category_total("exit")

    def exit_streak(self) -> int:
        """Get consecutive count of exit intents."""
        return self.category_streak("exit")

    # ==========================================================================
    # АГРЕГИРОВАННЫЕ МЕТОДЫ для паттернов поведения
    # ==========================================================================

    def get_category_counts(self) -> Dict[str, int]:
        """
        Get all category totals for the conversation.

        Returns:
            Dictionary of category -> total count

        Example:
            >>> tracker.get_category_counts()
            {'objection': 2, 'equipment_questions': 3, 'positive': 5, ...}
        """
        return {
            category: self.category_total(category)
            for category in INTENT_CATEGORIES.keys()
        }

    def get_active_categories(self, min_count: int = 1) -> List[str]:
        """
        Get list of categories with at least min_count occurrences.

        Args:
            min_count: Minimum count to be considered active

        Returns:
            List of active category names
        """
        return [
            category
            for category, count in self.get_category_counts().items()
            if count >= min_count
        ]

    def has_pattern(self, category: str, min_total: int = 0, min_streak: int = 0) -> bool:
        """
        Check if conversation has a pattern for a category.

        Useful for detecting patterns like "client asked about equipment 3+ times"
        or "3 consecutive objections".

        Args:
            category: Category to check
            min_total: Minimum total count required
            min_streak: Minimum consecutive count required

        Returns:
            True if pattern is detected

        Example:
            >>> tracker.has_pattern("equipment_questions", min_total=3)
            True  # Client asked about equipment 3+ times

            >>> tracker.has_pattern("objection", min_streak=3)
            True  # 3 consecutive objections
        """
        if min_total > 0 and self.category_total(category) < min_total:
            return False
        if min_streak > 0 and self.category_streak(category) < min_streak:
            return False
        return min_total > 0 or min_streak > 0

    def __repr__(self) -> str:
        return (
            f"IntentTracker(last={self.last_intent!r}, "
            f"streak={self._current_streak_count}, "
            f"turn={self._turn_number})"
        )


def should_skip_objection_recording(
    intent: str,
    tracker: 'IntentTracker',
    collected_data: dict,
) -> bool:
    """
    Check if objection recording should be skipped (limit already reached).

    SINGLE SOURCE OF TRUTH — shared between Blackboard.begin_turn() and
    StateMachine.apply_rules() (deprecated legacy path).
    """
    from src.yaml_config.constants import OBJECTION_INTENTS, get_persona_objection_limits

    if intent not in OBJECTION_INTENTS:
        return False

    persona = collected_data.get("persona", "default")
    limits = get_persona_objection_limits(persona)

    consecutive = tracker.objection_consecutive()
    total = tracker.objection_total()

    if consecutive >= limits["consecutive"] or total >= limits["total"]:
        return True
    return False


# Export all public components
__all__ = [
    "IntentTracker",
    "IntentRecord",
    "INTENT_CATEGORIES",
    "should_skip_objection_recording",
]
