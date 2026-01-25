"""
Refinement Layers - Adapters for existing refinement logic.

This module provides layer adapters that wrap existing refinement implementations
into the unified RefinementPipeline architecture.

Each adapter:
- Inherits from BaseRefinementLayer
- Wraps existing implementation (reuses battle-tested code)
- Registers itself with RefinementLayerRegistry via decorator
- Provides unified interface for pipeline

Architecture:
    BaseRefinementLayer (refinement_pipeline.py)
           |
           +--- ConfidenceCalibrationLayer (confidence_calibration.py) [CRITICAL priority]
           +--- ShortAnswerRefinementLayer (wraps refinement.py)
           +--- CompositeMessageLayer (wraps composite_refinement.py)
           +--- ObjectionRefinementLayer (wraps objection_refinement.py)

All layers are automatically registered when this module is imported.
Import this module in UnifiedClassifier to enable all layers.

Usage:
    # Import to register all layers
    from src.classifier import refinement_layers

    # Pipeline will auto-discover registered layers
    from src.classifier.refinement_pipeline import get_refinement_pipeline
    pipeline = get_refinement_pipeline()
"""

from typing import Any, Dict, List, Optional, Set
import logging
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
# LAYER 1: SHORT ANSWER REFINEMENT (State Loop Fix)
# =============================================================================

@register_refinement_layer("short_answer")
class ShortAnswerRefinementLayer(BaseRefinementLayer):
    """
    Refines short message classifications using context.

    Addresses the State Loop bug where short answers like "1", "да", "первое"
    are incorrectly classified as "greeting" by LLM.

    Uses short_answer_classification from constants.yaml.
    """

    LAYER_NAME = "short_answer"
    LAYER_PRIORITY = LayerPriority.HIGH
    FEATURE_FLAG = "classification_refinement"

    # Intents that may need refinement (low-signal in short message context)
    LOW_SIGNAL_INTENTS: Set[str] = {
        "greeting",
        "unclear",
        "small_talk",
        "gratitude",
    }

    # Actions that indicate we're awaiting data
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
    MAX_SHORT_WORDS = 5
    MAX_SHORT_CHARS = 25

    # Patterns for sentiment detection
    NEGATIVE_PATTERNS = [
        r"\bнет\b", r"\bне\s+надо\b", r"\bне\s+нужно\b", r"\bне\s+интересно\b",
        r"\bникак\b", r"\bничего\b", r"\bотказ", r"\bне\s+хочу\b", r"\bне\s+буду\b",
    ]

    POSITIVE_PATTERNS = [
        r"\bда\b", r"\bок\b", r"\bокей\b", r"\bхорошо\b", r"\bсогласен\b",
        r"\bверно\b", r"\bточно\b", r"\bконечно\b", r"\bага\b", r"\bугу\b",
        r"\bпервое\b", r"\bвторое\b", r"\bтретье\b", r"\bлад", r"\bдавай",
    ]

    def __init__(self):
        super().__init__()
        self._negative_regex = re.compile(
            "|".join(self.NEGATIVE_PATTERNS), re.IGNORECASE
        )
        self._positive_regex = re.compile(
            "|".join(self.POSITIVE_PATTERNS), re.IGNORECASE
        )

    def _get_config(self) -> Dict[str, Any]:
        """Load short_answer_classification from constants.yaml."""
        try:
            from src.yaml_config.constants import get_short_answer_config
            return get_short_answer_config()
        except ImportError:
            return {}

    def _should_apply(self, ctx: RefinementContext) -> bool:
        """Check if refinement should be applied."""
        # Check 1: Is message short?
        if not self._is_short_message(ctx.message):
            return False

        # Check 2: Did classifier return low-signal intent?
        if ctx.intent not in self.LOW_SIGNAL_INTENTS:
            return False

        # Check 3: Do we have context that suggests data collection?
        has_phase_context = (
            ctx.phase is not None and
            ctx.phase in self._config
        )
        has_action_context = ctx.last_action in self.AWAITING_DATA_ACTIONS
        is_greeting_state = ctx.state == "greeting"

        return has_phase_context or has_action_context or is_greeting_state

    def _do_refine(
        self,
        message: str,
        result: Dict[str, Any],
        ctx: RefinementContext
    ) -> RefinementResult:
        """Apply short answer refinement logic."""
        # Get refined intent based on phase and sentiment
        refined = self._get_refined_intent(message, ctx)

        if refined is None:
            return self._pass_through(result, ctx)

        refined_intent, refined_confidence = refined

        return self._create_refined_result(
            new_intent=refined_intent,
            new_confidence=refined_confidence,
            original_intent=ctx.intent,
            reason=f"short_answer_in_{ctx.phase or ctx.state}_context",
            result=result,
        )

    def _is_short_message(self, message: str) -> bool:
        """Check if message is short enough for refinement."""
        stripped = message.strip()
        words = stripped.split()
        return (
            len(words) <= self.MAX_SHORT_WORDS or
            len(stripped) <= self.MAX_SHORT_CHARS
        )

    def _get_refined_intent(
        self,
        message: str,
        ctx: RefinementContext
    ) -> Optional[tuple]:
        """Get refined intent based on sentiment and phase."""
        phase = ctx.phase

        # If no phase but in greeting, use "situation" as default
        if not phase and ctx.state == "greeting":
            phase = "situation"

        if not phase or phase not in self._config:
            return None

        phase_config = self._config[phase]
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

        # Neutral → default to positive for data collection
        if sentiment == "neutral":
            intent = phase_config.get("positive_intent")
            confidence = phase_config.get("positive_confidence", 0.7) * 0.85
            if intent:
                return (intent, confidence)

        return None

    def _detect_sentiment(self, message: str) -> str:
        """Detect sentiment of short message."""
        text = message.lower().strip()

        if self._negative_regex.search(text):
            return "negative"

        if self._positive_regex.search(text):
            return "positive"

        # Numbers typically positive (answering data questions)
        if re.search(r'\d+', text):
            return "positive"

        # Single words are typically informative
        if len(text.split()) == 1 and len(text) > 0:
            return "neutral"

        if len(text) <= 10:
            return "neutral"

        return "neutral"


