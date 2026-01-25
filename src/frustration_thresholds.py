"""
Centralized Frustration Thresholds Module.

This module provides the Single Source of Truth for all frustration-related
thresholds across the system. All components that need frustration thresholds
MUST import from this module to ensure consistency.

Architecture:
    constants.yaml
         |
         v
    yaml_config/constants.py (loads YAML)
         |
         v
    frustration_thresholds.py (THIS MODULE - validates & exports)
         |
         v
    +-----------------+-------------------+----------------------+
    |                 |                   |                      |
    v                 v                   v                      v
markers.py    conversation_guard.py   conditions/         conditions/
                                     fallback/           personalization/

Usage:
    from src.frustration_thresholds import (
        # Threshold values
        FRUSTRATION_WARNING,
        FRUSTRATION_HIGH,
        FRUSTRATION_CRITICAL,
        FRUSTRATION_MAX,
        # Validation
        validate_thresholds,
        # Helper functions for conditions
        is_frustration_warning,
        is_frustration_high,
        is_frustration_critical,
        needs_intervention,
    )

Part of Frustration System Unification (fixing guard intervention bug).
"""

from dataclasses import dataclass
from typing import Dict, Optional
import logging

from src.yaml_config.constants import (
    FRUSTRATION_THRESHOLDS as _YAML_FRUSTRATION_THRESHOLDS,
    GUARD_CONFIG as _YAML_GUARD_CONFIG,
    MAX_FRUSTRATION as _YAML_MAX_FRUSTRATION,
)

logger = logging.getLogger(__name__)


# =============================================================================
# THRESHOLD DATACLASS
# =============================================================================

@dataclass(frozen=True)
class FrustrationThresholdConfig:
    """
    Immutable configuration for frustration thresholds.

    Ensures type safety and provides clear documentation of threshold semantics.

    Threshold Scale (0-10):
        0-1:     Normal - no frustration
        2:       Elevated - slight annoyance, be careful
        3:       Moderate - noticeable frustration, adjust tone
        4:       Warning - start shortening responses
        5-6:     High-Warning - strong frustration, consider intervention
        7-8:     High - trigger guard intervention
        9:       Critical - recommend soft close
        10:      Maximum - immediate exit recommended
    """
    # Core thresholds (from constants.yaml)
    elevated: int     # Slight frustration, adjust approach (default: 2)
    moderate: int     # Noticeable frustration, empathetic tone (default: 3)
    warning: int      # Start shortening responses (default: 4)
    high: int         # Guard intervention triggered (default: 7)
    critical: int     # Soft close recommendation (default: 9)
    max_level: int    # Maximum possible value (default: 10)

    def __post_init__(self):
        """Validate threshold ordering."""
        if not (0 <= self.elevated < self.moderate < self.warning < self.high < self.critical <= self.max_level):
            raise ValueError(
                f"Invalid threshold ordering: "
                f"0 <= elevated({self.elevated}) < moderate({self.moderate}) < "
                f"warning({self.warning}) < high({self.high}) < "
                f"critical({self.critical}) <= max({self.max_level})"
            )


# =============================================================================
# LOAD AND VALIDATE FROM YAML
# =============================================================================

