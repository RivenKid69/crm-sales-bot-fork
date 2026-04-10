import pytest
from types import SimpleNamespace

from src.blackboard.blackboard import DialogueBlackboard
from src.blackboard.enums import Priority
from src.blackboard.orchestrator import DialogueOrchestrator
from src.blackboard.sources.pilot_survey_answer_gate import (
    PilotSurveyAnswerGateResult,
    PilotSurveyAnswerGateSource,
)
from src.bot import SalesBot
from src.config_loader import ConfigLoader
from src.dialog_transcript import DialogTranscript
from src.pilot_survey_response_plan import build_pilot_survey_response_plan
from src.state_machine import StateMachine


class FakeGateLLM:
    def __init__(self, *results):
        self.results = list(results)
        self.calls = []

    def generate_structured(self, *args, **kwargs):
        self.calls.append({"args": args, "kwargs": kwargs})
        if not self.results:
            return PilotSurveyAnswerGateResult(
                answer_accepted=False,
                confidence=0.95,
                reason="test_default",
            )
        return self.results.pop(0)


class FakeBotLLM(FakeGateLLM):
    def __init__(self, purpose_responses=None, *, purpose_errors=None):
        super().__init__()
        self.purpose_responses = dict(purpose_responses or {})
        self.purpose_errors = dict(purpose_errors or {})
        self.generate_calls = []

    def generate(self, *args, **kwargs):
        self.generate_calls.append({"args": args, "kwargs": kwargs})
        purpose = kwargs.get("purpose")
        if purpose in self.purpose_errors:
            raise self.purpose_errors[purpose]
        if purpose in self.purpose_responses:
            return self.purpose_responses[purpose]
        return "Короткий ответ по компании."


def _load_pilot_runtime():
    loader = ConfigLoader()
    config, flow = loader.load_bundle(flow_name="pilot_survey")
    state_machine = StateMachine(config=config, flow=flow)
    return config, flow, state_machine


def _blackboard(
    *,
    state: str = "survey_q1",
    intent: str = "info_provided",
    message: str = "Пилот запущен, сейчас проверяем основной сценарий.",
    secondary_intents=None,
):
    _, flow, state_machine = _load_pilot_runtime()
    state_machine.state = state
    state_machine.current_phase = flow.get_phase_for_state(state)
    bb = DialogueBlackboard(state_machine=state_machine, flow_config=flow)
    envelope = SimpleNamespace(
        secondary_intents=list(secondary_intents or []),
        repeated_question=None,
    )
    bb.begin_turn(
        intent=intent,
        extracted_data={},
        context_envelope=envelope,
        user_message=message,
    )
    return bb, flow, state_machine


def _latest_pilot_signal(bb):
    signals = bb.get_context_signals()
    assert signals
    return signals[-1]


def test_pilot_survey_flow_loads_with_consent_entrypoint():
    _, flow, state_machine = _load_pilot_runtime()

    assert flow.name == "pilot_survey"
    assert flow.get_entry_point("default") == "survey_consent"
    assert state_machine.state == "survey_consent"
    assert state_machine.current_phase == "survey"

    consent_transitions = flow.states["survey_consent"]["transitions"]
    assert consent_transitions["agreement"] == "survey_q1"
    assert consent_transitions["rejection"] == "survey_declined"
    assert consent_transitions["objection_think"] == "survey_declined"
    assert consent_transitions["objection_no_need"] == "survey_declined"
    assert flow.states["survey_declined"]["is_final"] is True

    q1_params = flow.states["survey_q1"]["_resolved_params"]
    assert q1_params["deterministic_question"].startswith("1/8.")
    assert flow.states["survey_complete"]["_resolved_params"]["final_phrase"]


def test_sales_bot_outbound_start_message_is_deterministic_and_not_a_turn():
    bot = SalesBot(
        llm=FakeBotLLM(
            purpose_responses={
                "pilot_survey_outbound_greeting_rewrite": (
                    "Добрый день! Вас приветствует отдел контроля качества Wipon.\n"
                    "Прошло 5 дней после активации онлайн-кассы в пилоте с Forte Bank, и я хочу убедиться, что всё работает стабильно, а подключение прошло комфортно.\n"
                    "Нам важно быстро проверить ваши первые шаги, чтобы система была удобной именно для вашего бизнеса.\n"
                    "Готовы уделить пару минут короткому блиц-опросу на 8 быстрых вопросов?"
                )
            }
        ),
        flow_name="pilot_survey",
    )

    message = bot.build_outbound_start_message()

    assert "отдел контроля качества Wipon" in message
    assert "5 дней" in message
    assert "Forte Bank" in message
    assert "8 быстрых вопросов" in message
    assert "1/8. Насколько легко было зарегистрировать кассу" not in message
    assert bot.state_machine.state == "survey_consent"
    assert len(bot.transcript) == 0


