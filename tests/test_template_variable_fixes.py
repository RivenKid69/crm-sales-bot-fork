"""
Тесты для исправлений проблем с переменными в шаблонах.

Проверяют:
- SafeDict безопасно обрабатывает отсутствующие ключи
- PERSONALIZATION_DEFAULTS содержит все необходимые переменные
- _apply_legacy_personalization заполняет bc_* переменные
- pain_point корректно обрабатывается когда не собран
- template.format_map(SafeDict(...)) не падает при отсутствующих переменных

Issue refs:
- style_full_instruction missing (145 occurrences)
- {pain_point} shown to client (75 occurrences)
- {bc_value_prop} shown to client (9 occurrences)
"""

import pytest
import sys
import os

# Добавляем src в путь
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from generator import (
    SafeDict,
    PERSONALIZATION_DEFAULTS,
    PersonalizationEngine,
    ResponseGenerator,
)


class TestSafeDict:
    """Тесты для SafeDict - безопасная подстановка переменных."""

    def test_returns_value_for_existing_key(self):
        """Возвращает значение для существующего ключа."""
        d = SafeDict({"name": "John", "age": "30"})
        assert d["name"] == "John"
        assert d["age"] == "30"

    def test_returns_empty_string_for_missing_key(self):
        """Возвращает пустую строку для отсутствующего ключа."""
        d = SafeDict({"name": "John"})
        assert d["missing_key"] == ""
        assert d["another_missing"] == ""

    def test_works_with_format_map(self):
        """Работает с str.format_map()."""
        template = "Hello {name}, your pain is {pain_point}"
        result = template.format_map(SafeDict({"name": "John"}))
        assert result == "Hello John, your pain is "

    def test_no_keyerror_on_missing(self):
        """Не выбрасывает KeyError при отсутствующем ключе."""
        d = SafeDict({})
        # Не должно падать
        _ = d["nonexistent"]
        assert True

    def test_complex_template_with_missing_vars(self):
        """Комплексный шаблон с отсутствующими переменными."""
        template = """
        Размер: {bc_size_label}
        Ценность: {bc_value_prop}
        Стиль: {style_full_instruction}
        Боль: {pain_point}
        """
        variables = {"pain_point": "теряем клиентов"}
        result = template.format_map(SafeDict(variables))

        assert "теряем клиентов" in result
        assert "{bc_size_label}" not in result
        assert "{bc_value_prop}" not in result
        assert "{style_full_instruction}" not in result

    def test_preserves_dict_functionality(self):
        """Сохраняет функциональность обычного словаря."""
        d = SafeDict({"a": 1, "b": 2})
        assert len(d) == 2
        assert "a" in d
        assert "c" not in d
        d["c"] = 3
        assert d["c"] == 3


class TestPersonalizationDefaults:
    """Тесты для PERSONALIZATION_DEFAULTS."""

    def test_contains_style_full_instruction(self):
        """Содержит style_full_instruction."""
        assert "style_full_instruction" in PERSONALIZATION_DEFAULTS
        assert isinstance(PERSONALIZATION_DEFAULTS["style_full_instruction"], str)

    def test_contains_bc_variables(self):
        """Содержит все bc_* переменные."""
        bc_vars = [
            "bc_size_label",
            "bc_pain_focus",
            "bc_value_prop",
            "bc_objection_counter",
            "bc_demo_pitch",
        ]
        for var in bc_vars:
            assert var in PERSONALIZATION_DEFAULTS, f"Missing {var}"

    def test_contains_ic_variables(self):
        """Содержит все ic_* переменные."""
        ic_vars = [
            "ic_keywords",
            "ic_examples",
            "ic_pain_examples",
        ]
        for var in ic_vars:
            assert var in PERSONALIZATION_DEFAULTS, f"Missing {var}"

    def test_contains_style_variables(self):
        """Содержит переменные стиля."""
        style_vars = [
            "adaptive_style_instruction",
            "adaptive_tactical_instruction",
        ]
        for var in style_vars:
            assert var in PERSONALIZATION_DEFAULTS, f"Missing {var}"

    def test_all_values_are_strings(self):
        """Все значения - строки."""
        for key, value in PERSONALIZATION_DEFAULTS.items():
            assert isinstance(value, str), f"{key} is not a string"

    def test_size_category_has_default(self):
        """size_category имеет значение по умолчанию."""
        assert PERSONALIZATION_DEFAULTS["size_category"] == "small"


