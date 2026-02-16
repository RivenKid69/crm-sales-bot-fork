"""
Bug #12b: Autonomous flow anti-loop chain fixes.

Covers:
- Fix 0: FactQuestionSource autonomy gate
- Fix 1: Overlay blacklist approach (protected_states)
- Fix 2: consecutive_same_action + repair protection bypass
- Fix 3: Forward-only autonomous transitions with persistent visited states
- Fix 4: Semantic dedup import path fix (module-level get_retriever)
- Fix 5: similarity_threshold from settings + borderline sync
- Fix 6/7: state-revisit oscillation detection and envelope wiring
"""

from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np

from src.blackboard.sources.autonomous_decision import (
    AutonomousDecision,
    AutonomousDecisionSource,
)
from src.blackboard.sources.fact_question import FactQuestionSource
from src.conditions.policy import PolicyContext, is_overlay_allowed
from src.conditions.trace import EvaluationTrace
from src.context_envelope import ContextEnvelope, ContextEnvelopeBuilder
from src.context_window import ContextWindow, TurnContext
from src.dialogue_policy import DialoguePolicy, PolicyDecision
from src import generator as generator_module
from src.generator import ResponseGenerator
from src.yaml_config.constants import (
    PROTECTED_STATES,
    REPAIR_ACTION_REPEAT_THRESHOLD,
)


class _Blackboard:
    def __init__(self, context, current_intent="info_provided"):
        self._context = context
        self.current_intent = current_intent
        self.actions = []
        self.transitions = []

    def get_context(self):
        return self._context

    def propose_action(self, **kwargs):
        self.actions.append(kwargs)

    def propose_transition(self, **kwargs):
        self.transitions.append(kwargs)


class _RetrieverStub:
    def __init__(self):
        self.kb = SimpleNamespace(sections=[])

    def embed_query(self, text):
        if text == "alpha beta gamma":
            return np.array([1.0, 0.0, 0.0])
        if text == "alpha beta gamma delta":
            return np.array([0.95, 0.05, 0.0])
        return np.array([1.0, 0.0, 0.0])


def _build_cw(states, actions=None, intents=None):
    cw = ContextWindow(max_size=20)
    actions = actions or ["continue_current_goal"] * len(states)
    intents = intents or ["info_provided"] * len(states)
    for idx, state in enumerate(states):
        cw.add_turn(
            TurnContext(
                user_message=f"u{idx}",
                bot_response=f"b{idx}",
                intent=intents[idx],
                action=actions[idx],
                state=state,
                next_state=state,
            )
        )
    return cw


class TestFactQuestionAutonomyGate:
    def test_skips_in_autonomous_state(self):
        source = FactQuestionSource()
        ctx = SimpleNamespace(
            state_config={"autonomous": True},
            context_envelope=SimpleNamespace(secondary_intents=[]),
        )
        bb = _Blackboard(ctx, current_intent="question_features")

        with patch.object(source, "_log_contribution") as log_mock:
            assert source.should_contribute(bb) is False
            log_mock.assert_called_once()
            assert "autonomous state uses LLM-driven response" in log_mock.call_args.kwargs["reason"]

    def test_contributes_when_autonomous_false_or_missing(self):
        source = FactQuestionSource()
        ctx_false = SimpleNamespace(
            state_config={"autonomous": False},
            context_envelope=SimpleNamespace(secondary_intents=[]),
        )
        bb_false = _Blackboard(ctx_false, current_intent="question_features")
        assert source.should_contribute(bb_false) is True

        ctx_missing = SimpleNamespace(
            state_config={},
            context_envelope=SimpleNamespace(secondary_intents=[]),
        )
        bb_missing = _Blackboard(ctx_missing, current_intent="question_features")
        assert source.should_contribute(bb_missing) is True


class TestOverlayBlacklistApproach:
    def test_overlay_allowed_for_any_non_protected_state(self):
        assert "escalated" in PROTECTED_STATES

        for state in PROTECTED_STATES:
            ctx = PolicyContext.create_test_context(state=state)
            assert ctx.is_overlay_allowed() is False
            assert is_overlay_allowed(ctx) is False

        for state in ["spin_problem", "autonomous_discovery", "brand_new_state"]:
            ctx = PolicyContext.create_test_context(state=state)
            assert ctx.is_overlay_allowed() is True
            assert is_overlay_allowed(ctx) is True


