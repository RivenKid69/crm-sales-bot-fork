"""
Tests for hallucination prevention: KB-empty guard (generator.py) and
ResponseBoundaryValidator extended detectors (response_boundary_validator.py).
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.response_boundary_validator import ResponseBoundaryValidator


# =============================================================================
# ResponseBoundaryValidator — new violation detectors
# =============================================================================


class TestHallucinatedIIN:
    def setup_method(self):
        self.validator = ResponseBoundaryValidator()

    def _ctx(self, facts: str = "") -> dict:
        return {"retrieved_facts": facts, "intent": "question_integration"}

    def test_iin_in_response_not_in_facts_triggers_violation(self):
        result = self.validator.validate_response(
            "Ваш ИИН: 123456789012",
            context=self._ctx(facts=""),
        )
        assert "hallucinated_iin" in result.violations

    def test_iin_in_response_and_in_facts_passes(self):
        facts = "Клиент с ИИН 123456789012 зарегистрирован."
        result = self.validator.validate_response(
            "Ваш ИИН: 123456789012",
            context=self._ctx(facts=facts),
        )
        assert "hallucinated_iin" not in result.violations

    def test_iin_violation_returns_fallback_not_original(self):
        result = self.validator.validate_response(
            "ИИН: 123456789012",
            context=self._ctx(facts=""),
        )
        assert result.fallback_used is True
        assert "123456789012" not in result.response
        # Fallback phrase should contain "уточню" or "коллег"
        lower = result.response.lower()
        assert "уточню" in lower or "коллег" in lower or "специалист" in lower

    def test_no_iin_in_response_no_violation(self):
        result = self.validator.validate_response(
            "Тариф Mini — 5000₸/мес.",
            context=self._ctx(),
        )
        assert "hallucinated_iin" not in result.violations


class TestHallucinatedPhone:
    def setup_method(self):
        self.validator = ResponseBoundaryValidator()

    def _ctx(self, facts: str = "") -> dict:
        return {"retrieved_facts": facts, "intent": "question_contact"}

    def test_kz_phone_not_in_facts_triggers_violation(self):
        result = self.validator.validate_response(
            "Позвоните нам: +7 777 123 45 67",
            context=self._ctx(facts=""),
        )
        assert "hallucinated_phone" in result.violations

    def test_kz_phone_present_in_facts_passes(self):
        facts = "Контакт менеджера: +7 777 123 45 67"
        result = self.validator.validate_response(
            "Звоните: +7 777 123 45 67",
            context=self._ctx(facts=facts),
        )
        assert "hallucinated_phone" not in result.violations

    def test_phone_violation_triggers_hard_fallback(self):
        result = self.validator.validate_response(
            "Наш номер: 87771234567",
            context=self._ctx(facts=""),
        )
        assert result.fallback_used is True
        assert "87771234567" not in result.response


class TestHallucinatedSendPromise:
    def setup_method(self):
        self.validator = ResponseBoundaryValidator()

    def _ctx(self) -> dict:
        return {"retrieved_facts": "", "intent": "question_docs"}

    def test_send_promise_triggers_violation(self):
        result = self.validator.validate_response(
            "Пришлю вам фото системы прямо сейчас.",
            context=self._ctx(),
        )
        assert "hallucinated_send_promise" in result.violations

    def test_send_promise_sanitized_not_hard_fallback(self):
        result = self.validator.validate_response(
            "Отправлю вам файл с тарифами.",
            context=self._ctx(),
        )
        # send_promise is NOT a hard hallucination — goes through sanitize path
        assert result.fallback_used is False or "hallucinated_send_promise" in result.violations
        # After sanitize the original promise text should be replaced
        assert "отправлю" not in result.response.lower() or "менеджер" in result.response.lower()

    def test_sanitize_replaces_send_promise_text(self):
        validator = ResponseBoundaryValidator()
        sanitized = validator._sanitize_send_promise("Скину вам каталог через минуту.")
        assert "менеджер" in sanitized.lower()
        assert "скину" not in sanitized.lower()


class TestHallucinatedPastAction:
    def setup_method(self):
        self.validator = ResponseBoundaryValidator()

    def _ctx(self) -> dict:
        return {"retrieved_facts": "", "intent": "question_status"}

    def test_past_action_triggers_violation(self):
        result = self.validator.validate_response(
            "Мы уже отправили вам договор вчера.",
            context=self._ctx(),
        )
        assert "hallucinated_past_action" in result.violations

    def test_past_action_returns_fallback(self):
        result = self.validator.validate_response(
            "Мы только что связались с вами.",
            context=self._ctx(),
        )
        assert result.fallback_used is True
        assert "отправили" not in result.response.lower()
        assert "связались" not in result.response.lower()


# =============================================================================
# KB-empty guard (generator.py)
# =============================================================================


def _make_generator_with_empty_kb():
    """
    Build a minimal ResponseGenerator with autonomous flow + empty KB retrieval.
    All heavy dependencies (LLM, retriever, enhanced pipeline) are mocked.
    """
    from src.generator import ResponseGenerator

    llm = MagicMock()
    flow = MagicMock()
    flow.name = "autonomous"
    flow.get_template.return_value = None

    gen = ResponseGenerator(llm=llm, flow=flow)

    # Patch retriever to return empty facts
    mock_retriever = MagicMock()
    mock_retriever.kb = MagicMock()
    mock_retriever.kb.company_name = "Wipon"
    mock_retriever.kb.company_description = "POS система"
    mock_retriever.get_company_info.return_value = "Wipon: POS система"

    return gen, flow, mock_retriever


def _autonomous_context(intent: str, contact: str = None) -> dict:
    collected = {}
    if contact:
        collected["contact_info"] = contact
    return {
        "intent": intent,
        "state": "autonomous_qualification",
        "user_message": "Тест",
        "history": [],
        "spin_phase": "situation",
        "collected_data": collected,
        "recent_fact_keys": [],
    }


class TestKBEmptyGuard:
    """Tests for the KB-empty hallucination guard in generator.generate()."""

    @patch("src.generator.get_retriever")
    def test_factual_intent_empty_kb_returns_handoff(self, mock_get_retriever):
        from src.generator import ResponseGenerator

        mock_retriever = MagicMock()
        mock_retriever.kb = MagicMock()
        mock_retriever.kb.company_name = "Wipon"
        mock_retriever.kb.company_description = "POS система"
        mock_get_retriever.return_value = mock_retriever

        llm = MagicMock()
        flow = MagicMock()
        flow.name = "autonomous"
        flow.get_template.return_value = None
        gen = ResponseGenerator(llm=llm, flow=flow)

        # Patch enhanced pipeline to return empty facts
        pipeline = MagicMock()
        pipeline.retrieve.return_value = ("", [], [])
        gen._enhanced_pipeline = pipeline

        ctx = _autonomous_context("question_integration")
        response = gen.generate(action="autonomous_respond", context=ctx)

        lower = response.lower()
        assert "уточню" in lower or "коллег" in lower or "специалист" in lower or "менеджер" in lower
        # Must not call LLM
        llm.generate.assert_not_called()

    @patch("src.generator.get_retriever")
    def test_factual_intent_empty_kb_with_contact_no_contact_question(self, mock_get_retriever):
        from src.generator import ResponseGenerator

        mock_retriever = MagicMock()
        mock_retriever.kb = MagicMock()
        mock_retriever.kb.company_name = "Wipon"
        mock_retriever.kb.company_description = "POS система"
        mock_get_retriever.return_value = mock_retriever

        llm = MagicMock()
        flow = MagicMock()
        flow.name = "autonomous"
        flow.get_template.return_value = None
        gen = ResponseGenerator(llm=llm, flow=flow)

        pipeline = MagicMock()
        pipeline.retrieve.return_value = ("", [], [])
        gen._enhanced_pipeline = pipeline

        ctx = _autonomous_context("price_question", contact="+77771234567")
        response = gen.generate(action="autonomous_respond", context=ctx)

        # Contact is known → should NOT ask for contact
        assert "?" not in response or "номер" not in response.lower()

    @patch("src.generator.get_retriever")
    def test_greeting_intent_empty_kb_does_not_trigger_guard(self, mock_get_retriever):
        """Conversational intents must bypass KB guard regardless of empty KB."""
        from src.generator import ResponseGenerator

        mock_retriever = MagicMock()
        mock_retriever.kb = MagicMock()
        mock_retriever.kb.company_name = "Wipon"
        mock_retriever.kb.company_description = "POS система"
        mock_retriever.get_company_info.return_value = "Wipon: POS система"
        mock_get_retriever.return_value = mock_retriever

        llm = MagicMock()
        llm.generate.return_value = "Добрый день! Чем могу помочь?"
        flow = MagicMock()
        flow.name = "autonomous"
        flow.get_template.return_value = None
        gen = ResponseGenerator(llm=llm, flow=flow)

        pipeline = MagicMock()
        pipeline.retrieve.return_value = ("", [], [])
        gen._enhanced_pipeline = pipeline

        ctx = _autonomous_context("greeting")
        gen.generate(action="autonomous_respond", context=ctx)
        # LLM should have been called (guard skipped for greeting)
        llm.generate.assert_called()

    @patch("src.generator.get_retriever")
    def test_factual_intent_with_facts_does_not_trigger_guard(self, mock_get_retriever):
        """When KB returns facts, guard must not fire — LLM is called normally."""
        from src.generator import ResponseGenerator

        mock_retriever = MagicMock()
        mock_retriever.kb = MagicMock()
        mock_retriever.kb.company_name = "Wipon"
        mock_retriever.kb.company_description = "POS система"
        mock_get_retriever.return_value = mock_retriever

        llm = MagicMock()
        llm.generate.return_value = "Интеграция с 1С поддерживается."
        flow = MagicMock()
        flow.name = "autonomous"
        flow.get_template.return_value = None
        gen = ResponseGenerator(llm=llm, flow=flow)

        pipeline = MagicMock()
        pipeline.retrieve.return_value = ("Интеграция с 1С: поддерживается через API.", [], ["integration"])
        gen._enhanced_pipeline = pipeline

        ctx = _autonomous_context("question_integration")
        gen.generate(action="autonomous_respond", context=ctx)
        llm.generate.assert_called()

    @patch("src.generator.get_retriever")
    def test_meta_template_key_is_kb_empty_handoff(self, mock_get_retriever):
        """_last_generation_meta must record kb_empty_handoff when guard fires."""
        from src.generator import ResponseGenerator

        mock_retriever = MagicMock()
        mock_retriever.kb = MagicMock()
        mock_retriever.kb.company_name = "Wipon"
        mock_retriever.kb.company_description = "POS система"
        mock_get_retriever.return_value = mock_retriever

        llm = MagicMock()
        flow = MagicMock()
        flow.name = "autonomous"
        flow.get_template.return_value = None
        gen = ResponseGenerator(llm=llm, flow=flow)

        pipeline = MagicMock()
        pipeline.retrieve.return_value = ("", [], [])
        gen._enhanced_pipeline = pipeline

        ctx = _autonomous_context("question_security")
        gen.generate(action="autonomous_respond", context=ctx)
        assert gen._last_generation_meta["selected_template_key"] == "kb_empty_handoff"
