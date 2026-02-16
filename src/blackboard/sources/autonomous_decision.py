# src/blackboard/sources/autonomous_decision.py

"""
AutonomousDecisionSource — LLM-driven state transition for autonomous flow.

Flow-gated: only fires when flow_name == "autonomous".
Calls LLM generate_structured() with Pydantic schema to decide:
- Whether to transition to the next sales phase
- Which action to take (always "autonomous_respond")

Safety layers:
1. Decision history — informs LLM about its previous decisions (soft signal)
2. Hard override — after N consecutive stay-decisions, forces transition
   with HIGH priority, bypassing LLM entirely (same principle as StallGuard)

Priority: NORMAL (42 in registry order).
Safety sources (GoBackGuard, ConversationGuard, ObjectionGuard, PriceQuestion,
StallGuard) all fire at CRITICAL/HIGH and override this source.
"""

from dataclasses import dataclass, field
from typing import Optional, Any, List, TYPE_CHECKING
import logging
import time

from pydantic import BaseModel

from ..knowledge_source import KnowledgeSource
from ..enums import Priority

if TYPE_CHECKING:
    from ..blackboard import DialogueBlackboard

logger = logging.getLogger(__name__)


@dataclass
class AutonomousDecisionRecord:
    """Immutable record of one autonomous decision."""
    turn_in_state: int
    intent: str
    state: str
    should_transition: bool
    next_state: str
    reasoning: str
    timestamp: float = field(default_factory=time.time)


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

    Safety: Hard override forces transition after N consecutive stay-decisions
    (threshold = phase_exhaust_threshold from state config). This creates:
    - Turn 3: PhaseExhaustedSource shows options (NORMAL)
    - Turn 4: Hard override forces transition (HIGH, LLM bypassed)
    - Turn 5-6: StallGuard soft/hard as ultimate backstop
    """

    def __init__(self, llm: Any = None, name: str = "AutonomousDecisionSource"):
        super().__init__(name)
        self._llm = llm
        self._decision_history: List[AutonomousDecisionRecord] = []

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

        Hard override: if stay-streak >= phase_exhaust_threshold, bypass LLM
        and force transition with HIGH priority.
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

        # Read optional_data from state config for data collection guidance
        optional_data = state_config.get("optional_data", [])

        # =====================================================================
        # Hard override: force transition after consecutive stay decisions
        # Threshold = phase_exhaust_threshold (options shown 1 turn before)
        # =====================================================================
        stay_override_threshold = state_config.get("phase_exhaust_threshold", 3)

        # Count CONSECUTIVE stays (break on first transition or state change)
        stay_streak = 0
        for d in reversed(self._decision_history):
            if d.state != state:
                break
            if not d.should_transition:
                stay_streak += 1
            else:
                break  # Streak broken by transition decision

        if stay_streak >= stay_override_threshold:
            # Determine target: next_phase_state from resolved params, or soft_close
            resolved_params = state_config.get("_resolved_params", {})
            target = (
                resolved_params.get("next_phase_state")
                or state_config.get("max_turns_fallback")  # safety fallback
                or "soft_close"
            )
            if target not in all_states and target not in ("close", "soft_close", "success"):
                target = "soft_close"

            logger.info(
                "AutonomousDecision: HARD OVERRIDE — %d consecutive stays in %s, "
                "forcing transition to %s (LLM bypassed)",
                stay_streak, state, target,
            )

            # Record the forced decision
            self._decision_history.append(AutonomousDecisionRecord(
                turn_in_state=turn_in_state,
                intent=intent,
                state=state,
                should_transition=True,
                next_state=target,
                reasoning=f"hard_override_after_{stay_streak}_stays",
            ))

            # Propose with HIGH priority — same as StallGuard
            blackboard.propose_action(
                action="autonomous_respond",
                priority=Priority.HIGH,
                combinable=True,
                reason_code=f"autonomous_hard_override_{stay_streak}_stays",
                source_name=self.name,
            )
            blackboard.propose_transition(
                next_state=target,
                priority=Priority.HIGH,
                reason_code=f"autonomous_hard_override_{stay_streak}_stays",
                source_name=self.name,
            )
            return  # Skip LLM call entirely

        # =====================================================================
        # Normal path: LLM decides with decision history context
        # =====================================================================

        # Build prompt for LLM decision (with decision history)
        prompt = self._build_decision_prompt(
            state=state,
            phase=current_phase,
            goal=goal,
            intent=intent,
            user_message=user_message,
            collected_data=collected_data,
            available_states=available_states,
            all_states_config=all_states,
            turn_in_state=turn_in_state,
            max_turns=max_turns,
            optional_data=optional_data,
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

        # Record decision in history
        self._decision_history.append(AutonomousDecisionRecord(
            turn_in_state=turn_in_state,
            intent=intent,
            state=state,
            should_transition=decision.should_transition,
            next_state=decision.next_state,
            reasoning=decision.reasoning[:100],
        ))

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
        all_states_config: dict = None,
        turn_in_state: int = 0,
        max_turns: int = 6,
        optional_data: list = None,
    ) -> str:
        """Build the decision prompt for LLM."""
        collected_keys = {
            k for k, v in collected_data.items()
            if v and not k.startswith("_")
        }
        collected_str = ", ".join(
            f"{k}={v}" for k, v in collected_data.items()
            if v and not k.startswith("_")
        ) or "пока ничего"

        # Build available states with goals for informed LLM choice
        all_states_config = all_states_config or {}
        if available_states:
            state_lines = []
            for s in available_states:
                s_cfg = all_states_config.get(s, {})
                s_goal = s_cfg.get("goal", "")
                if s_goal:
                    state_lines.append(f"  - {s}: {s_goal}")
                else:
                    state_lines.append(f"  - {s}")
            states_str = "\n".join(state_lines)
        else:
            states_str = "нет"

        # Compute missing optional data
        missing_optional = ""
        if optional_data:
            missing = [f for f in optional_data if f not in collected_keys]
            if missing:
                missing_optional = f"\nЖелательно собрать: {', '.join(missing)}"

        # Decision history — helps LLM avoid repetition before hard override
        decision_summary = ""
        recent = [d for d in self._decision_history[-5:] if d.state == state]
        if recent:
            stay_count = sum(1 for d in recent if not d.should_transition)
            lines = []
            for d in recent:
                verb = "ПЕРЕШЁЛ" if d.should_transition else "ОСТАЛСЯ"
                lines.append(f"  Ход {d.turn_in_state}: {d.intent} → {verb}")
            warning = ""
            if stay_count >= 2:
                warning = f"\n⚠️ Решение ОСТАТЬСЯ принято {stay_count} раз. Рассмотри переход."
            decision_summary = (
                "\nИСТОРИЯ ТВОИХ РЕШЕНИЙ в этом этапе:\n"
                + "\n".join(lines)
                + warning
            )

        # Objection-specific decision rules (softened — no unconditional hard lock)
        objection_rules = ""
        if intent.startswith("objection_"):
            objection_type = intent.replace("objection_", "")
            objection_rules = f"""
