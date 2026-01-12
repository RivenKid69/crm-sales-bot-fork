"""
Тесты для исправленных приоритетных паттернов в patterns.py

Эти тесты проверяют все исправленные паттерны:
1. rejection паттерны с word boundaries (не интересн, не нужн, не хоч, не буд)
2. отказ/отказываюсь с negative lookahead для compound words
3. закрыт/банкрот с word boundaries
4. не потян с word boundary
5. занят/загружен с контекстом
6. пока в farewell с end-of-line контекстом
"""

import pytest
import re
import sys
import os
import importlib.util

# Direct import to avoid loading the full classifier package which has dependencies
_patterns_path = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'src', 'classifier', 'intents', 'patterns.py'
)
_spec = importlib.util.spec_from_file_location('patterns', _patterns_path)
_patterns_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_patterns_module)
COMPILED_PRIORITY_PATTERNS = _patterns_module.COMPILED_PRIORITY_PATTERNS
PRIORITY_PATTERNS = _patterns_module.PRIORITY_PATTERNS


def match_pattern(text: str) -> tuple[str, float] | None:
    """Проверяет текст на совпадение с приоритетными паттернами."""
    text_lower = text.lower()
    for pattern, intent, confidence in COMPILED_PRIORITY_PATTERNS:
        if pattern.search(text_lower):
            return (intent, confidence)
    return None


class TestRejectionWordBoundaries:
    """Тесты для rejection паттернов с word boundaries."""

    # =========================================================================
    # ДОЛЖНО матчиться как rejection
    # =========================================================================

    @pytest.mark.parametrize("text,expected_intent", [
        # "не интересно" - отказ
        ("не интересно", "rejection"),
        ("мне не интересно", "rejection"),
        ("нам не интересно", "rejection"),
        ("это не интересно", "rejection"),
        ("совсем не интересно", "rejection"),
        # слитное написание
        ("неинтересно", "rejection"),

        # "не нужно" - теперь классифицируется как no_need (SPIN)
        # Это изменение в Phase 4 - более тонкая классификация для SPIN-сценариев
        ("не нужно", "no_need"),
        ("мне не нужно", "no_need"),
        ("нам не нужно", "no_need"),
        ("это не нужно", "no_need"),
        # слитное написание
        ("ненужно", "no_need"),

        # "не хочу/хотим" - отказ
        ("не хочу", "rejection"),
        ("я не хочу", "rejection"),
        ("мы не хотим", "rejection"),
        ("не хочется", "rejection"),

        # "не буду/будем" - отказ
        ("не буду", "rejection"),
        ("я не буду", "rejection"),
        ("мы не будем", "rejection"),
        ("не буду покупать", "rejection"),
    ])
    def test_rejection_patterns_match(self, text, expected_intent):
        """Проверяет что отказы корректно детектируются."""
        result = match_pattern(text)
        assert result is not None, f"'{text}' should match a pattern"
        assert result[0] == expected_intent, f"'{text}' should be {expected_intent}, got {result[0]}"

    # =========================================================================
    # НЕ ДОЛЖНО матчиться как rejection (false positives)
    # =========================================================================

    @pytest.mark.parametrize("text", [
        # "мне нужна" - это question_features или agreement, НЕ rejection!
        "мне нужна CRM",
        "мне нужна техническая документация",
        "мне нужна помощь",
        "мне нужно узнать о вашей системе",
        "нам нужна автоматизация",

        # "мне интересно" - это agreement, НЕ rejection!
        "мне интересно",
        "мне интересно узнать",
        "мне интересна эта тема",
        "нам интересно ваше предложение",

        # "мне хочется" - это желание, НЕ rejection!
        "мне хочется попробовать",
        "мне хочется узнать подробнее",

        # "мне будет" - НЕ rejection!
        "мне будет интересно",
        "мне будет удобно в понедельник",
        "нам будет полезно",
    ])
    def test_rejection_no_false_positives(self, text):
        """Проверяет что положительные фразы НЕ детектируются как rejection."""
        result = match_pattern(text)
        if result is not None:
            assert result[0] != "rejection", f"'{text}' should NOT be rejection, got {result[0]}"


