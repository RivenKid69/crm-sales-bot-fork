from types import SimpleNamespace

import pytest

from src.feature_flags import flags
from src.generator import ResponseGenerator
from src.response_directives import ResponseDirectives
from src.unknown_kb_fallbacks import is_pure_approved_unknown_kb_fallback


SAFE_FALLBACK = "Я уточню этот вопрос и чуть позже отпишу вам."
SAFE_QUESTION = "Что важно сейчас?"


class _FakeSection:
    def __init__(self) -> None:
        self.priority = 5
        self.facts = "Wipon overview."


class _FakeRetriever:
    def __init__(self) -> None:
        self.kb = SimpleNamespace(
            sections=[_FakeSection()],
            company_name="Wipon",
            company_description="CRM",
        )


class _Flow:
    name = "autonomous"

    def get_template(self, _key: str):
        return None


class _StructuredLLM:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = 0
        self.prompts = []

    def generate_structured(self, prompt, schema, **kwargs):
        self.calls += 1
        self.prompts.append(prompt)
        if not self.outputs:
            raise RuntimeError("no scripted output")
        payload = self.outputs.pop(0)
        if isinstance(payload, Exception):
            raise payload
        if payload is None:
            return None
        if isinstance(payload, str):
            return payload
        return schema.model_validate(payload)


@pytest.fixture(autouse=True)
def _reset_flags_and_retriever(monkeypatch):
    flags.clear_all_overrides()
    flags.set_override("response_diversity", False)
    flags.set_override("apology_system", False)
    flags.set_override("response_boundary_validator", False)
    flags.set_override("response_factual_verifier", False)
    monkeypatch.setattr("src.generator.get_retriever", lambda: _FakeRetriever())
    yield
    flags.clear_all_overrides()


def _make_generator(llm):
    return ResponseGenerator(llm=llm, flow=_Flow())


def _make_context(**overrides):
    context = {
        "intent": "question_support",
        "state": "autonomous_discovery",
        "user_message": "Какие условия по SLA?",
        "history": [{"user": "Нужны детали", "bot": "Расскажу по фактам."}],
        "collected_data": {
            "company_size": 12,
            "current_tools": "Excel",
            "business_type": "магазин",
            "pain_point": "ошибки в учете",
            "desired_outcome": "сократить потери",
            "role": "владелец",
        },
        "missing_data": [],
    }
    context.update(overrides)
    return context


def _post_process(generator, response, context=None, retrieved_facts=""):
    return generator.post_process_only(
        response=response,
        context=context or _make_context(),
        requested_action="autonomous_respond",
        selected_template_key="autonomous_respond",
        retrieved_facts=retrieved_facts,
    )


def test_pure_unknown_fallback_helper_rejects_prefixed_variant():
    assert is_pure_approved_unknown_kb_fallback(SAFE_FALLBACK) is True
    assert (
        is_pure_approved_unknown_kb_fallback(
            f"По этому пункту позже уточню. {SAFE_FALLBACK}"
        )
        is False
    )


def test_pure_fallback_stays_same_when_model_declines_followup():
    generator = _make_generator(
        _StructuredLLM([{"use_followup": False, "question": SAFE_QUESTION}])
    )

    processed, events = _post_process(generator, SAFE_FALLBACK)

    assert processed == SAFE_FALLBACK
    followup_events = [
        event for event in events if event.get("stage") == "approved_unknown_fallback_followup"
    ]
    assert followup_events
    assert followup_events[-1]["reason"] == "model_declined"


def test_valid_followup_appends_single_question_to_pure_fallback():
    generator = _make_generator(
        _StructuredLLM([{"use_followup": True, "question": SAFE_QUESTION}])
    )

    processed, events = _post_process(generator, SAFE_FALLBACK)

    assert processed == f"{SAFE_FALLBACK} {SAFE_QUESTION}"
    followup_events = [
        event for event in events if event.get("stage") == "approved_unknown_fallback_followup"
    ]
    assert followup_events
    assert followup_events[-1]["question_added"] is True
    assert followup_events[-1]["reason"] == "question_appended"


