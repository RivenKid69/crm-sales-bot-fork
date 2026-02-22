# src/blackboard/sources/transition_resolver.py

"""
Transition Resolver Knowledge Source for Dialogue Blackboard System.

This source handles intent-based state transitions (NOT data_complete transitions).
Clear separation of concerns with DataCollectorSource which handles data-based transitions.
"""

from typing import Optional, Dict, Any, List, Union, Set, TYPE_CHECKING
import logging

from ..knowledge_source import KnowledgeSource
from ..enums import Priority
from src.conditions.state_machine.registry import get_sm_registry
from src.conditions.state_machine.context import EvaluatorContext

if TYPE_CHECKING:
    from ..blackboard import DialogueBlackboard

logger = logging.getLogger(__name__)


class TransitionResolverSource(KnowledgeSource):
    """
    Knowledge Source for intent-based state transitions.

    Responsibility:
        - Detect explicit intent-to-transition mappings
        - Handle conditional transitions
        - Propose state transitions based on intent

    DOES NOT handle:
        - data_complete transitions (handled by DataCollectorSource)
        - Objection limit transitions (handled by ObjectionGuardSource)
        - "any" fallback transitions (handled separately in Orchestrator)

    Clear boundary with DataCollectorSource:
        - TransitionResolverSource: intent-based transitions (e.g., "rejection" -> "soft_close")
        - DataCollectorSource: data-based transitions (data_complete only)
    """

    # Transition triggers handled by other sources
    EXCLUDED_TRIGGERS: Set[str] = {
        "data_complete",  # Handled by DataCollectorSource
        "any",            # Handled separately as fallback
    }

    def __init__(
        self,
        condition_registry=None,
        expression_parser=None,
        name: str = "TransitionResolverSource"
    ):
        """
        Initialize the transition resolver source.

        Args:
            condition_registry: ConditionRegistry for conditional transitions.
                               Uses state_machine registry if not provided.
            expression_parser: ConditionExpressionParser for composite conditions.
            name: Source name for logging
        """
        super().__init__(name)
        self._condition_registry = condition_registry or get_sm_registry()
        self._expression_parser = expression_parser

    def should_contribute(self, blackboard: 'DialogueBlackboard') -> bool:
        """
        Quick check: does current state have transitions defined?
        """
        if not self._enabled:
            return False

        ctx = blackboard.get_context()
        transitions = ctx.state_config.get("transitions", {})

        return len(transitions) > 0

    def contribute(self, blackboard: 'DialogueBlackboard') -> None:
        """
        Check for intent-based transitions and propose if matched.

        Algorithm:
        1. Get transitions from state config
        2. Check if current intent matches a transition trigger
        3. Handle conditional transitions
        4. Propose transition with appropriate priority
        """
        ctx = blackboard.get_context()
        intent = ctx.current_intent
        transitions = ctx.state_config.get("transitions", {})

        # Skip excluded triggers
        if intent in self.EXCLUDED_TRIGGERS:
            self._log_contribution(
                reason=f"Trigger {intent} handled by dedicated source"
            )
            return

        # Check if intent has a transition defined
        if intent not in transitions:
            self._log_contribution(
                reason=f"No transition defined for intent: {intent}"
            )
            return

        transition_def = transitions[intent]

        # Resolve the transition
        next_state = self._resolve_transition(transition_def, ctx)

        if not next_state:
            self._log_contribution(
                reason=f"Transition for {intent} evaluated to None"
            )
            return

        # Autonomous flow: keep objections inside autonomous stages.
        # Shared _base transition "handle_objection" is deterministic and bypasses
        # AutonomousDecisionSource; remap it to autonomous objection phase state
        # instead of restarting from entry_state.
        flow_config = ctx.flow_config
        flow_name = flow_config.get("name", "") if isinstance(flow_config, dict) else getattr(flow_config, "name", "")
        if flow_name == "autonomous" and next_state == "handle_objection":
            phases = flow_config.get("phases", {}) if isinstance(flow_config, dict) else {}
            mapping = phases.get("mapping", {}) if isinstance(phases, dict) else {}
            entry_state = mapping.get("objection_handling", "autonomous_objection_handling")
            logger.debug(
                "TransitionResolverSource: autonomous remap handle_objection -> %s",
                entry_state,
            )
            next_state = entry_state

        # Determine priority based on intent type
        high_priority_intents = {
            "rejection",
            "hard_no",
            "end_conversation",
            "explicit_close_request",
        }

        is_autonomous = ctx.state_config.get("autonomous", False)
        is_autonomous_context = is_autonomous or (flow_name == "autonomous" and ctx.state == "greeting")
        if intent in high_priority_intents and is_autonomous_context:
            # In autonomous states, exit intents compete on equal footing with LLM
            priority = Priority.NORMAL
        else:
            priority = Priority.HIGH if intent in high_priority_intents else Priority.NORMAL

        # In autonomous greeting, avoid deterministic early exits (rejection/no_need/etc.).
        # Let AutonomousDecisionSource handle unusual first-turn behavior via LLM context.
        if flow_name == "autonomous" and ctx.state == "greeting" and intent in high_priority_intents:
            self._log_contribution(
                reason=f"Autonomous greeting: skip deterministic exit transition for intent {intent}"
            )
            return

        # Propose the transition
        blackboard.propose_transition(
            next_state=next_state,
            priority=priority,
            reason_code=f"intent_transition_{intent}",
            source_name=self.name,
            metadata={
                "trigger_intent": intent,
                "transition_type": type(transition_def).__name__,
            }
        )

        self._log_contribution(
            transition=next_state,
            reason=f"Intent-based transition: {intent} -> {next_state}"
        )

    def _resolve_transition(
        self,
        transition_def: Union[str, Dict, List],
        ctx
    ) -> Optional[str]:
        """
        Resolve a transition definition to a target state.

        Args:
            transition_def: Transition definition (string, dict, or list)
            ctx: Context snapshot

        Returns:
            Target state name or None
        """
        # Simple string transition
        if isinstance(transition_def, str):
            return transition_def

        # Conditional dict: {"when": "condition", "then": "state"}
        if isinstance(transition_def, dict):
            condition = transition_def.get("when")
            target = transition_def.get("then")

            if condition and target:
                eval_ctx = self._build_eval_context(ctx)

                if self._evaluate_condition(condition, eval_ctx):
                    return target

            return None

        # Conditional chain: [{"when": "c1", "then": "s1"}, ..., "default"]
        if isinstance(transition_def, list):
            for item in transition_def:
                if isinstance(item, str):
                    # Default fallback
                    return item

                if isinstance(item, dict):
                    condition = item.get("when")
                    target = item.get("then")

                    if condition and target:
                        eval_ctx = self._build_eval_context(ctx)

                        if self._evaluate_condition(condition, eval_ctx):
                            return target

            return None

        logger.warning(f"Unknown transition type: {type(transition_def)}")
        return None

    def _evaluate_condition(self, condition, eval_ctx: EvaluatorContext) -> bool:
        """
        Evaluate a condition using the shared utility (supports composite dict).

        Args:
            condition: Condition name (str) or composite dict to evaluate
            eval_ctx: Evaluation context

        Returns:
            True if condition is met, False otherwise
        """
        from src.conditions.expression_parser import evaluate_condition_value
        try:
            return evaluate_condition_value(
                condition, eval_ctx, self._condition_registry,
                self._expression_parser, source_name="TransitionResolverSource"
            )
        except (ValueError, TypeError) as e:
            logger.warning(f"Condition evaluation failed: {e}")
            return False
        except Exception as e:
            logger.error(f"Error evaluating condition '{condition}': {e}")
            return False

    def _build_eval_context(self, ctx) -> EvaluatorContext:
        """
        Build evaluation context for condition registry.

        Args:
            ctx: ContextSnapshot from blackboard

        Returns:
            EvaluatorContext for condition evaluation
        """
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
            persona=getattr(ctx, 'persona', 'default'),
        )