class TestOtkazPattern:
    """Тесты для паттерна отказ/отказываюсь."""

    # =========================================================================
    # ДОЛЖНО матчиться как rejection
    # =========================================================================

    @pytest.mark.parametrize("text,expected_intent", [
        ("отказ", "rejection"),
        ("отказываюсь", "rejection"),
        ("я отказываюсь", "rejection"),
        ("мы отказываемся", "rejection"),
        ("категорический отказ", "rejection"),
        ("это отказ", "rejection"),
    ])
    def test_otkaz_patterns_match(self, text, expected_intent):
        """Проверяет что отказы корректно детектируются."""
        result = match_pattern(text)
        assert result is not None, f"'{text}' should match a pattern"
        assert result[0] == expected_intent, f"'{text}' should be {expected_intent}, got {result[0]}"

    # =========================================================================
    # НЕ ДОЛЖНО матчиться как rejection (compound words)
    # =========================================================================

    @pytest.mark.parametrize("text", [
        # compound words с "отказ"
        "отказоустойчивость",
        "отказоустойчивая система",
        "высокая отказоустойчивость",
        "безотказный",
        "безотказная работа",
        "отказоустойчивый сервер",
    ])
    def test_otkaz_no_false_positives(self, text):
        """Проверяет что compound words с 'отказ' НЕ детектируются как rejection."""
        result = match_pattern(text)
        if result is not None:
            assert result[0] != "rejection", f"'{text}' should NOT be rejection, got {result[0]}"


class TestZakrytPattern:
    """Тесты для паттерна закрыт/банкрот."""

    # =========================================================================
    # ДОЛЖНО матчиться как rejection
    # =========================================================================

    @pytest.mark.parametrize("text,expected_intent", [
        ("мы закрыты", "rejection"),
        ("мы закрылись", "rejection"),
        ("мы закрываемся", "rejection"),
        ("мы банкроты", "rejection"),
        ("мы банкрот", "rejection"),
        ("компания ликвидирована", "rejection"),
        ("мы ликвидируемся", "rejection"),
    ])
    def test_zakryt_patterns_match(self, text, expected_intent):
        """Проверяет что статусы закрытия корректно детектируются."""
        result = match_pattern(text)
        assert result is not None, f"'{text}' should match a pattern"
        assert result[0] == expected_intent, f"'{text}' should be {expected_intent}, got {result[0]}"

    # =========================================================================
    # НЕ ДОЛЖНО матчиться как rejection (другие значения)
    # =========================================================================

    @pytest.mark.parametrize("text", [
        # "закрытие" как существительное (не про компанию)
        "закрытие сделки",
        "закрытие месяца",
        "автоматическое закрытие",
        # "закрытый" как прилагательное
        "закрытый канал",
        "закрытый клуб",
        "закрытая группа",
        # "ликвидация" как процесс (не про компанию)
        "ликвидация задолженности",
        "ликвидация последствий",
    ])
    def test_zakryt_no_false_positives(self, text):
        """Проверяет что другие значения слов НЕ детектируются как rejection."""
        result = match_pattern(text)
        if result is not None:
            assert result[0] != "rejection", f"'{text}' should NOT be rejection, got {result[0]}"


class TestNePotyanPattern:
    """Тесты для паттерна 'не потянем'."""

    # =========================================================================
    # ДОЛЖНО матчиться как objection_price
    # =========================================================================

    @pytest.mark.parametrize("text,expected_intent", [
        ("не потянем", "objection_price"),
        ("мы не потянем", "objection_price"),
        ("не потяну такую сумму", "objection_price"),
        ("не потянем эту цену", "objection_price"),
    ])
    def test_ne_potyan_patterns_match(self, text, expected_intent):
        """Проверяет что 'не потянем' корректно детектируется."""
        result = match_pattern(text)
        assert result is not None, f"'{text}' should match a pattern"
        assert result[0] == expected_intent, f"'{text}' should be {expected_intent}, got {result[0]}"

    # =========================================================================
    # НЕ ДОЛЖНО матчиться как objection_price
    # =========================================================================

    @pytest.mark.parametrize("text", [
        # "мне потянет" - это положительное высказывание
        "мне потянет",
        "нам потянет",
        "думаю нам потянет",
        "может мне потянет",
    ])
    def test_ne_potyan_no_false_positives(self, text):
        """Проверяет что 'мне потянет' НЕ детектируется как objection_price."""
        result = match_pattern(text)
        if result is not None:
            assert result[0] != "objection_price", f"'{text}' should NOT be objection_price, got {result[0]}"


