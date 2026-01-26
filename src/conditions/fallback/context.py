"""
FallbackContext for Fallback domain.

This module provides the domain-specific context for evaluating
conditions in the FallbackHandler.

Part of Phase 6: Fallback Domain (ARCHITECTURE_UNIFIED_PLAN.md)
"""

from typing import Dict, Any, Optional
from dataclasses import dataclass, field


# Fallback tiers in order of escalation
FALLBACK_TIERS = [
    "fallback_tier_1",  # Rephrase question
    "fallback_tier_2",  # Offer options
    "fallback_tier_3",  # Offer skip
    "soft_close",       # Graceful exit
]

# States where dynamic CTA is especially useful (loaded from config, these are defaults)
DYNAMIC_CTA_STATES = {
    "presentation",
}

# Pain categories for dynamic options
PAIN_CATEGORIES = {
    "losing_clients",
    "no_control",
    "manual_work",
}

# Company size thresholds
SMALL_COMPANY_THRESHOLD = 5
LARGE_COMPANY_THRESHOLD = 20


@dataclass
class FallbackContext:
    """
    Context for evaluating conditions in Fallback domain.

    Contains all data needed to select appropriate fallback tier
    and dynamic CTA options based on conversation state and history.

    Attributes:
        # Base context fields (from BaseContext protocol)
        collected_data: Data collected about the client during conversation
        state: Current dialogue state name
        turn_number: Current turn number in the dialogue (0-indexed)

        # Fallback-specific fields
        total_fallbacks: Total number of fallbacks in this conversation
        consecutive_fallbacks: Number of consecutive fallbacks
        current_tier: Current fallback tier being processed
        fallbacks_in_state: Fallbacks in current state
        last_successful_intent: Last intent that was successfully processed

        # Signals (from Source of Truth - readonly copies)
        frustration_level: Client frustration level (0-5)
        momentum_direction: Direction of conversation momentum
        engagement_level: Level of client engagement

        # Contextual data
        pain_category: Detected pain category (losing_clients, no_control, etc.)
        competitor_mentioned: Whether competitor was mentioned
        last_intent: Last intent detected
        company_size: Company size if known
    """
    # Base context fields (from BaseContext protocol)
    collected_data: Dict[str, Any] = field(default_factory=dict)
    state: str = ""
    turn_number: int = 0

    # Fallback-specific fields
    total_fallbacks: int = 0
    consecutive_fallbacks: int = 0
    current_tier: str = "fallback_tier_1"
    fallbacks_in_state: int = 0
    last_successful_intent: Optional[str] = None

    # Signals (from Source of Truth - readonly copies)
    frustration_level: int = 0
    momentum_direction: str = "neutral"
    engagement_level: str = "medium"
    pre_intervention_triggered: bool = False  # Pre-intervention at WARNING level (5-6)

    # Contextual data
    pain_category: Optional[str] = None
    competitor_mentioned: bool = False
    last_intent: Optional[str] = None
    company_size: Optional[int] = None

    def __post_init__(self):
        """Validate context fields after initialization."""
        if self.turn_number < 0:
            raise ValueError("turn_number cannot be negative")
        if self.total_fallbacks < 0:
            raise ValueError("total_fallbacks cannot be negative")
        if self.consecutive_fallbacks < 0:
            raise ValueError("consecutive_fallbacks cannot be negative")
        if self.frustration_level < 0:
            raise ValueError("frustration_level cannot be negative")
        if self.current_tier not in FALLBACK_TIERS:
            raise ValueError(f"current_tier must be one of {FALLBACK_TIERS}")

    @classmethod
    def from_handler_stats(
        cls,
        stats: Dict[str, Any],
        state: str,
        context: Optional[Dict[str, Any]] = None,
        current_tier: str = "fallback_tier_1"
    ) -> "FallbackContext":
        """
        Create context from FallbackHandler stats and conversation context.

        This factory method extracts data from the FallbackHandler's
        internal statistics and the conversation context.

        Args:
            stats: FallbackHandler stats dict
            state: Current dialogue state
            context: Additional context (collected_data, envelope data, etc.)
            current_tier: Current fallback tier

        Returns:
            Initialized FallbackContext
        """
        context = context or {}
        collected = context.get("collected_data", {})

        # Extract company_size and ensure it's an int
        company_size = collected.get("company_size")
        if company_size is not None:
            if isinstance(company_size, str):
                try:
                    company_size = int(company_size)
                except ValueError:
                    company_size = None

        return cls(
            # Base fields
            collected_data=collected,
            state=state,
            turn_number=context.get("turn_number", 0),

            # Fallback-specific
            total_fallbacks=stats.get("total_count", 0),
            consecutive_fallbacks=stats.get("tier_counts", {}).get(current_tier, 0),
            current_tier=current_tier,
            fallbacks_in_state=stats.get("state_counts", {}).get(state, 0),
            last_successful_intent=context.get("last_successful_intent"),

            # Signals
            frustration_level=context.get("frustration_level", 0),
            momentum_direction=context.get("momentum_direction", "neutral"),
            engagement_level=context.get("engagement_level", "medium"),
            pre_intervention_triggered=context.get("pre_intervention_triggered", False),

            # Contextual data
            pain_category=collected.get("pain_category"),
            competitor_mentioned=bool(collected.get("competitor_mentioned")),
            last_intent=context.get("last_intent"),
            company_size=company_size,
        )

    @classmethod
    def from_envelope(
        cls,
        envelope: Any,
        stats: Dict[str, Any],
        current_tier: str = "fallback_tier_1"
    ) -> "FallbackContext":
        """
        Create context from ContextEnvelope and FallbackHandler stats.

        This factory method extracts all necessary data from the
        ContextEnvelope (Source of Truth for signals) and handler stats.

        Args:
            envelope: ContextEnvelope instance
            stats: FallbackHandler stats dict
            current_tier: Current fallback tier

        Returns:
            Initialized FallbackContext
        """
        collected = envelope.collected_data.copy() if envelope.collected_data else {}

        # Extract company_size and ensure it's an int
        company_size = collected.get("company_size")
        if company_size is not None:
            if isinstance(company_size, str):
                try:
                    company_size = int(company_size)
                except ValueError:
                    company_size = None

        return cls(
            # Base fields
            collected_data=collected,
            state=envelope.state,
            turn_number=envelope.total_turns,

            # Fallback-specific
            total_fallbacks=stats.get("total_count", 0),
            consecutive_fallbacks=stats.get("tier_counts", {}).get(current_tier, 0),
            current_tier=current_tier,
            fallbacks_in_state=stats.get("state_counts", {}).get(envelope.state, 0),
            last_successful_intent=envelope.last_successful_intent if hasattr(envelope, 'last_successful_intent') else None,

            # Signals (from Source of Truth)
            frustration_level=envelope.frustration_level,
            momentum_direction=envelope.momentum_direction,
            engagement_level=envelope.engagement_level,
            pre_intervention_triggered=getattr(envelope, 'pre_intervention_triggered', False),

            # Contextual data
            pain_category=collected.get("pain_category"),
            competitor_mentioned=bool(collected.get("competitor_mentioned")),
            last_intent=envelope.last_intent,
            company_size=company_size,
        )

    @classmethod
    def create_test_context(
        cls,
        collected_data: Dict[str, Any] = None,
        state: str = "greeting",
        turn_number: int = 0,
        total_fallbacks: int = 0,
        consecutive_fallbacks: int = 0,
        current_tier: str = "fallback_tier_1",
        fallbacks_in_state: int = 0,
        last_successful_intent: Optional[str] = None,
        frustration_level: int = 0,
        momentum_direction: str = "neutral",
        engagement_level: str = "medium",
        pre_intervention_triggered: bool = False,
        pain_category: Optional[str] = None,
        competitor_mentioned: bool = False,
        last_intent: Optional[str] = None,
        company_size: Optional[int] = None,
    ) -> "FallbackContext":
        """
        Factory method to create a test context with defaults.

        This is the recommended way to create contexts for unit tests
        as it provides sensible defaults and allows selective overrides.
        """
        return cls(
            collected_data=collected_data or {},
            state=state,
            turn_number=turn_number,
            total_fallbacks=total_fallbacks,
            consecutive_fallbacks=consecutive_fallbacks,
            current_tier=current_tier,
            fallbacks_in_state=fallbacks_in_state,
            last_successful_intent=last_successful_intent,
            frustration_level=frustration_level,
            momentum_direction=momentum_direction,
            engagement_level=engagement_level,
            pre_intervention_triggered=pre_intervention_triggered,
            pain_category=pain_category,
            competitor_mentioned=competitor_mentioned,
            last_intent=last_intent,
            company_size=company_size,
        )

    def get_tier_index(self) -> int:
        """Get index of current tier in escalation order."""
        try:
            return FALLBACK_TIERS.index(self.current_tier)
        except ValueError:
            return 0

    def is_max_tier(self) -> bool:
        """Check if current tier is the maximum (soft_close)."""
        return self.current_tier == FALLBACK_TIERS[-1]

    def is_dynamic_cta_state(self) -> bool:
        """Check if current state supports dynamic CTA."""
        return self.state in DYNAMIC_CTA_STATES

    def is_small_company(self) -> bool:
        """Check if company is small (1-5 people)."""
        if self.company_size is None:
            return False
        return 0 < self.company_size <= SMALL_COMPANY_THRESHOLD

    def is_large_company(self) -> bool:
        """Check if company is large (20+ people)."""
        if self.company_size is None:
            return False
        return self.company_size > LARGE_COMPANY_THRESHOLD

    def has_pain_category(self) -> bool:
        """Check if a pain category has been identified."""
        return self.pain_category is not None and self.pain_category in PAIN_CATEGORIES

    def to_dict(self) -> Dict[str, Any]:
        """Convert context to dictionary representation."""
        return {
            "collected_data": self.collected_data,
            "state": self.state,
            "turn_number": self.turn_number,
            "total_fallbacks": self.total_fallbacks,
            "consecutive_fallbacks": self.consecutive_fallbacks,
            "current_tier": self.current_tier,
            "fallbacks_in_state": self.fallbacks_in_state,
            "last_successful_intent": self.last_successful_intent,
            "frustration_level": self.frustration_level,
            "momentum_direction": self.momentum_direction,
            "engagement_level": self.engagement_level,
            "pre_intervention_triggered": self.pre_intervention_triggered,
            "pain_category": self.pain_category,
            "competitor_mentioned": self.competitor_mentioned,
            "last_intent": self.last_intent,
            "company_size": self.company_size,
        }

    def __repr__(self) -> str:
        return (
            f"FallbackContext(state={self.state!r}, "
            f"tier={self.current_tier!r}, "
            f"total_fallbacks={self.total_fallbacks}, "
            f"consecutive={self.consecutive_fallbacks}, "
            f"frustration={self.frustration_level})"
        )


# Export all public components
__all__ = [
    "FallbackContext",
    "FALLBACK_TIERS",
    "DYNAMIC_CTA_STATES",
    "PAIN_CATEGORIES",
    "SMALL_COMPANY_THRESHOLD",
    "LARGE_COMPANY_THRESHOLD",
]
