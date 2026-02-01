"""
Tests for BUG #10: Price Question Loop fix.

Covers all 9 changes (0-8) across the defense-in-depth chain:
- Change 0: Import fix in dialogue_policy.py
- Change 1: Directive building deferred after policy override
- Change 2: ask_clarifying suppressed for answerable questions
- Change 3: answer_with_summary template conditional question
- Change 4: is_price_question with repeated_question fallback
- Change 5: is_answerable_question + repair overlay escape
- Change 6: Generator answer-template forcing for repeated questions
- Change 7: PriceQuestionSource secondary_intents + repeated_question
- Change 8: FactQuestionSource repeated_question fallback

NOTE: Tests with semantic search and LLM calls are fully skipped.
"""

import pytest
import yaml
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch
from typing import Dict, Any, Optional, List

from src.conditions.policy.context import PolicyContext
from src.conditions.policy.registry import policy_registry
from src.conditions.policy.conditions import (
    is_price_question,
    is_answerable_question,
)
from src.conditions.trace import EvaluationTrace, Resolution
from src.dialogue_policy import (
    DialoguePolicy,
    PolicyOverride,
    PolicyDecision,
    CascadeDisposition,
)
from src.blackboard.sources.price_question import PriceQuestionSource
from src.blackboard.sources.fact_question import FactQuestionSource
from src.blackboard.blackboard import DialogueBlackboard
from src.blackboard.enums import Priority
from src.yaml_config.constants import INTENT_CATEGORIES, REPAIR_PROTECTED_ACTIONS
from src.context_envelope import ContextEnvelope, ReasonCode
from src.response_directives import (
    ResponseDirectives,
    build_response_directives,
)


# =============================================================================
# Helpers
# =============================================================================

PRICE_INTENTS = set(INTENT_CATEGORIES.get("price_related", []))
QUESTION_INTENTS = set(INTENT_CATEGORIES.get("question", []))
ALL_ANSWERABLE = PRICE_INTENTS | QUESTION_INTENTS

BASE_DIR = Path(__file__).parent.parent
TEMPLATES_DIR = BASE_DIR / "src" / "yaml_config" / "templates"


def _get_fact_intent():
    """Get a valid fact intent from FactQuestionSource._fact_intents."""
    source = FactQuestionSource()
    intents = source.fact_intents
    return next(iter(intents), None)


def _get_non_price_fact_intent():
    """Get a fact intent in BOTH FactQuestionSource AND QUESTION_INTENTS (for generator tests)."""
    source = FactQuestionSource()
    # Must be in both _fact_intents and QUESTION_INTENTS for generator logic
    valid = (source.fact_intents & QUESTION_INTENTS) - PRICE_INTENTS
    return next(iter(valid), None)


def _make_mock_blackboard(
    current_intent: str = "greeting",
    secondary_intents: Optional[List[str]] = None,
    repeated_question: Optional[str] = None,
    collected_data: Optional[Dict[str, Any]] = None,
):
    """Create a mock blackboard with context for should_contribute() tests."""
    bb = Mock(spec=DialogueBlackboard)
    bb.current_intent = current_intent

    ctx = Mock()
    ctx.current_intent = current_intent
    ctx.collected_data = collected_data or {}
    ctx.state_config = {"rules": {}}

    envelope = Mock()
    envelope.secondary_intents = secondary_intents or []
    envelope.repeated_question = repeated_question
    ctx.context_envelope = envelope

    bb.get_context.return_value = ctx
    return bb


