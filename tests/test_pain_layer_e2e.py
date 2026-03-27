from pathlib import Path
from unittest.mock import Mock

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


class _FlowAutonomous:
    name = "autonomous"
    states = {
        "autonomous_problem": {"goal": "Выявить боль", "phase": "problem"},
        "autonomous_discovery": {"goal": "Квалификация", "phase": "situation"},
    }

    def get_template(self, _key: str):
        return None


class _FlowNonAutonomous:
    name = "spin_selling"
    states = {
        "qualification": {"goal": "Квалификация", "phase": "situation"},
    }

    def get_template(self, _key: str):
        return None


def _make_context(*, state: str, message: str, intent: str):
    return {
        "user_message": message,
        "intent": intent,
        "state": state,
        "history": [],
        "collected_data": {},
        "missing_data": ["company_size"],
        "goal": "",
        "spin_phase": "",
        "recent_fact_keys": [],
        "action": "autonomous_respond",
    }


def _load_autonomous_template() -> str:
    path = Path(__file__).parent.parent / "src" / "yaml_config" / "templates" / "autonomous" / "prompts.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data["templates"]["autonomous_respond"]["template"]


def test_pain_context_injected_only_for_autonomous(monkeypatch):
    monkeypatch.setattr("src.generator.get_retriever", lambda: _FakeRetriever())
    monkeypatch.setattr("src.knowledge.pain_retriever.retrieve_pain_context", lambda _m: "PAIN_BLOCK")

    gen_auto = ResponseGenerator(llm=Mock(), flow=_FlowAutonomous())
    gen_auto._enhanced_pipeline = _FakeEnhancedPipeline()

    ctx_auto = _make_context(
        state="autonomous_problem",
        message="касса тормозит в час пик",
        intent="problem_revealed",
    )
    prepared_auto = gen_auto.prepare_response_context("autonomous_problem", ctx_auto)
    assert prepared_auto["variables"]["pain_context"] == "PAIN_BLOCK"

    gen_non_auto = ResponseGenerator(llm=Mock(), flow=_FlowNonAutonomous())
    ctx_non_auto = _make_context(
        state="qualification",
        message="касса тормозит в час пик",
        intent="problem_revealed",
    )
    prepared_non_auto = gen_non_auto.prepare_response_context("qualification", ctx_non_auto)
    assert prepared_non_auto["variables"].get("pain_context", "") == ""


def test_ab_retrieved_facts_unchanged_with_pain_layer_on_off(monkeypatch):
    monkeypatch.setattr("src.generator.get_retriever", lambda: _FakeRetriever())
    gen = ResponseGenerator(llm=Mock(), flow=_FlowAutonomous())
    gen._enhanced_pipeline = _FakeEnhancedPipeline()

    ctx = _make_context(
        state="autonomous_problem",
        message="боюсь перехода на СНР 2026",
        intent="problem_revealed",
    )

    monkeypatch.setattr("src.knowledge.pain_retriever.retrieve_pain_context", lambda _m: "")
    prepared_off = gen.prepare_response_context("autonomous_problem", ctx)

    monkeypatch.setattr("src.knowledge.pain_retriever.retrieve_pain_context", lambda _m: "PAIN_BLOCK")
    prepared_on = gen.prepare_response_context("autonomous_problem", ctx)

    assert prepared_off["retrieved_facts"] == "MAIN_FACTS_BLOCK"
    assert prepared_on["retrieved_facts"] == "MAIN_FACTS_BLOCK"


def test_autonomous_prompt_renders_pain_context_before_main_facts(monkeypatch):
    monkeypatch.setattr("src.generator.get_retriever", lambda: _FakeRetriever())
    monkeypatch.setattr("src.knowledge.pain_retriever.retrieve_pain_context", lambda _m: "PAIN_BLOCK")

    gen = ResponseGenerator(llm=Mock(), flow=_FlowAutonomous())
    gen._enhanced_pipeline = _FakeEnhancedPipeline()

    ctx = _make_context(
        state="autonomous_problem",
        message="касса тормозит в час пик",
        intent="problem_revealed",
    )
    prepared = gen.prepare_response_context("autonomous_problem", ctx)

    template = _load_autonomous_template()
    rendered = template.format_map(SafeDict(prepared["variables"]))

    pain_pos = rendered.find("PAIN_BLOCK")
    facts_pos = rendered.find("=== FINAL GROUNDING FACTS ===")

    assert pain_pos != -1
    assert facts_pos != -1
    assert pain_pos < facts_pos
