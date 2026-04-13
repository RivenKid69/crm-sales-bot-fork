import pytest
from types import SimpleNamespace

from src.blackboard.blackboard import DialogueBlackboard
from src.blackboard.enums import Priority
from src.blackboard.orchestrator import DialogueOrchestrator
from src.blackboard.orchestrator import create_orchestrator
from src.blackboard.sources.pilot_survey_answer_gate import (
    PilotSurveyAnswerGateResult,
    PilotSurveyAnswerGateSource,
)
from src.bot import SalesBot
from src.config_loader import ConfigLoader
from src.conversation_guard import ConversationGuard
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


def _mock_bot_classification(intent: str = "info_provided"):
    return {
        "intent": intent,
        "extracted_data": {},
        "confidence": 0.95,
        "method": "mock",
        "style_modifiers": [],
        "secondary_signals": [],
        "semantic_frame": {},
        "style_separation_applied": False,
    }


def _mock_disambiguation_needed_classification():
    return {
        "intent": "disambiguation_needed",
        "confidence": 0.52,
        "extracted_data": {},
        "method": "mock",
        "reasoning": "agreement vs no_problem",
        "alternatives": [],
        "disambiguation_options": [
            {"intent": "agreement", "label": "Продолжить разговор", "confidence": 0.52},
            {"intent": "no_problem", "label": "Проблем нет", "confidence": 0.48},
            {"intent": "other", "label": "Другое", "confidence": 0.0},
        ],
        "disambiguation_question": "Уточните, пожалуйста:",
        "original_intent": "agreement",
        "original_scores": {"agreement": 0.52, "no_problem": 0.48},
    }


def _mock_bot_tone():
    return {
        "tone": "neutral",
        "frustration_level": 0,
        "tone_instruction": "",
        "style_instruction": "",
        "should_apologize": False,
        "should_offer_exit": False,
    }


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


def _create_pilot_orchestrator(*, state_machine, flow, config, llm):
    return create_orchestrator(
        state_machine=state_machine,
        flow_config=flow,
        llm=llm,
        blackboard_config=config.blackboard,
    )


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


def test_sales_bot_keeps_forced_support_redirect_and_continues_pilot_survey():
    llm = FakeBotLLM()
    llm.results = [
        PilotSurveyAnswerGateResult(
            verdict="valid",
            confidence=0.95,
            reason="survey_q3_answered",
        )
    ]
    bot = SalesBot(llm=llm, flow_name="pilot_survey")
    bot.transcript.append_turn_internal(
        user_text="Да, инструкцию получил.",
        bot_text="3/8. Обращались ли вы в техподдержку во время настройки? По какому вопросу?",
        intent="info_provided",
        state="survey_q2",
        action="continue_current_goal",
    )
    bot.state_machine.state = "survey_q3"
    bot.state_machine.current_phase = "survey"
    bot.last_bot_message = (
        "3/8. Обращались ли вы в техподдержку во время настройки? По какому вопросу?"
    )

    bot.classifier.classify = lambda *_args, **_kwargs: _mock_bot_classification(
        "misroute_technical_support"
    )
    bot._analyze_tone = lambda *_args, **_kwargs: _mock_bot_tone()

    result = bot.process("Да, обращался, но мне не ответили.")

    assert result["action"] == "redirect_misroute_technical_support"
    assert result["state"] == "survey_q4"
    assert result["response"] == (
        "Извините за неудобства. Вы обратились в отдел продаж. "
        "Пожалуйста, свяжитесь с технической поддержкой: +77070202019.\n\n"
        "4/8. Кто использует терминал: сам владелец или кассиры? "
        "Добавляли ли сотрудников через веб-кабинет?"
    )


def test_sales_bot_aged_pilot_survey_session_continues_after_valid_answer(monkeypatch):
    llm = FakeBotLLM()
    llm.results = [
        PilotSurveyAnswerGateResult(
            verdict="valid",
            confidence=0.95,
            reason="survey_q7_answered_after_restore",
        )
    ]
    bot = SalesBot(llm=llm, flow_name="pilot_survey")
    bot.transcript.append_turn_internal(
        user_text="Да, первую продажу провели.",
        bot_text="7/8. Добавляли ли товары и категории в каталог? Было ли это удобно и понятно?",
        intent="info_provided",
        state="survey_q6",
        action="continue_current_goal",
    )
    bot.state_machine.state = "survey_q7"
    bot.state_machine.current_phase = "survey"
    bot.last_bot_message = (
        "7/8. Добавляли ли товары и категории в каталог? Было ли это удобно и понятно?"
    )

    aged_guard_snapshot = bot.guard.to_dict()
    aged_guard_snapshot["elapsed_seconds"] = 31 * 60
    aged_guard = ConversationGuard.from_dict(
        aged_guard_snapshot,
        config=bot.guard.config,
    )
    bot.guard = aged_guard
    guard_source = bot._orchestrator.get_source("ConversationGuardSource")
    assert guard_source is not None
    guard_source._guard = aged_guard

    monkeypatch.setattr(
        bot.classifier,
        "classify",
        lambda *_args, **_kwargs: _mock_bot_classification(),
    )
    monkeypatch.setattr(bot, "_analyze_tone", lambda *_args, **_kwargs: _mock_bot_tone())

    result = bot.process("нет было непонятно")

    assert result["action"] == "continue_current_goal"
    assert result["state"] == "survey_q8"
    assert result["response"] == (
        "8/8. Возникали ли ошибки или зависания при проведении оплаты?"
    )


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


