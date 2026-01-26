# src/blackboard/sources/price_question.py

"""
Price Question Knowledge Source for Dialogue Blackboard System.

This source handles price-related questions and ensures they are answered
WITHOUT blocking data_complete transitions (combinable=True).

IMPORTANT: This source respects YAML rules defined in state configuration.
If a rule is defined for the price intent (e.g., in value_rules mixin),
that rule's action is used instead of the default answer_with_pricing.
"""

from typing import Set, Optional, Union, Dict, List, Any, TYPE_CHECKING
import logging

from ..knowledge_source import KnowledgeSource
from ..enums import Priority
from src.conditions.state_machine.context import EvaluatorContext

# FIX: Import from centralized constants (Single Source of Truth)
# This ensures PriceQuestionSource stays synchronized with constants.yaml
# and IntentTracker category_streak calculations
from src.yaml_config.constants import INTENT_CATEGORIES

if TYPE_CHECKING:
    from ..blackboard import DialogueBlackboard
    from src.conditions.registry import ConditionRegistry

logger = logging.getLogger(__name__)


def _get_price_intents_from_config() -> Set[str]:
    """
    Get price-related intents from INTENT_CATEGORIES (constants.yaml).

    This ensures synchronization with:
    - conditions.py price_repeated_3x/2x (uses category_streak("price_related"))
    - IntentTracker category tracking

    Falls back to hardcoded set if category not found.
    """
    intents = INTENT_CATEGORIES.get("price_related", [])
    if intents:
        return set(intents)

    # Fallback for backwards compatibility
    logger.warning("price_related category not found in constants.yaml, using fallback")
    return {
        "price_question",
        "pricing_details",
        "cost_inquiry",
        "discount_request",
        "payment_terms",
        "pricing_comparison",
        "budget_question",
    }


