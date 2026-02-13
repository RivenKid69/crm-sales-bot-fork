# src/blackboard/sources/autonomous_decision.py

"""
AutonomousDecisionSource — LLM-driven state transition for autonomous flow.

Flow-gated: only fires when flow_name == "autonomous".
Calls LLM generate_structured() with Pydantic schema to decide:
- Whether to transition to the next sales phase
- Which action to take (always "autonomous_respond")

Priority: NORMAL (42 in registry order).
Safety sources (GoBackGuard, ConversationGuard, ObjectionGuard, PriceQuestion,
StallGuard) all fire at CRITICAL/HIGH and override this source.
"""

from typing import Optional, Any, TYPE_CHECKING
import logging

from pydantic import BaseModel

from ..knowledge_source import KnowledgeSource
from ..enums import Priority

if TYPE_CHECKING:
    from ..blackboard import DialogueBlackboard

logger = logging.getLogger(__name__)


class AutonomousDecision(BaseModel):
    """Pydantic schema for LLM structured output."""
    next_state: str
    action: str = "autonomous_respond"
    reasoning: str = ""
    should_transition: bool = False


class AutonomousDecisionSource(KnowledgeSource):
    """
    Knowledge Source for LLM-driven state transitions in autonomous flow.

    Only activates when:
    1. Flow name is "autonomous"
    2. Feature flag autonomous_flow is enabled

    Uses LLM to evaluate conversation context and decide whether to
    transition to the next sales phase.
    """

    def __init__(self, llm: Any = None, name: str = "AutonomousDecisionSource"):
        super().__init__(name)
        self._llm = llm

    def should_contribute(self, blackboard: 'DialogueBlackboard') -> bool:
        """Only contribute for autonomous flow with LLM available."""
        if self._llm is None:
            return False

        from src.feature_flags import flags
        if not flags.is_enabled("autonomous_flow"):
            return False

        # Flow-gate: only for autonomous flow
        ctx = blackboard.get_context()
        flow_config = ctx.flow_config
        flow_name = flow_config.get("name", "") if isinstance(flow_config, dict) else getattr(flow_config, "name", "")
        if flow_name != "autonomous":
            return False

        # Don't contribute for terminal/shared states (greeting, close, etc.)
        state = ctx.state
        if not state.startswith("autonomous_"):
            return False

        return True

    def contribute(self, blackboard: 'DialogueBlackboard') -> None:
        """
        Call LLM to decide state transition, then propose to blackboard.
        """
        ctx = blackboard.get_context()
        state = ctx.state
        state_config = ctx.state_config
        current_phase = state_config.get("phase", "")
        goal = state_config.get("goal", "")
        collected_data = ctx.collected_data
        intent = ctx.current_intent
        user_message = ctx.user_message

        # Get available autonomous states from flow config
        flow_cfg = ctx.flow_config
        if isinstance(flow_cfg, dict):
            all_states = flow_cfg.get("states", {})
        else:
            all_states = getattr(flow_cfg, "states", {})
        available_states = [
            s for s in all_states
            if s.startswith("autonomous_") and s != state
        ]

        # Get turn-in-state count from context envelope
        envelope = ctx.context_envelope if hasattr(ctx, 'context_envelope') else None
        turn_in_state = getattr(envelope, 'consecutive_same_state', 0) if envelope else 0
        max_turns = state_config.get("max_turns_in_state", 6)

        # Build prompt for LLM decision
        prompt = self._build_decision_prompt(
            state=state,
            phase=current_phase,
            goal=goal,
            intent=intent,
            user_message=user_message,
            collected_data=collected_data,
            available_states=available_states,
            turn_in_state=turn_in_state,
            max_turns=max_turns,
        )

        try:
            decision = self._llm.generate_structured(
                prompt=prompt,
                schema=AutonomousDecision,
                purpose="autonomous_decision",
            )
        except Exception as e:
            logger.warning("AutonomousDecisionSource LLM call failed: %s", e)
            decision = None

        if decision is None:
            # Fallback: stay in current state with autonomous_respond
            blackboard.propose_action(
                action="autonomous_respond",
                priority=Priority.NORMAL,
                reason_code="autonomous_llm_fallback",
                source_name=self.name,
            )
            # Must also propose stay-transition to prevent inherited mixin transitions
            blackboard.propose_transition(
                next_state=state,
                priority=Priority.NORMAL,
                reason_code="autonomous_stay_llm_fallback",
                source_name=self.name,
            )
            return

        # Always propose autonomous_respond action
        blackboard.propose_action(
            action="autonomous_respond",
            priority=Priority.NORMAL,
            combinable=True,
            reason_code=f"autonomous_action_{decision.reasoning[:50]}" if decision.reasoning else "autonomous_action",
            source_name=self.name,
        )

        # Propose transition — ALWAYS propose to win over inherited mixin transitions
        if decision.should_transition and decision.next_state:
            target = decision.next_state
            # Validate target state exists
            if target in all_states or target in ("close", "soft_close", "success"):
                blackboard.propose_transition(
                    next_state=target,
                    priority=Priority.NORMAL,
                    reason_code=f"autonomous_transition_{decision.reasoning[:50]}" if decision.reasoning else "autonomous_transition",
                    source_name=self.name,
                )
                logger.info(
                    "AutonomousDecision: transition proposed",
                    extra={
                        "from_state": state,
                        "to_state": target,
                        "reasoning": decision.reasoning,
                    },
                )
            else:
                logger.warning(
                    "AutonomousDecision: invalid target state %s, staying",
                    target,
                )
                blackboard.propose_transition(
                    next_state=state,
                    priority=Priority.NORMAL,
                    reason_code="autonomous_stay_invalid_target",
                    source_name=self.name,
                )
        else:
            # Stay in current state — MUST propose to win over inherited mixin transitions
            # (TransitionResolverSource would otherwise propose handle_objection for objection intents)
            blackboard.propose_transition(
                next_state=state,
                priority=Priority.NORMAL,
                reason_code="autonomous_stay_in_state",
                source_name=self.name,
            )

    def _build_decision_prompt(
        self,
        state: str,
        phase: str,
        goal: str,
        intent: str,
        user_message: str,
        collected_data: dict,
        available_states: list,
        turn_in_state: int = 0,
        max_turns: int = 6,
    ) -> str:
        """Build the decision prompt for LLM."""
        collected_str = ", ".join(
            f"{k}={v}" for k, v in collected_data.items()
            if v and not k.startswith("_")
        ) or "пока ничего"

        states_str = ", ".join(available_states) if available_states else "нет"

        # Objection-specific decision rules
        objection_rules = ""
        if intent.startswith("objection_"):
            objection_type = intent.replace("objection_", "")
            objection_rules = f"""
ВАЖНО — ВОЗРАЖЕНИЕ: Клиент выразил возражение типа '{objection_type}'.
- should_transition=false — ОСТАВАЙСЯ в текущем этапе для отработки возражения
- Возражение нужно обработать В РАМКАХ текущего этапа, не переходя в другой
- Переходи дальше ТОЛЬКО если возражение полностью снято И цель этапа достигнута
- Если возражение серьёзное (цена, конкурент, доверие) — ВСЕГДА should_transition=false"""

        # Turn progress context (replaces StallGuard soft nudge)
        progress_hint = ""
        if max_turns > 0 and turn_in_state >= max_turns - 2:
            progress_hint = f"""
ПРОГРЕСС: Ход {turn_in_state} из {max_turns} в этом этапе.
- Если прогресс застопорился — рассмотри переход к следующему этапу
- Если есть прогресс (клиент делится информацией, отвечает на вопросы) — можно продолжить"""

        return f"""Ты — контроллер sales-диалога. Реши нужно ли перейти к следующему этапу.

Текущий этап: {phase} (состояние: {state})
Цель этапа: {goal}
Интент клиента: {intent}
Сообщение клиента: "{user_message}"
Собранные данные: {collected_str}

Доступные состояния для перехода: {states_str}
Также доступны: close, soft_close

Правила:
- should_transition=true ТОЛЬКО если цель текущего этапа достигнута или клиент явно хочет двигаться дальше
- next_state = одно из доступных состояний (или close/soft_close)
- Если клиент просит завершить — next_state="close" или "soft_close"
- Если цель ещё не достигнута — should_transition=false, next_state="{state}"
- action всегда "autonomous_respond"
{objection_rules}{progress_hint}
Ответь JSON:"""
