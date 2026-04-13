"""Response planning for deterministic pilot survey turns."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Optional, Sequence

from src.blackboard.sources.pilot_survey_answer_gate import PILOT_SURVEY_SIGNAL_SOURCE
from src.dialog_transcript import DialogTranscript, DialogTranscriptTurn


NOOP_ACTIONS = frozenset({
    "continue_current_goal",
    "continue_conversation",
    "acknowledge_and_continue",
})
UNCLEAR_CLARIFY_ACTIONS = NOOP_ACTIONS | frozenset({
    "ask_clarification",
    "guard_rephrase",
    "guard_offer_options",
    "offer_options",
})
CONSENT_STATE = "survey_consent"
FIRST_SURVEY_STATE = "survey_q1"
DECLINED_STATE = "survey_declined"

COMPANY_ANSWER_ACTIONS = frozenset({
    "answer_with_facts",
    "answer_with_knowledge",
    "answer_with_pricing",
    "answer_with_pricing_direct",
    "answer_with_pricing_brief",
    "answer_pricing_details",
    "answer_and_continue",
    "answer_technical_question",
    "answer_security_question",
    "compare_with_competitor",
    "compare_pricing",
    "discuss_budget",
    "explain_payment_terms",
    "explain_support_options",
    "explain_training_options",
    "explain_implementation_process",
    "handle_discount_request",
})


@dataclass(frozen=True)
class PilotSurveyResponsePlan:
    """Turn-local plan for composing pilot survey responses."""

    routing_state: str
    state: str
    next_state: str
    direct_response: str = ""
    generator_required: bool = False
    suffix: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def active(self) -> bool:
        return True

    def compose(self, generated_response: str = "") -> str:
        base = str(generated_response or "").strip()
        if self.direct_response:
            return self.direct_response.strip()
        if not self.suffix:
            return base
        if not base:
            return self.suffix.strip()
        return f"{base}\n\n{self.suffix.strip()}"


def build_pilot_survey_response_plan(
    *,
    flow: Any,
    sm_result: Dict[str, Any],
    context_signals: Sequence[Dict[str, Any]],
    transcript: Optional[DialogTranscript],
    action: str,
) -> Optional[PilotSurveyResponsePlan]:
    """Build a deterministic response plan from Blackboard's pilot survey signal."""

    if getattr(flow, "name", "") != "pilot_survey":
        return None

    consent_plan = _build_consent_transition_plan(flow=flow, sm_result=sm_result)
    if consent_plan:
        return consent_plan

    signal = _latest_pilot_signal(context_signals)
    if not signal:
        return None

    routing_state = str(signal.get("routing_state") or "")
    current_state = str(signal.get("state") or "")
    next_state = str(sm_result.get("next_state") or current_state)
    current_params = _state_params(flow, current_state)
    current_question = _deterministic_question(flow, current_state)
    final_phrase = _final_phrase(flow, next_state)

    if routing_state == "survey_answer":
        if next_state == current_state or not signal.get("answer_accepted"):
            return None
        direct = final_phrase if final_phrase else _deterministic_question(flow, next_state)
        if not direct:
            direct = _clarify_text(current_params)
        return _plan(
            routing_state=routing_state,
            state=current_state,
            next_state=next_state,
            direct_response=direct,
            deterministic_question=direct if not final_phrase else "",
            final_phrase=final_phrase,
        )

    if routing_state == "unclear":
        if str(action or "") not in UNCLEAR_CLARIFY_ACTIONS:
            return None
        direct = _clarify_text(current_params)
        return _plan(
            routing_state=routing_state,
            state=current_state,
            next_state=current_state,
            direct_response=direct,
            deterministic_question=current_question,
        )

    if routing_state == "company_question":
        if next_state != current_state or not _is_company_answer_action(action):
            return None
        suffix = _current_question_suffix(
            transcript=transcript,
            state=current_state,
            question=current_question,
        )
        return _plan(
            routing_state=routing_state,
            state=current_state,
            next_state=current_state,
            generator_required=True,
            suffix=suffix,
            deterministic_question=current_question,
            company_answer_appended=True,
        )

    if routing_state == "mixed":
        if not signal.get("answer_accepted") or not _is_company_answer_action(action):
            return None
        suffix = final_phrase if final_phrase else _deterministic_question(flow, next_state)
        if not suffix:
            suffix = _clarify_text(current_params)
        return _plan(
            routing_state=routing_state,
            state=current_state,
            next_state=next_state,
            generator_required=True,
            suffix=suffix,
            deterministic_question=suffix if not final_phrase else "",
            final_phrase=final_phrase,
            company_answer_appended=True,
        )

    return None