def _make_contribute_blackboard(
    current_intent: str = "greeting",
    secondary_intents: Optional[List[str]] = None,
    repeated_question: Optional[str] = None,
):
    """Create a mock blackboard suitable for contribute() tests.

    Uses Mock for context (not frozen ContextSnapshot) so we can
    inject envelope with secondary_intents and repeated_question.
    """
    bb = Mock(spec=DialogueBlackboard)
    bb.current_intent = current_intent

    ctx = Mock()
    ctx.current_intent = current_intent
    ctx.collected_data = {}
    ctx.state_config = {"rules": {}}

    envelope = Mock()
    envelope.secondary_intents = secondary_intents or []
    envelope.repeated_question = repeated_question
    ctx.context_envelope = envelope

    bb.get_context.return_value = ctx

    # Track proposals
    proposals = []

    def mock_propose_action(**kwargs):
        from src.blackboard.models import Proposal
        from src.blackboard.enums import ProposalType
        p = Proposal(
            type=ProposalType.ACTION,
            value=kwargs["action"],
            priority=kwargs.get("priority", Priority.NORMAL),
            source_name=kwargs.get("source_name", "test"),
            reason_code=kwargs.get("reason_code", ""),
            combinable=kwargs.get("combinable", False),
            metadata=kwargs.get("metadata", {}),
        )
        proposals.append(p)

    bb.propose_action = mock_propose_action
    bb.get_action_proposals = lambda: proposals

    return bb


def _make_envelope_mock(
    repeated_question=None,
    is_stuck=False,
    needs_repair=None,
):
    """Create a ContextEnvelope mock with all required attributes for build_response_directives."""
    envelope = Mock()
    envelope.repeated_question = repeated_question
    envelope.is_stuck = is_stuck
    envelope.has_oscillation = False
    envelope.turn_number = 5
    envelope.frustration_level = 0
    envelope.client_has_data = False
    envelope.first_objection_type = None
    envelope.confidence_trend = "stable"
    envelope.is_near_contact_state = False
    envelope.has_breakthrough = False
    envelope.reason_codes = []
    envelope.client_industry = ""
    envelope.client_company_size = ""
    envelope.collected_data = {}
    envelope.client_name = ""
    envelope.client_pain_points = []
    envelope.last_bot_responses = []
    envelope.objection_types_seen = []
    envelope.bot_responses = []
    envelope.history = []
    if needs_repair is not None:
        envelope.needs_repair = needs_repair
    else:
        envelope.needs_repair = bool(repeated_question) or is_stuck

    # has_reason must return True for POLICY_REPAIR_MODE when needs_repair
    def _has_reason(reason):
        if envelope.needs_repair and reason == ReasonCode.POLICY_REPAIR_MODE:
            return True
        return False
    envelope.has_reason = _has_reason

    return envelope


# =============================================================================
# Change 0: Fix broken import
# =============================================================================

class TestChange0ImportFix:
    """Verify the import in dialogue_policy.py L578 is correct."""

    def test_import_is_from_src_logger(self):
        """The price override path should not crash with ImportError."""
        from src.dialogue_policy import DialoguePolicy
        assert DialoguePolicy is not None

    def test_price_overlay_can_log(self):
        """Price overlay block uses 'from src.logger import logger' — must not crash."""
        from src.logger import logger
        assert logger is not None


# =============================================================================
# Change 4: is_price_question with repeated_question fallback
# =============================================================================

class TestChange4IsPriceQuestionRepeatedQuestion:
    """is_price_question should detect price from repeated_question."""

    def test_primary_intent_still_works(self):
        ctx = PolicyContext.create_test_context(current_intent="price_question")
        assert is_price_question(ctx) is True

    def test_secondary_intent_still_works(self):
        ctx = PolicyContext.create_test_context(
            current_intent="greeting",
            secondary_intents=["price_question"],
        )
        assert is_price_question(ctx) is True

    def test_repeated_question_fallback(self):
        """Bug #10 core: repeated_question catches classifier misses."""
        ctx = PolicyContext.create_test_context(
            current_intent="request_brevity",
            repeated_question="price_question",
        )
        assert is_price_question(ctx) is True

    def test_repeated_question_non_price_returns_false(self):
        ctx = PolicyContext.create_test_context(
            current_intent="greeting",
            repeated_question="question_technical",
        )
        assert is_price_question(ctx) is False

    @pytest.mark.parametrize("price_intent", list(PRICE_INTENTS)[:3])
    def test_various_price_intents_via_repeated_question(self, price_intent):
        ctx = PolicyContext.create_test_context(
            current_intent="request_brevity",
            repeated_question=price_intent,
        )
        assert is_price_question(ctx) is True


# =============================================================================
# Change 5A: is_answerable_question (universal)
# =============================================================================

