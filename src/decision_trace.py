"""
Decision Trace — полное логирование всех этапов принятия решений.

Обеспечивает сквозную прозрачность всех решений чат-бота во время симуляции.

Модуль содержит:
- DecisionTrace: главный контейнер для одного turn
- Специализированные trace классы для каждого этапа:
  - ClassificationTrace: классификация интента
  - ToneAnalysisTrace: анализ тона
  - GuardCheckTrace: проверка guard
  - FallbackTrace: fallback обработка
  - LeadScoreTrace: lead scoring
  - ObjectionTrace: обработка возражений
  - StateMachineTrace: переходы состояний
  - PolicyOverrideTrace: policy overlays
  - ResponseTrace: генерация ответа
  - LLMTrace: LLM вызовы
  - TimingTrace: тайминги
  - ContextWindowTrace: контекстное окно
  - PersonalizationTrace: персонализация
  - ClientAgentTrace: клиентский агент (для симулятора)
- DecisionTraceBuilder: builder для создания DecisionTrace
- DecisionStatistics: агрегированная статистика
"""

import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum


class TransitionType(str, Enum):
    """Тип перехода между состояниями."""
    FORWARD = "forward"
    STAY = "stay"
    GOBACK = "goback"
    SKIP = "skip"
    FINAL = "final"


class RuleType(str, Enum):
    """Тип правила."""
    SIMPLE = "simple"
    CONDITIONAL = "conditional"
    CHAIN = "chain"
    FALLBACK = "fallback"


class ResolutionPath(str, Enum):
    """Путь разрешения правила."""
    DIRECT = "direct"
    CONDITION_MATCHED = "condition_matched"
    DEFAULT = "default"
    FALLBACK = "fallback"


# =============================================================================
# Turn Metadata
# =============================================================================

@dataclass
class TurnMetadata:
    """Метаданные хода."""
    turn_number: int
    timestamp: float = field(default_factory=time.time)
    elapsed_ms: float = 0.0
    user_message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "turn_number": self.turn_number,
            "timestamp": self.timestamp,
            "elapsed_ms": round(self.elapsed_ms, 2),
            "user_message": self.user_message,
        }


# =============================================================================
# Classification Trace
# =============================================================================

@dataclass
class ClassificationTrace:
    """
    Трейс классификации интента.

    Включает все альтернативы для анализа качества классификации.
    """
    top_intent: str = ""
    confidence: float = 0.0
    all_scores: Dict[str, float] = field(default_factory=dict)
    method_used: str = ""  # "lemma", "hybrid", "llm"
    disambiguation_options: List[Dict] = field(default_factory=list)
    disambiguation_triggered: bool = False
    extracted_data: Dict[str, Any] = field(default_factory=dict)
    classification_time_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "top_intent": self.top_intent,
            "confidence": round(self.confidence, 4),
            "all_scores": {k: round(v, 4) for k, v in self.all_scores.items()},
            "method_used": self.method_used,
            "disambiguation_options": self.disambiguation_options,
            "disambiguation_triggered": self.disambiguation_triggered,
            "extracted_data": self.extracted_data,
            "classification_time_ms": round(self.classification_time_ms, 2),
        }

    def to_compact_dict(self) -> Dict[str, Any]:
        """Сокращенная версия для логов."""
        top3 = sorted(self.all_scores.items(), key=lambda x: -x[1])[:3]
        return {
            "intent": self.top_intent,
            "conf": round(self.confidence, 2),
            "top3": {k: round(v, 2) for k, v in top3},
            "method": self.method_used,
        }


# =============================================================================
# Tone Analysis Trace
# =============================================================================

@dataclass
class ToneAnalysisTrace:
    """Трейс анализа тона."""
    detected_tone: str = "neutral"
    frustration_level: int = 0
    markers_found: List[str] = field(default_factory=list)
    style: str = "neutral"
    should_apologize: bool = False
    should_offer_exit: bool = False
    analysis_time_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "detected_tone": self.detected_tone,
            "frustration_level": self.frustration_level,
            "markers_found": self.markers_found,
            "style": self.style,
            "should_apologize": self.should_apologize,
            "should_offer_exit": self.should_offer_exit,
            "analysis_time_ms": round(self.analysis_time_ms, 2),
        }


# =============================================================================
# Guard Check Trace
# =============================================================================

@dataclass
class GuardCheckTrace:
    """Трейс проверки ConversationGuard."""
    intervention_triggered: bool = False
    trigger_reason: Optional[str] = None
    can_continue: bool = True
    frustration_at_check: int = 0
    check_time_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "intervention_triggered": self.intervention_triggered,
            "trigger_reason": self.trigger_reason,
            "can_continue": self.can_continue,
            "frustration_at_check": self.frustration_at_check,
            "check_time_ms": round(self.check_time_ms, 2),
        }


# =============================================================================
# Fallback Trace
# =============================================================================

@dataclass
class FallbackTrace:
    """Трейс fallback обработки."""
    tier: Optional[str] = None
    reason: Optional[str] = None
    alternatives_considered: List[str] = field(default_factory=list)
    fallback_action: Optional[str] = None
    fallback_message: Optional[str] = None
    recovery_possible: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tier": self.tier,
            "reason": self.reason,
            "alternatives_considered": self.alternatives_considered,
            "fallback_action": self.fallback_action,
            "fallback_message": self.fallback_message[:100] if self.fallback_message else None,
            "recovery_possible": self.recovery_possible,
        }


# =============================================================================
# Lead Score Trace
# =============================================================================

@dataclass
class LeadScoreTrace:
    """Трейс изменения lead score."""
    previous_score: float = 0.0
    new_score: float = 0.0
    signals_applied: List[str] = field(default_factory=list)
    decay_applied: float = 0.0
    temperature: str = "cold"

    @property
    def score_change(self) -> float:
        return self.new_score - self.previous_score

    def to_dict(self) -> Dict[str, Any]:
        return {
            "previous_score": round(self.previous_score, 2),
            "new_score": round(self.new_score, 2),
            "score_change": round(self.score_change, 2),
            "signals_applied": self.signals_applied,
            "decay_applied": round(self.decay_applied, 2),
            "temperature": self.temperature,
        }


# =============================================================================
# Objection Trace
# =============================================================================

