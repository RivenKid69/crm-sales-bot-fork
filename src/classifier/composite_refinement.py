"""
Composite Message Refinement Layer.

Context-aware refinement for messages containing both data and meta-signals.
Prevents misclassification of composite messages like "5 человек, больше не нужно, быстрее"
by prioritizing data extraction over meta-intents.

Problem Addressed:
    LLM classifiers often misclassify composite messages as objections or unclear
    when they contain ambiguous phrases like "больше не нужно" (which can mean
    "no more needed" as quantity clarification or "not needed at all" as rejection).

Architecture:
    - Runs AFTER ClassificationRefinementLayer, BEFORE ObjectionRefinementLayer
    - Uses composite_refinement config from constants.yaml
    - Prioritizes data extraction when context expects data
    - Resolves ambiguous patterns based on context
    - Falls back to original result on any error (fail-safe)
    - UNIVERSAL: Works with any dialogue flow, not just SPIN

Pipeline Position:
    message → LLM/Hybrid → ClassificationRefinement → CompositeMessageRefinement →
    → ObjectionRefinement → DataAwareRefinement → ... → result

    INVARIANT: CompositeMessageLayer MUST run BEFORE DataAwareRefinementLayer
    so price_question intent is preserved (not overwritten by unclear→info_provided).

Design Principles:
    - Flow-Agnostic: Works with SPIN, BANT, custom flows or any dialogue structure
    - Configuration-Driven: All rules from YAML (constants.yaml)
    - Context-Based: Uses last_action, state, phase (any phase system)
    - Data Priority: Extracted data takes precedence over meta-signals
    - Fail-Safe: Never crashes, returns original on error

Usage:
    from src.classifier.composite_refinement import (
        CompositeMessageRefinementLayer,
        CompositeMessageContext
    )

    layer = CompositeMessageRefinementLayer()
    context = CompositeMessageContext(
        message="5 человек, больше не нужно, быстрее",
        intent="objection_think",
        confidence=0.75,
        current_phase="data_collection",  # Any phase name
        state="spin_situation",
        last_action="ask_about_company",
        extracted_data={}
    )
    refined_result = layer.refine(message, llm_result, context)
"""

from dataclasses import dataclass, field
from typing import Optional, Set, Dict, Any, List, Pattern, FrozenSet
import re
import logging

from src.yaml_config.constants import get_composite_refinement_config

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CompositeMessageContext:
    """
    Immutable context for composite message refinement.

    This context is flow-agnostic and works with any dialogue structure.

    Attributes:
        message: The user's message text
        intent: Classified intent from LLM
        confidence: Classification confidence (0.0-1.0)
        current_phase: Current dialogue phase (any phase system: SPIN, BANT, custom)
        state: Current state machine state
        last_action: Last action performed by the bot (key for context analysis)
        extracted_data: Already extracted data from LLM classification
        turn_number: Current turn number in conversation
        expects_data_type: Optional hint about expected data type (company_size, etc.)
    """
    message: str
    intent: str
    confidence: float
    current_phase: Optional[str] = None  # Generic phase, not SPIN-specific
    state: Optional[str] = None
    last_action: Optional[str] = None
    extracted_data: Dict[str, Any] = field(default_factory=dict)
    turn_number: int = 0
    expects_data_type: Optional[str] = None  # Hint about expected data


@dataclass
class CompositeRefinementResult:
    """
    Result of composite message refinement.

    Attributes:
        intent: Final intent (refined or original)
        confidence: Final confidence
        refined: Whether refinement was applied
        extracted_data: Extracted data fields (merged with original)
        secondary_signals: List of detected secondary signals (e.g., request_brevity)
        original_intent: Original intent before refinement (if refined)
        refinement_reason: Reason code for refinement (if refined)
        ambiguity_resolved: Description of resolved ambiguity (if any)
    """
    intent: str
    confidence: float
    refined: bool
    extracted_data: Dict[str, Any] = field(default_factory=dict)
    secondary_signals: List[str] = field(default_factory=list)
    original_intent: Optional[str] = None
    refinement_reason: Optional[str] = None
    ambiguity_resolved: Optional[str] = None


