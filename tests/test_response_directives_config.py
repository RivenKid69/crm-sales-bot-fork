"""
Тесты загрузки параметров ResponseDirectives из YAML конфига.

Проверяют:
- Загрузку секции response_directives из constants.yaml
- Использование параметров из конфига в ResponseDirectivesBuilder
- Fallback на default значения при отсутствии конфига
"""

import pytest
import sys
import os

from src.response_directives import (
    ResponseDirectives,
    ResponseDirectivesBuilder,
    ResponseTone,
    build_response_directives,
)
from src.context_envelope import ContextEnvelope, ReasonCode
from src.config_loader import get_config

class TestResponseDirectivesConfigLoading:
    """Тесты загрузки конфигурации."""

    def test_config_loaded(self):
        """Проверить что конфиг response_directives загружается."""
        config = get_config()
        rd_config = config.response_directives

        assert rd_config is not None
        assert isinstance(rd_config, dict)

    def test_config_has_required_sections(self):
        """Проверить наличие всех секций в конфиге."""
        config = get_config()
        rd_config = config.response_directives

        assert "tone_thresholds" in rd_config
        assert "max_words" in rd_config
        assert "max_summary_lines" in rd_config
        assert "objection_translations" in rd_config
        assert "collected_field_names" in rd_config
        assert "tone_instructions" in rd_config

    def test_tone_thresholds_values(self):
        """Проверить значения порогов тона."""
        config = get_config()
        thresholds = config.response_directives.get("tone_thresholds", {})

        assert "empathetic_frustration" in thresholds
        assert "validate_frustration" in thresholds
        assert isinstance(thresholds["empathetic_frustration"], int)
        assert isinstance(thresholds["validate_frustration"], int)

    def test_max_words_values(self):
        """Проверить значения max_words."""
        config = get_config()
        max_words = config.response_directives.get("max_words", {})

        assert "high_frustration" in max_words
        assert "low_engagement" in max_words
        assert "repair_mode" in max_words
        assert "default" in max_words

class TestBuilderUsesConfig:
    """Тесты использования конфига в Builder."""

    def test_builder_loads_config(self):
        """Проверить что Builder загружает конфиг."""
        envelope = ContextEnvelope()
        builder = ResponseDirectivesBuilder(envelope)

        # Builder должен иметь конфиг
        assert builder._config is not None
        assert isinstance(builder._config, dict)

    def test_tone_thresholds_from_config(self):
        """Проверить использование порогов тона из конфига."""
        config = get_config()
        threshold = config.response_directives.get("tone_thresholds", {}).get(
            "empathetic_frustration", 3
        )

        # Тест с frustration ниже порога
        envelope_below = ContextEnvelope(frustration_level=threshold - 1)
        directives_below = ResponseDirectivesBuilder(envelope_below).build()
        assert directives_below.tone != ResponseTone.EMPATHETIC

        # Тест с frustration на пороге
        envelope_at = ContextEnvelope(frustration_level=threshold)
        directives_at = ResponseDirectivesBuilder(envelope_at).build()
        assert directives_at.tone == ResponseTone.EMPATHETIC

    def test_max_words_from_config(self):
        """Проверить использование max_words из конфига."""
        config = get_config()
        max_words_config = config.response_directives.get("max_words", {})

        # Высокая фрустрация
        envelope = ContextEnvelope(frustration_level=5)
        directives = ResponseDirectivesBuilder(envelope).build()

        expected = max_words_config.get("high_frustration", 40)
        assert directives.max_words == expected

    def test_max_summary_lines_from_config(self):
        """Проверить max_summary_lines из конфига."""
        config = get_config()
        expected_lines = config.response_directives.get("max_summary_lines", 6)

        # Создаём envelope с множеством данных
        envelope = ContextEnvelope(
            total_turns=10,
            client_company_size=20,
            client_pain_points=["боль1", "боль2"],
            is_stuck=True,
            has_oscillation=True,
            repeated_question="q1",
            repeated_objection_types=["objection_price"],
            has_breakthrough=True,
            reason_codes=[ReasonCode.REPAIR_STUCK.value],
        )

        builder = ResponseDirectivesBuilder(envelope)
        summary = builder.build_context_summary()

        lines = summary.strip().split("\n")
        assert len(lines) <= expected_lines

    def test_objection_translations_from_config(self):
        """Проверить перевод возражений из конфига."""
        config = get_config()
        translations = config.response_directives.get("objection_translations", {})

        envelope = ContextEnvelope(
            objection_types_seen=["objection_price"],
        )

        directives = ResponseDirectivesBuilder(envelope).build()

        expected_translation = translations.get("objection_price", "цена")
        assert expected_translation in directives.objection_summary

    def test_collected_field_names_from_config(self):
        """Проверить названия полей из конфига."""
        config = get_config()
        field_names = config.response_directives.get("collected_field_names", {})

        envelope = ContextEnvelope(
            collected_data={"company_size": 10, "business_type": "услуги"},
        )

        directives = ResponseDirectivesBuilder(envelope).build()

        expected_size_name = field_names.get("company_size", "размер компании")
        assert expected_size_name in directives.do_not_repeat