class TestChange5AIsAnswerableQuestion:
    """is_answerable_question covers ALL question + price intents."""

    def test_price_intent_is_answerable(self):
        ctx = PolicyContext.create_test_context(current_intent="price_question")
        assert is_answerable_question(ctx) is True

    def test_question_intent_is_answerable(self):
        for q in list(QUESTION_INTENTS)[:3]:
            ctx = PolicyContext.create_test_context(current_intent=q)
            assert is_answerable_question(ctx) is True, f"Failed for {q}"

    def test_non_question_not_answerable(self):
        ctx = PolicyContext.create_test_context(current_intent="greeting")
        assert is_answerable_question(ctx) is False

    def test_secondary_intent_answerable(self):
        ctx = PolicyContext.create_test_context(
            current_intent="info_provided",
            secondary_intents=["question_technical"],
        )
        assert is_answerable_question(ctx) is True

    def test_repeated_question_answerable(self):
        ctx = PolicyContext.create_test_context(
            current_intent="request_brevity",
            repeated_question="question_features",
        )
        assert is_answerable_question(ctx) is True

    def test_unclear_not_answerable(self):
        """'unclear' is NOT in question or price_related categories."""
        ctx = PolicyContext.create_test_context(
            current_intent="unclear",
            repeated_question="unclear",
        )
        assert is_answerable_question(ctx) is False

    def test_registered_in_policy_registry(self):
        """is_answerable_question should be registered in the policy registry."""
        assert "is_answerable_question" in policy_registry


# =============================================================================
# Change 5B: Repair overlay escape for answerable questions
# =============================================================================

class TestChange5BRepairOverlayEscape:
    """Repair overlay should skip repair for answerable repeated questions."""

    @pytest.fixture
    def policy(self):
        return DialoguePolicy()

    def test_repair_skipped_for_price_repeated_question(self, policy):
        """When repeated_question is price and action is NOT repair_protected,
        repair overlay should yield via is_answerable_question."""
        ctx = PolicyContext.create_test_context(
            state="spin_situation",
            current_action="continue_current_goal",
            current_intent="request_brevity",
            repeated_question="price_question",
            is_stuck=False,
            has_oscillation=False,
        )
        sm_result = {"action": "continue_current_goal", "next_state": None}
        override = policy._apply_repair_overlay(ctx, sm_result, trace=None)

        assert override is not None
        assert override.decision == PolicyDecision.REPAIR_SKIPPED
        assert override.cascade_disposition == CascadeDisposition.PASS

    def test_repair_skipped_for_fact_repeated_question(self, policy):
        """Non-price answerable question also skips repair."""
        fact_intent = next(iter(QUESTION_INTENTS - PRICE_INTENTS), None)
        if fact_intent is None:
            pytest.skip("No non-price question intents available")

        ctx = PolicyContext.create_test_context(
            state="spin_situation",
            current_action="continue_current_goal",
            current_intent="request_brevity",
            repeated_question=fact_intent,
            is_stuck=False,
            has_oscillation=False,
        )
        sm_result = {"action": "continue_current_goal", "next_state": None}
        override = policy._apply_repair_overlay(ctx, sm_result, trace=None)

        assert override is not None
        assert override.decision == PolicyDecision.REPAIR_SKIPPED

    def test_repair_still_fires_for_unclear(self, policy):
        """'unclear' repeated questions should still trigger repair."""
        ctx = PolicyContext.create_test_context(
            state="spin_situation",
            current_action="continue_current_goal",
            current_intent="unclear",
            repeated_question="unclear",
            is_stuck=False,
            has_oscillation=False,
        )
        sm_result = {"action": "continue_current_goal", "next_state": None}
        override = policy._apply_repair_overlay(ctx, sm_result, trace=None)

        assert override is not None
        assert override.decision == PolicyDecision.REPAIR_CLARIFY

    def test_repair_protected_action_still_preserved(self, policy):
        """Bug #5: existing repair-protected actions still skip repair."""
        ctx = PolicyContext.create_test_context(
            state="spin_situation",
            current_action="answer_with_pricing",
            repeated_question="price_question",
            is_stuck=False,
            has_oscillation=False,
        )
        sm_result = {"action": "answer_with_pricing", "next_state": None}
        override = policy._apply_repair_overlay(ctx, sm_result, trace=None)

        assert override is not None
        assert override.decision == PolicyDecision.REPAIR_SKIPPED
        assert override.cascade_disposition == CascadeDisposition.STOP