def test_answer_gate_accepts_required_verdict_payload_from_llm():
    bb, _, _ = _blackboard(
        message="Было легко, проблем не было.",
    )
    source = PilotSurveyAnswerGateSource(llm=FakeGateLLM({"verdict": "valid"}))

    source.contribute(bb)

    signal = _latest_pilot_signal(bb)
    transitions = bb.get_transition_proposals()
    prompt = source._llm.calls[0]["kwargs"]["prompt"]
    assert signal["routing_state"] == "survey_answer"
    assert signal["answer_accepted"] is True
    assert signal["reason"] == "semantic_gate"
    assert "Верни строго JSON object" in prompt
    assert "Неправильно: valid" in prompt
    assert len(transitions) == 1
    assert transitions[0].value == "survey_q2"


def test_answer_gate_evaluates_rejection_labeled_binary_reply_as_survey_answer():
    bb, _, _ = _blackboard(
        state="survey_q2",
        intent="rejection",
        message="Нет",
    )
    source = PilotSurveyAnswerGateSource(
        llm=FakeGateLLM(
            PilotSurveyAnswerGateResult(
                verdict="valid",
                confidence=0.92,
                reason="binary_no_answer",
            )
        )
    )

    source.contribute(bb)

    signal = _latest_pilot_signal(bb)
    transitions = bb.get_transition_proposals()
    prompt = source._llm.calls[0]["kwargs"]["prompt"]
    assert signal["routing_state"] == "survey_answer"
    assert signal["answer_accepted"] is True
    assert len(transitions) == 1
    assert transitions[0].value == "survey_q3"
    assert "Не считай короткое 'да/нет'" in prompt


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


def test_answer_gate_ignores_company_intent_without_question_cue_for_survey_answer():
    bb, _, _ = _blackboard(
        intent="question_support",
        message="Да, было легко зарегистрировать кассу и подключить систему тоже было легко!",
    )
    bb.propose_action(
        action="explain_support_options",
        priority=Priority.HIGH,
        combinable=True,
        reason_code="fact_question_detected",
        source_name="FactQuestionSource",
    )
    source = PilotSurveyAnswerGateSource(
        llm=FakeGateLLM(
            PilotSurveyAnswerGateResult(
                verdict="valid",
                confidence=1.0,
                reason="q1_answer",
            )
        )
    )

    source.contribute(bb)

    signal = _latest_pilot_signal(bb)
    transitions = bb.get_transition_proposals()
    assert signal["routing_state"] == "survey_answer"
    assert signal["answer_accepted"] is True
    assert signal["company_question_present"] is False
    assert len(transitions) == 1
    assert transitions[0].value == "survey_q2"


def test_answer_gate_marks_declarative_company_request_as_mixed_when_llm_flags_it():
    bb, _, _ = _blackboard(
        state="survey_q2",
        intent="info_provided",
        message="Да, инструкция была понятна. Нужна интеграция с 1С",
        secondary_intents=["question_1c_integration"],
    )
    bb.propose_action(
        action="answer_with_facts",
        priority=Priority.HIGH,
        combinable=True,
        reason_code="fact_question_detected",
        source_name="FactQuestionSource",
    )
    source = PilotSurveyAnswerGateSource(
        llm=FakeGateLLM(
            PilotSurveyAnswerGateResult(
                verdict="valid",
                confidence=0.95,
                company_question_present=True,
                reason="survey_answer_with_fact_request",
            )
        )
    )

    source.contribute(bb)

    signal = _latest_pilot_signal(bb)
    transitions = bb.get_transition_proposals()
    assert signal["routing_state"] == "mixed"
    assert signal["answer_accepted"] is True
    assert signal["company_question_present"] is True
    assert signal["company_question_action_present"] is True
    assert len(transitions) == 1
    assert transitions[0].value == "survey_q3"


