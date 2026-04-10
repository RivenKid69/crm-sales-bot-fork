"""Semantic answer gate for the deterministic pilot survey flow."""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, Iterable, Literal, Optional, Set, TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from ..enums import Priority
from ..knowledge_source import KnowledgeSource
from src.yaml_config.constants import INTENT_CATEGORIES, get_fact_question_source_config

if TYPE_CHECKING:
    from ..blackboard import DialogueBlackboard

logger = logging.getLogger(__name__)


PILOT_SURVEY_SIGNAL_SOURCE = "pilot_survey_answer_gate"
ANSWER_ACCEPTED_TRANSITION = "answer_accepted"
DEFAULT_MIN_CONFIDENCE = 0.70

GATE_ABSTAIN_INTENTS = frozenset({
    "end_conversation",
    "farewell",
    "request_human",
})

COMPANY_QUESTION_ACTION_SOURCES = frozenset({
    "PriceQuestionSource",
    "FactQuestionSource",
})

_COMPANY_QUESTION_CUE_RE = re.compile(
    r"\?|(?:^|\s)(?:как|какие|какой|какая|что|где|когда|почему|зачем|"
    r"сколько|расскажите|подскажите|объясните|можете|можно\s+ли|есть\s+ли|"
    r"сколько\s+стоит|цена|стоимость|тариф)(?:\s|$)",
    re.IGNORECASE,
)


class PilotSurveyAnswerGateResult(BaseModel):
    """Structured LLM verdict for whether the current survey question is answered."""

    model_config = ConfigDict(extra="forbid")

    verdict: Literal["valid", "invalid"] = Field(
        ...,
        description="valid when the client message closes the current survey question; invalid otherwise",
    )
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    reason: str = ""

    @model_validator(mode="before")
    @classmethod
    def _map_legacy_answer_accepted(cls, data: Any) -> Any:
        if isinstance(data, dict) and "verdict" not in data and "answer_accepted" in data:
            migrated = dict(data)
            migrated["verdict"] = "valid" if migrated.pop("answer_accepted") else "invalid"
            return migrated
        return data

    @property
    def answer_accepted(self) -> bool:
        return self.verdict == "valid"


