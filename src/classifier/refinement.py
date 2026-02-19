"""
Classification Refinement Layer.

Context-aware refinement of LLM classification results for short messages.
Uses short_answer_classification from constants.yaml.

This module addresses the State Loop bug where short answers like "1", "да", "первое"
are incorrectly classified as "greeting" by LLM, causing the bot to get stuck.

Architecture:
    - Runs AFTER LLMClassifier
    - Uses SPIN_SHORT_ANSWER_CLASSIFICATION from constants.yaml
    - Only refines when strong contextual signals are present
    - Falls back to original result on any error (fail-safe)

Usage:
    from src.classifier.refinement import ClassificationRefinementLayer, RefinementContext

    layer = ClassificationRefinementLayer()
    context = RefinementContext(
        message="1",
        spin_phase="situation",
        state="greeting",
        last_action="ask_about_company",
        last_intent=None
    )
    refined_result = layer.refine(message, llm_result, context)
"""

from dataclasses import dataclass
from typing import Optional, Set, Dict, Any, Tuple, List
import logging
import re

from src.yaml_config.constants import get_short_answer_config

logger = logging.getLogger(__name__)


@dataclass
class RefinementContext:
    """
    Context for classification refinement.

    Attributes:
        message: The user's message text
        spin_phase: Current SPIN phase (situation, problem, implication, need_payoff)
        state: Current state machine state
        last_action: Last action performed by the bot
        last_intent: Previous intent from the user
    """
    message: str
    spin_phase: Optional[str]
    state: Optional[str]
    last_action: Optional[str]
    last_intent: Optional[str]


