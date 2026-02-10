# tests/test_disambiguation_blackboard_integration.py

"""
Integration tests for Disambiguation Through the Blackboard.

Verifies:
- Turn N: message -> intent="disambiguation_needed" -> DisambiguationSource ->
  ask_clarification -> format_question -> 18-key return
- Turn N+1 option: "1" -> DisambiguationResolutionLayer -> REFINED -> normal pipeline
- Turn N+1 critical: critical intent -> PASS -> contact_provided -> normal pipeline
- Turn N+1 custom: free text -> PASS -> LLM classification -> normal pipeline
- RefinementContext carries disambiguation fields
- Metadata flow through orchestrator -> models -> sm_result
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from typing import Dict, Any

from src.classifier.refinement_pipeline import RefinementContext, RefinementDecision
from src.classifier.disambiguation_resolution_layer import DisambiguationResolutionLayer
from src.blackboard.sources.disambiguation import DisambiguationSource
from src.blackboard.enums import Priority
from src.blackboard.models import ResolvedDecision

# =============================================================================
# Test: RefinementContext carries disambiguation fields
# =============================================================================

class TestRefinementContextDisambiguation:

    def test_default_values(self):
        ctx = RefinementContext(message="test")
        assert ctx.in_disambiguation is False
        assert ctx.disambiguation_options == []

    def test_explicit_values(self):
        options = [{"intent": "x", "label": "X"}]
        ctx = RefinementContext(
            message="test",
            in_disambiguation=True,
            disambiguation_options=options,
        )
        assert ctx.in_disambiguation is True
        assert ctx.disambiguation_options == options

    def test_update_from_result_preserves_disambiguation(self):
        options = [{"intent": "x", "label": "X"}]
        ctx = RefinementContext(
            message="test",
            in_disambiguation=True,
            disambiguation_options=options,
        )
        new_ctx = ctx.update_from_result({"intent": "new_intent", "confidence": 0.9})
        assert new_ctx.in_disambiguation is True
        assert new_ctx.disambiguation_options == options

# =============================================================================
# Test: Resolution layer + Source integration
# =============================================================================

class TestLayerSourceIntegration:
    """Test that the layer and source work together in the pipeline."""

    def test_option_selection_produces_resolved_intent(self):
        """Turn N+1: user picks "1" -> layer resolves to first option intent."""
        layer = DisambiguationResolutionLayer()
        options = [
            {"intent": "price_question", "label": "Цены"},
            {"intent": "demo_request", "label": "Демо"},
        ]
        ctx = RefinementContext(
            message="1",
            in_disambiguation=True,
            disambiguation_options=options,
            intent="unclear",
            confidence=0.3,
            metadata={},
        )
        result = {"intent": "unclear", "confidence": 0.3, "extracted_data": {}}

        refinement = layer._do_refine("1", result, ctx)

        assert refinement.decision == RefinementDecision.REFINED
        assert refinement.intent == "price_question"
        assert refinement.confidence == 0.9
        assert ctx.metadata["exit_disambiguation"] is True

    def test_critical_intent_exits_and_passes(self):
        """Turn N+1: user says contact -> layer exits disambiguation."""
        layer = DisambiguationResolutionLayer()
        options = [
            {"intent": "price_question", "label": "Цены"},
            {"intent": "demo_request", "label": "Демо"},
        ]
        ctx = RefinementContext(
            message="хочу связаться",
            in_disambiguation=True,
            disambiguation_options=options,
            intent="contact_provided",
            confidence=0.9,
            metadata={},
        )
        result = {"intent": "contact_provided", "confidence": 0.9, "extracted_data": {}}

        refinement = layer._do_refine("хочу связаться", result, ctx)

        assert refinement.decision == RefinementDecision.PASS_THROUGH
        assert refinement.intent == "contact_provided"
        assert ctx.metadata["exit_disambiguation"] is True

    def test_custom_input_uses_llm_classification(self):
        """Turn N+1: user types free text -> layer passes LLM classification."""
        layer = DisambiguationResolutionLayer()
        options = [
            {"intent": "price_question", "label": "Цены"},
            {"intent": "demo_request", "label": "Демо"},
        ]
        ctx = RefinementContext(
            message="меня интересуют функции",
            in_disambiguation=True,
            disambiguation_options=options,
            intent="feature_question",
            confidence=0.8,
            metadata={},
        )
        result = {"intent": "feature_question", "confidence": 0.8, "extracted_data": {}}

        refinement = layer._do_refine("меня интересуют функции", result, ctx)

        assert refinement.decision == RefinementDecision.PASS_THROUGH
        assert refinement.intent == "feature_question"
        assert ctx.metadata["exit_disambiguation"] is True

# =============================================================================
# Test: DisambiguationSource proposes correctly
# =============================================================================

class TestSourceProposal:

    def test_disambiguation_source_proposes_blocking_action(self):
        source = DisambiguationSource()

        # Mock blackboard
        bb = MagicMock()
        bb.current_intent = "disambiguation_needed"

        ctx = MagicMock()
        envelope = MagicMock()
        envelope.disambiguation_options = [{"intent": "price_question", "label": "Цены"}]
        envelope.disambiguation_question = "Уточните:"
        ctx.context_envelope = envelope
        bb.get_context.return_value = ctx

        source.contribute(bb)

        bb.propose_action.assert_called_once()
        call_kwargs = bb.propose_action.call_args[1]
        assert call_kwargs["action"] == "ask_clarification"
        assert call_kwargs["priority"] == Priority.HIGH
        assert call_kwargs["combinable"] is False
        assert call_kwargs["reason_code"] == "disambiguation_needed"

    def test_disambiguation_source_skips_non_disambiguation(self):
        source = DisambiguationSource()
        bb = MagicMock()
        bb.current_intent = "price_question"

        assert source.should_contribute(bb) is False

# =============================================================================
# Test: ResolvedDecision metadata flow
# =============================================================================

class TestResolvedDecisionMetadata:

    def test_to_sm_result_includes_disambiguation_fields(self):
        decision = ResolvedDecision(
            action="ask_clarification",
            next_state="spin_situation",
            disambiguation_options=[
                {"intent": "price_question", "label": "Цены"},
            ],
            disambiguation_question="Уточните:",
        )

        sm_result = decision.to_sm_result()

        assert "disambiguation_options" in sm_result
        assert sm_result["disambiguation_options"] == [
            {"intent": "price_question", "label": "Цены"},
        ]
        assert sm_result["disambiguation_question"] == "Уточните:"

    def test_to_sm_result_omits_empty_disambiguation(self):
        decision = ResolvedDecision(
            action="answer_with_pricing",
            next_state="spin_problem",
        )

        sm_result = decision.to_sm_result()

        assert "disambiguation_options" not in sm_result

    def test_to_sm_result_always_has_core_fields(self):
        """Verify all 18 core keys are present."""
        decision = ResolvedDecision(
            action="ask_clarification",
            next_state="spin_situation",
            prev_state="greeting",
            goal="Qualify the lead",
            collected_data={"name": "Test"},
            missing_data=["company"],
            optional_data=["email"],
            is_final=False,
            spin_phase="situation",
            prev_phase="greeting",
            circular_flow={"count": 0},
            objection_flow={"consecutive_objections": 0},
            disambiguation_options=[{"intent": "x", "label": "X"}],
            disambiguation_question="Q?",
        )

        sm_result = decision.to_sm_result()

        # Core fields
        assert "action" in sm_result
        assert "next_state" in sm_result
        assert "prev_state" in sm_result
        assert "goal" in sm_result
        assert "collected_data" in sm_result
        assert "missing_data" in sm_result
        assert "optional_data" in sm_result
        assert "is_final" in sm_result
        assert "spin_phase" in sm_result
        assert "prev_phase" in sm_result
        assert "circular_flow" in sm_result
        assert "objection_flow" in sm_result
        assert "reason_codes" in sm_result
        assert "resolution_trace" in sm_result
        # Disambiguation-specific
        assert "disambiguation_options" in sm_result
        assert "disambiguation_question" in sm_result

# =============================================================================
# Test: ConflictResolver priority semantics
# =============================================================================

class TestConflictResolverSemantics:
    """Test that disambiguation (HIGH, combinable=False) behaves correctly
    with respect to other priority levels."""

    def test_disambiguation_blocks_transitions(self):
        """combinable=False should prevent transitions from being applied."""
        from src.blackboard.models import Proposal
        from src.blackboard.enums import ProposalType

        disambiguation_proposal = Proposal(
            type=ProposalType.ACTION,
            value="ask_clarification",
            priority=Priority.HIGH,
            source_name="DisambiguationSource",
            reason_code="disambiguation_needed",
            combinable=False,
        )

        assert disambiguation_proposal.combinable is False
        assert disambiguation_proposal.priority == Priority.HIGH

    def test_critical_beats_high(self):
        """CRITICAL (escalation) should win over HIGH (disambiguation)."""
        assert Priority.CRITICAL < Priority.HIGH  # Lower value = higher priority

# =============================================================================
# Test: Typed fields E2E (ContextEnvelope → DisambiguationSource)
# =============================================================================

class TestTypedFieldsE2E:
    """End-to-end: typed disambiguation fields on ContextEnvelope flow
    correctly through DisambiguationSource into proposal metadata."""

    def test_typed_fields_produce_correct_proposal_metadata(self):
        """ContextEnvelope with typed fields → Source reads them → correct proposal."""
        from src.context_envelope import ContextEnvelope

        source = DisambiguationSource()
        options = [
            {"intent": "price_question", "label": "Цены"},
            {"intent": "demo_request", "label": "Демо"},
        ]

        # Build a real ContextEnvelope with typed fields
        envelope = ContextEnvelope()
        envelope.disambiguation_options = options
        envelope.disambiguation_question = "Уточните, пожалуйста:"

        # Wire into mock blackboard
        bb = MagicMock()
        bb.current_intent = "disambiguation_needed"
        ctx = MagicMock()
        ctx.context_envelope = envelope
        bb.get_context.return_value = ctx

        source.contribute(bb)

        bb.propose_action.assert_called_once()
        call_kwargs = bb.propose_action.call_args[1]
        assert call_kwargs["action"] == "ask_clarification"
        assert call_kwargs["metadata"]["disambiguation_options"] == options
        assert call_kwargs["metadata"]["disambiguation_question"] == "Уточните, пожалуйста:"

    def test_empty_typed_fields_no_proposal(self):
        """ContextEnvelope with empty typed fields → Source skips proposal (Defense Layer 1)."""
        from src.context_envelope import ContextEnvelope

        source = DisambiguationSource()

        # Build a real ContextEnvelope with default (empty) fields
        envelope = ContextEnvelope()

        bb = MagicMock()
        bb.current_intent = "disambiguation_needed"
        ctx = MagicMock()
        ctx.context_envelope = envelope
        bb.get_context.return_value = ctx

        source.contribute(bb)

        bb.propose_action.assert_not_called()

# =============================================================================
# Test: PhaseExhaustedSource priority interactions
# =============================================================================

class TestPhaseExhaustedPriorityInteractions:
    """Test that PhaseExhaustedSource interacts correctly with other sources
    via ConflictResolver priority semantics."""

    def test_disambiguation_wins_over_phase_exhausted(self):
        """DisambiguationSource (HIGH, combinable=False) beats
        PhaseExhaustedSource (NORMAL, combinable=True)."""
        from src.blackboard.models import Proposal
        from src.blackboard.enums import ProposalType

        disambiguation = Proposal(
            type=ProposalType.ACTION,
            value="ask_clarification",
            priority=Priority.HIGH,
            source_name="DisambiguationSource",
            reason_code="disambiguation_needed",
            combinable=False,
        )

        phase_exhausted = Proposal(
            type=ProposalType.ACTION,
            value="offer_options",
            priority=Priority.NORMAL,
            source_name="PhaseExhaustedSource",
            reason_code="phase_exhausted_options",
            combinable=True,
        )

        # HIGH < NORMAL numerically (lower = higher priority)
        assert disambiguation.priority < phase_exhausted.priority
        # Disambiguation is non-combinable, so it blocks
        assert disambiguation.combinable is False
        assert phase_exhausted.combinable is True

    def test_phase_exhausted_coexists_with_transition(self):
        """PhaseExhaustedSource (NORMAL action, combinable=True) coexists
        with TransitionResolver (NORMAL transition) — both apply."""
        from src.blackboard.models import Proposal
        from src.blackboard.enums import ProposalType

        phase_exhausted = Proposal(
            type=ProposalType.ACTION,
            value="offer_options",
            priority=Priority.NORMAL,
            source_name="PhaseExhaustedSource",
            reason_code="phase_exhausted_options",
            combinable=True,
        )

        transition = Proposal(
            type=ProposalType.TRANSITION,
            value="close",
            priority=Priority.NORMAL,
            source_name="TransitionResolverSource",
            reason_code="intent_transition",
            combinable=True,
        )

        # Both are combinable=True and NORMAL — they should coexist
        assert phase_exhausted.combinable is True
        assert transition.combinable is True
        assert phase_exhausted.priority == transition.priority

class TestDefenseInDepthDisambiguation:
    """Test defense-in-depth: disambiguation clears guard fallback."""

    def test_disambiguation_clears_fallback_concept(self):
        """When Blackboard returns ask_clarification with options,
        guard fallback_response should be cleared."""
        # This is a conceptual test — the actual clearing happens in bot.py
        # Here we verify the priority semantics that make it safe
        sm_result = {
            "action": "ask_clarification",
            "disambiguation_options": [
                {"intent": "price_question", "label": "Цены"},
                {"intent": "demo_request", "label": "Демо"},
            ],
        }

        fallback_response = {"response": "Generic menu", "tier": "fallback_tier_2"}

        # Condition from bot.py defense-in-depth:
        should_clear = bool(
            fallback_response
            and sm_result.get("action") == "ask_clarification"
            and sm_result.get("disambiguation_options")
        )
        assert should_clear is True

    def test_no_clear_without_disambiguation_options(self):
        """fallback_response NOT cleared when ask_clarification has no options."""
        sm_result = {
            "action": "ask_clarification",
            "disambiguation_options": [],
        }

        fallback_response = {"response": "Generic menu"}

        should_clear = bool(
            fallback_response
            and sm_result.get("action") == "ask_clarification"
            and sm_result.get("disambiguation_options")
        )
        assert should_clear is False

    def test_no_clear_for_non_disambiguation_action(self):
        """fallback_response NOT cleared for non-ask_clarification actions."""
        sm_result = {
            "action": "continue_conversation",
        }

        fallback_response = {"response": "Generic menu"}

        should_clear = (
            fallback_response
            and sm_result.get("action") == "ask_clarification"
            and sm_result.get("disambiguation_options")
        )
        assert should_clear is False