class PilotSurveyAnswerGateSource(KnowledgeSource):
    """
    Decides whether a user message semantically answers the current survey question.

    The source does not extract business fields and does not generate user-facing text.
    It emits a turn-local context signal and, when accepted, proposes the
    deterministic `transitions.answer_accepted` state transition.
    """

    def __init__(self, llm: Any = None, name: str = "PilotSurveyAnswerGateSource"):
        super().__init__(name)
        self._llm = llm
        self._company_question_intents = self._load_company_question_intents()

    @staticmethod
    def _load_company_question_intents() -> Set[str]:
        price_intents = set(INTENT_CATEGORIES.get("price_related", []) or [])
        fact_cfg = get_fact_question_source_config()
        fact_intents = set(fact_cfg.get("fact_intents", []) or [])
        if not fact_intents:
            try:
                from src.blackboard.sources.fact_question import FactQuestionSource

                fact_intents = set(FactQuestionSource.DEFAULT_FACT_INTENTS)
            except Exception:
                fact_intents = set(INTENT_CATEGORIES.get("all_questions", []) or [])
        return price_intents | fact_intents

    @staticmethod
    def _flow_name(ctx: Any) -> str:
        flow_config = getattr(ctx, "flow_config", {})
        if isinstance(flow_config, dict):
            return str(flow_config.get("name", "") or "")
        return str(getattr(flow_config, "name", "") or "")

    @staticmethod
    def _state_params(state_config: Any) -> Dict[str, Any]:
        if not isinstance(state_config, dict):
            return {}
        resolved = state_config.get("_resolved_params")
        if isinstance(resolved, dict):
            return resolved
        params = state_config.get("parameters")
        return params if isinstance(params, dict) else {}

    def should_contribute(self, blackboard: "DialogueBlackboard") -> bool:
        if not self._enabled:
            return False

        ctx = blackboard.get_context()
        if self._flow_name(ctx) != "pilot_survey":
            return False

        params = self._state_params(ctx.state_config)
        return bool(params.get("deterministic_question") and isinstance(params.get("answer_gate"), dict))

    def contribute(self, blackboard: "DialogueBlackboard") -> None:
        ctx = blackboard.get_context()
        params = self._state_params(ctx.state_config)
        answer_gate = params.get("answer_gate") if isinstance(params.get("answer_gate"), dict) else {}
        question = str(params.get("deterministic_question") or "").strip()
        if not question or not answer_gate:
            self._log_contribution(reason="pilot_survey state lacks deterministic question or answer_gate")
            return

        turn_intents = self._turn_intents(ctx)
        if turn_intents & GATE_ABSTAIN_INTENTS:
            self._log_contribution(
                reason=f"hard-stop intent present: {sorted(turn_intents & GATE_ABSTAIN_INTENTS)}"
            )
            return

        company_question_present = self._has_company_question_intent(ctx, turn_intents)
        company_action_present = self._has_company_question_action(blackboard)

        verdict = self._evaluate_answer(
            ctx=ctx,
            question=question,
            answer_gate=answer_gate,
            turn_intents=turn_intents,
        )
        min_confidence = self._min_confidence(answer_gate)
        answer_accepted = verdict.answer_accepted and verdict.confidence >= min_confidence
        reason = verdict.reason or "semantic_gate"

        if company_question_present and not company_action_present:
            answer_accepted = False
            reason = f"{reason}; company_question_action_missing"

        next_state = ctx.get_transition(ANSWER_ACCEPTED_TRANSITION)
        if answer_accepted and not next_state:
            answer_accepted = False
            reason = f"{reason}; missing_answer_accepted_transition"

        routing_state = self._routing_state(
            answer_accepted=answer_accepted,
            company_question_present=company_question_present,
        )
        if company_question_present and not company_action_present:
            routing_state = "unclear"

        signal = {
            "source": PILOT_SURVEY_SIGNAL_SOURCE,
            "state": ctx.state,
            "routing_state": routing_state,
            "answer_accepted": answer_accepted,
            "company_question_present": company_question_present,
            "company_question_action_present": company_action_present,
            "confidence": verdict.confidence,
            "min_confidence": min_confidence,
            "reason": reason[:240],
        }
        blackboard.add_context_signal(PILOT_SURVEY_SIGNAL_SOURCE, signal)

        if answer_accepted and next_state:
            blackboard.propose_transition(
                next_state=next_state,
                priority=Priority.NORMAL,
                reason_code="pilot_survey_answer_accepted",
                source_name=self.name,
                metadata=signal,
            )
            self._log_contribution(
                transition=next_state,
                reason=f"{routing_state}: {reason}",
            )
            return

        self._log_contribution(reason=f"{routing_state}: {reason}")

    def _evaluate_answer(
        self,
        *,
        ctx: Any,
        question: str,
        answer_gate: Dict[str, Any],
        turn_intents: Set[str],
    ) -> PilotSurveyAnswerGateResult:
        user_message = str(getattr(ctx, "user_message", "") or "")
        llm_result = self._evaluate_with_llm(
            user_message=user_message,
            question=question,
            answer_gate=answer_gate,
            turn_intents=turn_intents,
        )
        if llm_result is not None:
            return llm_result
        return PilotSurveyAnswerGateResult(
            verdict="invalid",
            confidence=0.0,
            reason="llm_verdict_unavailable",
        )

    def _evaluate_with_llm(
        self,
        *,
        user_message: str,
        question: str,
        answer_gate: Dict[str, Any],
        turn_intents: Set[str],
    ) -> Optional[PilotSurveyAnswerGateResult]:
        generate_structured = getattr(self._llm, "generate_structured", None)
        if not callable(generate_structured):
            return None

        intents_hint = ", ".join(sorted(str(intent) for intent in turn_intents if intent)) or "none"
        prompt = (
            "Ты semantic gate для детерминированного опроса по пилоту.\n"
            "Твоя задача: определить, можно ли считать текущий survey-вопрос закрытым.\n"
            "Не отвечай клиенту. Не извлекай поля.\n"
            "Верни строго JSON object по schema. Не возвращай scalar string.\n"
            'Правильно: {"verdict":"valid"}. Неправильно: valid.\n\n'
            "Verdict values:\n"
            "- valid: сообщение клиента отвечает на текущий survey-вопрос и закрывает его.\n"
            "- invalid: сообщение клиента не отвечает на текущий survey-вопрос.\n\n"
            "Короткие ответы вроде 'да' и 'нет' оценивай относительно текущего survey-вопроса.\n"
            "Не считай короткое 'да/нет' автоматическим согласием или отказом от разговора.\n"
            "Считай ответ invalid только если клиент явно не отвечает по смыслу, "
            "или прямо отказывается продолжать опрос/разговор, просит завершить или передать человеку.\n\n"
            f"Survey question:\n{question}\n\n"
            f"Valid if:\n{answer_gate.get('valid_if', '')}\n\n"
            f"Invalid if:\n{answer_gate.get('invalid_if', '')}\n\n"
            f"Detected intents for this turn:\n{intents_hint}\n\n"
            "Если в сообщении есть и ответ на survey-вопрос, и отдельный вопрос о компании, "
            "оценивай только наличие ответа на survey-вопрос.\n\n"
            f"Client message:\n{user_message}\n"
        )

        try:
            raw = generate_structured(
                prompt=prompt,
                schema=PilotSurveyAnswerGateResult,
                purpose="pilot_survey_answer_gate",
                temperature=0.0,
                num_predict=256,
            )
        except TypeError:
            try:
                raw = generate_structured(prompt, PilotSurveyAnswerGateResult)
            except Exception:
                logger.debug("PilotSurveyAnswerGateSource LLM call failed", exc_info=True)
                return None
        except Exception:
            logger.debug("PilotSurveyAnswerGateSource LLM call failed", exc_info=True)
            return None

        if isinstance(raw, tuple):
            raw = raw[0]
        if isinstance(raw, PilotSurveyAnswerGateResult):
            return raw
        if isinstance(raw, dict):
            try:
                return PilotSurveyAnswerGateResult.model_validate(raw)
            except ValidationError:
                return None
        return None

    @staticmethod
    def _min_confidence(answer_gate: Dict[str, Any]) -> float:
        raw = answer_gate.get("min_confidence", DEFAULT_MIN_CONFIDENCE)
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return DEFAULT_MIN_CONFIDENCE
        if value < 0.0 or value > 1.0:
            return DEFAULT_MIN_CONFIDENCE
        return value

    def _turn_intents(self, ctx: Any) -> Set[str]:
        intents: Set[str] = set()
        current = getattr(ctx, "current_intent", "")
        if current:
            intents.add(str(current))

        envelope = getattr(ctx, "context_envelope", None)
        secondary = getattr(envelope, "secondary_intents", None) if envelope else None
        if isinstance(secondary, Iterable) and not isinstance(secondary, (str, bytes)):
            intents.update(str(intent) for intent in secondary if intent)

        repeated_question = getattr(envelope, "repeated_question", None) if envelope else None
        if repeated_question:
            intents.add(str(repeated_question))

        return intents

    def _has_company_question_intent(self, ctx: Any, turn_intents: Set[str]) -> bool:
        if not (turn_intents & self._company_question_intents):
            return False
        envelope = getattr(ctx, "context_envelope", None)
        frame = getattr(envelope, "semantic_frame", None) if envelope else None
        if isinstance(frame, dict) and frame.get("has_question") is True:
            return True
        user_message = str(getattr(ctx, "user_message", "") or "")
        return bool(_COMPANY_QUESTION_CUE_RE.search(user_message))

    @staticmethod
    def _has_company_question_action(blackboard: "DialogueBlackboard") -> bool:
        return any(
            proposal.source_name in COMPANY_QUESTION_ACTION_SOURCES
            for proposal in blackboard.get_action_proposals()
        )

    @staticmethod
    def _routing_state(*, answer_accepted: bool, company_question_present: bool) -> str:
        if answer_accepted and company_question_present:
            return "mixed"
        if answer_accepted:
            return "survey_answer"
        if company_question_present:
            return "company_question"
        return "unclear"
