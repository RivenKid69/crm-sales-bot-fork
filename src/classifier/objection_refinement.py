"""
Objection Classification Refinement Layer.

Context-aware validation and refinement of objection classifications.
Prevents false-positive objection detection by checking:
- Topic alignment with bot's last question
- Question markers in message
- Interest patterns vs real objections
- Confidence thresholds

This module addresses the Objection Stuck bug where messages like
"бюджет пока не определён" are incorrectly classified as "objection_price"
when the bot just asked about budget (making it an answer, not an objection).

Architecture:
    - Runs AFTER ClassificationRefinementLayer
    - Uses objection_refinement config from constants.yaml
    - Only refines objection_* intents
    - Falls back to original result on any error (fail-safe)

Part of Phase 5: Objection Stuck Fix (OBJECTION_STUCK_FIX_PLAN.md)

Usage:
    from src.classifier.objection_refinement import (
        ObjectionRefinementLayer,
        ObjectionRefinementContext
    )

    layer = ObjectionRefinementLayer()
    context = ObjectionRefinementContext(
        message="бюджет пока не определён",
        intent="objection_price",
        confidence=0.75,
        last_bot_message="Какой у вас бюджет?",
        last_action="ask_about_budget",
        state="presentation",
        turn_number=5,
        last_objection_turn=None,
        last_objection_type=None,
    )
    refined_result = layer.refine(message, llm_result, context)
"""

from dataclasses import dataclass
from typing import Optional, Set, Dict, Any, List
import re
import logging

from src.yaml_config.constants import get_objection_refinement_config, OBJECTION_INTENTS

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ObjectionRefinementContext:
    """
    Immutable context for objection refinement.

    Attributes:
        message: The user's message text
        intent: Classified intent (objection_*)
        confidence: Classification confidence (0.0-1.0)
        last_bot_message: Last message from the bot (for topic alignment)
        last_action: Last action performed by the bot
        state: Current state machine state
        turn_number: Current turn number in conversation
        last_objection_turn: Turn number of last objection (for cooldown)
        last_objection_type: Type of last objection (for same-type cooldown)
    """
    message: str
    intent: str
    confidence: float
    last_bot_message: Optional[str]
    last_action: Optional[str]
    state: str
    turn_number: int
    last_objection_turn: Optional[int]
    last_objection_type: Optional[str]


@dataclass
class RefinementResult:
    """
    Result of objection refinement decision.

    Attributes:
        intent: Final intent (refined or original)
        confidence: Final confidence
        refined: Whether refinement was applied
        original_intent: Original intent before refinement (if refined)
        refinement_reason: Reason code for refinement (if refined)
    """
    intent: str
    confidence: float
    refined: bool
    original_intent: Optional[str] = None
    refinement_reason: Optional[str] = None


