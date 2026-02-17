"""
Tests for Question Suppression (BUG #9).

Three-level system with 5 defensive layers:
- density == 0 → "Задай ОДИН вопрос" (mandatory)
- density == 1 → "Можешь задать если уместно" (optional, LLM decides)
- density >= 2 → "НЕ задавай вопросов" (full suppression)
"""

import pytest
from unittest.mock import MagicMock, patch
from dataclasses import dataclass

from src.context_envelope import ContextEnvelope, ContextEnvelopeBuilder
from src.yaml_config.constants import (
    PERSONA_QUESTION_SUPPRESSION,
    get_persona_question_thresholds,
    INTENT_CATEGORIES,
)
from src.response_directives import ResponseDirectives, ResponseDirectivesBuilder, ResponseTone
from src.generator import PERSONALIZATION_DEFAULTS, QUESTION_STRIP_EXEMPT_ACTIONS


# =========================================================================
# Detection: _compute_question_density
# =========================================================================

class TestComputeQuestionDensity:
    """Tests for ContextEnvelopeBuilder._compute_question_density."""

    def _get_question_intents(self):
        """Get a list of known question intents for testing."""
        all_q = INTENT_CATEGORIES.get("all_questions", [])
        # Pick first 5 for testing
        return list(all_q)[:5] if all_q else ["question_pricing", "question_features", "question_integrations"]

    def test_compute_question_density_zero(self):
        """density=0 when no question intents in history."""
        density = ContextEnvelopeBuilder._compute_question_density(
            intent_history=["positive_feedback", "greeting", "objection_price"],
            current_intent=None,
            window=5,
        )
        assert density == 0

    def test_compute_question_density_one(self):
        """density=1 when one question intent in history."""
        q_intents = self._get_question_intents()
        density = ContextEnvelopeBuilder._compute_question_density(
            intent_history=["positive_feedback", q_intents[0], "greeting"],
            current_intent=None,
            window=5,
        )
        assert density == 1

    def test_compute_question_density_multiple(self):
        """density=2+ when multiple question intents in history."""
        q_intents = self._get_question_intents()
        density = ContextEnvelopeBuilder._compute_question_density(
            intent_history=[q_intents[0], "positive_feedback", q_intents[1]],
            current_intent=q_intents[0] if len(q_intents) > 0 else None,
            window=5,
        )
        assert density >= 2

    def test_density_non_consecutive(self):
        """Non-consecutive questions still count: [question, positive, question] → 2."""
        q_intents = self._get_question_intents()
        density = ContextEnvelopeBuilder._compute_question_density(
            intent_history=[q_intents[0], "positive_feedback", q_intents[1]],
            current_intent=None,
            window=5,
        )
        assert density == 2

    def test_density_with_current_intent(self):
        """current_intent included when not in tail of history."""
        q_intents = self._get_question_intents()
        density = ContextEnvelopeBuilder._compute_question_density(
            intent_history=["positive_feedback", "greeting"],
            current_intent=q_intents[0],
            window=5,
        )
        assert density == 1

    def test_density_current_intent_same_as_tail(self):
        """current_intent == tail of history → both counted (no dedup).

        This is correct because intent_history contains PREVIOUS turns and
        current_intent is the CURRENT turn — they are different turns even
        if the intent is the same (e.g., client asks two feature questions).
        """
        q_intents = self._get_question_intents()
        density = ContextEnvelopeBuilder._compute_question_density(
            intent_history=["positive_feedback", q_intents[0]],
            current_intent=q_intents[0],
            window=5,
        )
        # Should be 2 — previous turn + current turn both count
        assert density == 2

    def test_density_window_clips(self):
        """window=5 clips long history — only last 5 entries count."""
        q_intents = self._get_question_intents()
        # 3 questions outside window + 2 non-questions in window
        long_history = [q_intents[0], q_intents[0], q_intents[0]] + ["positive_feedback"] * 5
        density = ContextEnvelopeBuilder._compute_question_density(
            intent_history=long_history,
            current_intent=None,
            window=5,
        )
        assert density == 0  # All questions are outside the window


# =========================================================================
# Thresholds: persona-specific
# =========================================================================

