"""
Тесты для PersonalizationEngine.

Проверяют:
- Определение категории размера компании
- Определение отрасли по данным
- Генерация контекста персонализации
- Получение контраргументов для возражений
- Форматирование промптов с персонализацией
"""

import pytest
import sys
import os

# Добавляем src в путь

from src.generator import PersonalizationEngine

class TestSizeCategory:
    """Тесты определения категории размера компании"""

    def test_micro_size_1(self):
        """1 человек = micro"""
        category = PersonalizationEngine.get_size_category(1)
        assert category == "micro"

    def test_micro_size_5(self):
        """5 человек = micro"""
        category = PersonalizationEngine.get_size_category(5)
        assert category == "micro"

    def test_small_size_6(self):
        """6 человек = small"""
        category = PersonalizationEngine.get_size_category(6)
        assert category == "small"

    def test_small_size_15(self):
        """15 человек = small"""
        category = PersonalizationEngine.get_size_category(15)
        assert category == "small"

    def test_medium_size_16(self):
        """16 человек = medium"""
        category = PersonalizationEngine.get_size_category(16)
        assert category == "medium"

    def test_medium_size_50(self):
        """50 человек = medium"""
        category = PersonalizationEngine.get_size_category(50)
        assert category == "medium"

    def test_large_size_51(self):
        """51 человек = large"""
        category = PersonalizationEngine.get_size_category(51)
        assert category == "large"

    def test_large_size_100(self):
        """100 человек = large"""
        category = PersonalizationEngine.get_size_category(100)
        assert category == "large"

    def test_large_size_1000(self):
        """1000 человек = large"""
        category = PersonalizationEngine.get_size_category(1000)
        assert category == "large"

    def test_zero_returns_small(self):
        """0 человек возвращает small (default)"""
        category = PersonalizationEngine.get_size_category(0)
        assert category == "small"

    def test_negative_returns_small(self):
        """Отрицательное число возвращает small (default)"""
        category = PersonalizationEngine.get_size_category(-5)
        assert category == "small"

class TestIndustryDetection:
    """Тесты определения отрасли"""

    def test_detect_retail_by_business_type(self):
        """Определение retail по business_type"""
        collected_data = {"business_type": "магазин одежды"}
        industry = PersonalizationEngine.detect_industry(collected_data)
        assert industry == "retail"

    def test_detect_retail_by_keyword(self):
        """Определение retail по ключевому слову"""
        collected_data = {"business_type": "розничная торговля"}
        industry = PersonalizationEngine.detect_industry(collected_data)
        assert industry == "retail"

    def test_detect_services_by_business_type(self):
        """Определение services по business_type"""
        collected_data = {"business_type": "салон красоты"}
        industry = PersonalizationEngine.detect_industry(collected_data)
        assert industry == "services"

    def test_detect_horeca_by_business_type(self):
        """Определение horeca по business_type"""
        collected_data = {"business_type": "ресторан"}
        industry = PersonalizationEngine.detect_industry(collected_data)
        assert industry == "horeca"

    def test_detect_b2b_by_business_type(self):
        """Определение b2b по business_type"""
        collected_data = {"business_type": "оптовая компания"}
        industry = PersonalizationEngine.detect_industry(collected_data)
        assert industry == "b2b"

    def test_detect_real_estate_by_business_type(self):
        """Определение real_estate по business_type"""
        collected_data = {"business_type": "агентство недвижимости"}
        industry = PersonalizationEngine.detect_industry(collected_data)
        assert industry == "real_estate"

    def test_detect_it_by_business_type(self):
        """Определение it по business_type"""
        collected_data = {"business_type": "IT разработка"}
        industry = PersonalizationEngine.detect_industry(collected_data)
        assert industry == "it"

    def test_detect_by_pain_point(self):
        """Определение отрасли по pain_point"""
        collected_data = {
            "business_type": "компания",
            "pain_point": "пересортица на складе"
        }
        industry = PersonalizationEngine.detect_industry(collected_data)
        assert industry == "retail"

    def test_no_industry_detected(self):
        """Отрасль не определена"""
        collected_data = {"business_type": "какая-то компания"}
        industry = PersonalizationEngine.detect_industry(collected_data)
        assert industry is None

    def test_empty_data(self):
        """Пустые данные"""
        collected_data = {}
        industry = PersonalizationEngine.detect_industry(collected_data)
        assert industry is None

