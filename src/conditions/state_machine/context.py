"""
EvaluatorContext for StateMachine domain.

This module provides the domain-specific context for evaluating
conditions in the StateMachine (rules/transitions).

Part of Phase 2: StateMachine Domain (ARCHITECTURE_UNIFIED_PLAN.md)
"""

from typing import Dict, Any, Optional, List, Protocol, runtime_checkable, TYPE_CHECKING
from dataclasses import dataclass, field

# Import INTENT_CATEGORIES from the single source of truth
from src.intent_tracker import INTENT_CATEGORIES

# Import SPIN constants for auto-computing phase from state
from src.yaml_config.constants import (
    SPIN_STATES,
    SPIN_PHASES,
    # Objection limits from YAML (single source of truth)
    MAX_CONSECUTIVE_OBJECTIONS,
    MAX_TOTAL_OBJECTIONS,
)

if TYPE_CHECKING:
    from src.config_loader import FlowConfig

# Create reverse mapping: state -> phase
_STATE_TO_PHASE = {v: k for k, v in SPIN_STATES.items()}

# Alias for backward compatibility (tests may use SPIN_STATE_TO_PHASE)
SPIN_STATE_TO_PHASE = _STATE_TO_PHASE


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
        current_phase: Current phase name (from FlowConfig)
        is_phase_state: Whether current state is a phase state
        current_intent: The intent being processed
        prev_intent: Previous intent
        intent_tracker: IntentTracker for counting/streaks
        missing_required_data: List of required fields not yet collected
        config: Optional state configuration
        flow_config: Optional FlowConfig for phase info

        # === Context-aware fields (from ContextEnvelope) ===
        frustration_level: Client frustration level (0-5)
        is_stuck: Whether dialogue is stuck
        has_oscillation: Whether dialogue is oscillating
        momentum_direction: Momentum direction (positive/negative/neutral)
        momentum: Momentum score (-1 to +1)
        engagement_level: Engagement level (high/medium/low)
        repeated_question: Repeated question intent (or None)
        confidence_trend: Confidence trend (increasing/stable/decreasing)
        total_objections: Total objections in conversation
        has_breakthrough: Whether breakthrough was detected
        turns_since_breakthrough: Turns since breakthrough
        guard_intervention: Guard intervention type (or None)
    """
    # Base context fields (from BaseContext protocol)
    collected_data: Dict[str, Any] = field(default_factory=dict)
    state: str = ""
    turn_number: int = 0

    # StateMachine-specific fields
    current_phase: Optional[str] = None
    is_phase_state: bool = False
    current_intent: str = ""
    prev_intent: Optional[str] = None
    intent_tracker: Optional[IntentTrackerProtocol] = None
    missing_required_data: List[str] = field(default_factory=list)
    config: Optional[Dict[str, Any]] = None
    flow_config: Optional["FlowConfig"] = None

    # === Context-aware fields (from ContextEnvelope) ===
    frustration_level: int = 0
    is_stuck: bool = False
    has_oscillation: bool = False
    momentum_direction: str = "neutral"
    momentum: float = 0.0
    engagement_level: str = "medium"
    repeated_question: Optional[str] = None
    confidence_trend: str = "stable"
    total_objections: int = 0
    has_breakthrough: bool = False
    turns_since_breakthrough: Optional[int] = None
    guard_intervention: Optional[str] = None
    # FIX: Add tone field for busy/aggressive persona handling
    tone: Optional[str] = None
    # Count of unclear intents
    unclear_count: int = 0
    # Secondary intents (from RefinementPipeline via ContextEnvelope)
    secondary_intents: List[str] = field(default_factory=list)

    # === Persona-aware objection limits ===
    persona: str = ""

    # === DAG-specific fields ===
    is_dag_mode: bool = False
    active_branches: List[str] = field(default_factory=list)
    current_branch: Optional[str] = None
    dag_depth: int = 0  # Depth of fork nesting
    in_fork: bool = False
    fork_id: Optional[str] = None

    # === Objection limits (from YAML config, single source of truth) ===
    # These are populated from constants.yaml via constants.py
    max_consecutive_objections: int = field(default_factory=lambda: MAX_CONSECUTIVE_OBJECTIONS)
    max_total_objections: int = field(default_factory=lambda: MAX_TOTAL_OBJECTIONS)

    def __post_init__(self):
        """Validate and compute derived fields."""
        if self.turn_number < 0:
            raise ValueError("turn_number cannot be negative")

        # Auto-compute current_phase from state if not provided
        # FUNDAMENTAL FIX: Use flow_config.get_phase_for_state() as primary source
        # This ensures custom flows (BANT, MEDDIC, etc.) work correctly
        if self.current_phase is None:
            if self.flow_config is not None:
                # Use FlowConfig's canonical phase resolution (handles ALL flows)
                self.current_phase = self.flow_config.get_phase_for_state(self.state)
            elif self.state in _STATE_TO_PHASE:
                # Fallback to hardcoded SPIN mapping for backward compatibility
                self.current_phase = _STATE_TO_PHASE[self.state]

        # Compute is_phase_state from current_phase
        if not self.is_phase_state and self.current_phase is not None:
            self.is_phase_state = True

        # Auto-resolve persona-specific objection limits
        from src.yaml_config.constants import PERSONA_OBJECTION_LIMITS
        if (self.persona
            and self.persona in PERSONA_OBJECTION_LIMITS
            and self.max_consecutive_objections == MAX_CONSECUTIVE_OBJECTIONS
            and self.max_total_objections == MAX_TOTAL_OBJECTIONS):
            limits = PERSONA_OBJECTION_LIMITS[self.persona]
            self.max_consecutive_objections = limits["consecutive"]
            self.max_total_objections = limits["total"]

    # Legacy aliases for backward compatibility
    @property
    def spin_phase(self) -> Optional[str]:
        """Legacy alias for current_phase."""
        return self.current_phase

    @property
    def is_spin_state(self) -> bool:
        """Legacy alias for is_phase_state."""
        return self.is_phase_state

    @classmethod
    def from_state_machine(
        cls,
        state_machine: Any,
        current_intent: str,
        config: Optional[Dict[str, Any]] = None,
        context_envelope: Any = None
    ) -> "EvaluatorContext":
        """
        Create context from StateMachine instance.

        This factory method extracts all necessary data from the
        StateMachine and creates a properly initialized context.

        Args:
            state_machine: StateMachine instance
            current_intent: Intent being processed
            config: Optional state configuration (from SALES_STATES)
            context_envelope: Optional ContextEnvelope with rich context

        Returns:
            Initialized EvaluatorContext
        """
        state = state_machine.state
        collected_data = getattr(state_machine, 'collected_data', {})
        flow_config = getattr(state_machine, '_flow', None)

        # FUNDAMENTAL FIX: Use flow_config.get_phase_for_state() as primary source
        # This ensures custom flows (BANT, MEDDIC, etc.) work correctly
        current_phase = getattr(state_machine, 'current_phase', None)
        if current_phase is None:
            current_phase = getattr(state_machine, 'spin_phase', None)
        if current_phase is None and flow_config is not None:
            # Use FlowConfig's canonical phase resolution
            current_phase = flow_config.get_phase_for_state(state)

        # Compute missing required data
        missing = []
        if config:
            required = config.get("required_data", [])
            missing = [f for f in required if not collected_data.get(f)]

        # Get intent tracker if available
        intent_tracker = getattr(state_machine, 'intent_tracker', None)
        prev_intent = getattr(state_machine, 'last_intent', None)

        # Extract context-aware fields from envelope if provided
        frustration_level = 0
        is_stuck = False
        has_oscillation = False
        momentum_direction = "neutral"
        momentum = 0.0
        engagement_level = "medium"
        repeated_question = None
        confidence_trend = "stable"
        total_objections = 0
        has_breakthrough = False
        turns_since_breakthrough = None
        guard_intervention = None
        tone = None

        if context_envelope is not None:
            frustration_level = getattr(context_envelope, 'frustration_level', 0)
            is_stuck = getattr(context_envelope, 'is_stuck', False)
            has_oscillation = getattr(context_envelope, 'has_oscillation', False)
            momentum_direction = getattr(context_envelope, 'momentum_direction', "neutral")
            momentum = getattr(context_envelope, 'momentum', 0.0)
            engagement_level = getattr(context_envelope, 'engagement_level', "medium")
            repeated_question = getattr(context_envelope, 'repeated_question', None)
            confidence_trend = getattr(context_envelope, 'confidence_trend', "stable")
            total_objections = getattr(context_envelope, 'total_objections', 0)
            has_breakthrough = getattr(context_envelope, 'has_breakthrough', False)
            turns_since_breakthrough = getattr(context_envelope, 'turns_since_breakthrough', None)
            guard_intervention = getattr(context_envelope, 'guard_intervention', None)
            # FIX: Extract tone for busy/aggressive persona handling
            tone = getattr(context_envelope, 'tone', None)

        # Extract secondary intents from envelope
        secondary_intents = []
        if context_envelope is not None:
            secondary_intents = getattr(context_envelope, 'secondary_intents', []) or []

        # Extract DAG context if available
        is_dag_mode = False
        active_branches = []
        current_branch = None
        dag_depth = 0
        in_fork = False
        fork_id = None

        dag_ctx = getattr(state_machine, '_dag_context', None)
        if dag_ctx is not None:
            is_dag_mode = dag_ctx.is_dag_mode
            active_branches = dag_ctx.active_branch_ids
            dag_depth = len(dag_ctx.fork_stack)
            in_fork = dag_depth > 0
            fork_id = dag_ctx.current_fork

        # Extract objection limits from state_machine if explicitly set
        max_consecutive = getattr(
            state_machine, 'max_consecutive_objections', MAX_CONSECUTIVE_OBJECTIONS
        )
        max_total = getattr(
            state_machine, 'max_total_objections', MAX_TOTAL_OBJECTIONS
        )

        return cls(
            collected_data=collected_data.copy() if collected_data else {},
            state=state,
            turn_number=getattr(state_machine, 'turn_number', 0),
            current_phase=current_phase,
            is_phase_state=current_phase is not None,
            current_intent=current_intent,
            prev_intent=prev_intent,
            intent_tracker=intent_tracker,
            missing_required_data=missing,
            config=config,
            flow_config=flow_config,
            # Context-aware fields
            frustration_level=frustration_level,
            is_stuck=is_stuck,
            has_oscillation=has_oscillation,
            momentum_direction=momentum_direction,
            momentum=momentum,
            engagement_level=engagement_level,
            repeated_question=repeated_question,
            confidence_trend=confidence_trend,
            total_objections=total_objections,
            has_breakthrough=has_breakthrough,
            turns_since_breakthrough=turns_since_breakthrough,
            guard_intervention=guard_intervention,
            tone=tone,
            # Secondary intents
            secondary_intents=list(secondary_intents),
            # Persona (enables auto-resolution of objection limits in __post_init__)
            persona=collected_data.get("persona", "default"),
            # DAG fields
            is_dag_mode=is_dag_mode,
            active_branches=active_branches,
            current_branch=current_branch,
            dag_depth=dag_depth,
            in_fork=in_fork,
            fork_id=fork_id,
            # Objection limits from state_machine (explicit overrides prevent auto-resolution)
            max_consecutive_objections=max_consecutive,
            max_total_objections=max_total,
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
        config: Optional[Dict[str, Any]] = None,
        # Context-aware fields for testing
        frustration_level: int = 0,
        is_stuck: bool = False,
        has_oscillation: bool = False,
        momentum_direction: str = "neutral",
        momentum: float = 0.0,
        engagement_level: str = "medium",
        repeated_question: Optional[str] = None,
        confidence_trend: str = "stable",
        total_objections: int = 0,
        has_breakthrough: bool = False,
        turns_since_breakthrough: Optional[int] = None,
        guard_intervention: Optional[str] = None,
        tone: Optional[str] = None,
        # Secondary intents for testing
        secondary_intents: List[str] = None,
        # DAG fields for testing
        is_dag_mode: bool = False,
        active_branches: List[str] = None,
        current_branch: Optional[str] = None,
        dag_depth: int = 0,
        in_fork: bool = False,
        fork_id: Optional[str] = None,
        # Objection limits (defaults from YAML config)
        max_consecutive_objections: int = None,
        max_total_objections: int = None,
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
            frustration_level: Client frustration (0-5)
            is_stuck: Whether dialogue is stuck
            has_oscillation: Whether dialogue is oscillating
            momentum_direction: Momentum direction
            momentum: Momentum score
            engagement_level: Engagement level
            repeated_question: Repeated question intent
            confidence_trend: Confidence trend
            total_objections: Total objections count
            has_breakthrough: Breakthrough detected
            turns_since_breakthrough: Turns since breakthrough
            guard_intervention: Guard intervention type
            is_dag_mode: Whether in DAG execution mode
            active_branches: List of active branch IDs
            current_branch: Current branch being processed
            dag_depth: Depth of fork nesting
            in_fork: Whether inside a fork
            fork_id: Current fork ID

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
            config=config,
            frustration_level=frustration_level,
            is_stuck=is_stuck,
            has_oscillation=has_oscillation,
            momentum_direction=momentum_direction,
            momentum=momentum,
            engagement_level=engagement_level,
            repeated_question=repeated_question,
            confidence_trend=confidence_trend,
            total_objections=total_objections,
            has_breakthrough=has_breakthrough,
            turns_since_breakthrough=turns_since_breakthrough,
            guard_intervention=guard_intervention,
            tone=tone,
            # Secondary intents
            secondary_intents=secondary_intents or [],
            # DAG fields
            is_dag_mode=is_dag_mode,
            active_branches=active_branches or [],
            current_branch=current_branch,
            dag_depth=dag_depth,
            in_fork=in_fork,
            fork_id=fork_id,
            # Objection limits (use YAML defaults if not specified)
            max_consecutive_objections=(
                max_consecutive_objections
                if max_consecutive_objections is not None
                else MAX_CONSECUTIVE_OBJECTIONS
            ),
            max_total_objections=(
                max_total_objections
                if max_total_objections is not None
                else MAX_TOTAL_OBJECTIONS
            ),
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
            # Context-aware fields
            "frustration_level": self.frustration_level,
            "is_stuck": self.is_stuck,
            "has_oscillation": self.has_oscillation,
            "momentum_direction": self.momentum_direction,
            "momentum": self.momentum,
            "engagement_level": self.engagement_level,
            "repeated_question": self.repeated_question,
            "confidence_trend": self.confidence_trend,
            "total_objections": self.total_objections,
            "has_breakthrough": self.has_breakthrough,
            "turns_since_breakthrough": self.turns_since_breakthrough,
            "guard_intervention": self.guard_intervention,
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