class ClassificationRefinementLayer:
    """
    Refines LLM classification results using contextual signals.

    This layer addresses a specific problem: LLM classifiers often misclassify
    short answers (like "1", "да", "первое") as "greeting" when they should be
    classified based on the conversation context.

    The refinement logic:
    1. Check if the message is short (< 5 words or < 20 chars)
    2. Check if LLM returned a "low-signal" intent (greeting, unclear, etc.)
    3. Check if we have SPIN phase context or awaiting_data action
    4. If all conditions met, use short_answer_classification from constants.yaml

    Thread Safety:
        This class is thread-safe as it only reads from configuration.

    Example:
        >>> layer = ClassificationRefinementLayer()
        >>> ctx = RefinementContext(message="1", spin_phase="situation", ...)
        >>> result = layer.refine("1", {"intent": "greeting"}, ctx)
        >>> result["intent"]
        'situation_provided'
    """

    # Intents that may need refinement (low-signal in short message context)
    LOW_SIGNAL_INTENTS: Set[str] = {
        "greeting",
        "unclear",
        "small_talk",
        "gratitude",
    }

    # Actions that indicate we're awaiting data from the user
    AWAITING_DATA_ACTIONS: Set[str] = {
        "ask_about_company",
        "ask_about_problem",
        "ask_about_impact",
        "ask_about_outcome",
        "ask_for_clarification",
        "ask_situation",
        "ask_problem",
        "ask_implication",
        "ask_need_payoff",
        "transition_to_spin_situation",
        "transition_to_spin_problem",
        "transition_to_spin_implication",
        "transition_to_spin_need_payoff",
        "continue_current_goal",
        "clarify_one_question",
    }

    # Short message thresholds
    MAX_SHORT_WORDS: int = 5
    MAX_SHORT_CHARS: int = 25

    # Patterns for sentiment detection
    NEGATIVE_PATTERNS: List[str] = [
        r"\bнет\b",
        r"\bне\s+надо\b",
        r"\bне\s+нужно\b",
        r"\bне\s+интересно\b",
        r"\bникак\b",
        r"\bничего\b",
        r"\bотказ",
        r"\bне\s+хочу\b",
        r"\bне\s+буду\b",
    ]

    POSITIVE_PATTERNS: List[str] = [
        r"\bда\b",
        r"\bок\b",
        r"\bокей\b",
        r"\bхорошо\b",
        r"\bсогласен\b",
        r"\bверно\b",
        r"\bточно\b",
        r"\bконечно\b",
        r"\bага\b",
        r"\bугу\b",
        r"\bпервое\b",
        r"\bвторое\b",
        r"\bтретье\b",
        r"\bлад",  # ладно
        r"\bдавай",
    ]

    def __init__(self):
        """Initialize the refinement layer with configuration from constants.yaml."""
        self._short_answer_config = get_short_answer_config()
        self._negative_regex = re.compile(
            "|".join(self.NEGATIVE_PATTERNS),
            re.IGNORECASE
        )
        self._positive_regex = re.compile(
            "|".join(self.POSITIVE_PATTERNS),
            re.IGNORECASE
        )

        logger.debug(
            "ClassificationRefinementLayer initialized",
            extra={
                "phases_configured": list(self._short_answer_config.keys()),
                "low_signal_intents": list(self.LOW_SIGNAL_INTENTS),
            }
        )

    def should_refine(
        self,
        message: str,
        llm_intent: str,
        context: RefinementContext
    ) -> bool:
        """
        Determine if classification should be refined.

        Returns True if ALL conditions are met:
        1. Message is short (< MAX_SHORT_WORDS words or < MAX_SHORT_CHARS chars)
        2. LLM returned a low-signal intent (greeting, unclear, etc.)
        3. We have contextual signals (SPIN phase or awaiting_data action)

        Args:
            message: User's message text
            llm_intent: Intent returned by LLM classifier
            context: Refinement context with state information

        Returns:
            True if refinement should be applied, False otherwise
        """
        # Check 1: Is message short?
        if not self._is_short_message(message):
            return False

        # Check 2: Did LLM return low-signal intent?
        if llm_intent not in self.LOW_SIGNAL_INTENTS:
            return False

        # Check 3: Do we have context that suggests we're collecting data?
        has_phase_context = (
            context.spin_phase is not None and
            context.spin_phase in self._short_answer_config
        )
        has_action_context = context.last_action in self.AWAITING_DATA_ACTIONS

        # Also check if we're in greeting state (common stuck scenario)
        is_greeting_state = context.state == "greeting"

        return has_phase_context or has_action_context or is_greeting_state

    def refine(
        self,
        message: str,
        llm_result: Dict[str, Any],
        context: RefinementContext
    ) -> Dict[str, Any]:
        """
        Refine classification result using context.

        If refinement conditions are not met, returns the original result unchanged.
        If refinement fails for any reason, returns the original result (fail-safe).

        Args:
            message: User's message text
            llm_result: Original LLM classification result dict
            context: Refinement context with state information

        Returns:
            Refined result dict (or original if refinement not applicable)
        """
        llm_intent = llm_result.get("intent", "unclear")

        # Check if we should refine
        if not self.should_refine(message, llm_intent, context):
            return llm_result

        try:
            # Get refined intent from short_answer_classification
            refined = self._get_refined_intent(message, context)

            if refined is None:
                logger.debug(
                    "Refinement not applicable - no matching config",
                    extra={
                        "log_message": message[:50],
                        "llm_intent": llm_intent,
                        "phase": context.spin_phase,
                        "state": context.state,
                    }
                )
                return llm_result

            refined_intent, refined_confidence = refined

            logger.info(
                "Classification refined",
                extra={
                    "original_intent": llm_intent,
                    "refined_intent": refined_intent,
                    "confidence": refined_confidence,
                    "phase": context.spin_phase,
                    "state": context.state,
                    "log_message": message[:50],
                    "reason": f"short_answer_in_{context.spin_phase or context.state}_context",
                }
            )

            # Create refined result (preserve all original fields)
            result = llm_result.copy()
            result["intent"] = refined_intent
            result["confidence"] = refined_confidence
            result["refined"] = True
            result["original_intent"] = llm_intent
            result["original_confidence"] = llm_result.get("confidence", 0.0)
            result["refinement_reason"] = (
                f"short_answer_in_{context.spin_phase or 'unknown'}_phase"
            )

            return result

        except Exception as e:
            # Fail-safe: return original result on any error
            logger.warning(
                "Refinement failed, returning original result",
                extra={
                    "error": str(e),
                    "log_message": message[:50],
                    "llm_intent": llm_intent,
                }
            )
            return llm_result

    def _is_short_message(self, message: str) -> bool:
        """
        Check if message is short enough for refinement.

        A message is considered short if:
        - It has <= MAX_SHORT_WORDS words, OR
        - It has <= MAX_SHORT_CHARS characters (after stripping)

        Args:
            message: User's message text

        Returns:
            True if message is short, False otherwise
        """
        stripped = message.strip()
        words = stripped.split()

        return (
            len(words) <= self.MAX_SHORT_WORDS or
            len(stripped) <= self.MAX_SHORT_CHARS
        )

    def _get_refined_intent(
        self,
        message: str,
        context: RefinementContext
    ) -> Optional[Tuple[str, float]]:
        """
        Get refined intent based on message sentiment and phase.

        Uses short_answer_classification from constants.yaml to determine
        the appropriate intent based on:
        1. Current SPIN phase
        2. Message sentiment (positive/negative/neutral)

        Args:
            message: User's message text
            context: Refinement context

        Returns:
            Tuple of (intent, confidence) or None if not applicable
        """
        # Determine which phase config to use
        phase = context.spin_phase

        # If no phase but we're in greeting, use "situation" as default
        if not phase and context.state == "greeting":
            phase = "situation"

        if not phase or phase not in self._short_answer_config:
            return None

        phase_config = self._short_answer_config[phase]

        # Detect sentiment (positive/negative/neutral)
        sentiment = self._detect_sentiment(message)

        if sentiment == "positive":
            intent = phase_config.get("positive_intent")
            confidence = phase_config.get("positive_confidence", 0.7)
            if intent:
                return (intent, confidence)

        elif sentiment == "negative":
            intent = phase_config.get("negative_intent")
            confidence = phase_config.get("negative_confidence", 0.7)
            if intent:
                return (intent, confidence)

        # Neutral/unclear → default to positive for data collection
        # (most short answers are responses to questions, not rejections)
        if sentiment == "neutral":
            intent = phase_config.get("positive_intent")
            # Lower confidence for neutral sentiment
            confidence = phase_config.get("positive_confidence", 0.7) * 0.85
            if intent:
                return (intent, confidence)

        return None

    def _detect_sentiment(self, message: str) -> str:
        """
        Detect sentiment of short message.

        Uses pattern matching optimized for Russian short answers.

        Args:
            message: User's message text

        Returns:
            "positive", "negative", or "neutral"
        """
        text = message.lower().strip()

        # Check negative patterns first (they're more specific)
        if self._negative_regex.search(text):
            return "negative"

        # Check positive patterns
        if self._positive_regex.search(text):
            return "positive"

        # Numbers are typically positive (answering data questions)
        # e.g., "5", "10 человек", "1"
        if re.search(r'\d+', text):
            return "positive"

        # Single word answers are typically informative responses
        words = text.split()
        if len(words) == 1 and len(text) > 0:
            # Single word, not matching any pattern → likely neutral info
            return "neutral"

        # Very short messages without clear patterns
        if len(text) <= 10:
            return "neutral"

        return "neutral"


# Convenience function for external use
def create_refinement_context(
    message: str,
    context: Optional[Dict[str, Any]] = None
) -> RefinementContext:
    """
    Create RefinementContext from a classifier context dict.

    Args:
        message: User's message text
        context: Optional dict with state, spin_phase, last_action, last_intent

    Returns:
        RefinementContext instance
    """
    context = context or {}
    return RefinementContext(
        message=message,
        spin_phase=context.get("spin_phase"),
        state=context.get("state"),
        last_action=context.get("last_action"),
        last_intent=context.get("last_intent"),
    )