def test_sales_bot_outbound_start_message_falls_back_to_canonical_greeting_on_rewrite_failure():
    bot = SalesBot(
        llm=FakeBotLLM(
            purpose_errors={
                "pilot_survey_outbound_greeting_rewrite": RuntimeError("llm down")
            }
        ),
        flow_name="pilot_survey",
    )

    message = bot.build_outbound_start_message()

    assert "Вас приветствует отдел контроля качества Wipon." in message
    assert "С момента активации вашей онлайн-кассы с Forte Bank прошло 5 дней." in message
    assert "8 быстрых вопросов" in message
    assert "Вам сейчас удобно?" in message
    assert "1/8. Насколько легко было зарегистрировать кассу" not in message


def test_sales_bot_rewrites_pilot_survey_final_phrase_before_delivery():
    _, flow, _ = _load_pilot_runtime()
    signal = {
        "source": "pilot_survey_answer_gate",
        "state": "survey_q8",
        "routing_state": "survey_answer",
        "answer_accepted": True,
    }

    plan = build_pilot_survey_response_plan(
        flow=flow,
        sm_result={"next_state": "survey_complete"},
        context_signals=[signal],
        transcript=DialogTranscript(),
        action="continue_current_goal",
    )
    bot = SalesBot(
        llm=FakeBotLLM(
            purpose_responses={
                "pilot_survey_final_phrase_rewrite": "Благодарю вас за ответы!"
            }
        ),
        flow_name="pilot_survey",
    )

    delivered = bot._prepare_pilot_survey_response_plan_for_delivery(plan)
    composed = delivered.compose()

    assert composed == "Благодарю вас за ответы!"


def test_sales_bot_strips_trailing_follow_up_question_from_company_answer():
    text = (
        "Стоимость программы составляет 150 000 тенге в год за Lite и 220 000 тенге за Standard. "
        "Какой функционал будет для вас наиболее приоритетным?"
    )

    cleaned = SalesBot._strip_pilot_survey_follow_up_questions(text)

    assert "150 000 тенге" in cleaned
    assert "220 000 тенге" in cleaned
    assert "приоритетным?" not in cleaned
    assert not cleaned.endswith("?")


def test_sales_bot_keeps_company_answer_without_follow_up_question():
    text = "Стоимость программы составляет 150 000 тенге в год за Lite и 220 000 тенге за Standard."

    cleaned = SalesBot._strip_pilot_survey_follow_up_questions(text)

    assert cleaned == text


def test_sales_bot_outbound_start_message_fails_fast_after_first_turn():
    bot = SalesBot(llm=FakeBotLLM(), flow_name="pilot_survey")
    bot.transcript.append_turn_internal(
        user_text="Пилот уже идёт.",
        bot_text="2/8. Получили ли вы инструкцию по настройке? Была ли она понятна и достаточна?",
        intent="info_provided",
        state="survey_q1",
        action="continue_current_goal",
    )

    with pytest.raises(RuntimeError, match="only before the first committed turn"):
        bot.build_outbound_start_message()


def test_answer_gate_abstains_on_consent_state():
    bb, _, _ = _blackboard(
        state="survey_consent",
        intent="agreement",
        message="Да, удобно.",
    )
    source = PilotSurveyAnswerGateSource(llm=FakeGateLLM())

    assert source.should_contribute(bb) is False


def test_answer_gate_accepts_survey_answer_and_proposes_answer_accepted_transition():
    bb, _, _ = _blackboard()
    source = PilotSurveyAnswerGateSource(
        llm=FakeGateLLM(
            PilotSurveyAnswerGateResult(
                answer_accepted=True,
                confidence=0.91,
                reason="status_answered",
            )
        )
    )

    assert source.should_contribute(bb) is True
    source.contribute(bb)

    signal = _latest_pilot_signal(bb)
    transitions = bb.get_transition_proposals()
    assert signal["routing_state"] == "survey_answer"
    assert signal["answer_accepted"] is True
    assert signal["company_question_present"] is False
    assert len(transitions) == 1
    assert transitions[0].value == "survey_q2"
    assert transitions[0].priority == Priority.NORMAL


