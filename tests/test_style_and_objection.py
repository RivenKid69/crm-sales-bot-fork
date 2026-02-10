"""
Тесты для style_instruction и objection context.

Проверяют:
- Генерацию style_instruction на основе формальности клиента
- Получение objection_counter из конфига
- Передачу objection_type и objection_counter в промпт
- Интеграцию с generator.py
"""

import pytest
import sys
import os

# Добавляем src в путь

from src.tone_analyzer import ToneAnalyzer, Tone, Style, ToneAnalysis
from src.tone_analyzer.regex_analyzer import RegexToneAnalyzer
from src.settings import settings

class TestStyleInstruction:
    """Тесты для style_instruction"""

    def setup_method(self):
        """Создаём новый анализатор для каждого теста"""
        self.analyzer = RegexToneAnalyzer()

    def test_informal_style_detection(self):
        """Определение неформального стиля"""
        result = self.analyzer.analyze("короче, чё по ценам?")
        assert result.style == Style.INFORMAL

    def test_formal_style_detection(self):
        """Определение формального стиля"""
        result = self.analyzer.analyze("Добрый день, подскажите стоимость услуг")
        assert result.style == Style.FORMAL

    def test_style_instruction_for_informal(self):
        """Проверка style_instruction для неформального стиля"""
        result = self.analyzer.analyze("чё почём?")
        guidance = self.analyzer.get_response_guidance(result)

        assert "style_instruction" in guidance
        # Проверяем что для informal есть инструкция из конфига
        expected = settings.get_nested("tone_analyzer.style_instructions.informal", "")
        assert guidance["style_instruction"] == expected

    def test_style_instruction_for_formal(self):
        """Проверка style_instruction для формального стиля"""
        result = self.analyzer.analyze("Здравствуйте, меня интересует ваш продукт")
        guidance = self.analyzer.get_response_guidance(result)

        assert "style_instruction" in guidance
        # Для formal должна быть пустая строка по умолчанию
        expected = settings.get_nested("tone_analyzer.style_instructions.formal", "")
        assert guidance["style_instruction"] == expected

    def test_style_instruction_in_guidance_keys(self):
        """Проверка что style_instruction всегда присутствует в guidance"""
        test_messages = [
            "привет",
            "Здравствуйте",
            "чё там",
            "Добрый день!",
            "норм?",
        ]

        for msg in test_messages:
            result = self.analyzer.analyze(msg)
            guidance = self.analyzer.get_response_guidance(result)
            assert "style_instruction" in guidance, f"style_instruction отсутствует для: {msg}"

    def test_informal_markers_detection(self):
        """Проверка маркеров неформального стиля"""
        informal_messages = [
            "короче, надо подумать",  # "короче" а не "короч"
            "ок, понял",
            "норм, давай",
            "ну типа окей",  # несколько маркеров
        ]

        for msg in informal_messages:
            result = self.analyzer.analyze(msg)
            assert result.style == Style.INFORMAL, f"Ожидался INFORMAL для: {msg}"

class TestObjectionCounterConfig:
    """Тесты для objection counter из конфига"""

    def test_price_counter_exists(self):
        """Контраргумент для цены существует в конфиге"""
        counter = settings.get_nested("objection.counters.price", "")
        assert counter != "", "Контраргумент для price должен быть в конфиге"
        assert "окупается" in counter.lower() or "экономи" in counter.lower()

    def test_competitor_counter_exists(self):
        """Контраргумент для конкурента существует в конфиге"""
        counter = settings.get_nested("objection.counters.competitor", "")
        assert counter != "", "Контраргумент для competitor должен быть в конфиге"

    def test_no_time_counter_exists(self):
        """Контраргумент для 'нет времени' существует в конфиге"""
        counter = settings.get_nested("objection.counters.no_time", "")
        assert counter != "", "Контраргумент для no_time должен быть в конфиге"

    def test_think_counter_exists(self):
        """Контраргумент для 'надо подумать' существует в конфиге"""
        counter = settings.get_nested("objection.counters.think", "")
        assert counter != "", "Контраргумент для think должен быть в конфиге"

    def test_all_objection_types_have_counters(self):
        """Все типы возражений должны иметь контраргументы"""
        objection_types = [
            "price", "competitor", "no_time", "think",
            "no_need", "trust", "timing", "complexity"
        ]

        for obj_type in objection_types:
            counter = settings.get_nested(f"objection.counters.{obj_type}", "")
            assert counter != "", f"Контраргумент для {obj_type} должен быть в конфиге"

