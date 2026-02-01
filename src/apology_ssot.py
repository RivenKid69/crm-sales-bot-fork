"""
Apology System SSoT - Single Source of Truth for apology LOGIC.

This module centralizes all apology-related decision logic, ensuring consistency
across the system. Phrases are sourced from ResponseVariations (DRY principle).
This module provides the WHEN logic, not the WHAT content.

Architecture:
    frustration_thresholds.py (thresholds)
         |
         v
    apology_ssot.py (THIS MODULE - when to apologize)
         |
         v
    +------------------+--------------------+
    |                  |                    |
    response_directives.py   generator.py
         |
         v
    response_variations.py (phrases - APOLOGIES, EXIT_OFFERS)

Usage:
    from src.apology_ssot import (
        # Threshold values
        APOLOGY_THRESHOLD,
        EXIT_OFFER_THRESHOLD,
        # Decision functions
        should_apologize,
        should_offer_exit,
        # Instruction generators
        get_apology_instruction,
        get_exit_instruction,
    )

Part of Apology System Unification (fixing should_apologize bug).
"""

from typing import TYPE_CHECKING, Optional
import logging

from src.frustration_thresholds import (
    FRUSTRATION_WARNING,
    FRUSTRATION_HIGH,
    FRUSTRATION_CRITICAL,
    FRUSTRATION_MAX,
)
from src.yaml_config.constants import APOLOGY_TONE_OVERRIDES

if TYPE_CHECKING:
    from src.response_variations import ResponseVariations

logger = logging.getLogger(__name__)


# =============================================================================
# THRESHOLD VALUES (derived from frustration_thresholds SSoT)
# =============================================================================

APOLOGY_THRESHOLD: int = FRUSTRATION_WARNING
"""Apologize when frustration_level >= this threshold (default: 4 = warning)"""

EXIT_OFFER_THRESHOLD: int = FRUSTRATION_HIGH
"""Offer exit when frustration_level >= this threshold (default: 7 = high)"""


# =============================================================================
# DECISION FUNCTIONS
# =============================================================================

def should_apologize(frustration_level: int, tone: Optional[str] = None) -> bool:
    """
    Check if apology is needed based on frustration level and tone.

    Uses FRUSTRATION_WARNING threshold from frustration_thresholds SSoT.
    Tone-specific overrides are sourced from constants.yaml (SSOT).

    BUG #22: Skepticism is a business question, not frustration.
    Skeptical users get a higher threshold (from YAML) before apology fires.

    Backward-compatible: tone=None preserves existing behavior.

    Args:
        frustration_level: Current frustration level (0-10)
        tone: Optional tone string (e.g., "skeptical", "frustrated")

    Returns:
        True if apology should be included in response
    """
    if frustration_level < APOLOGY_THRESHOLD:
        return False
    # SSOT: tone-specific threshold from constants.yaml
    if tone and tone.lower() in APOLOGY_TONE_OVERRIDES:
        return frustration_level >= APOLOGY_TONE_OVERRIDES[tone.lower()]
    return True


def should_offer_exit(
    frustration_level: int,
    pre_intervention_triggered: bool = False
) -> bool:
    """
    Check if exit offer is needed based on frustration level or pre-intervention.

    Exit is offered when:
    1. frustration_level >= EXIT_OFFER_THRESHOLD (7), OR
    2. pre_intervention_triggered is True (WARNING level 5-6 with RUSHED/FRUSTRATED tone)

    This ensures consistency with FrustrationIntensityCalculator's should_offer_exit logic.

    Args:
        frustration_level: Current frustration level (0-10)
        pre_intervention_triggered: Whether pre-intervention was triggered at WARNING level

    Returns:
        True if exit offer should be included in response
    """
    return frustration_level >= EXIT_OFFER_THRESHOLD or pre_intervention_triggered


# =============================================================================
# INSTRUCTION GENERATORS (for LLM prompts)
# =============================================================================

def get_apology_instruction() -> str:
    """
    Get LLM instruction for including apology.

    Returns:
        Instruction string to prepend to LLM prompt
    """
    return "ОБЯЗАТЕЛЬНО начни с краткого извинения (1 фраза)."