ВОЗРАЖЕНИЕ: Клиент выразил возражение типа '{objection_type}'.
- Отработай возражение в рамках текущего этапа
- Если возражение снято — продолжай к цели этапа
- Если клиент повторяет то же возражение — смени подход или предложи демо/звонок"""

        # Turn progress context (replaces StallGuard soft nudge)
        progress_hint = ""
        if max_turns > 0 and turn_in_state >= max_turns - 2:
            progress_hint = f"""
ПРОГРЕСС: Ход {turn_in_state} из {max_turns} в этом этапе.
- Если прогресс застопорился — рассмотри переход к следующему этапу
- Если есть прогресс (клиент делится информацией, отвечает на вопросы) — можно продолжить"""

        # Data collection guidance (non-objection path)
        data_collection_rule = ""
        if not intent.startswith("objection_"):
            data_collection_rule = """
- Старайся собрать как можно больше данных о клиенте перед переходом
- При возражении клиента — отработай его, не переходи сразу к следующему этапу"""

        return f"""Ты — контроллер sales-диалога. Реши нужно ли перейти к следующему этапу.

Текущий этап: {phase} (состояние: {state})
Цель этапа: {goal}
Интент клиента: {intent}
Сообщение клиента: "{user_message}"
Собранные данные: {collected_str}{missing_optional}
{decision_summary}
Доступные состояния для перехода:
{states_str}
  - close: Завершить диалог (клиент согласен или назначен следующий шаг)
  - soft_close: Мягкое завершение (клиент не готов, оставить дверь открытой)

Правила:
- should_transition=true ТОЛЬКО если цель текущего этапа достигнута или клиент явно хочет двигаться дальше
- next_state = одно из доступных состояний (или close/soft_close)
- Если клиент просит завершить — next_state="close" или "soft_close"
- Если цель ещё не достигнута — should_transition=false, next_state="{state}"
- action всегда "autonomous_respond"{data_collection_rule}
{objection_rules}{progress_hint}
Ответь JSON:"""
