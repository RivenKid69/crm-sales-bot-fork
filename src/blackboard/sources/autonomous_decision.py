# src/blackboard/sources/autonomous_decision.py

"""
AutonomousDecisionSource — LLM-driven state transition for autonomous flow.

Flow-gated: only fires when flow_name == "autonomous".
Calls LLM generate_structured() with Pydantic schema to decide:
- Whether to transition to the next sales phase
- Which action to take (always "autonomous_respond")

Safety layers:
1. Decision history — informs LLM about its previous decisions (soft signal)
2. Deterministic terminal gate — blocks premature terminal transition without required data

Priority: NORMAL (42 in registry order).
Safety sources (GoBackGuard, ConversationGuard, ObjectionGuard, PriceQuestion,
StallGuard) all fire at CRITICAL/HIGH and override this source.
"""

from dataclasses import dataclass, field
from typing import Optional, Any, Dict, List, TYPE_CHECKING
import logging
import re
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

    Safety: LLM remains in control for in-stage progression decisions.
    Deterministic guards (terminal gate, StallGuard, ConversationGuard, etc.)
    still provide hard safety limits around that decision.
    """

    def __init__(self, llm: Any = None, name: str = "AutonomousDecisionSource"):
        super().__init__(name)
        self._llm = llm
        self._decision_history: List[AutonomousDecisionRecord] = []

    @staticmethod
    def _is_non_empty(value: Any) -> bool:
        if value is None:
            return False
        if isinstance(value, str):
            return bool(value.strip())
        if isinstance(value, (list, dict, tuple, set)):
            return len(value) > 0
        return True

    @staticmethod
    def _looks_like_phone(value: Any) -> bool:
        if not isinstance(value, str):
            return False
        digits = "".join(ch for ch in value if ch.isdigit())
        return len(digits) >= 10

    @staticmethod
    def _message_has_phone(value: str) -> bool:
        msg = str(value or "")
        return bool(re.search(r"\+?\d[\d\s\-()]{8,}\d", msg))

    @staticmethod
    def _message_has_iin(value: str) -> bool:
        msg = str(value or "")
        return bool(re.search(r"\b\d{12}\b", msg))

    def _message_has_contact_info(self, value: str) -> bool:
        msg = str(value or "")
        has_email = bool(re.search(r"[\w\.-]+@[\w\.-]+\.\w+", msg))
        return has_email or self._message_has_phone(msg)

    def _has_required_field(self, collected_data: Dict[str, Any], field: str) -> bool:
        """
        Terminal-gate field presence with pragmatic aliases.

        contact_info can be satisfied by kaspi_phone/phone/email.
        kaspi_phone can be satisfied by phone-like contact_info/phone.
        """
        if self._is_non_empty(collected_data.get(field)):
            return True

        if field == "contact_info":
            for alias in ("kaspi_phone", "phone", "email"):
                if self._is_non_empty(collected_data.get(alias)):
                    return True
            return False

        if field == "kaspi_phone":
            phone_alias = collected_data.get("phone")
            if self._is_non_empty(phone_alias) and self._looks_like_phone(str(phone_alias)):
                return True
            contact = collected_data.get("contact_info")
            if self._is_non_empty(contact) and self._looks_like_phone(str(contact)):
                return True
            return False

        return False

    @staticmethod
    def _looks_like_ready_to_buy_message(user_message: str) -> bool:
        """Detect explicit purchase readiness in free-form user message."""
        text = str(user_message or "").lower()
        buy_markers = (
            "готов покупать",
            "готов купить",
            "хочу купить",
            "выставляйте счет",
            "выставьте счет",
            "выставь счет",
            "хочу счет",
            "счёт выставляйте",
            "оплачу",
            "как оплатить",
            "оформим",
            "оформляйте",
        )
        return any(marker in text for marker in buy_markers)

    @staticmethod
    def _has_hard_contact_refusal(user_message: str) -> bool:
        """Detect explicit refusal to share contact details."""
        text = str(user_message or "").lower()
        refusal_markers = (
            "контакты не дам",
            "контакт не дам",
            "не дам контакт",
            "не проси мои контакты",
            "без контакта",
            "без контактов",
        )
        return any(marker in text for marker in refusal_markers)

    @staticmethod
    def _has_recent_payment_intent(envelope: Any, current_intent: str, user_message: str) -> bool:
        """
        Detect payment/invoice context from current turn + recent intent history.

        Used to prevent premature auto-finish into video_call_scheduled when
        client clearly asked to buy/invoice and payment path is still incomplete.
        """
        payment_intents = {"ready_to_buy", "request_invoice", "request_contract", "payment_confirmation", "agreement"}
        if current_intent in payment_intents:
            return True

        intents = list(getattr(envelope, "intent_history", []) or []) if envelope else []
        if any(i in payment_intents for i in intents[-3:]):
            return True

        return AutonomousDecisionSource._looks_like_ready_to_buy_message(user_message)

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

        LLM-driven path only: no counter-based hard override.
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

        # Deterministic terminal completion in autonomous_closing only:
        # if required terminal data is already present (including in current user turn),
        # finalize transition without waiting for another LLM decision cycle.
        if state == "autonomous_closing" and terminal_names:
            has_contact = (
                self._has_required_field(collected_data, "contact_info")
                or self._message_has_contact_info(user_message)
            )
            has_kaspi_phone = (
                self._has_required_field(collected_data, "kaspi_phone")
                or self._message_has_phone(user_message)
            )
            has_iin = (
                self._has_required_field(collected_data, "iin")
                or self._message_has_iin(user_message)
            )
            payment_intent_active = self._has_recent_payment_intent(
                envelope=envelope,
                current_intent=intent,
                user_message=user_message,
            )
            if "payment_ready" in terminal_names and has_kaspi_phone and has_iin:
                blackboard.propose_action(
                    action="autonomous_respond",
                    priority=Priority.HIGH,
                    priority_rank=0,
                    reason_code="autonomous_terminal_payment_ready",
                    source_name=self.name,
                )
                blackboard.propose_transition(
                    next_state="payment_ready",
                    priority=Priority.HIGH,
                    priority_rank=0,
                    reason_code="autonomous_terminal_payment_ready",
                    source_name=self.name,
                )
                self._decision_history.append(
                    AutonomousDecisionRecord(
                        turn_in_state=turn_in_state,
                        intent=intent,
                        state=state,
                        should_transition=True,
                        next_state="payment_ready",
                        reasoning="terminal_data_ready_payment",
                    )
                )
                return
            if (
                "video_call_scheduled" in terminal_names
                and has_contact
                and not (payment_intent_active and not has_iin)
            ):
                blackboard.propose_action(
                    action="autonomous_respond",
                    priority=Priority.HIGH,
                    priority_rank=0,
                    reason_code="autonomous_terminal_video_call",
                    source_name=self.name,
                )
                blackboard.propose_transition(
                    next_state="video_call_scheduled",
                    priority=Priority.HIGH,
                    priority_rank=0,
                    reason_code="autonomous_terminal_video_call",
                    source_name=self.name,
                )
                self._decision_history.append(
                    AutonomousDecisionRecord(
                        turn_in_state=turn_in_state,
                        intent=intent,
                        state=state,
                        should_transition=True,
                        next_state="video_call_scheduled",
                        reasoning="terminal_data_ready_video_call",
                    )
                )
                return

        # Build prompt for LLM decision with context signals from prior sources.
        context_signals = blackboard.get_context_signals()
        total_objections = int(getattr(envelope, "total_objections", 0) or 0)
        repeated_objection_types = list(getattr(envelope, "repeated_objection_types", []) or [])
        explicit_ready_to_buy = self._looks_like_ready_to_buy_message(user_message)
        hard_contact_refusal = self._has_hard_contact_refusal(user_message)
        payment_intent_active = self._has_recent_payment_intent(
            envelope=envelope,
            current_intent=intent,
            user_message=user_message,
        )

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
            context_signals=context_signals,
            total_objections=total_objections,
            repeated_objection_types=repeated_objection_types,
            explicit_ready_to_buy=explicit_ready_to_buy,
            hard_contact_refusal=hard_contact_refusal,
            payment_intent_active=payment_intent_active,
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
                priority_rank=0,
                reason_code="autonomous_llm_fallback",
                source_name=self.name,
            )
            # Must also propose stay-transition to prevent inherited mixin transitions
            blackboard.propose_transition(
                next_state=state,
                priority=Priority.NORMAL,
                priority_rank=0,
                reason_code="autonomous_stay_llm_fallback",
                source_name=self.name,
            )
            return

        # Always propose autonomous_respond action
        blackboard.propose_action(
            action="autonomous_respond",
            priority=Priority.NORMAL,
            priority_rank=0,
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

            # If LLM already decided to move into autonomous_closing and client
            # provided terminal data in the same turn, finalize directly.
            if target == "autonomous_closing" and intent == "contact_provided":
                has_contact = (
                    self._has_required_field(collected_data, "contact_info")
                    or self._message_has_contact_info(user_message)
                )
                has_kaspi_phone = (
                    self._has_required_field(collected_data, "kaspi_phone")
                    or self._message_has_phone(user_message)
                )
                has_iin = (
                    self._has_required_field(collected_data, "iin")
                    or self._message_has_iin(user_message)
                )
                payment_intent_active = self._has_recent_payment_intent(
                    envelope=envelope,
                    current_intent=intent,
                    user_message=user_message,
                )
                if "payment_ready" in all_states and has_kaspi_phone and has_iin:
                    target = "payment_ready"
                elif (
                    "video_call_scheduled" in all_states
                    and has_contact
                    and not (payment_intent_active and not has_iin)
                ):
                    target = "video_call_scheduled"

            # Hard gate: block premature terminal transition if required data is missing
            # LLM may ignore prompt instructions; this ensures data integrity regardless
            if target in terminal_names and terminal_requirements.get(target):
                reqs = terminal_requirements[target]
                missing_for_terminal = [
                    f for f in reqs if not self._has_required_field(collected_data, f)
                ]
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
                    priority_rank=0,
                    reason_code="autonomous_stay_terminal_gate",
                    source_name=self.name,
                )
            else:
                # Validate target state exists
                # payment_ready/video_call_scheduled уже в available_states через terminal_names injection
                # close и success убраны — LLM не должен прыгать туда напрямую из autonomous стейтов
                terminal_targets = {
                    s for s in ("payment_ready", "video_call_scheduled") if s in all_states
                }
                valid_targets = set(available_states) | terminal_targets | {"soft_close"}
                if target in valid_targets:
                    blackboard.propose_transition(
                        next_state=target,
                        priority=Priority.NORMAL,
                        priority_rank=0,
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
                        priority_rank=0,
                        reason_code="autonomous_stay_invalid_target",
                        source_name=self.name,
                    )
        else:
            # Stay in current state — MUST propose to win over inherited mixin transitions
            # (TransitionResolverSource would otherwise propose handle_objection for objection intents)
            blackboard.propose_transition(
                next_state=state,
                priority=Priority.NORMAL,
                priority_rank=0,
                reason_code="autonomous_stay_in_state",
                source_name=self.name,
            )

        # Record decision in history AFTER gate resolution so stay_streak counts actual outcomes.
        # If terminal_gate_blocked=True, LLM wanted to transition but code forced stay.
        # Record as stay to keep history aligned with actual transition outcome.
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
        context_signals: list = None,
        total_objections: int = 0,
        repeated_objection_types: list = None,
        explicit_ready_to_buy: bool = False,
        hard_contact_refusal: bool = False,
        payment_intent_active: bool = False,
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

        # Decision history — helps LLM avoid repetitive stay decisions
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

        # Context signals from prior sources (price/fact) + objection envelope context.
        signal_lines: List[str] = []
        for signal in context_signals or []:
            if signal.get("price_intent_detected"):
                category = signal.get("category", "price")
                signal_lines.append(
                    f"- Клиент спрашивает о цене ({category}). Реши: ответить в текущем этапе или переходить дальше."
                )
            fact_requested = signal.get("fact_requested")
            if fact_requested:
                signal_lines.append(
                    f"- Клиент просит факты о продукте ({fact_requested}). Реши: ответить в текущем этапе или переходить дальше."
                )

        if intent in {"demo_request", "callback_request"}:
            signal_lines.append(
                f"- ⚡ Клиент просит демо/звонок ({intent}). "
                "Это сигнал готовности — сильный сигнал для перехода в autonomous_closing. "
                "should_transition=true, next_state=autonomous_closing."
            )

        if intent == "contact_provided" and state != "autonomous_closing":
            signal_lines.append(
                "- ⚡ Клиент уже оставил контакт. "
                "Это сильный сигнал переходить в autonomous_closing, чтобы корректно завершить следующий шаг."
            )

        if intent in {"agreement", "ready_to_buy", "request_invoice", "request_contract"}:
            if self._looks_like_ready_to_buy_message(user_message):
                signal_lines.append(
                    "- ⚡ Клиент явно готов к покупке/счёту. "
                    "Считай это сильным сигналом: should_transition=true, next_state=autonomous_closing."
                )
            elif intent in {"ready_to_buy", "request_invoice", "request_contract"}:
                signal_lines.append(
                    f"- ⚡ Интент {intent} означает готовность к оформлению. "
                    "Рассмотри переход в autonomous_closing без лишней квалификации."
                )

        if intent == "agreement":
            signal_lines.append(
                "- ⚡ Клиент выражает согласие/готовность. "
                "Рассмотри переход в autonomous_closing для сбора контакта."
            )

        if hard_contact_refusal:
            signal_lines.append(
                "- ⛔ Клиент явно отказался давать контакты. "
                "Не форсируй переход в autonomous_closing только ради сбора контактов."
            )

        if payment_intent_active and state == "autonomous_closing":
            signal_lines.append(
                "- ⚡ Активен контекст покупки/счёта. "
                "Если для payment_ready не хватает ИИН или Kaspi-телефона — оставайся в autonomous_closing и запроси недостающее."
            )

        if intent.startswith("objection_"):
            objection_type = intent.replace("objection_", "")
            repeated = ", ".join(repeated_objection_types or [])
            repeated_part = f"; повторяющиеся типы: {repeated}" if repeated else ""
            signal_lines.append(
                f"- Клиент возражает ({objection_type}), это возражение №{max(total_objections, 1)}{repeated_part}. "
                "Реши: отработать возражение сейчас или предложить альтернативу."
            )

        explicit_ready_rule = ""
        if explicit_ready_to_buy and state != "autonomous_closing":
            explicit_ready_rule = (
                "\n- КРИТИЧНО: клиент явно готов покупать прямо сейчас. "
                "Выбери should_transition=true и next_state=\"autonomous_closing\"."
            )

        context_signal_block = ""
        if signal_lines:
            context_signal_block = "\nКОНТЕКСТНЫЕ СИГНАЛЫ:\n" + "\n".join(signal_lines)

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
- Собирай только данные, которые реально нужны для прогресса этапа
- Если ценность уже понятна и клиент вовлечён — переходи дальше без лишних уточнений
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
                        missing_t = [f for f in reqs if not self._has_required_field(collected_data, f)]
                        present_t = [f for f in reqs if self._has_required_field(collected_data, f)]
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
                        missing_t = [f for f in reqs if not self._has_required_field(collected_data, f)]
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
{context_signal_block}
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
{explicit_ready_rule}
{objection_rules}{progress_hint}
Ответь JSON:"""