class TestConsecutiveSameAction:
    def test_counter_and_context_wiring(self):
        cw = _build_cw(
            states=["spin_problem", "spin_problem", "spin_problem", "spin_problem"],
            actions=[
                "ask_question",
                "answer_with_facts",
                "answer_with_facts",
                "answer_with_facts",
            ],
        )
        assert cw.get_consecutive_same_action() == 3

        envelope = ContextEnvelope(consecutive_same_action=3)
        ctx = PolicyContext.from_envelope(envelope, current_action="answer_with_facts")
        assert ctx.consecutive_same_action == 3

        test_ctx = PolicyContext.create_test_context(consecutive_same_action=2)
        assert test_ctx.consecutive_same_action == 2


class TestRepairProtectionBypass:
    def test_bypass_triggers_when_action_repeats(self):
        policy = DialoguePolicy()
        trace = EvaluationTrace(
            rule_name="policy_override",
            intent="question_features",
            state="spin_problem",
            domain="policy",
        )
        ctx = PolicyContext.create_test_context(
            state="spin_problem",
            current_action="answer_with_facts",
            repeated_question="question_features",
            consecutive_same_action=REPAIR_ACTION_REPEAT_THRESHOLD,
        )

        override = policy._apply_repair_overlay(ctx, sm_result={}, trace=trace)

        assert override is not None
        assert override.action == policy.REPAIR_ACTIONS["repeated_question"]
        assert override.decision == PolicyDecision.REPAIR_CLARIFY
        assert override.signals_used["consecutive_same_action"] == REPAIR_ACTION_REPEAT_THRESHOLD
        assert trace.matched_condition == "repair_protection_bypassed_action_repeat"

    def test_protection_kept_below_threshold(self):
        policy = DialoguePolicy()
        ctx = PolicyContext.create_test_context(
            state="spin_problem",
            current_action="answer_with_facts",
            repeated_question="question_features",
            consecutive_same_action=max(REPAIR_ACTION_REPEAT_THRESHOLD - 1, 0),
        )

        override = policy._apply_repair_overlay(ctx, sm_result={}, trace=None)

        assert override is not None
        assert override.action is None
        assert override.decision == PolicyDecision.REPAIR_SKIPPED
        assert override.signals_used["action_preserved"] == "answer_with_facts"


class TestForwardOnlyTransitions:
    def test_phase_order_chain_with_fallback(self):
        all_states = {
            "autonomous_discovery": {
                "parameters": {
                    "prev_phase_state": "",
                    "next_phase_state": "autonomous_qualification",
                }
            },
            "autonomous_qualification": {
                "parameters": {
                    "prev_phase_state": "autonomous_discovery",
                    "next_phase_state": "autonomous_presentation",
                }
            },
            "autonomous_presentation": {
                "parameters": {
                    "prev_phase_state": "autonomous_qualification",
                    "next_phase_state": "",
                }
            },
            "autonomous_outside_chain": {"parameters": {}},
        }
        order = AutonomousDecisionSource._get_phase_order(all_states)
        assert order["autonomous_discovery"] == 0
        assert order["autonomous_qualification"] == 1
        assert order["autonomous_presentation"] == 2
        assert order["autonomous_outside_chain"] == 3

    def test_persistent_visited_blocks_back_transition(self):
        decision = AutonomousDecision(
            next_state="autonomous_discovery",
            action="autonomous_respond",
            reasoning="go back",
            should_transition=True,
        )
        source = AutonomousDecisionSource(llm=Mock(generate_structured=Mock(return_value=decision)))
        states = {
            "autonomous_discovery": {
                "parameters": {
                    "prev_phase_state": "",
                    "next_phase_state": "autonomous_qualification",
                }
            },
            "autonomous_qualification": {
                "parameters": {
                    "prev_phase_state": "autonomous_discovery",
                    "next_phase_state": "autonomous_presentation",
                }
            },
            "autonomous_presentation": {
                "parameters": {
                    "prev_phase_state": "autonomous_qualification",
                    "next_phase_state": "",
                }
            },
        }
        ctx = SimpleNamespace(
            state="autonomous_qualification",
            state_config={
                "phase": "qualification",
                "goal": "qualify",
                "parameters": {
                    "prev_phase_state": "autonomous_discovery",
                    "next_phase_state": "autonomous_presentation",
                },
            },
            flow_config={"name": "autonomous", "states": states},
            current_intent="agreement",
            user_message="повторю вопрос",
            collected_data={},
            context_envelope=SimpleNamespace(
                consecutive_same_state=2,
                state_history=["autonomous_discovery", "autonomous_qualification"],
            ),
        )
        bb = _Blackboard(ctx)

        source.contribute(bb)

        assert bb.transitions
        assert bb.transitions[-1]["next_state"] == "autonomous_qualification"
        assert "autonomous_stay_invalid_target" in bb.transitions[-1]["reason_code"]

    def test_prev_phase_allowed_once_when_not_visited(self):
        decision = AutonomousDecision(
            next_state="autonomous_discovery",
            action="autonomous_respond",
            reasoning="single rollback",
            should_transition=True,
        )
        source = AutonomousDecisionSource(llm=Mock(generate_structured=Mock(return_value=decision)))
        states = {
            "autonomous_discovery": {
                "parameters": {
                    "prev_phase_state": "",
                    "next_phase_state": "autonomous_qualification",
                }
            },
            "autonomous_qualification": {
                "parameters": {
                    "prev_phase_state": "autonomous_discovery",
                    "next_phase_state": "autonomous_presentation",
                }
            },
            "autonomous_presentation": {
                "parameters": {
                    "prev_phase_state": "autonomous_qualification",
                    "next_phase_state": "",
                }
            },
        }
        ctx = SimpleNamespace(
            state="autonomous_qualification",
            state_config={
                "phase": "qualification",
                "goal": "qualify",
                "parameters": {
                    "prev_phase_state": "autonomous_discovery",
                    "next_phase_state": "autonomous_presentation",
                },
            },
            flow_config={"name": "autonomous", "states": states},
            current_intent="clarification",
            user_message="можно назад",
            collected_data={},
            context_envelope=SimpleNamespace(
                consecutive_same_state=1,
                state_history=["autonomous_qualification"],
            ),
        )
        bb = _Blackboard(ctx)

        source.contribute(bb)

        assert bb.transitions
        assert bb.transitions[-1]["next_state"] == "autonomous_discovery"
        assert "autonomous_transition" in bb.transitions[-1]["reason_code"]