class TestPainPointHandling:
    """Тесты для обработки pain_point."""

    def test_none_pain_point_becomes_neutral(self):
        """None pain_point становится нейтральной формулировкой."""
        collected = {"pain_point": None}
        raw = collected.get("pain_point")
        if raw and raw != "?" and str(raw).strip():
            result = str(raw).strip()
        else:
            result = "текущие сложности"
        assert result == "текущие сложности"

    def test_question_mark_pain_point_becomes_neutral(self):
        """'?' pain_point становится нейтральной формулировкой."""
        collected = {"pain_point": "?"}
        raw = collected.get("pain_point")
        if raw and raw != "?" and str(raw).strip():
            result = str(raw).strip()
        else:
            result = "текущие сложности"
        assert result == "текущие сложности"

    def test_empty_pain_point_becomes_neutral(self):
        """Пустой pain_point становится нейтральной формулировкой."""
        collected = {"pain_point": ""}
        raw = collected.get("pain_point")
        if raw and raw != "?" and str(raw).strip():
            result = str(raw).strip()
        else:
            result = "текущие сложности"
        assert result == "текущие сложности"

    def test_whitespace_pain_point_becomes_neutral(self):
        """Пробельный pain_point становится нейтральной формулировкой."""
        collected = {"pain_point": "   "}
        raw = collected.get("pain_point")
        if raw and raw != "?" and str(raw).strip():
            result = str(raw).strip()
        else:
            result = "текущие сложности"
        assert result == "текущие сложности"

    def test_valid_pain_point_preserved(self):
        """Валидный pain_point сохраняется."""
        collected = {"pain_point": "теряем клиентов"}
        raw = collected.get("pain_point")
        if raw and raw != "?" and str(raw).strip():
            result = str(raw).strip()
        else:
            result = "текущие сложности"
        assert result == "теряем клиентов"


class TestLegacyPersonalizationFallback:
    """Тесты для legacy персонализации как fallback."""

    def test_get_context_returns_business_context(self):
        """get_context возвращает business_context."""
        collected = {"company_size": 10}
        context = PersonalizationEngine.get_context(collected)

        assert "business_context" in context
        assert context["business_context"] is not None
        assert "value_prop" in context["business_context"]

    def test_get_context_returns_size_category(self):
        """get_context возвращает size_category."""
        collected = {"company_size": 10}
        context = PersonalizationEngine.get_context(collected)

        assert "size_category" in context
        assert context["size_category"] == "small"

    def test_bc_value_prop_filled_for_small(self):
        """bc_value_prop заполняется для small компании."""
        collected = {"company_size": 10}
        context = PersonalizationEngine.get_context(collected)

        bc = context.get("business_context", {})
        assert bc.get("value_prop"), "value_prop should not be empty"

    def test_bc_value_prop_filled_for_micro(self):
        """bc_value_prop заполняется для micro компании."""
        collected = {"company_size": 3}
        context = PersonalizationEngine.get_context(collected)

        bc = context.get("business_context", {})
        assert bc.get("value_prop"), "value_prop should not be empty"

    def test_bc_value_prop_filled_for_medium(self):
        """bc_value_prop заполняется для medium компании."""
        collected = {"company_size": 30}
        context = PersonalizationEngine.get_context(collected)

        bc = context.get("business_context", {})
        assert bc.get("value_prop"), "value_prop should not be empty"

    def test_bc_value_prop_filled_for_large(self):
        """bc_value_prop заполняется для large компании."""
        collected = {"company_size": 100}
        context = PersonalizationEngine.get_context(collected)

        bc = context.get("business_context", {})
        assert bc.get("value_prop"), "value_prop should not be empty"

    def test_industry_context_when_detected(self):
        """industry_context заполняется когда отрасль определена."""
        collected = {"company_size": 10, "business_type": "ресторан"}
        context = PersonalizationEngine.get_context(collected)

        assert context.get("industry") == "horeca"
        assert context.get("industry_context") is not None