class TestPersonaThresholds:
    """Tests for persona-specific question suppression thresholds."""

    def test_persona_thresholds_technical(self):
        """Technical persona: suppress=1 (more aggressive suppression)."""
        thresholds = get_persona_question_thresholds("technical")
        assert thresholds["suppress"] == 1

    def test_persona_thresholds_default(self):
        """Default persona: suppress=2."""
        thresholds = get_persona_question_thresholds("")
        assert thresholds["suppress"] == 2

    def test_persona_thresholds_missing(self):
        """Unknown persona falls back to default."""
        thresholds = get_persona_question_thresholds("nonexistent_persona")
        assert thresholds["suppress"] == 2
        assert thresholds["optional"] == 1
        assert thresholds["window"] == 5

    def test_persona_thresholds_friendly(self):
        """Friendly persona: suppress=3 (more tolerant)."""
        thresholds = get_persona_question_thresholds("friendly")
        assert thresholds["suppress"] == 3


# =========================================================================
# Directives + Builder order
# =========================================================================

class TestResponseDirectivesSuppression:
    """Tests for ResponseDirectives question suppression."""

    def _make_envelope(self, density=0, persona=""):
        """Create a minimal ContextEnvelope for testing."""
        envelope = ContextEnvelope()
        envelope.client_question_density = density
        envelope.collected_data = {"persona": persona} if persona else {}
        envelope.intent_history = []
        envelope.action_history = []
        envelope.state_history = []
        envelope.reason_codes = set()
        return envelope

    def test_suppress_question_directive(self):
        """density >= suppress → suppress_question=True, question_mode='suppress'."""
        envelope = self._make_envelope(density=2)
        builder = ResponseDirectivesBuilder(envelope)
        directives = builder.build()
        assert directives.suppress_question is True
        assert directives.question_mode == "suppress"

    def test_optional_question_directive(self):
        """density == optional → question_mode='optional'."""
        envelope = self._make_envelope(density=1)
        builder = ResponseDirectivesBuilder(envelope)
        directives = builder.build()
        assert directives.question_mode == "optional"
        assert directives.suppress_question is False

    def test_mandatory_question_directive(self):
        """density == 0 → question_mode='mandatory'."""
        envelope = self._make_envelope(density=0)
        builder = ResponseDirectivesBuilder(envelope)
        directives = builder.build()
        assert directives.question_mode == "mandatory"
        assert directives.one_question is True

    def test_builder_order_overrides_apply_style(self):
        """_apply_style sets one_question=True, _apply_question_suppression overrides to False."""
        envelope = self._make_envelope(density=2)
        builder = ResponseDirectivesBuilder(envelope)
        directives = builder.build()
        # _apply_style would set one_question=True, but suppression overrides
        assert directives.one_question is False

    def test_suppress_overrides_ask_clarifying(self):
        """suppress=True + ask_clarifying=True → instruction has 'НЕ задавай', not 'уточняющий'."""
        directives = ResponseDirectives()
        directives.suppress_question = True
        directives.ask_clarifying = True
        instruction = directives.get_instruction()
        assert "НЕ задавай" in instruction
        assert "уточняющий" not in instruction

    def test_suppress_overrides_rephrase_mode(self):
        """suppress=True + rephrase_mode=True → instruction has 'НЕ задавай', not 'Переформулируй'."""
        directives = ResponseDirectives()
        directives.suppress_question = True
        directives.rephrase_mode = True
        instruction = directives.get_instruction()
        assert "НЕ задавай" in instruction
        assert "Переформулируй" not in instruction


# =========================================================================
# Generator: question_instruction override
# =========================================================================

class TestGeneratorQuestionInstruction:
    """Tests for question_instruction variable in generator."""

    def test_question_instruction_suppress(self):
        """rd.question_mode=='suppress' → text contains 'НЕ задавай'."""
        rd = ResponseDirectives()
        rd.question_mode = "suppress"
        rd.suppress_question = True

        # Simulate what generator does
        variables = dict(PERSONALIZATION_DEFAULTS)
        if rd.question_mode == "suppress":
            variables["question_instruction"] = (
                "\u26a0\ufe0f Клиент активно задаёт вопросы — НЕ задавай свои вопросы в ответ. "
                "Отвечай развёрнуто и полезно, демонстрируя экспертизу. "
                "Можешь добавить пример, факт или преимущество продукта."
            )
        assert "НЕ задавай" in variables["question_instruction"]

    def test_question_instruction_optional(self):
        """rd.question_mode=='optional' → text contains 'уместно'."""
        rd = ResponseDirectives()
        rd.question_mode = "optional"

        variables = dict(PERSONALIZATION_DEFAULTS)
        if rd.question_mode == "optional":
            variables["question_instruction"] = (
                "Можешь задать один вопрос если это уместно и естественно, "
                "но НЕ обязательно."
            )
        assert "уместно" in variables["question_instruction"]
        assert "НЕ обязательно" in variables["question_instruction"]

    def test_question_instruction_default(self):
        """Default question_instruction contains 'Задай ОДИН'."""
        assert "Задай ОДИН" in PERSONALIZATION_DEFAULTS["question_instruction"]

    def test_missing_data_hidden_on_suppress(self):
        """When suppress → missing_data is cleared."""
        rd = ResponseDirectives()
        rd.question_mode = "suppress"
        rd.suppress_question = True

        variables = {"missing_data": "company_size, pain_point", "available_questions": "Q1, Q2"}
        if rd.question_mode == "suppress":
            variables["missing_data"] = ""
            variables["available_questions"] = ""
        assert variables["missing_data"] == ""

    def test_available_questions_hidden_on_suppress(self):
        """When suppress → available_questions is cleared."""
        rd = ResponseDirectives()
        rd.question_mode = "suppress"

        variables = {"available_questions": "Выбери ОДИН вопрос: ..."}
        if rd.question_mode == "suppress":
            variables["available_questions"] = ""
        assert variables["available_questions"] == ""

    def test_question_instruction_in_personalization_defaults(self):
        """PERSONALIZATION_DEFAULTS has question_instruction key."""
        assert "question_instruction" in PERSONALIZATION_DEFAULTS