class CompositeMessageRefinementLayer:
    """
    Refines composite message classifications using context and data prioritization.

    This layer is FLOW-AGNOSTIC and works with any dialogue structure:
    - SPIN Selling (situation, problem, implication, need_payoff)
    - BANT (budget, authority, need, timeline)
    - Custom flows with any phase names
    - Simple linear flows

    The core principle: when bot asked a data question and user response
    contains extractable data, prioritize data intent over meta-intents.

    Thread Safety:
        This class is thread-safe as it only reads from configuration.

    Design Principles:
        - Universal: Works with any flow/phase system
        - Configuration-Driven: All rules from YAML (constants.yaml)
        - Action-Based: last_action is the primary context signal
        - Fail-Safe: Never crashes, returns original on error
        - Observable: Logs all refinement decisions with structured data

    Example:
        >>> layer = CompositeMessageRefinementLayer()
        >>> ctx = CompositeMessageContext(
        ...     message="5 человек, больше не нужно, быстрее",
        ...     intent="objection_think",
        ...     confidence=0.75,
        ...     current_phase="data_collection",  # Any phase
        ...     last_action="ask_about_company",
        ...     ...
        ... )
        >>> result = layer.refine(ctx.message, {"intent": "objection_think"}, ctx)
        >>> result["intent"]
        'info_provided'  # Refined because message contains extractable data
        >>> result["extracted_data"]["company_size"]
        5
    """

    # Intents that may need refinement (meta-intents or misclassifications)
    REFINABLE_INTENTS: FrozenSet[str] = frozenset({
        "objection_think",
        "objection_no_need",
        "objection_price",
        "objection_no_time",
        "rejection",
        "unclear",
        "small_talk",
        "request_brevity",
        "greeting",
        "gratitude",
        # BUG #2 FIX: Price intents — composite messages like "500. Скока стоит?"
        # contain extractable data that was blocked by this gate.
        # Combined with action_data_intent mapping (Fix 1d), the intent is PRESERVED
        # as price_question (not changed to info_provided).
        "price_question",
        "pricing_details",
        "cost_inquiry",
    })

    def __init__(self):
        """Initialize the refinement layer with configuration from constants.yaml."""
        self._config = get_composite_refinement_config()
        self._enabled = self._config.get("enabled", True)

        # Load configuration
        self._meta_signals = self._config.get("meta_signals", {})
        self._ambiguous_patterns = self._config.get("ambiguous_patterns", {})
        self._data_fields = self._config.get("data_fields", {})

        # Action → expected data type mapping (flow-agnostic)
        # This is the primary mechanism for context-aware refinement
        self._action_expects_data = self._config.get("action_expects_data", {})

        # Action → target intent mapping (what intent to use when data extracted)
        self._action_data_intent = self._config.get("action_data_intent", {})

        # State → phase mapping (optional, for backwards compatibility)
        self._state_phase_mapping = self._config.get("state_phase_mapping", {})

        # Default target intent when data extracted in data-expecting context
        self._default_data_intent = self._config.get(
            "default_data_intent", "info_provided"
        )

        # Confidence threshold for refinement
        self._min_confidence = self._config.get("min_confidence_for_refinement", 0.75)

        # BUG #2 FIX: Validate required mappings at startup
        if "answer_with_pricing" not in self._action_expects_data:
            logger.warning("Missing action_expects_data['answer_with_pricing'] — Bug #2 fix incomplete")
        if "answer_with_pricing" not in self._action_data_intent:
            logger.warning("Missing action_data_intent['answer_with_pricing'] — Bug #2 fix incomplete")

        # Compile patterns for efficiency
        self._compiled_patterns: Dict[str, Pattern] = {}
        self._compile_all_patterns()

        # Stats for monitoring
        self._refinements_total = 0
        self._refinements_by_type: Dict[str, int] = {}
        self._refinements_by_reason: Dict[str, int] = {}
        self._ambiguities_resolved: Dict[str, int] = {}
        self._data_extracted_count: Dict[str, int] = {}

        logger.debug(
            "CompositeMessageRefinementLayer initialized",
            extra={
                "enabled": self._enabled,
                "action_expects_data_count": len(self._action_expects_data),
                "meta_signals_count": len(self._meta_signals),
                "ambiguous_patterns_count": len(self._ambiguous_patterns),
                "data_fields_count": len(self._data_fields),
            }
        )

    def _compile_all_patterns(self) -> None:
        """Compile all regex patterns for efficient matching."""
        # Compile data field extraction patterns
        for field_name, config in self._data_fields.items():
            patterns = config.get("extract_patterns", [])
            if patterns:
                combined = "|".join(f"({p})" for p in patterns)
                try:
                    self._compiled_patterns[f"data_{field_name}"] = re.compile(
                        combined, re.IGNORECASE
                    )
                except re.error as e:
                    logger.warning(f"Invalid regex pattern for {field_name}: {e}")

        # Compile meta signal patterns
        for signal_name, config in self._meta_signals.items():
            patterns = config.get("patterns", [])
            if patterns:
                combined = "|".join(f"({p})" for p in patterns)
                try:
                    self._compiled_patterns[f"meta_{signal_name}"] = re.compile(
                        combined, re.IGNORECASE
                    )
                except re.error as e:
                    logger.warning(f"Invalid regex pattern for {signal_name}: {e}")

        # Compile ambiguous patterns
        for pattern_name, config in self._ambiguous_patterns.items():
            patterns = config.get("patterns", [])
            if patterns:
                combined = "|".join(f"({p})" for p in patterns)
                try:
                    self._compiled_patterns[f"ambig_{pattern_name}"] = re.compile(
                        combined, re.IGNORECASE
                    )
                except re.error as e:
                    logger.warning(f"Invalid regex pattern for {pattern_name}: {e}")

    def _is_data_expecting_context(self, ctx: CompositeMessageContext) -> bool:
        """
        Check if current context expects data from user.

        This is flow-agnostic and based on:
        1. last_action (primary) - if action is in action_expects_data mapping
        2. expects_data_type hint (explicit)
        3. state (fallback) - some states inherently expect data

        Args:
            ctx: Message context

        Returns:
            True if context expects data
        """
        # Check explicit hint
        if ctx.expects_data_type:
            return True

        # Check action-based expectation (primary mechanism)
        if ctx.last_action and ctx.last_action in self._action_expects_data:
            return True

        # Check state-based expectation (fallback)
        data_expecting_states = self._config.get("data_expecting_states", set())
        if ctx.state and ctx.state in data_expecting_states:
            return True

        # Check phase-based expectation (for backwards compatibility with SPIN etc.)
        data_expecting_phases = self._config.get("data_expecting_phases", set())
        if ctx.current_phase and ctx.current_phase in data_expecting_phases:
            return True

        return False

    def _get_expected_data_type(self, ctx: CompositeMessageContext) -> Optional[str]:
        """
        Get expected data type from context.

        Args:
            ctx: Message context

        Returns:
            Expected data type (e.g., "company_size") or None
        """
        # Explicit hint takes priority
        if ctx.expects_data_type:
            return ctx.expects_data_type

        # Action-based expectation
        if ctx.last_action:
            return self._action_expects_data.get(ctx.last_action)

        return None

    def _get_target_intent(self, ctx: CompositeMessageContext) -> str:
        """
        Get target intent for data provided in current context.

        Args:
            ctx: Message context

        Returns:
            Target intent (e.g., "info_provided", "situation_provided")
        """
        # Action-specific mapping takes priority
        if ctx.last_action and ctx.last_action in self._action_data_intent:
            return self._action_data_intent[ctx.last_action]

        # Default data intent
        return self._default_data_intent

    def should_refine(self, ctx: CompositeMessageContext) -> bool:
        """
        Determine if classification should be refined.

        Returns True if:
        1. Layer is enabled
        2. Intent is in refinable set (objection, unclear, etc.)
        3. Message contains potential data (numbers, keywords)
        4. Context expects data (based on action, state, or phase)

        Args:
            ctx: CompositeMessageContext with classification info

        Returns:
            True if refinement should be considered, False otherwise
        """
        if not self._enabled:
            return False

        # Only refine specific intents
        if ctx.intent not in self.REFINABLE_INTENTS:
            return False

        # Check if message contains potential data
        if not self._contains_potential_data(ctx.message):
            return False

        # Check if context expects data
        return self._is_data_expecting_context(ctx)

    def _contains_potential_data(self, message: str) -> bool:
        """
        Check if message contains potential extractable data.

        Looks for:
        - Numbers (quantities, sizes, etc.)
        - Keywords matching data field patterns
        - Quantity indicators

        Args:
            message: User's message text

        Returns:
            True if message likely contains data
        """
        text = message.lower()

        # Check for numbers (strongest signal)
        if re.search(r'\d+', text):
            return True

        # Check compiled data field patterns
        for key, pattern in self._compiled_patterns.items():
            if key.startswith("data_") and pattern.search(text):
                return True

        return False

    def refine(
        self,
        message: str,
        llm_result: Dict[str, Any],
        ctx: CompositeMessageContext
    ) -> Dict[str, Any]:
        """
        Refine composite message classification using context and data prioritization.

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

            # Analyze the message for data and signals
            analysis = self._analyze_message(message, ctx)

            # Apply refinement rules based on analysis
            result = self._apply_refinement_rules(ctx, analysis)

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
                if result.ambiguity_resolved:
                    self._ambiguities_resolved[result.ambiguity_resolved] = (
                        self._ambiguities_resolved.get(result.ambiguity_resolved, 0) + 1
                    )
                for field_name in result.extracted_data:
                    self._data_extracted_count[field_name] = (
                        self._data_extracted_count.get(field_name, 0) + 1
                    )

                logger.info(
                    "Composite message refined",
                    extra={
                        "original_intent": ctx.intent,
                        "refined_intent": result.intent,
                        "reason": result.refinement_reason,
                        "original_confidence": ctx.confidence,
                        "refined_confidence": result.confidence,
                        "extracted_data": result.extracted_data,
                        "secondary_signals": result.secondary_signals,
                        "ambiguity_resolved": result.ambiguity_resolved,
                        "message": message[:50],
                        "current_phase": ctx.current_phase,
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
                refined_result["refinement_layer"] = "composite"

                # Merge extracted data (new data takes precedence)
                existing_data = refined_result.get("extracted_data", {})
                merged_data = {**existing_data, **result.extracted_data}
                refined_result["extracted_data"] = merged_data

                # Add secondary signals as metadata
                if result.secondary_signals:
                    refined_result["secondary_signals"] = result.secondary_signals

                # Add ambiguity resolution info
                if result.ambiguity_resolved:
                    refined_result["ambiguity_resolved"] = result.ambiguity_resolved

                return refined_result

            return llm_result

        except Exception as e:
            # Fail-safe: return original result on any error
            logger.warning(
                "Composite refinement failed, returning original result",
                extra={
                    "error": str(e),
                    "user_message": message[:50],
                    "intent": ctx.intent,
                },
                exc_info=True
            )
            return llm_result

    def _analyze_message(
        self,
        message: str,
        ctx: CompositeMessageContext
    ) -> Dict[str, Any]:
        """
        Analyze message for data, meta-signals, and ambiguities.

        Args:
            message: User's message text
            ctx: Composite message context

        Returns:
            Analysis dict with:
            - extracted_data: Dict of field -> value
            - meta_signals: List of detected meta-signals
            - ambiguities: List of detected ambiguous patterns
            - has_data: bool indicating if extractable data found
        """
        text = message.lower()
        analysis: Dict[str, Any] = {
            "extracted_data": {},
            "meta_signals": [],
            "ambiguities": [],
            "has_data": False,
        }

        # Get expected data type for focused extraction
        expected_type = self._get_expected_data_type(ctx)

        # Extract data fields
        extracted = self._extract_data_fields(text, expected_type)
        if extracted:
            analysis["extracted_data"] = extracted
            analysis["has_data"] = True

        # Detect meta-signals
        for signal_name, config in self._meta_signals.items():
            pattern_key = f"meta_{signal_name}"
            if pattern_key in self._compiled_patterns:
                if self._compiled_patterns[pattern_key].search(text):
                    analysis["meta_signals"].append(signal_name)

        # Detect ambiguities
        for ambig_name, config in self._ambiguous_patterns.items():
            pattern_key = f"ambig_{ambig_name}"
            if pattern_key in self._compiled_patterns:
                if self._compiled_patterns[pattern_key].search(text):
                    analysis["ambiguities"].append({
                        "name": ambig_name,
                        "config": config,
                    })

        return analysis

    def _extract_data_fields(
        self,
        text: str,
        expected_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Extract data fields from message text.

        Args:
            text: Lowercased message text
            expected_type: Optional hint about expected data type

        Returns:
            Dict of field_name -> extracted_value
        """
        extracted: Dict[str, Any] = {}

        # If we know what type is expected, try that first
        if expected_type:
            value = self._extract_field(text, expected_type)
            if value is not None:
                extracted[expected_type] = value
                return extracted  # Return immediately for focused extraction

        # Otherwise, try all configured data fields
        for field_name in self._data_fields:
            value = self._extract_field(text, field_name)
            if value is not None:
                extracted[field_name] = value

        return extracted

    def _extract_field(self, text: str, field_name: str) -> Optional[Any]:
        """
        Extract a specific field from text.

        Args:
            text: Lowercased message text
            field_name: Name of field to extract

        Returns:
            Extracted value or None
        """
        config = self._data_fields.get(field_name, {})
        field_type = config.get("type", "str")

        # Use compiled pattern if available
        pattern_key = f"data_{field_name}"
        if pattern_key in self._compiled_patterns:
            match = self._compiled_patterns[pattern_key].search(text)
            if match:
                # For int fields, find the numeric group
                if field_type == "int":
                    for group in match.groups():
                        if group and group.isdigit():
                            return self._convert_value(group, field_type, config)
                    # If no pure digit group, try to extract from match
                    import re
                    num_match = re.search(r'\d+', match.group())
                    if num_match:
                        return self._convert_value(num_match.group(), field_type, config)
                else:
                    # For other types, get first non-None group
                    for group in match.groups():
                        if group:
                            return self._convert_value(group, field_type, config)

        # Fallback: generic number extraction for int fields
        if field_type == "int":
            return self._extract_generic_number(text, config)

        return None

    def _extract_generic_number(
        self,
        text: str,
        config: Dict[str, Any]
    ) -> Optional[int]:
        """
        Extract a number from text with validation.

        Args:
            text: Lowercased message text
            config: Field configuration with min/max bounds

        Returns:
            Extracted integer or None
        """
        # Find all numbers in text
        numbers = re.findall(r'\d+', text)
        if not numbers:
            return None

        # Get validation bounds
        min_val = config.get("min", 1)
        max_val = config.get("max", 100000)

        # Return first valid number
        for num_str in numbers:
            try:
                num = int(num_str)
                if min_val <= num <= max_val:
                    return num
            except ValueError:
                continue

        return None

    def _convert_value(
        self,
        raw_value: str,
        field_type: str,
        config: Dict[str, Any]
    ) -> Optional[Any]:
        """
        Convert extracted raw value to target type.

        Args:
            raw_value: Raw string value
            field_type: Target type (int, str, bool, enum)
            config: Field configuration

        Returns:
            Converted value or None
        """
        try:
            if field_type == "int":
                value = int(raw_value)
                min_val = config.get("min", 1)
                max_val = config.get("max", 100000)
                if min_val <= value <= max_val:
                    return value
                return None

            elif field_type == "bool":
                return raw_value.lower() in ("да", "yes", "true", "1", "конечно")

            elif field_type == "enum":
                allowed = config.get("allowed_values", [])
                if raw_value.lower() in [v.lower() for v in allowed]:
                    return raw_value
                return None

            else:  # str
                return raw_value.strip()

        except (ValueError, TypeError):
            return None

    def _apply_refinement_rules(
        self,
        ctx: CompositeMessageContext,
        analysis: Dict[str, Any]
    ) -> CompositeRefinementResult:
        """
        Apply refinement rules based on message analysis.

        Rule priority:
        1. Data priority - if data extracted and context expects data → data intent
        2. Ambiguity resolution - resolve based on context
        3. Meta-signal handling - add as secondary signals

        Args:
            ctx: Composite message context
            analysis: Message analysis result

        Returns:
            CompositeRefinementResult with decision
        """
        # Rule 1: Data priority - core refinement logic
        if analysis["has_data"] and self._is_data_expecting_context(ctx):
            # Determine target intent based on context
            target_intent = self._get_target_intent(ctx)

            # Check for ambiguities that need resolution
            ambiguity_resolved = None
            for ambig in analysis["ambiguities"]:
                resolved = self._resolve_ambiguity(ambig, ctx, analysis)
                if resolved:
                    ambiguity_resolved = resolved

            return CompositeRefinementResult(
                intent=target_intent,
                confidence=self._min_confidence,
                refined=True,
                extracted_data=analysis["extracted_data"],
                secondary_signals=analysis["meta_signals"],
                original_intent=ctx.intent,
                refinement_reason="data_priority_in_expecting_context",
                ambiguity_resolved=ambiguity_resolved,
            )

        # No refinement needed - let other layers handle
        return CompositeRefinementResult(
            intent=ctx.intent,
            confidence=ctx.confidence,
            refined=False,
        )

    def _resolve_ambiguity(
        self,
        ambiguity: Dict[str, Any],
        ctx: CompositeMessageContext,
        analysis: Dict[str, Any]
    ) -> Optional[str]:
        """
        Resolve ambiguous phrase based on context.

        For example: "больше не нужно" after "сколько человек" question
        → "no more needed" (quantity clarification), not "not needed at all"

        Args:
            ambiguity: Detected ambiguity info
            ctx: Composite message context
            analysis: Full message analysis

        Returns:
            Description of resolution or None
        """
        ambig_name = ambiguity["name"]
        config = ambiguity.get("config", {})

        # Get contexts where this ambiguity resolves to data vs rejection
        data_resolving_actions = set(config.get("data_resolving_actions", []))
        rejection_resolving_actions = set(config.get("rejection_resolving_actions", []))

        # If data was extracted and we're in data-expecting context → data interpretation
        if analysis["has_data"] and self._is_data_expecting_context(ctx):
            return f"{ambig_name}:quantity_clarification"

        # If action explicitly suggests data interpretation
        if ctx.last_action and ctx.last_action in data_resolving_actions:
            return f"{ambig_name}:data_response"

        # If action suggests rejection interpretation
        if ctx.last_action and ctx.last_action in rejection_resolving_actions:
            return f"{ambig_name}:rejection"

        return None

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
            "ambiguities_resolved": dict(self._ambiguities_resolved),
            "data_extracted_count": dict(self._data_extracted_count),
            "enabled": self._enabled,
        }


# Convenience function for external use
def create_composite_message_context(
    message: str,
    intent: str,
    confidence: float,
    context: Optional[Dict[str, Any]] = None
) -> CompositeMessageContext:
    """
    Create CompositeMessageContext from a classifier context dict.

    This function is flow-agnostic and works with any context structure.

    Args:
        message: User's message text
        intent: Classified intent
        confidence: Classification confidence
        context: Optional dict with state, phase, last_action, etc.

    Returns:
        CompositeMessageContext instance
    """
    context = context or {}

    # Determine current phase from various possible sources
    current_phase = (
        context.get("current_phase") or
        context.get("spin_phase") or
        context.get("phase") or
        context.get("dialogue_phase")
    )

    return CompositeMessageContext(
        message=message,
        intent=intent,
        confidence=confidence,
        current_phase=current_phase,
        state=context.get("state"),
        last_action=context.get("last_action"),
        extracted_data=context.get("extracted_data", {}),
        turn_number=context.get("turn_number", 0),
        expects_data_type=context.get("expects_data_type"),
    )
