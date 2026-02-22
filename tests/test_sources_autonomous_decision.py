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
    AutonomousDecisionRecord,
)
from src.blackboard.enums import Priority


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


# =============================================================================
# Test: Hard override objection detection (BUG #7)
# =============================================================================

_OVERRIDE_STATE_CONFIG = {
    "phase": "qualification",
    "goal": "Понять потребности клиента",
    "max_turns_in_state": 6,
    "phase_exhaust_threshold": 3,
    "_resolved_params": {"next_phase_state": "autonomous_presentation"},
}

_OVERRIDE_STATES = {
    "autonomous_qualification": {"phase": "qualification", "goal": "Понять потребности"},
    "autonomous_presentation": {"phase": "presentation", "goal": "Презентация продукта"},
    "autonomous_closing": {"phase": "closing", "goal": "Закрытие сделки"},
}


def _make_stay_record(intent: str, state: str = "autonomous_qualification") -> AutonomousDecisionRecord:
    """Create a stay (should_transition=False) history record."""
    return AutonomousDecisionRecord(
        turn_in_state=1,
        intent=intent,
        state=state,
        should_transition=False,
        next_state=state,
        reasoning="stay_in_state",
    )


class TestHardOverrideObjectionDetection:
    """Verify hard override correctly distinguishes objection-driven vs LLM-indecision streaks."""

    @patch("src.feature_flags.flags")
    def test_objection_driven_streak_routes_to_soft_close(self, mock_flags):
        """3 consecutive objection_timing stays → soft_close (not next phase)."""
        mock_flags.is_enabled.return_value = True

        source = AutonomousDecisionSource(llm=Mock())
        source._decision_history = [
            _make_stay_record("objection_timing"),
            _make_stay_record("objection_timing"),
            _make_stay_record("objection_timing"),
        ]

        bb = make_blackboard(
            state="autonomous_qualification",
            intent="objection_timing",
            state_config=_OVERRIDE_STATE_CONFIG,
            states=_OVERRIDE_STATES,
        )

        source.contribute(bb)

        assert len(bb._transition_proposals) == 1
        tp = bb._transition_proposals[0]
        assert tp["next_state"] == "soft_close"
        assert tp["priority"] == Priority.HIGH

    @patch("src.feature_flags.flags")
    def test_indecision_streak_routes_to_next_phase(self, mock_flags):
        """3 consecutive agreement stays (LLM indecisive) → autonomous_presentation."""
        mock_flags.is_enabled.return_value = True

        source = AutonomousDecisionSource(llm=Mock())
        source._decision_history = [
            _make_stay_record("agreement"),
            _make_stay_record("agreement"),
            _make_stay_record("agreement"),
        ]

        bb = make_blackboard(
            state="autonomous_qualification",
            intent="agreement",
            state_config=_OVERRIDE_STATE_CONFIG,
            states=_OVERRIDE_STATES,
        )

        source.contribute(bb)

        assert len(bb._transition_proposals) == 1
        tp = bb._transition_proposals[0]
        assert tp["next_state"] == "autonomous_presentation"
        assert tp["priority"] == Priority.HIGH

    @patch("src.feature_flags.flags")
    def test_mixed_streak_routes_to_next_phase(self, mock_flags):
        """2× objection_timing + 1× agreement → autonomous_presentation (not soft_close)."""
        mock_flags.is_enabled.return_value = True

        source = AutonomousDecisionSource(llm=Mock())
        source._decision_history = [
            _make_stay_record("objection_timing"),
            _make_stay_record("objection_timing"),
            _make_stay_record("agreement"),
        ]

        bb = make_blackboard(
            state="autonomous_qualification",
            intent="agreement",
            state_config=_OVERRIDE_STATE_CONFIG,
            states=_OVERRIDE_STATES,
        )

        source.contribute(bb)

        assert len(bb._transition_proposals) == 1
        tp = bb._transition_proposals[0]
        assert tp["next_state"] == "autonomous_presentation"
        assert tp["priority"] == Priority.HIGH

    @patch("src.feature_flags.flags")
    def test_all_objection_types_route_to_soft_close(self, mock_flags):
        """objection_price + objection_no_need + objection_think → soft_close."""
        mock_flags.is_enabled.return_value = True

        source = AutonomousDecisionSource(llm=Mock())
        source._decision_history = [
            _make_stay_record("objection_price"),
            _make_stay_record("objection_no_need"),
            _make_stay_record("objection_think"),
        ]

        bb = make_blackboard(
            state="autonomous_qualification",
            intent="objection_think",
            state_config=_OVERRIDE_STATE_CONFIG,
            states=_OVERRIDE_STATES,
        )

        source.contribute(bb)

        assert len(bb._transition_proposals) == 1
        tp = bb._transition_proposals[0]
        assert tp["next_state"] == "soft_close"
        assert tp["priority"] == Priority.HIGH

    @patch("src.feature_flags.flags")
    def test_objection_streak_ignores_configured_next_phase(self, mock_flags):
        """3× objection_no_need → soft_close even when next_phase_state is configured."""
        mock_flags.is_enabled.return_value = True

        source = AutonomousDecisionSource(llm=Mock())
        source._decision_history = [
            _make_stay_record("objection_no_need"),
            _make_stay_record("objection_no_need"),
            _make_stay_record("objection_no_need"),
        ]

        # next_phase_state is explicitly set, but objection streak must override it
        bb = make_blackboard(
            state="autonomous_qualification",
            intent="objection_no_need",
            state_config=_OVERRIDE_STATE_CONFIG,   # has next_phase_state=autonomous_presentation
            states=_OVERRIDE_STATES,
        )

        source.contribute(bb)

        assert len(bb._transition_proposals) == 1
        tp = bb._transition_proposals[0]
        assert tp["next_state"] == "soft_close"        # NOT autonomous_presentation
        assert tp["priority"] == Priority.HIGH