def test_question_mode_suppress_keeps_pure_fallback_without_llm_call():
    directives = ResponseDirectives()
    directives.question_mode = "suppress"
    directives.suppress_question = True
    llm = _StructuredLLM([{"use_followup": True, "question": SAFE_QUESTION}])
    generator = _make_generator(llm)

    processed, _ = _post_process(
        generator,
        SAFE_FALLBACK,
        context=_make_context(response_directives=directives),
    )

    assert processed == SAFE_FALLBACK
    assert llm.calls == 0
    trace = generator._last_postprocess_meta["postprocess_trace"]
    followup_step = [
        item for item in trace if item.get("rule_id") == "approved_unknown_fallback_followup"
    ]
    assert followup_step
    assert followup_step[-1]["enabled"] is False
    assert followup_step[-1]["reason"] == "question_mode_suppress"


@pytest.mark.parametrize(
    "payload,expected_reason",
    [
        ({"use_followup": True, "question": "Что важно? Что срочнее?"}, "question_rejected"),
        (
            {
                "use_followup": True,
                "question": "Что именно для вас сейчас наиболее важно вообще в работе команды и какие процессы дополнительно сильнее всего замедляют сотрудников ежедневно?",
            },
            "structured_output_invalid",
        ),
        ({"use_followup": True, "question": "Оставите номер для звонка?"}, "question_rejected"),
        ({"use_followup": True, "question": "Нужна интеграция с Kaspi?"}, "question_rejected"),
        ({"use_followup": True, "question": "Уточнить по базе знаний?"}, "question_rejected"),
        ("broken json", "structured_output_invalid"),
    ],
)
def test_invalid_followup_outputs_are_dropped(payload, expected_reason):
    generator = _make_generator(_StructuredLLM([payload]))

    processed, events = _post_process(generator, SAFE_FALLBACK)

    assert processed == SAFE_FALLBACK
    followup_events = [
        event for event in events if event.get("stage") == "approved_unknown_fallback_followup"
    ]
    assert followup_events
    assert followup_events[-1]["reason"] == expected_reason


def test_boundary_validator_fallback_can_gain_safe_followup(monkeypatch):
    from src.response_boundary_validator import boundary_validator

    flags.set_override("response_boundary_validator", True)
    generator = _make_generator(
        _StructuredLLM([{"use_followup": True, "question": SAFE_QUESTION}])
    )

    def _fake_validate(response, context, llm=None):
        if llm is not None:
            return SimpleNamespace(
                response=SAFE_FALLBACK,
                violations=["unknown_source_leak"],
                fallback_used=True,
            )
        return SimpleNamespace(response=response, violations=[], fallback_used=False)

    monkeypatch.setattr(boundary_validator, "validate_response", _fake_validate)

    processed, events = _post_process(generator, "В базе знаний нет данных.")

    assert processed == f"{SAFE_FALLBACK} {SAFE_QUESTION}"
    stages = [event.get("stage") for event in events]
    assert "boundary_validator" in stages
    assert "approved_unknown_fallback_followup" in stages


