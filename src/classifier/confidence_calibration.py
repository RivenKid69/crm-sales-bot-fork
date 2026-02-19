"""
Confidence Calibration Layer - Scientific LLM Confidence Calibration.

This module provides algorithmic confidence calibration to address the fundamental
problem of LLM overconfidence in classification tasks.

Problem:
    LLMs generate confidence as a JSON field, not computed from probabilities.
    This leads to systematically overconfident predictions (0.85-0.95) even when
    classification is incorrect.

Solution:
    Apply scientific calibration techniques:
    1. Entropy-based calibration: Use alternatives to compute uncertainty
    2. Heuristic calibration: Apply pattern-based rules for known error scenarios
    3. Gap-based calibration: Penalize when top alternatives are close in confidence

Architecture:
    - ICalibrationStrategy (Protocol): Interface for calibration strategies
    - EntropyCalibrationStrategy: Entropy-based uncertainty estimation
    - HeuristicCalibrationStrategy: Pattern-based confidence adjustment
    - GapCalibrationStrategy: Gap-based confidence penalty
    - ConfidenceCalibrator: Combines multiple strategies
    - ConfidenceCalibrationLayer: Integrates with RefinementPipeline

Scientific Background:
    - LLMs are systematically overconfident (Guo et al., 2017)
    - Entropy correlates with prediction uncertainty (Shannon, 1948)
    - Calibration improves decision-making reliability (Niculescu-Mizil & Caruana, 2005)
    - Verbal confidence needs post-hoc calibration (Tian et al., 2023)

SSoT: This is the Single Source of Truth for confidence calibration.
Config: src/yaml_config/constants.yaml (confidence_calibration section)

Usage:
    from src.classifier.confidence_calibration import ConfidenceCalibrationLayer

    # Layer is auto-registered with RefinementPipeline
    # Just import to register:
    from src.classifier import confidence_calibration
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, ClassVar, Dict, List, Optional, Protocol, Set, Tuple
import logging
import math
import re

from src.classifier.refinement_pipeline import (
    BaseRefinementLayer,
    LayerPriority,
    RefinementContext,
    RefinementResult,
    RefinementDecision,
    register_refinement_layer,
)

logger = logging.getLogger(__name__)


# =============================================================================
# ENUMS AND DATA CLASSES
# =============================================================================

class CalibrationReason(Enum):
    """Reasons for confidence calibration."""
    ENTROPY_HIGH = "entropy_high"              # High entropy in alternatives
    GAP_SMALL = "gap_small"                    # Small gap between top alternatives
    HEURISTIC_MATCH = "heuristic_match"        # Matched known error pattern
    SHORT_MESSAGE = "short_message"            # Short messages are less reliable
    ALTERNATIVES_CLOSE = "alternatives_close"  # Multiple plausible alternatives
    NO_ALTERNATIVES = "no_alternatives"        # No alternatives provided
    COMBINED = "combined"                      # Multiple factors combined


@dataclass
class CalibrationResult:
    """Result of confidence calibration."""
    original_confidence: float
    calibrated_confidence: float
    calibration_applied: bool
    reasons: List[CalibrationReason] = field(default_factory=list)
    entropy: Optional[float] = None
    gap: Optional[float] = None
    penalty_factors: Dict[str, float] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def confidence_delta(self) -> float:
        """How much confidence was reduced."""
        return self.original_confidence - self.calibrated_confidence

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging/storage."""
        return {
            "original_confidence": self.original_confidence,
            "calibrated_confidence": self.calibrated_confidence,
            "calibration_applied": self.calibration_applied,
            "confidence_delta": self.confidence_delta,
            "reasons": [r.value for r in self.reasons],
            "entropy": self.entropy,
            "gap": self.gap,
            "penalty_factors": self.penalty_factors,
        }


# =============================================================================
# CALIBRATION STRATEGY PROTOCOL
# =============================================================================

