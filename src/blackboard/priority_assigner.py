# src/blackboard/priority_assigner.py

"""
Priority assignment for Blackboard proposals based on FlowConfig.priorities.

This module maps YAML priority definitions to proposal ordering in the
Blackboard system. It does not generate proposals; it only assigns
priority_rank for tie-breaking within the same Priority enum.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from src.feature_flags import flags
from src.conditions.state_machine.context import EvaluatorContext
from src.conditions.state_machine.registry import sm_registry
from src.yaml_config.constants import INTENT_CATEGORIES, GO_BACK_INTENTS

from .enums import ProposalType
from .models import Proposal, ContextSnapshot


@dataclass(frozen=True)
class PriorityDefinition:
    """Parsed priority definition from YAML."""
    name: str
    priority: int
    intents: Optional[List[str]] = None
    intent_category: Optional[str] = None
    condition: Optional[str] = None
    feature_flag: Optional[str] = None
    trigger: Optional[str] = None
    action: Optional[str] = None
    handler: Optional[str] = None
    use_transitions: bool = False
    use_resolver: bool = False
    source: Optional[str] = None
    else_action: Optional[str] = None


class PriorityAssigner:
    """
    Assign numeric priority_rank to proposals based on FlowConfig.priorities.

    The rank is used as a tie-breaker in ConflictResolver when proposals share
    the same Priority enum value.
    """

    def __init__(
        self,
        flow_config,
        condition_registry=None,
    ):
        self._flow_config = flow_config
        self._condition_registry = condition_registry or sm_registry
        self._definitions = self._load_definitions(
            getattr(flow_config, "priorities", []) or []
        )
        self._intent_category_cache: Dict[str, set] = {}

    def assign(self, proposals: List[Proposal], ctx: ContextSnapshot) -> None:
        """Assign priority_rank to proposals in-place."""
        if not proposals or not self._definitions:
            return

        eval_ctx = self._build_eval_context(ctx)
        current_intent = ctx.current_intent

        for proposal in proposals:
            best = self._find_best_match(
                proposal=proposal,
                ctx=ctx,
                eval_ctx=eval_ctx,
                current_intent=current_intent,
            )
            if not best:
                continue

            if proposal.priority_rank is None or best.priority < proposal.priority_rank:
                proposal.priority_rank = best.priority
                proposal.metadata["priority_name"] = best.name
                proposal.metadata["priority_value"] = best.priority

    def _find_best_match(
        self,
        proposal: Proposal,
        ctx: ContextSnapshot,
        eval_ctx: EvaluatorContext,
        current_intent: str,
    ) -> Optional[PriorityDefinition]:
        best: Optional[PriorityDefinition] = None
        for definition in self._definitions:
            if not self._matches(definition, proposal, ctx, eval_ctx, current_intent):
                continue
            if best is None or definition.priority < best.priority:
                best = definition
        return best

    def _load_definitions(self, priorities: List[Dict[str, Any]]) -> List[PriorityDefinition]:
        definitions: List[PriorityDefinition] = []
        for item in priorities:
            if not isinstance(item, dict):
                continue

            intents = item.get("intents")
            if intents is not None and not isinstance(intents, list):
                intents = [intents]

            definition = PriorityDefinition(
                name=str(item.get("name", "")),
                priority=int(item.get("priority", 999)),
                intents=intents,
                intent_category=item.get("intent_category"),
                condition=item.get("condition"),
                feature_flag=item.get("feature_flag"),
                trigger=item.get("trigger"),
                action=item.get("action"),
                handler=item.get("handler"),
                use_transitions=bool(item.get("use_transitions")),
                use_resolver=bool(item.get("use_resolver")),
                source=item.get("source"),
                else_action=item.get("else"),
            )
            definitions.append(definition)

        return definitions

    def _matches(
        self,
        definition: PriorityDefinition,
        proposal: Proposal,
        ctx: ContextSnapshot,
        eval_ctx: EvaluatorContext,
        current_intent: str,
    ) -> bool:
        # Feature flag gating
        if definition.feature_flag:
            if not flags.is_enabled(definition.feature_flag):
                return False
            if not ctx.is_tenant_feature_enabled(definition.feature_flag):
                return False

        # Intent-based gating
        if definition.intents and current_intent not in definition.intents:
            return False

        if definition.intent_category:
            if not self._intent_in_category(current_intent, definition.intent_category):
                return False

        # Trigger gating (data_complete / any)
        if definition.trigger:
            if definition.trigger == "data_complete":
                if not self._is_data_complete_transition(proposal):
                    return False
            elif definition.trigger == "any":
                if not self._is_any_transition(proposal):
                    return False
            else:
                return False

        # Condition gating (with else semantics)
        if definition.condition:
            if not self._evaluate_condition(definition.condition, eval_ctx):
                if definition.else_action == "use_transitions":
                    # Don't boost intent-transitions in autonomous states —
                    # autonomous states handle all routing via AutonomousDecisionSource
                    if ctx.state_config.get("autonomous", False):
                        return False
                    return (
                        proposal.type == ProposalType.TRANSITION
                        and self._is_intent_transition(proposal)
                    )
                return False

        # Handler gating (priority handlers)
        if definition.handler:
            if not self._handler_matches(definition.handler, current_intent):
                return False

        # Action gating
        if definition.action:
            if proposal.type != ProposalType.ACTION:
                return False
            if proposal.value != definition.action:
                return False

        # Source gating (rules)
        if definition.source:
            if definition.source == "rules":
                if not self._is_rule_action(proposal):
                    return False
            else:
                return False

        # Resolver gating (rules imply action)
        if definition.use_resolver and proposal.type != ProposalType.ACTION:
            return False

        # Transition gating
        if definition.use_transitions:
            if proposal.type != ProposalType.TRANSITION:
                return False
            if not definition.intents and not definition.intent_category and not definition.trigger:
                # Only intent-based transitions should match generic transitions priority
                if not self._is_intent_transition(proposal):
                    return False

        return True

    def _handler_matches(self, handler: str, current_intent: str) -> bool:
        if handler == "phase_progress_handler":
            progress_intents = getattr(self._flow_config, "progress_intents", {}) or {}
            return current_intent in progress_intents
        if handler == "circular_flow_handler":
            return current_intent in GO_BACK_INTENTS
        return False

    def _is_rule_action(self, proposal: Proposal) -> bool:
        return (
            proposal.type == ProposalType.ACTION
            and proposal.reason_code.startswith("rule_")
        )

    def _is_intent_transition(self, proposal: Proposal) -> bool:
        return (
            proposal.type == ProposalType.TRANSITION
            and proposal.reason_code.startswith("intent_transition_")
        )

    def _is_data_complete_transition(self, proposal: Proposal) -> bool:
        return (
            proposal.type == ProposalType.TRANSITION
            and proposal.reason_code == "data_complete"
        )

    def _is_any_transition(self, proposal: Proposal) -> bool:
        return (
            proposal.type == ProposalType.TRANSITION
            and proposal.reason_code == "transition_any"
        )

    def _intent_in_category(self, intent: str, category: str) -> bool:
        if category in self._intent_category_cache:
            return intent in self._intent_category_cache[category]

        intents: Optional[List[str]] = None
        if hasattr(self._flow_config, "get_intent_category"):
            intents = self._flow_config.get_intent_category(category)

        if not intents:
            intents = INTENT_CATEGORIES.get(category, [])

        intent_set = set(intents or [])
        self._intent_category_cache[category] = intent_set
        return intent in intent_set

    def _evaluate_condition(self, condition: str, eval_ctx: EvaluatorContext) -> bool:
        if self._condition_registry.has(condition):
            return self._condition_registry.evaluate(condition, eval_ctx)
        return False

    def _build_eval_context(self, ctx: ContextSnapshot) -> EvaluatorContext:
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