class TestStateRevisitOscillation:
    def test_detect_patterns(self):
        assert _build_cw(["A", "B", "A", "B"]).detect_state_oscillation() is True
        assert _build_cw(["A", "B", "C", "A", "B"]).detect_state_oscillation() is True
        assert _build_cw(["A", "B", "A"]).detect_state_oscillation() is False
        assert _build_cw(["A", "B", "C", "D"]).detect_state_oscillation() is False

    def test_envelope_wiring_uses_state_oscillation(self):
        cw = _build_cw(
            states=["autonomous_discovery", "handle_objection", "autonomous_discovery", "handle_objection"],
            intents=["info_provided"] * 4,
        )
        builder = ContextEnvelopeBuilder(context_window=cw, current_intent="info_provided")
        envelope = builder.build()
        assert envelope.has_oscillation is True


class TestSemanticDedupFix:
    def test_semantic_similarity_uses_module_level_retriever_import(self, monkeypatch):
        retriever = _RetrieverStub()
        monkeypatch.setattr("src.generator.get_retriever", lambda: retriever)

        gen = ResponseGenerator(llm=Mock(), flow=None)
        sim = gen._compute_semantic_similarity("alpha beta gamma", "alpha beta gamma")
        assert sim > 0.99


class TestSimilarityThresholdConfig:
    def test_threshold_loaded_from_settings(self, monkeypatch):
        retriever = _RetrieverStub()
        monkeypatch.setattr("src.generator.get_retriever", lambda: retriever)

        gen = ResponseGenerator(llm=Mock(), flow=None)
        assert gen.SIMILARITY_THRESHOLD == 0.65

    def test_borderline_range_uses_configured_threshold(self, monkeypatch):
        retriever = _RetrieverStub()
        monkeypatch.setattr("src.generator.get_retriever", lambda: retriever)
        monkeypatch.setitem(generator_module.settings["generator"], "similarity_threshold", 0.80)
        monkeypatch.setitem(generator_module.settings["category_router"], "enabled", False)

        gen = ResponseGenerator(llm=Mock(), flow=None)
        gen._response_history = ["alpha beta gamma delta"]
        gen._compute_semantic_similarity = Mock(return_value=0.90)

        is_dup = gen._is_duplicate("alpha beta gamma", history=[])
        assert is_dup is True
        gen._compute_semantic_similarity.assert_called()
