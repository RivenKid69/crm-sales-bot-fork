"""
Тесты для ContextEnvelope и PIIRedactor.

Phase 0-1 из PLAN_CONTEXT_POLICY.md:
- ContextEnvelope: единый контракт контекста
- ContextEnvelopeBuilder: сборка из всех источников
- PIIRedactor: маскирование PII данных
- ReasonCode: объяснимость решений
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from context_envelope import (
    ContextEnvelope,
    ContextEnvelopeBuilder,
    ReasonCode,
    PIIRedactor,
    pii_redactor,
    build_context_envelope,
)


class TestReasonCode:
    """Тесты для ReasonCode enum."""

    def test_reason_code_values(self):
        """Проверить что все reason codes имеют правильный формат."""
        for code in ReasonCode:
            # Формат: category.subcategory или category.subcategory.detail
            parts = code.value.split(".")
            assert len(parts) >= 2, f"Invalid format: {code.value}"
            assert all(p for p in parts), f"Empty part in: {code.value}"

    def test_repair_codes(self):
        """Проверить repair reason codes."""
        repair_codes = [
            ReasonCode.REPAIR_STUCK,
            ReasonCode.REPAIR_OSCILLATION,
            ReasonCode.REPAIR_REPEATED_QUESTION,
            ReasonCode.REPAIR_CONFIDENCE_LOW,
        ]
        for code in repair_codes:
            assert code.value.startswith("repair.")

    def test_objection_codes(self):
        """Проверить objection reason codes."""
        objection_codes = [
            ReasonCode.OBJECTION_FIRST,
            ReasonCode.OBJECTION_REPEAT,
            ReasonCode.OBJECTION_REPEAT_PRICE,
            ReasonCode.OBJECTION_REPEAT_COMPETITOR,
            ReasonCode.OBJECTION_ESCALATE,
        ]
        for code in objection_codes:
            assert code.value.startswith("objection.")


class TestContextEnvelope:
    """Тесты для ContextEnvelope dataclass."""

    def test_default_values(self):
        """Проверить default значения."""
        envelope = ContextEnvelope()

        # Базовый контекст
        assert envelope.state == "greeting"
        assert envelope.spin_phase is None
        assert envelope.collected_data == {}
        assert envelope.missing_data == []

        # Level 1
        assert envelope.intent_history == []
        assert envelope.objection_count == 0
        assert envelope.has_oscillation is False
        assert envelope.is_stuck is False

        # Level 2
        assert envelope.momentum == 0.0
        assert envelope.engagement_level == "medium"
        assert envelope.engagement_score == 0.5

        # Level 3
        assert envelope.first_objection_type is None
        assert envelope.total_objections == 0
        assert envelope.has_breakthrough is False

        # Meta
        assert envelope.reason_codes == []

    def test_add_reason(self):
        """Проверить добавление reason codes."""
        envelope = ContextEnvelope()

        envelope.add_reason(ReasonCode.REPAIR_STUCK)
        assert ReasonCode.REPAIR_STUCK.value in envelope.reason_codes

        # Повторное добавление не дублирует
        envelope.add_reason(ReasonCode.REPAIR_STUCK)
        assert envelope.reason_codes.count(ReasonCode.REPAIR_STUCK.value) == 1

    def test_has_reason(self):
        """Проверить проверку reason codes."""
        envelope = ContextEnvelope()
        envelope.add_reason(ReasonCode.BREAKTHROUGH_DETECTED)

        assert envelope.has_reason(ReasonCode.BREAKTHROUGH_DETECTED)
        assert not envelope.has_reason(ReasonCode.REPAIR_STUCK)

    def test_get_reasons_by_category(self):
        """Проверить фильтрацию reason codes по категории."""
        envelope = ContextEnvelope()
        envelope.add_reason(ReasonCode.REPAIR_STUCK)
        envelope.add_reason(ReasonCode.REPAIR_OSCILLATION)
        envelope.add_reason(ReasonCode.OBJECTION_FIRST)

        repair_reasons = envelope.get_reasons_by_category("repair")
        assert len(repair_reasons) == 2
        assert "repair.stuck" in repair_reasons
        assert "repair.oscillation" in repair_reasons

        objection_reasons = envelope.get_reasons_by_category("objection")
        assert len(objection_reasons) == 1

    def test_for_classifier(self):
        """Проверить контекст для классификатора."""
        envelope = ContextEnvelope(
            state="spin_situation",
            spin_phase="situation",
            collected_data={"company_size": 10},
            intent_history=["greeting", "company_size"],
            is_stuck=True,
            momentum_direction="positive",
        )

        ctx = envelope.for_classifier()

        assert ctx["state"] == "spin_situation"
        assert ctx["spin_phase"] == "situation"
        assert ctx["collected_data"] == {"company_size": 10}
        assert ctx["intent_history"] == ["greeting", "company_size"]
        assert ctx["is_stuck"] is True
        assert ctx["momentum_direction"] == "positive"

    def test_for_generator(self):
        """Проверить контекст для генератора."""
        envelope = ContextEnvelope(
            state="presentation",
            frustration_level=3,
            should_apologize=True,
            client_pain_points=["потеря клиентов"],
            reason_codes=["repair.stuck"],
        )

        ctx = envelope.for_generator()

        assert ctx["state"] == "presentation"
        assert ctx["frustration_level"] == 3
        assert ctx["should_apologize"] is True
        assert ctx["client_pain_points"] == ["потеря клиентов"]
        assert ctx["reason_codes"] == ["repair.stuck"]

    def test_for_policy(self):
        """Проверить контекст для policy."""
        envelope = ContextEnvelope(
            state="spin_problem",
            is_stuck=True,
            momentum=-0.3,
            momentum_direction="negative",
            total_objections=2,
            most_effective_action="ask_pain_point",
        )

        ctx = envelope.for_policy()

        assert ctx["state"] == "spin_problem"
        assert ctx["is_stuck"] is True
        assert ctx["momentum"] == -0.3
        assert ctx["momentum_direction"] == "negative"
        assert ctx["total_objections"] == 2
        assert ctx["most_effective_action"] == "ask_pain_point"

    def test_to_dict(self):
        """Проверить сериализацию в словарь."""
        envelope = ContextEnvelope(
            state="greeting",
            total_turns=5,
            objection_count=1,
        )

        d = envelope.to_dict()

        assert isinstance(d, dict)
        assert d["state"] == "greeting"
        assert d["total_turns"] == 5
        assert d["objection_count"] == 1


class TestPIIRedactor:
    """Тесты для PIIRedactor."""

    def test_redact_phone(self):
        """Проверить маскирование телефонов."""
        redactor = PIIRedactor()

        # В тексте
        text = "Мой телефон +7 999 123-45-67"
        result = redactor.redact_text(text)
        assert "[PHONE]" in result
        assert "999" not in result

        # В данных
        data = {"phone": "+79991234567", "name": "test"}
        result = redactor.redact(data)
        assert result["phone"] != "+79991234567"
        assert "**" in result["phone"]

    def test_redact_email(self):
        """Проверить маскирование email."""
        redactor = PIIRedactor()

        # В тексте
        text = "Напишите на test@example.com"
        result = redactor.redact_text(text)
        assert "[EMAIL]" in result
        assert "test@example.com" not in result

        # В данных
        data = {"email": "client@company.ru"}
        result = redactor.redact(data)
        assert "**" in result["email"]

    def test_redact_preserves_non_pii(self):
        """Проверить что non-PII данные сохраняются."""
        redactor = PIIRedactor()

        data = {
            "company_size": 10,
            "business_type": "розница",
            "pain_point": "потеря клиентов",
        }

        result = redactor.redact(data)

        assert result["company_size"] == 10
        assert result["business_type"] == "розница"
        assert result["pain_point"] == "потеря клиентов"

    def test_redact_nested_dict(self):
        """Проверить маскирование во вложенных словарях."""
        redactor = PIIRedactor()

        data = {
            "client": {
                "phone": "+79991234567",
                "company": "ООО Тест"
            }
        }

        result = redactor.redact(data)

        assert "**" in result["client"]["phone"]
        assert result["client"]["company"] == "ООО Тест"

    def test_is_pii_key(self):
        """Проверить определение PII ключей."""
        redactor = PIIRedactor()

        assert redactor.is_pii_key("phone")
        assert redactor.is_pii_key("email")
        assert redactor.is_pii_key("contact_name")
        assert not redactor.is_pii_key("company_size")
        assert not redactor.is_pii_key("business_type")

    def test_mask_value(self):
        """Проверить маскирование значений."""
        redactor = PIIRedactor()

        # Короткое значение
        assert redactor._mask_value("ab") == "**"

        # Длинное значение
        masked = redactor._mask_value("+79991234567")
        assert masked.startswith("+7")
        assert masked.endswith("67")
        assert "*" in masked

    def test_singleton_instance(self):
        """Проверить singleton instance."""
        assert pii_redactor is not None
        assert isinstance(pii_redactor, PIIRedactor)


class TestContextEnvelopeBuilder:
    """Тесты для ContextEnvelopeBuilder."""

    def test_build_empty(self):
        """Проверить сборку без источников."""
        builder = ContextEnvelopeBuilder()
        envelope = builder.build()

        assert envelope.state == "greeting"
        # momentum.neutral всегда добавляется для нейтрального momentum
        assert "momentum.neutral" in envelope.reason_codes

    def test_build_with_tone_info(self):
        """Проверить сборку с tone info."""
        tone_info = {
            "tone": "frustrated",
            "frustration_level": 4,
            "should_apologize": True,
            "should_offer_exit": True,
        }

        builder = ContextEnvelopeBuilder(tone_info=tone_info)
        envelope = builder.build()

        assert envelope.tone == "frustrated"
        assert envelope.frustration_level == 4
        assert envelope.should_apologize is True
        assert envelope.should_offer_exit is True

    def test_build_with_guard_info(self):
        """Проверить сборку с guard info."""
        guard_info = {"intervention": "tier_2"}

        builder = ContextEnvelopeBuilder(guard_info=guard_info)
        envelope = builder.build()

        assert envelope.guard_intervention == "tier_2"
        assert envelope.has_reason(ReasonCode.GUARD_INTERVENTION)

    def test_compute_reason_codes_repair(self):
        """Проверить вычисление repair reason codes."""
        # Создаём envelope с repair сигналами
        envelope = ContextEnvelope(
            is_stuck=True,
            has_oscillation=True,
            repeated_question="question_price",
            confidence_trend="decreasing",
        )

        # Вручную вызываем _compute_reason_codes
        builder = ContextEnvelopeBuilder()
        builder._compute_reason_codes(envelope)

        assert envelope.has_reason(ReasonCode.REPAIR_STUCK)
        assert envelope.has_reason(ReasonCode.REPAIR_OSCILLATION)
        assert envelope.has_reason(ReasonCode.REPAIR_REPEATED_QUESTION)
        assert envelope.has_reason(ReasonCode.REPAIR_CONFIDENCE_LOW)
        assert envelope.has_reason(ReasonCode.POLICY_REPAIR_MODE)

    def test_compute_reason_codes_objection(self):
        """Проверить вычисление objection reason codes."""
        envelope = ContextEnvelope(
            first_objection_type="objection_price",
            total_objections=1,
        )

        builder = ContextEnvelopeBuilder()
        builder._compute_reason_codes(envelope)

        assert envelope.has_reason(ReasonCode.OBJECTION_FIRST)

        # С повторными возражениями
        envelope2 = ContextEnvelope(
            first_objection_type="objection_price",
            total_objections=3,
            repeated_objection_types=["objection_price", "objection_competitor"],
        )

        builder._compute_reason_codes(envelope2)

        assert envelope2.has_reason(ReasonCode.OBJECTION_REPEAT)
        assert envelope2.has_reason(ReasonCode.OBJECTION_REPEAT_PRICE)
        assert envelope2.has_reason(ReasonCode.OBJECTION_REPEAT_COMPETITOR)
        assert envelope2.has_reason(ReasonCode.OBJECTION_ESCALATE)

    def test_compute_reason_codes_breakthrough(self):
        """Проверить вычисление breakthrough reason codes."""
        envelope = ContextEnvelope(
            has_breakthrough=True,
            breakthrough_turn=5,
            total_turns=7,
            turns_since_breakthrough=2,
        )

        builder = ContextEnvelopeBuilder()
        builder._compute_reason_codes(envelope)

        assert envelope.has_reason(ReasonCode.BREAKTHROUGH_DETECTED)
        assert envelope.has_reason(ReasonCode.BREAKTHROUGH_WINDOW)
        assert envelope.has_reason(ReasonCode.BREAKTHROUGH_CTA)

    def test_compute_reason_codes_momentum(self):
        """Проверить вычисление momentum reason codes."""
        # Positive momentum
        envelope1 = ContextEnvelope(momentum_direction="positive")
        builder = ContextEnvelopeBuilder()
        builder._compute_reason_codes(envelope1)
        assert envelope1.has_reason(ReasonCode.MOMENTUM_POSITIVE)

        # Negative momentum
        envelope2 = ContextEnvelope(momentum_direction="negative")
        builder._compute_reason_codes(envelope2)
        assert envelope2.has_reason(ReasonCode.MOMENTUM_NEGATIVE)

    def test_compute_reason_codes_engagement(self):
        """Проверить вычисление engagement reason codes."""
        # High engagement
        envelope1 = ContextEnvelope(engagement_level="high")
        builder = ContextEnvelopeBuilder()
        builder._compute_reason_codes(envelope1)
        assert envelope1.has_reason(ReasonCode.ENGAGEMENT_HIGH)

        # Low engagement
        envelope2 = ContextEnvelope(engagement_level="low")
        builder._compute_reason_codes(envelope2)
        assert envelope2.has_reason(ReasonCode.ENGAGEMENT_LOW)

        # Declining engagement
        envelope3 = ContextEnvelope(engagement_trend="declining")
        builder._compute_reason_codes(envelope3)
        assert envelope3.has_reason(ReasonCode.ENGAGEMENT_DECLINING)

    def test_compute_reason_codes_policy(self):
        """Проверить вычисление policy reason codes."""
        # Conservative mode
        envelope1 = ContextEnvelope(
            confidence_trend="decreasing",
            momentum_direction="negative",
        )
        builder = ContextEnvelopeBuilder()
        builder._compute_reason_codes(envelope1)
        assert envelope1.has_reason(ReasonCode.POLICY_CONSERVATIVE)

        # Accelerate mode
        envelope2 = ContextEnvelope(
            momentum_direction="positive",
            is_progressing=True,
        )
        builder._compute_reason_codes(envelope2)
        assert envelope2.has_reason(ReasonCode.POLICY_ACCELERATE)


class TestBuildContextEnvelope:
    """Тесты для функции build_context_envelope."""

    def test_build_context_envelope_simple(self):
        """Проверить простой вызов функции."""
        envelope = build_context_envelope(
            tone_info={"frustration_level": 2},
            last_action="ask_company_size",
            last_intent="greeting",
        )

        assert envelope.frustration_level == 2
        assert envelope.last_action == "ask_company_size"
        assert envelope.last_intent == "greeting"

    def test_build_context_envelope_v2_engagement(self):
        """Проверить флаг v2 engagement."""
        envelope = build_context_envelope(
            use_v2_engagement=True,
        )

        # Envelope создаётся успешно с флагом v2
        assert envelope is not None


class TestContextEnvelopeIntegration:
    """Интеграционные тесты для ContextEnvelope."""

    def test_full_context_flow(self):
        """Проверить полный flow создания контекста."""
        # Симулируем данные из разных источников
        tone_info = {
            "tone": "interested",
            "frustration_level": 1,
            "should_apologize": False,
        }

        guard_info = {
            "intervention": None,
        }

        # Создаём envelope
        envelope = build_context_envelope(
            tone_info=tone_info,
            guard_info=guard_info,
            last_action="ask_pain_point",
            last_intent="company_size",
        )

        # Проверяем что всё заполнено
        assert envelope.tone == "interested"
        assert envelope.frustration_level == 1
        assert envelope.guard_intervention is None
        assert envelope.last_action == "ask_pain_point"
        assert envelope.last_intent == "company_size"

        # Проверяем контексты для подсистем
        classifier_ctx = envelope.for_classifier()
        assert "state" in classifier_ctx
        assert "intent_history" in classifier_ctx

        generator_ctx = envelope.for_generator()
        assert "tone" in generator_ctx
        assert "frustration_level" in generator_ctx

        policy_ctx = envelope.for_policy()
        assert "momentum" in policy_ctx
        assert "is_stuck" in policy_ctx

    def test_reason_codes_consistency(self):
        """Проверить консистентность reason codes."""
        envelope = ContextEnvelope(
            is_stuck=True,
            frustration_level=4,
            total_objections=3,
            repeated_objection_types=["objection_price"],
        )

        builder = ContextEnvelopeBuilder()
        builder._compute_reason_codes(envelope)

        # Repair mode должен быть активен
        assert envelope.has_reason(ReasonCode.POLICY_REPAIR_MODE)

        # Objection escalate должен быть активен
        assert envelope.has_reason(ReasonCode.OBJECTION_ESCALATE)

        # Guard frustration должен быть активен
        assert envelope.has_reason(ReasonCode.GUARD_FRUSTRATION)

        # Все reason codes должны быть в списке
        assert len(envelope.reason_codes) >= 3
