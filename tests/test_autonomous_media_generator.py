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
    assert "Сначала ответь по сути последнего сообщения" in template
    assert "Если это прямой вопрос, первая фраза обязана отвечать именно на него." in template
    assert "Ограничения и отсутствующие функции упоминай только если клиент спросил о них напрямую" in template


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
    assert "В документе это не указано" in captured["prompt"]
    assert captured["prompt"].count("В документе это не указано") == 1
    assert "Я уточню этот вопрос и чуть позже отпишу вам" not in captured["prompt"]


def test_unknown_fallback_contract_builder_handles_factual_non_factual_and_media_modes():
    gen = _make_generator()

    factual_contract = gen._build_unknown_fallback_contract(
        response_mode="normal_dialog",
        allow_unknown_kb_fallback=True,
    )
    non_factual_contract = gen._build_unknown_fallback_contract(
        response_mode="normal_dialog",
        allow_unknown_kb_fallback=False,
    )
    media_contract = gen._build_unknown_fallback_contract(
        response_mode="media_only",
        allow_unknown_kb_fallback=True,
    )

    assert "Я уточню этот вопрос и чуть позже отпишу вам" in factual_contract
    assert "только как полный финальный ответ" in factual_contract
    assert "В документе это не указано" not in factual_contract

    assert "не обещай дополнительное уточнение" in non_factual_contract
    assert "Я уточню этот вопрос и чуть позже отпишу вам" not in non_factual_contract
    assert "В документе это не указано" not in non_factual_contract

    assert "В документе это не указано" in media_contract
    assert "Я уточню этот вопрос и чуть позже отпишу вам" not in media_contract


def test_normal_dialog_factual_guardrails_reference_contract_without_hardcoding_phrase():
    gen = _make_generator()

    guardrails = gen._build_factual_guardrails(
        intent="question_features",
        user_message="Какая интеграция есть?",
        response_mode="normal_dialog",
    )

    assert "unknown-fallback contract" in guardrails
    assert "Я уточню этот вопрос и чуть позже отпишу вам" not in guardrails
    assert "В документе это не указано" not in guardrails


def test_factual_guardrails_include_short_disambiguation_rule():
    gen = _make_generator()

    guardrails = gen._build_factual_guardrails(
        intent="question_features",
        user_message="Какая интеграция есть?",
        response_mode="normal_dialog",
    )

    assert "Не подменяй названия тарифов" in guardrails
    assert "несколько похожих сущностей" in guardrails
    assert "короткое уточнение вместо догадки" in guardrails


def test_autonomous_system_prompt_includes_scope_rules():
    gen = _make_generator()

    system_prompt = gen._build_system_prompt(
        tone_instruction="",
        style_instruction="",
        response_mode="normal_dialog",
    )

    assert "Не приписывай клиенту боли, контекст, цели или ограничения" in system_prompt
    assert "специализируешься на Wipon" in system_prompt
    assert system_prompt.count("Не приписывай клиенту боли, контекст, цели или ограничения") == 1
    assert system_prompt.count("специализируешься на Wipon") == 1
    assert "Я уточню этот вопрос и чуть позже отпишу вам" not in system_prompt


def test_autonomous_system_prompt_scopes_greeting_guard_to_non_initial_turns():
    gen = _make_generator()

    system_prompt = gen._build_system_prompt(
        tone_instruction="",
        style_instruction="",
        response_mode="normal_dialog",
    )

    assert "В середине диалога избегай пустых шаблонов" in system_prompt
    assert "Если это не первое сообщение диалога, не начинай с приветствия." in system_prompt


def test_autonomous_safety_rules_drop_moved_scope_rules():
    gen = _make_generator()

    safety_rules = gen._build_safety_rules("normal_dialog")

    assert "Если используешь факты о продукте" in safety_rules
    assert "Если это прямой factual/pricing вопрос" not in safety_rules
    assert "Не подменяй названия тарифов" not in safety_rules
    assert "Не приписывай клиенту боли, контекст, цели или ограничения" not in safety_rules
    assert "специализируешься на Wipon" not in safety_rules
    assert "несколько похожих сущностей" not in safety_rules
    assert "Я уточню этот вопрос и чуть позже отпишу вам" not in safety_rules


def test_turn_safety_rules_do_not_mutate_unknown_fallback_wording():
    gen = _make_generator()

    factual = gen._build_turn_safety_rules(
        response_mode="normal_dialog",
        allow_unknown_kb_fallback=True,
    )
    non_factual = gen._build_turn_safety_rules(
        response_mode="normal_dialog",
        allow_unknown_kb_fallback=False,
    )

    assert factual == non_factual
    assert "Я уточню этот вопрос и чуть позже отпишу вам" not in factual


def test_factual_prompt_contains_kb_fallback_phrase_exactly_once():
    gen = _make_generator()
    gen.llm.generate.return_value = "Есть мобильное приложение."

    response = gen.generate(
        "continue_current_goal",
        {
            "intent": "question_features",
            "state": "autonomous_discovery",
            "user_message": "Есть мобильное приложение?",
            "history": [],
            "collected_data": {},
            "missing_data": [],
            "goal": "Ответить по возможностям",
            "spin_phase": "discovery",
            "_skip_retrieval": True,
            "retrieved_facts": "Есть мобильное приложение для владельца и кассира.",
        },
        max_retries=1,
    )

    assert response
    prompt = gen.llm.generate.call_args_list[0].args[0]
    assert prompt.count("Я уточню этот вопрос и чуть позже отпишу вам") == 1
    assert "В документе это не указано" not in prompt


def test_prepare_and_generate_paths_share_same_unknown_fallback_contract(monkeypatch):
    llm = Mock()
    captured = {}

    def _generate(prompt, **_kwargs):
        captured["prompt"] = prompt
        return "OK"

    llm.generate.side_effect = _generate
    flow = SimpleNamespace(name="autonomous", get_template=lambda key: "{unknown_fallback_contract}")
    gen = ResponseGenerator(llm=llm, flow=flow)
    gen.category_router = None
    gen._enhanced_pipeline = SimpleNamespace(
        retrieve=lambda **_kwargs: ("Есть мобильное приложение для владельца и кассира.", [], [])
    )

    monkeypatch.setattr(
        "src.generator.get_retriever",
        lambda: SimpleNamespace(
            kb=SimpleNamespace(
                company_name="Wipon",
                company_description="Retail automation",
            )
        ),
    )

    context = {
        "action": "continue_current_goal",
        "intent": "info_provided",
        "state": "autonomous_discovery",
        "user_message": "Хорошо",
        "history": [],
        "collected_data": {},
        "missing_data": ["current_tools"],
        "goal": "Понять текущий процесс",
        "spin_phase": "discovery",
        "_skip_retrieval": True,
        "retrieved_facts": "",
    }

    prepared = gen.prepare_response_context("autonomous_discovery", context)
    gen.generate("continue_current_goal", context, max_retries=1)

    assert prepared["variables"]["unknown_fallback_contract"] == captured["prompt"]
    assert prepared["variables"]["unknown_kb_instruction"] == prepared["variables"]["unknown_fallback_contract"]


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