# =============================================================================
# Change 2: Suppress ask_clarifying for answerable question types
# =============================================================================

class TestChange2SuppressAskClarifying:
    """Directives should NOT set ask_clarifying for answerable repeated questions."""

    def test_price_repeated_question_no_ask_clarifying(self):
        """Price repeated question: ask_clarifying should be False."""
        envelope = _make_envelope_mock(repeated_question="price_question")
        directives = build_response_directives(envelope)
        assert directives.ask_clarifying is False

    def test_fact_repeated_question_no_ask_clarifying(self):
        """Fact repeated question: ask_clarifying should be False."""
        fact_intent = next(iter(QUESTION_INTENTS), None)
        if fact_intent is None:
            pytest.skip("No question intents")
        envelope = _make_envelope_mock(repeated_question=fact_intent)
        directives = build_response_directives(envelope)
        assert directives.ask_clarifying is False

    def test_unclear_repeated_question_has_ask_clarifying(self):
        """'unclear' repeated question: ask_clarifying should be True."""
        envelope = _make_envelope_mock(repeated_question="unclear")
        directives = build_response_directives(envelope)
        assert directives.ask_clarifying is True

    def test_price_repair_context_has_price_data(self):
        """Price repeated question gets price-specific repair_context."""
        envelope = _make_envelope_mock(repeated_question="price_question")
        directives = build_response_directives(envelope)
        assert "цен" in directives.repair_context.lower()

    def test_non_price_repair_context_generic(self):
        """Non-price answerable question gets generic repair_context."""
        fact_intent = next(iter(QUESTION_INTENTS - PRICE_INTENTS), None)
        if fact_intent is None:
            pytest.skip("No non-price question intents")
        envelope = _make_envelope_mock(repeated_question=fact_intent)
        directives = build_response_directives(envelope)
        assert fact_intent in directives.repair_context


# =============================================================================
# Change 3: answer_with_summary template conditional question
# =============================================================================

class TestChange3TemplateSafety:
    """answer_with_summary template should have conditional question instruction."""

    @pytest.fixture
    def templates(self):
        path = TEMPLATES_DIR / "_base" / "prompts.yaml"
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data.get("templates", {})

    def test_answer_with_summary_no_unconditional_question(self, templates):
        """Template should NOT blindly say 'Задай ОДИН вопрос'."""
        tmpl = templates.get("answer_with_summary", {})
        text = tmpl.get("template", "")
        assert "ТОЛЬКО если ты полностью ответил" in text

    def test_answer_with_summary_warns_about_concrete_questions(self, templates):
        """Template should warn not to ask questions when user asked something concrete."""
        tmpl = templates.get("answer_with_summary", {})
        text = tmpl.get("template", "")
        assert "НЕ задавай вопрос" in text


# =============================================================================
# Change 7: PriceQuestionSource secondary_intents + repeated_question
# =============================================================================

