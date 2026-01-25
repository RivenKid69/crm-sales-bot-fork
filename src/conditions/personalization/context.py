"""
PersonalizationContext for Personalization domain.

This module provides the domain-specific context for evaluating
conditions in the PersonalizationEngine/CTAGenerator.

Part of Phase 7: Personalization Domain (ARCHITECTURE_UNIFIED_PLAN.md)
"""

from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field

# Import from Single Source of Truth for frustration thresholds
from src.frustration_thresholds import (
    FRUSTRATION_MODERATE,
    FRUSTRATION_WARNING,
    FRUSTRATION_HIGH,
)


# CTA types for personalization
CTA_TYPES = {
    "demo": "Demo request CTA",
    "contact": "Contact information CTA",
    "trial": "Trial access CTA",
    "info": "Information request CTA",
}

# States where CTA is appropriate (defaults, can be overridden by config)
CTA_ELIGIBLE_STATES = {
    "presentation",
    "handle_objection",
    "close",
}

# States where soft CTA is preferred (defaults, can be overridden by config)
SOFT_CTA_STATES: set = set()

# States where direct CTA is preferred (defaults)
DIRECT_CTA_STATES = {
    "presentation",
    "close",
}

# Industry categories for personalization
INDUSTRIES = {
    "retail",
    "services",
    "b2b",
    "manufacturing",
    "it",
    "consulting",
}

# Role categories for personalization
ROLES = {
    "owner",
    "director",
    "manager",
    "sales",
    "marketing",
    "other",
}

# Pain categories for personalization
PAIN_CATEGORIES = {
    "losing_clients",
    "no_control",
    "manual_work",
    "no_analytics",
    "team_chaos",
}

# Company size thresholds
SMALL_COMPANY_THRESHOLD = 5
MEDIUM_COMPANY_THRESHOLD = 20
LARGE_COMPANY_THRESHOLD = 50

# Frustration thresholds for CTA
# NOTE: Using centralized thresholds from src.frustration_thresholds
SOFT_CTA_FRUSTRATION_THRESHOLD = FRUSTRATION_MODERATE  # Use soft CTA at moderate frustration
NO_CTA_FRUSTRATION_THRESHOLD = FRUSTRATION_HIGH  # Skip CTA at high frustration

# Minimum turns before CTA
MIN_TURNS_FOR_CTA = 3