@dataclass
class ObjectionTrace:
    """Трейс обработки возражения."""
    detected: bool = False
    detected_type: Optional[str] = None
    attempt_number: int = 0
    strategy_selected: Optional[str] = None
    should_soft_close: bool = False
    consecutive_count: int = 0
    total_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "detected": self.detected,
            "detected_type": self.detected_type,
            "attempt_number": self.attempt_number,
            "strategy_selected": self.strategy_selected,
            "should_soft_close": self.should_soft_close,
            "consecutive_count": self.consecutive_count,
            "total_count": self.total_count,
        }


# =============================================================================
# State Machine Trace (РАСШИРЕННЫЙ)
# =============================================================================

@dataclass
class RuleResolutionTrace:
    """Детальный трейс разрешения правила."""
    intent: str = ""
    rules_checked: List[Dict[str, Any]] = field(default_factory=list)  # [{rule_name, matched}]
    rule_type: str = "simple"  # simple, conditional, chain
    final_rule: Optional[str] = None
    resolution_path: str = "direct"  # direct, condition_matched, default, fallback

    def to_dict(self) -> Dict[str, Any]:
        return {
            "intent": self.intent,
            "rules_checked": self.rules_checked,
            "rule_type": self.rule_type,
            "final_rule": self.final_rule,
            "resolution_path": self.resolution_path,
        }


@dataclass
class ConditionEvaluationTrace:
    """Трейс оценки условий."""
    conditions_checked: List[Dict[str, Any]] = field(default_factory=list)  # [{name, result, field_values}]
    matched_condition: Optional[str] = None
    evaluation_time_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "conditions_checked": self.conditions_checked,
            "matched_condition": self.matched_condition,
            "evaluation_time_ms": round(self.evaluation_time_ms, 2),
        }


@dataclass
class TransitionDecisionTrace:
    """Трейс решения о переходе."""
    transition_type: str = "forward"  # forward, stay, goback, skip, final
    reason: str = ""  # rule_matched, no_rule, guard_override, policy_override
    alternatives_considered: List[Dict[str, str]] = field(default_factory=list)  # [{state, why_rejected}]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "transition_type": self.transition_type,
            "reason": self.reason,
            "alternatives_considered": self.alternatives_considered,
        }


@dataclass
class CollectedDataChangesTrace:
    """Трейс изменений собранных данных."""
    before: Dict[str, Any] = field(default_factory=dict)
    after: Dict[str, Any] = field(default_factory=dict)
    new_fields: List[str] = field(default_factory=list)
    updated_fields: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "before": self.before,
            "after": self.after,
            "new_fields": self.new_fields,
            "updated_fields": self.updated_fields,
        }


@dataclass
class RequiredDataStatusTrace:
    """Трейс статуса обязательных данных."""
    required: List[str] = field(default_factory=list)
    collected: List[str] = field(default_factory=list)
    missing: List[str] = field(default_factory=list)
    completion_percent: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "required": self.required,
            "collected": self.collected,
            "missing": self.missing,
            "completion_percent": round(self.completion_percent, 1),
        }


@dataclass
class CircularFlowTrace:
    """Трейс circular flow (goback)."""
    goback_triggered: bool = False
    goback_from: Optional[str] = None
    goback_to: Optional[str] = None
    goback_count: int = 0
    max_gobacks: int = 2
    goback_history: List[Dict[str, Any]] = field(default_factory=list)  # [{from, to, turn}]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "goback_triggered": self.goback_triggered,
            "goback_from": self.goback_from,
            "goback_to": self.goback_to,
            "goback_count": self.goback_count,
            "max_gobacks": self.max_gobacks,
            "goback_history": self.goback_history,
        }


@dataclass
class OnEnterActionsTrace:
    """Трейс on_enter действий."""
    actions_executed: List[str] = field(default_factory=list)
    results: List[Dict[str, Any]] = field(default_factory=list)  # [{action, success, details}]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "actions_executed": self.actions_executed,
            "results": self.results,
        }


@dataclass
class PhaseProgressTrace:
    """Трейс прогресса по фазам."""
    current_phase: Optional[str] = None
    phase_order: List[str] = field(default_factory=list)
    phases_completed: List[str] = field(default_factory=list)
    next_phase: Optional[str] = None
    skip_conditions_checked: List[Dict[str, Any]] = field(default_factory=list)  # [{phase, condition, result}]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "current_phase": self.current_phase,
            "phase_order": self.phase_order,
            "phases_completed": self.phases_completed,
            "next_phase": self.next_phase,
            "skip_conditions_checked": self.skip_conditions_checked,
        }


@dataclass
class FlowConfigTrace:
    """Трейс конфигурации flow."""
    flow_name: str = ""
    current_state_config: Dict[str, Any] = field(default_factory=dict)
    available_transitions: List[Dict[str, str]] = field(default_factory=list)  # [{intent, next_state}]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "flow_name": self.flow_name,
            "current_state_config": self.current_state_config,
            "available_transitions": self.available_transitions,
        }


@dataclass
class StateMachineTrace:
    """
    Полный трейс StateMachine (РАСШИРЕННЫЙ).

    Содержит все детали перехода состояний.
    """
    prev_state: str = ""
    next_state: str = ""
    prev_phase: Optional[str] = None
    next_phase: Optional[str] = None
    action: str = ""
    is_final: bool = False

    # Детальные компоненты
    rule_resolution: Optional[RuleResolutionTrace] = None
    condition_evaluation: Optional[ConditionEvaluationTrace] = None
    transition_decision: Optional[TransitionDecisionTrace] = None
    collected_data_changes: Optional[CollectedDataChangesTrace] = None
    required_data_status: Optional[RequiredDataStatusTrace] = None
    circular_flow: Optional[CircularFlowTrace] = None
    on_enter_actions: Optional[OnEnterActionsTrace] = None
    phase_progress: Optional[PhaseProgressTrace] = None
    flow_config: Optional[FlowConfigTrace] = None

    # Время выполнения
    processing_time_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "prev_state": self.prev_state,
            "next_state": self.next_state,
            "prev_phase": self.prev_phase,
            "next_phase": self.next_phase,
            "action": self.action,
            "is_final": self.is_final,
            "processing_time_ms": round(self.processing_time_ms, 2),
        }

        if self.rule_resolution:
            result["rule_resolution"] = self.rule_resolution.to_dict()
        if self.condition_evaluation:
            result["condition_evaluation"] = self.condition_evaluation.to_dict()
        if self.transition_decision:
            result["transition_decision"] = self.transition_decision.to_dict()
        if self.collected_data_changes:
            result["collected_data_changes"] = self.collected_data_changes.to_dict()
        if self.required_data_status:
            result["required_data_status"] = self.required_data_status.to_dict()
        if self.circular_flow:
            result["circular_flow"] = self.circular_flow.to_dict()
        if self.on_enter_actions:
            result["on_enter_actions"] = self.on_enter_actions.to_dict()
        if self.phase_progress:
            result["phase_progress"] = self.phase_progress.to_dict()
        if self.flow_config:
            result["flow_config"] = self.flow_config.to_dict()

        return result

    def to_compact_dict(self) -> Dict[str, Any]:
        """Сокращенная версия для логов."""
        return {
            "prev": self.prev_state,
            "next": self.next_state,
            "action": self.action,
            "phase": f"{self.prev_phase}->{self.next_phase}" if self.prev_phase != self.next_phase else self.next_phase,
            "final": self.is_final,
        }