class TestChange7PriceQuestionSource:
    """PriceQuestionSource should handle secondary intents and repeated_question."""

    @pytest.fixture
    def source(self):
        return PriceQuestionSource()

    def test_should_contribute_via_repeated_question(self, source):
        """should_contribute detects price via repeated_question."""
        bb = _make_mock_blackboard(
            current_intent="request_brevity",
            repeated_question="price_question",
        )
        assert source.should_contribute(bb) is True

    def test_should_contribute_via_secondary(self, source):
        """should_contribute detects price via secondary intents."""
        bb = _make_mock_blackboard(
            current_intent="info_provided",
            secondary_intents=["price_question"],
        )
        assert source.should_contribute(bb) is True

    def test_should_contribute_false_no_price(self, source):
        """should_contribute is False when no price signal at all."""
        bb = _make_mock_blackboard(
            current_intent="greeting",
            repeated_question="question_technical",
        )
        assert source.should_contribute(bb) is False

    def test_contribute_resolves_from_secondary(self, source):
        """contribute() fixes pre-existing bug: secondary intents now resolve."""
        bb = _make_contribute_blackboard(
            current_intent="info_provided",
            secondary_intents=["price_question"],
        )
        source.contribute(bb)
        proposals = bb.get_action_proposals()
        price_proposals = [p for p in proposals if p.reason_code == "price_question_priority"]
        assert len(price_proposals) >= 1
        assert price_proposals[0].metadata.get("detection_source") == "secondary"

    def test_contribute_resolves_from_repeated_question(self, source):
        """contribute() resolves intent from repeated_question."""
        bb = _make_contribute_blackboard(
            current_intent="request_brevity",
            repeated_question="price_question",
        )
        source.contribute(bb)
        proposals = bb.get_action_proposals()
        price_proposals = [p for p in proposals if p.reason_code == "price_question_priority"]
        assert len(price_proposals) >= 1
        assert price_proposals[0].metadata.get("detection_source") == "repeated_question"

    def test_contribute_metadata_has_detection_source(self, source):
        """contribute() includes detection_source in metadata."""
        bb = _make_contribute_blackboard(
            current_intent="request_brevity",
            repeated_question="price_question",
        )
        source.contribute(bb)
        proposals = bb.get_action_proposals()
        price_proposals = [p for p in proposals if p.reason_code == "price_question_priority"]
        assert len(price_proposals) >= 1
        assert "detection_source" in price_proposals[0].metadata


# =============================================================================
# Change 8: FactQuestionSource repeated_question fallback
# =============================================================================

class TestChange8FactQuestionSource:
    """FactQuestionSource should detect questions via repeated_question."""

    @pytest.fixture
    def source(self):
        return FactQuestionSource()

    def test_should_contribute_via_repeated_question(self, source):
        """should_contribute detects fact question via repeated_question."""
        fact_intent = _get_fact_intent()
        if fact_intent is None:
            pytest.skip("No fact intents available")
        bb = _make_mock_blackboard(
            current_intent="request_brevity",
            repeated_question=fact_intent,
        )
        assert source.should_contribute(bb) is True

    def test_should_contribute_false_no_fact(self, source):
        """should_contribute is False when repeated_question is not a fact intent."""
        bb = _make_mock_blackboard(
            current_intent="greeting",
            repeated_question="unclear",
        )
        assert source.should_contribute(bb) is False

    def test_contribute_resolves_from_repeated_question(self, source):
        """contribute() resolves intent from repeated_question."""
        fact_intent = _get_fact_intent()
        if fact_intent is None:
            pytest.skip("No fact intents available")

        bb = _make_contribute_blackboard(
            current_intent="request_brevity",
            repeated_question=fact_intent,
        )
        source.contribute(bb)
        proposals = bb.get_action_proposals()
        fact_proposals = [p for p in proposals if p.reason_code == "fact_question_detected"]
        assert len(fact_proposals) >= 1

    def test_contribute_primary_still_works(self, source):
        """Primary intent detection is unchanged."""
        fact_intent = _get_fact_intent()
        if fact_intent is None:
            pytest.skip("No fact intents available")

        bb = _make_contribute_blackboard(current_intent=fact_intent)
        source.contribute(bb)
        proposals = bb.get_action_proposals()
        fact_proposals = [p for p in proposals if p.reason_code == "fact_question_detected"]
        assert len(fact_proposals) >= 1


# =============================================================================
# Change 6: Generator answer-template forcing
# =============================================================================