class TestBuilderConfigFallback:
    """Тесты fallback значений при отсутствии конфига."""

    def test_fallback_when_empty_config(self):
        """Проверить fallback при пустом конфиге."""
        envelope = ContextEnvelope(frustration_level=4)

        # Передаём пустой конфиг
        builder = ResponseDirectivesBuilder(envelope, config={})
        directives = builder.build()

        # Должны использоваться default значения
        assert directives.tone == ResponseTone.EMPATHETIC
        assert directives.max_words == 40  # default for high frustration

    def test_fallback_max_summary_lines(self):
        """Проверить fallback для max_summary_lines."""
        envelope = ContextEnvelope(total_turns=5)

        builder = ResponseDirectivesBuilder(envelope, config={})

        # Должен использоваться default
        assert builder.max_summary_lines == 6  # _DEFAULT_MAX_SUMMARY_LINES

    def test_fallback_tone_thresholds(self):
        """Проверить fallback для tone_thresholds."""
        envelope = ContextEnvelope()

        builder = ResponseDirectivesBuilder(envelope, config={})

        # Должны использоваться default thresholds
        assert builder.tone_thresholds == {
            "empathetic_frustration": 3,
            "validate_frustration": 2,
        }

    def test_fallback_objection_translations(self):
        """Проверить fallback для objection_translations."""
        envelope = ContextEnvelope(
            objection_types_seen=["objection_price"],
        )

        builder = ResponseDirectivesBuilder(envelope, config={})
        directives = builder.build()

        # Должен использоваться default перевод
        assert "цена" in directives.objection_summary

class TestBuilderConfigOverride:
    """Тесты переопределения параметров через конфиг."""

    def test_custom_config_overrides_defaults(self):
        """Проверить что custom конфиг переопределяет defaults."""
        custom_config = {
            "tone_thresholds": {
                "empathetic_frustration": 5,  # Повышенный порог
                "validate_frustration": 4,
            },
            "max_words": {
                "high_frustration": 30,  # Меньше слов
                "default": 50,
            },
        }

        # С frustration_level=4 (ниже custom порога 5)
        envelope = ContextEnvelope(frustration_level=4)
        builder = ResponseDirectivesBuilder(envelope, config=custom_config)
        directives = builder.build()

        # Не должен быть EMPATHETIC (порог 5)
        assert directives.tone != ResponseTone.EMPATHETIC

        # С frustration_level=5 (на custom пороге)
        envelope_high = ContextEnvelope(frustration_level=5)
        builder_high = ResponseDirectivesBuilder(envelope_high, config=custom_config)
        directives_high = builder_high.build()

        # Должен быть EMPATHETIC
        assert directives_high.tone == ResponseTone.EMPATHETIC
        assert directives_high.max_words == 30  # custom значение
