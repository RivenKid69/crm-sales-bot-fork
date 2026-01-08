"""
Dialogue Policy — контекстные оверлеи для выбора action.

Phase 3: Оптимизация SPIN Flow (docs/PLAN_CONTEXT_POLICY.md)

DialoguePolicy добавляет гибкость в поведение бота БЕЗ нарушения
инвариантов state machine. Оверлеи применяются только на
"железобетонных" сигналах:
- has_breakthrough + turns_since_breakthrough
- repeated_objection_types + total_objections
- is_stuck + repeated_question
- most_effective_action / least_effective_action

АНТИ-ПАТТЕРНЫ (запрещены):
- soft_close на основе engagement (noisy signal)
- пропуск SPIN фаз "по momentum"
- hard-branching без стабильных сигналов

Использование:
    from dialogue_policy import DialoguePolicy

    policy = DialoguePolicy()
    override = policy.maybe_override(sm_result, envelope)

    if override:
        action = override["action"]
        reason = override["reason_codes"]
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum

from context_envelope import ContextEnvelope, ReasonCode
from feature_flags import flags


class PolicyDecision(Enum):
    """Тип решения policy."""
    NO_OVERRIDE = "no_override"              # Оставить action state machine
    REPAIR_CLARIFY = "repair_clarify"        # Перейти в режим уточнения
    REPAIR_CHOICES = "repair_choices"        # Предложить варианты
    REPAIR_SUMMARIZE = "repair_summarize"    # Суммировать понимание
    OBJECTION_REFRAME = "objection_reframe"  # Переформулировать ценность
    OBJECTION_ESCALATE = "objection_escalate"  # Эскалация возражения
    BREAKTHROUGH_CTA = "breakthrough_cta"    # Мягкий CTA после прорыва
    CONSERVATIVE = "conservative"             # Консервативный режим


@dataclass
class PolicyOverride:
    """
    Результат policy override.

    Attributes:
        action: Новый action (или None если без изменений)
        next_state: Новый state (или None если сохранить текущий)
        reason_codes: Reason codes объясняющие решение
        decision: Тип решения
        signals_used: Сигналы на которых основано решение
        expected_effect: Ожидаемый эффект
    """
    action: Optional[str] = None
    next_state: Optional[str] = None
    reason_codes: List[str] = field(default_factory=list)
    decision: PolicyDecision = PolicyDecision.NO_OVERRIDE
    signals_used: Dict[str, Any] = field(default_factory=dict)
    expected_effect: str = ""

    @property
    def has_override(self) -> bool:
        """Есть ли override."""
        return self.action is not None

    def to_dict(self) -> Dict[str, Any]:
        """Сериализовать в словарь."""
        return {
            "action": self.action,
            "next_state": self.next_state,
            "reason_codes": self.reason_codes,
            "decision": self.decision.value,
            "signals_used": self.signals_used,
            "expected_effect": self.expected_effect,
        }


class DialoguePolicy:
    """
    Контекстные оверлеи для выбора action.

    Принципы:
    1. State machine остаётся source-of-truth
    2. Оверлеи только на стабильных сигналах
    3. Каждое решение объяснимо (reason codes)
    4. Всё контролируется feature flags

    Оверлеи (консервативные):
    1. Repair mode: stuck/repeated_question → clarify/choices
    2. Repeated objection escalation: → reframe_value
    3. Breakthrough window: → soft CTA
    4. Conservative mode: низкая confidence → уточнение

    Usage:
        policy = DialoguePolicy()
        override = policy.maybe_override(sm_result, envelope)
    """

    # Mapping action для repair mode
    REPAIR_ACTIONS = {
        "stuck": "clarify_one_question",
        "oscillation": "summarize_and_clarify",
        "repeated_question": "answer_with_summary",
    }

    # Mapping action для возражений
    OBJECTION_ACTIONS = {
        "reframe": "reframe_value",
        "escalate": "handle_repeated_objection",
        "empathize": "empathize_and_redirect",
    }

    # States в которых разрешены оверлеи
    OVERLAY_ALLOWED_STATES = {
        "spin_situation",
        "spin_problem",
        "spin_implication",
        "spin_need_payoff",
        "presentation",
        "handle_objection",
    }

    # States которые нельзя менять через policy
    PROTECTED_STATES = {
        "greeting",
        "close",
        "success",
        "soft_close",
    }

    def __init__(self, shadow_mode: bool = False):
        """
        Args:
            shadow_mode: Если True, только логируем решения без применения
        """
        self.shadow_mode = shadow_mode
        self._decision_history: List[PolicyOverride] = []

    def maybe_override(
        self,
        sm_result: Dict[str, Any],
        envelope: ContextEnvelope,
    ) -> Optional[PolicyOverride]:
        """
        Проверить нужен ли override action.

        Args:
            sm_result: Результат state machine
            envelope: ContextEnvelope с полным контекстом

        Returns:
            PolicyOverride если нужен override, иначе None
        """
        # Проверяем feature flag
        if not flags.is_enabled("context_policy_overlays"):
            return None

        # Проверяем разрешён ли оверлей для текущего состояния
        current_state = sm_result.get("next_state", envelope.state)
        if current_state in self.PROTECTED_STATES:
            return None

        if current_state not in self.OVERLAY_ALLOWED_STATES:
            return None

        # Получаем контекст для policy
        policy_context = envelope.for_policy()

        # Проверяем оверлеи в порядке приоритета
        override = None

        # 1. Guard intervention имеет высший приоритет
        if envelope.guard_intervention:
            override = self._handle_guard_intervention(envelope, sm_result)

        # 2. Repair mode (stuck, oscillation, repeated question)
        if not override and envelope.has_reason(ReasonCode.POLICY_REPAIR_MODE):
            override = self._apply_repair_overlay(envelope, sm_result)

        # 3. Repeated objection escalation
        if not override and envelope.repeated_objection_types:
            override = self._apply_objection_overlay(envelope, sm_result)

        # 4. Breakthrough window CTA
        if not override and envelope.has_reason(ReasonCode.BREAKTHROUGH_CTA):
            override = self._apply_breakthrough_overlay(envelope, sm_result)

        # 5. Conservative mode (низкая confidence)
        if not override and envelope.has_reason(ReasonCode.POLICY_CONSERVATIVE):
            override = self._apply_conservative_overlay(envelope, sm_result)

        # Записываем в историю
        if override:
            self._decision_history.append(override)

            # Shadow mode: возвращаем None но логируем
            if self.shadow_mode:
                from logger import logger
                logger.info(
                    "Policy shadow decision",
                    decision=override.decision.value,
                    action=override.action,
                    reason_codes=override.reason_codes,
                )
                return None

        return override

    def _handle_guard_intervention(
        self,
        envelope: ContextEnvelope,
        sm_result: Dict[str, Any]
    ) -> Optional[PolicyOverride]:
        """Обработать интервенцию guard."""
        # Guard уже обрабатывается в bot.py, здесь только логируем
        return PolicyOverride(
            action=None,  # Не меняем action, guard сам обработает
            reason_codes=[ReasonCode.GUARD_INTERVENTION.value],
            decision=PolicyDecision.NO_OVERRIDE,
            signals_used={"guard_intervention": envelope.guard_intervention},
            expected_effect="Guard handles intervention",
        )

    def _apply_repair_overlay(
        self,
        envelope: ContextEnvelope,
        sm_result: Dict[str, Any]
    ) -> Optional[PolicyOverride]:
        """
        Применить оверлей для repair mode.

        Триггеры:
        - is_stuck: клиент застрял
        - has_oscillation: клиент колеблется
        - repeated_question: повторный вопрос

        Actions:
        - clarify_one_question: один конкретный вопрос
        - summarize_and_clarify: суммировать + уточнить
        - answer_with_summary: ответить + краткое резюме
        """
        signals = {}
        action = None
        decision = PolicyDecision.NO_OVERRIDE

        if envelope.is_stuck:
            signals["is_stuck"] = True
            signals["unclear_count"] = envelope.unclear_count
            action = self.REPAIR_ACTIONS["stuck"]
            decision = PolicyDecision.REPAIR_CLARIFY

        elif envelope.has_oscillation:
            signals["has_oscillation"] = True
            action = self.REPAIR_ACTIONS["oscillation"]
            decision = PolicyDecision.REPAIR_SUMMARIZE

        elif envelope.repeated_question:
            signals["repeated_question"] = envelope.repeated_question
            action = self.REPAIR_ACTIONS["repeated_question"]
            decision = PolicyDecision.REPAIR_CLARIFY

        if action:
            return PolicyOverride(
                action=action,
                next_state=None,  # Сохраняем текущий state
                reason_codes=[ReasonCode.POLICY_REPAIR_MODE.value],
                decision=decision,
                signals_used=signals,
                expected_effect="Clarify understanding and recover dialogue",
            )

        return None

    def _apply_objection_overlay(
        self,
        envelope: ContextEnvelope,
        sm_result: Dict[str, Any]
    ) -> Optional[PolicyOverride]:
        """
        Применить оверлей для повторных возражений.

        Триггеры:
        - repeated_objection_types: типы повторных возражений
        - total_objections >= 3: много возражений

        Actions:
        - reframe_value: переформулировать ценность
        - handle_repeated_objection: эскалация тактики
        """
        signals = {
            "repeated_objection_types": envelope.repeated_objection_types,
            "total_objections": envelope.total_objections,
        }

        # Эскалация при >= 3 возражениях
        if envelope.total_objections >= 3:
            return PolicyOverride(
                action=self.OBJECTION_ACTIONS["escalate"],
                next_state=None,
                reason_codes=[
                    ReasonCode.OBJECTION_ESCALATE.value,
                    ReasonCode.OBJECTION_REPEAT.value,
                ],
                decision=PolicyDecision.OBJECTION_ESCALATE,
                signals_used=signals,
                expected_effect="Escalate objection handling, change approach",
            )

        # Reframe при повторных возражениях
        if envelope.repeated_objection_types:
            # Проверяем least_effective_action чтобы не повторять
            signals["least_effective_action"] = envelope.least_effective_action

            return PolicyOverride(
                action=self.OBJECTION_ACTIONS["reframe"],
                next_state=None,
                reason_codes=[ReasonCode.OBJECTION_REPEAT.value],
                decision=PolicyDecision.OBJECTION_REFRAME,
                signals_used=signals,
                expected_effect="Reframe value proposition, avoid repeating failed approach",
            )

        return None

    def _apply_breakthrough_overlay(
        self,
        envelope: ContextEnvelope,
        sm_result: Dict[str, Any]
    ) -> Optional[PolicyOverride]:
        """
        Применить оверлей для breakthrough window.

        Триггеры:
        - has_breakthrough: был прорыв
        - turns_since_breakthrough in [1, 3]: окно для CTA

        Actions:
        - добавить soft CTA (не меняем action, добавляем directive)
        """
        signals = {
            "has_breakthrough": True,
            "turns_since_breakthrough": envelope.turns_since_breakthrough,
            "breakthrough_action": envelope.breakthrough_action,
        }

        # Не меняем action, но сигнализируем о CTA
        # Реальное добавление CTA происходит через ResponseDirectives
        return PolicyOverride(
            action=None,  # Не меняем action
            next_state=None,
            reason_codes=[
                ReasonCode.BREAKTHROUGH_CTA.value,
                ReasonCode.POLICY_CTA_SOFT.value,
            ],
            decision=PolicyDecision.BREAKTHROUGH_CTA,
            signals_used=signals,
            expected_effect="Add soft CTA, capitalize on breakthrough momentum",
        )

    def _apply_conservative_overlay(
        self,
        envelope: ContextEnvelope,
        sm_result: Dict[str, Any]
    ) -> Optional[PolicyOverride]:
        """
        Применить консервативный оверлей.

        Триггеры:
        - confidence_trend == "decreasing"
        - momentum_direction == "negative"

        Actions:
        - Более осторожные действия (уточнение вместо прогресса)
        """
        signals = {
            "confidence_trend": envelope.confidence_trend,
            "momentum_direction": envelope.momentum_direction,
        }

        # Только если уже есть action который можно заменить на более консервативный
        current_action = sm_result.get("action", "")

        # Список actions которые можно сделать консервативнее
        aggressive_actions = {
            "transition_to_presentation",
            "transition_to_close",
            "ask_for_demo",
            "ask_for_contact",
        }

        if current_action in aggressive_actions:
            return PolicyOverride(
                action="continue_current_goal",  # Остаёмся на текущем этапе
                next_state=None,
                reason_codes=[ReasonCode.POLICY_CONSERVATIVE.value],
                decision=PolicyDecision.CONSERVATIVE,
                signals_used=signals,
                expected_effect="Stay in current phase, avoid premature advancement",
            )

        return None

    def get_decision_history(self) -> List[Dict[str, Any]]:
        """Получить историю решений."""
        return [d.to_dict() for d in self._decision_history]

    def get_override_rate(self) -> float:
        """
        Получить процент оверлеев.

        Returns:
            Доля решений с override (0.0 - 1.0)
        """
        if not self._decision_history:
            return 0.0

        overrides = sum(1 for d in self._decision_history if d.has_override)
        return overrides / len(self._decision_history)

    def get_decision_distribution(self) -> Dict[str, int]:
        """Получить распределение типов решений."""
        distribution: Dict[str, int] = {}
        for d in self._decision_history:
            key = d.decision.value
            distribution[key] = distribution.get(key, 0) + 1
        return distribution

    def reset(self) -> None:
        """Сбросить историю."""
        self._decision_history.clear()


class ContextPolicyMetrics:
    """
    Метрики для context policy.

    Отслеживает:
    - action_override_rate: доля оверлеев
    - reason_code_distribution: распределение по reason codes
    - shadow_mode_stats: статистика shadow mode
    """

    def __init__(self):
        self.reset()

    def reset(self) -> None:
        """Сбросить метрики."""
        self.total_decisions: int = 0
        self.override_count: int = 0
        self.reason_code_counts: Dict[str, int] = {}
        self.decision_type_counts: Dict[str, int] = {}
        self.shadow_decisions: int = 0

    def record_decision(self, override: PolicyOverride, shadow: bool = False) -> None:
        """
        Записать решение policy.

        Args:
            override: PolicyOverride
            shadow: True если shadow mode
        """
        self.total_decisions += 1

        if shadow:
            self.shadow_decisions += 1

        if override.has_override:
            self.override_count += 1

        # Reason codes
        for code in override.reason_codes:
            self.reason_code_counts[code] = \
                self.reason_code_counts.get(code, 0) + 1

        # Decision type
        decision_type = override.decision.value
        self.decision_type_counts[decision_type] = \
            self.decision_type_counts.get(decision_type, 0) + 1

    def get_override_rate(self) -> float:
        """Получить долю оверлеев."""
        if self.total_decisions == 0:
            return 0.0
        return self.override_count / self.total_decisions

    def get_summary(self) -> Dict[str, Any]:
        """Получить сводку метрик."""
        return {
            "total_decisions": self.total_decisions,
            "override_count": self.override_count,
            "override_rate": self.get_override_rate(),
            "shadow_decisions": self.shadow_decisions,
            "reason_code_distribution": self.reason_code_counts,
            "decision_type_distribution": self.decision_type_counts,
        }