class PriceQuestionSource(KnowledgeSource):
    """
    Knowledge Source for handling price-related questions.

    Responsibility:
        - Detect price-related intents
        - Check YAML rules in state config for custom action
        - Propose rule-based action OR fallback to "answer_with_pricing"
        - Always combinable=True (allows state transitions to proceed)

    Intents handled (from constants.yaml price_related category):
        - price_question
        - pricing_details
        - cost_inquiry
        - discount_request
        - payment_terms
        - pricing_comparison
        - budget_question

    This source addresses the core problem: price questions should be answered
    WITHOUT blocking data_complete transitions.

    FIX: Now uses constants.yaml as Single Source of Truth for price intents.
    This ensures synchronization with IntentTracker.category_streak("price_related")
    and conditions.py price_repeated_3x/2x.
    """

    # FIX: Load from constants.yaml instead of hardcoding
    # This ensures synchronization across the system
    DEFAULT_PRICE_INTENTS: Set[str] = _get_price_intents_from_config()

    # Fallback actions when no rule is defined
    DEFAULT_ACTIONS: Dict[str, str] = {
        "discount_request": "handle_discount_request",
        "payment_terms": "explain_payment_terms",
        "pricing_comparison": "compare_pricing",
        "budget_question": "discuss_budget",
    }

    def __init__(
        self,
        price_intents: Optional[Set[str]] = None,
        condition_registry: Optional['ConditionRegistry'] = None,
        name: str = "PriceQuestionSource"
    ):
        """
        Initialize the price question source.

        Args:
            price_intents: Set of intents considered price-related.
                           Defaults to DEFAULT_PRICE_INTENTS.
            condition_registry: ConditionRegistry for conditional rules.
                               Uses state_machine registry if not provided.
            name: Source name for logging
        """
        super().__init__(name)
        self._price_intents = price_intents or self.DEFAULT_PRICE_INTENTS.copy()

        # Lazy initialization of condition registry
        if condition_registry is not None:
            self._condition_registry = condition_registry
        else:
            from src.conditions.state_machine.registry import sm_registry
            self._condition_registry = sm_registry

    @property
    def price_intents(self) -> Set[str]:
        """Get the set of price-related intents."""
        return self._price_intents

    def add_price_intent(self, intent: str) -> None:
        """Add an intent to the price intents set."""
        self._price_intents.add(intent)

    def remove_price_intent(self, intent: str) -> None:
        """Remove an intent from the price intents set."""
        self._price_intents.discard(intent)

    def should_contribute(self, blackboard: 'DialogueBlackboard') -> bool:
        """
        Quick check: is current intent price-related?

        O(1) check against price intents set.

        Args:
            blackboard: The dialogue blackboard

        Returns:
            True if current intent is price-related, False otherwise
        """
        if not self._enabled:
            return False

        return blackboard.current_intent in self._price_intents

    def contribute(self, blackboard: 'DialogueBlackboard') -> None:
        """
        Propose action for price questions, respecting YAML rules.

        Algorithm:
        1. Check if YAML rules define an action for this intent
        2. If rule exists, resolve it (handles conditionals)
        3. If no rule, use fallback action (answer_with_pricing or specific)

        Key design decision: combinable=True
        This allows the action to coexist with transitions (e.g., data_complete).
        The bot will answer the price question AND transition to the next phase.

        Args:
            blackboard: The dialogue blackboard to contribute to
        """
        if not self._enabled:
            return

        ctx = blackboard.get_context()
        intent = ctx.current_intent

        if intent not in self._price_intents:
            self._log_contribution(reason="Intent not price-related")
            return

        # FIX: First, check YAML rules in state config
        rules = ctx.state_config.get("rules", {})
        action = None
        rule_source = "fallback"

        if intent in rules:
            rule = rules[intent]
            action = self._resolve_rule(rule, ctx)
            if action:
                rule_source = "yaml_rule"
                logger.debug(f"Price intent '{intent}' resolved from YAML rule: {action}")

        # If no rule or rule evaluated to None, use fallback
        if not action:
            action = self.DEFAULT_ACTIONS.get(intent, "answer_with_pricing")
            rule_source = "fallback"
            logger.debug(f"Price intent '{intent}' using fallback action: {action}")

        # Check if we have pricing data available
        has_pricing = bool(ctx.collected_data.get("pricing_tier"))

        # Propose action with HIGH priority (but combinable!)
        blackboard.propose_action(
            action=action,
            priority=Priority.HIGH,
            combinable=True,  # KEY: Allows coexistence with transitions
            reason_code="price_question_priority",
            source_name=self.name,
            metadata={
                "original_intent": intent,
                "has_pricing_data": has_pricing,
                "rule_source": rule_source,
            }
        )

        self._log_contribution(
            action=action,
            reason=f"Price intent detected: {intent} (source: {rule_source})"
        )

    def _resolve_rule(
        self,
        rule: Union[str, Dict, List],
        ctx: Any
    ) -> Optional[str]:
        """
        Resolve a rule to an action.

        Supports:
        - Simple string: "calculate_roi_response"
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

        # Conditional dict: {"when": "condition", "then": "action"}
        if isinstance(rule, dict):
            condition = rule.get("when")
            action = rule.get("then")

            if condition and action:
                eval_ctx = self._build_eval_context(ctx)

                if self._evaluate_condition(condition, eval_ctx):
                    return action

            return None

        # Conditional chain: [{"when": "c1", "then": "a1"}, ..., "default"]
        if isinstance(rule, list):
            for item in rule:
                if isinstance(item, str):
                    # Default fallback (last item in chain)
                    return item

                if isinstance(item, dict):
                    condition = item.get("when")
                    action = item.get("then")

                    if condition and action:
                        eval_ctx = self._build_eval_context(ctx)

                        if self._evaluate_condition(condition, eval_ctx):
                            return action

            return None

        logger.warning(f"Unknown rule type: {type(rule)}")
        return None

    def _evaluate_condition(self, condition: str, eval_ctx: EvaluatorContext) -> bool:
        """
        Evaluate a condition using the registry.

        Args:
            condition: Condition name to evaluate
            eval_ctx: Evaluation context

        Returns:
            True if condition is met, False otherwise
        """
        try:
            if self._condition_registry.has(condition):
                return self._condition_registry.evaluate(condition, eval_ctx)
            else:
                logger.warning(f"Condition '{condition}' not found in registry")
                return False
        except Exception as e:
            logger.error(f"Error evaluating condition '{condition}': {e}")
            return False

    def _build_eval_context(self, ctx: Any) -> EvaluatorContext:
        """Build evaluation context for condition registry."""
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
            # Context-aware fields from envelope (if available)
            frustration_level=getattr(envelope, "frustration_level", 0),
            is_stuck=getattr(envelope, "is_stuck", False),
            has_oscillation=getattr(envelope, "has_oscillation", False),
            momentum_direction=getattr(envelope, "momentum_direction", "neutral"),
            momentum=getattr(envelope, "momentum", 0.0),
            engagement_level=getattr(envelope, "engagement_level", "medium"),
            repeated_question=getattr(envelope, "repeated_question", None),
            confidence_trend=getattr(envelope, "confidence_trend", "stable"),
            total_objections=getattr(envelope, "total_objections", 0),
            has_breakthrough=getattr(envelope, "has_breakthrough", False),
            turns_since_breakthrough=getattr(envelope, "turns_since_breakthrough", None),
            guard_intervention=getattr(envelope, "guard_intervention", None),
            tone=getattr(envelope, "tone", None),
            unclear_count=getattr(envelope, "unclear_count", 0),
        )
