# src/blackboard/sources/intent_processor.py

from typing import Optional, Dict, Any, List, Union, TYPE_CHECKING
import logging

from ..knowledge_source import KnowledgeSource
from ..blackboard import DialogueBlackboard
from ..enums import Priority
from src.conditions.state_machine.context import EvaluatorContext

if TYPE_CHECKING:
    from src.rules.resolver import RuleResolver
    from src.conditions.registry import ConditionRegistry

logger = logging.getLogger(__name__)


class IntentProcessorSource(KnowledgeSource):
    """
    Knowledge Source for general intent-to-action mapping.

    Responsibility:
        - Map intents to actions based on state rules
        - Use RuleResolver for conditional rule evaluation
        - Handle rules defined in state configuration

    DOES NOT handle:
        - Price questions (handled by PriceQuestionSource)
        - Objection limits (handled by ObjectionGuardSource)
        - State transitions (handled by TransitionResolverSource)
        - Data completeness (handled by DataCollectorSource)

    Rule formats supported:
        1. Simple string: "unclear": "probe_situation"
        2. Conditional dict: {"when": "condition", "then": "action"}
        3. Conditional chain: [{"when": "cond1", "then": "act1"}, "default"]
    """

    # Intents handled by dedicated sources (skip here)
    DEDICATED_SOURCE_INTENTS = {
        # Price questions handled by PriceQuestionSource
        "price_question",
        "pricing_details",
        "cost_inquiry",
        "discount_request",
        "payment_terms",
        "pricing_comparison",
        "budget_question",
    }

    def __init__(
        self,
        rule_resolver: Optional['RuleResolver'] = None,
        condition_registry: Optional['ConditionRegistry'] = None,
        name: str = "IntentProcessorSource"
    ):
        """
        Initialize the intent processor source.

        Args:
            rule_resolver: RuleResolver instance for conditional rules.
                          Created if not provided (uses sm_registry).
            condition_registry: ConditionRegistry for condition evaluation.
                               Created if not provided (uses sm_registry).
            name: Source name for logging
        """
        super().__init__(name)

        # Lazy initialization of defaults to avoid circular imports
        if rule_resolver is not None:
            self._rule_resolver = rule_resolver
        else:
            from src.rules.resolver import create_resolver
            self._rule_resolver = create_resolver()

        if condition_registry is not None:
            self._condition_registry = condition_registry
        else:
            from src.conditions.state_machine.registry import sm_registry
            self._condition_registry = sm_registry

    @property
    def rule_resolver(self) -> 'RuleResolver':
        """Get the rule resolver instance."""
        return self._rule_resolver

    @property
    def condition_registry(self) -> 'ConditionRegistry':
        """Get the condition registry instance."""
        return self._condition_registry

    def should_contribute(self, blackboard: DialogueBlackboard) -> bool:
        """
        Quick check: should we process this intent?

        Skip if:
        - Source is disabled
        - Intent is handled by a dedicated source
        - No rules defined for current state
        """
        if not self._enabled:
            return False

        intent = blackboard.current_intent

        # Skip intents handled by dedicated sources
        if intent in self.DEDICATED_SOURCE_INTENTS:
            return False

        return True

    def contribute(self, blackboard: DialogueBlackboard) -> None:
        """
        Map intent to action using state rules.

        Algorithm:
        1. Get rules from current state config
        2. Check if intent has a rule defined
        3. If conditional rule, evaluate using RuleResolver
        4. Propose resolved action
        """
        if not self._enabled:
            return

        ctx = blackboard.get_context()
        intent = ctx.current_intent

        # Skip dedicated source intents
        if intent in self.DEDICATED_SOURCE_INTENTS:
            self._log_contribution(
                reason=f"Intent {intent} handled by dedicated source"
            )
            return

        # Get rules from state config
        rules = ctx.state_config.get("rules", {})

        # Check if intent has a rule
        if intent not in rules:
            self._log_contribution(
                reason=f"No rule defined for intent: {intent}"
            )
            return

        rule = rules[intent]

        # Resolve the rule (handles simple string, conditional dict, chain)
        action = self._resolve_rule(rule, ctx)

        if not action:
            self._log_contribution(
                reason=f"Rule for {intent} evaluated to None"
            )
            return

        # Determine if action should be combinable
        # Most actions are combinable, but some block transitions
        blocking_actions = {
            "handle_rejection",
            "emergency_escalate",
            "end_conversation",
        }
        combinable = action not in blocking_actions

        # Propose the action
        blackboard.propose_action(
            action=action,
            priority=Priority.NORMAL,
            combinable=combinable,
            reason_code=f"rule_{intent}",
            source_name=self.name,
            metadata={
                "intent": intent,
                "rule_type": type(rule).__name__,
            }
        )

        self._log_contribution(
            action=action,
            reason=f"Rule matched for intent: {intent}"
        )

    def _resolve_rule(
        self,
        rule: Union[str, Dict, List],
        ctx
    ) -> Optional[str]:
        """
        Resolve a rule to an action.

        Args:
            rule: Rule definition (string, dict, or list)
            ctx: Context snapshot

        Returns:
            Resolved action name or None
        """
        # Simple string rule
        if isinstance(rule, str):
            return rule

        # Conditional dict rule: {"when": "condition", "then": "action"}
        if isinstance(rule, dict):
            condition = rule.get("when")
            action = rule.get("then")

            if condition and action:
                # Build evaluation context for condition registry
                eval_ctx = self._build_eval_context(ctx)

                if self._condition_registry.evaluate(condition, eval_ctx):
                    return action

            return None

        # Conditional chain: [{"when": "c1", "then": "a1"}, ..., "default"]
        if isinstance(rule, list):
            for item in rule:
                if isinstance(item, str):
                    # Default fallback
                    return item

                if isinstance(item, dict):
                    condition = item.get("when")
                    action = item.get("then")

                    if condition and action:
                        eval_ctx = self._build_eval_context(ctx)

                        if self._condition_registry.evaluate(condition, eval_ctx):
                            return action

            return None

        logger.warning(f"Unknown rule type: {type(rule)}")
        return None

    def _build_eval_context(self, ctx) -> EvaluatorContext:
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
