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
    # FIX: Added request_brevity - LLM often misclassifies short answers like "1"
    # as request_brevity when they're actually info_provided responses
    LOW_SIGNAL_INTENTS: Set[str] = {
        "greeting",
        "unclear",
        "small_talk",
        "gratitude",
        "request_brevity",  # FIX: "1" often misclassified as request_brevity
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
# LAYER 3: FIRST CONTACT REFINEMENT (First Turn Objection Bug Fix)
# =============================================================================


@register_refinement_layer("first_contact")
class FirstContactRefinementLayer(BaseRefinementLayer):
    """
    Refines objection classifications during first contact phase (turns 0-2).

    Problem: LLM classifies cautious interest as objection on first turn.
    Example: "слушайте мне тут посоветовали... но я не уверен"
             LLM returns objection_trust → bot goes to handle_objection
             Expected: consultation_request → bot greets and starts dialog

    Semantic difference by turn_number:
      turn=1: "не уверен" = modesty, cautious interest (want to learn more)
      turn>3: "не уверен" = doubt after presentation (real objection)

    This layer handles ONLY the first case (turn ≤ max_turn).

    Architecture:
    - OCP: New layer, doesn't modify existing ObjectionRefinementLayer
    - SRP: Single responsibility - first contact classification
    - Config-Driven: Patterns loaded from YAML
    - Registry: Auto-registered via @register_refinement_layer decorator
    """

    LAYER_NAME = "first_contact"
    LAYER_PRIORITY = LayerPriority.HIGH  # 75 - runs BEFORE objection refinement
    FEATURE_FLAG = "first_contact_refinement"

    def __init__(self) -> None:
        super().__init__()
        self._referral_regex: Optional[re.Pattern] = None
        self._cautious_regex: Optional[re.Pattern] = None
        self._first_contact_regex: Optional[re.Pattern] = None
        self._suspicious_intents: Set[str] = set()
        self._active_states: Set[str] = set()
        self._init_patterns()

    def _get_config(self) -> Dict[str, Any]:
        """Load first_contact_refinement config from constants.yaml."""
        try:
            from src.yaml_config.constants import get_first_contact_refinement_config

            return get_first_contact_refinement_config()
        except ImportError:
            return {}

    def _init_patterns(self) -> None:
        """Initialize regex patterns from config."""
        # Load pattern lists
        referral_patterns = self._config.get("referral_patterns", [])
        cautious_patterns = self._config.get("cautious_interest_patterns", [])
        first_contact_patterns = self._config.get("first_contact_patterns", [])

        # Compile regexes
        self._referral_regex = self._compile_patterns(referral_patterns)
        self._cautious_regex = self._compile_patterns(cautious_patterns)
        self._first_contact_regex = self._compile_patterns(first_contact_patterns)

        # Load intent and state sets
        self._suspicious_intents = set(self._config.get("suspicious_intents", []))
        self._active_states = set(self._config.get("active_states", []))

    @staticmethod
    def _compile_patterns(patterns: List[str]) -> Optional[re.Pattern]:
        """Compile patterns into single regex."""
        if not patterns:
            return None
        escaped = [re.escape(p) for p in patterns]
        return re.compile("|".join(escaped), re.IGNORECASE)

    def _should_apply(self, ctx: RefinementContext) -> bool:
        """
        Check if first contact refinement should apply.

        Conditions:
        1. Layer is enabled in config
        2. turn_number <= max_turn_number (early turns only)
        3. state is in active_states (greeting, initial)
        4. intent is in suspicious_intents (objection_* on turn=1 is suspicious)
        """
        if not self._config.get("enabled", True):
            return False

        max_turn = self._config.get("max_turn_number", 2)
        if ctx.turn_number > max_turn:
            return False

        # State check - only apply in greeting/initial states
        if ctx.state and self._active_states and ctx.state not in self._active_states:
            return False

        # Intent check - only refine suspicious intents
        if ctx.intent not in self._suspicious_intents:
            return False

        return True

    def _do_refine(
        self,
        message: str,
        result: Dict[str, Any],
        ctx: RefinementContext,
    ) -> RefinementResult:
        """
        Refine objection to consultation_request on first contact.

        Logic:
        - If message has referral pattern ("посоветовали") → refine
        - If message has cautious interest pattern ("не уверен") → refine
        - If message has first contact pattern ("слушайте") + any of above → refine

        All patterns indicate cautious interest, NOT real objection.
        """
        text = message.lower()

        # Check for patterns
        has_referral = self._referral_regex and self._referral_regex.search(text)
        has_cautious = self._cautious_regex and self._cautious_regex.search(text)
        has_first_contact = (
            self._first_contact_regex and self._first_contact_regex.search(text)
        )

        # Determine if refinement is needed
        should_refine = False
        reason_parts = []

        if has_referral:
            should_refine = True
            reason_parts.append("referral")

        if has_cautious:
            should_refine = True
            reason_parts.append("cautious_interest")

        # First contact marker strengthens the case
        if has_first_contact and (has_referral or has_cautious):
            reason_parts.append("first_contact_marker")

        # If no clear signal but it's turn 1 and objection, still refine
        # because objection on turn=1 in greeting is almost always wrong
        if not should_refine and ctx.turn_number <= 1 and ctx.state == "greeting":
            # Even without explicit patterns, objection on turn=1 is suspicious
            should_refine = True
            reason_parts.append("early_turn_objection")

        if should_refine:
            target_intent = self._config.get("target_intent", "consultation_request")
            refined_confidence = self._config.get("refined_confidence", 0.75)
            reason = f"first_contact:{'+'.join(reason_parts)}"

            return self._create_refined_result(
                new_intent=target_intent,
                new_confidence=refined_confidence,
                original_intent=ctx.intent,
                reason=reason,
                result=result,
                metadata={
                    "turn_number": ctx.turn_number,
                    "state": ctx.state,
                    "has_referral": bool(has_referral),
                    "has_cautious": bool(has_cautious),
                    "has_first_contact": bool(has_first_contact),
                },
            )

        # No refinement needed
        return self._pass_through(result, ctx)


# =============================================================================
# LAYER 3.5: GREETING CONTEXT REFINEMENT (Dialog Failure Fix)
# =============================================================================


@register_refinement_layer("greeting_context")
class GreetingContextRefinementLayer(BaseRefinementLayer):
    """
    Refines technical/misclassified intents in greeting context.

    Problem: In greeting state, intents like problem_sync, request_references
    get classified by LLM but lead to escalated/close via _universal_base transitions.
    This layer redirects them to problem_revealed/need_expressed for flow entry.

    Uses SSOT categories from constants.yaml — adding intent to technical_problems
    category automatically includes it in suspicious_intents.
    """

    LAYER_NAME = "greeting_context"
    LAYER_PRIORITY = LayerPriority.HIGH  # 75
    FEATURE_FLAG = "greeting_context_refinement"

    def __init__(self) -> None:
        super().__init__()
        self._suspicious_intents: Set[str] = set()
        self._active_states: Set[str] = set()
        self._target_overrides: Dict[str, str] = {}
        self._init_suspicious_intents()

    def _get_config(self) -> Dict[str, Any]:
        """Load greeting_context_refinement config from constants.yaml."""
        try:
            from src.yaml_config.constants import get_greeting_context_refinement_config
            return get_greeting_context_refinement_config()
        except ImportError:
            return {}

    def _init_suspicious_intents(self) -> None:
        """Load suspicious intents from SSOT categories, not hardcoded list."""
        from src.yaml_config.constants import INTENT_CATEGORIES

        categories = self._config.get("suspicious_intent_categories", [])
        self._suspicious_intents = set()
        for cat in categories:
            self._suspicious_intents.update(INTENT_CATEGORIES.get(cat, []))
        # Also allow explicit additions for edge cases
        explicit = self._config.get("additional_suspicious_intents", [])
        self._suspicious_intents.update(explicit)

        self._active_states = set(self._config.get("active_states", ["greeting"]))
        self._target_overrides = self._config.get("target_overrides", {})

    def _should_apply(self, ctx: RefinementContext) -> bool:
        """Check if greeting context refinement should apply."""
        if not self._config.get("enabled", True):
            return False

        max_turn = self._config.get("max_turn_number", 3)

        # Apply in greeting state OR early turns with no state
        in_greeting = ctx.state in self._active_states
        early_no_state = ctx.state is None and ctx.turn_number <= max_turn

        if not (in_greeting or early_no_state):
            return False

        if ctx.intent not in self._suspicious_intents:
            return False

        return True

    def _do_refine(
        self,
        message: str,
        result: Dict[str, Any],
        ctx: RefinementContext,
    ) -> RefinementResult:
        """Refine suspicious intent in greeting context to safe target."""
        default_target = self._config.get("default_target", "problem_revealed")
        target = self._target_overrides.get(ctx.intent, default_target)
        confidence = self._config.get("refined_confidence", 0.75)

        return self._create_refined_result(
            new_intent=target,
            new_confidence=confidence,
            original_intent=ctx.intent,
            reason=f"greeting_context:{ctx.intent}→{target}",
            result=result,
            metadata={"state": ctx.state, "turn": ctx.turn_number},
        )


# =============================================================================
# LAYER 4: OBJECTION REFINEMENT (Objection Stuck Fix)
# =============================================================================

@register_refinement_layer("objection")
class ObjectionRefinementLayerAdapter(BaseRefinementLayer):
    """
    Validates and refines objection classifications using context.

    Prevents false-positive objection detection by checking:
    - Topic alignment with bot's last question
    - Question markers in message
    - Interest patterns vs real objections
    - Uncertainty patterns (skeptic personas)
    - Confidence thresholds

    FIX: Added Rule 5 (uncertainty_patterns) to match ObjectionRefinementLayer.
    This was missing and caused ObjectionReturnSource to never trigger for
    skeptic personas who express uncertainty like "не уверен нужно ли".

    Without Rule 5, objection_think was NOT being refined to question_features,
    so ObjectionReturnSource.should_contribute() returned False (objection_think
    is not in return_intents), causing 37 dialogs with phases_reached: [].
    """

    LAYER_NAME = "objection"
    LAYER_PRIORITY = LayerPriority.NORMAL
    FEATURE_FLAG = "objection_refinement"

    def __init__(self):
        super().__init__()
        self._callback_regex = None
        self._interest_regex = None
        self._uncertainty_regex = None  # FIX: Added for Rule 5
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
        # FIX: Load uncertainty_patterns for Rule 5 (skeptic persona handling)
        uncertainty_patterns = self._config.get("uncertainty_patterns", [])

        self._callback_regex = self._compile_patterns(callback_patterns)
        self._interest_regex = self._compile_patterns(interest_patterns)
        # FIX: Initialize uncertainty regex for Rule 5
        self._uncertainty_regex = self._compile_patterns(uncertainty_patterns)

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

        # Hard ceiling: very confident objection classifications bypass all rules.
        hard_ceiling = self._config.get("confidence_hard_ceiling", 0.92)
        if ctx.confidence >= hard_ceiling:
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

        # Rule 2: Question markers — only for low-confidence objections
        question_max_conf = self._config.get("question_refinement_max_confidence", 0.75)
        if self._has_question_markers(message) and ctx.confidence < question_max_conf:
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

        # Rule 5: Uncertainty patterns (objection_think → question)
        # FIX: This rule was MISSING in the adapter but present in ObjectionRefinementLayer.
        # Skeptic personas use phrases like "не уверен нужно ли", "сомневаюсь", "зачем это нужно"
        # which are implicit questions about value proposition, not real objections.
        #
        # Without this rule:
        #   - objection_think stays as objection_think
        #   - ObjectionReturnSource.should_contribute() returns False
        #   - Bot gets stuck in handle_objection → soft_close
        #   - phases_reached: [] for 37 dialogs
        #
        # With this rule:
        #   - objection_think → question_features (via uncertainty pattern)
        #   - ObjectionReturnSource triggers return to phase
        #   - Dialog continues normally through sales phases
        if ctx.intent == "objection_think":
            if self._uncertainty_regex and self._uncertainty_regex.search(message):
                alternative = self._get_uncertainty_alternative(ctx)
                return self._create_refined_result(
                    new_intent=alternative,
                    new_confidence=0.7,
                    original_intent=ctx.intent,
                    reason="uncertainty_pattern",
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

    def _get_uncertainty_alternative(self, ctx: RefinementContext) -> str:
        """
        Get alternative intent for uncertainty context.

        FIX: This method was MISSING in the adapter but present in ObjectionRefinementLayer.
        It handles skeptic personas who express uncertainty without explicit question words.
        E.g., "не уверен нужно ли" is an implicit question about value proposition.

        Args:
            ctx: RefinementContext

        Returns:
            Alternative intent name (defaults to question_features)
        """
        mapping = self._config.get("refinement_mapping", {}).get(ctx.intent, {})
        # Try uncertainty_context first, fall back to question_context
        alternative = mapping.get("uncertainty_context")
        if alternative:
            return alternative
        alternative = mapping.get("question_context")
        if alternative:
            return alternative
        # Default for objection_think uncertainty
        return "question_features"


# =============================================================================
# LAYER 5: OPTION SELECTION REFINEMENT (Disambiguation Assist Fix)
# =============================================================================


@register_refinement_layer("option_selection")
class OptionSelectionRefinementLayer(BaseRefinementLayer):
    """
    Refines short numeric/ordinal responses when bot asked a question with options.

    Problem: Bot asks inline question like "Скорость или функционал?" (not in disambiguation mode).
    Client (simulator) responds "1" thinking it's option selection.
    LLM classifies "1" as request_brevity (0.9) instead of info_provided.

    Solution: Detect when last_bot_message contains option patterns (X или Y?),
    and short numeric answer ("1", "2", "первое") - refine to info_provided with
    secondary signal indicating option selection.

    Architecture:
    - OCP: New layer, doesn't modify existing layers
    - SRP: Single responsibility - option selection detection
    - Config-Driven: Patterns loaded from YAML
    - Registry: Auto-registered via @register_refinement_layer decorator

    Research basis:
    - Grice's Cooperative Principle: short answers in response to questions
      carry implicature of answering that specific question
    - Conversational repair research: numeric responses to binary questions
      are understood as selections, not meta-comments
    """

    LAYER_NAME = "option_selection"
    LAYER_PRIORITY = LayerPriority.HIGH  # 75 - runs early
    FEATURE_FLAG = "option_selection_refinement"

    # Patterns to detect option-bearing questions in bot message
    OPTION_QUESTION_PATTERNS: List[str] = [
        r"(.+?)\s+или\s+(.+?)\?",  # "X или Y?"
        r"что\s+(?:для\s+вас\s+)?(?:важн|приоритетн|лучше)",  # Priority questions
        r"(?:вам|вас)\s+(?:важн|интересн|нужн)",  # "Вам важнее..."
        r"(?:выбер|предпочт)",  # "Выберите" / "Предпочитаете"
    ]

    # Patterns to detect numeric/ordinal selection answers
    SELECTION_ANSWER_PATTERNS: List[str] = [
        r"^1$",  # Just "1"
        r"^2$",  # Just "2"
        r"^3$",  # Just "3"
        r"^перв",  # "первое", "первый"
        r"^втор",  # "второе", "второй"
        r"^трет",  # "третье", "третий"
        r"^один$",
        r"^два$",
        r"^три$",
    ]

    # Intents that may be wrong when user is answering option question
    SUSPICIOUS_INTENTS: Set[str] = {
        "request_brevity",  # Main culprit
        "greeting",
        "unclear",
        "small_talk",
        "gratitude",
        "objection_no_time",  # "1" might be misread as "hurry up"
    }

    def __init__(self) -> None:
        super().__init__()
        self._option_question_regex: Optional[re.Pattern] = None
        self._selection_answer_regex: Optional[re.Pattern] = None
        self._init_patterns()

    def _get_config(self) -> Dict[str, Any]:
        """Load option_selection_refinement config from constants.yaml."""
        try:
            from src.yaml_config.constants import get_option_selection_config
            return get_option_selection_config()
        except (ImportError, AttributeError):
            # Config function not yet added, use defaults
            return {
                "enabled": True,
                "target_intent": "info_provided",
                "refined_confidence": 0.75,
                "secondary_signal": "option_selection",
            }

    def _init_patterns(self) -> None:
        """Initialize regex patterns."""
        # Load from config or use defaults
        option_patterns = self._config.get(
            "option_question_patterns",
            self.OPTION_QUESTION_PATTERNS
        )
        selection_patterns = self._config.get(
            "selection_answer_patterns",
            self.SELECTION_ANSWER_PATTERNS
        )

        self._option_question_regex = self._compile_patterns(option_patterns)
        self._selection_answer_regex = self._compile_patterns(selection_patterns)

        # Load suspicious intents from config or use defaults
        config_suspicious = self._config.get("suspicious_intents", [])
        if config_suspicious:
            self.SUSPICIOUS_INTENTS = set(config_suspicious)

    @staticmethod
    def _compile_patterns(patterns: List[str]) -> Optional[re.Pattern]:
        """Compile patterns into single regex."""
        if not patterns:
            return None
        return re.compile("|".join(patterns), re.IGNORECASE)

    def _should_apply(self, ctx: RefinementContext) -> bool:
        """
        Check if option selection refinement should apply.

        Conditions:
        0. NOT in disambiguation (disambiguation_resolution handles that)
        1. Layer is enabled in config
        2. Intent is in suspicious_intents (might be wrong)
        3. Message is short (selection-like)
        4. last_bot_message contains option patterns
        """
        if not self._config.get("enabled", True):
            return False

        # Disambiguation resolution layer handles option selection during disambiguation
        if ctx.in_disambiguation:
            return False

        # Check 1: Is intent suspicious?
        if ctx.intent not in self.SUSPICIOUS_INTENTS:
            return False

        # Check 2: Is message short enough to be selection?
        if len(ctx.message.strip()) > 15:
            return False

        # Check 3: Does message match selection pattern?
        if not self._is_selection_answer(ctx.message):
            return False

        # Check 4: Did bot ask an option question?
        # Need last_bot_message in context
        last_bot_msg = ctx.last_bot_message or ctx.metadata.get("last_bot_message", "")
        if not last_bot_msg:
            return False

        if not self._is_option_question(last_bot_msg):
            return False

        return True

    def _do_refine(
        self,
        message: str,
        result: Dict[str, Any],
        ctx: RefinementContext,
    ) -> RefinementResult:
        """
        Refine to info_provided with option_selection signal.

        Logic:
        - Extract which option was selected (1, 2, etc.)
        - Refine intent to info_provided
        - Add secondary_signal "option_selection"
        - Add metadata about selected option index
        """
        # Extract selected option index
        option_index = self._extract_option_index(message)

        # Extract options from bot message for context
        last_bot_msg = ctx.last_bot_message or ctx.metadata.get("last_bot_message", "")
        extracted_options = self._extract_options_from_question(last_bot_msg)

        target_intent = self._config.get("target_intent", "info_provided")
        refined_confidence = self._config.get("refined_confidence", 0.75)
        secondary_signal = self._config.get("secondary_signal", "option_selection")

        # Build reason
        reason_parts = ["option_selection"]
        if option_index is not None:
            reason_parts.append(f"index={option_index}")
        if extracted_options:
            reason_parts.append(f"options={len(extracted_options)}")

        return self._create_refined_result(
            new_intent=target_intent,
            new_confidence=refined_confidence,
            original_intent=ctx.intent,
            reason=":".join(reason_parts),
            result=result,
            secondary_signals=[secondary_signal],
            metadata={
                "option_index": option_index,
                "extracted_options": extracted_options,
                "original_bot_question": last_bot_msg[:100] if last_bot_msg else None,
            },
        )

    def _is_selection_answer(self, message: str) -> bool:
        """Check if message looks like option selection."""
        if not self._selection_answer_regex:
            return False
        text = message.lower().strip()
        return bool(self._selection_answer_regex.search(text))

    def _is_option_question(self, bot_message: str) -> bool:
        """Check if bot message contains option patterns."""
        if not self._option_question_regex:
            return False
        return bool(self._option_question_regex.search(bot_message))

    def _extract_option_index(self, message: str) -> Optional[int]:
        """Extract which option was selected (0-indexed)."""
        text = message.lower().strip()

        # Numeric
        if text == "1" or text.startswith("перв") or text == "один":
            return 0
        if text == "2" or text.startswith("втор") or text == "два":
            return 1
        if text == "3" or text.startswith("трет") or text == "три":
            return 2

        return None

    def _extract_options_from_question(self, bot_message: str) -> List[str]:
        """Extract option labels from bot question."""
        options = []

        # Pattern: "X или Y?"
        match = re.search(r"(.+?)\s+или\s+(.+?)\?", bot_message, re.IGNORECASE)
        if match:
            options.append(match.group(1).strip())
            options.append(match.group(2).strip())

        return options


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
    # FIX: Added secondary_intent_detection to expected layers
    # FIX: Added first_contact for First Turn Objection Bug Fix
    # FIX: Added option_selection for Disambiguation Assist Fix
    expected = [
        "style_modifier_detection",  # Style/Semantic Separation
        "disambiguation_resolution",  # Disambiguation Resolution Fix
        "confidence_calibration",
        "secondary_intent_detection",  # Lost Question Fix
        "short_answer",
        "composite_message",
        "first_contact",  # First Turn Objection Bug Fix
        "greeting_context",  # Dialog Failure Fix
        "objection",
        "option_selection",  # Disambiguation Assist Fix
        "comparison",  # Comparison → objection_competitor refinement
    ]
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

# FIX: Import secondary_intent_detection to register the layer
try:
    from src.classifier import secondary_intent_detection  # noqa: F401
except ImportError as e:
    logger.warning(f"Could not import secondary_intent_detection: {e}")

# Import disambiguation_resolution_layer to register the layer
try:
    from src.classifier import disambiguation_resolution_layer  # noqa: F401
except ImportError as e:
    logger.warning(f"Could not import disambiguation_resolution_layer: {e}")

# Import data_aware_refinement to register the layer
try:
    from src.classifier import data_aware_refinement  # noqa: F401
except ImportError as e:
    logger.warning(f"Could not import data_aware_refinement: {e}")

# Import comparison_refinement to register the layer
try:
    from src.classifier import comparison_refinement  # noqa: F401
except ImportError as e:
    logger.warning(f"Could not import comparison_refinement: {e}")

# Import style_modifier_detection to register the layer
try:
    from src.classifier import style_modifier_detection  # noqa: F401
except ImportError as e:
    logger.warning(f"Could not import style_modifier_detection: {e}")

# Verify on import (DEBUG level)
logger.debug(f"Refinement layers registered: {verify_layers_registered()}")