def test_answer_gate_falls_back_to_heuristic_when_llm_verdict_is_uninformative():
    bb, _, _ = _blackboard(
        message="В целом зарегистрировать кассу и подключить систему было легко, только шаг с подтверждением кассы сначала был непонятен.",
    )
    source = PilotSurveyAnswerGateSource(
        llm=FakeGateLLM(
            PilotSurveyAnswerGateResult(
                answer_accepted=False,
                confidence=0.0,
                reason="",
            )
        )
    )

    source.contribute(bb)

    signal = _latest_pilot_signal(bb)
    transitions = bb.get_transition_proposals()
    assert signal["routing_state"] == "survey_answer"
    assert signal["answer_accepted"] is True
    assert signal["reason"] == "heuristic_informative_message"
    assert len(transitions) == 1
    assert transitions[0].value == "survey_q2"


def test_answer_gate_company_question_stays_on_current_survey_state():
    bb, _, _ = _blackboard(
        intent="price_question",
        message="Сколько стоит продукт?",
    )
    bb.propose_action(
        action="answer_with_pricing",
        priority=Priority.HIGH,
        combinable=True,
        reason_code="price_question",
        source_name="PriceQuestionSource",
    )
    source = PilotSurveyAnswerGateSource(
        llm=FakeGateLLM(
            PilotSurveyAnswerGateResult(
                answer_accepted=False,
                confidence=0.93,
                reason="not_a_survey_answer",
            )
        )
    )

    source.contribute(bb)

    signal = _latest_pilot_signal(bb)
    assert signal["routing_state"] == "company_question"
    assert signal["answer_accepted"] is False
    assert signal["company_question_present"] is True
    assert signal["company_question_action_present"] is True
    assert bb.get_transition_proposals() == []


def test_answer_gate_mixed_combines_company_answer_with_survey_transition():
    bb, _, _ = _blackboard(
        intent="info_provided",
        message="Пилот запущен. И сколько стоит продукт после пилота?",
        secondary_intents=["price_question"],
    )
    bb.propose_action(
        action="answer_with_pricing",
        priority=Priority.HIGH,
        combinable=True,
        reason_code="price_question",
        source_name="PriceQuestionSource",
    )
    source = PilotSurveyAnswerGateSource(
        llm=FakeGateLLM(
            PilotSurveyAnswerGateResult(
                answer_accepted=True,
                confidence=0.89,
                reason="status_plus_price",
            )
        )
    )

    source.contribute(bb)

    signal = _latest_pilot_signal(bb)
    transitions = bb.get_transition_proposals()
    assert signal["routing_state"] == "mixed"
    assert signal["answer_accepted"] is True
    assert signal["company_question_present"] is True
    assert len(transitions) == 1
    assert transitions[0].value == "survey_q2"


def test_answer_gate_fails_closed_when_company_intent_lacks_company_action():
    bb, _, _ = _blackboard(
        intent="price_question",
        message="Сколько стоит продукт?",
    )
    source = PilotSurveyAnswerGateSource(
        llm=FakeGateLLM(
            PilotSurveyAnswerGateResult(
                answer_accepted=True,
                confidence=0.91,
                reason="ambiguous_price_turn",
            )
        )
    )

    source.contribute(bb)

    signal = _latest_pilot_signal(bb)
    assert signal["routing_state"] == "unclear"
    assert signal["answer_accepted"] is False
    assert signal["company_question_present"] is True
    assert signal["company_question_action_present"] is False
    assert "company_question_action_missing" in signal["reason"]
    assert bb.get_transition_proposals() == []


def test_response_plan_consent_acceptance_returns_first_question_without_generator():
    _, flow, _ = _load_pilot_runtime()

    plan = build_pilot_survey_response_plan(
        flow=flow,
        sm_result={"prev_state": "survey_consent", "next_state": "survey_q1"},
        context_signals=[],
        transcript=DialogTranscript(),
        action="acknowledge_and_continue",
    )

    assert plan is not None
    assert plan.routing_state == "consent_accepted"
    assert plan.generator_required is False
    assert plan.compose().startswith("1/8.")


