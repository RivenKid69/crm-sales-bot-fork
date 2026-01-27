"""
PolicyContext for DialoguePolicy domain.

This module provides the domain-specific context for evaluating
conditions in the DialoguePolicy (action overlays).

Part of Phase 5: DialoguePolicy Domain (ARCHITECTURE_UNIFIED_PLAN.md)
"""

from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field

# Import from single source of truth (yaml_config/constants.py)
from src.yaml_config.constants import (
    OVERLAY_ALLOWED_STATES,
    PROTECTED_STATES,
    AGGRESSIVE_ACTIONS,
    # Objection limits from YAML (single source of truth)
    MAX_CONSECUTIVE_OBJECTIONS,
    MAX_TOTAL_OBJECTIONS,
)


@dataclass
class PolicyContext:
    """
    Context for evaluating conditions in DialoguePolicy domain.

    Contains all data needed to evaluate policy overlays,
    including repair signals, objection data, breakthrough info,
    and momentum/engagement indicators.

    Attributes:
        # Base context fields
        collected_data: Data collected about the client during conversation
        state: Current dialogue state name
        turn_number: Current turn number in the dialogue (0-indexed)

        # Basic context
        current_phase: Current phase (from FlowConfig)
        last_action: Last action taken by the bot
        last_intent: Last intent from the client
        current_action: Current action being evaluated for override

        # Level 1 signals (Repair)
        is_stuck: Whether client is stuck
        has_oscillation: Whether oscillation detected
        repeated_question: Repeated question intent or None
        confidence_trend: Trend of confidence ("increasing", "decreasing", "stable")
        unclear_count: Count of unclear intents

        # Level 2 signals (Momentum/Engagement)
        momentum: Momentum score (-1 to +1)
        momentum_direction: Direction of momentum ("positive", "negative", "neutral")
        engagement_level: Level of engagement ("high", "medium", "low", "disengaged")
        engagement_trend: Trend of engagement ("improving", "declining", "stable")
        funnel_velocity: Velocity through sales funnel
        is_progressing: Whether conversation is progressing
        is_regressing: Whether conversation is regressing

        # Level 3 signals (Episodic memory)
        total_objections: Total number of objections
        repeated_objection_types: Types of repeated objections
        has_breakthrough: Whether breakthrough was detected
        turns_since_breakthrough: Turns since breakthrough occurred
        most_effective_action: Most effective action observed
        least_effective_action: Least effective action observed

        # Guard signals
        frustration_level: Level of frustration (0-5)
        guard_intervention: Guard intervention type or None
    """
    # Base context fields (from BaseContext protocol)
    collected_data: Dict[str, Any] = field(default_factory=dict)
    state: str = ""
    turn_number: int = 0

    # Basic context
    current_phase: Optional[str] = None
    last_action: Optional[str] = None
    last_intent: Optional[str] = None
    current_action: Optional[str] = None

    # Legacy alias for spin_phase is added via property after dataclass fields

    # Level 1 signals (Repair)
    is_stuck: bool = False
    has_oscillation: bool = False
    repeated_question: Optional[str] = None
    confidence_trend: str = "stable"
    unclear_count: int = 0

    # Level 2 signals (Momentum/Engagement)
    momentum: float = 0.0
    momentum_direction: str = "neutral"
    engagement_level: str = "medium"
    engagement_trend: str = "stable"
    funnel_velocity: float = 0.0
    is_progressing: bool = False
    is_regressing: bool = False

    # Level 3 signals (Episodic memory)
    total_objections: int = 0
    repeated_objection_types: List[str] = field(default_factory=list)
    has_breakthrough: bool = False
    turns_since_breakthrough: Optional[int] = None
    most_effective_action: Optional[str] = None
    least_effective_action: Optional[str] = None

    # Guard signals
    frustration_level: int = 0
    guard_intervention: Optional[str] = None
    pre_intervention_triggered: bool = False  # Pre-intervention at WARNING level (5-6)

    # Secondary intents (from RefinementPipeline via ContextEnvelope)
    secondary_intents: List[str] = field(default_factory=list)

    # Objection limits (from YAML config, single source of truth)
    max_consecutive_objections: int = field(default_factory=lambda: MAX_CONSECUTIVE_OBJECTIONS)
    max_total_objections: int = field(default_factory=lambda: MAX_TOTAL_OBJECTIONS)

    def __post_init__(self):
        """Validate context fields after initialization."""
        if self.turn_number < 0:
            raise ValueError("turn_number cannot be negative")
        if self.frustration_level < 0:
            raise ValueError("frustration_level cannot be negative")

    @property
    def spin_phase(self) -> Optional[str]:
        """Legacy alias for current_phase."""
        return self.current_phase

    @classmethod
    def from_envelope(
        cls,
        envelope: Any,
        current_action: Optional[str] = None
    ) -> "PolicyContext":
        """
        Create context from ContextEnvelope.

        This factory method extracts all necessary data from the
        ContextEnvelope and creates a properly initialized context.

        Args:
            envelope: ContextEnvelope instance
            current_action: Current action being evaluated

        Returns:
            Initialized PolicyContext
        """
        return cls(
            # Base fields
            collected_data=envelope.collected_data.copy() if envelope.collected_data else {},
            state=envelope.state,
            turn_number=envelope.total_turns,

            # Basic context
            current_phase=getattr(envelope, 'current_phase', None) or getattr(envelope, 'spin_phase', None),
            last_action=envelope.last_action,
            last_intent=envelope.last_intent,
            current_action=current_action,

            # Level 1 signals
            is_stuck=envelope.is_stuck,
            has_oscillation=envelope.has_oscillation,
            repeated_question=envelope.repeated_question,
            confidence_trend=envelope.confidence_trend,
            unclear_count=envelope.unclear_count,

            # Level 2 signals
            momentum=envelope.momentum,
            momentum_direction=envelope.momentum_direction,
            engagement_level=envelope.engagement_level,
            engagement_trend=envelope.engagement_trend,
            funnel_velocity=envelope.funnel_velocity,
            is_progressing=envelope.is_progressing,
            is_regressing=envelope.is_regressing,

            # Level 3 signals
            total_objections=envelope.total_objections,
            repeated_objection_types=list(envelope.repeated_objection_types) if envelope.repeated_objection_types else [],
            has_breakthrough=envelope.has_breakthrough,
            turns_since_breakthrough=envelope.turns_since_breakthrough,
            most_effective_action=envelope.most_effective_action,
            least_effective_action=envelope.least_effective_action,

            # Guard signals
            frustration_level=envelope.frustration_level,
            guard_intervention=envelope.guard_intervention,
            pre_intervention_triggered=getattr(envelope, 'pre_intervention_triggered', False),
            # Secondary intents
            secondary_intents=getattr(envelope, 'secondary_intents', []) or [],
            # Objection limits (from envelope if available, else from YAML config)
            max_consecutive_objections=getattr(
                envelope, 'max_consecutive_objections', MAX_CONSECUTIVE_OBJECTIONS
            ),
            max_total_objections=getattr(
                envelope, 'max_total_objections', MAX_TOTAL_OBJECTIONS
            ),
        )

    @classmethod
    def create_test_context(
        cls,
        collected_data: Dict[str, Any] = None,
        state: str = "greeting",
        turn_number: int = 0,
        current_phase: Optional[str] = None,
        last_action: Optional[str] = None,
        last_intent: Optional[str] = None,
        current_action: Optional[str] = None,
        is_stuck: bool = False,
        has_oscillation: bool = False,
        repeated_question: Optional[str] = None,
        confidence_trend: str = "stable",
        unclear_count: int = 0,
        momentum: float = 0.0,
        momentum_direction: str = "neutral",
        engagement_level: str = "medium",
        engagement_trend: str = "stable",
        funnel_velocity: float = 0.0,
        is_progressing: bool = False,
        is_regressing: bool = False,
        total_objections: int = 0,
        repeated_objection_types: List[str] = None,
        has_breakthrough: bool = False,
        turns_since_breakthrough: Optional[int] = None,
        most_effective_action: Optional[str] = None,
        least_effective_action: Optional[str] = None,
        frustration_level: int = 0,
        guard_intervention: Optional[str] = None,
        pre_intervention_triggered: bool = False,
        # Secondary intents for testing
        secondary_intents: List[str] = None,
        # Objection limits (defaults from YAML config)
        max_consecutive_objections: int = None,
        max_total_objections: int = None,
    ) -> "PolicyContext":
        """
        Factory method to create a test context with defaults.

        This is the recommended way to create contexts for unit tests
        as it provides sensible defaults and allows selective overrides.
        """
        return cls(
            collected_data=collected_data or {},
            state=state,
            turn_number=turn_number,
            current_phase=current_phase,
            last_action=last_action,
            last_intent=last_intent,
            current_action=current_action,
            is_stuck=is_stuck,
            has_oscillation=has_oscillation,
            repeated_question=repeated_question,
            confidence_trend=confidence_trend,
            unclear_count=unclear_count,
            momentum=momentum,
            momentum_direction=momentum_direction,
            engagement_level=engagement_level,
            engagement_trend=engagement_trend,
            funnel_velocity=funnel_velocity,
            is_progressing=is_progressing,
            is_regressing=is_regressing,
            total_objections=total_objections,
            repeated_objection_types=repeated_objection_types or [],
            has_breakthrough=has_breakthrough,
            turns_since_breakthrough=turns_since_breakthrough,
            most_effective_action=most_effective_action,
            least_effective_action=least_effective_action,
            frustration_level=frustration_level,
            guard_intervention=guard_intervention,
            pre_intervention_triggered=pre_intervention_triggered,
            secondary_intents=secondary_intents or [],
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

    def is_overlay_allowed(self) -> bool:
        """Check if overlay is allowed for current state."""
        return self.state in OVERLAY_ALLOWED_STATES

    def is_protected_state(self) -> bool:
        """Check if current state is protected from overlays."""
        return self.state in PROTECTED_STATES

    def is_aggressive_action(self) -> bool:
        """Check if current action is aggressive."""
        return self.current_action in AGGRESSIVE_ACTIONS

    def to_dict(self) -> Dict[str, Any]:
        """Convert context to dictionary representation."""
        return {
            "collected_data": self.collected_data,
            "state": self.state,
            "turn_number": self.turn_number,
            "spin_phase": self.spin_phase,
            "last_action": self.last_action,
            "last_intent": self.last_intent,
            "current_action": self.current_action,
            "is_stuck": self.is_stuck,
            "has_oscillation": self.has_oscillation,
            "repeated_question": self.repeated_question,
            "confidence_trend": self.confidence_trend,
            "unclear_count": self.unclear_count,
            "momentum": self.momentum,
            "momentum_direction": self.momentum_direction,
            "engagement_level": self.engagement_level,
            "engagement_trend": self.engagement_trend,
            "funnel_velocity": self.funnel_velocity,
            "is_progressing": self.is_progressing,
            "is_regressing": self.is_regressing,
            "total_objections": self.total_objections,
            "repeated_objection_types": self.repeated_objection_types,
            "has_breakthrough": self.has_breakthrough,
            "turns_since_breakthrough": self.turns_since_breakthrough,
            "most_effective_action": self.most_effective_action,
            "least_effective_action": self.least_effective_action,
            "frustration_level": self.frustration_level,
            "guard_intervention": self.guard_intervention,
            "pre_intervention_triggered": self.pre_intervention_triggered,
            "secondary_intents": self.secondary_intents,
        }

    def __repr__(self) -> str:
        return (
            f"PolicyContext(state={self.state!r}, "
            f"turn={self.turn_number}, "
            f"spin_phase={self.spin_phase!r}, "
            f"is_stuck={self.is_stuck}, "
            f"has_breakthrough={self.has_breakthrough})"
        )


# Export all public components
__all__ = [
    "PolicyContext",
    "OVERLAY_ALLOWED_STATES",
    "PROTECTED_STATES",
    "AGGRESSIVE_ACTIONS",
]