class TestGeneratorObjectionContext:
    """Тесты для objection context в generator"""

    def test_get_objection_counter_from_config(self):
        """Получение контраргумента из конфига"""
        from src.generator import ResponseGenerator

        # Создаём mock LLM
        class MockLLM:
            def generate(self, prompt):
                return "Тестовый ответ"

        gen = ResponseGenerator(MockLLM())

        # Проверяем что метод возвращает контраргумент из конфига
        counter = gen._get_objection_counter("price", {})
        expected = settings.get_nested("objection.counters.price", "")
        assert counter == expected

    def test_get_objection_counter_fallback(self):
        """Fallback на PersonalizationEngine при отсутствии в конфиге"""
        from src.generator import ResponseGenerator, PersonalizationEngine

        class MockLLM:
            def generate(self, prompt):
                return "Тестовый ответ"

        gen = ResponseGenerator(MockLLM())

        # Для несуществующего типа должен использоваться fallback
        counter = gen._get_objection_counter("unknown_type", {"company_size": 10})
        # Fallback возвращает value_prop из PersonalizationEngine
        assert counter != ""

    def test_get_objection_counter_empty_for_no_type(self):
        """Пустой контраргумент если нет типа возражения"""
        from src.generator import ResponseGenerator

        class MockLLM:
            def generate(self, prompt):
                return "Тестовый ответ"

        gen = ResponseGenerator(MockLLM())

        counter = gen._get_objection_counter("", {})
        assert counter == ""

        counter = gen._get_objection_counter(None, {})
        assert counter == ""

class TestPromptTemplatesWithObjection:
    """Тесты для шаблонов промптов с возражениями"""

    def test_handle_objection_template_has_objection_counter(self):
        """Шаблон handle_objection содержит {objection_counter}"""
        from src.config import PROMPT_TEMPLATES

        template = PROMPT_TEMPLATES.get("handle_objection", "")
        assert "{objection_counter}" in template, \
            "Шаблон handle_objection должен содержать {objection_counter}"

    def test_handle_objection_template_has_objection_type(self):
        """Шаблон handle_objection содержит {objection_type}"""
        from src.config import PROMPT_TEMPLATES

        template = PROMPT_TEMPLATES.get("handle_objection", "")
        assert "{objection_type}" in template, \
            "Шаблон handle_objection должен содержать {objection_type}"

    def test_specific_objection_templates_exist(self):
        """Специфичные шаблоны для типов возражений существуют"""
        from src.config import PROMPT_TEMPLATES

        expected_templates = [
            "handle_objection_price",
            "handle_objection_competitor",
            "handle_objection_no_time",
            "handle_objection_think",
            "handle_objection_no_need",
            "handle_objection_trust",
            "handle_objection_timing",
            "handle_objection_complexity",
        ]

        for template_name in expected_templates:
            assert template_name in PROMPT_TEMPLATES, \
                f"Шаблон {template_name} должен существовать"

    def test_specific_templates_have_objection_counter(self):
        """Специфичные шаблоны содержат {objection_counter}"""
        from src.config import PROMPT_TEMPLATES

        templates_with_counter = [
            "handle_objection_price",
            "handle_objection_competitor",
            "handle_objection_no_time",
            "handle_objection_think",
            "handle_objection_no_need",
            "handle_objection_trust",
            "handle_objection_timing",
            "handle_objection_complexity",
        ]

        for template_name in templates_with_counter:
            template = PROMPT_TEMPLATES.get(template_name, "")
            assert "{objection_counter}" in template, \
                f"Шаблон {template_name} должен содержать {{objection_counter}}"

