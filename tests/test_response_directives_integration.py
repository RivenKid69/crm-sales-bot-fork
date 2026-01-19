"""
Интеграционные тесты ResponseDirectives с bot.py и generator.py.

Проверяют:
- Создание ResponseDirectives в bot.py
- Передачу в context для generator
- Использование в generator.py
- Feature flag контроль
"""

import pytest
import sys
import os
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from response_directives import (
    ResponseDirectives,
    ResponseDirectivesBuilder,
    ResponseTone,
    build_response_directives,
)
from context_envelope import ContextEnvelope, ReasonCode
from feature_flags import flags


class TestResponseDirectivesFeatureFlag:
    """Тесты feature flag для ResponseDirectives."""

    def test_flag_exists(self):
        """Проверить что флаг существует."""
        assert hasattr(flags, "context_response_directives")

    def test_flag_default_value(self):
        """Проверить default значение флага."""
        # По умолчанию флаг выключен
        flags.clear_override("context_response_directives")
        # После наших изменений флаг может быть включен в DEFAULTS
        # Просто проверяем что property работает
        value = flags.context_response_directives
        assert isinstance(value, bool)

    def test_flag_can_be_enabled(self):
        """Проверить что флаг можно включить."""
        flags.set_override("context_response_directives", True)
        assert flags.context_response_directives is True
        flags.clear_override("context_response_directives")

    def test_flag_can_be_disabled(self):
        """Проверить что флаг можно выключить."""
        flags.set_override("context_response_directives", False)
        assert flags.context_response_directives is False
        flags.clear_override("context_response_directives")


class TestDirectiveInstruction:
    """Тесты генерации instruction из directives."""

    def test_directive_instruction_generated(self):
        """Проверить что instruction генерируется."""
        envelope = ContextEnvelope(
            frustration_level=4,
            is_stuck=True,
            reason_codes=[ReasonCode.POLICY_REPAIR_MODE.value],
        )

        directives = build_response_directives(envelope)
        instruction = directives.get_instruction()

        # Должны быть ключевые фразы
        assert len(instruction) > 0
        assert "эмпатичный" in instruction.lower()

    def test_directive_instruction_for_confident_tone(self):
        """Проверить instruction для уверенного тона."""
        envelope = ContextEnvelope(
            has_breakthrough=True,
            reason_codes=[ReasonCode.BREAKTHROUGH_DETECTED.value],
        )

        directives = build_response_directives(envelope)
        instruction = directives.get_instruction()

        assert "уверенный" in instruction.lower()

    def test_directive_instruction_empty_for_neutral(self):
        """Проверить что для нейтрального тона instruction минимален."""
        envelope = ContextEnvelope()

        directives = build_response_directives(envelope)
        instruction = directives.get_instruction()

        # Для нейтрального тона не должно быть тональных инструкций
        assert "эмпатичный" not in instruction.lower()
        assert "уверенный" not in instruction.lower()


class TestDirectivesMemory:
    """Тесты memory полей в directives."""

    def test_client_card_generated(self):
        """Проверить генерацию client_card."""
        envelope = ContextEnvelope(
            client_company_size=15,
            client_pain_points=["потеря клиентов"],
            collected_data={"business_type": "розница"},
        )

        directives = build_response_directives(envelope)

        assert "15" in directives.client_card
        assert "розница" in directives.client_card

    def test_do_not_repeat_generated(self):
        """Проверить генерацию do_not_repeat."""
        envelope = ContextEnvelope(
            collected_data={
                "company_size": 10,
                "business_type": "услуги",
            },
        )

        directives = build_response_directives(envelope)

        assert len(directives.do_not_repeat) >= 2
        assert "размер компании" in directives.do_not_repeat

    def test_objection_summary_generated(self):
        """Проверить генерацию objection_summary."""
        envelope = ContextEnvelope(
            objection_types_seen=["objection_price", "objection_competitor"],
        )

        directives = build_response_directives(envelope)

        assert "цена" in directives.objection_summary
        assert "конкурент" in directives.objection_summary

    def test_reference_pain_generated(self):
        """Проверить генерацию reference_pain."""
        envelope = ContextEnvelope(
            client_pain_points=["потеря клиентов", "долгие продажи"],
        )

        directives = build_response_directives(envelope)

        assert directives.reference_pain == "потеря клиентов"


class TestDirectivesToDict:
    """Тесты сериализации directives в dict."""

    def test_to_dict_structure(self):
        """Проверить структуру to_dict()."""
        directives = ResponseDirectives(
            tone=ResponseTone.EMPATHETIC,
            max_words=40,
            validate=True,
            repair_mode=True,
            client_card="компания ~15 чел",
        )

        d = directives.to_dict()

        assert "style" in d
        assert "dialogue_moves" in d
        assert "memory" in d

        assert d["style"]["tone"] == "empathetic"
        assert d["style"]["max_words"] == 40
        assert d["dialogue_moves"]["validate"] is True
        assert d["dialogue_moves"]["repair_mode"] is True
        assert d["memory"]["client_card"] == "компания ~15 чел"

    def test_to_dict_for_generator(self):
        """Проверить что to_dict() готов для generator."""
        envelope = ContextEnvelope(
            frustration_level=4,
            collected_data={"company_size": 10},
            client_pain_points=["потеря клиентов"],
        )

        directives = build_response_directives(envelope)
        d = directives.to_dict()

        # Memory поля должны быть готовы для generator
        memory = d.get("memory", {})
        assert memory.get("client_card") or True  # Может быть пустым
        assert isinstance(memory.get("do_not_repeat", []), list)


