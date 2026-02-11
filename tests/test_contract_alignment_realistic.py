"""Realistic integration tests for contract alignment and final response guardrail."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.feature_flags import flags


class _FakeSection:
    def __init__(self, priority: int, facts: str):
        self.priority = priority
        self.facts = facts


class _FakeRetriever:
    def __init__(self) -> None:
        self.kb = SimpleNamespace(
            sections=[_FakeSection(priority=5, facts="Wipon CRM для продаж и автоматизации.")],
            company_name="Wipon",
            company_description="CRM-платформа",
        )

    def get_company_info(self) -> str:
        return "Wipon: CRM-платформа"

    def retrieve_with_urls(self, message: str, intent: str, state: str, categories, top_k: int):
        return ("Стоимость зависит от тарифа и внедрения.", [])


class _ScriptedLLM:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0

    def generate(self, prompt: str) -> str:
        self.calls += 1
        if self._responses:
            return self._responses.pop(0)
        return "По стоимости сориентирую в ₸. Пришлю точный расчет."


class _FakeFlow:
    def __init__(self, templates=None):
        self.name = "test_flow"
        self.templates = templates or {}
        self.phase_order = ["situation"]
        self.post_phases_state = None
        self.phase_mapping = {"situation": "spin_situation"}
        self.simulation_limits = {}

    def get_template(self, key: str):
        return self.templates.get(key)


@pytest.fixture(autouse=True)
def _clear_flags():
    from src.response_boundary_validator import boundary_validator

    flags.clear_all_overrides()
    boundary_validator.reset_metrics()
    yield
    flags.clear_all_overrides()
    boundary_validator.reset_metrics()


def _make_decision(action: str, next_state: str, is_final: bool = False):
    from src.blackboard.models import ResolvedDecision

    decision = ResolvedDecision(action=action, next_state=next_state)
    decision.prev_state = "greeting"
    decision.goal = "test goal"
    decision.collected_data = {}
    decision.missing_data = []
    decision.optional_data = []
    decision.is_final = is_final
    decision.spin_phase = "situation"
    decision.circular_flow = {}
    decision.objection_flow = {}
    return decision


def test_generator_end_to_end_pricing_action_with_brevity_and_boundary_validator(monkeypatch):
    """
    Realistic chain:
    intent=request_brevity + pricing action should keep pricing template,
    then boundary validator should repair currency/typo/punctuation artifacts.
    """
    from src.generator import ResponseGenerator

    flags.set_override("response_deduplication", False)
    flags.set_override("response_diversity", False)
    flags.set_override("apology_system", False)
    flags.set_override("response_boundary_validator", True)
    flags.set_override("response_boundary_retry", True)
    flags.set_override("response_boundary_fallback", True)

    fake_retriever = _FakeRetriever()
    monkeypatch.setattr("src.generator.get_retriever", lambda: fake_retriever)

    llm = _ScriptedLLM(
        responses=[
            "Понимаю. — Стоимость 1000 руб, присылну детали.",
            "Ок, стоимость 1000 ₽. — присылну.",
        ]
    )
    flow = _FakeFlow(
        templates={
            "answer_with_pricing_direct": "Ответь коротко и по фактам. {retrieved_facts}",
            "continue_current_goal": "Продолжай диалог. {retrieved_facts}",
        }
    )
    generator = ResponseGenerator(llm=llm, flow=flow)
    # Exclude category routing call from this scenario to keep llm calls deterministic.
    generator.category_router = None

    context = {
        "intent": "request_brevity",
        "state": "presentation",
        "user_message": "короче и цену сразу",
        "history": [],
        "collected_data": {},
        "missing_data": [],
    }
    response = generator.generate("answer_with_pricing_direct", context)
    meta = generator.get_last_generation_meta()

    assert "руб" not in response.lower()
    assert "₽" not in response
    assert "₸" in response
    assert "присылну" not in response.lower()
    assert "пришлю" in response.lower()
    assert ". —" not in response

    assert meta["requested_action"] == "answer_with_pricing_direct"
    assert meta["selected_template_key"] == "answer_with_pricing_direct"
    stages = [e.get("stage") for e in meta.get("validation_events", [])]
    assert "retry" in stages
    assert llm.calls == 2  # main generation + boundary retry


def test_salesbot_process_realistic_pricing_turn_keeps_contracts(monkeypatch):
    """
    Realistic full turn:
    classifier -> orchestrator decision -> generator with diversity + boundary validator ->
    response + decision_trace + confidence mirror.
    """
    from src.bot import SalesBot
    from src.response_diversity import diversity_engine

    flags.set_override("conversation_guard_in_pipeline", True)
    flags.set_override("tone_analysis", False)
    flags.set_override("lead_scoring", False)
    flags.set_override("objection_handler", False)
    flags.set_override("cta_generator", False)
    flags.set_override("context_full_envelope", False)
    flags.set_override("context_policy_overlays", False)
    flags.set_override("context_response_directives", False)
    flags.set_override("response_deduplication", False)
    flags.set_override("response_diversity", True)
    flags.set_override("apology_system", False)
    flags.set_override("response_boundary_validator", True)
    flags.set_override("response_boundary_retry", False)
    flags.set_override("response_boundary_fallback", True)

    fake_retriever = _FakeRetriever()
    monkeypatch.setattr("src.generator.get_retriever", lambda: fake_retriever)
    monkeypatch.setattr(
        diversity_engine,
        "get_opening",
        lambda category, context=None: "Услышал.",
    )

    llm = _ScriptedLLM(
        responses=["Понимаю. — Стоимость 1000 руб, присылну детали."]
    )
    bot = SalesBot(llm=llm, enable_tracing=True)
    bot.generator.category_router = None

    bot.classifier.classify = Mock(return_value={
        "intent": "request_brevity",
        "confidence": 0.93,
        "extracted_data": {},
        "all_scores": {"request_brevity": 0.93},
    })
    bot._orchestrator.process_turn = Mock(
        return_value=_make_decision("answer_with_pricing_direct", "presentation")
    )

    result = bot.process("короче и цену сразу")

    assert result["action"] == "answer_with_pricing_direct"
    assert result["confidence"] == pytest.approx(0.93)
    assert "руб" not in result["response"].lower()
    assert "₽" not in result["response"]
    assert "₸" in result["response"]
    assert "присылну" not in result["response"].lower()
    assert "пришлю" in result["response"].lower()
    assert ". —" not in result["response"]

    trace = result["decision_trace"]
    assert trace["classification"]["confidence"] == pytest.approx(0.93)
    assert trace["response"]["template_key"] == "answer_with_pricing_direct"
    assert trace["response"]["requested_action"] == "answer_with_pricing_direct"


def test_generator_boundary_metrics_track_realistic_multi_turn_violations(monkeypatch):
    """Boundary metrics should reflect violations/retries across multiple turns."""
    from src.generator import ResponseGenerator
    from src.response_boundary_validator import boundary_validator

    flags.set_override("response_deduplication", False)
    flags.set_override("response_diversity", False)
    flags.set_override("apology_system", False)
    flags.set_override("response_boundary_validator", True)
    flags.set_override("response_boundary_retry", True)
    flags.set_override("response_boundary_fallback", True)

    fake_retriever = _FakeRetriever()
    monkeypatch.setattr("src.generator.get_retriever", lambda: fake_retriever)

    llm = _ScriptedLLM(
        responses=[
            "Цена 1000 руб, присылну детали.",
            "Цена 1000 ₸, пришлю детали.",
            ". — пришлю детали сегодня",
            "Пришлю детали сегодня.",
        ]
    )
    generator = ResponseGenerator(llm=llm)
    generator.category_router = None

    price_context = {
        "intent": "price_question",
        "state": "presentation",
        "user_message": "сколько стоит",
        "history": [],
        "collected_data": {},
        "missing_data": [],
    }
    generic_context = {
        "intent": "info_provided",
        "state": "spin_situation",
        "user_message": "ок",
        "history": [],
        "collected_data": {},
        "missing_data": [],
    }

    response_price = generator.generate("answer_with_pricing_direct", price_context)
    response_generic = generator.generate("continue_current_goal", generic_context)

    assert "руб" not in response_price.lower()
    assert "присылну" not in response_price.lower()
    assert ". —" not in response_generic

    metrics = boundary_validator.get_metrics()
    assert metrics["response_validation.total"] == 2
    assert metrics["response_validation.retry_used"] == 2
    assert metrics["response_validation.fallback_used"] == 0
    assert metrics["response_validation.violations_by_type"]["currency_locale"] == 1
    assert metrics["response_validation.violations_by_type"]["known_typos"] == 1
    assert metrics["response_validation.violations_by_type"]["opening_punctuation"] == 1
    assert llm.calls == 4  # 2x generation + 2x boundary retry


def test_simulation_runner_uses_trace_confidence_and_report_shows_coverage(monkeypatch):
    """Realistic runner flow with mixed confidence sources and report sanity coverage."""
    import src.bot as bot_module
    import src.simulator.runner as runner_module
    from src.simulator.report import ReportGenerator
    from src.simulator.runner import SimulationRunner

    class FakeClientAgent:
        def __init__(self, llm, persona, kb_pool=None, persona_key=None):
            self._idx = 0

        def start_conversation(self):
            return "Привет"

        def should_continue(self):
            return True

        def respond(self, _bot_response):
            self._idx += 1
            return f"message_{self._idx}"

        def get_last_trace(self):
            return None

        def is_budget_exhausted(self):
            return False

        def get_summary(self):
            return {"objections": 0, "kb_questions_used": 0, "kb_topics_covered": []}

    class FakeBot:
        def __init__(self, *args, **kwargs):
            self._turn = 0
            self._flow = _FakeFlow()
            self.state_machine = SimpleNamespace(collected_data={})

        def process(self, _message):
            self._turn += 1
            if self._turn == 1:
                return {
                    "response": "Ответ 1",
                    "state": "greeting",
                    "intent": "greeting",
                    "action": "greet_back",
                    "confidence": 0.10,  # must be ignored in favor of trace confidence
                    "decision_trace": {"classification": {"confidence": 0.91}},
                    "visited_states": ["greeting"],
                    "initial_state": "greeting",
                    "is_final": False,
                }
            if self._turn == 2:
                return {
                    "response": "Ответ 2",
                    "state": "spin_situation",
                    "intent": "info_provided",
                    "action": "continue_current_goal",
                    "confidence": 0.55,  # used as fallback (no trace confidence)
                    "decision_trace": {},
                    "visited_states": ["spin_situation"],
                    "initial_state": "greeting",
                    "is_final": False,
                }
            return {
                "response": "Ответ 3",
                "state": "soft_close",
                "intent": "fallback_close",
                "action": "soft_close",
                # no confidence and no trace -> should become 0.0
                "visited_states": ["soft_close"],
                "initial_state": "spin_situation",
                "is_final": True,
            }

        def get_lead_score(self):
            return {"score": 0.42}

    monkeypatch.setattr(runner_module, "ClientAgent", FakeClientAgent)
    monkeypatch.setattr(bot_module, "SalesBot", FakeBot)

    runner = SimulationRunner(bot_llm=Mock(), client_llm=Mock(), verbose=False)
    result = runner.run_single("happy_path")

    confidences = [t["confidence"] for t in result.dialogue]
    assert confidences == [0.91, 0.55, 0.0]

    report = ReportGenerator()._section_decision_analysis([result])
    assert "Dialogue confidence non-zero coverage: 2/3 (67%)" in report


def test_simulation_runner_preserves_response_trace_template_metadata(monkeypatch):
    """Runner should keep response trace metadata for RCA-friendly reporting."""
    import src.bot as bot_module
    import src.simulator.runner as runner_module
    from src.simulator.runner import SimulationRunner

    class FakeClientAgent:
        def __init__(self, llm, persona, kb_pool=None, persona_key=None):
            self._idx = 0

        def start_conversation(self):
            return "Привет"

        def should_continue(self):
            return True

        def respond(self, _bot_response):
            self._idx += 1
            return f"message_{self._idx}"

        def get_last_trace(self):
            return None

        def is_budget_exhausted(self):
            return False

        def get_summary(self):
            return {"objections": 0, "kb_questions_used": 0, "kb_topics_covered": []}

    class FakeBot:
        def __init__(self, *args, **kwargs):
            self._turn = 0
            self._flow = _FakeFlow()
            self.state_machine = SimpleNamespace(collected_data={})

        def process(self, _message):
            self._turn += 1
            if self._turn == 1:
                return {
                    "response": "Ответ 1",
                    "state": "presentation",
                    "intent": "price_question",
                    "action": "answer_with_pricing_direct",
                    "confidence": 0.10,  # ignored due to trace confidence
                    "decision_trace": {
                        "classification": {"confidence": 0.87},
                        "response": {
                            "template_key": "answer_with_pricing_direct",
                            "requested_action": "answer_with_pricing_direct",
                        },
                    },
                    "visited_states": ["presentation"],
                    "initial_state": "greeting",
                    "is_final": False,
                }
            return {
                "response": "Ответ 2",
                "state": "soft_close",
                "intent": "fallback_close",
                "action": "soft_close",
                "confidence": 0.41,  # used because no trace confidence
                "decision_trace": {
                    "response": {
                        "template_key": "soft_close",
                        "requested_action": "soft_close",
                    }
                },
                "visited_states": ["soft_close"],
                "initial_state": "presentation",
                "is_final": True,
            }

        def get_lead_score(self):
            return {"score": 0.1}

    monkeypatch.setattr(runner_module, "ClientAgent", FakeClientAgent)
    monkeypatch.setattr(bot_module, "SalesBot", FakeBot)

    runner = SimulationRunner(bot_llm=Mock(), client_llm=Mock(), verbose=False)
    result = runner.run_single("happy_path")

    assert [t["confidence"] for t in result.dialogue] == [0.87, 0.41]
    assert result.dialogue[0]["decision_trace"]["response"]["template_key"] == "answer_with_pricing_direct"
    assert result.dialogue[0]["decision_trace"]["response"]["requested_action"] == "answer_with_pricing_direct"
    assert result.decision_traces[1]["response"]["template_key"] == "soft_close"
    assert len(result.decision_traces) == 2


def test_report_warns_when_dialogue_confidence_coverage_is_zero():
    """If all dialogue confidences are 0.0, report should emit explicit warning."""
    from src.simulator.report import ReportGenerator
    from src.simulator.runner import SimulationResult

    result = SimulationResult(
        simulation_id=1,
        persona="happy_path",
        outcome="soft_close",
        turns=2,
        duration_seconds=1.0,
        dialogue=[
            {"turn": 1, "client": "hi", "bot": "hello", "state": "greeting", "intent": "greeting", "action": "greet_back", "confidence": 0.0},
            {"turn": 2, "client": "ok", "bot": "bye", "state": "soft_close", "intent": "fallback_close", "action": "soft_close", "confidence": 0.0},
        ],
        decision_traces=[{"classification": {"confidence": 0.78, "method_used": "llm", "top_intent": "greeting"}}],
    )

    report = ReportGenerator()._section_decision_analysis([result])
    assert "WARNING: dialogue confidence coverage is 0% (all turns are 0.0)" in report