def test_response_plan_consent_rejection_returns_declined_final_without_generator():
    _, flow, _ = _load_pilot_runtime()

    plan = build_pilot_survey_response_plan(
        flow=flow,
        sm_result={"prev_state": "survey_consent", "next_state": "survey_declined"},
        context_signals=[],
        transcript=DialogTranscript(),
        action="acknowledge_rejection",
    )

    assert plan is not None
    assert plan.routing_state == "consent_declined"
    assert plan.generator_required is False
    assert plan.compose() == "Хорошо, спасибо. Мы свяжемся с вами позже."


def test_orchestrator_consent_acceptance_enters_first_survey_question():
    config, flow, state_machine = _load_pilot_runtime()
    orchestrator = DialogueOrchestrator(
        state_machine=state_machine,
        flow_config=flow,
        llm=FakeGateLLM(),
    )
    envelope = SimpleNamespace(
        secondary_intents=[],
        secondary_intent_confidence={},
        repeated_question=None,
        intent_confidence=0.95,
        last_user_message="Да, удобно.",
    )

    decision = orchestrator.process_turn(
        intent="agreement",
        extracted_data={},
        context_envelope=envelope,
        user_message="Да, удобно.",
    )

    assert decision.next_state == "survey_q1"
    assert decision.prev_state == "survey_consent"


def test_orchestrator_consent_callback_request_finishes_without_survey_questions():
    config, flow, state_machine = _load_pilot_runtime()
    orchestrator = DialogueOrchestrator(
        state_machine=state_machine,
        flow_config=flow,
        llm=FakeGateLLM(),
    )
    envelope = SimpleNamespace(
        secondary_intents=[],
        secondary_intent_confidence={},
        repeated_question=None,
        intent_confidence=0.95,
        last_user_message="Нет, давайте позже.",
    )

    decision = orchestrator.process_turn(
        intent="callback_request",
        extracted_data={},
        context_envelope=envelope,
        user_message="Нет, давайте позже.",
    )

    assert decision.next_state == "survey_declined"
    assert decision.prev_state == "survey_consent"
    assert decision.is_final is True


def test_response_plan_survey_answer_returns_next_question_without_generator():
    _, flow, _ = _load_pilot_runtime()
    signal = {
        "source": "pilot_survey_answer_gate",
        "state": "survey_q1",
        "routing_state": "survey_answer",
        "answer_accepted": True,
    }

    plan = build_pilot_survey_response_plan(
        flow=flow,
        sm_result={"next_state": "survey_q2"},
        context_signals=[signal],
        transcript=DialogTranscript(),
        action="continue_current_goal",
    )

    assert plan is not None
    assert plan.generator_required is False
    assert plan.compose().startswith("2/8.")


def test_response_plan_survey_answer_last_question_returns_final_phrase_without_generator():
    _, flow, _ = _load_pilot_runtime()
    signal = {
        "source": "pilot_survey_answer_gate",
        "state": "survey_q8",
        "routing_state": "survey_answer",
        "answer_accepted": True,
    }

    plan = build_pilot_survey_response_plan(
        flow=flow,
        sm_result={"next_state": "survey_complete"},
        context_signals=[signal],
        transcript=DialogTranscript(),
        action="continue_current_goal",
    )

    assert plan is not None
    assert plan.generator_required is False
    assert plan.compose() == "Спасибо за ваши ответы!"


def test_response_plan_company_question_repeats_current_question_then_soft_bridge():
    _, flow, _ = _load_pilot_runtime()
    signal = {
        "source": "pilot_survey_answer_gate",
        "state": "survey_q2",
        "routing_state": "company_question",
        "answer_accepted": False,
    }
    transcript = DialogTranscript()

    first_plan = build_pilot_survey_response_plan(
        flow=flow,
        sm_result={"next_state": "survey_q2"},
        context_signals=[signal],
        transcript=transcript,
        action="answer_with_pricing",
    )
    assert first_plan is not None
    assert first_plan.generator_required is True
    assert first_plan.suffix.startswith("2/8.")

    transcript.append_turn_internal(
        user_text="Сколько стоит?",
        bot_text=first_plan.compose("Ответ по цене."),
        intent="price_question",
        state="survey_q2",
        action="answer_with_pricing",
        source_branch="pilot_survey_response",
        metadata=first_plan.metadata,
    )
    second_plan = build_pilot_survey_response_plan(
        flow=flow,
        sm_result={"next_state": "survey_q2"},
        context_signals=[signal],
        transcript=transcript,
        action="answer_with_pricing",
    )

    assert second_plan is not None
    assert second_plan.suffix.startswith("И вернусь к вопросу: 2/8.")


