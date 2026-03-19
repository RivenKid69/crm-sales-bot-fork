from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import yaml

from src.generator import ResponseGenerator, SafeDict


class _AutonomousFlow:
    name = "autonomous"
    states = {}

    def __init__(self):
        path = Path(__file__).parent.parent / "src" / "yaml_config" / "templates" / "autonomous" / "prompts.yaml"
        with open(path, "r", encoding="utf-8") as handle:
            self.templates = yaml.safe_load(handle)["templates"]

    def get_template(self, key: str) -> str:
        template = self.templates.get(key) or {}
        return str(template.get("template") or "")


def _make_generator() -> ResponseGenerator:
    llm = Mock()
    llm.generate.return_value = "Краткий ответ по фактам."
    return ResponseGenerator(llm=llm, flow=_AutonomousFlow())


def _media_context(**overrides):
    context = {
        "user_message": "что в документе?",
        "intent": "question_features",
        "state": "autonomous_presentation",
        "history": [],
        "goal": "Понять потребности",
        "collected_data": {},
        "missing_data": [],
        "spin_phase": "presentation",
        "retrieved_facts": "[doc.pdf]\nФакты:\n- У клиента 3 магазина.",
        "kb_retrieved_facts": "KB FACT",
        "final_grounding_facts": "[doc.pdf]\nФакты:\n- У клиента 3 магазина.",
        "selected_media_grounding": "[doc.pdf]\nФакты:\n- У клиента 3 магазина.",
        "media_route_mode": "media_only",
        "media_route_instruction": "MEDIA ROUTE",
        "retrieved_urls": "",
        "_skip_retrieval": True,
    }
    context.update(overrides)
    return context


def test_route_aware_override_selects_autonomous_media_only():
    template_key = ResponseGenerator._apply_route_aware_template_override(
        requested_action="autonomous_respond",
        selected_template_key="autonomous_respond",
        context=_media_context(),
    )

    assert template_key == "autonomous_media_only"


def test_route_aware_override_does_not_break_secondary_answer_injection():
    template_key = ResponseGenerator._apply_route_aware_template_override(
        requested_action="autonomous_respond",
        selected_template_key="blocking_with_pricing",
        context=_media_context(),
    )

    assert template_key == "blocking_with_pricing"


def test_route_aware_override_keeps_continue_current_goal_in_hybrid_family():
    template_key = ResponseGenerator._apply_route_aware_template_override(
        requested_action="continue_current_goal",
        selected_template_key="continue_current_goal",
        context=_media_context(
            media_route_mode="hybrid",
            final_grounding_facts="KB FACT\n\n[doc.pdf]\nФакты:\n- У клиента 3 магазина.",
        ),
    )

    assert template_key == "autonomous_respond"


def test_autonomous_media_only_template_renders_without_sales_stage_vars():
    path = Path(__file__).parent.parent / "src" / "yaml_config" / "templates" / "autonomous" / "prompts.yaml"
    with open(path, "r", encoding="utf-8") as handle:
        prompts = yaml.safe_load(handle)["templates"]

    template = prompts["autonomous_media_only"]["template"]
    rendered = template.format_map(
        SafeDict(
            {
                "system": "SYSTEM",
                "safety_rules": "SAFE",
                "history": "HISTORY",
                "user_message": "что в документе?",
                "selected_media_grounding": "MEDIA",
                "address_instruction": "",
                "language_instruction": "",
                "stress_instruction": "",
            }
        )
    )

    assert "{goal}" not in rendered
    assert "{spin_phase}" not in rendered
    assert "MEDIA" in rendered


def test_route_aware_media_factual_helper_is_narrow():
    assert ResponseGenerator._is_route_aware_media_factual_turn(_media_context()) is True
    assert ResponseGenerator._is_route_aware_media_factual_turn(
        _media_context(
            media_route_mode="normal_dialog",
            selected_media_grounding="",
            user_message="Сколько стоит Lite?",
            intent="price_question",
        )
    ) is False


def test_autonomous_respond_prompt_defers_limitations_until_directly_asked():
    path = Path(__file__).parent.parent / "src" / "yaml_config" / "templates" / "autonomous" / "prompts.yaml"
    with open(path, "r", encoding="utf-8") as handle:
        prompts = yaml.safe_load(handle)["templates"]

    template = prompts["autonomous_respond"]["template"]
    assert 'Если клиент спрашивает в целом "подходит ли", "что умеет", "как внедрить" — сначала дай ценность' in template
    assert "Ограничения, отсутствующие модули и недоработки упоминай только если клиент спросил о них напрямую" in template
    assert 'Не начинай ответ с "но", "однако", ограничений, отсутствующих функций или минусов продукта.' in template


def test_generate_media_only_uses_media_template_and_factual_guardrail():
    gen = _make_generator()
    captured = {}

    def _generate(prompt, **_kwargs):
        captured["prompt"] = prompt
        return "Ответ по документу."

    gen.llm.generate.side_effect = _generate

    response = gen.generate("autonomous_respond", _media_context(), max_retries=1)

    assert response
    assert "SELECTED MEDIA GROUNDING" in captured["prompt"]
    assert "KB GROUNDING" not in captured["prompt"]
    assert "КРИТИЧЕСКИЕ ПРАВИЛА ФАКТОЛОГИИ" in captured["prompt"]


def test_media_factual_turn_reaches_verifier_in_postprocess(monkeypatch):
    gen = _make_generator()
    verifier_called = {"value": False}

    class _Verifier:
        def is_enabled(self):
            return True

        def verify_and_rewrite(self, **_kwargs):
            verifier_called["value"] = True
            return SimpleNamespace(
                verifier_used=True,
                changed=False,
                verifier_verdict="pass",
                reason_codes=[],
                final_response="Проверенный ответ.",
            )

    monkeypatch.setattr(gen, "_ensure_factual_verifier", lambda: _Verifier())
    monkeypatch.setattr(gen, "_has_factual_verifier_coverage", lambda *_args, **_kwargs: True)

    processed, _events = gen.post_process_only(
        response="Ответ по документу.",
        context=_media_context(),
        requested_action="autonomous_respond",
        selected_template_key="autonomous_media_only",
        retrieved_facts=_media_context()["retrieved_facts"],
    )

    assert verifier_called["value"] is True
    assert processed == "Проверенный ответ."