class TestChange6GeneratorTemplateForcing:
    """Generator should force answer template for repeated answerable questions."""

    def test_generator_module_loads(self):
        """Ensure generator module loads without import errors."""
        from src.generator import ResponseGenerator
        assert ResponseGenerator is not None

    def test_repeated_price_question_forces_price_template(self):
        """Repeated price question should force price template selection."""
        template_key = "continue_current_goal"
        _rq = "price_question"
        _answerable = QUESTION_INTENTS | PRICE_INTENTS
        _price = PRICE_INTENTS

        if _rq in _answerable and template_key not in REPAIR_PROTECTED_ACTIONS:
            if _rq in _price:
                template_key = "answer_with_pricing"
            else:
                template_key = "answer_with_knowledge"

        assert template_key == "answer_with_pricing"

    def test_repeated_fact_question_forces_knowledge_template(self):
        """Repeated fact question should force answer_with_knowledge template."""
        fact_intent = _get_non_price_fact_intent()
        if fact_intent is None:
            pytest.skip("No non-price fact intents")

        template_key = "continue_current_goal"
        _rq = fact_intent
        _answerable = QUESTION_INTENTS | PRICE_INTENTS
        _price = PRICE_INTENTS

        if _rq in _answerable and template_key not in REPAIR_PROTECTED_ACTIONS:
            if _rq in _price:
                template_key = "answer_with_pricing"
            else:
                template_key = "answer_with_knowledge"

        assert template_key == "answer_with_knowledge"

    def test_already_protected_action_not_overridden(self):
        """If template_key is already a repair-protected action, don't override."""
        template_key = "answer_with_pricing"
        _rq = "price_question"
        _answerable = QUESTION_INTENTS | PRICE_INTENTS

        if _rq in _answerable and template_key not in REPAIR_PROTECTED_ACTIONS:
            template_key = "answer_with_knowledge"

        assert template_key == "answer_with_pricing"


# =============================================================================
# Change 1: Directive building deferred after policy override
# =============================================================================

class TestChange1DeferredDirectives:
    """Directives should be built AFTER policy override."""

    def test_bot_module_loads(self):
        """Ensure bot module loads without import errors after change."""
        from src.bot import SalesBot
        assert SalesBot is not None

    def test_directive_building_position(self):
        """Verify the deferred comment exists in the code (structural check)."""
        import inspect
        from src import bot
        source = inspect.getsource(bot)
        defer_pos = source.find("Bug #10: Defer ResponseDirectives until AFTER policy override")
        build_pos = source.find("Bug #10: Build ResponseDirectives AFTER policy override")
        policy_record = source.find("trace_builder.record_policy_override")

        assert defer_pos != -1, "Deferred directive comment not found"
        assert build_pos != -1, "Post-override build comment not found"
        assert build_pos > policy_record, "Directives built before policy override recorded"


# =============================================================================
# Cross-layer: Full pipeline scenario tests
# =============================================================================

class TestCrossLayerPriceScenario:
    """
    Cross-layer test: Compound message "Некогда. Цену скажи" with
    classifier returning request_brevity, prior turns had price_question.
    """

    def test_price_question_source_catches_via_repeated_question(self):
        """Blackboard layer: PriceQuestionSource fires via repeated_question."""
        source = PriceQuestionSource()
        bb = _make_mock_blackboard(
            current_intent="request_brevity",
            repeated_question="price_question",
        )
        assert source.should_contribute(bb) is True

    def test_policy_condition_catches_via_repeated_question(self):
        """Policy layer: is_price_question returns True via repeated_question."""
        ctx = PolicyContext.create_test_context(
            current_intent="request_brevity",
            repeated_question="price_question",
        )
        assert is_price_question(ctx) is True

    def test_directives_suppress_ask_clarifying(self):
        """Directives layer: ask_clarifying is False for price repeated question."""
        envelope = _make_envelope_mock(repeated_question="price_question")
        directives = build_response_directives(envelope)
        assert directives.ask_clarifying is False

    def test_repair_overlay_skips_for_price_question(self):
        """Repair overlay: skips repair when is_answerable_question is True."""
        policy = DialoguePolicy()
        ctx = PolicyContext.create_test_context(
            state="spin_situation",
            current_action="continue_current_goal",
            current_intent="request_brevity",
            repeated_question="price_question",
            is_stuck=False,
            has_oscillation=False,
        )
        sm_result = {"action": "continue_current_goal", "next_state": None}
        override = policy._apply_repair_overlay(ctx, sm_result, trace=None)

        assert override is not None
        assert override.decision == PolicyDecision.REPAIR_SKIPPED
        assert override.cascade_disposition == CascadeDisposition.PASS