# =============================================================================
# Policy Override Trace
# =============================================================================

@dataclass
class PolicyOverrideTrace:
    """Трейс policy override."""
    was_overridden: bool = False
    original_action: Optional[str] = None
    override_action: Optional[str] = None
    reason_codes: List[str] = field(default_factory=list)
    signals_used: List[str] = field(default_factory=list)
    decision: Optional[str] = None  # REPAIR, CONSERVATIVE, etc.

    def to_dict(self) -> Dict[str, Any]:
        return {
            "was_overridden": self.was_overridden,
            "original_action": self.original_action,
            "override_action": self.override_action,
            "reason_codes": self.reason_codes,
            "signals_used": self.signals_used,
            "decision": self.decision,
        }


# =============================================================================
# Response Trace
# =============================================================================

@dataclass
class ResponseTrace:
    """Трейс генерации ответа."""
    template_key: Optional[str] = None
    personalization_applied: Dict[str, Any] = field(default_factory=dict)
    cta_added: bool = False
    cta_type: Optional[str] = None
    response_length: int = 0
    generation_time_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "template_key": self.template_key,
            "personalization_applied": self.personalization_applied,
            "cta_added": self.cta_added,
            "cta_type": self.cta_type,
            "response_length": self.response_length,
            "generation_time_ms": round(self.generation_time_ms, 2),
        }


# =============================================================================
# LLM Trace (НОВОЕ)
# =============================================================================

@dataclass
class LLMTrace:
    """
    Трейс LLM вызова.

    Сохраняет все детали вызова LLM для анализа.
    """
    request_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    purpose: str = ""  # classification, response_generation, etc.
    prompt_system: Optional[str] = None
    prompt_user: str = ""
    raw_response: str = ""
    tokens_input: int = 0
    tokens_output: int = 0
    latency_ms: float = 0.0
    model_used: str = ""
    circuit_breaker_state: str = "closed"
    retry_count: int = 0
    success: bool = True
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "purpose": self.purpose,
            "prompt_system": self.prompt_system[:200] if self.prompt_system else None,
            "prompt_user": self.prompt_user[:200] if self.prompt_user else "",
            "raw_response": self.raw_response[:500] if self.raw_response else "",
            "tokens_input": self.tokens_input,
            "tokens_output": self.tokens_output,
            "latency_ms": round(self.latency_ms, 2),
            "model_used": self.model_used,
            "circuit_breaker_state": self.circuit_breaker_state,
            "retry_count": self.retry_count,
            "success": self.success,
            "error": self.error,
        }

    def to_compact_dict(self) -> Dict[str, Any]:
        """Сокращенная версия."""
        return {
            "id": self.request_id,
            "purpose": self.purpose,
            "tokens": {"in": self.tokens_input, "out": self.tokens_output},
            "latency_ms": round(self.latency_ms, 2),
            "success": self.success,
        }


# =============================================================================
# Timing Trace (НОВОЕ)
# =============================================================================

@dataclass
class TimingTrace:
    """Трейс таймингов turn."""
    tone_analysis_ms: float = 0.0
    guard_check_ms: float = 0.0
    classification_ms: float = 0.0
    classification_llm_ms: float = 0.0  # LLM часть классификации
    state_machine_ms: float = 0.0
    response_generation_ms: float = 0.0
    response_generation_llm_ms: float = 0.0  # LLM часть генерации
    total_turn_ms: float = 0.0
    bottleneck: str = ""  # какой этап занял больше всего

    def compute_bottleneck(self) -> None:
        """Вычислить bottleneck."""
        timings = {
            "tone_analysis": self.tone_analysis_ms,
            "guard_check": self.guard_check_ms,
            "classification": self.classification_ms,
            "state_machine": self.state_machine_ms,
            "response_generation": self.response_generation_ms,
        }
        if timings:
            self.bottleneck = max(timings, key=timings.get)

    def to_dict(self) -> Dict[str, Any]:
        self.compute_bottleneck()
        return {
            "tone_analysis_ms": round(self.tone_analysis_ms, 2),
            "guard_check_ms": round(self.guard_check_ms, 2),
            "classification_ms": round(self.classification_ms, 2),
            "classification_llm_ms": round(self.classification_llm_ms, 2),
            "state_machine_ms": round(self.state_machine_ms, 2),
            "response_generation_ms": round(self.response_generation_ms, 2),
            "response_generation_llm_ms": round(self.response_generation_llm_ms, 2),
            "total_turn_ms": round(self.total_turn_ms, 2),
            "bottleneck": self.bottleneck,
        }


# =============================================================================
# Context Window Trace (НОВОЕ)
# =============================================================================

@dataclass
class TurnSummary:
    """Краткая информация о ходе для sliding window."""
    turn: int
    intent: str
    action: str
    confidence: float
    state: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "turn": self.turn,
            "intent": self.intent,
            "action": self.action,
            "confidence": round(self.confidence, 2),
            "state": self.state,
        }