class ICalibrationStrategy(Protocol):
    """Protocol for confidence calibration strategies."""

    @property
    def name(self) -> str:
        """Strategy name for identification."""
        ...

    @property
    def enabled(self) -> bool:
        """Whether strategy is enabled."""
        ...

    def calibrate(
        self,
        confidence: float,
        alternatives: List[Dict[str, Any]],
        ctx: RefinementContext,
        config: Dict[str, Any]
    ) -> Tuple[float, Optional[CalibrationReason], Dict[str, float]]:
        """
        Apply calibration to confidence.

        Args:
            confidence: Original confidence value
            alternatives: List of alternative intents with confidences
            ctx: Refinement context
            config: Calibration configuration

        Returns:
            Tuple of (calibrated_confidence, reason, penalty_factors)
        """
        ...


# =============================================================================
# CALIBRATION STRATEGIES
# =============================================================================

class EntropyCalibrationStrategy:
    """
    Entropy-based confidence calibration.

    Uses Shannon entropy to estimate uncertainty from alternatives distribution.
    High entropy = high uncertainty = lower confidence.

    Formula:
        entropy = -sum(p_i * log(p_i)) for each alternative
        normalized_entropy = entropy / log(n) where n = number of alternatives

    Calibration:
        If entropy > threshold: reduce confidence proportionally
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self._config = config or {}
        self._enabled = self._config.get("enabled", True)

    @property
    def name(self) -> str:
        return "entropy"

    @property
    def enabled(self) -> bool:
        return self._enabled

    def calibrate(
        self,
        confidence: float,
        alternatives: List[Dict[str, Any]],
        ctx: RefinementContext,
        config: Dict[str, Any]
    ) -> Tuple[float, Optional[CalibrationReason], Dict[str, float]]:
        """Apply entropy-based calibration."""
        if not self._enabled or not alternatives:
            return confidence, None, {}

        # Extract confidences from alternatives
        alt_confidences = [alt.get("confidence", 0.0) for alt in alternatives]

        # Add primary confidence to distribution
        all_confidences = [confidence] + alt_confidences

        # Normalize to probability distribution
        total = sum(all_confidences)
        if total == 0:
            return confidence, None, {}

        probabilities = [c / total for c in all_confidences]

        # Calculate Shannon entropy
        entropy = 0.0
        for p in probabilities:
            if p > 0:
                entropy -= p * math.log2(p)

        # Normalize entropy (0 to 1)
        max_entropy = math.log2(len(probabilities)) if len(probabilities) > 1 else 1
        normalized_entropy = entropy / max_entropy if max_entropy > 0 else 0

        # Get thresholds from config
        entropy_threshold = config.get("entropy_threshold", 0.5)
        entropy_penalty_factor = config.get("entropy_penalty_factor", 0.15)

        # Apply penalty if entropy is high
        if normalized_entropy > entropy_threshold:
            excess_entropy = normalized_entropy - entropy_threshold
            penalty = excess_entropy * entropy_penalty_factor
            calibrated = max(0.1, confidence - penalty)

            return calibrated, CalibrationReason.ENTROPY_HIGH, {
                "entropy": normalized_entropy,
                "entropy_penalty": penalty,
            }

        return confidence, None, {"entropy": normalized_entropy}


class GapCalibrationStrategy:
    """
    Gap-based confidence calibration.

    Penalizes confidence when the gap between top-1 and top-2 is small.
    Small gap = ambiguous classification = lower confidence.

    Calibration:
        If gap < threshold: reduce confidence proportionally
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self._config = config or {}
        self._enabled = self._config.get("enabled", True)

    @property
    def name(self) -> str:
        return "gap"

    @property
    def enabled(self) -> bool:
        return self._enabled

    def calibrate(
        self,
        confidence: float,
        alternatives: List[Dict[str, Any]],
        ctx: RefinementContext,
        config: Dict[str, Any]
    ) -> Tuple[float, Optional[CalibrationReason], Dict[str, float]]:
        """Apply gap-based calibration."""
        if not self._enabled or not alternatives:
            # No alternatives = no gap info = apply small penalty
            no_alt_penalty = config.get("no_alternatives_penalty", 0.1)
            if confidence > 0.8:
                calibrated = confidence - no_alt_penalty
                return calibrated, CalibrationReason.NO_ALTERNATIVES, {
                    "no_alternatives_penalty": no_alt_penalty
                }
            return confidence, None, {}

        # Get top alternative confidence
        top_alt_confidence = max(
            alt.get("confidence", 0.0) for alt in alternatives
        )

        # Use original LLM confidence for gap measurement (avoid entropy cascade)
        original_confidence = ctx.confidence if hasattr(ctx, 'confidence') else confidence
        gap = original_confidence - top_alt_confidence

        # Get thresholds from config
        gap_threshold = config.get("gap_threshold", 0.2)
        gap_penalty_factor = config.get("gap_penalty_factor", 0.2)
        min_gap_for_high_confidence = config.get("min_gap_for_high_confidence", 0.15)

        # Apply penalty if gap is small
        if gap < gap_threshold:
            deficit = gap_threshold - gap
            penalty = deficit * gap_penalty_factor

            # Extra penalty for very high confidence with small gap
            if original_confidence >= 0.85 and gap < min_gap_for_high_confidence:
                penalty += config.get("high_confidence_small_gap_penalty", 0.1)

            calibrated = max(0.1, confidence - penalty)

            return calibrated, CalibrationReason.GAP_SMALL, {
                "gap": gap,
                "gap_penalty": penalty,
            }

        return confidence, None, {"gap": gap}


