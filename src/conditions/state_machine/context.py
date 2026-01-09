"""
EvaluatorContext for StateMachine domain.

This module provides the domain-specific context for evaluating
conditions in the StateMachine (rules/transitions).

Part of Phase 2: StateMachine Domain (ARCHITECTURE_UNIFIED_PLAN.md)
"""

from typing import Dict, Any, Optional, List, Protocol, runtime_checkable
from dataclasses import dataclass, field


# SPIN phases and their order (from state_machine.py)
SPIN_PHASES = ["situation", "problem", "implication", "need_payoff"]

# Mapping of state names to SPIN phases
SPIN_STATE_TO_PHASE = {
    "spin_situation": "situation",
    "spin_problem": "problem",
    "spin_implication": "implication",
    "spin_need_payoff": "need_payoff",
}

# States that are part of SPIN flow
SPIN_STATES = set(SPIN_STATE_TO_PHASE.keys())

# Intent categories for tracking
INTENT_CATEGORIES = {
    "objection": [
        "objection_price",
        "objection_competitor",
        "objection_no_time",
        "objection_think",
    ],
    "positive": [
        "agreement",
        "demo_request",
        "callback_request",
        "contact_provided",
        "consultation_request",
        "situation_provided",
        "problem_revealed",
        "implication_acknowledged",
        "need_expressed",
        "info_provided",
        "question_features",
        "question_integrations",
        "comparison",
        "greeting",
        "gratitude",
    ],
    "question": [
        "price_question",
        "question_features",
        "question_integrations",
        "question_technical",
        "comparison",
    ],
    "spin_progress": [
        "situation_provided",
        "problem_revealed",
        "implication_acknowledged",
        "need_expressed",
    ],
}


@runtime_checkable
class IntentTrackerProtocol(Protocol):
    """
    Protocol for IntentTracker.

    This allows the context to work with either the real IntentTracker
    (Phase 3) or a mock/stub for testing.
    """

    @property
    def last_intent(self) -> Optional[str]:
        """Last recorded intent."""
        ...

    @property
    def prev_intent(self) -> Optional[str]:
        """Previous intent before last."""
        ...

    def streak_count(self, intent: str) -> int:
        """Get consecutive count for an intent."""
        ...

    def total_count(self, intent: str) -> int:
        """Get total count for an intent."""
        ...

    def category_streak(self, category: str) -> int:
        """Get consecutive count for an intent category."""
        ...

    def category_total(self, category: str) -> int:
        """Get total count for an intent category."""
        ...


@dataclass
class SimpleIntentTracker:
    """
    Simple implementation of IntentTrackerProtocol for testing.

    This provides a basic implementation that can be used in unit tests
    and for creating test contexts without the full IntentTracker.
    """
    _last_intent: Optional[str] = None
    _prev_intent: Optional[str] = None
    _intent_counts: Dict[str, int] = field(default_factory=dict)
    _intent_streaks: Dict[str, int] = field(default_factory=dict)
    _category_counts: Dict[str, int] = field(default_factory=dict)
    _category_streaks: Dict[str, int] = field(default_factory=dict)

    @property
    def last_intent(self) -> Optional[str]:
        return self._last_intent

    @property
    def prev_intent(self) -> Optional[str]:
        return self._prev_intent

    def streak_count(self, intent: str) -> int:
        return self._intent_streaks.get(intent, 0)

    def total_count(self, intent: str) -> int:
        return self._intent_counts.get(intent, 0)

    def category_streak(self, category: str) -> int:
        return self._category_streaks.get(category, 0)

    def category_total(self, category: str) -> int:
        return self._category_counts.get(category, 0)

    def set_intent_streak(self, intent: str, count: int) -> None:
        """Set streak count for an intent (for testing)."""
        self._intent_streaks[intent] = count

    def set_intent_total(self, intent: str, count: int) -> None:
        """Set total count for an intent (for testing)."""
        self._intent_counts[intent] = count

    def set_category_streak(self, category: str, count: int) -> None:
        """Set streak count for a category (for testing)."""
        self._category_streaks[category] = count

    def set_category_total(self, category: str, count: int) -> None:
        """Set total count for a category (for testing)."""
        self._category_counts[category] = count

    def record(self, intent: str) -> None:
        """Record an intent (simple implementation)."""
        self._prev_intent = self._last_intent
        self._last_intent = intent

        # Update total count
        self._intent_counts[intent] = self._intent_counts.get(intent, 0) + 1

        # Update streak - reset all others, increment this one
        for key in self._intent_streaks:
            if key != intent:
                self._intent_streaks[key] = 0
        self._intent_streaks[intent] = self._intent_streaks.get(intent, 0) + 1

        # Update category counts/streaks
        for category, intents in INTENT_CATEGORIES.items():
            if intent in intents:
                self._category_counts[category] = self._category_counts.get(category, 0) + 1
                self._category_streaks[category] = self._category_streaks.get(category, 0) + 1
            else:
                self._category_streaks[category] = 0


