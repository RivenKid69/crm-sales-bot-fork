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

        # Build prompt for LLM decision
        prompt = self._build_decision_prompt(
            state=state,
            phase=current_phase,
            goal=goal,
            intent=intent,
            user_message=user_message,
            collected_data=collected_data,
            available_states=available_states,
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
            return

        # Always propose autonomous_respond action
        blackboard.propose_action(
            action="autonomous_respond",
            priority=Priority.NORMAL,
            combinable=True,
            reason_code=f"autonomous_action_{decision.reasoning[:50]}" if decision.reasoning else "autonomous_action",
            source_name=self.name,
        )

        # Propose transition if LLM decided to move to next phase
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
                    "AutonomousDecision: invalid target state %s, ignoring",
                    target,
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
    ) -> str:
        """Build the decision prompt for LLM."""
        collected_str = ", ".join(
            f"{k}={v}" for k, v in collected_data.items()
            if v and not k.startswith("_")
        ) or "пока ничего"

        states_str = ", ".join(available_states) if available_states else "нет"

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

Ответь JSON:"""