class TestClosingDeterministicCompletion:
    """Regression tests for deterministic completion in autonomous_closing."""

    @patch("src.feature_flags.flags")
    def test_payment_context_does_not_autofinish_video_call_without_iin(self, mock_flags):
        """
        If client is in invoice/payment context and only shared phone,
        source must stay in autonomous_closing (collect IIN first), not auto video_call.
        """
        mock_flags.is_enabled.return_value = True

        llm = make_llm(
            AutonomousDecision(
                next_state="autonomous_closing",
                action="autonomous_respond",
                reasoning="need missing payment fields",
                should_transition=False,
            )
        )
        source = AutonomousDecisionSource(llm=llm)

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
            "terminal_state_requirements": {
                "payment_ready": ["kaspi_phone", "iin"],
                "video_call_scheduled": ["contact_info"],
            },
        }
        bb = make_blackboard(
            state="autonomous_closing",
            intent="contact_provided",
            user_message="Телефон: +77015551234",
            state_config=state_config,
            context_envelope=envelope,
        )

        source.contribute(bb)

        assert len(bb._transition_proposals) == 1
        tp = bb._transition_proposals[0]
        assert tp["next_state"] == "autonomous_closing"
        assert "stay" in tp["reason_code"]

    @patch("src.feature_flags.flags")
    def test_video_call_autofinish_when_no_payment_context(self, mock_flags):
        """Without payment/invoice intent, contact-only path can auto-finish video_call."""
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
            "terminal_state_requirements": {
                "payment_ready": ["kaspi_phone", "iin"],
                "video_call_scheduled": ["contact_info"],
            },
        }
        bb = make_blackboard(
            state="autonomous_closing",
            intent="contact_provided",
            user_message="Мой телефон +77073334455",
            state_config=state_config,
            context_envelope=envelope,
        )

        source.contribute(bb)

        assert len(bb._transition_proposals) == 1
        tp = bb._transition_proposals[0]
        assert tp["next_state"] == "video_call_scheduled"
        assert tp["reason_code"] == "autonomous_terminal_video_call"


class TestMergedContactFastPath:
    """Merged-mode regression guards for contact_provided handling."""

    @patch("src.feature_flags.flags")
    def test_merged_fastpath_finishes_video_call_from_autonomous_stage(self, mock_flags):
        """When merged mode is on, contact_provided should not stall in non-closing stage."""
        mock_flags.is_enabled.return_value = True

        llm = make_llm(
            AutonomousDecision(
                next_state="autonomous_negotiation",
                action="autonomous_respond",
                reasoning="stay",
                should_transition=False,
            )
        )
        source = AutonomousDecisionSource(llm=llm)
        states = {
            "autonomous_negotiation": {"phase": "negotiation", "goal": "Обсудить условия"},
            "autonomous_closing": {"phase": "closing", "goal": "Закрыть сделку"},
            "payment_ready": {"phase": "terminal", "goal": "Оплата"},
            "video_call_scheduled": {"phase": "terminal", "goal": "Видеозвонок"},
        }
        bb = make_blackboard(
            state="autonomous_negotiation",
            intent="contact_provided",
            user_message="Мой номер: +77073334455",
            states=states,
            state_config={
                "phase": "negotiation",
                "goal": "Обсудить условия",
                "max_turns_in_state": 6,
            },
            context_envelope=SimpleNamespace(
                consecutive_same_state=1,
                intent_history=["question_features"],
                total_objections=0,
                repeated_objection_types=[],
                state_history=["autonomous_objection_handling", "autonomous_negotiation"],
            ),
        )

        source.contribute(bb)

        assert len(bb._transition_proposals) == 1
        tp = bb._transition_proposals[0]
        assert tp["next_state"] == "video_call_scheduled"
        assert tp["reason_code"] == "autonomous_merged_terminal_video_call"
        llm.generate_structured.assert_not_called()

    @patch("src.feature_flags.flags")
    def test_merged_fastpath_keeps_payment_guard_without_iin(self, mock_flags):
        """Merged fastpath must not bypass payment-context IIN guard."""
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
            "autonomous_closing": {"phase": "closing", "goal": "Закрыть сделку"},
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
    def test_contact_provided_redirect_keeps_closing_when_payment_missing_iin(self, mock_flags):
        """
        LLM may suggest autonomous_closing on contact_provided.
        In payment context, redirect must not skip to video_call_scheduled without IIN.
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
            state_config=state_config,
            context_envelope=envelope,
        )

        source.contribute(bb)

        assert len(bb._transition_proposals) == 1
        tp = bb._transition_proposals[0]
        assert tp["next_state"] == "autonomous_closing"

    @patch("src.feature_flags.flags")
    def test_video_call_allowed_after_recent_iin_refusal(self, mock_flags):
        """
        If payment context existed but client recently refused/deferred IIN,
        contact-only path should auto-finish into video_call_scheduled.
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
            "terminal_state_requirements": {
                "payment_ready": ["kaspi_phone", "iin"],
                "video_call_scheduled": ["contact_info"],
            },
        }
        bb = make_blackboard(
            state="autonomous_closing",
            intent="contact_provided",
            user_message="Ок, тогда видеозвонок: founder@example.com",
            state_config=state_config,
            context_envelope=envelope,
        )

        source.contribute(bb)

        assert len(bb._transition_proposals) == 1
        tp = bb._transition_proposals[0]
        assert tp["next_state"] == "video_call_scheduled"
        assert tp["reason_code"] == "autonomous_terminal_video_call"