# =============================================================================
# LAYER 2: COMPOSITE MESSAGE REFINEMENT
# =============================================================================

@register_refinement_layer("composite_message")
class CompositeMessageLayer(BaseRefinementLayer):
    """
    Refines composite message classifications with data priority.

    Addresses misclassification of messages like "5 человек, больше не нужно, быстрее"
    which should be classified as info_provided (with company_size=5) rather than
    objection_think.

    Key principle: When bot asked for data and user responds with extractable data,
    prioritize data intent over meta-intents.
    """

    LAYER_NAME = "composite_message"
    LAYER_PRIORITY = LayerPriority.HIGH
    FEATURE_FLAG = "composite_refinement"

    # Intents that can be refined to data intents
    REFINABLE_INTENTS: Set[str] = {
        "objection_think",
        "objection_no_need",
        "objection_no_time",
        "rejection",
        "unclear",
        "small_talk",
        "gratitude",
    }

    def _get_config(self) -> Dict[str, Any]:
        """Load composite_refinement config from constants.yaml."""
        try:
            from src.yaml_config.constants import get_composite_refinement_config
            return get_composite_refinement_config()
        except ImportError:
            return {}

    def _should_apply(self, ctx: RefinementContext) -> bool:
        """Check if composite refinement should apply."""
        # Only refine refinable intents
        if ctx.intent not in self.REFINABLE_INTENTS:
            return False

        # Check if we're in data-expecting context
        action_expects = self._config.get("action_expects_data", {})
        data_states = set(self._config.get("data_expecting_states", []))
        data_phases = set(self._config.get("data_expecting_phases", []))

        has_action_context = ctx.last_action in action_expects
        has_state_context = ctx.state in data_states
        has_phase_context = ctx.phase in data_phases

        return has_action_context or has_state_context or has_phase_context

    def _do_refine(
        self,
        message: str,
        result: Dict[str, Any],
        ctx: RefinementContext
    ) -> RefinementResult:
        """Apply composite message refinement."""
        # Try to extract data
        extracted = self._extract_data(message, ctx)

        if not extracted:
            # Check for ambiguous pattern resolution
            ambiguous_result = self._resolve_ambiguous_pattern(message, ctx)
            if ambiguous_result:
                return ambiguous_result
            return self._pass_through(result, ctx)

        # Data extracted - refine to data intent
        field_name, field_value = extracted

        # Determine target intent
        action_intents = self._config.get("action_data_intent", {})
        target_intent = action_intents.get(
            ctx.last_action,
            self._config.get("default_data_intent", "info_provided")
        )

        # Detect secondary signals (meta-intents that aren't primary)
        secondary_signals = self._detect_secondary_signals(message)

        # Create refined result with extracted data
        new_extracted = result.get("extracted_data", {}).copy()
        new_extracted[field_name] = field_value

        return self._create_refined_result(
            new_intent=target_intent,
            new_confidence=self._config.get("min_confidence_for_refinement", 0.75),
            original_intent=ctx.intent,
            reason=f"data_extracted:{field_name}",
            result=result,
            extracted_data=new_extracted,
            secondary_signals=secondary_signals,
        )

    def _extract_data(
        self,
        message: str,
        ctx: RefinementContext
    ) -> Optional[tuple]:
        """Try to extract data from message based on context."""
        action_expects = self._config.get("action_expects_data", {})
        expected_type = action_expects.get(ctx.last_action) or ctx.expects_data_type

        if not expected_type:
            return None

        data_fields = self._config.get("data_fields", {})
        field_config = data_fields.get(expected_type)

        if not field_config:
            return None

        # Try extraction patterns
        patterns = field_config.get("extract_patterns", [])
        text = message.lower()

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                # Get the captured group (number or value)
                value = match.group(1) if match.groups() else match.group(0)

                # Validate and convert
                field_type = field_config.get("type", "str")
                if field_type == "int":
                    try:
                        int_value = int(value)
                        min_val = field_config.get("min", 1)
                        max_val = field_config.get("max", 10000)
                        if min_val <= int_value <= max_val:
                            return (expected_type, int_value)
                    except ValueError:
                        continue
                else:
                    return (expected_type, value)

        return None

    def _detect_secondary_signals(self, message: str) -> List[str]:
        """Detect secondary meta-signals in message."""
        signals = []
        meta_signals = self._config.get("meta_signals", {})
        text = message.lower()

        for signal_name, signal_config in meta_signals.items():
            patterns = signal_config.get("patterns", [])
            for pattern in patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    signals.append(signal_name)
                    break

        return signals

    def _resolve_ambiguous_pattern(
        self,
        message: str,
        ctx: RefinementContext
    ) -> Optional[RefinementResult]:
        """Resolve ambiguous patterns based on context."""
        ambiguous = self._config.get("ambiguous_patterns", {})
        text = message.lower()

        for pattern_name, pattern_config in ambiguous.items():
            patterns = pattern_config.get("patterns", [])

            for pattern in patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    # Check if action resolves to data
                    data_actions = set(pattern_config.get("data_resolving_actions", []))
                    rejection_actions = set(pattern_config.get("rejection_resolving_actions", []))

                    if ctx.last_action in data_actions:
                        # Ambiguous phrase in data context → info_provided
                        return RefinementResult(
                            decision=RefinementDecision.REFINED,
                            intent="info_provided",
                            confidence=0.7,
                            original_intent=ctx.intent,
                            refinement_reason=f"ambiguity_resolved:{pattern_name}:data_context",
                            metadata={"ambiguity_pattern": pattern_name},
                        )
                    elif ctx.last_action in rejection_actions:
                        # Keep as rejection
                        return None

        return None