class TestZanyatZagruzhenPattern:
    """Тесты для паттерна занят/загружен."""

    # =========================================================================
    # ДОЛЖНО матчиться как objection_no_time
    # =========================================================================

    @pytest.mark.parametrize("text,expected_intent", [
        ("я занят", "objection_no_time"),
        ("мы заняты", "objection_no_time"),
        ("сейчас занят", "objection_no_time"),
        ("я загружен", "objection_no_time"),
        ("сейчас загружены", "objection_no_time"),
        ("мы очень заняты", "objection_no_time"),
        ("я очень загружен", "objection_no_time"),
        # слова без контекста
        ("запара", "objection_no_time"),
        ("у нас завал", "objection_no_time"),
        ("сейчас аврал", "objection_no_time"),
    ])
    def test_zanyat_patterns_match(self, text, expected_intent):
        """Проверяет что 'занят/загружен' корректно детектируется."""
        result = match_pattern(text)
        assert result is not None, f"'{text}' should match a pattern"
        assert result[0] == expected_intent, f"'{text}' should be {expected_intent}, got {result[0]}"

    # =========================================================================
    # НЕ ДОЛЖНО матчиться как objection_no_time
    # =========================================================================

    @pytest.mark.parametrize("text", [
        # "занятие" - существительное, не про занятость
        "занятие спортом",
        "интересное занятие",
        "любимое занятие",
        # "занятость" - тоже существительное
        "высокая занятость",
        "полная занятость",
        # "загружен" - про файлы/данные
        "файл загружен",
        "данные загружены",
        "документ загружен",
        # "место занято" - не про время
        "место занято",
        "это место занято",
        "все места заняты",
    ])
    def test_zanyat_no_false_positives(self, text):
        """Проверяет что другие значения слов НЕ детектируются как objection_no_time."""
        result = match_pattern(text)
        if result is not None:
            assert result[0] != "objection_no_time", f"'{text}' should NOT be objection_no_time, got {result[0]}"


class TestPokaFarewellPattern:
    """Тесты для паттерна 'пока' в farewell."""

    # =========================================================================
    # ДОЛЖНО матчиться как farewell
    # =========================================================================

    @pytest.mark.parametrize("text,expected_intent", [
        # "пока" в конце предложения
        ("пока", "farewell"),
        ("пока!", "farewell"),
        ("пока.", "farewell"),
        ("ну пока", "farewell"),
        ("ладно, пока", "farewell"),
        # "пока" с другими прощаниями
        ("спасибо, пока", "farewell"),
        ("до свидания", "farewell"),
        ("до связи", "farewell"),
        ("всего доброго", "farewell"),
    ])
    def test_poka_farewell_patterns_match(self, text, expected_intent):
        """Проверяет что 'пока' как прощание корректно детектируется."""
        result = match_pattern(text)
        assert result is not None, f"'{text}' should match a pattern"
        assert result[0] == expected_intent, f"'{text}' should be {expected_intent}, got {result[0]}"

    # =========================================================================
    # НЕ ДОЛЖНО матчиться как farewell
    # =========================================================================

    @pytest.mark.parametrize("text", [
        # "пока используем" - текущее состояние, НЕ прощание
        "пока используем excel",
        "пока используем другую систему",
        "пока работаем с 1с",
        "пока сидим на амо",
        # "пока изучаем" - процесс, НЕ прощание
        "пока изучаю вопрос",
        "пока думаю",
        "пока решаем",
        # "пока не" - условие, НЕ прощание
        "пока не готовы",
        "пока не определились",
        "пока не знаю",
    ])
    def test_poka_no_false_positives(self, text):
        """Проверяет что 'пока используем' НЕ детектируется как farewell."""
        result = match_pattern(text)
        if result is not None:
            assert result[0] != "farewell", f"'{text}' should NOT be farewell, got {result[0]}"


