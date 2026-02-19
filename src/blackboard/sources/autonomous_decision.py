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
from src.yaml_config.constants import OBJECTION_INTENTS

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

    @staticmethod
    def _get_phase_order(all_states: dict) -> dict:
        """Build {state_name: order_index} from next_phase_state chain in YAML."""
        start = None
        for state_name, cfg in all_states.items():
            if not state_name.startswith("autonomous_"):
                continue
            prev = cfg.get("parameters", {}).get("prev_phase_state", "")
            if not prev.startswith("autonomous_"):
                start = state_name
                break

        if not start:
            return {
                state_name: idx
                for idx, state_name in enumerate(
                    sorted(s for s in all_states if s.startswith("autonomous_"))
                )
            }

        result = {}
        current = start
        idx = 0
        while current and current not in result:
            result[current] = idx
            nxt = all_states.get(current, {}).get("parameters", {}).get(
                "next_phase_state", ""
            )
            current = nxt if nxt.startswith("autonomous_") else None
            idx += 1

        # Fallback: autonomous states not in chain get max_idx+1 (reachable forward)
        max_idx = max(result.values()) if result else -1
        for state_name in all_states:
            if state_name.startswith("autonomous_") and state_name not in result:
                max_idx += 1
                result[state_name] = max_idx

        return result

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
        phase_order = self._get_phase_order(all_states)
        current_idx = phase_order.get(state, -1)
        prev_phase = state_config.get("parameters", {}).get("prev_phase_state", "")

        # Persistent visited states from ContextWindow, survives source re-instantiation
        envelope = ctx.context_envelope if hasattr(ctx, 'context_envelope') else None
        visited_states = set(getattr(envelope, "state_history", [])) if envelope else set()
        available_states = [
            s
            for s in all_states
            if s.startswith("autonomous_")
            and s != state
            and (
                phase_order.get(s, -1) > current_idx
                or (s == prev_phase and s not in visited_states)
            )
        ]

        # Inject terminal states from YAML config into available_states (data-driven)
        # Goals are already in all_states from _base/states.yaml — no need to modify all_states
        terminal_names = state_config.get("terminal_states", [])
        if terminal_names:
            available_states = available_states + [n for n in terminal_names if n not in available_states]

        if logger.isEnabledFor(logging.DEBUG):
            blocked = [
                s
                for s in all_states
                if s.startswith("autonomous_")
                and s != state
                and s not in available_states
            ]
            if blocked:
                logger.debug(
                    "AutonomousDecision: blocked back-transitions from %s: %s (visited: %s)",
                    state,
                    blocked,
                    visited_states,
                )

        # Get turn-in-state count from context envelope
        turn_in_state = getattr(envelope, 'consecutive_same_state', 0) if envelope else 0
        max_turns = state_config.get("max_turns_in_state", 6)

        # Read optional_data and terminal requirements from state config
        optional_data = state_config.get("optional_data", [])
        terminal_requirements = state_config.get("terminal_state_requirements", {})

        # =====================================================================
        # Hard override: force transition after consecutive stay decisions
        # Threshold = phase_exhaust_threshold (options shown 1 turn before)
        # =====================================================================
        stay_override_threshold = state_config.get("phase_exhaust_threshold", 3)

        # Count CONSECUTIVE stays (break on first transition or state change)
        stay_streak = 0
        stay_streak_records: List[AutonomousDecisionRecord] = []
        for d in reversed(self._decision_history):
            if d.state != state:
                break
            if not d.should_transition:
                stay_streak += 1
                stay_streak_records.append(d)        # <-- collect for objection detection
            else:
                break  # Streak broken by transition decision

        if stay_streak >= stay_override_threshold:
            resolved_params = state_config.get("_resolved_params", {})

            # Detect objection-driven streak: if ALL consecutive stays were caused by
            # client objections (client disinterested), route to soft_close instead of
            # forcing next phase (which would be wrong — client won't engage there either).
            _objection_set = set(OBJECTION_INTENTS)
            all_objection_driven = bool(stay_streak_records) and all(
                d.intent in _objection_set for d in stay_streak_records
            )

            if all_objection_driven:
                target = "soft_close"
                override_type = "objection_driven"
            elif terminal_names:
                # Apply terminal gate: pick first terminal (easiest first = reversed order)
                # where all required data is already collected. If none qualify → soft_close.
                target = None
                for t in reversed(terminal_names):
                    reqs = terminal_requirements.get(t, [])
                    missing = [f for f in reqs if not collected_data.get(f)]
                    if not missing:
                        target = t
                        break
                if target:
                    override_type = "phase_exhausted_terminal"
                else:
                    # No terminal has required data — graceful exit
                    target = "soft_close"
                    override_type = "phase_exhausted_no_data"
                    logger.info(
                        "AutonomousDecision: HARD OVERRIDE — no terminal state has required data "
                        "(missing for %s), falling back to soft_close",
                        {t: [f for f in terminal_requirements.get(t, []) if not collected_data.get(f)]
                         for t in terminal_names},
                    )
            else:
                target = (
                    resolved_params.get("next_phase_state")
                    or state_config.get("max_turns_fallback")  # safety fallback
                    or "soft_close"
                )
                override_type = "phase_exhausted"

            if target not in all_states and target not in ("close", "soft_close", "success"):
                target = "soft_close"

            logger.info(
                "AutonomousDecision: HARD OVERRIDE — %d consecutive stays in %s, "
                "forcing transition to %s (type=%s, LLM bypassed)",
                stay_streak, state, target, override_type,
            )

            # Record the forced decision
            self._decision_history.append(AutonomousDecisionRecord(
                turn_in_state=turn_in_state,
                intent=intent,
                state=state,
                should_transition=True,
                next_state=target,
                reasoning=f"hard_override_{override_type}_{stay_streak}_stays",
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
            terminal_names=terminal_names,
            terminal_requirements=terminal_requirements,
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
        terminal_gate_blocked = False
        if decision.should_transition and decision.next_state:
            target = decision.next_state
            # Intercept: LLM выбрал close из autonomous стейта — redirect
            if target == "close" and state.startswith("autonomous_"):
                if "autonomous_closing" in available_states:
                    logger.info(
                        "AutonomousDecision: redirecting close → autonomous_closing from %s", state
                    )
                    target = "autonomous_closing"
                else:
                    target = "soft_close"

            # Hard gate: block premature terminal transition if required data is missing
            # LLM may ignore prompt instructions; this ensures data integrity regardless
            if target in terminal_names and terminal_requirements.get(target):
                reqs = terminal_requirements[target]
                missing_for_terminal = [f for f in reqs if not collected_data.get(f)]
                if missing_for_terminal:
                    logger.warning(
                        "AutonomousDecision: terminal gate — blocked %s → %s "
                        "(missing required fields: %s), forcing stay",
                        state, target, missing_for_terminal,
                    )
                    terminal_gate_blocked = True

            if terminal_gate_blocked:
                blackboard.propose_transition(
                    next_state=state,
                    priority=Priority.NORMAL,
                    reason_code="autonomous_stay_terminal_gate",
                    source_name=self.name,
                )
            else:
                # Validate target state exists
                # payment_ready/video_call_scheduled уже в available_states через terminal_names injection
                # close и success убраны — LLM не должен прыгать туда напрямую из autonomous стейтов
                valid_targets = set(available_states) | {"soft_close"}
                if target in valid_targets:
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

        # Record decision in history AFTER gate resolution so stay_streak counts actual outcomes.
        # If terminal_gate_blocked=True, LLM wanted to transition but code forced stay —
        # record as should_transition=False so the streak counter increments correctly
        # and hard override eventually fires instead of looping forever.
        actual_transitioned = decision.should_transition and not terminal_gate_blocked
        self._decision_history.append(AutonomousDecisionRecord(
            turn_in_state=turn_in_state,
            intent=intent,
            state=state,
            should_transition=actual_transitioned,
            next_state=decision.next_state if actual_transitioned else state,
            reasoning=(
                f"gate_blocked:{decision.reasoning[:80]}"
                if terminal_gate_blocked
                else decision.reasoning[:100]
            ),
        ))

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
        terminal_names: list = None,
        terminal_requirements: dict = None,
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

        # Compute missing optional data (only non-terminal-requirement fields)
        terminal_req_fields: set = set()
        if terminal_requirements:
            for fields in terminal_requirements.values():
                terminal_req_fields.update(fields)
        missing_optional = ""
        if optional_data:
            non_terminal_optional = [f for f in optional_data if f not in terminal_req_fields]
            missing = [f for f in non_terminal_optional if f not in collected_keys]
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

        # Build context-dependent close options for prompt
        terminal_status_block = ""
        if terminal_names:
            # Build per-terminal requirements status so LLM knows exactly what blocks each transition
            if terminal_requirements:
                status_lines = []
                for t in terminal_names:
                    reqs = terminal_requirements.get(t, [])
                    if reqs:
                        missing_t = [f for f in reqs if not collected_data.get(f)]
                        present_t = [f for f in reqs if collected_data.get(f)]
                        if missing_t:
                            status_lines.append(
                                f"  ⛔ {t}: НЕ ГОТОВО — нужно собрать: {', '.join(missing_t)}"
                            )
                        else:
                            status_lines.append(
                                f"  ✅ {t}: ГОТОВО (собраны: {', '.join(present_t)})"
                            )
                    else:
                        status_lines.append(f"  {t}")
                terminal_status_block = (
                    "\nСТАТУС ТЕРМИНАЛЬНЫХ СТЕЙТОВ:\n"
                    + "\n".join(status_lines)
                    + "\n"
                )
                # Build per-terminal missing fields instruction
                missing_instructions = []
                for t in terminal_names:
                    reqs = terminal_requirements.get(t, [])
                    if reqs:
                        missing_t = [f for f in reqs if not collected_data.get(f)]
                        if missing_t:
                            missing_instructions.append(
                                f"   → {t}: ПРЯМО СПРОСИ клиента про {', '.join(missing_t)}"
                            )
                ask_hint = ("\n".join(missing_instructions) + "\n") if missing_instructions else ""
                gate_rule = (
                    "⛔ СТРОГОЕ ПРАВИЛО: Переход в терминальный стейт ТОЛЬКО если статус ✅ ГОТОВО.\n"
                    "   При ⛔ НЕ ГОТОВО — should_transition=false, next_state=текущий стейт.\n"
                    f"{ask_hint}"
                )
            else:
                gate_rule = ""

            # autonomous_closing: LLM должен выбирать terminal states, а не close/success
            close_section = "  - soft_close: Мягкое завершение (клиент твёрдо отказывается)"
            close_rules = (
                gate_rule
                + f"- next_state = одно из [{', '.join(terminal_names)}] или soft_close при отказе\n"
                f"- ⛔ ЗАПРЕЩЕНО: close, success"
            )
        elif state.startswith("autonomous_"):
            close_section = "  - soft_close: Мягкое завершение (клиент твёрдо отказывается)"
            close_rules = (
                "- Если клиент твёрдо отказывается — next_state=\"soft_close\"\n"
                "- Для закрытия сделки — переходи в autonomous_closing (если доступен выше)"
            )
        else:
            close_section = (
                "  - close: Завершить диалог (клиент согласен или назначен следующий шаг)\n"
                "  - soft_close: Мягкое завершение (клиент не готов, оставить дверь открытой)"
            )
            close_rules = (
                "- next_state = одно из доступных состояний (или close/soft_close)\n"
                "- Если клиент просит завершить — next_state=\"close\" или \"soft_close\""
            )

        return f"""Ты — контроллер sales-диалога. Реши нужно ли перейти к следующему этапу.

Текущий этап: {phase} (состояние: {state})
Цель этапа: {goal}
Интент клиента: {intent}
Сообщение клиента: "{user_message}"
Собранные данные: {collected_str}{missing_optional}
{terminal_status_block}{decision_summary}
Доступные состояния для перехода:
{states_str}
{close_section}

Правила:
- should_transition=true ТОЛЬКО если цель текущего этапа достигнута или клиент явно хочет двигаться дальше
{close_rules}
- Если цель ещё не достигнута — should_transition=false, next_state="{state}"
- action всегда "autonomous_respond"{data_collection_rule}
{objection_rules}{progress_hint}
Ответь JSON:"""
