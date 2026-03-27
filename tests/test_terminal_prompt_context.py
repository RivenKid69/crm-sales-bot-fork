from pathlib import Path

import yaml

from src.generator import ResponseGenerator, SafeDict


class _FakeSection:
    def __init__(self):
        self.priority = 5
        self.facts = "fact"


class _FakeRetriever:
    def __init__(self):
        self.kb = type(
            "KB",
            (),
            {
                "sections": [_FakeSection()],
                "company_name": "Wipon",
                "company_description": "CRM",
            },
        )()

    def get_company_info(self):
        return "Wipon: CRM"

    def retrieve_with_urls(self, **kwargs):
        return "MAIN_FACTS_BLOCK", []


class _FakeEnhancedPipeline:
    def retrieve(self, **kwargs):
        return "MAIN_FACTS_BLOCK", [], ["main_fact_1"]


class _CaptureLLM:
    def __init__(self, response: str = "Принято."):
        self.response = response
        self.last_prompt = ""

    def generate(self, prompt: str, purpose: str | None = None) -> str:
        self.last_prompt = prompt
        return self.response


def _load_autonomous_templates() -> dict:
    path = (
        Path(__file__).parent.parent
        / "src"
        / "yaml_config"
        / "templates"
        / "autonomous"
        / "prompts.yaml"
    )
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data["templates"]


_AUTONOMOUS_TEMPLATES = _load_autonomous_templates()
_TERMINAL_REQS = {
    "payment_ready": {
        "required_any": ["contact_name", "client_name"],
        "required_all": ["business_type", "city", "automation_before"],
    },
    "video_call_scheduled": {
        "required_any": ["contact_name", "client_name"],
        "required_all": ["business_type", "city", "automation_before"],
    },
}


class _FlowAutonomousClosing:
    name = "autonomous"
    states = {
        "autonomous_closing": {
            "goal": "Закрыть сделку",
            "phase": "closing",
            "terminal_state_requirements": _TERMINAL_REQS,
        },
    }

    def get_template(self, key: str):
        template = _AUTONOMOUS_TEMPLATES.get(key)
        if not template:
            return None
        return template.get("template")


def _make_context() -> dict:
    return {
        "user_message": "Хочу оплатить и подключиться",
        "intent": "agreement",
        "state": "autonomous_closing",
        "history": [],
        "collected_data": {
            "contact_name": "Айдар",
            "business_type": "магазин",
            "city": "Алматы",
        },
        "missing_data": [],
        "goal": "Закрыть сделку",
        "spin_phase": "closing",
        "recent_fact_keys": [],
        "action": "autonomous_respond",
        "terminal_state_requirements": _TERMINAL_REQS,
        "response_mode": "normal_dialog",
    }


def test_prepare_response_context_includes_terminal_status_and_closing_request(monkeypatch):
    monkeypatch.setattr("src.generator.get_retriever", lambda: _FakeRetriever())
    monkeypatch.setattr("src.knowledge.pain_retriever.retrieve_pain_context", lambda _m: "")

    gen = ResponseGenerator(llm=_CaptureLLM(), flow=_FlowAutonomousClosing())
    gen._enhanced_pipeline = _FakeEnhancedPipeline()

    prepared = gen.prepare_response_context("autonomous_closing", _make_context())
    variables = prepared["variables"]

    assert "СТАТУС ТЕРМИНАЛЬНЫХ СТЕЙТОВ" in variables["terminal_status"]
    assert "payment_ready: НЕ ГОТОВО" in variables["terminal_status"]
    assert "video_call_scheduled: НЕ ГОТОВО" in variables["terminal_status"]
    assert "была ли раньше автоматизация" in variables["terminal_status"]
    assert "current_tools" not in variables["terminal_status"]
    assert "ОБЯЗАТЕЛЬНО" in variables["closing_data_request"]
    assert "была ли раньше автоматизация" in variables["closing_data_request"]
    assert "current_tools" not in variables["closing_data_request"]


def test_autonomous_template_render_exposes_terminal_context(monkeypatch):
    monkeypatch.setattr("src.generator.get_retriever", lambda: _FakeRetriever())
    monkeypatch.setattr("src.knowledge.pain_retriever.retrieve_pain_context", lambda _m: "")

    gen = ResponseGenerator(llm=_CaptureLLM(), flow=_FlowAutonomousClosing())
    gen._enhanced_pipeline = _FakeEnhancedPipeline()

    prepared = gen.prepare_response_context("autonomous_closing", _make_context())
    template = _AUTONOMOUS_TEMPLATES["autonomous_respond"]["template"]
    rendered = template.format_map(SafeDict(prepared["variables"]))

    assert "СТАТУС ТЕРМИНАЛЬНЫХ СТЕЙТОВ" in rendered
    assert "payment_ready: НЕ ГОТОВО" in rendered
    assert "ОБЯЗАТЕЛЬНО: твой ответ ДОЛЖЕН содержать вопрос про была ли раньше автоматизация." in rendered


def test_generate_sends_terminal_context_to_llm(monkeypatch):
    monkeypatch.setattr("src.generator.get_retriever", lambda: _FakeRetriever())
    monkeypatch.setattr("src.knowledge.pain_retriever.retrieve_pain_context", lambda _m: "")

    llm = _CaptureLLM()
    gen = ResponseGenerator(llm=llm, flow=_FlowAutonomousClosing())
    gen._post_process_response = lambda response, **kwargs: (response, [])
    gen._compute_and_cache_response_embedding = lambda _response: None

    context = _make_context()
    context.update(
        {
            "_skip_retrieval": True,
            "retrieved_facts": "MAIN_FACTS_BLOCK",
            "fact_keys": ["main_fact_1"],
        }
    )

    response = gen.generate("autonomous_respond", context)

    assert response == "Принято."
    assert "СТАТУС ТЕРМИНАЛЬНЫХ СТЕЙТОВ" in llm.last_prompt
    assert "payment_ready: НЕ ГОТОВО" in llm.last_prompt
    assert "Для перехода сейчас не хватает: была ли раньше автоматизация." in llm.last_prompt
    assert "ОБЯЗАТЕЛЬНО: твой ответ ДОЛЖЕН содержать вопрос про была ли раньше автоматизация." in llm.last_prompt