def get_exit_instruction() -> str:
    """
    Get LLM instruction for offering exit.

    Returns:
        Instruction string to include in LLM prompt
    """
    return "Предложи завершить разговор если неудобно."


# =============================================================================
# PHRASE BUILDERS (using ResponseVariations for LRU rotation)
# =============================================================================

def build_apology_prefix(variations: "ResponseVariations") -> str:
    """
    Build apology prefix using ResponseVariations.

    Uses LRU rotation to avoid repeating same phrase.

    Args:
        variations: ResponseVariations instance for phrase selection

    Returns:
        Apology phrase string
    """
    return variations.get_apology()


def build_exit_suffix(variations: "ResponseVariations") -> str:
    """
    Build exit offer suffix using ResponseVariations.

    Uses LRU rotation to avoid repeating same phrase.

    Args:
        variations: ResponseVariations instance for phrase selection

    Returns:
        Exit offer phrase string
    """
    return variations.get_exit_offer()


# =============================================================================
# APOLOGY DETECTION (for post-processing)
# =============================================================================

# Markers that indicate response already contains an apology
APOLOGY_MARKERS = [
    "извин",
    "прощ",
    "сорри",
    "простите",
    "понимаю, это может",
    "понимаю вашу",
    "понимаю ваше",
]


def has_apology(response: str) -> bool:
    """
    Check if response already contains an apology phrase.

    Used by generator to avoid duplicate apologies.

    Args:
        response: Bot response text

    Returns:
        True if response contains apology marker
    """
    response_lower = response.lower()
    return any(marker in response_lower for marker in APOLOGY_MARKERS)


# =============================================================================
# VALIDATION
# =============================================================================

def validate_thresholds() -> bool:
    """
    Validate that apology thresholds are consistent with frustration SSoT.

    This should be called at application startup.

    Returns:
        True if thresholds are consistent

    Raises:
        ValueError: If thresholds are inconsistent
    """
    if APOLOGY_THRESHOLD != FRUSTRATION_WARNING:
        raise ValueError(
            f"APOLOGY_THRESHOLD ({APOLOGY_THRESHOLD}) != "
            f"FRUSTRATION_WARNING ({FRUSTRATION_WARNING})"
        )

    if EXIT_OFFER_THRESHOLD != FRUSTRATION_HIGH:
        raise ValueError(
            f"EXIT_OFFER_THRESHOLD ({EXIT_OFFER_THRESHOLD}) != "
            f"FRUSTRATION_HIGH ({FRUSTRATION_HIGH})"
        )

    if not (APOLOGY_THRESHOLD < EXIT_OFFER_THRESHOLD):
        raise ValueError(
            f"APOLOGY_THRESHOLD ({APOLOGY_THRESHOLD}) must be < "
            f"EXIT_OFFER_THRESHOLD ({EXIT_OFFER_THRESHOLD})"
        )

    # Validate tone overrides are within valid range (BUG #22)
    for tone_name, threshold in APOLOGY_TONE_OVERRIDES.items():
        if not (APOLOGY_THRESHOLD <= threshold <= FRUSTRATION_MAX):
            raise ValueError(
                f"APOLOGY_TONE_OVERRIDES[{tone_name}]={threshold} "
                f"must be between APOLOGY_THRESHOLD({APOLOGY_THRESHOLD}) "
                f"and FRUSTRATION_MAX({FRUSTRATION_MAX})"
            )

    logger.info(
        f"Apology thresholds validated: "
        f"apology_at={APOLOGY_THRESHOLD}, exit_at={EXIT_OFFER_THRESHOLD}, "
        f"tone_overrides={APOLOGY_TONE_OVERRIDES}"
    )
    return True


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    # Threshold values
    "APOLOGY_THRESHOLD",
    "EXIT_OFFER_THRESHOLD",
    # Decision functions
    "should_apologize",
    "should_offer_exit",
    # Instruction generators
    "get_apology_instruction",
    "get_exit_instruction",
    # Phrase builders
    "build_apology_prefix",
    "build_exit_suffix",
    # Detection
    "APOLOGY_MARKERS",
    "has_apology",
    # Validation
    "validate_thresholds",
]