def test_response_plan_mixed_last_question_appends_final_phrase():
    _, flow, _ = _load_pilot_runtime()
    signal = {
        "source": "pilot_survey_answer_gate",
        "state": "survey_q8",
        "routing_state": "mixed",
        "answer_accepted": True,
    }

    plan = build_pilot_survey_response_plan(
        flow=flow,
        sm_result={"next_state": "survey_complete"},
        context_signals=[signal],
        transcript=DialogTranscript(),
        action="answer_with_facts",
    )

    assert plan is not None
    assert plan.generator_required is True
    assert "Спасибо за ваши ответы!" in plan.compose("Ответ по компании.")
    assert "8/8." not in plan.suffix


def test_response_plan_unclear_uses_deterministic_clarify_without_transition():
    _, flow, _ = _load_pilot_runtime()
    signal = {
        "source": "pilot_survey_answer_gate",
        "state": "survey_q4",
        "routing_state": "unclear",
        "answer_accepted": False,
    }

    plan = build_pilot_survey_response_plan(
        flow=flow,
        sm_result={"next_state": "survey_q4"},
        context_signals=[signal],
        transcript=DialogTranscript(),
        action="continue_current_goal",
    )

    assert plan is not None
    assert plan.generator_required is False
    assert "кто сейчас использует терминал" in plan.compose()


def test_orchestrator_company_question_in_pilot_survey_keeps_state_and_returns_pricing_action():
    config, flow, state_machine = _load_pilot_runtime()
    state_machine.state = "survey_q1"
    state_machine.current_phase = flow.get_phase_for_state("survey_q1")
    orchestrator = DialogueOrchestrator(
        state_machine=state_machine,
        flow_config=flow,
        llm=FakeGateLLM(
            PilotSurveyAnswerGateResult(
                answer_accepted=False,
                confidence=0.94,
                reason="pure_company_question",
            )
        ),
    )
    envelope = SimpleNamespace(
        secondary_intents=[],
        secondary_intent_confidence={},
        repeated_question=None,
        intent_confidence=0.95,
        last_user_message="Сколько стоит продукт?",
    )

    decision = orchestrator.process_turn(
        intent="price_question",
        extracted_data={},
        context_envelope=envelope,
        user_message="Сколько стоит продукт?",
    )

    signal = orchestrator.blackboard.get_context_signals()[-1]
    assert decision.action == "answer_with_pricing"
    assert decision.next_state == "survey_q1"
    assert signal["source"] == "pilot_survey_answer_gate"
    assert signal["routing_state"] == "company_question"


def test_orchestrator_mixed_turn_in_pilot_survey_combines_company_answer_and_transition():
    config, flow, state_machine = _load_pilot_runtime()
    state_machine.state = "survey_q1"
    state_machine.current_phase = flow.get_phase_for_state("survey_q1")
    orchestrator = DialogueOrchestrator(
        state_machine=state_machine,
        flow_config=flow,
        llm=FakeGateLLM(
            PilotSurveyAnswerGateResult(
                answer_accepted=True,
                confidence=0.91,
                reason="mixed_turn",
            )
        ),
    )
    envelope = SimpleNamespace(
        secondary_intents=["price_question"],
        secondary_intent_confidence={"price_question": 0.9},
        repeated_question=None,
        intent_confidence=0.93,
        last_user_message="Пилот уже запущен. Сколько стоит продукт после пилота?",
    )

    decision = orchestrator.process_turn(
        intent="info_provided",
        extracted_data={},
        context_envelope=envelope,
        user_message="Пилот уже запущен. Сколько стоит продукт после пилота?",
    )

    signal = orchestrator.blackboard.get_context_signals()[-1]
    assert decision.action == "answer_with_pricing"
    assert decision.next_state == "survey_q2"
    assert signal["source"] == "pilot_survey_answer_gate"
    assert signal["routing_state"] == "mixed"