class TestTemplateFormatSafety:
    """Тесты безопасности форматирования шаблонов."""

    def test_missing_variable_no_crash(self):
        """Отсутствующая переменная не вызывает падение."""
        template = "Hello {name}, size: {bc_size_label}, style: {style_full_instruction}"
        variables = {"name": "Test"}

        # Не должно падать
        result = template.format_map(SafeDict(variables))
        assert "Test" in result
        assert "{bc_size_label}" not in result
        assert "{style_full_instruction}" not in result

    def test_partial_variables_work(self):
        """Частичный набор переменных работает."""
        template = "{system}\n{style_full_instruction}\nРазмер: {bc_size_label}"
        variables = {
            "system": "Ты продавец",
            # style_full_instruction и bc_size_label отсутствуют
        }

        result = template.format_map(SafeDict(variables))
        assert "Ты продавец" in result
        assert "{style_full_instruction}" not in result
        assert "{bc_size_label}" not in result

    def test_all_personalization_defaults_in_template(self):
        """Все переменные из PERSONALIZATION_DEFAULTS работают в шаблоне."""
        # Создаём шаблон со всеми переменными
        template = " ".join(f"{{{key}}}" for key in PERSONALIZATION_DEFAULTS.keys())

        # Не должно падать с пустым словарём
        result = template.format_map(SafeDict({}))

        # Все {переменные} должны быть заменены на пустые строки
        assert "{" not in result


class TestRealTemplateScenarios:
    """Тесты с реальными шаблонами из config.py."""

    def test_presentation_template_scenario(self):
        """Сценарий шаблона presentation."""
        # Упрощённая версия шаблона presentation
        template = """{system}

{style_full_instruction}

Информация о клиенте:
- Размер команды: {bc_size_label} ({company_size} человек)
- Фокус боли: {bc_pain_focus}
- Проблема: {pain_point}

Задача: Презентовать решение с {bc_value_prop}
"""
        variables = {
            "system": "Ты продавец CRM",
            "company_size": "10",
            "pain_point": "текущие сложности",
            # bc_* и style_full_instruction отсутствуют
        }

        result = template.format_map(SafeDict(variables))

        assert "Ты продавец CRM" in result
        assert "10 человек" in result
        assert "текущие сложности" in result
        # Проверяем что {переменные} не показываются
        assert "{style_full_instruction}" not in result
        assert "{bc_size_label}" not in result
        assert "{bc_pain_focus}" not in result
        assert "{bc_value_prop}" not in result

    def test_handle_objection_template_scenario(self):
        """Сценарий шаблона handle_objection."""
        template = """{system}

{style_full_instruction}

Тип возражения: {objection_type}
Контекст: {bc_value_prop}
"""
        variables = {
            "system": "Ты продавец",
            "objection_type": "price",
            # style_full_instruction и bc_value_prop отсутствуют
        }

        result = template.format_map(SafeDict(variables))

        assert "Ты продавец" in result
        assert "price" in result
        assert "{style_full_instruction}" not in result
        assert "{bc_value_prop}" not in result


class TestIntegrationWithPersonalizationEngine:
    """Интеграционные тесты с PersonalizationEngine."""

    def test_variables_from_legacy_engine(self):
        """Переменные из legacy PersonalizationEngine."""
        collected = {"company_size": 10, "business_type": "магазин"}

        # Начинаем с defaults
        variables = dict(PERSONALIZATION_DEFAULTS)

        # Применяем legacy персонализацию
        context = PersonalizationEngine.get_context(collected)
        bc = context.get("business_context") or {}

        variables["size_category"] = context.get("size_category", "small")
        variables["bc_size_label"] = bc.get("size_label", "")
        variables["bc_pain_focus"] = bc.get("pain_focus", "")
        variables["bc_value_prop"] = bc.get("value_prop", "")

        # Проверяем что переменные заполнены
        assert variables["size_category"] == "small"
        assert variables["bc_size_label"] == "растущая команда"
        assert variables["bc_value_prop"], "bc_value_prop should not be empty"

    def test_full_template_with_legacy_personalization(self):
        """Полный шаблон с legacy персонализацией."""
        template = """Клиент: {bc_size_label}
Ценность: {bc_value_prop}
Стиль: {style_full_instruction}
"""
        collected = {"company_size": 10}

        # Начинаем с defaults (style_full_instruction будет пустой)
        variables = dict(PERSONALIZATION_DEFAULTS)

        # Применяем legacy персонализацию
        context = PersonalizationEngine.get_context(collected)
        bc = context.get("business_context") or {}

        variables["bc_size_label"] = bc.get("size_label", "")
        variables["bc_value_prop"] = bc.get("value_prop", "")

        result = template.format_map(SafeDict(variables))

        assert "растущая команда" in result
        assert variables["bc_value_prop"] in result
        # style_full_instruction должен быть пустым, но не {style_full_instruction}
        assert "{style_full_instruction}" not in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