class HeuristicCalibrationStrategy:
    """
    Heuristic-based confidence calibration.

    Applies pattern-based rules for known error scenarios:
    - Short messages with high confidence
    - Specific intent patterns known to be overconfident
    - Context-based confidence adjustments

    This addresses known LLM failure modes documented in project analysis.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self._config = config or {}
        self._enabled = self._config.get("enabled", True)

    @property
    def name(self) -> str:
        return "heuristic"

    @property
    def enabled(self) -> bool:
        return self._enabled

    def calibrate(
        self,
        confidence: float,
        alternatives: List[Dict[str, Any]],
        ctx: RefinementContext,
        config: Dict[str, Any]
    ) -> Tuple[float, Optional[CalibrationReason], Dict[str, float]]:
        """Apply heuristic-based calibration."""
        if not self._enabled:
            return confidence, None, {}

        penalties = {}
        total_penalty = 0.0

        # Rule 1: Short message penalty
        # Short messages are inherently ambiguous
        short_msg_threshold = config.get("short_message_words", 3)
        short_msg_penalty = config.get("short_message_penalty", 0.15)

        word_count = len(ctx.message.strip().split())
        if word_count <= short_msg_threshold and confidence >= 0.8:
            total_penalty += short_msg_penalty
            penalties["short_message_penalty"] = short_msg_penalty

        # Rule 2: Overconfident intent patterns
        # Certain intents are known to be overconfident
        overconfident_intents = set(config.get("overconfident_intents", [
            "greeting", "farewell", "small_talk", "agreement", "gratitude"
        ]))
        overconfident_penalty = config.get("overconfident_intent_penalty", 0.1)

        if ctx.intent in overconfident_intents and confidence >= 0.85:
            total_penalty += overconfident_penalty
            penalties["overconfident_intent_penalty"] = overconfident_penalty

        # Rule 3: Misaligned context penalty
        # When intent doesn't match expected context
        context_mismatch_penalty = config.get("context_mismatch_penalty", 0.1)

        # Check for data-expecting context with non-data intent
        data_expecting_actions = set(config.get("data_expecting_actions", [
            "ask_about_company", "ask_about_problem", "ask_situation",
            "ask_problem", "ask_implication", "ask_need_payoff",
        ]))
        data_intents = set(config.get("data_intents", [
            "info_provided", "situation_provided", "problem_revealed",
            "implication_acknowledged", "need_expressed",
        ]))

        if ctx.last_action in data_expecting_actions:
            if ctx.intent not in data_intents and confidence >= 0.8:
                total_penalty += context_mismatch_penalty
                penalties["context_mismatch_penalty"] = context_mismatch_penalty

        # Rule 4: Objection with high confidence
        # Objection intents are often overconfident - lowered threshold from 0.9 to 0.8
        # FIX: Порог 0.9 был слишком высок - objection_think с confidence 0.80-0.89 не обрабатывался
        objection_intents = set(config.get("objection_intents", [
            "objection_price", "objection_no_time", "objection_think",
            "objection_no_need", "objection_competitor",
        ]))
        objection_penalty = config.get("objection_overconfidence_penalty", 0.1)

        if ctx.intent in objection_intents and confidence >= 0.8:
            # High confidence objection needs verification (threshold lowered to 0.8)
            total_penalty += objection_penalty
            penalties["objection_overconfidence_penalty"] = objection_penalty

        # Rule 5: Objection without alternatives - VERY suspicious
        # FIX: LLM часто не возвращает alternatives для objection интентов
        # Это делает entropy и gap стратегии неэффективными
        # Добавляем дополнительный штраф для objection без alternatives
        objection_no_alt_penalty = config.get("objection_no_alternatives_penalty", 0.15)
        objection_no_alt_threshold = config.get("objection_no_alternatives_threshold", 0.75)

        if (ctx.intent in objection_intents and
            not alternatives and
            confidence >= objection_no_alt_threshold):
            # Objection with no alternatives is highly suspicious
            total_penalty += objection_no_alt_penalty
            penalties["objection_no_alternatives_penalty"] = objection_no_alt_penalty

        # Apply total penalty
        if total_penalty > 0:
            calibrated = max(0.1, confidence - total_penalty)
            return calibrated, CalibrationReason.HEURISTIC_MATCH, penalties

        return confidence, None, {}


# =============================================================================
# CONFIDENCE CALIBRATOR
# =============================================================================

class ConfidenceCalibrator:
    """
    Combines multiple calibration strategies.

    Applies all enabled strategies and combines their effects:
    - Sequential application (each strategy refines previous result)
    - Configurable combination weights
    - Floor and ceiling for final confidence

    Usage:
        calibrator = ConfidenceCalibrator(config)
        result = calibrator.calibrate(confidence, alternatives, ctx)
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self._config = config or self._load_default_config()

        # Initialize strategies
        self._strategies: List[ICalibrationStrategy] = []
        self._init_strategies()

        # Statistics
        self._calibrations_total = 0
        self._calibrations_applied = 0
        self._total_delta = 0.0
        self._calibrations_by_reason: Dict[str, int] = {}

    def _load_default_config(self) -> Dict[str, Any]:
        """Load configuration from YAML."""
        try:
            from src.yaml_config.constants import get_confidence_calibration_config
            return get_confidence_calibration_config()
        except (ImportError, AttributeError):
            logger.warning(
                "Could not load confidence_calibration config, using defaults"
            )
            return self._get_fallback_config()

    def _get_fallback_config(self) -> Dict[str, Any]:
        """Fallback configuration if YAML not available."""
        return {
            "enabled": True,
            "min_confidence_floor": 0.1,
            "max_confidence_ceiling": 0.95,

            # Entropy strategy
            "entropy_enabled": True,
            "entropy_threshold": 0.5,
            "entropy_penalty_factor": 0.15,

            # Gap strategy
            "gap_enabled": True,
            "gap_threshold": 0.2,
            "gap_penalty_factor": 0.2,
            "no_alternatives_penalty": 0.1,
            "min_gap_for_high_confidence": 0.15,
            "high_confidence_small_gap_penalty": 0.1,

            # Heuristic strategy
            "heuristic_enabled": True,
            "short_message_words": 3,
            "short_message_penalty": 0.15,
            "overconfident_intent_penalty": 0.1,
            "context_mismatch_penalty": 0.1,
            "objection_overconfidence_penalty": 0.1,
            "overconfident_intents": [
                "greeting", "farewell", "small_talk", "agreement", "gratitude"
            ],
            "data_expecting_actions": [
                "ask_about_company", "ask_about_problem", "ask_situation",
                "ask_problem", "ask_implication", "ask_need_payoff",
            ],
            "data_intents": [
                "info_provided", "situation_provided", "problem_revealed",
                "implication_acknowledged", "need_expressed",
            ],
            "objection_intents": [
                "objection_price", "objection_no_time", "objection_think",
                "objection_no_need", "objection_competitor",
            ],
            # Rule 5: Objection without alternatives (FIX for LLM not returning alternatives)
            "objection_no_alternatives_penalty": 0.15,
            "objection_no_alternatives_threshold": 0.75,
        }

    def _init_strategies(self) -> None:
        """Initialize calibration strategies based on config."""
        if self._config.get("entropy_enabled", True):
            self._strategies.append(EntropyCalibrationStrategy({
                "enabled": self._config.get("entropy_enabled", True),
            }))

        if self._config.get("gap_enabled", True):
            self._strategies.append(GapCalibrationStrategy({
                "enabled": self._config.get("gap_enabled", True),
            }))

        if self._config.get("heuristic_enabled", True):
            self._strategies.append(HeuristicCalibrationStrategy({
                "enabled": self._config.get("heuristic_enabled", True),
            }))

    def calibrate(
        self,
        confidence: float,
        alternatives: List[Dict[str, Any]],
        ctx: RefinementContext
    ) -> CalibrationResult:
        """
        Apply all calibration strategies.

        Args:
            confidence: Original LLM confidence
            alternatives: Alternative intents with confidences
            ctx: Refinement context

        Returns:
            CalibrationResult with calibrated confidence and metadata
        """
        self._calibrations_total += 1

        # Start with original confidence
        current_confidence = confidence
        all_reasons: List[CalibrationReason] = []
        all_penalties: Dict[str, float] = {}
        entropy_value = None
        gap_value = None

        # Apply each strategy
        for strategy in self._strategies:
            if not strategy.enabled:
                continue

            calibrated, reason, penalties = strategy.calibrate(
                current_confidence, alternatives, ctx, self._config
            )

            if reason:
                current_confidence = calibrated
                all_reasons.append(reason)
                all_penalties.update(penalties)

            # Capture entropy and gap values
            if "entropy" in penalties:
                entropy_value = penalties["entropy"]
            if "gap" in penalties:
                gap_value = penalties["gap"]

        # Apply floor and ceiling
        min_floor = self._config.get("min_confidence_floor", 0.1)
        max_ceiling = self._config.get("max_confidence_ceiling", 0.95)
        current_confidence = max(min_floor, min(max_ceiling, current_confidence))

        # Build result
        calibration_applied = len(all_reasons) > 0
        if calibration_applied:
            self._calibrations_applied += 1
            self._total_delta += (confidence - current_confidence)

            # Track reasons
            final_reason = (
                CalibrationReason.COMBINED if len(all_reasons) > 1
                else all_reasons[0]
            )
            reason_key = final_reason.value
            self._calibrations_by_reason[reason_key] = (
                self._calibrations_by_reason.get(reason_key, 0) + 1
            )

        return CalibrationResult(
            original_confidence=confidence,
            calibrated_confidence=current_confidence,
            calibration_applied=calibration_applied,
            reasons=all_reasons,
            entropy=entropy_value,
            gap=gap_value,
            penalty_factors=all_penalties,
        )

    def get_stats(self) -> Dict[str, Any]:
        """Get calibrator statistics."""
        avg_delta = (
            self._total_delta / self._calibrations_applied
            if self._calibrations_applied > 0 else 0.0
        )

        return {
            "calibrations_total": self._calibrations_total,
            "calibrations_applied": self._calibrations_applied,
            "calibration_rate": (
                self._calibrations_applied / self._calibrations_total
                if self._calibrations_total > 0 else 0.0
            ),
            "avg_confidence_delta": avg_delta,
            "calibrations_by_reason": dict(self._calibrations_by_reason),
            "strategies_enabled": [s.name for s in self._strategies if s.enabled],
        }