def _build_consent_transition_plan(
    *,
    flow: Any,
    sm_result: Dict[str, Any],
) -> Optional[PilotSurveyResponsePlan]:
    prev_state = str(sm_result.get("prev_state") or "")
    next_state = str(sm_result.get("next_state") or "")
    if prev_state != CONSENT_STATE or next_state == prev_state:
        return None

    if next_state == FIRST_SURVEY_STATE:
        question = _deterministic_question(flow, FIRST_SURVEY_STATE)
        if not question:
            return None
        return _plan(
            routing_state="consent_accepted",
            state=prev_state,
            next_state=next_state,
            direct_response=question,
            deterministic_question=question,
        )

    if next_state == DECLINED_STATE:
        response = _final_phrase(flow, DECLINED_STATE)
        if not response:
            return None
        return _plan(
            routing_state="consent_declined",
            state=prev_state,
            next_state=next_state,
            direct_response=response,
        )

    return None


def _plan(
    *,
    routing_state: str,
    state: str,
    next_state: str,
    direct_response: str = "",
    generator_required: bool = False,
    suffix: str = "",
    deterministic_question: str = "",
    final_phrase: str = "",
    company_answer_appended: bool = False,
) -> PilotSurveyResponsePlan:
    metadata = {
        "pilot_survey": True,
        "pilot_survey_state": state,
        "pilot_survey_next_state": next_state,
        "routing_state": routing_state,
        "deterministic_question": deterministic_question,
        "final_phrase": final_phrase,
        "company_answer_appended": company_answer_appended,
    }
    return PilotSurveyResponsePlan(
        routing_state=routing_state,
        state=state,
        next_state=next_state,
        direct_response=direct_response,
        generator_required=generator_required,
        suffix=suffix,
        metadata=metadata,
    )


def _latest_pilot_signal(signals: Sequence[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    for signal in reversed(list(signals or [])):
        if signal.get("source") == PILOT_SURVEY_SIGNAL_SOURCE:
            return dict(signal)
    return None


def _state_params(flow: Any, state: str) -> Dict[str, Any]:
    states = getattr(flow, "states", {}) or {}
    state_config = states.get(state, {}) if isinstance(states, dict) else {}
    if not isinstance(state_config, dict):
        return {}
    resolved = state_config.get("_resolved_params")
    if isinstance(resolved, dict):
        return resolved
    params = state_config.get("parameters")
    return params if isinstance(params, dict) else {}


def _deterministic_question(flow: Any, state: str) -> str:
    return str(_state_params(flow, state).get("deterministic_question") or "").strip()


def _final_phrase(flow: Any, state: str) -> str:
    return str(_state_params(flow, state).get("final_phrase") or "").strip()


def _clarify_text(state_params: Dict[str, Any]) -> str:
    answer_gate = state_params.get("answer_gate") if isinstance(state_params, dict) else {}
    if isinstance(answer_gate, dict):
        clarify = str(answer_gate.get("clarify") or "").strip()
        if clarify:
            return clarify
    return "Коротко уточните, пожалуйста, ответ на текущий вопрос."


def _is_company_answer_action(action: Any) -> bool:
    value = str(action or "").strip()
    if value in COMPANY_ANSWER_ACTIONS:
        return True
    return value.startswith(("answer_", "explain_", "compare_", "discuss_"))


def _current_question_suffix(
    *,
    transcript: Optional[DialogTranscript],
    state: str,
    question: str,
) -> str:
    if not question:
        return ""
    if _was_question_repeated_after_company_answer(transcript, state=state, question=question):
        return f"И вернусь к вопросу: {question}"
    return question


def _was_question_repeated_after_company_answer(
    transcript: Optional[DialogTranscript],
    *,
    state: str,
    question: str,
) -> bool:
    if transcript is None or not question:
        return False
    turns: Iterable[DialogTranscriptTurn] = transcript.recent_turns(8)
    for turn in reversed(list(turns)):
        metadata = dict(turn.metadata or {})
        if not metadata.get("pilot_survey"):
            continue
        if metadata.get("routing_state") != "company_question":
            continue
        if metadata.get("pilot_survey_state") != state:
            continue
        if metadata.get("deterministic_question") != question:
            continue
        if metadata.get("company_answer_appended"):
            return True
    return False