@dataclass
class ContextWindowTrace:
    """Трейс контекстного окна."""
    sliding_window: List[TurnSummary] = field(default_factory=list)
    episodic_events: List[str] = field(default_factory=list)  # breakthrough, first_objection, etc.
    momentum_breakdown: Dict[str, Any] = field(default_factory=dict)  # {raw, direction, components}
    engagement_breakdown: Dict[str, Any] = field(default_factory=dict)  # {score, level, trend, factors}
    client_profile_snapshot: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sliding_window": [t.to_dict() for t in self.sliding_window],
            "episodic_events": self.episodic_events,
            "momentum_breakdown": self.momentum_breakdown,
            "engagement_breakdown": self.engagement_breakdown,
            "client_profile_snapshot": self.client_profile_snapshot,
        }


# =============================================================================
# Personalization Trace (НОВОЕ)
# =============================================================================

@dataclass
class PersonalizationTrace:
    """Трейс персонализации."""
    template_selected: str = ""
    selection_reason: str = ""
    substitutions: Dict[str, str] = field(default_factory=dict)
    business_context: str = ""  # small_business, enterprise
    industry_context: str = ""  # horeca, retail, etc.

    def to_dict(self) -> Dict[str, Any]:
        return {
            "template_selected": self.template_selected,
            "selection_reason": self.selection_reason,
            "substitutions": self.substitutions,
            "business_context": self.business_context,
            "industry_context": self.industry_context,
        }


# =============================================================================
# Client Agent Trace (НОВОЕ - для симулятора)
# =============================================================================

@dataclass
class ClientAgentTrace:
    """
    Трейс клиентского агента (для симулятора).

    Показывает как симулятор принимал решения за клиента.
    """
    persona_name: str = ""
    persona_description: str = ""
    prompt_sent_to_llm: str = ""
    raw_llm_response: str = ""
    cleaned_response: str = ""
    noise_applied: Dict[str, List[str]] = field(default_factory=dict)  # {typos: [...], shortenings: [...]}
    objection_decision: Dict[str, Any] = field(default_factory=dict)  # {roll, threshold, injected}
    objection_injected: Optional[str] = None
    variety_check: Dict[str, bool] = field(default_factory=dict)  # {similar_to_last, forced_alternative}
    leave_decision: Dict[str, Any] = field(default_factory=dict)  # {should_leave, reason}
    llm_latency_ms: float = 0.0
    # Disambiguation handling (button selection)
    disambiguation_decision: Dict[str, Any] = field(default_factory=dict)  # {detected, options, chosen_index, reason}
    # KB question injection
    kb_question_used: Optional[str] = None
    kb_question_source: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "persona_name": self.persona_name,
            "persona_description": self.persona_description[:200] if self.persona_description else "",
            "prompt_sent_to_llm": self.prompt_sent_to_llm[:500] if self.prompt_sent_to_llm else "",
            "raw_llm_response": self.raw_llm_response[:200] if self.raw_llm_response else "",
            "cleaned_response": self.cleaned_response,
            "noise_applied": self.noise_applied,
            "objection_decision": self.objection_decision,
            "objection_injected": self.objection_injected,
            "variety_check": self.variety_check,
            "leave_decision": self.leave_decision,
            "llm_latency_ms": round(self.llm_latency_ms, 2),
        }
        # Include disambiguation if it was triggered
        if self.disambiguation_decision:
            result["disambiguation_decision"] = self.disambiguation_decision
        # Include KB question if used
        if self.kb_question_used:
            result["kb_question_used"] = self.kb_question_used
            result["kb_question_source"] = self.kb_question_source
        return result

    def to_compact_dict(self) -> Dict[str, Any]:
        """Сокращенная версия."""
        result = {
            "persona": self.persona_name,
            "response": self.cleaned_response[:100] if self.cleaned_response else "",
            "objection": self.objection_injected,
            "latency_ms": round(self.llm_latency_ms, 2),
        }
        # Include disambiguation choice if triggered
        if self.disambiguation_decision.get("detected"):
            result["disambiguation"] = {
                "chosen": self.disambiguation_decision.get("chosen_option", ""),
                "reason": self.disambiguation_decision.get("reason", ""),
            }
        return result


# =============================================================================
# Main Decision Trace
# =============================================================================