def _load_thresholds() -> FrustrationThresholdConfig:
    """
    Load and validate frustration thresholds from YAML config.

    Ensures consistency between frustration.thresholds and guard config.

    Returns:
        FrustrationThresholdConfig with validated thresholds

    Raises:
        ValueError: If thresholds are inconsistent
    """
    # Get values from YAML config (with sensible defaults)
    elevated = _YAML_FRUSTRATION_THRESHOLDS.get("elevated", 2)
    moderate = _YAML_FRUSTRATION_THRESHOLDS.get("moderate", 3)
    warning = _YAML_FRUSTRATION_THRESHOLDS.get("warning", 4)
    high = _YAML_FRUSTRATION_THRESHOLDS.get("high", 7)
    critical = _YAML_FRUSTRATION_THRESHOLDS.get("critical", 9)
    max_level = _YAML_MAX_FRUSTRATION

    # Validate consistency with guard config
    guard_high = _YAML_GUARD_CONFIG.get("high_frustration_threshold", 7)

    if high != guard_high:
        logger.warning(
            f"THRESHOLD MISMATCH DETECTED: "
            f"frustration.thresholds.high={high} != "
            f"guard.high_frustration_threshold={guard_high}. "
            f"Using frustration.thresholds.high={high} as source of truth."
        )

    return FrustrationThresholdConfig(
        elevated=elevated,
        moderate=moderate,
        warning=warning,
        high=high,
        critical=critical,
        max_level=max_level,
    )


# Load at module import time
_config = _load_thresholds()


# =============================================================================
# EXPORTED THRESHOLD VALUES (Single Source of Truth)
# =============================================================================

# Individual thresholds for direct use
FRUSTRATION_ELEVATED: int = _config.elevated
"""Slight frustration detected, adjust approach. Default: 2"""

FRUSTRATION_MODERATE: int = _config.moderate
"""Noticeable frustration, use empathetic tone. Default: 3"""

FRUSTRATION_WARNING: int = _config.warning
"""Start shortening responses, be more concise. Default: 4"""

FRUSTRATION_HIGH: int = _config.high
"""Trigger guard intervention, offer help/exit. Default: 7"""

FRUSTRATION_CRITICAL: int = _config.critical
"""Recommend soft close, user is highly frustrated. Default: 9"""

FRUSTRATION_MAX: int = _config.max_level
"""Maximum possible frustration level (0-10 scale). Default: 10"""

# Dictionary format (for components that expect it)
FRUSTRATION_THRESHOLDS: Dict[str, int] = {
    "elevated": FRUSTRATION_ELEVATED,
    "moderate": FRUSTRATION_MODERATE,
    "warning": FRUSTRATION_WARNING,
    "high": FRUSTRATION_HIGH,
    "critical": FRUSTRATION_CRITICAL,
}


# =============================================================================
# VALIDATION FUNCTIONS
# =============================================================================

def validate_thresholds() -> bool:
    """
    Validate that all frustration thresholds are consistent across config.

    This should be called at application startup to catch configuration errors.

    Returns:
        True if thresholds are consistent

    Raises:
        ValueError: If thresholds are inconsistent
    """
    # Re-check against current YAML values
    yaml_high = _YAML_FRUSTRATION_THRESHOLDS.get("high", 7)
    guard_high = _YAML_GUARD_CONFIG.get("high_frustration_threshold", 7)

    if yaml_high != guard_high:
        raise ValueError(
            f"Frustration threshold mismatch in constants.yaml: "
            f"frustration.thresholds.high={yaml_high} != "
            f"guard.high_frustration_threshold={guard_high}. "
            f"These MUST be equal for consistent guard intervention behavior."
        )

    logger.info(
        "Frustration thresholds validated: "
        f"warning={FRUSTRATION_WARNING}, high={FRUSTRATION_HIGH}, "
        f"critical={FRUSTRATION_CRITICAL}, max={FRUSTRATION_MAX}"
    )
    return True


# =============================================================================
# HELPER FUNCTIONS FOR CONDITIONS
# =============================================================================

def is_frustration_elevated(level: int) -> bool:
    """
    Check if frustration level has reached elevated threshold.

    At elevated level, bot should:
    - Be more careful with responses
    - Start adjusting tone
    - Monitor for escalation

    Args:
        level: Current frustration level (0-10)

    Returns:
        True if level >= elevated threshold (2)
    """
    return level >= FRUSTRATION_ELEVATED