class ObjectionRefinementLayer:
    """
    Refines objection classifications using contextual signals.

    This layer addresses false-positive objection detection by checking:
    1. Topic alignment - if bot asked about budget and user mentions budget,
       it's likely an answer, not an objection
    2. Question markers - messages with "?" or question words are questions
    3. Callback patterns - "позвоните завтра" is callback_request, not objection
    4. Interest patterns - "подумать над предложением" shows interest

    Thread Safety:
        This class is thread-safe as it only reads from configuration.

    Design Principles:
        - Configuration-Driven: All rules from YAML (constants.yaml)
        - Fail-Safe: Never crashes, returns original on error
        - Observable: Logs all refinement decisions with structured data
        - SOLID: Single responsibility - objection validation only

    Example:
        >>> layer = ObjectionRefinementLayer()
        >>> ctx = ObjectionRefinementContext(
        ...     message="бюджет пока не определён",
        ...     intent="objection_price",
        ...     confidence=0.75,
        ...     last_action="ask_about_budget",
        ...     ...
        ... )
        >>> result = layer.refine(ctx.message, {"intent": "objection_price"}, ctx)
        >>> result["intent"]
        'info_provided'  # Refined because bot asked about budget
    """

    def __init__(self):
        """Initialize the refinement layer with configuration from constants.yaml."""
        self._config = get_objection_refinement_config()
        self._enabled = self._config.get("enabled", True)
        self._min_confidence = self._config.get("min_confidence_to_accept", 0.85)
        self._question_markers = set(self._config.get("question_markers", []))
        self._callback_patterns = self._config.get("callback_patterns", [])
        self._interest_patterns = self._config.get("interest_patterns", [])
        self._uncertainty_patterns = self._config.get("uncertainty_patterns", [])
        self._refinement_mapping = self._config.get("refinement_mapping", {})
        self._topic_actions = self._config.get("topic_alignment_actions", {})
        self._cooldown = self._config.get("cooldown", {})

        # Compile patterns for efficiency
        self._callback_regex = self._compile_patterns(self._callback_patterns)
        self._interest_regex = self._compile_patterns(self._interest_patterns)
        self._uncertainty_regex = self._compile_patterns(self._uncertainty_patterns)

        # Stats for monitoring
        self._refinements_total = 0
        self._refinements_by_type: Dict[str, int] = {}
        self._refinements_by_reason: Dict[str, int] = {}

        # Convert OBJECTION_INTENTS to set for O(1) lookup
        self._objection_intents: Set[str] = set(OBJECTION_INTENTS)

        logger.debug(
            "ObjectionRefinementLayer initialized",
            extra={
                "enabled": self._enabled,
                "min_confidence": self._min_confidence,
                "objection_types": len(self._objection_intents),
                "callback_patterns": len(self._callback_patterns),
                "interest_patterns": len(self._interest_patterns),
                "uncertainty_patterns": len(self._uncertainty_patterns),
            }
        )

    @staticmethod
    def _compile_patterns(patterns: List[str]) -> re.Pattern:
        """
        Compile list of patterns into single regex for efficient matching.

        Args:
            patterns: List of pattern strings

        Returns:
            Compiled regex pattern (case-insensitive)
        """
        if not patterns:
            return re.compile(r"^$")  # Never matches
        escaped = [re.escape(p) for p in patterns]
        return re.compile("|".join(escaped), re.IGNORECASE)

    def should_refine(self, ctx: ObjectionRefinementContext) -> bool:
        """
        Determine if classification should be refined.

        Returns True if:
        1. Layer is enabled
        2. Intent is objection_*
        3. Confidence is below threshold OR refinement signals present

        High confidence objections without context issues are accepted as-is.

        Args:
            ctx: ObjectionRefinementContext with classification info

        Returns:
            True if refinement should be considered, False otherwise
        """
        if not self._enabled:
            return False

        if ctx.intent not in self._objection_intents:
            return False

        # High confidence objections with no context issues → accept as-is
        if ctx.confidence >= self._min_confidence:
            # Even high confidence should be checked for question markers
            # and topic alignment
            if not self._has_question_markers(ctx.message):
                if not self._is_topic_aligned(ctx):
                    return False

        return True

    def refine(
        self,
        message: str,
        llm_result: Dict[str, Any],
        ctx: ObjectionRefinementContext
    ) -> Dict[str, Any]:
        """
        Refine objection classification using context.

        If refinement conditions are not met, returns the original result unchanged.
        If refinement fails for any reason, returns the original result (fail-safe).

        Args:
            message: User's message text
            llm_result: Original LLM classification result dict
            ctx: Refinement context with classification info

        Returns:
            Refined result dict (or original if refinement not applicable)
        """
        try:
            if not self.should_refine(ctx):
                return llm_result

            # Apply refinement rules
            result = self._apply_refinement_rules(ctx)

            if result.refined:
                # Update stats
                self._refinements_total += 1
                self._refinements_by_type[ctx.intent] = (
                    self._refinements_by_type.get(ctx.intent, 0) + 1
                )
                if result.refinement_reason:
                    self._refinements_by_reason[result.refinement_reason] = (
                        self._refinements_by_reason.get(result.refinement_reason, 0) + 1
                    )

                logger.info(
                    "Objection refined",
                    extra={
                        "original_intent": ctx.intent,
                        "refined_intent": result.intent,
                        "reason": result.refinement_reason,
                        "original_confidence": ctx.confidence,
                        "refined_confidence": result.confidence,
                        "log_message": message[:50],
                        "state": ctx.state,
                        "last_action": ctx.last_action,
                    }
                )

                # Create refined result (preserve all original fields)
                refined_result = llm_result.copy()
                refined_result["intent"] = result.intent
                refined_result["confidence"] = result.confidence
                refined_result["refined"] = True
                refined_result["original_intent"] = ctx.intent
                refined_result["original_confidence"] = ctx.confidence
                refined_result["refinement_reason"] = result.refinement_reason
                refined_result["refinement_layer"] = "objection"

                return refined_result

            return llm_result

        except Exception as e:
            # Fail-safe: return original result on any error
            logger.warning(
                "Objection refinement failed, returning original result",
                extra={
                    "error": str(e),
                    "user_message": message[:50],
                    "intent": ctx.intent,
                },
                exc_info=True
            )
            return llm_result

    def _apply_refinement_rules(self, ctx: ObjectionRefinementContext) -> RefinementResult:
        """
        Apply refinement rules in priority order.

        Rules are checked in order of specificity/reliability:
        1. Topic alignment (most reliable - bot just asked about this)
        2. Question markers (message is a question, not objection)
        3. Callback patterns (objection_no_time → callback_request)
        4. Interest patterns (objection_think → interest)
        5. Uncertainty patterns (objection_think → question)
           FIX: Root Cause #2 - skeptic phrases like "не уверен нужно ли"

        Args:
            ctx: ObjectionRefinementContext

        Returns:
            RefinementResult with decision
        """
        # Rule 1: Topic alignment (bot asked about this topic)
        # If bot just asked about budget and user mentions budget,
        # it's an answer to the question, not an objection
        if self._is_topic_aligned(ctx):
            alternative = self._get_topic_alternative(ctx)
            if alternative:
                return RefinementResult(
                    intent=alternative,
                    confidence=0.75,
                    refined=True,
                    original_intent=ctx.intent,
                    refinement_reason="topic_alignment"
                )

        # Rule 2: Question markers
        # Messages with "?" or question words are questions, not objections
        if self._has_question_markers(ctx.message):
            alternative = self._get_question_alternative(ctx)
            if alternative:
                return RefinementResult(
                    intent=alternative,
                    confidence=0.7,
                    refined=True,
                    original_intent=ctx.intent,
                    refinement_reason="question_markers"
                )

        # Rule 3: Callback patterns (objection_no_time → callback_request)
        # "сейчас занят, позвоните завтра" is a callback request
        if ctx.intent == "objection_no_time":
            if self._callback_regex.search(ctx.message):
                return RefinementResult(
                    intent="callback_request",
                    confidence=0.8,
                    refined=True,
                    original_intent=ctx.intent,
                    refinement_reason="callback_pattern"
                )

        # Rule 4: Interest patterns (objection_think → interest)
        # "подумать над предложением" shows interest, not objection
        if ctx.intent == "objection_think":
            if self._interest_regex.search(ctx.message):
                return RefinementResult(
                    intent="question_features",
                    confidence=0.7,
                    refined=True,
                    original_intent=ctx.intent,
                    refinement_reason="interest_pattern"
                )

        # Rule 5: Uncertainty patterns (objection_think → question)
        # FIX: Root Cause #2 - skeptic personas use phrases like "не уверен нужно ли"
        # which are implicit questions, not real objections.
        # "зачем это нужно" (without "?") should be treated as question
        if ctx.intent == "objection_think":
            if self._uncertainty_regex.search(ctx.message):
                alternative = self._get_uncertainty_alternative(ctx)
                return RefinementResult(
                    intent=alternative,
                    confidence=0.7,
                    refined=True,
                    original_intent=ctx.intent,
                    refinement_reason="uncertainty_pattern"
                )

        # Rule 6: Cooldown violation (optional - just log)
        if self._violates_cooldown(ctx):
            logger.debug(
                "Objection within cooldown period",
                extra={
                    "intent": ctx.intent,
                    "turn": ctx.turn_number,
                    "last_objection_turn": ctx.last_objection_turn,
                }
            )
            # Note: We don't refine based on cooldown alone,
            # just log for monitoring

        # No refinement needed - keep original
        return RefinementResult(
            intent=ctx.intent,
            confidence=ctx.confidence,
            refined=False
        )

    def _has_question_markers(self, message: str) -> bool:
        """
        Check if message contains question markers.

        Question markers indicate the message is a question, not an objection.
        E.g., "бюджет какой нужен?" is a price question, not objection_price.

        Args:
            message: User's message text

        Returns:
            True if message contains question markers
        """
        text = message.lower()

        # Direct question mark
        if "?" in message:
            return True

        # Question words from config
        for marker in self._question_markers:
            if marker in text:
                return True

        return False

    def _is_topic_aligned(self, ctx: ObjectionRefinementContext) -> bool:
        """
        Check if objection topic aligns with bot's last question.

        If bot asked about budget and user mentions budget,
        it's likely an answer, not an objection.

        Args:
            ctx: ObjectionRefinementContext

        Returns:
            True if topic is aligned (likely answer, not objection)
        """
        if not ctx.last_action:
            return False

        # Get objection topic
        topic = self._get_objection_topic(ctx.intent)
        if not topic:
            return False

        # Check if last action was about this topic
        topic_actions = self._topic_actions.get(topic, [])
        return ctx.last_action in topic_actions

    def _get_objection_topic(self, intent: str) -> Optional[str]:
        """
        Map objection intent to topic name.

        Args:
            intent: Objection intent name

        Returns:
            Topic name or None
        """
        topic_map = {
            "objection_price": "budget",
            "objection_no_time": "time",
            "objection_competitor": "competitor",
            "objection_complexity": "complexity",
            "objection_timing": "time",
        }
        return topic_map.get(intent)

    def _get_topic_alternative(self, ctx: ObjectionRefinementContext) -> Optional[str]:
        """
        Get alternative intent based on topic alignment.

        Args:
            ctx: ObjectionRefinementContext

        Returns:
            Alternative intent name or None
        """
        mapping = self._refinement_mapping.get(ctx.intent, {})
        return mapping.get("info_context", "info_provided")

    def _get_question_alternative(self, ctx: ObjectionRefinementContext) -> Optional[str]:
        """
        Get alternative intent for question context.

        Args:
            ctx: ObjectionRefinementContext

        Returns:
            Alternative intent name or None
        """
        mapping = self._refinement_mapping.get(ctx.intent, {})
        return mapping.get("question_context")

    def _get_uncertainty_alternative(self, ctx: ObjectionRefinementContext) -> str:
        """
        Get alternative intent for uncertainty context.

        Handles skeptic personas who express uncertainty without explicit question words.
        E.g., "не уверен нужно ли" is an implicit question about value proposition.

        Args:
            ctx: ObjectionRefinementContext

        Returns:
            Alternative intent name (defaults to question_features)
        """
        mapping = self._refinement_mapping.get(ctx.intent, {})
        # Try uncertainty_context first, fall back to question_context
        alternative = mapping.get("uncertainty_context")
        if alternative:
            return alternative
        alternative = mapping.get("question_context")
        if alternative:
            return alternative
        # Default for objection_think uncertainty
        return "question_features"

    def _violates_cooldown(self, ctx: ObjectionRefinementContext) -> bool:
        """
        Check if objection violates cooldown rules.

        Cooldown prevents rapid-fire objection detection which may indicate
        false positives or user frustration.

        Args:
            ctx: ObjectionRefinementContext

        Returns:
            True if cooldown is violated
        """
        if ctx.last_objection_turn is None:
            return False

        turns_since = ctx.turn_number - ctx.last_objection_turn
        min_turns = self._cooldown.get("min_turns_between_objections", 2)

        if turns_since < min_turns:
            return True

        # Same type cooldown
        if ctx.last_objection_type == ctx.intent:
            min_same = self._cooldown.get("min_turns_same_type", 3)
            if turns_since < min_same:
                return True

        return False

    def get_stats(self) -> Dict[str, Any]:
        """
        Get refinement statistics for monitoring.

        Returns:
            Dict with refinement statistics
        """
        return {
            "refinements_total": self._refinements_total,
            "refinements_by_type": dict(self._refinements_by_type),
            "refinements_by_reason": dict(self._refinements_by_reason),
            "enabled": self._enabled,
        }


# Convenience function for external use
def create_objection_refinement_context(
    message: str,
    intent: str,
    confidence: float,
    context: Optional[Dict[str, Any]] = None
) -> ObjectionRefinementContext:
    """
    Create ObjectionRefinementContext from a classifier context dict.

    Args:
        message: User's message text
        intent: Classified intent
        confidence: Classification confidence
        context: Optional dict with state, last_action, etc.

    Returns:
        ObjectionRefinementContext instance
    """
    context = context or {}
    return ObjectionRefinementContext(
        message=message,
        intent=intent,
        confidence=confidence,
        last_bot_message=context.get("last_bot_message"),
        last_action=context.get("last_action"),
        state=context.get("state", "greeting"),
        turn_number=context.get("turn_number", 0),
        last_objection_turn=context.get("last_objection_turn"),
        last_objection_type=context.get("last_objection_type"),
    )