@dataclass
class DecisionTrace:
    """
    Полный трейс всех решений для одного turn.

    Объединяет все компоненты трассировки.
    """
    # Метаданные
    metadata: TurnMetadata = field(default_factory=TurnMetadata)

    # Компоненты трейса
    classification: Optional[ClassificationTrace] = None
    tone_analysis: Optional[ToneAnalysisTrace] = None
    guard_check: Optional[GuardCheckTrace] = None
    fallback: Optional[FallbackTrace] = None
    lead_score: Optional[LeadScoreTrace] = None
    objection: Optional[ObjectionTrace] = None
    state_machine: Optional[StateMachineTrace] = None
    policy_override: Optional[PolicyOverrideTrace] = None
    response: Optional[ResponseTrace] = None

    # Новые компоненты
    llm_traces: List[LLMTrace] = field(default_factory=list)
    timing: Optional[TimingTrace] = None
    context_window: Optional[ContextWindowTrace] = None
    personalization: Optional[PersonalizationTrace] = None

    # Для симулятора
    client_agent: Optional[ClientAgentTrace] = None

    # Результат
    bot_response: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Полная сериализация."""
        result = {
            "metadata": self.metadata.to_dict(),
            "bot_response": self.bot_response[:500] if self.bot_response else "",
        }

        if self.classification:
            result["classification"] = self.classification.to_dict()
        if self.tone_analysis:
            result["tone_analysis"] = self.tone_analysis.to_dict()
        if self.guard_check:
            result["guard_check"] = self.guard_check.to_dict()
        if self.fallback:
            result["fallback"] = self.fallback.to_dict()
        if self.lead_score:
            result["lead_score"] = self.lead_score.to_dict()
        if self.objection:
            result["objection"] = self.objection.to_dict()
        if self.state_machine:
            result["state_machine"] = self.state_machine.to_dict()
        if self.policy_override:
            result["policy_override"] = self.policy_override.to_dict()
        if self.response:
            result["response"] = self.response.to_dict()
        if self.llm_traces:
            result["llm_traces"] = [t.to_dict() for t in self.llm_traces]
        if self.timing:
            result["timing"] = self.timing.to_dict()
        if self.context_window:
            result["context_window"] = self.context_window.to_dict()
        if self.personalization:
            result["personalization"] = self.personalization.to_dict()
        if self.client_agent:
            result["client_agent"] = self.client_agent.to_dict()

        return result

    def to_compact_dict(self) -> Dict[str, Any]:
        """Сокращенная версия для логов."""
        result = {
            "turn": self.metadata.turn_number,
            "ms": round(self.metadata.elapsed_ms, 1),
        }

        if self.classification:
            result["classification"] = self.classification.to_compact_dict()
        if self.state_machine:
            result["state_machine"] = self.state_machine.to_compact_dict()
        if self.lead_score:
            result["lead"] = {
                "prev": self.lead_score.previous_score,
                "new": self.lead_score.new_score,
            }
        if self.fallback and self.fallback.tier:
            result["fallback"] = self.fallback.tier
        if self.policy_override and self.policy_override.was_overridden:
            result["policy"] = self.policy_override.decision

        return result

    def to_report_string(self) -> str:
        """Форматирование для текстового отчёта."""
        lines = []
        meta = self.metadata

        lines.append(f"Turn {meta.turn_number}: {self.state_machine.prev_state if self.state_machine else '?'} -> {self.state_machine.next_state if self.state_machine else '?'}")

        if self.classification:
            c = self.classification
            top3 = sorted(c.all_scores.items(), key=lambda x: -x[1])[:3]
            alt_str = ", ".join(f"{k}({v:.2f})" for k, v in top3[1:]) if len(top3) > 1 else "none"
            lines.append(f"  [CLASSIFICATION] {c.top_intent} ({c.confidence:.2f}) via {c.method_used}")
            lines.append(f"    Alternatives: {alt_str}")

        if self.tone_analysis:
            t = self.tone_analysis
            markers = ", ".join(t.markers_found[:3]) if t.markers_found else "none"
            lines.append(f"  [TONE] {t.detected_tone} | frustration: {t.frustration_level}")
            if t.markers_found:
                lines.append(f"    Markers: {markers}")

        if self.guard_check and self.guard_check.intervention_triggered:
            lines.append(f"  [GUARD] intervention: {self.guard_check.trigger_reason}")

        if self.lead_score:
            l = self.lead_score
            signals = ", ".join(l.signals_applied) if l.signals_applied else "none"
            lines.append(f"  [LEAD] {l.previous_score:.0f} -> {l.new_score:.0f} | signals: {signals}")

        if self.state_machine:
            sm = self.state_machine
            lines.append(f"  [STATE] {sm.prev_state} -> {sm.next_state} | action: {sm.action}")

            # Детали rule_resolution
            if sm.rule_resolution:
                rr = sm.rule_resolution
                lines.append(f"    Rule: {rr.final_rule} ({rr.rule_type}, {rr.resolution_path})")

            # Required data
            if sm.required_data_status:
                rd = sm.required_data_status
                lines.append(f"    Required data: {rd.completion_percent:.0f}% ({len(rd.collected)}/{len(rd.required)})")

            # Circular flow
            if sm.circular_flow and sm.circular_flow.goback_triggered:
                cf = sm.circular_flow
                lines.append(f"    Goback: {cf.goback_from} -> {cf.goback_to} (count: {cf.goback_count})")

        if self.policy_override and self.policy_override.was_overridden:
            p = self.policy_override
            lines.append(f"  [POLICY] {p.decision} ({', '.join(p.reason_codes)})")
        else:
            lines.append(f"  [POLICY] NO_OVERRIDE")

        if self.response:
            r = self.response
            cta_str = f"yes ({r.cta_type})" if r.cta_added else "no"
            lines.append(f"  [RESPONSE] template: {r.template_key} | CTA: {cta_str}")

        if self.timing:
            lines.append(f"  [TIME] {self.timing.total_turn_ms:.0f}ms")

        return "\n".join(lines)


# =============================================================================
# Decision Trace Builder
# =============================================================================

class DecisionTraceBuilder:
    """
    Builder для пошагового создания DecisionTrace.

    Usage:
        builder = DecisionTraceBuilder(turn=1, message="привет")
        builder.record_classification(classification_result)
        builder.record_tone(tone_info)
        ...
        trace = builder.build()
    """

    def __init__(self, turn: int, message: str = ""):
        self._trace = DecisionTrace(
            metadata=TurnMetadata(
                turn_number=turn,
                user_message=message,
            )
        )
        self._start_time = time.time()
        self._timing = TimingTrace()

    def record_classification(
        self,
        result: Dict[str, Any],
        all_scores: Dict[str, float] = None,
        elapsed_ms: float = 0.0,
        llm_ms: float = 0.0,
    ) -> "DecisionTraceBuilder":
        """Записать результат классификации."""
        # Determine disambiguation_triggered from multiple sources:
        # 1. Explicit flag from unified disambiguation (unified_disambiguation)
        # 2. Legacy check: intent == "disambiguation_needed"
        disambiguation_triggered = (
            result.get("disambiguation_triggered", False) or
            result.get("intent") == "disambiguation_needed"
        )

        self._trace.classification = ClassificationTrace(
            top_intent=result.get("intent", ""),
            confidence=result.get("confidence", 0.0),
            all_scores=all_scores or result.get("all_scores", {}),
            method_used=result.get("method", ""),
            disambiguation_options=result.get("disambiguation_options", []),
            disambiguation_triggered=disambiguation_triggered,
            extracted_data=result.get("extracted_data", {}),
            classification_time_ms=elapsed_ms,
        )
        self._timing.classification_ms = elapsed_ms
        self._timing.classification_llm_ms = llm_ms
        return self

    def record_tone(
        self,
        tone_info: Dict[str, Any],
        elapsed_ms: float = 0.0,
    ) -> "DecisionTraceBuilder":
        """Записать результат анализа тона."""
        self._trace.tone_analysis = ToneAnalysisTrace(
            detected_tone=tone_info.get("tone", "neutral"),
            frustration_level=tone_info.get("frustration_level", 0),
            markers_found=tone_info.get("markers_found", []),
            style=tone_info.get("style", "neutral"),
            should_apologize=tone_info.get("should_apologize", False),
            should_offer_exit=tone_info.get("should_offer_exit", False),
            analysis_time_ms=elapsed_ms,
        )
        self._timing.tone_analysis_ms = elapsed_ms
        return self

    def record_guard(
        self,
        intervention: Optional[str],
        reason: Optional[str] = None,
        can_continue: Optional[bool] = None,
        frustration: int = 0,
        elapsed_ms: float = 0.0,
    ) -> "DecisionTraceBuilder":
        """Записать результат проверки guard."""
        self._trace.guard_check = GuardCheckTrace(
            intervention_triggered=intervention is not None,
            trigger_reason=intervention or reason,
            can_continue=can_continue if can_continue is not None else (intervention is None),
            frustration_at_check=frustration,
            check_time_ms=elapsed_ms,
        )
        self._timing.guard_check_ms = elapsed_ms
        return self

    def record_fallback(
        self,
        tier: Optional[str],
        reason: Optional[str] = None,
        action: Optional[str] = None,
        message: Optional[str] = None,
    ) -> "DecisionTraceBuilder":
        """Записать fallback."""
        self._trace.fallback = FallbackTrace(
            tier=tier,
            reason=reason,
            fallback_action=action,
            fallback_message=message,
        )
        return self

    def record_lead_score(
        self,
        previous: float,
        new: float,
        signals: List[str] = None,
        decay: float = 0.0,
        temperature: str = "cold",
    ) -> "DecisionTraceBuilder":
        """Записать изменение lead score."""
        self._trace.lead_score = LeadScoreTrace(
            previous_score=previous,
            new_score=new,
            signals_applied=signals or [],
            decay_applied=decay,
            temperature=temperature,
        )
        return self

    def record_objection(
        self,
        detected: bool,
        objection_type: Optional[str] = None,
        attempt: int = 0,
        strategy: Optional[str] = None,
        soft_close: bool = False,
        consecutive: int = 0,
        total: int = 0,
    ) -> "DecisionTraceBuilder":
        """Записать обработку возражения."""
        self._trace.objection = ObjectionTrace(
            detected=detected,
            detected_type=objection_type,
            attempt_number=attempt,
            strategy_selected=strategy,
            should_soft_close=soft_close,
            consecutive_count=consecutive,
            total_count=total,
        )
        return self

    def record_state_machine(
        self,
        sm_result: Dict[str, Any],
        elapsed_ms: float = 0.0,
    ) -> "DecisionTraceBuilder":
        """Записать результат StateMachine."""
        self._trace.state_machine = StateMachineTrace(
            prev_state=sm_result.get("prev_state", ""),
            next_state=sm_result.get("next_state", ""),
            prev_phase=sm_result.get("prev_phase"),
            next_phase=sm_result.get("spin_phase"),
            action=sm_result.get("action", ""),
            is_final=sm_result.get("is_final", False),
            processing_time_ms=elapsed_ms,
        )
        self._timing.state_machine_ms = elapsed_ms
        return self

    def record_state_machine_detail(
        self,
        rule_resolution: RuleResolutionTrace = None,
        condition_evaluation: ConditionEvaluationTrace = None,
        transition_decision: TransitionDecisionTrace = None,
        collected_data_changes: CollectedDataChangesTrace = None,
        required_data_status: RequiredDataStatusTrace = None,
        circular_flow: CircularFlowTrace = None,
        on_enter_actions: OnEnterActionsTrace = None,
        phase_progress: PhaseProgressTrace = None,
        flow_config: FlowConfigTrace = None,
    ) -> "DecisionTraceBuilder":
        """Записать детали StateMachine."""
        if self._trace.state_machine:
            sm = self._trace.state_machine
            if rule_resolution:
                sm.rule_resolution = rule_resolution
            if condition_evaluation:
                sm.condition_evaluation = condition_evaluation
            if transition_decision:
                sm.transition_decision = transition_decision
            if collected_data_changes:
                sm.collected_data_changes = collected_data_changes
            if required_data_status:
                sm.required_data_status = required_data_status
            if circular_flow:
                sm.circular_flow = circular_flow
            if on_enter_actions:
                sm.on_enter_actions = on_enter_actions
            if phase_progress:
                sm.phase_progress = phase_progress
            if flow_config:
                sm.flow_config = flow_config
        return self

    def record_policy_override(
        self,
        override: Any,  # PolicyOverride from dialogue_policy
    ) -> "DecisionTraceBuilder":
        """Записать policy override."""
        if override and hasattr(override, 'has_override') and override.has_override:
            self._trace.policy_override = PolicyOverrideTrace(
                was_overridden=True,
                original_action=getattr(override, 'original_action', None),
                override_action=getattr(override, 'action', None),
                reason_codes=getattr(override, 'reason_codes', []),
                signals_used=getattr(override, 'signals', []),
                decision=getattr(override, 'decision', None).value if hasattr(override, 'decision') and override.decision else None,
            )
        else:
            self._trace.policy_override = PolicyOverrideTrace(was_overridden=False)
        return self

    def record_response(
        self,
        template_key: Optional[str] = None,
        personalization: Dict[str, Any] = None,
        cta_added: bool = False,
        cta_type: Optional[str] = None,
        response_text: str = "",
        elapsed_ms: float = 0.0,
        llm_ms: float = 0.0,
    ) -> "DecisionTraceBuilder":
        """Записать генерацию ответа."""
        self._trace.response = ResponseTrace(
            template_key=template_key,
            personalization_applied=personalization or {},
            cta_added=cta_added,
            cta_type=cta_type,
            response_length=len(response_text),
            generation_time_ms=elapsed_ms,
        )
        self._trace.bot_response = response_text
        self._timing.response_generation_ms = elapsed_ms
        self._timing.response_generation_llm_ms = llm_ms
        return self

    def add_llm_trace(self, llm_trace: LLMTrace) -> "DecisionTraceBuilder":
        """Добавить LLM trace."""
        self._trace.llm_traces.append(llm_trace)
        return self

    def record_context_window(
        self,
        sliding_window: List[TurnSummary] = None,
        episodic_events: List[str] = None,
        momentum: Dict[str, Any] = None,
        engagement: Dict[str, Any] = None,
        profile: Dict[str, Any] = None,
    ) -> "DecisionTraceBuilder":
        """Записать контекстное окно."""
        self._trace.context_window = ContextWindowTrace(
            sliding_window=sliding_window or [],
            episodic_events=episodic_events or [],
            momentum_breakdown=momentum or {},
            engagement_breakdown=engagement or {},
            client_profile_snapshot=profile or {},
        )
        return self

    def record_personalization(
        self,
        template: str = "",
        reason: str = "",
        substitutions: Dict[str, str] = None,
        business_ctx: str = "",
        industry_ctx: str = "",
    ) -> "DecisionTraceBuilder":
        """Записать персонализацию."""
        self._trace.personalization = PersonalizationTrace(
            template_selected=template,
            selection_reason=reason,
            substitutions=substitutions or {},
            business_context=business_ctx,
            industry_context=industry_ctx,
        )
        return self

    def record_client_agent(
        self,
        client_trace: ClientAgentTrace,
    ) -> "DecisionTraceBuilder":
        """Записать клиентский агент trace."""
        self._trace.client_agent = client_trace
        return self

    def build(self) -> DecisionTrace:
        """Завершить и вернуть trace."""
        # Финализируем timing
        total_ms = (time.time() - self._start_time) * 1000
        self._timing.total_turn_ms = total_ms
        self._timing.compute_bottleneck()
        self._trace.timing = self._timing

        # Обновляем metadata
        self._trace.metadata.elapsed_ms = total_ms

        return self._trace


# =============================================================================
# Decision Statistics (Агрегированная статистика)
# =============================================================================

@dataclass
class DecisionStatistics:
    """
    Полная статистика по всем симуляциям.

    Агрегирует данные из всех DecisionTrace.
    """

    # === ОБЩАЯ СТАТИСТИКА ===
    total_simulations: int = 0
    total_turns: int = 0
    avg_turns_per_simulation: float = 0.0
    total_duration_seconds: float = 0.0

    # === OUTCOMES ===
    outcomes: Dict[str, int] = field(default_factory=dict)
    outcome_rates: Dict[str, float] = field(default_factory=dict)

    # === ПО ПЕРСОНАМ ===
    per_persona: Dict[str, Dict] = field(default_factory=dict)

    # === CLASSIFICATION ===
    classification_stats: Dict[str, Any] = field(default_factory=dict)

    # === TONE & FRUSTRATION ===
    tone_stats: Dict[str, Any] = field(default_factory=dict)

    # === FALLBACK ===
    fallback_stats: Dict[str, Any] = field(default_factory=dict)

    # === LEAD SCORING ===
    lead_score_stats: Dict[str, Any] = field(default_factory=dict)

    # === STATE MACHINE ===
    state_machine_stats: Dict[str, Any] = field(default_factory=dict)

    # === POLICY ===
    policy_stats: Dict[str, Any] = field(default_factory=dict)

    # === OBJECTIONS ===
    objection_stats: Dict[str, Any] = field(default_factory=dict)

    # === PHASES ===
    phase_stats: Dict[str, Any] = field(default_factory=dict)

    # === RESPONSE ===
    response_stats: Dict[str, Any] = field(default_factory=dict)

    # === QUALITY ===
    quality_metrics: Dict[str, Any] = field(default_factory=dict)

    # === LLM ===
    llm_stats: Dict[str, Any] = field(default_factory=dict)

    # === TIMING ===
    timing_stats: Dict[str, Any] = field(default_factory=dict)

    # === CLIENT AGENT ===
    client_agent_stats: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Сериализовать в словарь."""
        return {
            "total_simulations": self.total_simulations,
            "total_turns": self.total_turns,
            "avg_turns_per_simulation": round(self.avg_turns_per_simulation, 2),
            "total_duration_seconds": round(self.total_duration_seconds, 2),
            "outcomes": self.outcomes,
            "outcome_rates": {k: round(v, 2) for k, v in self.outcome_rates.items()},
            "per_persona": self.per_persona,
            "classification": self.classification_stats,
            "tone": self.tone_stats,
            "fallback": self.fallback_stats,
            "lead_scoring": self.lead_score_stats,
            "state_machine": self.state_machine_stats,
            "policy": self.policy_stats,
            "objections": self.objection_stats,
            "phases": self.phase_stats,
            "response": self.response_stats,
            "quality_metrics": self.quality_metrics,
            "llm": self.llm_stats,
            "timing": self.timing_stats,
            "client_agent": self.client_agent_stats,
        }