# =============================================================================
# CONFIDENCE CALIBRATION LAYER
# =============================================================================

@register_refinement_layer("confidence_calibration")
class ConfidenceCalibrationLayer(BaseRefinementLayer):
    """
    Refinement layer for scientific confidence calibration.

    Integrates with RefinementPipeline to apply post-hoc calibration
    to LLM-generated confidence values.

    Key Features:
        - Entropy-based uncertainty estimation
        - Gap-based ambiguity detection
        - Heuristic pattern matching for known errors
        - Configurable via YAML
        - Full statistics tracking

    Priority: CRITICAL (runs first, before other refinement layers)

    This layer is crucial because subsequent layers and disambiguation
    logic depend on accurate confidence values.
    """

    LAYER_NAME: ClassVar[str] = "confidence_calibration"
    LAYER_PRIORITY: ClassVar[LayerPriority] = LayerPriority.CRITICAL
    FEATURE_FLAG: ClassVar[Optional[str]] = "confidence_calibration"

    def __init__(self):
        # Initialize calibrator before calling super().__init__()
        # because _get_config() may be called during initialization
        self._calibrator: Optional[ConfidenceCalibrator] = None
        super().__init__()

        # Initialize calibrator with loaded config
        self._calibrator = ConfidenceCalibrator(self._config)

    def _get_config(self) -> Dict[str, Any]:
        """Load confidence calibration configuration."""
        try:
            from src.yaml_config.constants import get_confidence_calibration_config
            return get_confidence_calibration_config()
        except (ImportError, AttributeError):
            return {}

    def _should_apply(self, ctx: RefinementContext) -> bool:
        """
        Check if calibration should be applied.

        Calibration applies to all classifications, but with varying intensity
        based on the confidence level and context.
        """
        # Always apply calibration - the strategies will decide what to do
        return True

    def _do_refine(
        self,
        message: str,
        result: Dict[str, Any],
        ctx: RefinementContext
    ) -> RefinementResult:
        """
        Apply confidence calibration.

        Args:
            message: User's message
            result: Classification result with confidence and alternatives
            ctx: Refinement context

        Returns:
            RefinementResult with calibrated confidence
        """
        original_confidence = result.get("confidence", 0.0)
        alternatives = result.get("alternatives", [])

        # Apply calibration
        calibration = self._calibrator.calibrate(
            original_confidence, alternatives, ctx
        )

        if not calibration.calibration_applied:
            # No calibration needed
            return self._pass_through(result, ctx)

        # Log significant calibrations
        if calibration.confidence_delta >= 0.1:
            logger.info(
                "Significant confidence calibration applied",
                extra={
                    "layer": self.name,
                    "original_confidence": calibration.original_confidence,
                    "calibrated_confidence": calibration.calibrated_confidence,
                    "delta": calibration.confidence_delta,
                    "reasons": [r.value for r in calibration.reasons],
                    "intent": ctx.intent,
                    "log_message": message[:50],
                }
            )

        # Build reason string
        reason_parts = [r.value for r in calibration.reasons]
        reason_str = "calibration:" + "+".join(reason_parts)

        # Create refined result with calibrated confidence
        return RefinementResult(
            decision=RefinementDecision.REFINED,
            intent=ctx.intent,  # Intent stays the same
            confidence=calibration.calibrated_confidence,
            original_intent=None,  # Not changing intent
            refinement_reason=reason_str,
            layer_name=self.name,
            extracted_data=result.get("extracted_data", {}),
            pre_calibration_confidence=calibration.original_confidence,
            metadata={
                "calibration": calibration.to_dict(),
                "original_confidence": calibration.original_confidence,
            },
        )

    def get_stats(self) -> Dict[str, Any]:
        """Get layer statistics including calibrator stats."""
        stats = super().get_stats()

        if self._calibrator:
            stats["calibrator_stats"] = self._calibrator.get_stats()

        return stats


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def calculate_entropy(confidences: List[float]) -> float:
    """
    Calculate normalized Shannon entropy from confidence distribution.

    Args:
        confidences: List of confidence values

    Returns:
        Normalized entropy (0 to 1)
    """
    if not confidences:
        return 0.0

    total = sum(confidences)
    if total == 0:
        return 0.0

    probabilities = [c / total for c in confidences]

    entropy = 0.0
    for p in probabilities:
        if p > 0:
            entropy -= p * math.log2(p)

    max_entropy = math.log2(len(probabilities)) if len(probabilities) > 1 else 1
    return entropy / max_entropy if max_entropy > 0 else 0.0


def calculate_gap(primary: float, alternatives: List[float]) -> float:
    """
    Calculate gap between primary confidence and highest alternative.

    Args:
        primary: Primary intent confidence
        alternatives: List of alternative confidences

    Returns:
        Gap value (primary - max(alternatives))
    """
    if not alternatives:
        return 1.0  # No alternatives = maximum gap

    top_alt = max(alternatives)
    return primary - top_alt


# =============================================================================
# MODULE INITIALIZATION
# =============================================================================

logger.debug("ConfidenceCalibrationLayer registered with RefinementPipeline")
