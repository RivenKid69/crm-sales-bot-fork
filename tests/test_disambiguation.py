"""
Тесты для модулей disambiguation (этапы 1 и 2).

Покрытие:
- DisambiguationAnalyzer: анализ scores и принятие решений
- DisambiguationUI: форматирование вопросов и парсинг ответов
- DisambiguationMetrics: метрики эффективности
- StateMachine: disambiguation флаги и методы
- intent_labels: маппинг интентов на labels
- feature_flags: intent_disambiguation flag
- config: DISAMBIGUATION_CONFIG
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from classifier.disambiguation import DisambiguationAnalyzer, DisambiguationResult
from disambiguation_ui import DisambiguationUI
from metrics import DisambiguationMetrics
from state_machine import StateMachine
from constants.intent_labels import INTENT_LABELS, get_label
from feature_flags import FeatureFlags
from config import DISAMBIGUATION_CONFIG, CLASSIFIER_CONFIG


# =============================================================================
# DisambiguationAnalyzer Tests
# =============================================================================

class TestDisambiguationAnalyzerBasic:
    """Базовые тесты DisambiguationAnalyzer"""

    @pytest.fixture
    def analyzer(self):
        return DisambiguationAnalyzer()

    def test_create_analyzer(self, analyzer):
        """Создание экземпляра DisambiguationAnalyzer"""
        assert analyzer is not None
        assert analyzer.config is not None
        assert analyzer.disambiguation_config is not None

    def test_analyze_returns_result(self, analyzer):
        """analyze возвращает DisambiguationResult"""
        result = analyzer.analyze(
            root_scores={"greeting": 3},
            lemma_scores={}
        )
        assert isinstance(result, DisambiguationResult)

    def test_empty_scores_returns_unclear(self, analyzer):
        """Пустые scores возвращают unclear"""
        result = analyzer.analyze(
            root_scores={},
            lemma_scores={}
        )
        assert not result.needs_disambiguation
        assert result.fallback_intent == "unclear"
        assert result.merged_scores == {}

    def test_high_confidence_no_disambiguation(self, analyzer):
        """Высокий confidence не требует disambiguation"""
        result = analyzer.analyze(
            root_scores={"greeting": 3},
            lemma_scores={"greeting": 4.0}
        )
        assert not result.needs_disambiguation
        assert result.top_confidence > 0

    def test_low_confidence_returns_unclear(self, analyzer):
        """Низкий confidence возвращает unclear"""
        result = analyzer.analyze(
            root_scores={"unclear": 1},
            lemma_scores={}
        )
        assert not result.needs_disambiguation
        assert result.fallback_intent == "unclear"


class TestDisambiguationAnalyzerLogic:
    """Тесты логики disambiguation"""

    @pytest.fixture
    def analyzer(self):
        return DisambiguationAnalyzer()

    def test_close_scores_triggers_disambiguation(self, analyzer):
        """Близкие scores вызывают disambiguation"""
        result = analyzer.analyze(
            root_scores={"price_question": 2, "question_features": 2},
            lemma_scores={"price_question": 2.0, "question_features": 2.0}
        )
        assert result.needs_disambiguation
        assert len(result.options) >= 2

    def test_large_gap_no_disambiguation(self, analyzer):
        """Большой разрыв между scores не требует disambiguation"""
        result = analyzer.analyze(
            root_scores={"greeting": 3, "agreement": 1},
            lemma_scores={"greeting": 3.0}
        )
        assert not result.needs_disambiguation

    def test_bypass_intents_no_disambiguation(self, analyzer):
        """Bypass интенты не требуют disambiguation"""
        # rejection в bypass_disambiguation_intents
        result = analyzer.analyze(
            root_scores={"rejection": 2, "agreement": 2},
            lemma_scores={}
        )
        assert not result.needs_disambiguation

    def test_contact_provided_bypass(self, analyzer):
        """contact_provided в bypass интентах"""
        result = analyzer.analyze(
            root_scores={"contact_provided": 2, "agreement": 2},
            lemma_scores={}
        )
        assert not result.needs_disambiguation

    def test_demo_request_bypass(self, analyzer):
        """demo_request в bypass интентах"""
        result = analyzer.analyze(
            root_scores={"demo_request": 2, "agreement": 2},
            lemma_scores={}
        )
        assert not result.needs_disambiguation


class TestDisambiguationAnalyzerCooldown:
    """Тесты cooldown механизма"""

    @pytest.fixture
    def analyzer(self):
        return DisambiguationAnalyzer()

    def test_cooldown_prevents_disambiguation(self, analyzer):
        """Cooldown предотвращает повторный disambiguation"""
        result = analyzer.analyze(
            root_scores={"price_question": 2, "question_features": 2},
            lemma_scores={},
            context={"turns_since_last_disambiguation": 1}
        )
        assert not result.needs_disambiguation

    def test_no_cooldown_after_threshold(self, analyzer):
        """После cooldown threshold disambiguation разрешён"""
        result = analyzer.analyze(
            root_scores={"price_question": 2, "question_features": 2},
            lemma_scores={},
            context={"turns_since_last_disambiguation": 999}
        )
        # Может быть disambiguation если scores близкие
        assert isinstance(result.needs_disambiguation, bool)

    def test_none_context_handled(self, analyzer):
        """None context обрабатывается корректно"""
        result = analyzer.analyze(
            root_scores={"price_question": 2, "question_features": 2},
            lemma_scores={},
            context=None
        )
        assert isinstance(result.needs_disambiguation, bool)


class TestDisambiguationAnalyzerMergeScores:
    """Тесты слияния scores"""

    @pytest.fixture
    def analyzer(self):
        return DisambiguationAnalyzer()

    def test_merge_only_root_scores(self, analyzer):
        """Слияние только root scores"""
        result = analyzer._merge_scores(
            root_scores={"greeting": 3},
            lemma_scores={}
        )
        assert "greeting" in result
        assert result["greeting"] > 0
        assert result["greeting"] <= 1.0

    def test_merge_both_scores(self, analyzer):
        """Слияние root и lemma scores"""
        result = analyzer._merge_scores(
            root_scores={"greeting": 2},
            lemma_scores={"greeting": 2.0}
        )
        assert "greeting" in result
        # Должен быть взвешенное среднее
        assert result["greeting"] > 0

    def test_merge_different_intents(self, analyzer):
        """Слияние с разными интентами"""
        result = analyzer._merge_scores(
            root_scores={"greeting": 2},
            lemma_scores={"agreement": 2.0}
        )
        assert "greeting" in result
        assert "agreement" in result


class TestDisambiguationAnalyzerBuildOptions:
    """Тесты построения опций"""

    @pytest.fixture
    def analyzer(self):
        return DisambiguationAnalyzer()

    def test_build_options_excludes_unclear(self, analyzer):
        """build_options исключает unclear"""
        options = analyzer._build_options([
            ("unclear", 0.5),
            ("price_question", 0.5),
            ("question_features", 0.5)
        ])
        intents = [o["intent"] for o in options]
        assert "unclear" not in intents

    def test_build_options_excludes_small_talk(self, analyzer):
        """build_options исключает small_talk"""
        options = analyzer._build_options([
            ("small_talk", 0.5),
            ("price_question", 0.5),
            ("question_features", 0.5)
        ])
        intents = [o["intent"] for o in options]
        assert "small_talk" not in intents

    def test_build_options_max_limit(self, analyzer):
        """build_options ограничивает количество опций"""
        max_opts = analyzer.disambiguation_config["max_options"]
        options = analyzer._build_options([
            ("price_question", 0.5),
            ("question_features", 0.5),
            ("agreement", 0.5),
            ("greeting", 0.5),
            ("demo_request", 0.5)
        ])
        assert len(options) <= max_opts

    def test_build_options_min_confidence(self, analyzer):
        """build_options отфильтровывает низкий confidence"""
        min_conf = analyzer.disambiguation_config["min_option_confidence"]
        options = analyzer._build_options([
            ("price_question", 0.5),
            ("question_features", 0.1)  # Ниже порога
        ])
        for opt in options:
            assert opt["confidence"] >= min_conf

    def test_build_options_has_labels(self, analyzer):
        """build_options добавляет labels"""
        options = analyzer._build_options([
            ("price_question", 0.5),
            ("question_features", 0.5)
        ])
        for opt in options:
            assert "label" in opt
            assert opt["label"] is not None


# =============================================================================
# DisambiguationUI Tests
# =============================================================================

class TestDisambiguationUIBasic:
    """Базовые тесты DisambiguationUI"""

    @pytest.fixture
    def ui(self):
        return DisambiguationUI()

    def test_create_ui(self, ui):
        """Создание экземпляра DisambiguationUI"""
        assert ui is not None

    def test_format_question_returns_string(self, ui):
        """format_question возвращает строку"""
        options = [
            {"intent": "price_question", "label": "Цена"},
            {"intent": "question_features", "label": "Функции"}
        ]
        result = ui.format_question("", options, {})
        assert isinstance(result, str)
        assert len(result) > 0


class TestDisambiguationUIParseNumeric:
    """Тесты парсинга числовых ответов"""

    @pytest.fixture
    def ui(self):
        return DisambiguationUI()

    def test_parse_number_1(self, ui):
        """Парсинг числа 1"""
        options = [
            {"intent": "price_question", "label": "Цена"},
            {"intent": "question_features", "label": "Функции"}
        ]
        assert ui.parse_answer("1", options) == "price_question"

    def test_parse_number_2(self, ui):
        """Парсинг числа 2"""
        options = [
            {"intent": "price_question", "label": "Цена"},
            {"intent": "question_features", "label": "Функции"}
        ]
        assert ui.parse_answer("2", options) == "question_features"

    def test_parse_number_3(self, ui):
        """Парсинг числа 3"""
        options = [
            {"intent": "price_question", "label": "Цена"},
            {"intent": "question_features", "label": "Функции"},
            {"intent": "agreement", "label": "Продолжить"}
        ]
        assert ui.parse_answer("3", options) == "agreement"


class TestDisambiguationUIParseWord:
    """Тесты парсинга словесных номеров"""

    @pytest.fixture
    def ui(self):
        return DisambiguationUI()

    def test_parse_first(self, ui):
        """Парсинг 'первый'"""
        options = [
            {"intent": "price_question", "label": "Цена"},
            {"intent": "question_features", "label": "Функции"}
        ]
        assert ui.parse_answer("первый", options) == "price_question"

    def test_parse_second(self, ui):
        """Парсинг 'второй'"""
        options = [
            {"intent": "price_question", "label": "Цена"},
            {"intent": "question_features", "label": "Функции"}
        ]
        assert ui.parse_answer("второе", options) == "question_features"

    def test_parse_first_partial(self, ui):
        """Парсинг 'перв...'"""
        options = [
            {"intent": "price_question", "label": "Цена"},
            {"intent": "question_features", "label": "Функции"}
        ]
        assert ui.parse_answer("перв", options) == "price_question"


class TestDisambiguationUIParseKeyword:
    """Тесты парсинга ключевых слов"""

    @pytest.fixture
    def ui(self):
        return DisambiguationUI()

    def test_parse_price_keyword(self, ui):
        """Парсинг ключевого слова 'цена'"""
        options = [
            {"intent": "price_question", "label": "Цена"},
            {"intent": "question_features", "label": "Функции"}
        ]
        assert ui.parse_answer("про цену", options) == "price_question"

    def test_parse_features_keyword(self, ui):
        """Парсинг ключевого слова 'функции'"""
        options = [
            {"intent": "price_question", "label": "Цена"},
            {"intent": "question_features", "label": "Функции"}
        ]
        assert ui.parse_answer("какие функции", options) == "question_features"

    def test_parse_keyword_only_in_options(self, ui):
        """Ключевое слово работает только для интентов в options"""
        options = [
            {"intent": "agreement", "label": "Продолжить"},
            {"intent": "greeting", "label": "Приветствие"}
        ]
        # "цена" не должна сработать, т.к. price_question нет в options
        result = ui.parse_answer("цена", options)
        assert result is None

    def test_parse_podrobnee_keyword(self, ui):
        """Парсинг ключевого слова 'подробнее о системе' -> question_features."""
        options = [
            {"intent": "question_features", "label": "Подробнее о системе"},
            {"intent": "price_question", "label": "Цены"},
        ]
        assert ui.parse_answer("подробнее о системе", options) == "question_features"

    def test_parse_sistema_keyword(self, ui):
        """Парсинг ключевого слова 'о системе' -> question_features."""
        options = [
            {"intent": "question_features", "label": "О системе"},
            {"intent": "demo_request", "label": "Демо"},
        ]
        assert ui.parse_answer("расскажите о системе", options) == "question_features"

    def test_parse_pozhje_keyword(self, ui):
        """Парсинг ключевого слова 'связаться позже' -> callback_request."""
        options = [
            {"intent": "callback_request", "label": "Связаться позже"},
            {"intent": "demo_request", "label": "Демо"},
        ]
        assert ui.parse_answer("связаться позже", options) == "callback_request"

    def test_parse_pozhe_standalone(self, ui):
        """Парсинг 'позже' -> callback_request."""
        options = [
            {"intent": "callback_request", "label": "Связаться позже"},
            {"intent": "question_features", "label": "Функции"},
        ]
        assert ui.parse_answer("позже", options) == "callback_request"


class TestDisambiguationUIParseEmpty:
    """Тесты парсинга пустых ответов"""

    @pytest.fixture
    def ui(self):
        return DisambiguationUI()

    def test_parse_empty_string(self, ui):
        """Пустая строка возвращает None"""
        options = [{"intent": "price_question", "label": "Цена"}]
        assert ui.parse_answer("", options) is None

    def test_parse_whitespace(self, ui):
        """Пробелы возвращают None"""
        options = [{"intent": "price_question", "label": "Цена"}]
        assert ui.parse_answer("   ", options) is None

    def test_parse_none(self, ui):
        """None возвращает None"""
        options = [{"intent": "price_question", "label": "Цена"}]
        # Это может вызвать ошибку, нужна проверка
        result = ui.parse_answer(None, options)  # type: ignore
        assert result is None


class TestDisambiguationUIFormat:
    """Тесты форматирования вопросов"""

    @pytest.fixture
    def ui(self):
        return DisambiguationUI()

    def test_format_two_options_inline(self, ui):
        """Два варианта форматируются inline"""
        options = [
            {"intent": "price_question", "label": "Узнать стоимость"},
            {"intent": "question_features", "label": "Узнать о функциях"}
        ]
        result = ui.format_question("", options, {})
        assert "или" in result
        assert "1." not in result

    def test_format_three_options_numbered(self, ui):
        """Три варианта форматируются с номерами"""
        options = [
            {"intent": "price_question", "label": "Цена"},
            {"intent": "question_features", "label": "Функции"},
            {"intent": "agreement", "label": "Продолжить"}
        ]
        result = ui.format_question("", options, {})
        assert "1." in result
        assert "2." in result
        assert "3." in result

    def test_format_handles_missing_label(self, ui):
        """Форматирование с отсутствующим label"""
        options = [
            {"intent": "unknown_intent"},
            {"intent": "another_unknown"}
        ]
        result = ui.format_question("", options, {})
        # Должен использовать intent как label
        assert "unknown_intent" in result or "another_unknown" in result


class TestDisambiguationUIGetOptionLabel:
    """Тесты _get_option_label"""

    @pytest.fixture
    def ui(self):
        return DisambiguationUI()

    def test_get_option_label_explicit(self, ui):
        """Явно указанный label"""
        label = ui._get_option_label({"intent": "test", "label": "Test Label"})
        assert label == "Test Label"

    def test_get_option_label_from_mapping(self, ui):
        """Label из INTENT_LABELS"""
        label = ui._get_option_label({"intent": "price_question"})
        assert label == "Узнать стоимость"

    def test_get_option_label_fallback(self, ui):
        """Fallback на intent name"""
        label = ui._get_option_label({"intent": "unknown_xyz"})
        assert label == "unknown_xyz"

    def test_get_option_label_never_returns_none(self, ui):
        """_get_option_label никогда не возвращает None"""
        # Различные варианты опций
        test_cases = [
            {"intent": "test", "label": "Test"},
            {"intent": "price_question"},
            {"intent": "unknown_intent"},
            {"intent": ""},
        ]
        for opt in test_cases:
            result = ui._get_option_label(opt)
            assert result is not None


class TestDisambiguationUIRepeatQuestion:
    """Тесты format_repeat_question"""

    @pytest.fixture
    def ui(self):
        return DisambiguationUI()

    def test_format_repeat_question(self, ui):
        """format_repeat_question возвращает строку"""
        options = [
            {"intent": "price_question", "label": "Цена"},
            {"intent": "question_features", "label": "Функции"}
        ]
        result = ui.format_repeat_question(options)
        assert isinstance(result, str)
        assert "Не совсем понял" in result

    def test_format_repeat_question_includes_custom_hint(self, ui):
        """format_repeat_question включает подсказку о своём варианте"""
        options = [
            {"intent": "price_question", "label": "Цена"},
            {"intent": "question_features", "label": "Функции"}
        ]
        result = ui.format_repeat_question(options)
        assert "своими словами" in result.lower()


# =============================================================================
# DisambiguationUI Custom Input Tests (4-й вариант)
# =============================================================================

class TestDisambiguationUICustomInput:
    """Тесты для 4-го варианта 'Свой вариант'"""

    @pytest.fixture
    def ui(self):
        return DisambiguationUI()

    def test_custom_input_marker_exists(self, ui):
        """CUSTOM_INPUT_MARKER существует"""
        assert hasattr(DisambiguationUI, "CUSTOM_INPUT_MARKER")
        assert DisambiguationUI.CUSTOM_INPUT_MARKER == "_custom_input"

    def test_parse_number_4_with_three_options(self, ui):
        """Парсинг числа 4 при 3 опциях возвращает custom_input"""
        options = [
            {"intent": "price_question", "label": "Цена"},
            {"intent": "question_features", "label": "Функции"},
            {"intent": "agreement", "label": "Продолжить"}
        ]
        result = ui.parse_answer("4", options)
        assert result == DisambiguationUI.CUSTOM_INPUT_MARKER

    def test_parse_number_3_with_two_options(self, ui):
        """Парсинг числа 3 при 2 опциях возвращает custom_input"""
        options = [
            {"intent": "price_question", "label": "Цена"},
            {"intent": "question_features", "label": "Функции"}
        ]
        result = ui.parse_answer("3", options)
        assert result == DisambiguationUI.CUSTOM_INPUT_MARKER

    def test_parse_fourth_word_with_three_options(self, ui):
        """Парсинг 'четвёртый' при 3 опциях возвращает custom_input"""
        options = [
            {"intent": "price_question", "label": "Цена"},
            {"intent": "question_features", "label": "Функции"},
            {"intent": "agreement", "label": "Продолжить"}
        ]
        assert ui.parse_answer("четвёртый", options) == DisambiguationUI.CUSTOM_INPUT_MARKER
        assert ui.parse_answer("четвертый", options) == DisambiguationUI.CUSTOM_INPUT_MARKER
        assert ui.parse_answer("четыре", options) == DisambiguationUI.CUSTOM_INPUT_MARKER

    def test_parse_third_word_with_two_options(self, ui):
        """Парсинг 'третий' при 2 опциях возвращает custom_input"""
        options = [
            {"intent": "price_question", "label": "Цена"},
            {"intent": "question_features", "label": "Функции"}
        ]
        assert ui.parse_answer("третий", options) == DisambiguationUI.CUSTOM_INPUT_MARKER
        assert ui.parse_answer("три", options) == DisambiguationUI.CUSTOM_INPUT_MARKER

    def test_parse_custom_keywords(self, ui):
        """Парсинг ключевых слов 'свой', 'другое'"""
        options = [
            {"intent": "price_question", "label": "Цена"},
            {"intent": "question_features", "label": "Функции"}
        ]
        assert ui.parse_answer("свой вариант", options) == DisambiguationUI.CUSTOM_INPUT_MARKER
        assert ui.parse_answer("своё", options) == DisambiguationUI.CUSTOM_INPUT_MARKER
        assert ui.parse_answer("другое", options) == DisambiguationUI.CUSTOM_INPUT_MARKER

    def test_format_numbered_includes_custom_hint(self, ui):
        """_format_numbered включает подсказку о своём варианте"""
        options = [
            {"intent": "price_question", "label": "Цена"},
            {"intent": "question_features", "label": "Функции"},
            {"intent": "agreement", "label": "Продолжить"}
        ]
        result = ui._format_numbered(options)
        assert "своими словами" in result.lower()

    def test_format_numbered_two_options_includes_custom_hint(self, ui):
        """_format_numbered с 2 опциями включает подсказку"""
        options = [
            {"intent": "price_question", "label": "Цена"},
            {"intent": "question_features", "label": "Функции"}
        ]
        result = ui._format_numbered(options)
        assert "своими словами" in result.lower()

    def test_number_4_does_not_match_when_only_one_option(self, ui):
        """Число 4 не срабатывает когда только 1 опция (custom = 2)"""
        options = [{"intent": "price_question", "label": "Цена"}]
        # "4" не должно совпадать, т.к. custom_input_index = 1 (2-й вариант)
        result = ui.parse_answer("4", options)
        assert result is None

    def test_number_2_is_custom_when_one_option(self, ui):
        """Число 2 = custom_input когда только 1 опция"""
        options = [{"intent": "price_question", "label": "Цена"}]
        result = ui.parse_answer("2", options)
        assert result == DisambiguationUI.CUSTOM_INPUT_MARKER

    def test_regular_options_still_work(self, ui):
        """Обычные опции по-прежнему работают"""
        options = [
            {"intent": "price_question", "label": "Цена"},
            {"intent": "question_features", "label": "Функции"},
            {"intent": "agreement", "label": "Продолжить"}
        ]
        assert ui.parse_answer("1", options) == "price_question"
        assert ui.parse_answer("2", options) == "question_features"
        assert ui.parse_answer("3", options) == "agreement"
        assert ui.parse_answer("первый", options) == "price_question"
        assert ui.parse_answer("второй", options) == "question_features"


class TestDisambiguationUICustomInputIntegration:
    """Интеграционные тесты для 'Свой вариант'"""

    @pytest.fixture
    def mock_llm(self):
        from unittest.mock import MagicMock
        llm = MagicMock()
        llm.generate.return_value = "Тестовый ответ"
        return llm

    @pytest.fixture
    def bot(self, mock_llm):
        from bot import SalesBot
        from feature_flags import flags

        flags.set_override("intent_disambiguation", True)
        flags.set_override("metrics_tracking", True)

        bot = SalesBot(mock_llm)
        bot.generator.generate = lambda action, ctx: "Тестовый ответ от генератора"
        yield bot

        flags.clear_override("intent_disambiguation")
        flags.clear_override("metrics_tracking")

    def test_custom_input_direct_classification(self, bot):
        """Свободный текст классифицируется напрямую"""
        options = [
            {"intent": "price_question", "label": "Узнать стоимость"},
            {"intent": "question_features", "label": "Узнать о функциях"}
        ]
        bot.state_machine.enter_disambiguation(options, {})

        # Пользователь пишет свой вопрос напрямую
        result = bot.process("Меня интересует интеграция с 1С")

        # Должен выйти из disambiguation и классифицировать
        assert not bot.state_machine.in_disambiguation
        assert "response" in result

    def test_custom_input_with_keyword_classifies(self, bot):
        """Ключевое слово 'свой' тоже классифицирует сообщение"""
        options = [
            {"intent": "price_question", "label": "Узнать стоимость"},
            {"intent": "question_features", "label": "Узнать о функциях"}
        ]
        bot.state_machine.enter_disambiguation(options, {})

        # Даже "свой вариант" классифицируется (хотя результат будет unclear)
        result = bot.process("свой вариант")

        assert not bot.state_machine.in_disambiguation
        assert "response" in result

    def test_next_message_after_custom_input_is_classified(self, bot):
        """Следующее сообщение после custom_input классифицируется обычно"""
        options = [
            {"intent": "price_question", "label": "Узнать стоимость"},
            {"intent": "question_features", "label": "Узнать о функциях"}
        ]
        bot.state_machine.enter_disambiguation(options, {})

        # Выбираем свой вариант
        bot.process("3")

        # Следующее сообщение должно быть классифицировано обычным образом
        assert not bot.state_machine.in_disambiguation
        result = bot.process("Меня интересует интеграция с 1С")

        # Сообщение обработано обычным классификатором
        assert "response" in result

    def test_custom_input_metrics_recorded(self, bot):
        """Метрики записываются при выборе custom_input"""
        options = [
            {"intent": "price_question", "label": "Узнать стоимость"},
            {"intent": "question_features", "label": "Узнать о функциях"}
        ]

        # Инициируем disambiguation через state_machine (как делает Blackboard pipeline)
        bot.state_machine.enter_disambiguation(
            options=options,
            extracted_data={},
        )
        bot.disambiguation_metrics.record_disambiguation(
            options=["price_question", "question_features"],
            scores={"price_question": 0.5, "question_features": 0.48},
        )

        # Выбираем свой вариант
        bot.process("свой")

        # Метрики должны быть записаны
        assert bot.disambiguation_metrics.total_disambiguations == 1


# =============================================================================
# DisambiguationMetrics Tests
# =============================================================================

class TestDisambiguationMetricsBasic:
    """Базовые тесты DisambiguationMetrics"""

    @pytest.fixture
    def metrics(self):
        return DisambiguationMetrics()

    def test_create_metrics(self, metrics):
        """Создание экземпляра DisambiguationMetrics"""
        assert metrics is not None
        assert metrics.total_disambiguations == 0

    def test_reset_metrics(self, metrics):
        """reset сбрасывает все метрики"""
        metrics.total_disambiguations = 10
        metrics.resolved_on_first_try = 5
        metrics.reset()
        assert metrics.total_disambiguations == 0
        assert metrics.resolved_on_first_try == 0


class TestDisambiguationMetricsRecording:
    """Тесты записи метрик"""

    @pytest.fixture
    def metrics(self):
        return DisambiguationMetrics()

    def test_record_disambiguation(self, metrics):
        """record_disambiguation увеличивает счётчик"""
        metrics.record_disambiguation(
            options=["price_question", "question_features"],
            scores={"price_question": 0.5, "question_features": 0.45}
        )
        assert metrics.total_disambiguations == 1
        assert len(metrics.score_gaps) == 1

    def test_record_disambiguation_by_intent(self, metrics):
        """record_disambiguation записывает по интентам"""
        metrics.record_disambiguation(
            options=["price_question", "question_features"],
            scores={}
        )
        assert metrics.disambiguation_by_intent.get("price_question") == 1
        assert metrics.disambiguation_by_intent.get("question_features") == 1

    def test_record_resolution_first_try(self, metrics):
        """record_resolution первая попытка"""
        metrics.record_disambiguation(["a", "b"], {})
        metrics.record_resolution("a", attempt=1, success=True)
        assert metrics.resolved_on_first_try == 1
        assert metrics.resolved_on_second_try == 0

    def test_record_resolution_second_try(self, metrics):
        """record_resolution вторая попытка"""
        metrics.record_disambiguation(["a", "b"], {})
        metrics.record_resolution("a", attempt=2, success=True)
        assert metrics.resolved_on_first_try == 0
        assert metrics.resolved_on_second_try == 1

    def test_record_resolution_failed(self, metrics):
        """record_resolution неудача"""
        metrics.record_disambiguation(["a", "b"], {})
        metrics.record_resolution("unclear", attempt=3, success=False)
        assert metrics.fallback_to_unclear == 1


class TestDisambiguationMetricsCalculations:
    """Тесты вычисления метрик"""

    @pytest.fixture
    def metrics(self):
        m = DisambiguationMetrics()
        # 10 disambiguations: 6 first try, 2 second try, 2 failed
        for _ in range(6):
            m.record_disambiguation(["a", "b"], {"a": 0.5, "b": 0.45})
            m.record_resolution("a", 1, True)
        for _ in range(2):
            m.record_disambiguation(["a", "b"], {"a": 0.5, "b": 0.45})
            m.record_resolution("a", 2, True)
        for _ in range(2):
            m.record_disambiguation(["a", "b"], {"a": 0.5, "b": 0.45})
            m.record_resolution("unclear", 3, False)
        return m

    def test_effectiveness_rate(self, metrics):
        """get_effectiveness_rate вычисляет правильно"""
        # (6 + 2) / 10 = 0.8
        assert metrics.get_effectiveness_rate() == 0.8

    def test_first_try_rate(self, metrics):
        """get_first_try_rate вычисляет правильно"""
        # 6 / 10 = 0.6
        assert metrics.get_first_try_rate() == 0.6

    def test_fallback_rate(self, metrics):
        """get_fallback_rate вычисляет правильно"""
        # 2 / 10 = 0.2
        assert metrics.get_fallback_rate() == 0.2

    def test_average_score_gap(self, metrics):
        """get_average_score_gap вычисляет правильно"""
        # Все gaps одинаковые: 0.5 - 0.45 = 0.05
        assert metrics.get_average_score_gap() == pytest.approx(0.05)

    def test_zero_disambiguations(self):
        """Нулевые disambiguations возвращают 0"""
        m = DisambiguationMetrics()
        assert m.get_effectiveness_rate() == 0.0
        assert m.get_first_try_rate() == 0.0
        assert m.get_fallback_rate() == 0.0
        assert m.get_average_score_gap() == 0.0


class TestDisambiguationMetricsOutput:
    """Тесты вывода метрик"""

    @pytest.fixture
    def metrics(self):
        m = DisambiguationMetrics()
        m.record_disambiguation(["a", "b"], {"a": 0.5, "b": 0.45})
        m.record_resolution("a", 1, True)
        return m

    def test_to_log_dict(self, metrics):
        """to_log_dict возвращает словарь"""
        result = metrics.to_log_dict()
        assert isinstance(result, dict)
        assert "total_disambiguations" in result
        assert "effectiveness_rate" in result

    def test_get_summary(self, metrics):
        """get_summary возвращает полный словарь"""
        result = metrics.get_summary()
        assert isinstance(result, dict)
        assert "total_disambiguations" in result
        assert "resolved_on_first_try" in result
        assert "disambiguation_by_intent" in result


# =============================================================================
# StateMachine Disambiguation Tests
# =============================================================================

class TestStateMachineDisambiguationInit:
    """Тесты инициализации disambiguation в StateMachine"""

    def test_init_disambiguation_state(self):
        """StateMachine инициализирует disambiguation state"""
        sm = StateMachine()
        assert sm.in_disambiguation is False
        assert sm.disambiguation_context is None
        assert sm.pre_disambiguation_state is None
        assert sm.turns_since_last_disambiguation == 999

    def test_reset_clears_disambiguation(self):
        """reset очищает disambiguation state"""
        sm = StateMachine()
        sm.in_disambiguation = True
        sm.disambiguation_context = {"test": "data"}
        sm.turns_since_last_disambiguation = 5

        sm.reset()

        assert sm.in_disambiguation is False
        assert sm.disambiguation_context is None
        assert sm.turns_since_last_disambiguation == 999


class TestStateMachineDisambiguationMethods:
    """Тесты методов disambiguation в StateMachine"""

    @pytest.fixture
    def sm(self):
        return StateMachine()

    def test_increment_turn(self, sm):
        """increment_turn увеличивает счётчик"""
        sm.turns_since_last_disambiguation = 5
        sm.increment_turn()
        assert sm.turns_since_last_disambiguation == 6

    def test_increment_turn_max_value(self, sm):
        """increment_turn не увеличивает при 999"""
        sm.turns_since_last_disambiguation = 999
        sm.increment_turn()
        assert sm.turns_since_last_disambiguation == 999

    def test_enter_disambiguation(self, sm):
        """enter_disambiguation устанавливает state"""
        options = [{"intent": "a"}, {"intent": "b"}]
        sm.enter_disambiguation(options, {"key": "value"})

        assert sm.in_disambiguation is True
        assert sm.pre_disambiguation_state == "greeting"
        assert sm.disambiguation_context["options"] == options
        assert sm.disambiguation_context["extracted_data"] == {"key": "value"}
        assert sm.disambiguation_context["attempt"] == 1

    def test_resolve_disambiguation(self, sm):
        """resolve_disambiguation возвращает state и intent"""
        sm.enter_disambiguation([{"intent": "a"}])
        state, intent = sm.resolve_disambiguation("a")

        assert state == "greeting"
        assert intent == "a"
        assert sm.in_disambiguation is False
        assert sm.turns_since_last_disambiguation == 0

    def test_exit_disambiguation(self, sm):
        """exit_disambiguation очищает state"""
        sm.enter_disambiguation([{"intent": "a"}])
        sm.exit_disambiguation()

        assert sm.in_disambiguation is False
        assert sm.disambiguation_context is None
        assert sm.turns_since_last_disambiguation == 0


class TestStateMachineGetContext:
    """Тесты get_context в StateMachine"""

    @pytest.fixture
    def sm(self):
        return StateMachine()

    def test_get_context_basic(self, sm):
        """get_context возвращает базовый контекст"""
        context = sm.get_context()
        assert "state" in context
        assert "turns_since_last_disambiguation" in context

    def test_get_context_with_disambiguation(self, sm):
        """get_context включает in_disambiguation"""
        sm.enter_disambiguation([{"intent": "a"}])
        context = sm.get_context()
        assert context.get("in_disambiguation") is True

    def test_get_context_without_disambiguation(self, sm):
        """get_context без in_disambiguation когда не активен"""
        context = sm.get_context()
        assert "in_disambiguation" not in context


# =============================================================================
# Intent Labels Tests
# =============================================================================

class TestIntentLabels:
    """Тесты для INTENT_LABELS и get_label"""

    def test_intent_labels_is_dict(self):
        """INTENT_LABELS это словарь"""
        assert isinstance(INTENT_LABELS, dict)

    def test_intent_labels_has_values(self):
        """INTENT_LABELS содержит значения"""
        assert len(INTENT_LABELS) > 0

    def test_intent_labels_common_intents(self):
        """INTENT_LABELS содержит основные интенты"""
        assert "price_question" in INTENT_LABELS
        assert "question_features" in INTENT_LABELS
        assert "agreement" in INTENT_LABELS
        assert "rejection" in INTENT_LABELS
        assert "greeting" in INTENT_LABELS

    def test_get_label_known_intent(self):
        """get_label возвращает label для известного интента"""
        label = get_label("price_question")
        assert label == "Узнать стоимость"

    def test_get_label_unknown_intent(self):
        """get_label возвращает intent для неизвестного"""
        label = get_label("unknown_xyz_123")
        assert label == "unknown_xyz_123"


# =============================================================================
# Feature Flags Tests
# =============================================================================

class TestIntentDisambiguationFlag:
    """Тесты для intent_disambiguation flag"""

    def test_flag_in_defaults(self):
        """intent_disambiguation в DEFAULTS"""
        assert "intent_disambiguation" in FeatureFlags.DEFAULTS

    def test_flag_default_false(self):
        """intent_disambiguation по умолчанию False"""
        assert FeatureFlags.DEFAULTS["intent_disambiguation"] is False

    def test_flag_property_exists(self):
        """Property intent_disambiguation существует"""
        ff = FeatureFlags()
        assert hasattr(ff, "intent_disambiguation")

    def test_flag_property_returns_bool(self):
        """Property intent_disambiguation возвращает bool"""
        ff = FeatureFlags()
        assert isinstance(ff.intent_disambiguation, bool)

    def test_flag_override_works(self):
        """Override для intent_disambiguation работает"""
        ff = FeatureFlags()
        ff.set_override("intent_disambiguation", True)
        assert ff.intent_disambiguation is True
        ff.clear_override("intent_disambiguation")


# =============================================================================
# Config Tests
# =============================================================================

class TestDisambiguationConfig:
    """Тесты для DISAMBIGUATION_CONFIG"""

    def test_config_exists(self):
        """DISAMBIGUATION_CONFIG существует"""
        assert DISAMBIGUATION_CONFIG is not None
        assert isinstance(DISAMBIGUATION_CONFIG, dict)

    def test_config_min_confidence_threshold(self):
        """min_confidence_threshold настроен"""
        assert "min_confidence_threshold" in DISAMBIGUATION_CONFIG
        assert isinstance(DISAMBIGUATION_CONFIG["min_confidence_threshold"], (int, float))

    def test_config_max_score_gap(self):
        """max_score_gap настроен"""
        assert "max_score_gap" in DISAMBIGUATION_CONFIG
        assert isinstance(DISAMBIGUATION_CONFIG["max_score_gap"], (int, float))

    def test_config_max_options(self):
        """max_options настроен"""
        assert "max_options" in DISAMBIGUATION_CONFIG
        assert isinstance(DISAMBIGUATION_CONFIG["max_options"], int)

    def test_config_excluded_intents(self):
        """excluded_intents настроен"""
        assert "excluded_intents" in DISAMBIGUATION_CONFIG
        assert isinstance(DISAMBIGUATION_CONFIG["excluded_intents"], list)
        assert "unclear" in DISAMBIGUATION_CONFIG["excluded_intents"]

    def test_config_bypass_intents(self):
        """bypass_disambiguation_intents настроен"""
        assert "bypass_disambiguation_intents" in DISAMBIGUATION_CONFIG
        assert isinstance(DISAMBIGUATION_CONFIG["bypass_disambiguation_intents"], list)
        assert "rejection" in DISAMBIGUATION_CONFIG["bypass_disambiguation_intents"]

    def test_config_cooldown_turns(self):
        """cooldown_turns настроен"""
        assert "cooldown_turns" in DISAMBIGUATION_CONFIG
        assert isinstance(DISAMBIGUATION_CONFIG["cooldown_turns"], int)


# =============================================================================
# Edge Cases Tests
# =============================================================================

class TestEdgeCases:
    """Тесты краевых случаев"""

    def test_analyzer_with_custom_config(self):
        """Analyzer с кастомным config"""
        custom_config = {"root_match_weight": 2.0}
        analyzer = DisambiguationAnalyzer(config=custom_config)
        assert analyzer.config["root_match_weight"] == 2.0

    def test_ui_empty_options(self):
        """UI с пустыми options"""
        ui = DisambiguationUI()
        result = ui.parse_answer("1", [])
        assert result is None

    def test_metrics_multiple_intents(self):
        """Metrics с множественными интентами"""
        m = DisambiguationMetrics()
        for i in range(5):
            m.record_disambiguation(
                [f"intent_{i}", "common"],
                {f"intent_{i}": 0.5, "common": 0.4}
            )
        assert len(m.disambiguation_by_intent) > 1
        assert m.disambiguation_by_intent.get("common") == 5

    def test_state_machine_disambiguation_context_none(self):
        """StateMachine с None disambiguation_context"""
        sm = StateMachine()
        # Не вызываем enter_disambiguation
        context = sm.get_context()
        assert "in_disambiguation" not in context


# =============================================================================
# Integration Tests for Disambiguation (Stage 3-4)
# =============================================================================

class TestDisambiguationIntegrationBasic:
    """Базовые интеграционные тесты disambiguation"""

    @pytest.fixture
    def mock_llm(self):
        """Мок LLM"""
        from unittest.mock import MagicMock
        llm = MagicMock()
        llm.generate.return_value = "Тестовый ответ"
        return llm

    @pytest.fixture
    def bot(self, mock_llm):
        """SalesBot с включённым disambiguation"""
        from unittest.mock import patch
        from bot import SalesBot
        from feature_flags import flags

        flags.set_override("intent_disambiguation", True)
        flags.set_override("metrics_tracking", True)

        bot = SalesBot(mock_llm)
        # Мокируем generate чтобы избежать инициализации retriever
        bot.generator.generate = lambda action, ctx: "Тестовый ответ от генератора"
        yield bot

        flags.clear_override("intent_disambiguation")
        flags.clear_override("metrics_tracking")

    def test_bot_has_disambiguation_ui(self, bot):
        """Bot имеет disambiguation_ui property"""
        assert hasattr(bot, "disambiguation_ui")
        # Ленивая инициализация - доступ к property
        ui = bot.disambiguation_ui
        assert ui is not None

    def test_bot_has_disambiguation_metrics(self, bot):
        """Bot имеет disambiguation_metrics"""
        assert hasattr(bot, "disambiguation_metrics")
        assert bot.disambiguation_metrics is not None

    def test_bot_reset_clears_disambiguation_metrics(self, bot):
        """reset() сбрасывает disambiguation_metrics"""
        bot.disambiguation_metrics.total_disambiguations = 10
        bot.reset()
        assert bot.disambiguation_metrics.total_disambiguations == 0

    def test_increment_turn_called(self, bot):
        """increment_turn вызывается при process"""
        initial = bot.state_machine.turns_since_last_disambiguation
        bot.process("Привет")
        # Счётчик должен измениться (либо +1, либо остаться 999)
        after = bot.state_machine.turns_since_last_disambiguation
        assert after == initial + 1 or initial == 999


class TestDisambiguationIntegrationFlow:
    """Тесты полного flow disambiguation"""

    @pytest.fixture
    def mock_llm(self):
        from unittest.mock import MagicMock
        llm = MagicMock()
        llm.generate.return_value = "Тестовый ответ"
        return llm

    @pytest.fixture
    def bot(self, mock_llm):
        from bot import SalesBot
        from feature_flags import flags

        flags.set_override("intent_disambiguation", True)
        flags.set_override("metrics_tracking", True)

        bot = SalesBot(mock_llm)
        bot.generator.generate = lambda action, ctx: "Тестовый ответ от генератора"
        yield bot

        flags.clear_override("intent_disambiguation")
        flags.clear_override("metrics_tracking")

    def test_disambiguation_numeric_response(self, bot):
        """Числовой ответ на disambiguation работает"""
        # Входим в режим disambiguation вручную
        options = [
            {"intent": "price_question", "label": "Узнать стоимость"},
            {"intent": "question_features", "label": "Узнать о функциях"}
        ]
        bot.state_machine.enter_disambiguation(options, {})

        # Отвечаем числом
        result = bot.process("1")

        # Должен выйти из disambiguation
        assert not bot.state_machine.in_disambiguation
        # Должен вернуть ответ
        assert "response" in result

    def test_disambiguation_unknown_answer_classifies_directly(self, bot):
        """Непонятный ответ классифицируется напрямую (как свой вариант)"""
        options = [
            {"intent": "price_question", "label": "Узнать стоимость"},
            {"intent": "question_features", "label": "Узнать о функциях"}
        ]
        bot.state_machine.enter_disambiguation(options, {})

        # Отвечаем чем-то непонятным - это теперь "свой вариант"
        result = bot.process("абракадабра")

        # Должен выйти из disambiguation и классифицировать ответ
        assert not bot.state_machine.in_disambiguation
        assert "response" in result

    def test_disambiguation_critical_intent_exits(self, bot):
        """Критический интент выходит из disambiguation"""
        options = [
            {"intent": "price_question", "label": "Узнать стоимость"},
            {"intent": "question_features", "label": "Узнать о функциях"}
        ]
        bot.state_machine.enter_disambiguation(options, {})

        # Предоставляем телефон - критический интент
        result = bot.process("мой телефон 87771234567")

        # Должен выйти из disambiguation
        assert not bot.state_machine.in_disambiguation

    def test_disambiguation_preserves_extracted_data(self, bot):
        """Extracted data сохраняется при disambiguation"""
        options = [
            {"intent": "price_question", "label": "Узнать стоимость"},
            {"intent": "question_features", "label": "Узнать о функциях"}
        ]
        extracted_data = {"company_size": 15}
        bot.state_machine.enter_disambiguation(options, extracted_data)

        # Проверяем что данные сохранены в контексте
        ctx = bot.state_machine.disambiguation_context
        assert ctx["extracted_data"] == extracted_data


class TestDisambiguationIntegrationCooldown:
    """Тесты cooldown disambiguation"""

    @pytest.fixture
    def mock_llm(self):
        from unittest.mock import MagicMock
        llm = MagicMock()
        llm.generate.return_value = "Тестовый ответ"
        return llm

    @pytest.fixture
    def bot(self, mock_llm):
        from bot import SalesBot
        from feature_flags import flags

        flags.set_override("intent_disambiguation", True)
        flags.set_override("metrics_tracking", True)

        bot = SalesBot(mock_llm)
        bot.generator.generate = lambda action, ctx: "Тестовый ответ от генератора"
        yield bot

        flags.clear_override("intent_disambiguation")
        flags.clear_override("metrics_tracking")

    def test_cooldown_resets_after_disambiguation(self, bot):
        """Cooldown сбрасывается после disambiguation"""
        options = [
            {"intent": "price_question", "label": "Узнать стоимость"},
            {"intent": "question_features", "label": "Узнать о функциях"}
        ]
        bot.state_machine.enter_disambiguation(options, {})
        bot.state_machine.resolve_disambiguation("price_question")

        # Cooldown должен быть 0
        assert bot.state_machine.turns_since_last_disambiguation == 0

    def test_cooldown_increments_each_turn(self, bot):
        """Cooldown увеличивается каждый ход"""
        # Сбрасываем через exit_disambiguation
        bot.state_machine.exit_disambiguation()
        assert bot.state_machine.turns_since_last_disambiguation == 0

        # Каждый process увеличивает счётчик
        bot.process("Привет")
        assert bot.state_machine.turns_since_last_disambiguation == 1

        bot.process("Как дела")
        assert bot.state_machine.turns_since_last_disambiguation == 2


class TestDisambiguationIntegrationMetrics:
    """Тесты метрик disambiguation"""

    @pytest.fixture
    def mock_llm(self):
        from unittest.mock import MagicMock
        llm = MagicMock()
        llm.generate.return_value = "Тестовый ответ"
        return llm

    @pytest.fixture
    def bot(self, mock_llm):
        from bot import SalesBot
        from feature_flags import flags

        flags.set_override("intent_disambiguation", True)
        flags.set_override("metrics_tracking", True)

        bot = SalesBot(mock_llm)
        bot.generator.generate = lambda action, ctx: "Тестовый ответ от генератора"
        yield bot

        flags.clear_override("intent_disambiguation")
        flags.clear_override("metrics_tracking")

    def test_get_disambiguation_metrics(self, bot):
        """get_disambiguation_metrics возвращает словарь"""
        result = bot.get_disambiguation_metrics()
        assert isinstance(result, dict)
        assert "total_disambiguations" in result

    def test_disambiguation_metrics_recorded(self, bot):
        """Метрики записываются при disambiguation"""
        options = [
            {"intent": "price_question", "label": "Узнать стоимость"},
            {"intent": "question_features", "label": "Узнать о функциях"}
        ]

        # Инициируем disambiguation через state_machine (как делает Blackboard pipeline)
        bot.state_machine.enter_disambiguation(
            options=options,
            extracted_data={},
        )
        bot.disambiguation_metrics.record_disambiguation(
            options=["price_question", "question_features"],
            scores={"price_question": 0.5, "question_features": 0.48},
        )

        assert bot.disambiguation_metrics.total_disambiguations == 1


class TestHybridClassifierDisambiguation:
    """Тесты интеграции disambiguation в HybridClassifier"""

    @pytest.fixture
    def classifier(self):
        from classifier import HybridClassifier
        return HybridClassifier()

    def test_classifier_has_disambiguation_analyzer(self, classifier):
        """Classifier имеет disambiguation_analyzer property"""
        assert hasattr(classifier, "disambiguation_analyzer")
        # Ленивая инициализация
        analyzer = classifier.disambiguation_analyzer
        assert analyzer is not None

    def test_classifier_respects_flag(self):
        """Classifier уважает feature flag"""
        from classifier import HybridClassifier
        from feature_flags import flags

        # Выключаем флаг
        flags.set_override("intent_disambiguation", False)
        classifier = HybridClassifier()

        result = classifier.classify("интересно", {})

        # Не должно быть disambiguation_needed
        assert result["intent"] != "disambiguation_needed"

        flags.clear_override("intent_disambiguation")

    def test_classifier_returns_disambiguation_fields(self):
        """При disambiguation возвращаются нужные поля"""
        from classifier import HybridClassifier
        from feature_flags import flags

        flags.set_override("intent_disambiguation", True)
        classifier = HybridClassifier()

        # Даём сообщение которое может вызвать disambiguation
        # (если scores достаточно близкие)
        result = classifier.classify("расскажите подробнее", {})

        if result["intent"] == "disambiguation_needed":
            assert "disambiguation_options" in result
            assert "disambiguation_question" in result
            assert "original_scores" in result

        flags.clear_override("intent_disambiguation")


class TestDisambiguationEndToEnd:
    """End-to-end тесты disambiguation"""

    @pytest.fixture
    def mock_llm(self):
        from unittest.mock import MagicMock
        llm = MagicMock()
        llm.generate.return_value = "Тестовый ответ от бота"
        return llm

    @pytest.fixture
    def bot(self, mock_llm):
        from bot import SalesBot
        from feature_flags import flags

        flags.set_override("intent_disambiguation", True)
        flags.set_override("metrics_tracking", True)
        flags.set_override("tone_analysis", False)  # Отключаем для простоты

        bot = SalesBot(mock_llm)
        bot.generator.generate = lambda action, ctx: "Тестовый ответ от генератора"
        yield bot

        flags.clear_all_overrides()

    def test_full_disambiguation_and_resolve(self, bot):
        """Полный цикл: disambiguation → ответ → продолжение"""
        # Вручную входим в disambiguation
        options = [
            {"intent": "price_question", "label": "Узнать стоимость"},
            {"intent": "question_features", "label": "Узнать о функциях"}
        ]
        bot.state_machine.enter_disambiguation(options, {})

        # Пользователь выбирает первый вариант
        result = bot.process("1")

        # Проверяем результат
        assert not bot.state_machine.in_disambiguation
        assert "response" in result
        # Интент должен быть price_question (разрешённый)
        # или результат его обработки

    def test_disambiguation_metrics_summary_after_flow(self, bot):
        """Сводка метрик после flow"""
        options = [
            {"intent": "price_question", "label": "Узнать стоимость"},
            {"intent": "question_features", "label": "Узнать о функциях"}
        ]

        # Инициируем disambiguation через state_machine (как делает Blackboard pipeline)
        bot.state_machine.enter_disambiguation(
            options=options,
            extracted_data={},
        )
        bot.disambiguation_metrics.record_disambiguation(
            options=["price_question", "question_features"],
            scores={"price_question": 0.5, "question_features": 0.48},
        )

        # Разрешаем через process
        result = bot.process("первый")

        # Проверяем метрики
        summary = bot.get_disambiguation_metrics()
        assert summary["total_disambiguations"] == 1
        assert summary["resolved_on_first_try"] == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