def aggregate_decision_statistics(
    traces_by_simulation: Dict[int, List[DecisionTrace]],
    outcomes: Dict[int, str] = None,
    personas: Dict[int, str] = None,
    durations: Dict[int, float] = None,
) -> DecisionStatistics:
    """
    Агрегировать статистику из всех traces.

    Args:
        traces_by_simulation: Dict[sim_id -> List[DecisionTrace]]
        outcomes: Dict[sim_id -> outcome]
        personas: Dict[sim_id -> persona]
        durations: Dict[sim_id -> duration_seconds]

    Returns:
        DecisionStatistics с агрегированными данными
    """
    stats = DecisionStatistics()

    outcomes = outcomes or {}
    personas = personas or {}
    durations = durations or {}

    stats.total_simulations = len(traces_by_simulation)
    stats.total_turns = sum(len(traces) for traces in traces_by_simulation.values())
    stats.avg_turns_per_simulation = stats.total_turns / max(stats.total_simulations, 1)
    stats.total_duration_seconds = sum(durations.values())

    # Outcomes
    for sim_id, outcome in outcomes.items():
        stats.outcomes[outcome] = stats.outcomes.get(outcome, 0) + 1

    for outcome, count in stats.outcomes.items():
        stats.outcome_rates[outcome] = count / max(stats.total_simulations, 1)

    # Per persona
    persona_data: Dict[str, Dict] = {}
    for sim_id, traces in traces_by_simulation.items():
        persona = personas.get(sim_id, "unknown")
        if persona not in persona_data:
            persona_data[persona] = {
                "count": 0,
                "success": 0,
                "turns": 0,
                "avg_turns": 0.0,
                "success_rate": 0.0,
            }
        persona_data[persona]["count"] += 1
        persona_data[persona]["turns"] += len(traces)
        if outcomes.get(sim_id) == "success":
            persona_data[persona]["success"] += 1

    for persona, data in persona_data.items():
        data["avg_turns"] = data["turns"] / max(data["count"], 1)
        data["success_rate"] = data["success"] / max(data["count"], 1)

    stats.per_persona = persona_data

    # Classification stats
    all_confidences = []
    method_counts: Dict[str, int] = {}
    intent_counts: Dict[str, int] = {}
    disambiguation_count = 0

    for traces in traces_by_simulation.values():
        for trace in traces:
            if trace.classification:
                c = trace.classification
                all_confidences.append(c.confidence)
                method_counts[c.method_used] = method_counts.get(c.method_used, 0) + 1
                intent_counts[c.top_intent] = intent_counts.get(c.top_intent, 0) + 1
                if c.disambiguation_triggered:
                    disambiguation_count += 1

    if all_confidences:
        stats.classification_stats = {
            "avg_confidence": sum(all_confidences) / len(all_confidences),
            "confidence_distribution": {
                ">0.9": len([c for c in all_confidences if c > 0.9]),
                "0.7-0.9": len([c for c in all_confidences if 0.7 <= c <= 0.9]),
                "<0.7": len([c for c in all_confidences if c < 0.7]),
            },
            "method_usage": method_counts,
            "intent_frequency": dict(sorted(intent_counts.items(), key=lambda x: -x[1])[:10]),
            "disambiguation_rate": disambiguation_count / max(len(all_confidences), 1),
        }

    # Fallback stats
    total_fallbacks = 0
    fallback_by_tier: Dict[str, int] = {}

    for traces in traces_by_simulation.values():
        for trace in traces:
            if trace.fallback and trace.fallback.tier:
                total_fallbacks += 1
                tier = trace.fallback.tier
                fallback_by_tier[tier] = fallback_by_tier.get(tier, 0) + 1

    stats.fallback_stats = {
        "total_fallbacks": total_fallbacks,
        "fallback_rate": total_fallbacks / max(stats.total_turns, 1),
        "by_tier": fallback_by_tier,
    }

    # Lead score stats
    final_scores = []
    all_signals: Dict[str, int] = {}

    for sim_id, traces in traces_by_simulation.items():
        if traces:
            last_trace = traces[-1]
            if last_trace.lead_score:
                final_scores.append(last_trace.lead_score.new_score)

        for trace in traces:
            if trace.lead_score:
                for signal in trace.lead_score.signals_applied:
                    all_signals[signal] = all_signals.get(signal, 0) + 1

    if final_scores:
        stats.lead_score_stats = {
            "avg_final_score": sum(final_scores) / len(final_scores),
            "score_distribution": {
                "hot": len([s for s in final_scores if s >= 70]),
                "warm": len([s for s in final_scores if 40 <= s < 70]),
                "cold": len([s for s in final_scores if s < 40]),
            },
            "top_signals": dict(sorted(all_signals.items(), key=lambda x: -x[1])[:10]),
        }

    # State machine stats
    transition_counts: Dict[str, int] = {}
    state_visits: Dict[str, int] = {}
    transition_types: Dict[str, int] = {"forward": 0, "stay": 0, "goback": 0, "skip": 0, "final": 0}

    for traces in traces_by_simulation.values():
        for trace in traces:
            if trace.state_machine:
                sm = trace.state_machine

                # State visits
                state_visits[sm.next_state] = state_visits.get(sm.next_state, 0) + 1

                # Transitions
                trans_key = f"{sm.prev_state}->{sm.next_state}"
                transition_counts[trans_key] = transition_counts.get(trans_key, 0) + 1

                # Transition type
                if sm.is_final:
                    transition_types["final"] += 1
                elif sm.prev_state == sm.next_state:
                    transition_types["stay"] += 1
                elif sm.circular_flow and sm.circular_flow.goback_triggered:
                    transition_types["goback"] += 1
                else:
                    transition_types["forward"] += 1

    stats.state_machine_stats = {
        "state_visit_frequency": dict(sorted(state_visits.items(), key=lambda x: -x[1])[:15]),
        "transition_frequency": dict(sorted(transition_counts.items(), key=lambda x: -x[1])[:15]),
        "transition_types": transition_types,
        "avg_states_per_dialog": len(state_visits) / max(stats.total_simulations, 1),
    }

    # Policy stats
    override_count = 0
    override_types: Dict[str, int] = {}

    for traces in traces_by_simulation.values():
        for trace in traces:
            if trace.policy_override and trace.policy_override.was_overridden:
                override_count += 1
                decision = trace.policy_override.decision or "unknown"
                override_types[decision] = override_types.get(decision, 0) + 1

    stats.policy_stats = {
        "total_overrides": override_count,
        "override_rate": override_count / max(stats.total_turns, 1),
        "override_types": override_types,
    }

    # LLM stats
    total_llm_calls = 0
    total_tokens_in = 0
    total_tokens_out = 0
    all_latencies = []
    retries = 0

    for traces in traces_by_simulation.values():
        for trace in traces:
            for llm_trace in trace.llm_traces:
                total_llm_calls += 1
                total_tokens_in += llm_trace.tokens_input
                total_tokens_out += llm_trace.tokens_output
                all_latencies.append(llm_trace.latency_ms)
                retries += llm_trace.retry_count

    if all_latencies:
        sorted_latencies = sorted(all_latencies)
        p95_idx = int(len(sorted_latencies) * 0.95)
        stats.llm_stats = {
            "total_llm_calls": total_llm_calls,
            "total_tokens_input": total_tokens_in,
            "total_tokens_output": total_tokens_out,
            "avg_latency_ms": sum(all_latencies) / len(all_latencies),
            "p95_latency_ms": sorted_latencies[p95_idx] if p95_idx < len(sorted_latencies) else 0,
            "max_latency_ms": max(all_latencies),
            "total_retries": retries,
        }

    # Timing stats
    all_turn_times = []
    bottleneck_counts: Dict[str, int] = {}

    for traces in traces_by_simulation.values():
        for trace in traces:
            if trace.timing:
                all_turn_times.append(trace.timing.total_turn_ms)
                bottleneck = trace.timing.bottleneck
                if bottleneck:
                    bottleneck_counts[bottleneck] = bottleneck_counts.get(bottleneck, 0) + 1

    if all_turn_times:
        stats.timing_stats = {
            "avg_turn_ms": sum(all_turn_times) / len(all_turn_times),
            "bottleneck_distribution": bottleneck_counts,
        }

    # Quality metrics
    high_conf_count = len([c for c in all_confidences if c > 0.8]) if all_confidences else 0
    stats.quality_metrics = {
        "classification_accuracy_proxy": high_conf_count / max(len(all_confidences), 1) if all_confidences else 0,
        "flow_efficiency": stats.avg_turns_per_simulation,
    }

    return stats