class TestGetContext:
    """Тесты получения контекста персонализации"""

    def test_context_with_size(self):
        """Контекст с размером компании"""
        collected_data = {"company_size": 10}
        context = PersonalizationEngine.get_context(collected_data)

        assert context["size_category"] == "small"
        assert context["business_context"] is not None
        assert "value_prop" in context["business_context"]

    def test_context_with_industry(self):
        """Контекст с отраслью"""
        collected_data = {
            "company_size": 10,
            "business_type": "ресторан"
        }
        context = PersonalizationEngine.get_context(collected_data)

        assert context["industry"] == "horeca"
        assert context["industry_context"] is not None

    def test_context_with_pain_point(self):
        """Контекст с болью"""
        collected_data = {
            "company_size": 10,
            "pain_point": "теряем клиентов"
        }
        context = PersonalizationEngine.get_context(collected_data)

        assert context["has_pain_point"] is True
        assert "теряем клиентов" in context["pain_reference"]

    def test_context_without_pain_point(self):
        """Контекст без боли"""
        collected_data = {"company_size": 10}
        context = PersonalizationEngine.get_context(collected_data)

        assert context["has_pain_point"] is False
        assert context["pain_reference"] == ""

    def test_context_personalized_value_prop(self):
        """Персонализированное ценностное предложение"""
        collected_data = {
            "company_size": 3,
            "business_type": "магазин"
        }
        context = PersonalizationEngine.get_context(collected_data)

        assert context["personalized_value_prop"]
        # Для micro должно быть про простоту
        assert "простота" in context["business_context"]["pain_focus"].lower() or \
               "время" in context["business_context"]["pain_focus"].lower()

    def test_context_string_company_size(self):
        """Размер компании как строка"""
        collected_data = {"company_size": "15"}
        context = PersonalizationEngine.get_context(collected_data)

        assert context["size_category"] == "small"

    def test_context_invalid_company_size(self):
        """Невалидный размер компании"""
        collected_data = {"company_size": "not a number"}
        context = PersonalizationEngine.get_context(collected_data)

        # Должен вернуть default
        assert context["size_category"] == "small"

    def test_context_empty_data(self):
        """Пустые данные"""
        context = PersonalizationEngine.get_context({})

        assert context["size_category"] == "small"
        assert context["industry"] is None
        assert context["has_pain_point"] is False

class TestBusinessContexts:
    """Тесты бизнес-контекстов по размеру"""

    def test_micro_context(self):
        """Контекст для micro компании"""
        context = PersonalizationEngine.get_context({"company_size": 3})
        bc = context["business_context"]

        assert bc["size_label"] == "небольшая команда"
        assert "простота" in bc["pain_focus"].lower() or "время" in bc["pain_focus"].lower()

    def test_small_context(self):
        """Контекст для small компании"""
        context = PersonalizationEngine.get_context({"company_size": 10})
        bc = context["business_context"]

        assert bc["size_label"] == "растущая команда"
        assert "контроль" in bc["pain_focus"].lower() or "координация" in bc["pain_focus"].lower()

    def test_medium_context(self):
        """Контекст для medium компании"""
        context = PersonalizationEngine.get_context({"company_size": 30})
        bc = context["business_context"]

        assert bc["size_label"] == "средний бизнес"
        assert "автоматизация" in bc["pain_focus"].lower() or "масштабирование" in bc["pain_focus"].lower()

    def test_large_context(self):
        """Контекст для large компании"""
        context = PersonalizationEngine.get_context({"company_size": 100})
        bc = context["business_context"]

        assert bc["size_label"] == "крупная компания"
        assert "интеграция" in bc["pain_focus"].lower() or "кастомизация" in bc["pain_focus"].lower()

class TestObjectionCounter:
    """Тесты контраргументов для возражений"""

    def test_price_objection_micro(self):
        """Контраргумент на цену для micro"""
        counter = PersonalizationEngine.get_objection_counter(
            {"company_size": 3},
            "price"
        )
        assert "время" in counter.lower() or "окуп" in counter.lower()

    def test_price_objection_small(self):
        """Контраргумент на цену для small"""
        counter = PersonalizationEngine.get_objection_counter(
            {"company_size": 10},
            "price"
        )
        assert "стоимость" in counter.lower() or "конкурент" in counter.lower()

    def test_no_time_objection(self):
        """Контраргумент на нет времени"""
        counter = PersonalizationEngine.get_objection_counter(
            {"company_size": 10},
            "no_time"
        )
        # Должен вернуть demo_pitch
        assert "демо" in counter.lower() or "покажу" in counter.lower() or "минут" in counter.lower()

    def test_other_objection(self):
        """Контраргумент на другое возражение"""
        counter = PersonalizationEngine.get_objection_counter(
            {"company_size": 10},
            "other"
        )
        # Должен вернуть value_prop
        assert counter  # Не пустой