# =============================================================================
# LAYER 3: OBJECTION REFINEMENT (Objection Stuck Fix)
# =============================================================================

@register_refinement_layer("objection")
class ObjectionRefinementLayerAdapter(BaseRefinementLayer):
    """
    Validates and refines objection classifications using context.

    Prevents false-positive objection detection by checking:
    - Topic alignment with bot's last question
    - Question markers in message
    - Interest patterns vs real objections
    - Confidence thresholds
    """

    LAYER_NAME = "objection"
    LAYER_PRIORITY = LayerPriority.NORMAL
    FEATURE_FLAG = "objection_refinement"

    def __init__(self):
        super().__init__()
        self._callback_regex = None
        self._interest_regex = None
        self._objection_intents: Set[str] = set()
        self._init_patterns()

    def _get_config(self) -> Dict[str, Any]:
        """Load objection_refinement config from constants.yaml."""
        try:
            from src.yaml_config.constants import get_objection_refinement_config
            return get_objection_refinement_config()
        except ImportError:
            return {}

    def _init_patterns(self) -> None:
        """Initialize regex patterns from config."""
        callback_patterns = self._config.get("callback_patterns", [])
        interest_patterns = self._config.get("interest_patterns", [])

        self._callback_regex = self._compile_patterns(callback_patterns)
        self._interest_regex = self._compile_patterns(interest_patterns)

        # Load objection intents
        try:
            from src.yaml_config.constants import OBJECTION_INTENTS
            self._objection_intents = set(OBJECTION_INTENTS)
        except ImportError:
            self._objection_intents = {
                "objection_price", "objection_competitor", "objection_no_time",
                "objection_think", "objection_timing", "objection_complexity",
                "objection_trust", "objection_no_need", "objection_risk",
            }

    @staticmethod
    def _compile_patterns(patterns: List[str]) -> re.Pattern:
        """Compile patterns into single regex."""
        if not patterns:
            return re.compile(r"^$")
        escaped = [re.escape(p) for p in patterns]
        return re.compile("|".join(escaped), re.IGNORECASE)

    def _should_apply(self, ctx: RefinementContext) -> bool:
        """Check if objection refinement should apply."""
        if not self._config.get("enabled", True):
            return False

        if ctx.intent not in self._objection_intents:
            return False

        # High confidence without context issues → accept
        min_confidence = self._config.get("min_confidence_to_accept", 0.85)
        if ctx.confidence >= min_confidence:
            if not self._has_question_markers(ctx.message):
                if not self._is_topic_aligned(ctx):
                    return False

        return True

    def _do_refine(
        self,
        message: str,
        result: Dict[str, Any],
        ctx: RefinementContext
    ) -> RefinementResult:
        """Apply objection refinement rules."""

        # Rule 1: Topic alignment
        if self._is_topic_aligned(ctx):
            alternative = self._get_topic_alternative(ctx)
            if alternative:
                return self._create_refined_result(
                    new_intent=alternative,
                    new_confidence=0.75,
                    original_intent=ctx.intent,
                    reason="topic_alignment",
                    result=result,
                )

        # Rule 2: Question markers
        if self._has_question_markers(message):
            alternative = self._get_question_alternative(ctx)
            if alternative:
                return self._create_refined_result(
                    new_intent=alternative,
                    new_confidence=0.7,
                    original_intent=ctx.intent,
                    reason="question_markers",
                    result=result,
                )

        # Rule 3: Callback patterns
        if ctx.intent == "objection_no_time":
            if self._callback_regex and self._callback_regex.search(message):
                return self._create_refined_result(
                    new_intent="callback_request",
                    new_confidence=0.8,
                    original_intent=ctx.intent,
                    reason="callback_pattern",
                    result=result,
                )

        # Rule 4: Interest patterns
        if ctx.intent == "objection_think":
            if self._interest_regex and self._interest_regex.search(message):
                return self._create_refined_result(
                    new_intent="question_features",
                    new_confidence=0.7,
                    original_intent=ctx.intent,
                    reason="interest_pattern",
                    result=result,
                )

        # No refinement needed
        return self._pass_through(result, ctx)

    def _has_question_markers(self, message: str) -> bool:
        """Check if message contains question markers."""
        text = message.lower()

        if "?" in message:
            return True

        question_markers = self._config.get("question_markers", [])
        for marker in question_markers:
            if marker in text:
                return True

        return False

    def _is_topic_aligned(self, ctx: RefinementContext) -> bool:
        """Check if objection topic aligns with bot's last question."""
        if not ctx.last_action:
            return False

        topic = self._get_objection_topic(ctx.intent)
        if not topic:
            return False

        topic_actions = self._config.get("topic_alignment_actions", {})
        return ctx.last_action in topic_actions.get(topic, [])

    def _get_objection_topic(self, intent: str) -> Optional[str]:
        """Map objection intent to topic."""
        topic_map = {
            "objection_price": "budget",
            "objection_no_time": "time",
            "objection_competitor": "competitor",
            "objection_complexity": "complexity",
            "objection_timing": "time",
        }
        return topic_map.get(intent)

    def _get_topic_alternative(self, ctx: RefinementContext) -> Optional[str]:
        """Get alternative intent for topic alignment."""
        mapping = self._config.get("refinement_mapping", {}).get(ctx.intent, {})
        return mapping.get("info_context", "info_provided")

    def _get_question_alternative(self, ctx: RefinementContext) -> Optional[str]:
        """Get alternative intent for question context."""
        mapping = self._config.get("refinement_mapping", {}).get(ctx.intent, {})
        return mapping.get("question_context")


# =============================================================================
# AUTO-REGISTRATION VERIFICATION
# =============================================================================

def verify_layers_registered() -> List[str]:
    """
    Verify all expected layers are registered.

    Returns:
        List of registered layer names
    """
    from src.classifier.refinement_pipeline import RefinementLayerRegistry

    registry = RefinementLayerRegistry.get_registry()
    expected = ["confidence_calibration", "short_answer", "composite_message", "objection"]
    registered = registry.get_all_names()

    for layer in expected:
        if layer not in registered:
            logger.warning(f"Expected layer '{layer}' not registered")

    return registered


# Import confidence_calibration to register the layer
# This must be done AFTER the verify_layers_registered function definition
# to avoid circular imports
try:
    from src.classifier import confidence_calibration  # noqa: F401
except ImportError as e:
    logger.warning(f"Could not import confidence_calibration: {e}")

# Verify on import (DEBUG level)
logger.debug(f"Refinement layers registered: {verify_layers_registered()}")