def is_frustration_moderate(level: int) -> bool:
    """
    Check if frustration level has reached moderate threshold.

    At moderate level, bot should:
    - Use empathetic tone
    - Acknowledge user's concerns
    - Be more careful with pushing

    Args:
        level: Current frustration level (0-10)

    Returns:
        True if level >= moderate threshold (3)
    """
    return level >= FRUSTRATION_MODERATE


def is_frustration_warning(level: int) -> bool:
    """
    Check if frustration level has reached warning threshold.

    At warning level, bot should:
    - Shorten responses
    - Be more concise
    - Avoid long explanations
    - Consider recovery is difficult

    Args:
        level: Current frustration level (0-10)

    Returns:
        True if level >= warning threshold (4)
    """
    return level >= FRUSTRATION_WARNING


def is_frustration_high(level: int) -> bool:
    """
    Check if frustration level has reached high threshold.

    At high level, bot should:
    - Trigger guard intervention (TIER_3)
    - Offer help or exit
    - Use empathetic tone
    - Strongly consider soft close

    This is the threshold used by ConversationGuard for intervention.

    Args:
        level: Current frustration level (0-10)

    Returns:
        True if level >= high threshold (7)
    """
    return level >= FRUSTRATION_HIGH


def is_frustration_critical(level: int) -> bool:
    """
    Check if frustration level has reached critical threshold.

    At critical level, bot should:
    - Strongly recommend soft close
    - Stop pushing for goals
    - Focus on graceful exit

    Args:
        level: Current frustration level (0-10)

    Returns:
        True if level >= critical threshold (9)
    """
    return level >= FRUSTRATION_CRITICAL


def needs_intervention(level: int) -> bool:
    """
    Check if frustration level requires guard intervention.

    This is the primary function for ConversationGuard and fallback conditions.
    Uses FRUSTRATION_HIGH threshold for consistency.

    Args:
        level: Current frustration level (0-10)

    Returns:
        True if intervention should be triggered
    """
    return is_frustration_high(level)


def needs_immediate_escalation(level: int) -> bool:
    """
    Check if frustration level requires immediate escalation to soft_close.

    Uses FRUSTRATION_HIGH threshold (not a different hardcoded value).
    This ensures consistency with ConversationGuard.

    Args:
        level: Current frustration level (0-10)

    Returns:
        True if immediate escalation is needed
    """
    return is_frustration_high(level)


def can_recover(level: int) -> bool:
    """
    Check if conversation can still be recovered based on frustration.

    Recovery is possible below the warning threshold.

    Args:
        level: Current frustration level (0-10)

    Returns:
        True if recovery is possible (level < 4)
    """
    return level < FRUSTRATION_WARNING


def get_frustration_severity(level: int) -> str:
    """
    Get the severity classification for a frustration level.

    Args:
        level: Current frustration level (0-10)

    Returns:
        Severity string: "normal", "elevated", "moderate", "warning", "high", or "critical"
    """
    if level >= FRUSTRATION_CRITICAL:
        return "critical"
    elif level >= FRUSTRATION_HIGH:
        return "high"
    elif level >= FRUSTRATION_WARNING:
        return "warning"
    elif level >= FRUSTRATION_MODERATE:
        return "moderate"
    elif level >= FRUSTRATION_ELEVATED:
        return "elevated"
    else:
        return "normal"


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    # Config class
    "FrustrationThresholdConfig",
    # Threshold values
    "FRUSTRATION_ELEVATED",
    "FRUSTRATION_MODERATE",
    "FRUSTRATION_WARNING",
    "FRUSTRATION_HIGH",
    "FRUSTRATION_CRITICAL",
    "FRUSTRATION_MAX",
    "FRUSTRATION_THRESHOLDS",
    # Validation
    "validate_thresholds",
    # Helper functions
    "is_frustration_elevated",
    "is_frustration_moderate",
    "is_frustration_warning",
    "is_frustration_high",
    "is_frustration_critical",
    "needs_intervention",
    "needs_immediate_escalation",
    "can_recover",
    "get_frustration_severity",
]