def test_followup_prompt_includes_llm_guidance_from_missing_client_context():
    generator = _make_generator(
        _StructuredLLM([{"use_followup": False, "question": SAFE_QUESTION}])
    )

    processed, _events = _post_process(
        generator,
        SAFE_FALLBACK,
        context=_make_context(
            history=[
                {
                    "user": "Смотрим систему для сети магазинов",
                    "bot": "Поняла. А что сейчас больше всего напрягает в работе?",
                }
            ],
            collected_data={},
            missing_data=["company_size", "current_tools", "pain_point", "desired_outcome"],
        ),
    )

    assert processed == SAFE_FALLBACK
    prompt = generator.llm.prompts[-1]
    assert "CLIENT_PROFILE_CARD:" in prompt
    assert "MISSING_DATA:" in prompt
    assert "FOLLOWUP_GUIDANCE:" in prompt
    assert "AVAILABLE_QUESTIONS:" in prompt
    assert "DO_NOT_ASK:" in prompt
    assert "RECENT_BOT_QUESTIONS:" in prompt
    assert "как к вам лучше обращаться" in prompt.lower()
    assert "в какой сфере вы работаете" in prompt.lower()
    assert "в каком вы городе" in prompt.lower()
    assert "раньше автоматизация у вас уже была" in prompt.lower()
    assert "company_size" not in prompt
    assert "current_tools" not in prompt
    assert "pain_point" not in prompt


def test_autonomous_unknown_followup_ignores_legacy_missing_fields_when_profile_complete():
    phase = ResponseGenerator._resolve_unknown_fallback_followup_phase(
        "autonomous_discovery",
        {
            "contact_name": "Айдана",
            "business_type": "магазин",
            "city": "Алматы",
            "automation_before": False,
        },
        ["company_size", "current_tools", "pain_point"],
    )

    assert phase == ""


def test_autonomous_unknown_followup_guidance_uses_only_unified_profile_questions():
    generator = _make_generator(_StructuredLLM([]))

    guidance = generator._build_unknown_fallback_followup_guidance(
        state="autonomous_discovery",
        collected_data={},
        missing_data=["company_size", "current_tools", "pain_point", "desired_outcome"],
        history=[],
    )

    combined = " ".join(guidance.values()).lower()
    assert "как к вам лучше обращаться" in combined
    assert "в какой сфере вы работаете" in combined
    assert "в каком вы городе" in combined
    assert "раньше автоматизация у вас уже была" in combined
    assert "company_size" not in combined
    assert "current_tools" not in combined
    assert "pain_point" not in combined


def test_factual_verifier_safe_minimal_fallback_can_gain_same_followup(monkeypatch):
    flags.set_override("response_factual_verifier", True)
    generator = _make_generator(
        _StructuredLLM(
            [
                {
                    "verdict": "fail",
                    "checks": [
                        {
                            "claim": "Mini 1 ₸/мес",
                            "supported": False,
                            "evidence_quote": "",
                        }
                    ],
                    "rewritten_response": "",
                    "confidence": 0.41,
                },
                {"use_followup": True, "question": SAFE_QUESTION},
            ]
        )
    )
    monkeypatch.setattr("src.factual_verifier.pick_unknown_kb_fallback", lambda: SAFE_FALLBACK)

    processed, events = _post_process(
        generator,
        "Mini стоит 1 ₸/мес.",
        context=_make_context(
            intent="price_question",
            user_message="Сколько стоит Mini?",
        ),
        retrieved_facts="Mini — 150 000 ₸/год.",
    )

    assert processed == f"{SAFE_FALLBACK} {SAFE_QUESTION}"
    factual_events = [event for event in events if event.get("stage") == "factual_verifier"]
    assert factual_events
    assert factual_events[-1]["verdict"] == "fail"
    assert "safe_minimal_fallback" in factual_events[-1]["reason_codes"]


def test_regular_discovery_response_does_not_enter_followup_path():
    llm = _StructuredLLM([{"use_followup": True, "question": SAFE_QUESTION}])
    generator = _make_generator(llm)
    original = "Расскажите подробнее о вашем бизнесе — подберу подходящий вариант."

    processed, _ = _post_process(generator, original)

    assert processed == original
    assert llm.calls == 0
    trace = generator._last_postprocess_meta["postprocess_trace"]
    followup_step = [
        item for item in trace if item.get("rule_id") == "approved_unknown_fallback_followup"
    ]
    assert followup_step
    assert followup_step[-1]["enabled"] is False
    assert followup_step[-1]["reason"] == "not_pure_approved_unknown_fallback"