def test_answer_gate_marks_declarative_company_request_as_company_question_without_survey_answer():
    bb, _, _ = _blackboard(
        state="survey_q2",
        intent="info_provided",
        message="Мне нужна интеграция с 1С",
        secondary_intents=["question_1c_integration"],
    )
    bb.propose_action(
        action="answer_with_facts",
        priority=Priority.HIGH,
        combinable=True,
        reason_code="fact_question_detected",
        source_name="FactQuestionSource",
    )
    source = PilotSurveyAnswerGateSource(
        llm=FakeGateLLM(
            PilotSurveyAnswerGateResult(
                verdict="invalid",
                confidence=0.95,
                company_question_present=True,
                reason="pure_fact_request",
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
    orchestrator = _create_pilot_orchestrator(
        state_machine=state_machine,
        flow=flow,
        config=config,
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
    orchestrator = _create_pilot_orchestrator(
        state_machine=state_machine,
        flow=flow,
        config=config,
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


def test_response_plan_unclear_with_acknowledge_and_continue_still_returns_clarify():
    _, flow, _ = _load_pilot_runtime()
    signal = {
        "source": "pilot_survey_answer_gate",
        "state": "survey_q2",
        "routing_state": "unclear",
        "answer_accepted": False,
    }

    plan = build_pilot_survey_response_plan(
        flow=flow,
        sm_result={"next_state": "survey_q2"},
        context_signals=[signal],
        transcript=DialogTranscript(),
        action="acknowledge_and_continue",
    )

    assert plan is not None
    assert plan.generator_required is False
    assert "инструкцию по настройке" in plan.compose()


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


def test_response_plan_unclear_overrides_guard_offer_options_with_survey_clarify():
    _, flow, _ = _load_pilot_runtime()
    signal = {
        "source": "pilot_survey_answer_gate",
        "state": "survey_q3",
        "routing_state": "unclear",
        "answer_accepted": False,
    }

    plan = build_pilot_survey_response_plan(
        flow=flow,
        sm_result={"next_state": "survey_q3"},
        context_signals=[signal],
        transcript=DialogTranscript(),
        action="guard_offer_options",
    )

    assert plan is not None
    assert plan.generator_required is False
    assert plan.compose() == (
        "Уточните, пожалуйста: вы обращались в техподдержку во время настройки? "
        "Если да, то по какому вопросу?"
    )


def test_orchestrator_company_question_in_pilot_survey_keeps_state_and_returns_pricing_action():
    config, flow, state_machine = _load_pilot_runtime()
    state_machine.state = "survey_q1"
    state_machine.current_phase = flow.get_phase_for_state("survey_q1")
    orchestrator = _create_pilot_orchestrator(
        state_machine=state_machine,
        flow=flow,
        config=config,
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
    orchestrator = _create_pilot_orchestrator(
        state_machine=state_machine,
        flow=flow,
        config=config,
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


def test_orchestrator_declarative_fact_request_in_mixed_turn_answers_and_advances_survey():
    config, flow, state_machine = _load_pilot_runtime()
    state_machine.state = "survey_q2"
    state_machine.current_phase = flow.get_phase_for_state("survey_q2")
    orchestrator = _create_pilot_orchestrator(
        state_machine=state_machine,
        flow=flow,
        config=config,
        llm=FakeGateLLM(
            PilotSurveyAnswerGateResult(
                verdict="valid",
                confidence=0.94,
                company_question_present=True,
                reason="survey_answer_with_fact_request",
            )
        ),
    )
    envelope = SimpleNamespace(
        secondary_intents=["question_1c_integration"],
        secondary_intent_confidence={"question_1c_integration": 0.9},
        repeated_question=None,
        intent_confidence=0.93,
        last_user_message="Да, инструкция была понятна. Нужна интеграция с 1С",
    )

    decision = orchestrator.process_turn(
        intent="info_provided",
        extracted_data={},
        context_envelope=envelope,
        user_message="Да, инструкция была понятна. Нужна интеграция с 1С",
    )

    signal = orchestrator.blackboard.get_context_signals()[-1]
    assert decision.action == "answer_with_facts"
    assert decision.next_state == "survey_q3"
    assert signal["routing_state"] == "mixed"


def test_orchestrator_declarative_fact_request_without_survey_answer_keeps_state():
    config, flow, state_machine = _load_pilot_runtime()
    state_machine.state = "survey_q2"
    state_machine.current_phase = flow.get_phase_for_state("survey_q2")
    orchestrator = _create_pilot_orchestrator(
        state_machine=state_machine,
        flow=flow,
        config=config,
        llm=FakeGateLLM(
            PilotSurveyAnswerGateResult(
                verdict="invalid",
                confidence=0.95,
                company_question_present=True,
                reason="pure_fact_request",
            )
        ),
    )
    envelope = SimpleNamespace(
        secondary_intents=["question_1c_integration"],
        secondary_intent_confidence={"question_1c_integration": 0.9},
        repeated_question=None,
        intent_confidence=0.92,
        last_user_message="Мне нужна интеграция с 1С",
    )

    decision = orchestrator.process_turn(
        intent="info_provided",
        extracted_data={},
        context_envelope=envelope,
        user_message="Мне нужна интеграция с 1С",
    )

    signal = orchestrator.blackboard.get_context_signals()[-1]
    assert decision.action == "answer_with_facts"
    assert decision.next_state == "survey_q2"
    assert signal["routing_state"] == "company_question"


def test_orchestrator_rejection_labeled_binary_reply_advances_when_gate_accepts_answer():
    config, flow, state_machine = _load_pilot_runtime()
    state_machine.state = "survey_q2"
    state_machine.current_phase = flow.get_phase_for_state("survey_q2")
    orchestrator = _create_pilot_orchestrator(
        state_machine=state_machine,
        flow=flow,
        config=config,
        llm=FakeGateLLM(
            PilotSurveyAnswerGateResult(
                answer_accepted=True,
                confidence=0.93,
                reason="binary_no_answer",
            )
        ),
    )
    envelope = SimpleNamespace(
        secondary_intents=[],
        secondary_intent_confidence={},
        repeated_question=None,
        intent_confidence=0.91,
        last_user_message="Нет",
    )

    decision = orchestrator.process_turn(
        intent="rejection",
        extracted_data={},
        context_envelope=envelope,
        user_message="Нет",
    )

    signal = orchestrator.blackboard.get_context_signals()[-1]
    assert decision.action == "continue_current_goal"
    assert decision.next_state == "survey_q3"
    assert signal["routing_state"] == "survey_answer"
    assert "intent_transition_rejection" not in decision.reason_codes


def test_orchestrator_explicit_rejection_still_soft_closes_when_gate_rejects_answer():
    config, flow, state_machine = _load_pilot_runtime()
    state_machine.state = "survey_q2"
    state_machine.current_phase = flow.get_phase_for_state("survey_q2")
    orchestrator = _create_pilot_orchestrator(
        state_machine=state_machine,
        flow=flow,
        config=config,
        llm=FakeGateLLM(
            PilotSurveyAnswerGateResult(
                answer_accepted=False,
                confidence=0.96,
                reason="explicit_exit",
            )
        ),
    )
    envelope = SimpleNamespace(
        secondary_intents=[],
        secondary_intent_confidence={},
        repeated_question=None,
        intent_confidence=0.95,
        last_user_message="Нет, не хочу продолжать опрос.",
    )

    decision = orchestrator.process_turn(
        intent="rejection",
        extracted_data={},
        context_envelope=envelope,
        user_message="Нет, не хочу продолжать опрос.",
    )

    signal = orchestrator.blackboard.get_context_signals()[-1]
    assert decision.next_state == "soft_close"
    assert signal["routing_state"] == "unclear"
    assert "intent_transition_rejection" in decision.reason_codes


def test_sales_bot_repeated_binary_answers_across_survey_states_clarifies_instead_of_generic_options(
    monkeypatch,
):
    llm = FakeBotLLM()
    llm.results = [
        PilotSurveyAnswerGateResult(
            verdict="valid",
            confidence=0.95,
            reason="q2_binary_yes",
        ),
        PilotSurveyAnswerGateResult(
            verdict="invalid",
            confidence=0.95,
            reason="q3_missing_topic",
        ),
    ]
    bot = SalesBot(llm=llm, flow_name="pilot_survey")
    bot.state_machine.state = "survey_q2"
    bot.state_machine.current_phase = "survey"

    monkeypatch.setattr(
        bot.classifier,
        "classify",
        lambda *_args, **_kwargs: _mock_bot_classification(),
    )
    monkeypatch.setattr(bot, "_analyze_tone", lambda *_args, **_kwargs: _mock_bot_tone())

    first = bot.process("Да")
    second = bot.process("Да")

    assert first["action"] == "continue_current_goal"
    assert first["response"].startswith("3/8.")
    assert second["action"] == "continue_current_goal"
    assert second["state"] == "survey_q3"
    assert second["response"] == (
        "Уточните, пожалуйста: вы обращались в техподдержку во время настройки? "
        "Если да, то по какому вопросу?"
    )
    assert "Что вас интересует?" not in second["response"]


def test_sales_bot_disambiguation_needed_on_valid_pilot_answer_still_advances_survey(
    monkeypatch,
):
    llm = FakeBotLLM()
    llm.results = [
        PilotSurveyAnswerGateResult(
            verdict="valid",
            confidence=0.95,
            reason="q2_answer_valid_despite_ambiguous_intent",
        ),
    ]
    bot = SalesBot(llm=llm, flow_name="pilot_survey")
    bot.state_machine.state = "survey_q2"
    bot.state_machine.current_phase = "survey"
    bot.last_bot_message = (
        "2/8. Получили ли вы инструкцию по настройке? Была ли она понятна и достаточна?"
    )

    monkeypatch.setattr(
        bot.classifier,
        "classify",
        lambda *_args, **_kwargs: _mock_disambiguation_needed_classification(),
    )
    monkeypatch.setattr(bot, "_analyze_tone", lambda *_args, **_kwargs: _mock_bot_tone())

    result = bot.process("Да все ок")

    assert result["action"] == "continue_current_goal"
    assert result["state"] == "survey_q3"
    assert result["response"] == (
        "3/8. Обращались ли вы в техподдержку во время настройки? По какому вопросу?"
    )
    assert "Продолжить разговор" not in result["response"]


def test_sales_bot_disambiguation_needed_on_invalid_pilot_answer_uses_survey_clarify(
    monkeypatch,
):
    llm = FakeBotLLM()
    llm.results = [
        PilotSurveyAnswerGateResult(
            verdict="invalid",
            confidence=0.95,
            reason="q2_answer_missing_instruction_details",
        ),
    ]
    bot = SalesBot(llm=llm, flow_name="pilot_survey")
    bot.state_machine.state = "survey_q2"
    bot.state_machine.current_phase = "survey"
    bot.last_bot_message = (
        "2/8. Получили ли вы инструкцию по настройке? Была ли она понятна и достаточна?"
    )

    monkeypatch.setattr(
        bot.classifier,
        "classify",
        lambda *_args, **_kwargs: _mock_disambiguation_needed_classification(),
    )
    monkeypatch.setattr(bot, "_analyze_tone", lambda *_args, **_kwargs: _mock_bot_tone())

    result = bot.process("Да")

    assert result["action"] == "continue_current_goal"
    assert result["state"] == "survey_q2"
    assert result["response"] == (
        "Подскажите, пожалуйста: инструкцию по настройке вы получили, и она была "
        "понятна и достаточна или чего-то не хватило?"
    )
    assert "Продолжить разговор" not in result["response"]


def test_sales_bot_mixed_company_answer_uses_current_survey_context_for_generation(
    monkeypatch,
):
    from src.feature_flags import flags

    flags.clear_all_overrides()
    flags.set_override("context_full_envelope", True)
    try:
        llm = FakeBotLLM()
        llm.results = [
            PilotSurveyAnswerGateResult(
                verdict="valid",
                confidence=0.95,
                company_question_present=True,
                reason="survey_answer_with_fact_request",
            ),
        ]
        bot = SalesBot(llm=llm, flow_name="pilot_survey")
        bot.state_machine.state = "survey_q2"
        bot.state_machine.current_phase = "survey"

        monkeypatch.setattr(
            bot.classifier,
            "classify",
            lambda *_args, **_kwargs: {
                **_mock_bot_classification(),
                "secondary_signals": ["question_1c_integration"],
            },
        )
        monkeypatch.setattr(bot, "_analyze_tone", lambda *_args, **_kwargs: _mock_bot_tone())

        captured = {}

        def _capture_generate(action, context, max_retries=None):
            captured["action"] = action
            captured["context"] = dict(context)
            return "Ответ по компании."

        monkeypatch.setattr(bot.generator, "generate", _capture_generate)

        result = bot.process("Да, инструкция понятна. А с 1С есть интеграция?")

        current_goal = bot._flow.states.get("survey_q2", {}).get("goal", "")
        assert result["action"] == "answer_with_facts"
        assert result["state"] == "survey_q3"
        assert captured["action"] == "answer_with_facts"
        assert captured["context"]["state"] == "survey_q2"
        assert captured["context"]["goal"] == current_goal
        assert captured["context"]["grounding_intent"] == "question_1c_integration"
        assert captured["context"]["grounding_categories"] == ["integrations"]
        assert result["response"] == (
            "Ответ по компании.\n\n"
            "3/8. Обращались ли вы в техподдержку во время настройки? По какому вопросу?"
        )
    finally:
        flags.clear_all_overrides()
