"""
Regression tests for BUG #4: Objection metrics chain (Nodes 1-2-3).
"""

import logging
import sys
import types
from unittest.mock import MagicMock

from src.classifier.refinement_layers import ObjectionRefinementLayerAdapter
from src.classifier.refinement_pipeline import RefinementContext
from src.intent_tracker import IntentTracker
from src.simulator.client_agent import ClientAgent, OBJECTION_INJECTIONS
from src.simulator.personas import PERSONAS, Persona
from src.simulator.runner import SimulationRunner


def test_node2_all_persona_preferred_objection_keys_exist_in_injection_dict():
    missing_by_persona = {}

    for persona_key, persona in PERSONAS.items():
        missing = sorted(
            key for key in persona.preferred_objections
            if key not in OBJECTION_INJECTIONS
        )
        if missing:
            missing_by_persona[persona_key] = missing

    assert not missing_by_persona, (
        "Some personas reference objection keys missing in OBJECTION_INJECTIONS: "
        f"{missing_by_persona}"
    )


def test_node2_unknown_objection_key_logs_warning_and_skips_injection(caplog):
    llm = MagicMock()
    persona = Persona(
        name="Broken Persona",
        description="Test persona with invalid objection key",
        max_turns=5,
        objection_probability=1.0,
        preferred_objections=["missing_key"],
        conversation_starters=["Привет"],
    )
    agent = ClientAgent(llm, persona)

    with caplog.at_level(logging.WARNING):
        response = agent._inject_objection("базовый ответ")

    assert response == "базовый ответ"
    assert agent.get_summary()["objections"] == 0
    assert "Broken Persona" in caplog.text
    assert "missing_key" in caplog.text


def test_node3_question_marker_does_not_refine_highish_confidence_objection():
    adapter = ObjectionRefinementLayerAdapter()
    ctx = RefinementContext(
        message="дорого. скидка есть?",
        state="handle_objection",
        intent="objection_price",
        confidence=0.82,
    )

    result = adapter.refine(
        ctx.message,
        {"intent": "objection_price", "confidence": 0.82},
        ctx,
    )

    assert result.refined is False
    assert result.intent == "objection_price"


def test_node3_question_marker_refines_low_confidence_objection_to_question():
    adapter = ObjectionRefinementLayerAdapter()
    ctx = RefinementContext(
        message="Сколько стоит?",
        state="handle_objection",
        intent="objection_price",
        confidence=0.55,
    )

    result = adapter.refine(
        ctx.message,
        {"intent": "objection_price", "confidence": 0.55},
        ctx,
    )

    assert result.refined is True
    assert result.intent == "price_question"
    assert result.refinement_reason == "question_markers"


def test_node3_hard_ceiling_prevents_any_refinement():
    adapter = ObjectionRefinementLayerAdapter()
    ctx = RefinementContext(
        message="Это дорого?",
        state="handle_objection",
        intent="objection_price",
        confidence=0.95,
    )

    result = adapter.refine(
        ctx.message,
        {"intent": "objection_price", "confidence": 0.95},
        ctx,
    )

    assert result.refined is False
    assert result.intent == "objection_price"


def test_node1_intent_tracker_moves_pending_objections_to_handled_on_non_objection():
    tracker = IntentTracker()
    tracker.record("objection_price", "handle_objection")
    tracker.record("objection_competitor", "handle_objection")
    tracker.record("objection_no_time", "handle_objection")
    tracker.record("agreement", "close")

    assert tracker.objection_total() == 3
    assert tracker.objection_handled_total() == 3
    assert tracker.to_dict()["pending_objections"] == 0


def test_node1_intent_tracker_keeps_pending_when_conversation_ends_on_objection_streak():
    tracker = IntentTracker()
    tracker.record("objection_price", "handle_objection")
    tracker.record("objection_competitor", "handle_objection")
    tracker.record("objection_no_time", "handle_objection")

    assert tracker.objection_total() == 3
    assert tracker.objection_handled_total() == 0
    assert tracker.to_dict()["pending_objections"] == 3


def test_node1_intent_tracker_serialization_preserves_pending_and_handled_counters():
    tracker = IntentTracker()
    tracker.record("objection_price", "handle_objection")
    tracker.record("objection_competitor", "handle_objection")
    tracker.record("agreement", "close")
    tracker.record("objection_no_time", "handle_objection")

    serialized = tracker.to_dict()
    restored = IntentTracker.from_dict(serialized)

    assert restored.objection_handled_total() == 2
    assert restored.to_dict()["pending_objections"] == 1
    assert restored.objection_total() == 3


def test_node1_runner_extracts_objection_metrics_from_intent_tracker(monkeypatch):
    class FakeClientAgent:
        def __init__(self, *args, **kwargs):
            self.turn = 0

        def start_conversation(self):
            return "Привет"

        def should_continue(self):
            return False

        def respond(self, _bot_message: str):
            self.turn += 1
            return "ок"

        def get_last_trace(self):
            return None

        def is_budget_exhausted(self):
            return False

        def get_summary(self):
            # Intentionally wrong value to ensure runner uses bot intent_tracker.
            return {"objections": 99, "kb_questions_used": 0, "kb_topics_covered": []}

    tracker = IntentTracker()
    tracker.record("objection_price", "handle_objection")
    tracker.record("agreement", "close")

    class FakeStateMachine:
        def __init__(self):
            self.collected_data = {}
            self.intent_tracker = tracker

    class FakeSalesBot:
        def __init__(self, *args, **kwargs):
            self._flow = None
            self.state_machine = FakeStateMachine()

        def process(self, _client_message: str):
            return {
                "response": "Принято",
                "state": "close",
                "intent": "agreement",
                "action": "close",
                "confidence": 0.9,
                "is_final": True,
            }

        def get_lead_score(self):
            return {"score": 0.0, "temperature": "cold"}

    monkeypatch.setattr("src.simulator.runner.ClientAgent", FakeClientAgent)

    fake_bot_module = types.ModuleType("src.bot")
    fake_bot_module.SalesBot = FakeSalesBot
    monkeypatch.setitem(sys.modules, "src.bot", fake_bot_module)

    runner = SimulationRunner(bot_llm=MagicMock(), client_llm=MagicMock())
    result = runner._run_single(sim_id=1, persona_name="happy_path")

    assert result.objections_count > 0
    assert result.objections_handled > 0
    assert result.objections_count == 1
    assert result.objections_handled == 1
