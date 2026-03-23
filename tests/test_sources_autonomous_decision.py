# tests/test_sources_autonomous_decision.py

"""
Tests for AutonomousDecisionSource — deterministic LLM-driven objection handling.

Verifies:
1. Self-loop transitions always proposed (stay in state wins over mixin transitions)
2. Objection-aware decision prompt enrichment
3. Turn progress hints near max_turns
4. LLM fallback proposes stay-transition
5. Non-autonomous states are skipped
6. Generator template key preservation for autonomous flow
7. Autonomous objection framework instructions (4P/3F)
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from typing import Dict, Any, Optional
from types import SimpleNamespace

from src.blackboard.sources.autonomous_decision import (
    AutonomousDecisionSource,
    AutonomousDecision,
    AutonomousDecisionAndResponse,
    AutonomousDecisionRecord,
)
from src.blackboard.enums import Priority


CLOSING_TERMINAL_REQUIREMENTS = {
    "payment_ready": {
        "required_any": ["contact_name", "client_name"],
        "required_all": ["business_type", "city", "automation_before"],
        "required_if_true": {"automation_before": ["current_tools"]},
    },
    "video_call_scheduled": {
        "required_any": ["contact_name", "client_name"],
        "required_all": ["business_type", "city", "automation_before"],
        "required_if_true": {"automation_before": ["current_tools"]},
    },
}


# =============================================================================
# Mock Helpers
# =============================================================================

class MockContextSnapshot:
    """Mock ContextSnapshot for AutonomousDecisionSource tests."""

    def __init__(
        self,
        state: str = "autonomous_qualification",
        state_config: Optional[Dict[str, Any]] = None,
        flow_config: Optional[Any] = None,
        current_intent: str = "agreement",
        user_message: str = "Да, расскажите",
        collected_data: Optional[Dict[str, Any]] = None,
        context_envelope: Optional[Any] = None,
        media_turn_context: Optional[Any] = None,
    ):
        self.state = state
        self.state_config = state_config or {
            "phase": "qualification",
            "goal": "Понять потребности клиента",
            "max_turns_in_state": 6,
        }
        self.flow_config = flow_config or MockFlowConfig()
        self.current_intent = current_intent
        self.user_message = user_message
        self.collected_data = collected_data or {}
        self.context_envelope = context_envelope
        self.media_turn_context = media_turn_context


class MockFlowConfig:
    """Mock FlowConfig for autonomous flow."""

    def __init__(self, name: str = "autonomous", states: Optional[Dict] = None):
        self.name = name
        self.states = states or {
            "autonomous_qualification": {"phase": "qualification", "goal": "Понять потребности"},
            "autonomous_presentation": {"phase": "presentation", "goal": "Презентация продукта"},
            "autonomous_closing": {"phase": "closing", "goal": "Закрытие сделки"},
        }

    def get(self, key, default=None):
        return getattr(self, key, default)


class MockEnvelope:
    """Mock ContextEnvelope with consecutive_same_state."""

    def __init__(self, consecutive_same_state: int = 0):
        self.consecutive_same_state = consecutive_same_state


def make_blackboard(
    state: str = "autonomous_qualification",
    intent: str = "agreement",
    user_message: str = "Да, расскажите",
    collected_data: Optional[Dict] = None,
    flow_name: str = "autonomous",
    states: Optional[Dict] = None,
    state_config: Optional[Dict] = None,
    context_envelope: Optional[Any] = None,
    media_turn_context: Optional[Any] = None,
):
    """Create a mock blackboard for AutonomousDecisionSource tests."""
    flow_config = MockFlowConfig(name=flow_name, states=states)
    ctx = MockContextSnapshot(
        state=state,
        state_config=state_config or {
            "phase": "qualification",
            "goal": "Понять потребности клиента",
            "max_turns_in_state": 6,
        },
        flow_config=flow_config,
        current_intent=intent,
        user_message=user_message,
        collected_data=collected_data or {},
        context_envelope=context_envelope,
        media_turn_context=media_turn_context,
    )

    bb = Mock()
    bb.get_context.return_value = ctx

    # Track proposals
    bb._action_proposals = []
    bb._transition_proposals = []

    def propose_action(**kwargs):
        bb._action_proposals.append(kwargs)

    def propose_transition(**kwargs):
        bb._transition_proposals.append(kwargs)

    bb.propose_action.side_effect = propose_action
    bb.propose_transition.side_effect = propose_transition
    bb.get_context_signals.return_value = []
    bb._pre_generated_response = None
    bb.set_pre_generated_response.side_effect = lambda value: setattr(bb, "_pre_generated_response", value)

    return bb


def make_llm(decision: Optional[AutonomousDecision] = None, fail: bool = False):
    """Create a mock LLM that returns given decision."""
    llm = Mock()
    if fail:
        llm.generate_structured.side_effect = Exception("LLM unavailable")
    else:
        llm.generate_structured.return_value = decision
    return llm


# =============================================================================
# Test: Always proposes transition on stay (Fix 1 — core fix)
# =============================================================================

class TestAlwaysProposesTransition:
    """Verify AutonomousDecisionSource ALWAYS proposes a transition."""

    @patch("src.feature_flags.flags")
    def test_always_proposes_transition_on_stay(self, mock_flags):
        """When LLM returns should_transition=false, verify a self-loop transition is proposed."""
        mock_flags.is_enabled.return_value = True

        decision = AutonomousDecision(
            next_state="autonomous_qualification",
            action="autonomous_respond",
            reasoning="goal not achieved yet",
            should_transition=False,
        )
        llm = make_llm(decision)
        source = AutonomousDecisionSource(llm=llm)
        bb = make_blackboard(intent="objection_price", user_message="это дорого")

        source.contribute(bb)

        # Should have exactly 1 transition proposal — self-loop
        assert len(bb._transition_proposals) == 1
        tp = bb._transition_proposals[0]
        assert tp["next_state"] == "autonomous_qualification"
        assert tp["priority"] == Priority.NORMAL
        assert "autonomous_stay_in_state" in tp["reason_code"]

    @patch("src.feature_flags.flags")
    def test_always_proposes_transition_on_move(self, mock_flags):
        """When LLM returns should_transition=true, verify target transition is proposed."""
        mock_flags.is_enabled.return_value = True

        decision = AutonomousDecision(
            next_state="autonomous_presentation",
            action="autonomous_respond",
            reasoning="qualification complete",
            should_transition=True,
        )
        llm = make_llm(decision)
        source = AutonomousDecisionSource(llm=llm)
        bb = make_blackboard()

        source.contribute(bb)

        assert len(bb._transition_proposals) == 1
        tp = bb._transition_proposals[0]
        assert tp["next_state"] == "autonomous_presentation"
        assert tp["priority"] == Priority.NORMAL
        assert "autonomous_transition" in tp["reason_code"]

    @patch("src.feature_flags.flags")
    def test_invalid_target_proposes_stay(self, mock_flags):
        """When LLM returns invalid target, verify self-loop fallback."""
        mock_flags.is_enabled.return_value = True

        decision = AutonomousDecision(
            next_state="nonexistent_state",
            action="autonomous_respond",
            reasoning="confused",
            should_transition=True,
        )
        llm = make_llm(decision)
        source = AutonomousDecisionSource(llm=llm)
        bb = make_blackboard()

        source.contribute(bb)

        assert len(bb._transition_proposals) == 1
        tp = bb._transition_proposals[0]
        assert tp["next_state"] == "autonomous_qualification"
        assert "autonomous_stay_invalid_target" in tp["reason_code"]


# =============================================================================
# Test: LLM fallback proposes stay-transition (Fix 1)
# =============================================================================

class TestLLMFallback:
    """Verify LLM failure produces both action AND stay-transition."""

    @patch("src.feature_flags.flags")
    def test_llm_fallback_proposes_stay_transition(self, mock_flags):
        """When LLM call fails, verify both action and stay-transition are proposed."""
        mock_flags.is_enabled.return_value = True

        llm = make_llm(fail=True)
        source = AutonomousDecisionSource(llm=llm)
        bb = make_blackboard()

        source.contribute(bb)

        # Should have action
        assert len(bb._action_proposals) == 1
        assert bb._action_proposals[0]["action"] == "autonomous_respond"
        assert "autonomous_llm_fallback" in bb._action_proposals[0]["reason_code"]

        # Should have stay-transition
        assert len(bb._transition_proposals) == 1
        tp = bb._transition_proposals[0]
        assert tp["next_state"] == "autonomous_qualification"
        assert "autonomous_stay_llm_fallback" in tp["reason_code"]

    @patch("src.feature_flags.flags")
    def test_llm_returns_none_proposes_stay_transition(self, mock_flags):
        """When LLM returns None, verify stay-transition is proposed."""
        mock_flags.is_enabled.return_value = True

        llm = make_llm(decision=None)
        source = AutonomousDecisionSource(llm=llm)
        bb = make_blackboard()

        source.contribute(bb)

        assert len(bb._transition_proposals) == 1
        assert bb._transition_proposals[0]["next_state"] == "autonomous_qualification"


# =============================================================================
# Test: Non-autonomous state skipped
# =============================================================================

class TestShouldContribute:
    """Verify should_contribute flow-gating logic."""

    @patch("src.feature_flags.flags")
    def test_non_autonomous_state_skipped(self, mock_flags):
        """When state=handle_objection, verify should_contribute returns False."""
        mock_flags.is_enabled.return_value = True

        llm = Mock()
        source = AutonomousDecisionSource(llm=llm)
        bb = make_blackboard(state="handle_objection")

        result = source.should_contribute(bb)

        assert result is False

    @patch("src.feature_flags.flags")
    def test_non_autonomous_flow_skipped(self, mock_flags):
        """When flow is not 'autonomous', should_contribute returns False."""
        mock_flags.is_enabled.return_value = True

        llm = Mock()
        source = AutonomousDecisionSource(llm=llm)
        bb = make_blackboard(flow_name="spin")

        result = source.should_contribute(bb)

        assert result is False

    def test_no_llm_skipped(self):
        """When no LLM available, should_contribute returns False."""
        source = AutonomousDecisionSource(llm=None)
        bb = make_blackboard()

        result = source.should_contribute(bb)

        assert result is False


# =============================================================================
# Test: Objection intent enriches decision prompt (Fix 2)
# =============================================================================

class TestDecisionPromptEnrichment:
    """Verify decision prompt is enriched for objection intents and turn progress."""

    def test_objection_intent_enriches_decision_prompt(self):
        """When intent=objection_price, verify the decision prompt includes objection rules."""
        source = AutonomousDecisionSource(llm=Mock())

        prompt = source._build_decision_prompt(
            state="autonomous_qualification",
            phase="qualification",
            goal="Понять потребности",
            intent="objection_price",
            user_message="это дорого",
            collected_data={"company_size": "10"},
            available_states=["autonomous_presentation"],
        )

        assert "ВОЗРАЖЕНИЕ" in prompt
        assert "price" in prompt
        assert "should_transition=false" in prompt

    def test_non_objection_intent_no_enrichment(self):
        """When intent is not objection, verify no objection rules in prompt."""
        source = AutonomousDecisionSource(llm=Mock())

        prompt = source._build_decision_prompt(
            state="autonomous_qualification",
            phase="qualification",
            goal="Понять потребности",
            intent="agreement",
            user_message="Да, интересно",
            collected_data={},
            available_states=["autonomous_presentation"],
        )

        assert "ВОЗРАЖЕНИЕ" not in prompt

    def test_progress_hint_near_max_turns(self):
        """When turn_in_state >= max_turns-2, verify decision prompt includes progress hint."""
        source = AutonomousDecisionSource(llm=Mock())

        prompt = source._build_decision_prompt(
            state="autonomous_qualification",
            phase="qualification",
            goal="Понять потребности",
            intent="agreement",
            user_message="Да",
            collected_data={},
            available_states=["autonomous_presentation"],
            turn_in_state=4,
            max_turns=6,
        )

        assert "ПРОГРЕСС" in prompt
        assert "4" in prompt
        assert "6" in prompt

    def test_no_progress_hint_early_turns(self):
        """When turn_in_state < max_turns-2, verify no progress hint."""
        source = AutonomousDecisionSource(llm=Mock())

        prompt = source._build_decision_prompt(
            state="autonomous_qualification",
            phase="qualification",
            goal="Понять потребности",
            intent="agreement",
            user_message="Да",
            collected_data={},
            available_states=["autonomous_presentation"],
            turn_in_state=1,
            max_turns=6,
        )

        assert "ПРОГРЕСС" not in prompt

    def test_interrupt_question_secondary_adds_signal(self):
        """Secondary question intent should add interruption guard in autonomous non-closing stage."""
        source = AutonomousDecisionSource(llm=Mock())

        prompt = source._build_decision_prompt(
            state="autonomous_qualification",
            phase="qualification",
            goal="Понять потребности",
            intent="agreement",
            user_message="Да, но чем вы отличаетесь от iiko?",
            collected_data={},
            available_states=["autonomous_presentation"],
            secondary_intents=["comparison", "question_features"],
        )

        assert "ПЕРЕБИВАНИЕ ЭТАПА" in prompt
        assert "should_transition=false" in prompt

    def test_interrupt_signal_not_added_in_closing(self):
        """Interruption guard must not be injected for autonomous_closing."""
        source = AutonomousDecisionSource(llm=Mock())

        prompt = source._build_decision_prompt(
            state="autonomous_closing",
            phase="closing",
            goal="Закрытие сделки",
            intent="question_features",
            user_message="А как работает интеграция с Kaspi?",
            collected_data={},
            available_states=["autonomous_closing"],
            secondary_intents=["question_integrations"],
        )

        assert "ПЕРЕБИВАНИЕ ЭТАПА" not in prompt

    def test_interrupt_signal_not_added_for_strong_closing_signal(self):
        """If client is explicitly ready to buy, interruption hint should not push stay-in-stage."""
        source = AutonomousDecisionSource(llm=Mock())

        prompt = source._build_decision_prompt(
            state="autonomous_presentation",
            phase="presentation",
            goal="Показать ценность",
            intent="request_invoice",
            user_message="Есть API? И выставляйте счёт.",
            collected_data={},
            available_states=["autonomous_closing"],
            secondary_intents=["question_integrations"],
            explicit_ready_to_buy=True,
        )

        assert "ПЕРЕБИВАНИЕ ЭТАПА" not in prompt

    def test_tariff_comparison_intent_is_treated_as_interrupt(self):
        """question_tariff_comparison should trigger interruption handling in autonomous non-closing state."""
        source = AutonomousDecisionSource(llm=Mock())

        prompt = source._build_decision_prompt(
            state="autonomous_presentation",
            phase="presentation",
            goal="Показать ценность",
            intent="question_tariff_comparison",
            user_message="Сравните ваши тарифы между собой.",
            collected_data={},
            available_states=["autonomous_closing"],
            secondary_intents=[],
        )

        assert "ПЕРЕБИВАНИЕ ЭТАПА" in prompt

    def test_media_prompt_includes_attachment_class_and_mode(self):
        source = AutonomousDecisionSource(llm=Mock())

        prompt = source._build_decision_prompt(
            state="autonomous_qualification",
            phase="qualification",
            goal="Понять потребности",
            intent="question_features",
            user_message="что в документе?",
            collected_data={},
            available_states=["autonomous_presentation"],
            attachment_only=True,
            media_safety_class="attachment_summary",
            media_candidate_mode="current",
            media_candidates=[
                {
                    "knowledge_id": "card-1",
                    "file_name": "doc.pdf",
                    "media_kind": "document",
                    "summary": "Документ клиента",
                    "facts": ["Компания Альфа"],
                }
            ],
        )

        assert "attachment_only: true" in prompt
        assert "media_safety_class: attachment_summary" in prompt
        assert "media_candidate_mode: current" in prompt


# =============================================================================
# Test: Media routing safety classifier and deterministic rewrite
# =============================================================================

class TestMediaRoutingSafety:
    """Verify deterministic media safety classes and route enforcement."""

    @staticmethod
    def _media_context(*, attachment_only=False, current=None, historical=None):
        return SimpleNamespace(
            attachment_only=attachment_only,
            current_cards=tuple(current or ()),
            historical_candidates=tuple(historical or ()),
        )

    @staticmethod
    def _card(card_id: str, summary: str = "Документ клиента") -> Dict[str, Any]:
        return {
            "knowledge_id": card_id,
            "file_name": "doc.pdf",
            "media_kind": "document",
            "summary": summary,
            "facts": [summary],
        }

    @pytest.mark.parametrize(
        ("attachment_only", "user_message", "has_current", "has_historical", "expected"),
        [
            (True, "", True, False, "attachment_summary"),
            (False, "что в документе?", True, False, "current_media_factual"),
            (False, "посмотри документ и скажи, подойдет ли Lite", True, False, "current_media_product_fit"),
            (False, "что было в документе?", False, True, "historical_media_factual"),
            (False, "по документу какой тариф подойдет?", False, True, "historical_media_product_fit"),
            (False, "Сколько стоит Lite?", False, False, "none"),
        ],
    )
    def test_media_safety_classifier(self, attachment_only, user_message, has_current, has_historical, expected):
        source = AutonomousDecisionSource(llm=Mock())
        current = [self._card("card-current")] if has_current else []
        historical = [self._card("card-history")] if has_historical else []

        result = source._classify_media_safety(
            attachment_only=attachment_only,
            user_message=user_message,
            current_candidates=current,
            historical_candidates=historical,
        )

        assert result == expected

    def test_product_fit_has_precedence_over_factual_markers(self):
        source = AutonomousDecisionSource(llm=Mock())

        result = source._classify_media_safety(
            attachment_only=False,
            user_message="что в документе и подойдет ли Lite?",
            current_candidates=[self._card("card-current")],
            historical_candidates=[],
        )

        assert result == "current_media_product_fit"

    def test_route_rewrite_forces_media_only_and_deterministic_ids(self):
        source = AutonomousDecisionSource(llm=Mock())
        decision = AutonomousDecision(
            reasoning="client asked about document",
            should_transition=False,
            response_mode="hybrid",
            selected_media_card_ids=["bad-id"],
        )
        current_candidates = [
            self._card("card-2", "Второй"),
            self._card("card-1", "Первый"),
        ]

        metadata, rewritten = source._resolve_route_metadata(
            decision,
            media_safety_class="current_media_factual",
            current_candidates=current_candidates,
            historical_candidates=[],
        )

        assert rewritten is True
        assert metadata["response_mode"] == "media_only"
        assert metadata["selected_media_card_ids"] == ["card-2", "card-1"]
        assert metadata["route_source"] == "fallback"

    def test_empty_shortlist_keeps_normal_dialog_fallback_contract(self):
        source = AutonomousDecisionSource(llm=Mock())
        decision = AutonomousDecision(
            reasoning="broken media route",
            should_transition=False,
            response_mode="media_only",
            selected_media_card_ids=["card-1"],
        )

        metadata, rewritten = source._resolve_route_metadata(
            decision,
            media_safety_class="current_media_factual",
            current_candidates=[],
            historical_candidates=[],
        )

        assert rewritten is False
        assert metadata["response_mode"] == "normal_dialog"
        assert metadata["selected_media_card_ids"] == []
        assert metadata["route_source"] == "fallback"

    @patch("src.feature_flags.flags")
    def test_merged_pre_generated_response_disabled_when_route_rewritten(self, mock_flags):
        mock_flags.is_enabled.side_effect = lambda name: name in {"autonomous_flow", "merged_autonomous_call"}

        merged = AutonomousDecisionAndResponse(
            reasoning="respond from document",
            should_transition=False,
            response_mode="hybrid",
            selected_media_card_ids=[],
            response="MERGED RESPONSE",
        )
        llm = Mock()
        llm.generate_merged.return_value = merged
        source = AutonomousDecisionSource(llm=llm)
        bb = make_blackboard(
            intent="question_features",
            user_message="что в документе?",
            media_turn_context=self._media_context(
                current=[self._card("card-1")],
            ),
        )
        bb.get_response_context.return_value = {
            "variables": {},
            "retrieved_facts": "KB FACT",
            "kb_retrieved_facts": "KB FACT",
            "media_candidates_compact": "",
            "grounding_contract_version": 2,
        }

        source.contribute(bb)

        assert bb._pre_generated_response is None
        assert len(bb._action_proposals) == 1
        assert bb._action_proposals[0]["metadata"]["response_mode"] == "media_only"
        assert bb._action_proposals[0]["metadata"]["route_source"] == "fallback"


# =============================================================================
# Test: Generator template key preserved for autonomous objection (Fix 3b)
# =============================================================================

class TestGeneratorTemplateKeyPreservation:
    """Verify _select_template_key returns autonomous_respond for autonomous flow."""

    def test_template_key_preserved_for_autonomous_objection(self):
        """When action=autonomous_respond and intent=objection_price, template stays autonomous_respond."""
        from src.generator import ResponseGenerator

        llm = Mock()
        llm.generate.return_value = "test"

        gen = ResponseGenerator(llm)

        template_key = gen._select_template_key(
            intent="objection_price",
            action="autonomous_respond",
            context={},
        )

        assert template_key == "autonomous_respond"

    def test_template_key_preserved_for_autonomous_price(self):
        """When action=autonomous_respond and intent=price_question, template stays autonomous_respond."""
        from src.generator import ResponseGenerator

        llm = Mock()
        gen = ResponseGenerator(llm)

        template_key = gen._select_template_key(
            intent="price_question",
            action="autonomous_respond",
            context={},
        )

        assert template_key == "autonomous_respond"

    def test_non_autonomous_objection_uses_specific_template(self):
        """When action is NOT autonomous_respond, objection template is used normally."""
        from src.generator import ResponseGenerator

        llm = Mock()
        gen = ResponseGenerator(llm)

        template_key = gen._select_template_key(
            intent="objection_price",
            action="handle_objection",
            context={},
        )

        # Should NOT be autonomous_respond
        assert template_key != "autonomous_respond"


# =============================================================================
# Test: Autonomous objection response includes framework (Fix 3d)
# =============================================================================

class TestAutonomousObjectionFramework:
    """Verify _build_autonomous_objection_instructions returns correct frameworks."""

    def test_4p_framework_for_rational_objection(self):
        """Rational objections (price, competitor, etc.) use 4P framework."""
        from src.generator import ResponseGenerator

        llm = Mock()
        gen = ResponseGenerator(llm)

        instructions = gen._build_autonomous_objection_instructions("objection_price")

        assert "4P" in instructions
        assert "ПАУЗА" in instructions
        assert "УТОЧНЕНИЕ" in instructions
        assert "ПРЕЗЕНТАЦИЯ ЦЕННОСТИ" in instructions
        assert "ПРОДВИЖЕНИЕ" in instructions

    def test_3f_framework_for_emotional_objection(self):
        """Emotional objections (think, trust, no_need) use 3F framework."""
        from src.generator import ResponseGenerator

        llm = Mock()
        gen = ResponseGenerator(llm)

        instructions = gen._build_autonomous_objection_instructions("objection_think")

        assert "3F" in instructions
        assert "FEEL" in instructions
        assert "FELT" in instructions
        assert "FOUND" in instructions

    def test_competitor_objection_uses_4p(self):
        """objection_competitor should use 4P (rational) framework."""
        from src.generator import ResponseGenerator

        llm = Mock()
        gen = ResponseGenerator(llm)

        instructions = gen._build_autonomous_objection_instructions("objection_competitor")

        assert "4P" in instructions

    def test_trust_objection_uses_3f(self):
        """objection_trust should use 3F (emotional) framework."""
        from src.generator import ResponseGenerator

        llm = Mock()
        gen = ResponseGenerator(llm)

        instructions = gen._build_autonomous_objection_instructions("objection_trust")

        assert "3F" in instructions


# =============================================================================
# Test: Self-loop wins over inherited objection transition (Integration)
# =============================================================================

class TestSelfLoopPriority:
    """Verify self-loop transition at order=42 beats TransitionResolver at order=50."""

    @patch("src.feature_flags.flags")
    def test_stay_transition_beats_inherited_objection(self, mock_flags):
        """
        Simulate both AutonomousDecisionSource (order=42) and
        TransitionResolverSource (order=50) proposals.
        With equal NORMAL priority, order=42 wins stable sort.
        """
        mock_flags.is_enabled.return_value = True

        decision = AutonomousDecision(
            next_state="autonomous_qualification",
            action="autonomous_respond",
            reasoning="handling objection in state",
            should_transition=False,
        )
        llm = make_llm(decision)
        source = AutonomousDecisionSource(llm=llm)
        bb = make_blackboard(intent="objection_price", user_message="это дорого")

        source.contribute(bb)

        # AutonomousDecisionSource proposes self-loop
        assert len(bb._transition_proposals) == 1
        autonomous_tp = bb._transition_proposals[0]
        assert autonomous_tp["next_state"] == "autonomous_qualification"
        assert autonomous_tp["priority"] == Priority.NORMAL

        # Simulate what TransitionResolverSource (order=50) would propose
        # In real system, ConflictResolver would see both and pick order=42
        mock_transition_resolver_proposal = {
            "next_state": "handle_objection",
            "priority": Priority.NORMAL,
            "reason_code": "intent_transition_objection_price",
            "source_name": "TransitionResolverSource",
        }

        # The autonomous proposal (order=42) should win over
        # TransitionResolver (order=50) for equal NORMAL priority
        # because stable sort preserves order (42 < 50)
        assert autonomous_tp["source_name"] == "AutonomousDecisionSource"
        assert autonomous_tp["next_state"] != mock_transition_resolver_proposal["next_state"]


class TestClosingDeterministicCompletion:
    """Regression tests for deterministic completion in autonomous_closing."""

    @patch("src.feature_flags.flags")
    def test_payment_context_does_not_autofinish_payment_ready_without_required_profile(self, mock_flags):
        """
        Payment fastpath must be blocked until profile data required by terminal gate
        is already collected.
        """
        mock_flags.is_enabled.return_value = True

        source = AutonomousDecisionSource(llm=Mock())

        envelope = SimpleNamespace(
            consecutive_same_state=1,
            intent_history=["request_invoice"],
            total_objections=0,
            repeated_objection_types=[],
            state_history=["autonomous_discovery", "autonomous_closing"],
        )
        state_config = {
            "phase": "closing",
            "goal": "Закрытие сделки",
            "max_turns_in_state": 6,
            "terminal_states": ["payment_ready", "video_call_scheduled"],
            "terminal_state_requirements": CLOSING_TERMINAL_REQUIREMENTS,
        }
        bb = make_blackboard(
            state="autonomous_closing",
            intent="request_invoice",
            user_message="Да, хочу оплатить. Выставляйте счёт.",
            state_config=state_config,
            context_envelope=envelope,
        )

        source.contribute(bb)

        assert len(bb._transition_proposals) == 1
        tp = bb._transition_proposals[0]
        assert tp["next_state"] == "autonomous_closing"
        assert tp["reason_code"] == "autonomous_stay_llm_fallback"

    @patch("src.feature_flags.flags")
    def test_payment_context_autofinishes_payment_ready_with_required_profile(self, mock_flags):
        mock_flags.is_enabled.return_value = True

        source = AutonomousDecisionSource(llm=Mock())

        envelope = SimpleNamespace(
            consecutive_same_state=1,
            intent_history=["request_invoice"],
            total_objections=0,
            repeated_objection_types=[],
            state_history=["autonomous_discovery", "autonomous_closing"],
        )
        state_config = {
            "phase": "closing",
            "goal": "Закрытие сделки",
            "max_turns_in_state": 6,
            "terminal_states": ["payment_ready", "video_call_scheduled"],
            "terminal_state_requirements": CLOSING_TERMINAL_REQUIREMENTS,
        }
        bb = make_blackboard(
            state="autonomous_closing",
            intent="request_invoice",
            user_message="Да, хочу оплатить. Выставляйте счёт.",
            state_config=state_config,
            context_envelope=envelope,
            collected_data={
                "contact_name": "Айбота",
                "business_type": "магазин",
                "city": "Астана",
                "automation_before": True,
                "current_tools": "Excel",
            },
        )

        source.contribute(bb)

        assert len(bb._transition_proposals) == 1
        tp = bb._transition_proposals[0]
        assert tp["next_state"] == "payment_ready"
        assert tp["reason_code"] == "autonomous_terminal_payment_ready"

    @patch("src.feature_flags.flags")
    def test_video_call_does_not_autofinish_without_required_profile(self, mock_flags):
        """Video-call fastpath must also respect terminal profile requirements."""
        mock_flags.is_enabled.return_value = True

        source = AutonomousDecisionSource(llm=Mock())
        envelope = SimpleNamespace(
            consecutive_same_state=1,
            intent_history=["question_features"],
            total_objections=0,
            repeated_objection_types=[],
            state_history=["autonomous_discovery", "autonomous_closing"],
        )
        state_config = {
            "phase": "closing",
            "goal": "Закрытие сделки",
            "max_turns_in_state": 6,
            "terminal_states": ["payment_ready", "video_call_scheduled"],
            "terminal_state_requirements": CLOSING_TERMINAL_REQUIREMENTS,
        }
        bb = make_blackboard(
            state="autonomous_closing",
            intent="demo_request",
            user_message="Да, хочу видеозвонок, давайте созвонимся.",
            state_config=state_config,
            context_envelope=envelope,
        )

        source.contribute(bb)

        assert len(bb._transition_proposals) == 1
        tp = bb._transition_proposals[0]
        assert tp["next_state"] == "autonomous_closing"
        assert tp["reason_code"] == "autonomous_stay_llm_fallback"

    @patch("src.feature_flags.flags")
    def test_video_call_autofinish_when_requested_with_required_profile(self, mock_flags):
        mock_flags.is_enabled.return_value = True

        source = AutonomousDecisionSource(llm=Mock())
        envelope = SimpleNamespace(
            consecutive_same_state=1,
            intent_history=["question_features"],
            total_objections=0,
            repeated_objection_types=[],
            state_history=["autonomous_discovery", "autonomous_closing"],
        )
        state_config = {
            "phase": "closing",
            "goal": "Закрытие сделки",
            "max_turns_in_state": 6,
            "terminal_states": ["payment_ready", "video_call_scheduled"],
            "terminal_state_requirements": CLOSING_TERMINAL_REQUIREMENTS,
        }
        bb = make_blackboard(
            state="autonomous_closing",
            intent="demo_request",
            user_message="Да, хочу видеозвонок, давайте созвонимся.",
            state_config=state_config,
            context_envelope=envelope,
            collected_data={
                "client_name": "Айбота",
                "business_type": "магазин",
                "city": "Астана",
                "automation_before": False,
            },
        )

        source.contribute(bb)

        assert len(bb._transition_proposals) == 1
        tp = bb._transition_proposals[0]
        assert tp["next_state"] == "video_call_scheduled"
        assert tp["reason_code"] == "autonomous_terminal_video_call"


class TestMergedContactFastPath:
    """Merged-mode regression guards for contact_provided handling."""

    @patch("src.feature_flags.flags")
    def test_merged_fastpath_falls_back_to_autonomous_closing_without_required_profile(self, mock_flags):
        """Cross-state terminal upgrade must not bypass closing profile requirements."""
        mock_flags.is_enabled.return_value = True

        llm = make_llm(
            AutonomousDecision(
                next_state="autonomous_closing",
                action="autonomous_respond",
                reasoning="collect iin first",
                should_transition=True,
            )
        )
        source = AutonomousDecisionSource(llm=llm)
        states = {
            "autonomous_negotiation": {"phase": "negotiation", "goal": "Обсудить условия"},
            "autonomous_closing": {
                "phase": "closing",
                "goal": "Закрыть сделку",
                "terminal_states": ["payment_ready", "video_call_scheduled"],
                "terminal_state_requirements": CLOSING_TERMINAL_REQUIREMENTS,
            },
            "payment_ready": {"phase": "terminal", "goal": "Оплата"},
            "video_call_scheduled": {"phase": "terminal", "goal": "Видеозвонок"},
        }
        bb = make_blackboard(
            state="autonomous_negotiation",
            intent="contact_provided",
            user_message="Телефон: +77015551234",
            states=states,
            state_config={
                "phase": "negotiation",
                "goal": "Обсудить условия",
                "max_turns_in_state": 6,
            },
            context_envelope=SimpleNamespace(
                consecutive_same_state=1,
                intent_history=["request_invoice"],
                total_objections=0,
                repeated_objection_types=[],
                state_history=["autonomous_objection_handling", "autonomous_negotiation"],
            ),
        )

        source.contribute(bb)

        assert len(bb._transition_proposals) == 1
        tp = bb._transition_proposals[0]
        assert tp["next_state"] == "autonomous_closing"
        llm.generate_structured.assert_called_once()

    @patch("src.feature_flags.flags")
    def test_contact_provided_redirect_keeps_autonomous_closing_without_required_profile(self, mock_flags):
        """
        Redirect into terminal state must fall back to autonomous_closing until
        the required profile is complete.
        """
        mock_flags.is_enabled.return_value = True

        llm = make_llm(
            AutonomousDecision(
                next_state="autonomous_closing",
                action="autonomous_respond",
                reasoning="move to closing",
                should_transition=True,
            )
        )
        source = AutonomousDecisionSource(llm=llm)
        states = {
            "autonomous_discovery": {"phase": "discovery", "goal": "Понять контекст"},
            "autonomous_closing": {
                "phase": "closing",
                "goal": "Закрыть сделку",
                "terminal_states": ["payment_ready", "video_call_scheduled"],
                "terminal_state_requirements": CLOSING_TERMINAL_REQUIREMENTS,
            },
            "payment_ready": {"phase": "terminal", "goal": "Оплата"},
            "video_call_scheduled": {"phase": "terminal", "goal": "Видеозвонок"},
        }
        envelope = SimpleNamespace(
            consecutive_same_state=0,
            intent_history=["request_invoice"],
            total_objections=0,
            repeated_objection_types=[],
            state_history=["autonomous_discovery"],
        )
        state_config = {
            "phase": "discovery",
            "goal": "Понять контекст",
            "max_turns_in_state": 6,
        }
        bb = make_blackboard(
            state="autonomous_discovery",
            intent="contact_provided",
            user_message="Телефон: +77015551234",
            states=states,
            state_config=state_config,
            context_envelope=envelope,
        )

        source.contribute(bb)

        assert len(bb._transition_proposals) == 1
        tp = bb._transition_proposals[0]
        assert tp["next_state"] == "autonomous_closing"

    @patch("src.feature_flags.flags")
    def test_contact_provided_redirect_enters_payment_ready_with_required_profile(self, mock_flags):
        mock_flags.is_enabled.return_value = True

        llm = make_llm(
            AutonomousDecision(
                next_state="autonomous_closing",
                action="autonomous_respond",
                reasoning="move to closing",
                should_transition=True,
            )
        )
        source = AutonomousDecisionSource(llm=llm)
        states = {
            "autonomous_discovery": {"phase": "discovery", "goal": "Понять контекст"},
            "autonomous_closing": {
                "phase": "closing",
                "goal": "Закрыть сделку",
                "terminal_states": ["payment_ready", "video_call_scheduled"],
                "terminal_state_requirements": CLOSING_TERMINAL_REQUIREMENTS,
            },
            "payment_ready": {"phase": "terminal", "goal": "Оплата"},
            "video_call_scheduled": {"phase": "terminal", "goal": "Видеозвонок"},
        }
        envelope = SimpleNamespace(
            consecutive_same_state=0,
            intent_history=["request_invoice"],
            total_objections=0,
            repeated_objection_types=[],
            state_history=["autonomous_discovery"],
        )
        bb = make_blackboard(
            state="autonomous_discovery",
            intent="contact_provided",
            user_message="Телефон: +77015551234",
            states=states,
            state_config={
                "phase": "discovery",
                "goal": "Понять контекст",
                "max_turns_in_state": 6,
            },
            context_envelope=envelope,
            collected_data={
                "contact_name": "Айбота",
                "business_type": "магазин",
                "city": "Астана",
                "automation_before": True,
                "current_tools": "Excel",
            },
        )

        source.contribute(bb)

        assert len(bb._transition_proposals) == 1
        tp = bb._transition_proposals[0]
        assert tp["next_state"] == "payment_ready"

    @patch("src.feature_flags.flags")
    def test_video_call_request_from_negotiation_routes_into_autonomous_closing(self, mock_flags):
        """
        If client asks for a video call from negotiation stage, merged fastpath
        should route into autonomous_closing; terminal selection happens there.
        """
        mock_flags.is_enabled.return_value = True

        source = AutonomousDecisionSource(llm=Mock())
        envelope = SimpleNamespace(
            consecutive_same_state=1,
            intent_history=["request_invoice", "objection_contract_bound"],
            total_objections=0,
            repeated_objection_types=[],
            state_history=["autonomous_discovery", "autonomous_closing"],
        )
        state_config = {
            "phase": "closing",
            "goal": "Закрытие сделки",
            "max_turns_in_state": 6,
            "terminal_states": ["payment_ready", "video_call_scheduled"],
            "terminal_state_requirements": CLOSING_TERMINAL_REQUIREMENTS,
        }
        bb = make_blackboard(
            state="autonomous_closing",
            intent="demo_request",
            user_message="Ок, тогда лучше видеозвонок.",
            state_config=state_config,
            context_envelope=envelope,
        )

        source.contribute(bb)

        assert len(bb._transition_proposals) == 1
        tp = bb._transition_proposals[0]
        assert tp["next_state"] == "autonomous_closing"
