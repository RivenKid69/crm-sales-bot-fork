from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import yaml

import src.generator as generator_module
from src.blackboard.enums import Priority, ProposalType
from src.blackboard.models import Proposal
from src.blackboard.proposal_validator import ProposalValidator
from src.config_loader import ConfigLoader
from src.generator import (
    AUTONOMOUS_NON_TEMPLATE_ACTIONS,
    ResponseGenerator,
    TemplateConfigurationError,
)
from src.response_routing_contract import AUTONOMOUS_RESPONSE_TEMPLATE_KEYS


ROOT = Path(__file__).resolve().parents[1]
AUTONOMOUS_PROMPTS_PATH = ROOT / "src" / "yaml_config" / "templates" / "autonomous" / "prompts.yaml"

CANONICAL_AUTONOMOUS_TEMPLATE_KEYS = {
    "greet_back",
    "autonomous_respond",
    "continue_current_goal",
    "autonomous_media_only",
    "answer_with_facts",
    "clarify_one_question",
    "summarize_and_clarify",
    "nudge_progress",
    "reframe_value",
    "handle_repeated_objection",
    "empathize_and_redirect",
    "objection_limit_reached",
    "blocking_with_pricing",
    "escalate_to_human",
    "soft_close",
    "close",
    "handle_farewell",
}