class TestFormatPromptWithPersonalization:
    """Тесты форматирования промпта с персонализацией"""

    def test_format_basic_prompt(self):
        """Базовое форматирование"""
        template = "Размер: {size_category}. Боль: {pain_reference}"
        collected_data = {
            "company_size": 10,
            "pain_point": "теряем клиентов"
        }

        result = PersonalizationEngine.format_prompt_with_personalization(
            template, collected_data
        )

        assert "small" in result
        assert "теряем клиентов" in result

    def test_format_with_business_context(self):
        """Форматирование с бизнес-контекстом"""
        template = "Фокус: {bc_pain_focus}"
        collected_data = {"company_size": 10}

        result = PersonalizationEngine.format_prompt_with_personalization(
            template, collected_data
        )

        assert result  # Не пустой

    def test_format_with_industry_context(self):
        """Форматирование с отраслевым контекстом"""
        template = "Примеры: {ic_examples}"
        collected_data = {
            "company_size": 10,
            "business_type": "ресторан"
        }

        result = PersonalizationEngine.format_prompt_with_personalization(
            template, collected_data
        )

        # Должен содержать примеры для horeca
        assert result

    def test_format_with_additional_kwargs(self):
        """Форматирование с дополнительными переменными"""
        template = "Размер: {size_category}. Сообщение: {user_message}"
        collected_data = {"company_size": 10}

        result = PersonalizationEngine.format_prompt_with_personalization(
            template, collected_data,
            user_message="Привет!"
        )

        assert "small" in result
        assert "Привет!" in result

    def test_format_missing_variable(self):
        """Отсутствующая переменная"""
        template = "Тест: {unknown_variable}"
        collected_data = {"company_size": 10}

        # Не должен падать, должен вернуть исходный шаблон
        result = PersonalizationEngine.format_prompt_with_personalization(
            template, collected_data
        )

        assert result == template

class TestAllBusinessContextsComplete:
    """Проверка полноты бизнес-контекстов"""

    def test_all_size_categories_have_context(self):
        """Все категории размера имеют контекст"""
        for category in ["micro", "small", "medium", "large"]:
            context = PersonalizationEngine.BUSINESS_CONTEXTS.get(category)
            assert context is not None, f"No context for {category}"

    def test_all_contexts_have_required_fields(self):
        """Все контексты имеют обязательные поля"""
        required_fields = [
            "size_label",
            "pain_focus",
            "value_prop",
            "objection_counter",
            "demo_pitch"
        ]

        for category, context in PersonalizationEngine.BUSINESS_CONTEXTS.items():
            for field in required_fields:
                assert field in context, f"Missing {field} in {category}"
                assert context[field], f"Empty {field} in {category}"

class TestAllIndustryContextsComplete:
    """Проверка полноты отраслевых контекстов"""

    def test_all_industries_have_context(self):
        """Все отрасли имеют контекст"""
        expected_industries = ["retail", "services", "horeca", "b2b", "real_estate", "it"]
        for industry in expected_industries:
            context = PersonalizationEngine.INDUSTRY_CONTEXTS.get(industry)
            assert context is not None, f"No context for {industry}"

    def test_all_industry_contexts_have_required_fields(self):
        """Все отраслевые контексты имеют обязательные поля"""
        required_fields = ["keywords", "examples", "pain_examples"]

        for industry, context in PersonalizationEngine.INDUSTRY_CONTEXTS.items():
            for field in required_fields:
                assert field in context, f"Missing {field} in {industry}"
                assert context[field], f"Empty {field} in {industry}"
                assert isinstance(context[field], list), f"{field} should be list in {industry}"

class TestEdgeCases:
    """Тесты граничных случаев"""

    def test_none_values(self):
        """None значения в данных"""
        collected_data = {
            "company_size": None,
            "business_type": None,
            "pain_point": None
        }
        context = PersonalizationEngine.get_context(collected_data)

        # Должен обработать без ошибок
        assert context["size_category"] == "small"
        assert context["industry"] is None

    def test_float_company_size(self):
        """Float размер компании"""
        collected_data = {"company_size": 10.5}
        context = PersonalizationEngine.get_context(collected_data)

        # Должен обработать (10.5 попадает в small range)
        assert context["size_category"] == "small"

    def test_very_large_company(self):
        """Очень большая компания"""
        collected_data = {"company_size": 10000}
        context = PersonalizationEngine.get_context(collected_data)

        assert context["size_category"] == "large"

    def test_mixed_case_business_type(self):
        """Смешанный регистр business_type"""
        collected_data = {"business_type": "МАГАЗИН Одежды"}
        industry = PersonalizationEngine.detect_industry(collected_data)

        assert industry == "retail"

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