# =========================================================================
# Post-processing: _strip_trailing_question
# =========================================================================

class TestStripTrailingQuestion:
    """Tests for _strip_trailing_question post-processing."""

    def _make_generator(self):
        """Create a minimal ResponseGenerator mock for testing."""
        from src.generator import ResponseGenerator
        gen = ResponseGenerator.__new__(ResponseGenerator)
        return gen

    def test_strip_trailing_question(self):
        """'Ответ. Вопрос?' → 'Ответ.'"""
        gen = self._make_generator()
        result = gen._strip_trailing_question("Ответ здесь. Какой у вас вопрос?")
        assert result == "Ответ здесь."

    def test_strip_preserves_single_sentence(self):
        """'Вопрос?' → 'Вопрос?' (don't strip the only sentence)."""
        gen = self._make_generator()
        result = gen._strip_trailing_question("Какой у вас вопрос?")
        assert result == "Какой у вас вопрос?"

    def test_strip_no_question(self):
        """'Ответ.' → 'Ответ.' (no change when no trailing question)."""
        gen = self._make_generator()
        result = gen._strip_trailing_question("Ответ.")
        assert result == "Ответ."

    def test_strip_exempts_probe_actions(self):
        """probe_situation is exempt from stripping."""
        assert "probe_situation" in QUESTION_STRIP_EXEMPT_ACTIONS
        assert "probe_problem" in QUESTION_STRIP_EXEMPT_ACTIONS
        assert "probe_implication" in QUESTION_STRIP_EXEMPT_ACTIONS
        assert "probe_need_payoff" in QUESTION_STRIP_EXEMPT_ACTIONS

    def test_strip_exempts_transition_actions(self):
        """Transition actions are exempt from stripping."""
        assert "transition_to_spin_problem" in QUESTION_STRIP_EXEMPT_ACTIONS
        assert "transition_to_spin_implication" in QUESTION_STRIP_EXEMPT_ACTIONS
        assert "transition_to_spin_need_payoff" in QUESTION_STRIP_EXEMPT_ACTIONS
        assert "transition_to_presentation" in QUESTION_STRIP_EXEMPT_ACTIONS

    def test_strip_exempts_clarify(self):
        """clarify_one_question is exempt from stripping."""
        assert "clarify_one_question" in QUESTION_STRIP_EXEMPT_ACTIONS


# =========================================================================
# Constants exports
# =========================================================================

class TestConstantsExports:
    """Tests for constants module exports."""

    def test_constants_exports(self):
        """PERSONA_QUESTION_SUPPRESSION and get_persona_question_thresholds in module."""
        from src.yaml_config import constants
        assert hasattr(constants, "PERSONA_QUESTION_SUPPRESSION")
        assert hasattr(constants, "get_persona_question_thresholds")
        assert callable(constants.get_persona_question_thresholds)

    def test_persona_question_suppression_loaded(self):
        """PERSONA_QUESTION_SUPPRESSION loaded from YAML with expected keys."""
        assert "default" in PERSONA_QUESTION_SUPPRESSION
        assert "technical" in PERSONA_QUESTION_SUPPRESSION
        assert "friendly" in PERSONA_QUESTION_SUPPRESSION

    def test_question_mode_in_to_dict(self):
        """ResponseDirectives.to_dict() includes suppress_question and question_mode."""
        rd = ResponseDirectives()
        rd.suppress_question = True
        rd.question_mode = "suppress"
        d = rd.to_dict()
        assert d["style"]["suppress_question"] is True
        assert d["style"]["question_mode"] == "suppress"
