# src/blackboard/sources/fact_question.py

"""
Fact Question Knowledge Source for Dialogue Blackboard System.

Architectural Solution for the "Lost Question" Bug - Part 2.

Problem:
    Questions like "question_features", "question_integrations", "question_technical"
    don't have dedicated Knowledge Sources like PriceQuestionSource.
    When these questions are lost in composite messages (classified as info_provided),
    there's no mechanism to recover and answer them.

Solution:
    This source handles ALL fact-based questions universally:
    1. Checks primary intent for question_* patterns
    2. Checks secondary_intents from SecondaryIntentDetectionLayer
    3. Proposes answer_with_facts action with HIGH priority
    4. Always combinable=True (allows state transitions)

Architecture:
    - Extends PriceQuestionSource pattern (proven architecture)
    - Uses secondary_intents from classification result
    - Configuration-driven: fact_intents from constants.yaml
    - Respects YAML rules for custom actions per intent

Design Principles:
    - UNIVERSAL: Handles any question requiring factual answer
    - NON-BLOCKING: combinable=True allows transitions
    - CONFIGURABLE: Intents and actions from YAML
    - FAIL-SAFE: Safe defaults on any error

Relationship with Other Sources:
    - PriceQuestionSource: Handles price_* intents specifically (keeps for backward compat)
    - FactQuestionSource: Handles all OTHER fact-based questions
    - Overlap is OK: ConflictResolver will pick highest priority

Usage:
    # Registered automatically via SourceRegistry
    # Activated when:
    # 1. current_intent in fact_question_intents, OR
    # 2. secondary_intents contains fact_question intent
"""

from typing import Set, Optional, Union, Dict, List, Any, TYPE_CHECKING, FrozenSet
import logging

from ..knowledge_source import KnowledgeSource
from ..enums import Priority

if TYPE_CHECKING:
    from ..blackboard import DialogueBlackboard
    from src.conditions.registry import ConditionRegistry

logger = logging.getLogger(__name__)