class TestCriticalSimulationPhrases:
    """
    Критические тесты для фраз из симуляции, которые вызывали false positives.
    Эти фразы были обнаружены в simulation_report_full.txt.
    """

    @pytest.mark.parametrize("text,expected_not_intent", [
        # Фразы которые НЕ должны быть rejection
        ("мне нужна техдок", "rejection"),
        ("мне нужна автоматизация", "rejection"),
        ("нам нужно решение", "rejection"),
        ("мне интересно узнать", "rejection"),

        # Фразы которые НЕ должны быть farewell
        ("пока используем excel", "farewell"),
        ("пока работаем в 1с", "farewell"),
        ("пока у нас другая система", "farewell"),

        # Фразы которые НЕ должны быть rejection (compound words)
        ("отказоустойчивость вашей системы", "rejection"),
        ("какая отказоустойчивость?", "rejection"),
        ("нужна высокая отказоустойчивость", "rejection"),
    ])
    def test_simulation_false_positives_fixed(self, text, expected_not_intent):
        """Проверяет что фразы из симуляции больше не дают false positives."""
        result = match_pattern(text)
        if result is not None:
            assert result[0] != expected_not_intent, \
                f"'{text}' should NOT be {expected_not_intent}, got {result[0]}"


class TestPatternCompilation:
    """Тесты для проверки корректной компиляции паттернов."""

    def test_all_patterns_compile(self):
        """Проверяет что все паттерны корректно компилируются."""
        for pattern_str, intent, confidence in PRIORITY_PATTERNS:
            try:
                re.compile(pattern_str, re.IGNORECASE)
            except re.error as e:
                pytest.fail(f"Pattern '{pattern_str}' for intent '{intent}' failed to compile: {e}")

    def test_compiled_patterns_count_matches(self):
        """Проверяет что количество скомпилированных паттернов совпадает."""
        assert len(COMPILED_PRIORITY_PATTERNS) == len(PRIORITY_PATTERNS), \
            "Compiled patterns count should match original patterns count"

    def test_all_patterns_have_valid_intents(self):
        """Проверяет что все паттерны имеют валидные интенты."""
        valid_intents = {
            # Основные интенты
            "rejection", "agreement", "greeting", "farewell", "gratitude",
            "question_features", "question_integrations", "price_question",
            "pricing_details", "comparison", "objection_price", "objection_no_time",
            "objection_competitor", "objection_think", "demo_request",
            "callback_request", "consultation_request", "small_talk", "unclear",
            # Дополнительные интенты (Phase 4)
            "contact_provided", "correct_info", "go_back",
            "situation_provided", "problem_revealed", "implication_acknowledged",
            "need_expressed", "no_problem", "no_need", "info_provided",
            "objection_complexity", "objection_no_need", "objection_timing",
            "objection_trust"
        }
        for pattern_str, intent, confidence in PRIORITY_PATTERNS:
            assert intent in valid_intents, \
                f"Pattern '{pattern_str}' has invalid intent: {intent}"

    def test_all_patterns_have_valid_confidence(self):
        """Проверяет что все паттерны имеют валидную confidence."""
        for pattern_str, intent, confidence in PRIORITY_PATTERNS:
            assert 0.0 <= confidence <= 1.0, \
                f"Pattern '{pattern_str}' has invalid confidence: {confidence}"


class TestEdgeCases:
    """Тесты для edge cases."""

    @pytest.mark.parametrize("text,should_match", [
        # Пустые и специальные строки
        ("", False),
        ("   ", False),
        (".", False),
        ("?", True),  # unclear pattern
        ("???", True),  # unclear pattern

        # Смешанный регистр
        ("НЕ ИНТЕРЕСНО", True),
        ("Мне Нужна CRM", False),  # положительная фраза
        ("ОТКАЗ", True),

        # Строки с пробелами
        ("  пока  ", True),
        ("  не интересно  ", True),
    ])
    def test_edge_cases(self, text, should_match):
        """Проверяет edge cases."""
        result = match_pattern(text)
        if should_match:
            assert result is not None, f"'{text}' should match some pattern"
        # Для should_match=False мы не проверяем - может матчить другие паттерны


class TestIntegrationWithNormalization:
    """
    Тесты для проверки работы паттернов с нормализованным текстом.
    Нормализатор: "умеет"→"умет", "программа"→"програма"
    """

    @pytest.mark.parametrize("text,expected_intent", [
        # Нормализованные фразы
        ("что умет програма", "question_features"),
        ("расскажи те о системе", "question_features"),
        ("что вы предлагаете", "question_features"),
    ])
    def test_normalized_text_matching(self, text, expected_intent):
        """Проверяет что нормализованные фразы матчатся корректно."""
        result = match_pattern(text)
        assert result is not None, f"'{text}' should match a pattern"
        assert result[0] == expected_intent, f"'{text}' should be {expected_intent}, got {result[0]}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