@dataclass
class EvaluatorContext:
    """
    Context for evaluating conditions in StateMachine domain.

    Contains all data needed to evaluate rules and transitions,
    including collected data, state information, and intent history.

    Attributes:
        collected_data: Data collected about the client during conversation
        state: Current dialogue state name
        turn_number: Current turn number in the dialogue (0-indexed)
        spin_phase: Current SPIN phase if in SPIN flow (situation, problem, etc.)
        is_spin_state: Whether current state is part of SPIN flow
        current_intent: The intent being processed
        prev_intent: Previous intent
        intent_tracker: IntentTracker for counting/streaks
        missing_required_data: List of required fields not yet collected
        config: Optional state configuration from SALES_STATES
    """
    # Base context fields (from BaseContext protocol)
    collected_data: Dict[str, Any] = field(default_factory=dict)
    state: str = ""
    turn_number: int = 0

    # StateMachine-specific fields
    spin_phase: Optional[str] = None
    is_spin_state: bool = False
    current_intent: str = ""
    prev_intent: Optional[str] = None
    intent_tracker: Optional[IntentTrackerProtocol] = None
    missing_required_data: List[str] = field(default_factory=list)
    config: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        """Validate and compute derived fields."""
        if self.turn_number < 0:
            raise ValueError("turn_number cannot be negative")

        # Compute is_spin_state if not set
        if not self.is_spin_state and self.state in SPIN_STATES:
            self.is_spin_state = True

        # Compute spin_phase if not set and in SPIN state
        if not self.spin_phase and self.state in SPIN_STATE_TO_PHASE:
            self.spin_phase = SPIN_STATE_TO_PHASE[self.state]

    @classmethod
    def from_state_machine(
        cls,
        state_machine: Any,
        current_intent: str,
        config: Optional[Dict[str, Any]] = None
    ) -> "EvaluatorContext":
        """
        Create context from StateMachine instance.

        This factory method extracts all necessary data from the
        StateMachine and creates a properly initialized context.

        Args:
            state_machine: StateMachine instance
            current_intent: Intent being processed
            config: Optional state configuration (from SALES_STATES)

        Returns:
            Initialized EvaluatorContext
        """
        state = state_machine.state
        collected_data = getattr(state_machine, 'collected_data', {})
        spin_phase = getattr(state_machine, 'spin_phase', None)

        # Compute missing required data
        missing = []
        if config:
            required = config.get("required_data", [])
            missing = [f for f in required if not collected_data.get(f)]

        # Get intent tracker if available
        intent_tracker = getattr(state_machine, 'intent_tracker', None)
        prev_intent = getattr(state_machine, 'last_intent', None)

        return cls(
            collected_data=collected_data.copy() if collected_data else {},
            state=state,
            turn_number=getattr(state_machine, 'turn_number', 0),
            spin_phase=spin_phase,
            is_spin_state=state in SPIN_STATES,
            current_intent=current_intent,
            prev_intent=prev_intent,
            intent_tracker=intent_tracker,
            missing_required_data=missing,
            config=config
        )

    @classmethod
    def create_test_context(
        cls,
        collected_data: Dict[str, Any] = None,
        state: str = "greeting",
        turn_number: int = 0,
        current_intent: str = "",
        intent_tracker: Optional[IntentTrackerProtocol] = None,
        missing_required_data: List[str] = None,
        config: Optional[Dict[str, Any]] = None
    ) -> "EvaluatorContext":
        """
        Factory method to create a test context with defaults.

        This is the recommended way to create contexts for unit tests
        as it provides sensible defaults and allows selective overrides.

        Args:
            collected_data: Optional data to include
            state: Optional state name (default: "greeting")
            turn_number: Optional turn number
            current_intent: Optional intent being processed
            intent_tracker: Optional tracker for intents
            missing_required_data: Optional list of missing fields
            config: Optional state configuration

        Returns:
            A new EvaluatorContext instance
        """
        # Create simple tracker if none provided
        if intent_tracker is None:
            intent_tracker = SimpleIntentTracker()

        return cls(
            collected_data=collected_data or {},
            state=state,
            turn_number=turn_number,
            current_intent=current_intent,
            intent_tracker=intent_tracker,
            missing_required_data=missing_required_data or [],
            config=config
        )

    def has_field(self, field_name: str) -> bool:
        """Check if a field exists in collected_data."""
        return bool(self.collected_data.get(field_name))

    def has_any_field(self, field_names: List[str]) -> bool:
        """Check if any of the specified fields exist."""
        return any(self.has_field(name) for name in field_names)

    def has_all_fields(self, field_names: List[str]) -> bool:
        """Check if all of the specified fields exist."""
        return all(self.has_field(name) for name in field_names)

    def get_field(self, field_name: str, default: Any = None) -> Any:
        """Get a field value from collected_data with default."""
        return self.collected_data.get(field_name, default)

    def get_intent_streak(self, intent: str) -> int:
        """Get consecutive count for an intent from tracker."""
        if self.intent_tracker:
            return self.intent_tracker.streak_count(intent)
        return 0

    def get_intent_total(self, intent: str) -> int:
        """Get total count for an intent from tracker."""
        if self.intent_tracker:
            return self.intent_tracker.total_count(intent)
        return 0

    def get_category_streak(self, category: str) -> int:
        """Get consecutive count for intent category from tracker."""
        if self.intent_tracker:
            return self.intent_tracker.category_streak(category)
        return 0

    def get_category_total(self, category: str) -> int:
        """Get total count for intent category from tracker."""
        if self.intent_tracker:
            return self.intent_tracker.category_total(category)
        return 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert context to dictionary representation."""
        return {
            "collected_data": self.collected_data,
            "state": self.state,
            "turn_number": self.turn_number,
            "spin_phase": self.spin_phase,
            "is_spin_state": self.is_spin_state,
            "current_intent": self.current_intent,
            "prev_intent": self.prev_intent,
            "missing_required_data": self.missing_required_data,
        }

    def __repr__(self) -> str:
        return (
            f"EvaluatorContext(state={self.state!r}, "
            f"intent={self.current_intent!r}, "
            f"turn={self.turn_number}, "
            f"spin_phase={self.spin_phase!r})"
        )


# Export all public components
__all__ = [
    "EvaluatorContext",
    "SimpleIntentTracker",
    "IntentTrackerProtocol",
    "SPIN_PHASES",
    "SPIN_STATE_TO_PHASE",
    "SPIN_STATES",
    "INTENT_CATEGORIES",
]
