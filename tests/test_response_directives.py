"""
Тесты для ResponseDirectives и ResponseDirectivesBuilder.

Phase 2 из PLAN_CONTEXT_POLICY.md:
- ResponseDirectives: директивы для "человечных" ответов
- ResponseDirectivesBuilder: генерация директив из контекста
- build_context_summary: краткое резюме контекста
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from response_directives import (
    ResponseDirectives,
    ResponseDirectivesBuilder,
    ResponseTone,
    DialogueMove,
    build_response_directives,
    build_context_summary,
)
from context_envelope import ContextEnvelope, ReasonCode


class TestResponseTone:
    """Тесты для ResponseTone enum."""

    def test_tone_values(self):
        """Проверить значения тонов."""
        assert ResponseTone.EMPATHETIC.value == "empathetic"
        assert ResponseTone.NEUTRAL.value == "neutral"
        assert ResponseTone.CONFIDENT.value == "confident"
        assert ResponseTone.SUPPORTIVE.value == "supportive"


class TestDialogueMove:
    """Тесты для DialogueMove enum."""

    def test_dialogue_move_values(self):
        """Проверить значения диалоговых действий."""
        assert DialogueMove.VALIDATE.value == "validate"
        assert DialogueMove.SUMMARIZE_CLIENT.value == "summarize"
        assert DialogueMove.ASK_CLARIFYING.value == "clarify"
        assert DialogueMove.OFFER_CHOICES.value == "choices"
        assert DialogueMove.CTA_SOFT.value == "cta_soft"
        assert DialogueMove.REPAIR.value == "repair"


class TestResponseDirectives:
    """Тесты для ResponseDirectives dataclass."""

    def test_default_values(self):
        """Проверить default значения."""
        directives = ResponseDirectives()

        # Стиль
        assert directives.tone == ResponseTone.NEUTRAL
        assert directives.max_words == 60
        assert directives.one_question is True
        assert directives.use_bullets is False
        assert directives.be_brief is False

        # Диалоговые действия
        assert directives.validate is False
        assert directives.summarize_client is False
        assert directives.ask_clarifying is False
        assert directives.offer_choices is False
        assert directives.cta_soft is False
        assert directives.repair_mode is False

        # Память
        assert directives.client_card == ""
        assert directives.objection_summary == ""
        assert directives.do_not_repeat == []
        assert directives.reference_pain == ""

        # Meta
        assert directives.reason_codes == []
        assert directives.instruction == ""

    def test_to_dict(self):
        """Проверить сериализацию в словарь."""
        directives = ResponseDirectives(
            tone=ResponseTone.EMPATHETIC,
            max_words=40,
            validate=True,
            client_card="компания ~10 чел",
        )

        d = directives.to_dict()

        assert d["style"]["tone"] == "empathetic"
        assert d["style"]["max_words"] == 40
        assert d["dialogue_moves"]["validate"] is True
        assert d["memory"]["client_card"] == "компания ~10 чел"

    def test_get_instruction_empty(self):
        """Проверить пустую инструкцию для default директив."""
        directives = ResponseDirectives()
        instruction = directives.get_instruction()

        # Для нейтрального тона и default значений инструкция минимальна
        assert "Максимум 1 вопрос" in instruction

    def test_get_instruction_empathetic(self):
        """Проверить инструкцию для эмпатичного тона."""
        directives = ResponseDirectives(
            tone=ResponseTone.EMPATHETIC,
            validate=True,
        )

        instruction = directives.get_instruction()

        assert "эмпатичный" in instruction.lower()
        assert "признания ситуации" in instruction.lower()

    def test_get_instruction_repair_mode(self):
        """Проверить инструкцию для repair mode."""
        directives = ResponseDirectives(
            repair_mode=True,
            ask_clarifying=True,
            offer_choices=True,
        )

        instruction = directives.get_instruction()

        assert "восстановления" in instruction.lower()
        assert "уточняющий вопрос" in instruction.lower()
        # "Предложи 2-3 варианта ответа" содержит "вариант"
        assert "вариант" in instruction.lower()

    def test_get_instruction_do_not_repeat(self):
        """Проверить инструкцию с do_not_repeat."""
        directives = ResponseDirectives(
            do_not_repeat=["размер компании", "тип бизнеса"],
        )

        instruction = directives.get_instruction()

        assert "размер компании" in instruction
        assert "тип бизнеса" in instruction
        assert "Не спрашивай повторно" in instruction

    def test_get_instruction_brief(self):
        """Проверить инструкцию для краткого ответа."""
        directives = ResponseDirectives(
            be_brief=True,
            max_words=30,
        )

        instruction = directives.get_instruction()

        # "Будь краток" содержит "краток"
        assert "краток" in instruction.lower()
        assert "30 слов" in instruction


class TestResponseDirectivesBuilder:
    """Тесты для ResponseDirectivesBuilder."""

    def test_build_neutral(self):
        """Проверить сборку для нейтрального контекста."""
        envelope = ContextEnvelope()

        builder = ResponseDirectivesBuilder(envelope)
        directives = builder.build()

        assert directives.tone == ResponseTone.NEUTRAL
        assert directives.repair_mode is False
        assert directives.validate is False

    def test_determine_tone_empathetic_frustration(self):
        """Проверить определение эмпатичного тона при фрустрации."""
        envelope = ContextEnvelope(frustration_level=4)

        builder = ResponseDirectivesBuilder(envelope)
        directives = builder.build()

        assert directives.tone == ResponseTone.EMPATHETIC
        assert directives.validate is True

    def test_determine_tone_empathetic_objection(self):
        """Проверить определение эмпатичного тона при возражении."""
        envelope = ContextEnvelope(
            first_objection_type="objection_price",
            reason_codes=["objection.first"],
        )

        builder = ResponseDirectivesBuilder(envelope)
        directives = builder.build()

        assert directives.tone == ResponseTone.EMPATHETIC
        assert directives.validate is True

    def test_determine_tone_supportive_repair(self):
        """Проверить определение поддерживающего тона при repair."""
        envelope = ContextEnvelope(
            is_stuck=True,
            reason_codes=[ReasonCode.POLICY_REPAIR_MODE.value],
        )

        builder = ResponseDirectivesBuilder(envelope)
        directives = builder.build()

        assert directives.tone == ResponseTone.SUPPORTIVE
        assert directives.repair_mode is True

    def test_determine_tone_confident_breakthrough(self):
        """Проверить определение уверенного тона при breakthrough."""
        envelope = ContextEnvelope(
            has_breakthrough=True,
            reason_codes=[ReasonCode.BREAKTHROUGH_DETECTED.value],
        )

        builder = ResponseDirectivesBuilder(envelope)
        directives = builder.build()

        assert directives.tone == ResponseTone.CONFIDENT

    def test_apply_style_frustration(self):
        """Проверить применение стиля при фрустрации."""
        envelope = ContextEnvelope(frustration_level=4)

        builder = ResponseDirectivesBuilder(envelope)
        directives = builder.build()

        assert directives.max_words == 40
        assert directives.be_brief is True

    def test_apply_style_low_engagement(self):
        """Проверить применение стиля при низком engagement."""
        envelope = ContextEnvelope(engagement_level="low")

        builder = ResponseDirectivesBuilder(envelope)
        directives = builder.build()

        assert directives.max_words == 50
        assert directives.be_brief is True

    def test_apply_repair_stuck(self):
        """Проверить применение repair при stuck."""
        envelope = ContextEnvelope(
            is_stuck=True,
            reason_codes=[ReasonCode.POLICY_REPAIR_MODE.value],
        )

        builder = ResponseDirectivesBuilder(envelope)
        directives = builder.build()

        assert directives.repair_mode is True
        assert directives.offer_choices is True
        assert directives.ask_clarifying is True

    def test_apply_repair_repeated_question(self):
        """Проверить применение repair при повторном вопросе."""
        envelope = ContextEnvelope(
            repeated_question="question_price",
            reason_codes=[ReasonCode.POLICY_REPAIR_MODE.value],
        )

        builder = ResponseDirectivesBuilder(envelope)
        directives = builder.build()

        assert directives.repair_mode is True
        assert directives.ask_clarifying is True
        assert directives.use_bullets is True

    def test_apply_cta_soft_breakthrough(self):
        """Проверить добавление soft CTA при breakthrough."""
        envelope = ContextEnvelope(
            has_breakthrough=True,
            turns_since_breakthrough=2,
            reason_codes=[ReasonCode.BREAKTHROUGH_CTA.value],
        )

        builder = ResponseDirectivesBuilder(envelope)
        directives = builder.build()

        assert directives.cta_soft is True

    def test_fill_memory_client_card(self):
        """Проверить заполнение client card."""
        envelope = ContextEnvelope(
            client_company_size=15,
            client_pain_points=["потеря клиентов"],
            collected_data={"business_type": "розница"},
        )

        builder = ResponseDirectivesBuilder(envelope)
        directives = builder.build()

        assert "15" in directives.client_card
        assert "потеря клиентов" in directives.client_card
        assert "розница" in directives.client_card

    def test_fill_memory_objection_summary(self):
        """Проверить заполнение objection summary."""
        envelope = ContextEnvelope(
            objection_types_seen=["objection_price", "objection_competitor"],
        )

        builder = ResponseDirectivesBuilder(envelope)
        directives = builder.build()

        assert "цена" in directives.objection_summary
        assert "конкурент" in directives.objection_summary

    def test_fill_memory_do_not_repeat(self):
        """Проверить заполнение do_not_repeat."""
        envelope = ContextEnvelope(
            collected_data={
                "company_size": 10,
                "business_type": "услуги",
            },
        )

        builder = ResponseDirectivesBuilder(envelope)
        directives = builder.build()

        assert "размер компании" in directives.do_not_repeat
        assert "тип бизнеса" in directives.do_not_repeat

    def test_fill_memory_reference_pain(self):
        """Проверить заполнение reference_pain."""
        envelope = ContextEnvelope(
            client_pain_points=["потеря клиентов", "долгие продажи"],
        )

        builder = ResponseDirectivesBuilder(envelope)
        directives = builder.build()

        assert directives.reference_pain == "потеря клиентов"


class TestBuildContextSummary:
    """Тесты для build_context_summary."""

    def test_empty_context(self):
        """Проверить summary для пустого контекста."""
        envelope = ContextEnvelope()

        builder = ResponseDirectivesBuilder(envelope)
        summary = builder.build_context_summary()

        # Для пустого контекста summary может быть пустым
        assert isinstance(summary, str)

    def test_summary_with_turns(self):
        """Проверить summary с количеством ходов."""
        envelope = ContextEnvelope(total_turns=5)

        builder = ResponseDirectivesBuilder(envelope)
        summary = builder.build_context_summary()

        assert "5" in summary

    def test_summary_with_company_size(self):
        """Проверить summary с размером компании."""
        envelope = ContextEnvelope(client_company_size=20)

        builder = ResponseDirectivesBuilder(envelope)
        summary = builder.build_context_summary()

        assert "20" in summary
        assert "сотрудник" in summary.lower()

    def test_summary_with_pain_points(self):
        """Проверить summary с болями."""
        envelope = ContextEnvelope(
            client_pain_points=["потеря клиентов"],
        )

        builder = ResponseDirectivesBuilder(envelope)
        summary = builder.build_context_summary()

        assert "потеря клиентов" in summary

    def test_summary_with_repair_signals(self):
        """Проверить summary с repair сигналами."""
        envelope = ContextEnvelope(
            is_stuck=True,
            reason_codes=[ReasonCode.REPAIR_STUCK.value],
        )

        builder = ResponseDirectivesBuilder(envelope)
        summary = builder.build_context_summary()

        assert "застрял" in summary.lower()

    def test_summary_with_objections(self):
        """Проверить summary с возражениями."""
        envelope = ContextEnvelope(
            repeated_objection_types=["objection_price"],
        )

        builder = ResponseDirectivesBuilder(envelope)
        summary = builder.build_context_summary()

        assert "возражен" in summary.lower()

    def test_summary_with_breakthrough(self):
        """Проверить summary с breakthrough."""
        envelope = ContextEnvelope(has_breakthrough=True)

        builder = ResponseDirectivesBuilder(envelope)
        summary = builder.build_context_summary()

        assert "прорыв" in summary.lower()

    def test_summary_max_lines(self):
        """Проверить ограничение длины summary."""
        envelope = ContextEnvelope(
            total_turns=10,
            client_company_size=20,
            client_pain_points=["боль1", "боль2", "боль3"],
            is_stuck=True,
            has_oscillation=True,
            repeated_question="q1",
            repeated_objection_types=["obj1", "obj2"],
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


class TestBuildFunctions:
    """Тесты для функций build_response_directives и build_context_summary."""

    def test_build_response_directives(self):
        """Проверить функцию build_response_directives."""
        envelope = ContextEnvelope(
            frustration_level=3,
            is_stuck=True,
        )

        directives = build_response_directives(envelope)

        assert isinstance(directives, ResponseDirectives)
        assert directives.tone == ResponseTone.EMPATHETIC
        assert directives.validate is True

    def test_build_context_summary_function(self):
        """Проверить функцию build_context_summary."""
        envelope = ContextEnvelope(
            total_turns=5,
            client_company_size=10,
        )

        summary = build_context_summary(envelope)

        assert isinstance(summary, str)
        assert "5" in summary or "10" in summary


class TestResponseDirectivesIntegration:
    """Интеграционные тесты для ResponseDirectives."""

    def test_full_flow_frustrated_client(self):
        """Проверить полный flow для фрустрированного клиента."""
        envelope = ContextEnvelope(
            state="spin_problem",
            frustration_level=4,
            is_stuck=True,
            repeated_question="question_price",
            total_objections=2,
            objection_types_seen=["objection_price"],
            client_company_size=15,
            collected_data={
                "company_size": 15,
                "business_type": "розница",
            },
            reason_codes=[
                ReasonCode.POLICY_REPAIR_MODE.value,
                ReasonCode.REPAIR_STUCK.value,
                ReasonCode.REPAIR_REPEATED_QUESTION.value,
            ],
        )

        directives = build_response_directives(envelope)

        # Тон должен быть эмпатичным
        assert directives.tone == ResponseTone.EMPATHETIC

        # Должен быть repair mode
        assert directives.repair_mode is True
        assert directives.ask_clarifying is True

        # Должен быть validate
        assert directives.validate is True

        # Должен быть краткий ответ
        assert directives.be_brief is True
        assert directives.max_words <= 50

        # Client card должен быть заполнен
        assert "15" in directives.client_card
        assert "розница" in directives.client_card

        # do_not_repeat должен быть заполнен
        assert len(directives.do_not_repeat) > 0

        # Instruction должна содержать все директивы
        instruction = directives.get_instruction()
        assert len(instruction) > 0

    def test_full_flow_interested_client(self):
        """Проверить полный flow для заинтересованного клиента."""
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

        # Тон должен быть уверенным
        assert directives.tone == ResponseTone.CONFIDENT

        # Должен быть soft CTA
        assert directives.cta_soft is True

        # Должен быть summarize (есть данные)
        assert directives.summarize_client is True

        # НЕ должен быть repair mode
        assert directives.repair_mode is False

        # Client card должен быть заполнен
        assert "30" in directives.client_card
