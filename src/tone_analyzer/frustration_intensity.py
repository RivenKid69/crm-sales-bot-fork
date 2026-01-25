"""
Frustration Intensity Calculator - Signal-Aware Frustration Accumulation.

This module implements intensity-based frustration calculation, where multiple
signals of the same tone type in a single message contribute more weight.

Architecture:
    This follows the Protocol + Registry pattern from DESIGN_PRINCIPLES.md:

    1. IFrustrationIntensityCalculator Protocol - defines the interface
    2. FrustrationIntensityCalculator - default implementation
    3. Registry for extensibility
    4. YAML-driven configuration (SSoT)

Root Cause Fix:
    Original bug: Only ONE signal per tone counted (break statement in regex_analyzer.py)
    Result: "быстрее, не тяни, некогда" (3 RUSHED markers) = +1 frustration

    With intensity calculation:
    - 1 signal = base weight (e.g., +1 for RUSHED)
    - 2 signals = base weight * 1.5
    - 3+ signals = base weight * 2.0

    This ensures users expressing strong frustration get appropriate response.

Usage:
    from src.tone_analyzer.frustration_intensity import (
        FrustrationIntensityCalculator,
        calculate_frustration_delta,
    )

    calculator = FrustrationIntensityCalculator()
    delta = calculator.calculate(
        tone=Tone.RUSHED,
        signal_count=3,
        consecutive_turns=4
    )

Part of Frustration System Unification.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Protocol, runtime_checkable
import logging

from .models import Tone

logger = logging.getLogger(__name__)


# =============================================================================
# CONFIGURATION (will be loaded from YAML)
# =============================================================================

@dataclass(frozen=True)
class IntensityConfig:
    """
    Configuration for intensity-based frustration calculation.

    Loaded from constants.yaml:frustration.intensity
    """
    # Base weights per tone (default values, can be overridden by YAML)
    base_weights: Dict[str, int] = field(default_factory=lambda: {
        "frustrated": 3,
        "rushed": 2,      # Increased from 1 to 2 - RUSHED users need faster response
        "skeptical": 1,
        "confused": 1,
    })

    # Intensity multipliers based on signal count
    # Format: {min_signals: multiplier}
    intensity_multipliers: Dict[int, float] = field(default_factory=lambda: {
        1: 1.0,    # 1 signal = base weight
        2: 1.5,    # 2 signals = 1.5x base weight
        3: 2.0,    # 3+ signals = 2x base weight
    })

    # Consecutive turn bonus - frustration escalates faster with repeated negative tones
    consecutive_turn_multiplier: float = 1.2
    consecutive_turn_threshold: int = 2  # Start bonus after 2+ consecutive turns

    # Decay weights for positive tones
    decay_weights: Dict[str, int] = field(default_factory=lambda: {
        "neutral": 1,
        "positive": 2,
        "interested": 2,
    })

    # Special handling for RUSHED tone
    # If RUSHED detected with high intensity, trigger pre-intervention at WARNING threshold
    rushed_pre_intervention_threshold: int = 2  # signal count to trigger pre-intervention

    # Maximum frustration level
    max_frustration: int = 10


def load_intensity_config() -> IntensityConfig:
    """
    Load intensity configuration from YAML.

    Falls back to defaults if config not available.
    """
    try:
        from src.yaml_config.constants import (
            FRUSTRATION_INTENSITY_CONFIG,
            MAX_FRUSTRATION,
        )

        return IntensityConfig(
            base_weights=FRUSTRATION_INTENSITY_CONFIG.get("base_weights", {
                "frustrated": 3,
                "rushed": 2,
                "skeptical": 1,
                "confused": 1,
            }),
            intensity_multipliers=FRUSTRATION_INTENSITY_CONFIG.get("intensity_multipliers", {
                1: 1.0,
                2: 1.5,
                3: 2.0,
            }),
            consecutive_turn_multiplier=FRUSTRATION_INTENSITY_CONFIG.get(
                "consecutive_turn_multiplier", 1.2
            ),
            consecutive_turn_threshold=FRUSTRATION_INTENSITY_CONFIG.get(
                "consecutive_turn_threshold", 2
            ),
            decay_weights=FRUSTRATION_INTENSITY_CONFIG.get("decay_weights", {
                "neutral": 1,
                "positive": 2,
                "interested": 2,
            }),
            rushed_pre_intervention_threshold=FRUSTRATION_INTENSITY_CONFIG.get(
                "rushed_pre_intervention_threshold", 2
            ),
            max_frustration=MAX_FRUSTRATION,
        )
    except ImportError:
        logger.warning(
            "Could not load FRUSTRATION_INTENSITY_CONFIG from YAML, using defaults"
        )
        return IntensityConfig()


# =============================================================================
# PROTOCOL (Interface)
# =============================================================================

@runtime_checkable
class IFrustrationIntensityCalculator(Protocol):
    """
    Protocol for frustration intensity calculators.

    Follows the Protocol pattern from DESIGN_PRINCIPLES.md for extensibility.
    """

    def calculate(
        self,
        tone: Tone,
        signal_count: int,
        consecutive_turns: int = 0,
    ) -> int:
        """
        Calculate frustration delta based on tone, signal count, and context.

        Args:
            tone: Detected tone (FRUSTRATED, RUSHED, etc.)
            signal_count: Number of signals detected for this tone
            consecutive_turns: Number of consecutive turns with negative tone

        Returns:
            Frustration delta (positive = increase, negative = decrease)
        """
        ...

    def should_pre_intervene(
        self,
        tone: Tone,
        signal_count: int,
        current_frustration: int,
    ) -> bool:
        """
        Check if pre-intervention should be triggered.

        Pre-intervention provides early guidance (shorter responses, offer exit)
        before reaching the HIGH threshold for full intervention.

        Args:
            tone: Detected tone
            signal_count: Number of signals
            current_frustration: Current frustration level

        Returns:
            True if pre-intervention should be triggered
        """
        ...

    def get_intervention_urgency(
        self,
        tone: Tone,
        signal_count: int,
        current_frustration: int,
    ) -> str:
        """
        Get intervention urgency level.

        Args:
            tone: Detected tone
            signal_count: Number of signals
            current_frustration: Current frustration level

        Returns:
            Urgency level: "none", "low", "medium", "high", "critical"
        """
        ...


# =============================================================================
# IMPLEMENTATION
# =============================================================================

class FrustrationIntensityCalculator:
    """
    Default implementation of IFrustrationIntensityCalculator.

    Calculates frustration delta based on:
    - Tone type (FRUSTRATED, RUSHED, SKEPTICAL, CONFUSED)
    - Signal count (intensity)
    - Consecutive turns of negative tone

    Example:
        "быстрее, не тяни, некогда" (3 RUSHED signals)
        - Base weight for RUSHED: 2
        - Intensity multiplier for 3 signals: 2.0
        - Delta: 2 * 2.0 = 4

        After 2 turns: frustration = 8 (above HIGH threshold of 7)
        Intervention triggered!
    """

    # Tones that increase frustration
    NEGATIVE_TONES = {Tone.FRUSTRATED, Tone.RUSHED, Tone.SKEPTICAL, Tone.CONFUSED}

    # Tones that decrease frustration (decay)
    POSITIVE_TONES = {Tone.NEUTRAL, Tone.POSITIVE, Tone.INTERESTED}

    def __init__(self, config: Optional[IntensityConfig] = None):
        """
        Initialize calculator with configuration.

        Args:
            config: Configuration for intensity calculation.
                    If None, loads from YAML or uses defaults.
        """
        self.config = config or load_intensity_config()
        self._consecutive_negative_turns = 0
        self._last_tone: Optional[Tone] = None

    def calculate(
        self,
        tone: Tone,
        signal_count: int,
        consecutive_turns: int = 0,
    ) -> int:
        """
        Calculate frustration delta with intensity-based weighting.

        Args:
            tone: Detected tone
            signal_count: Number of signals detected
            consecutive_turns: External consecutive turn count (optional)

        Returns:
            Frustration delta (positive or negative integer)
        """
        if signal_count <= 0:
            return 0

        # Track consecutive negative turns internally
        if tone in self.NEGATIVE_TONES:
            if self._last_tone in self.NEGATIVE_TONES:
                self._consecutive_negative_turns += 1
            else:
                self._consecutive_negative_turns = 1
        else:
            self._consecutive_negative_turns = 0

        self._last_tone = tone

        # Use external count if provided, otherwise use internal tracking
        consecutive = consecutive_turns if consecutive_turns > 0 else self._consecutive_negative_turns

        # Calculate delta based on tone type
        if tone in self.NEGATIVE_TONES:
            return self._calculate_increase(tone, signal_count, consecutive)
        elif tone in self.POSITIVE_TONES:
            return self._calculate_decrease(tone)
        else:
            return 0

    def _calculate_increase(
        self,
        tone: Tone,
        signal_count: int,
        consecutive_turns: int,
    ) -> int:
        """Calculate frustration increase for negative tones."""
        # Get base weight
        tone_name = tone.value.lower()
        base_weight = self.config.base_weights.get(tone_name, 1)

        # Get intensity multiplier
        intensity_mult = self._get_intensity_multiplier(signal_count)

        # Get consecutive turn multiplier
        consecutive_mult = 1.0
        if consecutive_turns >= self.config.consecutive_turn_threshold:
            consecutive_mult = self.config.consecutive_turn_multiplier

        # Calculate total delta
        delta = int(base_weight * intensity_mult * consecutive_mult)

        logger.debug(
            "Frustration increase calculated",
            tone=tone.value,
            signal_count=signal_count,
            base_weight=base_weight,
            intensity_mult=intensity_mult,
            consecutive_mult=consecutive_mult,
            delta=delta,
        )

        return max(1, delta)  # Minimum delta of 1

    def _calculate_decrease(self, tone: Tone) -> int:
        """Calculate frustration decrease for positive tones."""
        tone_name = tone.value.lower()
        decay = self.config.decay_weights.get(tone_name, 1)
        return -decay  # Negative delta = decrease

    def _get_intensity_multiplier(self, signal_count: int) -> float:
        """Get intensity multiplier based on signal count."""
        # Find the highest threshold that signal_count meets
        multiplier = 1.0
        for threshold in sorted(self.config.intensity_multipliers.keys()):
            if signal_count >= threshold:
                multiplier = self.config.intensity_multipliers[threshold]
        return multiplier

    def should_pre_intervene(
        self,
        tone: Tone,
        signal_count: int,
        current_frustration: int,
    ) -> bool:
        """
        Check if pre-intervention should be triggered.

        Pre-intervention is triggered when:
        1. RUSHED tone with high signal count (user explicitly says "быстрее, не тяни, некогда")
        2. OR frustration is at WARNING level with any negative tone

        This ensures users expressing urgency get immediate response even if
        frustration hasn't reached the HIGH threshold.
        """
        from src.frustration_thresholds import FRUSTRATION_WARNING

        # RUSHED with high intensity triggers pre-intervention
        if tone == Tone.RUSHED:
            if signal_count >= self.config.rushed_pre_intervention_threshold:
                logger.info(
                    "Pre-intervention triggered: RUSHED tone with high intensity",
                    signal_count=signal_count,
                    threshold=self.config.rushed_pre_intervention_threshold,
                )
                return True

        # WARNING level with any negative tone triggers pre-intervention
        if current_frustration >= FRUSTRATION_WARNING and tone in self.NEGATIVE_TONES:
            logger.info(
                "Pre-intervention triggered: WARNING level with negative tone",
                frustration=current_frustration,
                tone=tone.value,
            )
            return True

        return False

    def get_intervention_urgency(
        self,
        tone: Tone,
        signal_count: int,
        current_frustration: int,
    ) -> str:
        """
        Get intervention urgency level for response guidance.

        Levels:
        - "none": No intervention needed
        - "low": Slight adjustment (be more concise)
        - "medium": Moderate adjustment (shorter responses, empathetic tone)
        - "high": Strong adjustment (very short, offer exit)
        - "critical": Immediate soft close recommended
        """
        from src.frustration_thresholds import (
            FRUSTRATION_ELEVATED,
            FRUSTRATION_MODERATE,
            FRUSTRATION_WARNING,
            FRUSTRATION_HIGH,
            FRUSTRATION_CRITICAL,
        )

        # Critical frustration = critical urgency
        if current_frustration >= FRUSTRATION_CRITICAL:
            return "critical"

        # High frustration = high urgency
        if current_frustration >= FRUSTRATION_HIGH:
            return "high"

        # RUSHED with multiple signals = high urgency even below threshold
        if tone == Tone.RUSHED and signal_count >= 3:
            return "high"

        # WARNING level or RUSHED with 2 signals = medium urgency
        if current_frustration >= FRUSTRATION_WARNING:
            return "medium"
        if tone == Tone.RUSHED and signal_count >= 2:
            return "medium"

        # MODERATE level = low urgency
        if current_frustration >= FRUSTRATION_MODERATE:
            return "low"

        # ELEVATED level with negative tone = low urgency
        if current_frustration >= FRUSTRATION_ELEVATED and tone in self.NEGATIVE_TONES:
            return "low"

        return "none"

    def reset(self) -> None:
        """Reset internal state for new conversation."""
        self._consecutive_negative_turns = 0
        self._last_tone = None


# =============================================================================
# REGISTRY (for extensibility)
# =============================================================================

class FrustrationIntensityRegistry:
    """
    Registry for FrustrationIntensityCalculator implementations.

    Follows the Registry pattern from DESIGN_PRINCIPLES.md.
    """

    _calculators: Dict[str, type] = {}
    _default: str = "default"

    @classmethod
    def register(cls, name: str, calculator_class: type) -> None:
        """Register a calculator implementation."""
        cls._calculators[name] = calculator_class
        logger.debug(f"Registered frustration intensity calculator: {name}")

    @classmethod
    def get(cls, name: Optional[str] = None) -> IFrustrationIntensityCalculator:
        """Get calculator by name (or default)."""
        name = name or cls._default
        if name not in cls._calculators:
            raise KeyError(f"Calculator '{name}' not registered")
        return cls._calculators[name]()

    @classmethod
    def set_default(cls, name: str) -> None:
        """Set the default calculator."""
        if name not in cls._calculators:
            raise KeyError(f"Calculator '{name}' not registered")
        cls._default = name

    @classmethod
    def list_registered(cls) -> List[str]:
        """List all registered calculators."""
        return list(cls._calculators.keys())


# Register default implementation
FrustrationIntensityRegistry.register("default", FrustrationIntensityCalculator)


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def calculate_frustration_delta(
    tone: Tone,
    signal_count: int,
    consecutive_turns: int = 0,
) -> int:
    """
    Calculate frustration delta using the default calculator.

    Convenience function for simple use cases.

    Args:
        tone: Detected tone
        signal_count: Number of signals detected
        consecutive_turns: Consecutive turns with negative tone

    Returns:
        Frustration delta
    """
    calculator = FrustrationIntensityRegistry.get()
    return calculator.calculate(tone, signal_count, consecutive_turns)


def should_pre_intervene(
    tone: Tone,
    signal_count: int,
    current_frustration: int,
) -> bool:
    """
    Check if pre-intervention should be triggered.

    Convenience function for simple use cases.
    """
    calculator = FrustrationIntensityRegistry.get()
    return calculator.should_pre_intervene(tone, signal_count, current_frustration)


def get_intervention_urgency(
    tone: Tone,
    signal_count: int,
    current_frustration: int,
) -> str:
    """
    Get intervention urgency level.

    Convenience function for simple use cases.
    """
    calculator = FrustrationIntensityRegistry.get()
    return calculator.get_intervention_urgency(tone, signal_count, current_frustration)


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    # Config
    "IntensityConfig",
    "load_intensity_config",
    # Protocol
    "IFrustrationIntensityCalculator",
    # Implementation
    "FrustrationIntensityCalculator",
    # Registry
    "FrustrationIntensityRegistry",
    # Convenience functions
    "calculate_frustration_delta",
    "should_pre_intervene",
    "get_intervention_urgency",
]