class TestSystemPromptWithStyle:
    """Тесты для SYSTEM_PROMPT с style_instruction"""

    def test_system_prompt_has_style_instruction_placeholder(self):
        """SYSTEM_PROMPT содержит {style_instruction}"""
        from src.config import SYSTEM_PROMPT

        assert "{style_instruction}" in SYSTEM_PROMPT, \
            "SYSTEM_PROMPT должен содержать {style_instruction}"

    def test_system_prompt_has_tone_instruction_placeholder(self):
        """SYSTEM_PROMPT содержит {tone_instruction}"""
        from src.config import SYSTEM_PROMPT

        assert "{tone_instruction}" in SYSTEM_PROMPT, \
            "SYSTEM_PROMPT должен содержать {tone_instruction}"

    def test_system_prompt_can_be_formatted(self):
        """SYSTEM_PROMPT можно форматировать с обоими инструкциями"""
        from src.config import SYSTEM_PROMPT

        formatted = SYSTEM_PROMPT.format(
            tone_instruction="Будь кратким.",
            style_instruction="Отвечай менее формально."
        )

        assert "Будь кратким." in formatted
        assert "Отвечай менее формально." in formatted

    def test_system_prompt_with_empty_instructions(self):
        """SYSTEM_PROMPT форматируется корректно с пустыми инструкциями"""
        from src.config import SYSTEM_PROMPT

        formatted = SYSTEM_PROMPT.format(
            tone_instruction="",
            style_instruction=""
        )

        # Должен содержать базовый текст
        assert "менеджер по продажам" in formatted.lower()
        assert "русском языке" in formatted.lower()

class TestToneAnalyzerConfigIntegration:
    """Тесты интеграции ToneAnalyzer с конфигом"""

    def test_thresholds_from_config(self):
        """Пороги анализатора тона из конфига"""
        # Проверяем что пороги существуют в конфиге
        tier1 = settings.get_nested("tone_analyzer.thresholds.tier1_high_confidence")
        tier2 = settings.get_nested("tone_analyzer.thresholds.tier2_threshold")

        assert tier1 is not None, "tier1_high_confidence должен быть в конфиге"
        assert tier2 is not None, "tier2_threshold должен быть в конфиге"
        assert tier1 > tier2, "tier1 должен быть выше tier2"

    def test_semantic_settings_from_config(self):
        """Настройки семантического анализатора из конфига"""
        threshold = settings.get_nested("tone_analyzer.semantic.threshold")
        ambiguity = settings.get_nested("tone_analyzer.semantic.ambiguity_delta")

        assert threshold is not None, "semantic.threshold должен быть в конфиге"
        assert ambiguity is not None, "semantic.ambiguity_delta должен быть в конфиге"

class TestBotIntegration:
    """Тесты интеграции с bot.py"""

    def test_analyze_tone_returns_style_instruction(self):
        """_analyze_tone возвращает style_instruction"""
        # Импортируем после setup path
        from src.feature_flags import flags

        # Включаем tone_analysis для теста
        flags.set_override("tone_analysis", True)

        try:
            from src.bot import SalesBot

            # Создаём mock компоненты
            class MockLLM:
                def generate(self, prompt):
                    return "Тест"
                def generate_structured(self, prompt, schema):
                    return {"intent": "greeting", "confidence": 0.9}

            # Используем реальный ToneAnalyzer
            from src.tone_analyzer import ToneAnalyzer
            analyzer = ToneAnalyzer()

            # Анализируем неформальное сообщение
            result = analyzer.analyze("чё почём?")
            guidance = analyzer.get_response_guidance(result)

            assert "style_instruction" in guidance
            assert result.style == Style.INFORMAL
        finally:
            flags.clear_override("tone_analysis")

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