def _load_autonomous_templates() -> dict:
    with open(AUTONOMOUS_PROMPTS_PATH, "r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)["templates"]


class _AutonomousFlowStub:
    def __init__(self, templates: dict | None = None):
        self.name = "autonomous"
        self.templates = templates or {}

    def get_template(self, key: str) -> str:
        template = self.templates.get(key) or {}
        return str(template.get("template") or "")


def _make_context(**overrides) -> dict:
    context = {
        "intent": "info_provided",
        "state": "autonomous_discovery",
        "user_message": "У нас магазин в Алматы",
        "history": [],
        "goal": "Понять профиль клиента",
        "collected_data": {},
        "missing_data": ["automation_before"],
        "spin_phase": "discovery",
        "retrieved_facts": "FACTS",
        "_skip_retrieval": True,
    }
    context.update(overrides)
    return context


def _select_runtime_template(gen: ResponseGenerator, *, action: str, context: dict) -> str:
    template_key = gen._select_template_key(context.get("intent", ""), action, context)
    if gen._flow and gen._flow.name == "autonomous" and gen._should_inject_secondary_answer(action, context):
        template_key = "blocking_with_pricing"
    if gen._flow and gen._flow.name == "autonomous":
        template_key = gen._apply_route_aware_template_override(
            requested_action=action,
            selected_template_key=template_key,
            context=context,
        )
    return template_key


@pytest.fixture(scope="module")
def autonomous_flow():
    return ConfigLoader().load_flow("autonomous")


@pytest.fixture()
def autonomous_generator(autonomous_flow):
    llm = Mock()
    llm.generate.return_value = "OK"
    return ResponseGenerator(llm=llm, flow=autonomous_flow)


def test_autonomous_prompts_yaml_is_the_canonical_llm_template_set():
    templates = _load_autonomous_templates()

    assert set(templates) == CANONICAL_AUTONOMOUS_TEMPLATE_KEYS
    assert AUTONOMOUS_RESPONSE_TEMPLATE_KEYS == frozenset(CANONICAL_AUTONOMOUS_TEMPLATE_KEYS)


def test_autonomous_closing_templates_follow_autonomous_policy():
    templates = _load_autonomous_templates()

    close_template = templates["close"]["template"]
    soft_close_template = templates["soft_close"]["template"]
    farewell_template = templates["handle_farewell"]["template"]

    close_lower = close_template.lower()
    assert "демо" in close_lower
    assert "пробный сценарий" in close_lower

    for template in (soft_close_template, farewell_template):
        lowered = template.lower()
        assert "демо" not in lowered
        assert "тестов" not in lowered

    assert "{closing_data_request}" in close_template
    assert "{terminal_status}" in close_template
    assert "{state_gated_rules}" in close_template


def test_autonomous_answer_first_and_anti_stall_contract_is_explicit():
    templates = _load_autonomous_templates()

    for template_key in ("answer_with_facts", "autonomous_respond", "continue_current_goal"):
        template = templates[template_key]["template"]
        assert "первая фраза обязана отвечать" in template
        assert "{unknown_fallback_contract}" in template
        assert "Я уточню этот вопрос и чуть позже отпишу вам." not in template
        assert "После неё нельзя добавлять продажу" not in template
        assert "Не компенсируй неизвестный ответ" in template
        assert "Не делай жёстких выводов о необходимости оборудования" in template
        assert "Не выводи сырой текст из grounding" in template


def test_autonomous_unknown_fallback_contract_is_injected_only_via_variable():
    templates = _load_autonomous_templates()

    for template_key in (
        "answer_with_facts",
        "autonomous_respond",
        "autonomous_media_only",
        "continue_current_goal",
        "blocking_with_pricing",
    ):
        template = templates[template_key]["template"]
        assert "{unknown_fallback_contract}" in template
        assert "Я уточню этот вопрос и чуть позже отпишу вам." not in template
        assert "В документе это не указано." not in template


def test_autonomous_closing_templates_avoid_false_promises_and_hidden_cta():
    templates = _load_autonomous_templates()

    escalate_template = templates["escalate_to_human"]["template"].lower()
    soft_close_template = templates["soft_close"]["template"].lower()
    close_template = templates["close"]["template"].lower()

    assert "чуть позже вам перезвонят" not in escalate_template
    assert "не обещай, что кто-то точно позвонит" in escalate_template
    assert "не превращай ответ в скрытый cta" in escalate_template
    assert "не превращай завершение в скрытый cta" in soft_close_template
    assert "не обещай написать, перезвонить, передать, оформить или подготовить" in soft_close_template
    assert "не превращай closing в скрытый cta" in close_template
    assert "\"вам перезвонят\"" in close_template


def test_autonomous_loader_uses_only_autonomous_prompts_yaml(autonomous_flow):
    templates = _load_autonomous_templates()

    assert autonomous_flow.templates == templates
    assert "deflect_and_continue" not in autonomous_flow.templates
    assert "ask_how_to_help" not in autonomous_flow.templates
    assert {"soft_close", "close", "handle_farewell"} <= set(autonomous_flow.templates)


def test_autonomous_valid_actions_exclude_legacy_prompt_templates(autonomous_generator):
    valid_actions = autonomous_generator.get_valid_actions()

    assert CANONICAL_AUTONOMOUS_TEMPLATE_KEYS <= valid_actions
    assert AUTONOMOUS_NON_TEMPLATE_ACTIONS <= valid_actions
    assert "answer_with_knowledge" not in valid_actions
    assert "deflect_and_continue" not in valid_actions
    assert "ask_how_to_help" not in valid_actions


def test_autonomous_validator_accepts_structural_non_template_actions(autonomous_generator):
    validator = ProposalValidator(
        valid_actions=autonomous_generator.get_valid_actions(),
        strict_mode=False,
    )

    proposals = [
        Proposal(
            type=ProposalType.ACTION,
            value=action,
            priority=Priority.HIGH,
            source_name="TestSource",
            reason_code="TEST",
            combinable=False,
        )
        for action in sorted(AUTONOMOUS_NON_TEMPLATE_ACTIONS)
    ]

    errors = validator.validate(proposals)

    assert not any(error.error_code == "INVALID_ACTION" for error in errors)


@pytest.mark.parametrize(
    ("action", "context", "expected_template_key"),
    [
        ("autonomous_respond", _make_context(intent="greeting", state="greeting"), "greet_back"),
        ("autonomous_respond", _make_context(), "autonomous_respond"),
        ("continue_current_goal", _make_context(), "continue_current_goal"),
        ("close", _make_context(intent="request_contract", state="autonomous_closing"), "close"),
        ("soft_close", _make_context(intent="rejection", state="soft_close"), "soft_close"),
        ("polite_farewell", _make_context(intent="farewell"), "handle_farewell"),
        ("escalate_to_human", _make_context(intent="request_human"), "escalate_to_human"),
        ("answer_with_facts", _make_context(intent="question_features"), "answer_with_facts"),
        (
            "objection_limit_reached",
            _make_context(
                intent="objection_price",
                state="autonomous_presentation",
                context_envelope=SimpleNamespace(secondary_intents=["price_question"]),
            ),
            "blocking_with_pricing",
        ),
        (
            "continue_current_goal",
            _make_context(
                state="autonomous_presentation",
                spin_phase="presentation",
                media_route_mode="media_only",
                selected_media_grounding="[doc.pdf]\nФакты",
            ),
            "autonomous_media_only",
        ),
    ],
)
def test_every_autonomous_template_key_selected_by_generator_exists(
    autonomous_generator,
    action,
    context,
    expected_template_key,
):
    template_key = _select_runtime_template(autonomous_generator, action=action, context=context)

    assert template_key == expected_template_key
    assert template_key in autonomous_generator._flow.templates


def test_autonomous_continue_current_goal_does_not_remap_to_legacy_keyspace(autonomous_generator):
    context = _make_context(
        context_envelope=SimpleNamespace(repeated_question="question_features"),
    )

    template_key = autonomous_generator._select_template_key(
        context["intent"],
        "continue_current_goal",
        context,
    )

    assert template_key == "continue_current_goal"
    assert not template_key.startswith("spin_")
    assert template_key != "answer_with_knowledge"


def test_autonomous_get_template_hard_fails_without_python_or_base_fallback(monkeypatch):
    flow = _AutonomousFlowStub(
        {
            "continue_current_goal": {
                "template": "FLOW CONTINUE TEMPLATE",
            }
        }
    )
    gen = ResponseGenerator(llm=Mock(), flow=flow)
    monkeypatch.setitem(generator_module.PROMPT_TEMPLATES, "close", "LEGACY CLOSE TEMPLATE")
    monkeypatch.setitem(
        generator_module.PROMPT_TEMPLATES,
        "continue_current_goal",
        "LEGACY CONTINUE TEMPLATE",
    )

    with pytest.raises(TemplateConfigurationError, match="close"):
        gen._get_template("close")


@pytest.mark.parametrize("template_key", sorted(CANONICAL_AUTONOMOUS_TEMPLATE_KEYS))
def test_autonomous_flow_contains_non_empty_template_bodies(autonomous_flow, template_key):
    template = autonomous_flow.get_template(template_key)

    assert template_key in autonomous_flow.templates
    assert template.strip()


def test_autonomous_missing_template_keeps_requested_key_in_generation_meta(monkeypatch):
    llm = Mock()
    llm.generate.return_value = "OK"
    flow = _AutonomousFlowStub(
        {
            "continue_current_goal": {
                "template": "FLOW CONTINUE TEMPLATE",
            }
        }
    )
    gen = ResponseGenerator(llm=llm, flow=flow)

    monkeypatch.setattr(
        "src.generator.get_retriever",
        lambda: SimpleNamespace(
            kb=SimpleNamespace(company_name="Wipon", company_description="Retail automation")
        ),
    )
    monkeypatch.setattr(gen, "_get_template", lambda _key: "{system}")

    gen.generate(
        "close",
        _make_context(
            intent="request_contract",
            state="autonomous_closing",
        ),
    )

    assert gen.get_last_generation_meta()["selected_template_key"] == "close"