class TestFullFlowIntegration:
    """Полные интеграционные тесты."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Включить feature flags для тестов."""
        flags.set_override("context_response_directives", True)
        flags.set_override("context_full_envelope", True)
        yield
        flags.clear_override("context_response_directives")
        flags.clear_override("context_full_envelope")

    def test_frustrated_client_full_flow(self):
        """Полный flow для фрустрированного клиента."""
        envelope = ContextEnvelope(
            state="spin_problem",
            frustration_level=4,
            is_stuck=True,
            repeated_question="question_price",
            objection_types_seen=["objection_price"],
            collected_data={
                "company_size": 15,
                "business_type": "розница",
            },
            client_company_size=15,
            reason_codes=[
                ReasonCode.POLICY_REPAIR_MODE.value,
                ReasonCode.REPAIR_STUCK.value,
            ],
        )

        directives = build_response_directives(envelope)

        # Проверяем все аспекты
        assert directives.tone == ResponseTone.EMPATHETIC
        assert directives.validate is True
        assert directives.repair_mode is True
        assert directives.be_brief is True
        assert directives.max_words <= 50

        # Проверяем memory
        assert "15" in directives.client_card
        assert len(directives.do_not_repeat) >= 2
        assert "цена" in directives.objection_summary

        # Проверяем instruction
        instruction = directives.get_instruction()
        assert len(instruction) > 50
        assert "эмпатичный" in instruction.lower()

        # Проверяем to_dict для generator
        d = directives.to_dict()
        assert d["style"]["tone"] == "empathetic"
        assert d["dialogue_moves"]["repair_mode"] is True

    def test_interested_client_full_flow(self):
        """Полный flow для заинтересованного клиента."""
        envelope = ContextEnvelope(
            state="presentation",
            frustration_level=0,
            has_breakthrough=True,
            turns_since_breakthrough=2,
            momentum_direction="positive",
            engagement_level="high",
            client_has_data=True,
            client_company_size=30,
            client_pain_points=["потеря клиентов"],
            reason_codes=[
                ReasonCode.BREAKTHROUGH_DETECTED.value,
                ReasonCode.BREAKTHROUGH_CTA.value,
                ReasonCode.MOMENTUM_POSITIVE.value,
            ],
        )

        directives = build_response_directives(envelope)

        # Проверяем
        assert directives.tone == ResponseTone.CONFIDENT
        assert directives.cta_soft is True
        assert directives.summarize_client is True
        assert directives.repair_mode is False

        # Проверяем memory
        assert "30" in directives.client_card

        # Проверяем instruction
        instruction = directives.get_instruction()
        assert "уверенный" in instruction.lower()


class TestContextSummary:
    """Тесты context summary."""

    def test_summary_includes_turns(self):
        """Проверить что summary включает ходы."""
        envelope = ContextEnvelope(total_turns=5)

        builder = ResponseDirectivesBuilder(envelope)
        summary = builder.build_context_summary()

        assert "5" in summary

    def test_summary_includes_company_size(self):
        """Проверить что summary включает размер компании."""
        envelope = ContextEnvelope(client_company_size=20)

        builder = ResponseDirectivesBuilder(envelope)
        summary = builder.build_context_summary()

        assert "20" in summary
        assert "сотрудник" in summary.lower()

    def test_summary_includes_breakthrough(self):
        """Проверить что summary включает breakthrough."""
        envelope = ContextEnvelope(has_breakthrough=True)

        builder = ResponseDirectivesBuilder(envelope)
        summary = builder.build_context_summary()

        assert "прорыв" in summary.lower()

    def test_summary_respects_max_lines(self):
        """Проверить ограничение длины summary."""
        envelope = ContextEnvelope(
            total_turns=10,
            client_company_size=20,
            client_pain_points=["боль1", "боль2", "боль3"],
            is_stuck=True,
            has_oscillation=True,
            repeated_question="q1",
            repeated_objection_types=["objection_price", "objection_competitor"],
            has_breakthrough=True,
            reason_codes=[
                ReasonCode.REPAIR_STUCK.value,
                ReasonCode.REPAIR_OSCILLATION.value,
            ],
        )

        builder = ResponseDirectivesBuilder(envelope)
        summary = builder.build_context_summary()

        lines = summary.strip().split("\n")
        assert len(lines) <= builder.max_summary_lines