class FactQuestionSource(KnowledgeSource):
    """
    Knowledge Source for handling fact-based questions.

    Responsibility:
        - Detect fact-requiring question intents (primary OR secondary)
        - Check YAML rules for custom actions
        - Propose answer_with_facts or custom action
        - Always combinable=True (allows state transitions)

    Intents handled (default set, configurable via YAML):
        - question_features
        - question_integrations
        - question_technical
        - question_equipment_*
        - question_tariff_*
        - question_tis_*
        - question_fiscal_*
        - question_security
        - comparison
        - And more...

    Key Innovation:
        This source checks BOTH primary intent AND secondary_intents.
        This solves the "lost question" bug where composite messages
        have data as primary and question as secondary.

    Example:
        Message: "100 человек. Как насчёт интеграции с Каспи?"
        Primary intent: info_provided (data detected)
        Secondary intents: ["question_integrations"]

        FactQuestionSource detects "question_integrations" in secondary
        and proposes "answer_with_facts" to respond to the question.
    """

    # Default fact-requiring intents (can be overridden from config)
    DEFAULT_FACT_INTENTS: FrozenSet[str] = frozenset({
        # Features and capabilities
        "question_features",
        "question_capabilities",

        # Integrations
        "question_integrations",
        "question_kaspi_integration",
        "question_bank_terminal",
        "question_1c_integration",
        "question_api",

        # Technical
        "question_technical",
        "question_security",
        "question_requirements",
        "question_setup",

        # Equipment
        "question_equipment_general",
        "question_pos_monoblock",
        "question_scales",
        "question_scanner",
        "question_printer",

        # Tariffs (excluding price - handled by PriceQuestionSource)
        "question_tariff_comparison",
        "question_tariff_mini",
        "question_tariff_lite",
        "question_tariff_standard",
        "question_tariff_professional",
        "question_tariff_enterprise",

        # TIS/Fiscal
        "question_tis_general",
        "question_tis_limits",
        "question_fiscal_general",

        # Business scenarios
        "question_grocery_store",
        "question_restaurant_cafe",
        "question_retail_shop",
        "question_wholesale",
        "question_services",

        # Accounting
        "question_accounting_services",
        "question_esf_snt",

        # Comparison with competitors
        "comparison",
        "question_competitor",

        # Support
        "question_support",
        "question_training",
        "question_implementation",

        # Delivery
        "question_delivery",
        "question_delivery_time",
    })

    # Intents to exclude (handled by other sources)
    EXCLUDED_INTENTS: FrozenSet[str] = frozenset({
        "price_question",
        "pricing_details",
        "cost_inquiry",
        "discount_request",
        "payment_terms",
        "pricing_comparison",
        "budget_question",
    })

    # Default action when no YAML rule defined
    DEFAULT_ACTION = "answer_with_facts"

    # Custom actions for specific intents (fallback if no YAML rule)
    INTENT_SPECIFIC_ACTIONS: Dict[str, str] = {
        "question_technical": "answer_technical_question",
        "question_security": "answer_security_question",
        "comparison": "compare_with_competitor",
        "question_competitor": "compare_with_competitor",
        "question_support": "explain_support_options",
        "question_training": "explain_training_options",
        "question_implementation": "explain_implementation_process",
    }

    def __init__(
        self,
        fact_intents: Optional[Set[str]] = None,
        condition_registry: Optional['ConditionRegistry'] = None,
        name: str = "FactQuestionSource"
    ):
        """
        Initialize the fact question source.

        Args:
            fact_intents: Set of intents considered fact-requiring.
                         Defaults to config from YAML, then DEFAULT_FACT_INTENTS.
            condition_registry: ConditionRegistry for conditional rules.
            name: Source name for logging
        """
        super().__init__(name)

        # Load config from YAML (SSoT)
        self._config = self._load_config()

        # Build fact intents set (exclude price intents to avoid overlap)
        if fact_intents is not None:
            self._fact_intents = fact_intents - self.EXCLUDED_INTENTS
        else:
            # Priority: YAML config -> DEFAULT_FACT_INTENTS (fallback)
            yaml_intents = self._config.get("fact_intents", [])
            if yaml_intents:
                self._fact_intents = set(yaml_intents) - self.EXCLUDED_INTENTS
            else:
                self._fact_intents = set(self.DEFAULT_FACT_INTENTS)

        # Load default actions from YAML (merges with hardcoded)
        yaml_actions = self._config.get("default_actions", {})
        self._intent_actions = {**self.INTENT_SPECIFIC_ACTIONS, **yaml_actions}

        # Lazy initialization of condition registry
        if condition_registry is not None:
            self._condition_registry = condition_registry
        else:
            from src.conditions.state_machine.registry import sm_registry
            self._condition_registry = sm_registry

        # Stats
        self._primary_detections = 0
        self._secondary_detections = 0

        logger.debug(
            f"{self.name} initialized with {len(self._fact_intents)} fact intents"
        )

    @property
    def fact_intents(self) -> Set[str]:
        """Get the set of fact-requiring intents."""
        return self._fact_intents

    def add_fact_intent(self, intent: str) -> None:
        """Add an intent to the fact intents set."""
        if intent not in self.EXCLUDED_INTENTS:
            self._fact_intents.add(intent)

    def remove_fact_intent(self, intent: str) -> None:
        """Remove an intent from the fact intents set."""
        self._fact_intents.discard(intent)

    @staticmethod
    def _load_config() -> Dict[str, Any]:
        """
        Load fact_question_source config from YAML (SSoT).

        Returns:
            Configuration dict with fact_intents, default_actions, etc.
            Falls back to empty dict on any error.
        """
        try:
            from src.yaml_config.constants import get_fact_question_source_config
            return get_fact_question_source_config()
        except ImportError:
            logger.warning(
                "Could not import get_fact_question_source_config, "
                "using DEFAULT_FACT_INTENTS as fallback"
            )
            return {}
        except Exception as e:
            logger.warning(f"Error loading fact_question_source config: {e}")
            return {}

    def should_contribute(self, blackboard: 'DialogueBlackboard') -> bool:
        """
        Check if current situation requires fact-based answer.

        Returns True if:
        1. Primary intent is a fact-requiring question, OR
        2. Secondary intents contain a fact-requiring question, OR
        3. repeated_question is a fact-requiring question (fallback)

        O(1) complexity for primary check, O(n) for secondary where n is small.

        Args:
            blackboard: The dialogue blackboard

        Returns:
            True if fact question detected, False otherwise
        """
        if not self._enabled:
            return False

        # Autonomous states have LLM-driven response with KB context via
        # kb_categories. FactQuestionSource's static template would override
        # the LLM's varied response.
        ctx = blackboard.get_context()
        state_config = getattr(ctx, "state_config", {}) if ctx is not None else {}
        if state_config.get("autonomous", False):
            self._log_contribution(
                reason="Skipped: autonomous state uses LLM-driven response"
            )
            return False

        # Check 1: Primary intent
        if blackboard.current_intent in self._fact_intents:
            return True

        # Check 2: Secondary intents (from SecondaryIntentDetectionLayer)
        secondary_intents = self._get_secondary_intents(ctx)

        if secondary_intents:
            for intent in secondary_intents:
                if intent in self._fact_intents:
                    return True

        # Check 3: repeated_question fallback (catches classifier misses)
        envelope = getattr(ctx, 'context_envelope', None) if ctx else None
        if envelope:
            rq = getattr(envelope, 'repeated_question', None)
            if rq and rq in self._fact_intents:
                return True

        return False

    def _get_secondary_intents(self, ctx: Any) -> List[str]:
        """
        Extract secondary intents from context.

        Secondary intents are populated by SecondaryIntentDetectionLayer
        and stored in the classification result.

        Args:
            ctx: Context snapshot

        Returns:
            List of secondary intent names
        """
        # Try to get from context_envelope (where refinement results are stored)
        envelope = ctx.context_envelope
        if envelope is not None:
            # Check for secondary_intents in various possible locations
            secondary = getattr(envelope, "secondary_intents", None)
            if secondary:
                return list(secondary)

        return []

    def contribute(self, blackboard: 'DialogueBlackboard') -> None:
        """
        Propose action for fact-based questions.

        Algorithm:
        1. Determine which fact intent triggered (primary or secondary)
        2. Check YAML rules for custom action
        3. If no rule, use intent-specific or default action
        4. Propose with HIGH priority, combinable=True

        Args:
            blackboard: The dialogue blackboard to contribute to
        """
        if not self._enabled:
            return

        ctx = blackboard.get_context()
        primary_intent = ctx.current_intent

        # Determine which fact intent to handle
        fact_intent = None
        detection_source = "none"

        # Priority 1: Primary intent
        if primary_intent in self._fact_intents:
            fact_intent = primary_intent
            detection_source = "primary"
            self._primary_detections += 1

        # Priority 2: Secondary intents
        if fact_intent is None:
            secondary_intents = self._get_secondary_intents(ctx)
            for intent in secondary_intents:
                if intent in self._fact_intents:
                    fact_intent = intent
                    detection_source = "secondary"
                    self._secondary_detections += 1
                    break

        # Priority 3: repeated_question fallback
        if fact_intent is None:
            envelope = getattr(ctx, 'context_envelope', None)
            if envelope:
                rq = getattr(envelope, 'repeated_question', None)
                if rq and rq in self._fact_intents:
                    fact_intent = rq
                    detection_source = "repeated_question"

        if fact_intent is None:
            self._log_contribution(reason="No fact intent found")
            return

        # Resolve action from YAML rules
        rules = ctx.state_config.get("rules", {})
        action = None
        rule_source = "fallback"

        if fact_intent in rules:
            rule = rules[fact_intent]
            action = self._resolve_rule(rule, ctx)
            if action:
                rule_source = "yaml_rule"
                logger.debug(
                    f"Fact intent '{fact_intent}' resolved from YAML rule: {action}"
                )

        # Fallback: intent-specific or default action (from YAML or hardcoded)
        if not action:
            action = self._intent_actions.get(
                fact_intent, self._config.get("fallback_action", self.DEFAULT_ACTION)
            )
            rule_source = "fallback"
            logger.debug(
                f"Fact intent '{fact_intent}' using fallback action: {action}"
            )

        # Propose action with HIGH priority (but combinable!)
        blackboard.propose_action(
            action=action,
            priority=Priority.HIGH,
            combinable=True,  # KEY: Allows coexistence with transitions
            reason_code="fact_question_detected",
            source_name=self.name,
            metadata={
                "fact_intent": fact_intent,
                "detection_source": detection_source,
                "primary_intent": primary_intent,
                "rule_source": rule_source,
            }
        )

        self._log_contribution(
            action=action,
            reason=f"Fact intent '{fact_intent}' detected via {detection_source}"
        )

    def _resolve_rule(
        self,
        rule: Union[str, Dict, List],
        ctx: Any
    ) -> Optional[str]:
        """
        Resolve a rule to an action.

        Supports same formats as PriceQuestionSource:
        - Simple string: "answer_with_facts"
        - Conditional dict: {"when": "condition", "then": "action"}
        - Conditional chain: [{"when": "c1", "then": "a1"}, "default"]

        Args:
            rule: Rule definition from YAML
            ctx: Context snapshot

        Returns:
            Resolved action name or None
        """
        # Simple string rule
        if isinstance(rule, str):
            return rule

        # Conditional dict
        if isinstance(rule, dict):
            condition = rule.get("when")
            action = rule.get("then")

            if condition and action:
                from src.conditions.state_machine.context import EvaluatorContext
                eval_ctx = self._build_eval_context(ctx)

                if self._evaluate_condition(condition, eval_ctx):
                    return action

            return None

        # Conditional chain
        if isinstance(rule, list):
            for item in rule:
                if isinstance(item, str):
                    return item

                if isinstance(item, dict):
                    condition = item.get("when")
                    action = item.get("then")

                    if condition and action:
                        from src.conditions.state_machine.context import EvaluatorContext
                        eval_ctx = self._build_eval_context(ctx)

                        if self._evaluate_condition(condition, eval_ctx):
                            return action

            return None

        logger.warning(f"Unknown rule type: {type(rule)}")
        return None

    def _evaluate_condition(self, condition: str, eval_ctx: Any) -> bool:
        """Evaluate a condition using the registry."""
        try:
            if self._condition_registry.has(condition):
                return self._condition_registry.evaluate(condition, eval_ctx)
            else:
                logger.warning(f"Condition '{condition}' not found in registry")
                return False
        except Exception as e:
            logger.error(f"Error evaluating condition '{condition}': {e}")
            return False

    def _build_eval_context(self, ctx: Any) -> Any:
        """Build evaluation context for condition registry."""
        from src.conditions.state_machine.context import EvaluatorContext

        envelope = ctx.context_envelope
        current_phase = ctx.current_phase

        return EvaluatorContext(
            collected_data=dict(ctx.collected_data),
            state=ctx.state,
            turn_number=ctx.turn_number,
            current_phase=current_phase,
            is_phase_state=current_phase is not None,
            current_intent=ctx.current_intent,
            prev_intent=ctx.last_intent,
            intent_tracker=ctx.intent_tracker,
            missing_required_data=ctx.get_missing_required_data(),
            config=ctx.state_config,
            frustration_level=getattr(envelope, "frustration_level", 0),
            is_stuck=getattr(envelope, "is_stuck", False),
            has_oscillation=getattr(envelope, "has_oscillation", False),
            momentum=getattr(envelope, "momentum", 0.0),
            engagement_level=getattr(envelope, "engagement_level", "medium"),
            repeated_question=getattr(envelope, "repeated_question", None),
            tone=getattr(envelope, "tone", None),
        )

    def get_stats(self) -> Dict[str, Any]:
        """Get monitoring statistics."""
        return {
            "name": self.name,
            "enabled": self._enabled,
            "fact_intents_count": len(self._fact_intents),
            "primary_detections": self._primary_detections,
            "secondary_detections": self._secondary_detections,
            "total_detections": self._primary_detections + self._secondary_detections,
            "secondary_detection_rate": (
                self._secondary_detections / (self._primary_detections + self._secondary_detections)
                if (self._primary_detections + self._secondary_detections) > 0
                else 0.0
            ),
        }