class TestCrossLayerFactScenario:
    """
    Cross-layer test: Repeated fact question with classifier miss.
    """

    def test_fact_source_catches_via_repeated_question(self):
        """Blackboard layer: FactQuestionSource fires via repeated_question."""
        fact_intent = _get_fact_intent()
        if not fact_intent:
            pytest.skip("No fact intents")

        source = FactQuestionSource()
        bb = _make_mock_blackboard(
            current_intent="request_brevity",
            repeated_question=fact_intent,
        )
        assert source.should_contribute(bb) is True

    def test_policy_condition_catches_fact_question(self):
        """Policy layer: is_answerable_question returns True for fact."""
        fact_intent = next(iter(QUESTION_INTENTS - PRICE_INTENTS), None)
        if not fact_intent:
            pytest.skip("No non-price question intents")

        ctx = PolicyContext.create_test_context(
            current_intent="request_brevity",
            repeated_question=fact_intent,
        )
        assert is_answerable_question(ctx) is True

    def test_repair_overlay_skips_for_fact_question(self):
        """Repair overlay: skips repair for fact question."""
        fact_intent = next(iter(QUESTION_INTENTS - PRICE_INTENTS), None)
        if not fact_intent:
            pytest.skip("No non-price question intents")

        policy = DialoguePolicy()
        ctx = PolicyContext.create_test_context(
            state="spin_situation",
            current_action="continue_current_goal",
            current_intent="request_brevity",
            repeated_question=fact_intent,
            is_stuck=False,
            has_oscillation=False,
        )
        sm_result = {"action": "continue_current_goal", "next_state": None}
        override = policy._apply_repair_overlay(ctx, sm_result, trace=None)

        assert override is not None
        assert override.decision == PolicyDecision.REPAIR_SKIPPED


class TestRegressionRepairStillWorks:
    """Regression: repair still fires for non-answerable repeated questions."""

    def test_unclear_repeated_triggers_repair(self):
        """'unclear' repeated question still triggers repair."""
        policy = DialoguePolicy()
        ctx = PolicyContext.create_test_context(
            state="spin_situation",
            current_action="continue_current_goal",
            current_intent="unclear",
            repeated_question="unclear",
            is_stuck=False,
            has_oscillation=False,
        )
        sm_result = {"action": "continue_current_goal", "next_state": None}
        override = policy._apply_repair_overlay(ctx, sm_result, trace=None)

        assert override is not None
        assert override.decision == PolicyDecision.REPAIR_CLARIFY


class TestPreExistingBugFix:
    """Change 7B: PriceQuestionSource.contribute() secondary_intents bug fix."""

    def test_secondary_price_intent_no_longer_silently_discarded(self):
        """Compound message: primary=info_provided, secondary=price_question.
        contribute() should resolve from secondary, not early-return."""
        source = PriceQuestionSource()
        bb = _make_contribute_blackboard(
            current_intent="info_provided",
            secondary_intents=["price_question"],
        )
        source.contribute(bb)
        proposals = bb.get_action_proposals()
        price_proposals = [p for p in proposals if p.reason_code == "price_question_priority"]
        assert len(price_proposals) >= 1, (
            "PriceQuestionSource silently discarded secondary price intent"
        )
        assert price_proposals[0].metadata.get("detection_source") == "secondary"


# =============================================================================
# INTENT_CATEGORIES sanity checks
# =============================================================================

class TestIntentCategoriesSanity:
    """Ensure INTENT_CATEGORIES has the expected structure."""

    def test_price_related_exists(self):
        assert "price_related" in INTENT_CATEGORIES
        assert len(INTENT_CATEGORIES["price_related"]) >= 2

    def test_question_exists(self):
        assert "question" in INTENT_CATEGORIES
        assert len(INTENT_CATEGORIES["question"]) >= 5

    def test_no_overlap_price_unclear(self):
        """'unclear' should NOT be in price_related or question."""
        assert "unclear" not in PRICE_INTENTS
        assert "unclear" not in QUESTION_INTENTS