@dataclass
class PersonalizationContext:
    """
    Context for evaluating conditions in Personalization domain.

    Contains all data needed to personalize responses, select appropriate
    CTAs, and adjust tone based on client context and conversation state.

    Attributes:
        # Base context fields (from BaseContext protocol)
        collected_data: Data collected about the client during conversation
        state: Current dialogue state name
        turn_number: Current turn number in the dialogue (0-indexed)

        # Company information
        company_size: Number of employees in the company
        role: Client's role in the company
        industry: Company's industry

        # Pain information
        pain_category: Main pain category detected
        pain_point: Specific pain point description
        current_crm: Current CRM system if mentioned

        # Signals (from Source of Truth - readonly copies)
        has_breakthrough: Whether a breakthrough moment occurred
        engagement_level: Current engagement level (high/medium/low/disengaged)
        momentum_direction: Conversation momentum (positive/neutral/negative)
        frustration_level: Client frustration level (0-5)

        # Objection context
        objection_type: Type of current/last objection if any
        total_objections: Total number of objections in conversation
        repeated_objection_types: Types of repeated objections

        # CTA context
        last_action: Last action taken by the bot
        last_cta_turn: Turn number when CTA was last added
        cta_count: Number of CTAs added in conversation

        # Additional personalization data
        competitor_mentioned: Whether a competitor was mentioned
        budget_mentioned: Whether budget was discussed
        timeline_mentioned: Whether timeline was discussed
    """
    # Base context fields (from BaseContext protocol)
    collected_data: Dict[str, Any] = field(default_factory=dict)
    state: str = ""
    turn_number: int = 0
    current_phase: Optional[str] = None
    config: Dict[str, Any] = field(default_factory=dict)

    # Company information
    company_size: Optional[int] = None
    role: Optional[str] = None
    industry: Optional[str] = None

    # Pain information
    pain_category: Optional[str] = None
    pain_point: Optional[str] = None
    current_crm: Optional[str] = None

    # Signals (from Source of Truth - readonly copies)
    has_breakthrough: bool = False
    engagement_level: str = "medium"
    momentum_direction: str = "neutral"
    frustration_level: int = 0

    # Objection context
    objection_type: Optional[str] = None
    total_objections: int = 0
    repeated_objection_types: List[str] = field(default_factory=list)

    # CTA context
    last_action: Optional[str] = None
    last_cta_turn: Optional[int] = None
    cta_count: int = 0

    # Additional personalization data
    competitor_mentioned: bool = False
    budget_mentioned: bool = False
    timeline_mentioned: bool = False

    def __post_init__(self):
        """Validate context fields after initialization."""
        if self.turn_number < 0:
            raise ValueError("turn_number cannot be negative")
        if self.frustration_level < 0:
            raise ValueError("frustration_level cannot be negative")
        if self.total_objections < 0:
            raise ValueError("total_objections cannot be negative")
        if self.cta_count < 0:
            raise ValueError("cta_count cannot be negative")

    @classmethod
    def from_envelope(
        cls,
        envelope: Any,
        cta_stats: Optional[Dict[str, Any]] = None
    ) -> "PersonalizationContext":
        """
        Create context from ContextEnvelope.

        This factory method extracts all necessary data from the
        ContextEnvelope (Source of Truth for signals).

        Args:
            envelope: ContextEnvelope instance
            cta_stats: Optional CTA statistics (last_cta_turn, cta_count)

        Returns:
            Initialized PersonalizationContext
        """
        collected = envelope.collected_data.copy() if envelope.collected_data else {}
        cta_stats = cta_stats or {}

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

            # Company information
            company_size=company_size,
            role=collected.get("role"),
            industry=collected.get("industry"),

            # Pain information
            pain_category=collected.get("pain_category"),
            pain_point=collected.get("pain_point"),
            current_crm=collected.get("current_crm"),

            # Signals (from Source of Truth)
            has_breakthrough=envelope.has_breakthrough,
            engagement_level=envelope.engagement_level,
            momentum_direction=envelope.momentum_direction,
            frustration_level=envelope.frustration_level,

            # Objection context
            objection_type=envelope.first_objection_type,
            total_objections=envelope.total_objections,
            repeated_objection_types=list(envelope.repeated_objection_types),

            # CTA context
            last_action=envelope.last_action,
            last_cta_turn=cta_stats.get("last_cta_turn"),
            cta_count=cta_stats.get("cta_count", 0),

            # Additional personalization data
            competitor_mentioned=bool(collected.get("competitor_mentioned")),
            budget_mentioned=bool(collected.get("budget_mentioned")),
            timeline_mentioned=bool(collected.get("timeline_mentioned")),
        )

    @classmethod
    def from_context_dict(
        cls,
        context: Dict[str, Any],
        state: str,
        cta_stats: Optional[Dict[str, Any]] = None
    ) -> "PersonalizationContext":
        """
        Create context from a dictionary.

        This factory method extracts data from a context dictionary,
        useful for integration with CTAGenerator.

        Args:
            context: Context dictionary
            state: Current dialogue state
            cta_stats: Optional CTA statistics

        Returns:
            Initialized PersonalizationContext
        """
        collected = context.get("collected_data", {})
        cta_stats = cta_stats or {}

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

            # Company information
            company_size=company_size,
            role=collected.get("role"),
            industry=collected.get("industry"),

            # Pain information
            pain_category=collected.get("pain_category"),
            pain_point=collected.get("pain_point"),
            current_crm=collected.get("current_crm"),

            # Signals
            has_breakthrough=context.get("has_breakthrough", False),
            engagement_level=context.get("engagement_level", "medium"),
            momentum_direction=context.get("momentum_direction", "neutral"),
            frustration_level=context.get("frustration_level", 0),

            # Objection context
            objection_type=context.get("objection_type"),
            total_objections=context.get("total_objections", 0),
            repeated_objection_types=context.get("repeated_objection_types", []),

            # CTA context
            last_action=context.get("last_action"),
            last_cta_turn=cta_stats.get("last_cta_turn"),
            cta_count=cta_stats.get("cta_count", 0),

            # Additional personalization data
            competitor_mentioned=bool(collected.get("competitor_mentioned")),
            budget_mentioned=bool(collected.get("budget_mentioned")),
            timeline_mentioned=bool(collected.get("timeline_mentioned")),
        )

    @classmethod
    def create_test_context(
        cls,
        collected_data: Optional[Dict[str, Any]] = None,
        state: str = "presentation",
        turn_number: int = 5,
        company_size: Optional[int] = None,
        role: Optional[str] = None,
        industry: Optional[str] = None,
        pain_category: Optional[str] = None,
        pain_point: Optional[str] = None,
        current_crm: Optional[str] = None,
        has_breakthrough: bool = False,
        engagement_level: str = "medium",
        momentum_direction: str = "neutral",
        frustration_level: int = 0,
        objection_type: Optional[str] = None,
        total_objections: int = 0,
        repeated_objection_types: Optional[List[str]] = None,
        last_action: Optional[str] = None,
        last_cta_turn: Optional[int] = None,
        cta_count: int = 0,
        competitor_mentioned: bool = False,
        budget_mentioned: bool = False,
        timeline_mentioned: bool = False,
    ) -> "PersonalizationContext":
        """
        Factory method to create a test context with defaults.

        This is the recommended way to create contexts for unit tests
        as it provides sensible defaults and allows selective overrides.
        """
        return cls(
            collected_data=collected_data or {},
            state=state,
            turn_number=turn_number,
            company_size=company_size,
            role=role,
            industry=industry,
            pain_category=pain_category,
            pain_point=pain_point,
            current_crm=current_crm,
            has_breakthrough=has_breakthrough,
            engagement_level=engagement_level,
            momentum_direction=momentum_direction,
            frustration_level=frustration_level,
            objection_type=objection_type,
            total_objections=total_objections,
            repeated_objection_types=repeated_objection_types or [],
            last_action=last_action,
            last_cta_turn=last_cta_turn,
            cta_count=cta_count,
            competitor_mentioned=competitor_mentioned,
            budget_mentioned=budget_mentioned,
            timeline_mentioned=timeline_mentioned,
        )

    def is_small_company(self) -> bool:
        """Check if company is small (1-5 people)."""
        if self.company_size is None:
            return False
        return 0 < self.company_size <= SMALL_COMPANY_THRESHOLD

    def is_medium_company(self) -> bool:
        """Check if company is medium (6-20 people)."""
        if self.company_size is None:
            return False
        return SMALL_COMPANY_THRESHOLD < self.company_size <= MEDIUM_COMPANY_THRESHOLD

    def is_large_company(self) -> bool:
        """Check if company is large (20+ people)."""
        if self.company_size is None:
            return False
        return self.company_size > MEDIUM_COMPANY_THRESHOLD

    def is_enterprise_company(self) -> bool:
        """Check if company is enterprise (50+ people)."""
        if self.company_size is None:
            return False
        return self.company_size > LARGE_COMPANY_THRESHOLD

    def has_company_context(self) -> bool:
        """Check if any company context is available."""
        return (
            self.company_size is not None or
            self.role is not None or
            self.industry is not None
        )

    def has_pain_context(self) -> bool:
        """Check if pain context is available."""
        return (
            self.pain_category is not None or
            self.pain_point is not None
        )

    def is_cta_eligible_state(self) -> bool:
        """Check if current state is eligible for CTA."""
        eligible_states = self.config.get("cta_eligible_states", CTA_ELIGIBLE_STATES)
        return self.state in eligible_states

    def is_soft_cta_state(self) -> bool:
        """Check if current state prefers soft CTA."""
        soft_states = self.config.get("soft_cta_states", SOFT_CTA_STATES)
        return self.state in soft_states

    def is_direct_cta_state(self) -> bool:
        """Check if current state prefers direct CTA."""
        direct_states = self.config.get("direct_cta_states", DIRECT_CTA_STATES)
        return self.state in direct_states

    def should_use_soft_cta(self) -> bool:
        """Check if soft CTA should be used based on frustration."""
        return self.frustration_level >= SOFT_CTA_FRUSTRATION_THRESHOLD

    def should_skip_cta(self) -> bool:
        """Check if CTA should be skipped due to high frustration."""
        return self.frustration_level >= NO_CTA_FRUSTRATION_THRESHOLD

    def is_enough_turns_for_cta(self) -> bool:
        """Check if enough turns have passed for CTA."""
        return self.turn_number >= MIN_TURNS_FOR_CTA

    def has_rich_context(self) -> bool:
        """Check if rich contextual data is available (2+ data points)."""
        count = 0
        if self.company_size is not None:
            count += 1
        if self.role is not None:
            count += 1
        if self.industry is not None:
            count += 1
        if self.pain_category is not None:
            count += 1
        if self.competitor_mentioned:
            count += 1
        return count >= 2

    def to_dict(self) -> Dict[str, Any]:
        """Convert context to dictionary representation."""
        return {
            "collected_data": self.collected_data,
            "state": self.state,
            "turn_number": self.turn_number,
            "company_size": self.company_size,
            "role": self.role,
            "industry": self.industry,
            "pain_category": self.pain_category,
            "pain_point": self.pain_point,
            "current_crm": self.current_crm,
            "has_breakthrough": self.has_breakthrough,
            "engagement_level": self.engagement_level,
            "momentum_direction": self.momentum_direction,
            "frustration_level": self.frustration_level,
            "objection_type": self.objection_type,
            "total_objections": self.total_objections,
            "repeated_objection_types": self.repeated_objection_types,
            "last_action": self.last_action,
            "last_cta_turn": self.last_cta_turn,
            "cta_count": self.cta_count,
            "competitor_mentioned": self.competitor_mentioned,
            "budget_mentioned": self.budget_mentioned,
            "timeline_mentioned": self.timeline_mentioned,
        }

    def __repr__(self) -> str:
        return (
            f"PersonalizationContext(state={self.state!r}, "
            f"company_size={self.company_size}, "
            f"pain={self.pain_category!r}, "
            f"engagement={self.engagement_level!r}, "
            f"frustration={self.frustration_level})"
        )


# Export all public components
__all__ = [
    "PersonalizationContext",
    "CTA_TYPES",
    "CTA_ELIGIBLE_STATES",
    "SOFT_CTA_STATES",
    "DIRECT_CTA_STATES",
    "INDUSTRIES",
    "ROLES",
    "PAIN_CATEGORIES",
    "SMALL_COMPANY_THRESHOLD",
    "MEDIUM_COMPANY_THRESHOLD",
    "LARGE_COMPANY_THRESHOLD",
    "SOFT_CTA_FRUSTRATION_THRESHOLD",
    "NO_CTA_FRUSTRATION_THRESHOLD",
    "MIN_TURNS_FOR_CTA",
]
