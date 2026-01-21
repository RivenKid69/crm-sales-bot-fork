"""
Тесты для обработки disambiguation (нажатия кнопок) в ClientAgent.

Проверяет:
- Детекцию disambiguation сообщений от бота
- Извлечение вариантов выбора
- Выбор опции на основе персоны
- Генерацию ответа в правильном формате
"""
import pytest
from unittest.mock import MagicMock

from simulator.client_agent import ClientAgent, PERSONA_OPTION_PREFERENCES
from simulator.personas import Persona


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def mock_llm():
    """Mock LLM для тестов."""
    llm = MagicMock()
    llm.generate.return_value = "ок, понял"
    return llm


@pytest.fixture
def happy_path_persona():
    """Идеальный клиент."""
    return Persona(
        name="happy_path",
        description="Заинтересованный клиент",
        max_turns=15,
        objection_probability=0.1,
        preferred_objections=[],
        conversation_starters=["Привет"]
    )


@pytest.fixture
def busy_persona():
    """Занятой клиент."""
    return Persona(
        name="busy",
        description="Очень занятой клиент",
        max_turns=8,
        objection_probability=0.4,
        preferred_objections=["time"],
        conversation_starters=["быстро"]
    )


@pytest.fixture
def price_sensitive_persona():
    """Ценовик."""
    return Persona(
        name="price_sensitive",
        description="Клиент, для которого цена главное",
        max_turns=12,
        objection_probability=0.8,
        preferred_objections=["price"],
        conversation_starters=["сколько стоит?"]
    )


@pytest.fixture
def aggressive_persona():
    """Агрессивный клиент."""
    return Persona(
        name="aggressive",
        description="Грубый и нетерпеливый",
        max_turns=8,
        objection_probability=0.7,
        preferred_objections=["waste_time"],
        conversation_starters=["давайте без воды"]
    )


@pytest.fixture
def skeptic_persona():
    """Скептик."""
    return Persona(
        name="skeptic",
        description="Скептичный клиент",
        max_turns=12,
        objection_probability=0.6,
        preferred_objections=["skepticism"],
        conversation_starters=["не уверен что нужно"]
    )


# =============================================================================
# Test Disambiguation Detection
# =============================================================================

class TestDisambiguationDetection:
    """Тесты детекции disambiguation сообщений."""

    def test_detect_numbered_list(self, mock_llm, happy_path_persona):
        """Детекция нумерованного списка."""
        agent = ClientAgent(mock_llm, happy_path_persona)

        message = """Уточните, пожалуйста:
1. Узнать цену
2. Узнать о функциях
3. Другое
Или напишите ваш вопрос своими словами."""

        assert agent._detect_disambiguation(message) is True

    def test_detect_inline_format(self, mock_llm, happy_path_persona):
        """Детекция inline формата."""
        agent = ClientAgent(mock_llm, happy_path_persona)

        message = "Вы хотите узнать цену или записаться на демо?"
        assert agent._detect_disambiguation(message) is True

    def test_detect_confirm_question(self, mock_llm, happy_path_persona):
        """Детекция уточняющего вопроса."""
        agent = ClientAgent(mock_llm, happy_path_persona)

        message = "Правильно ли я понял — вас интересует цена?"
        assert agent._detect_disambiguation(message) is True

    def test_detect_or_question(self, mock_llm, happy_path_persona):
        """Детекция простого вопроса с 'или'."""
        agent = ClientAgent(mock_llm, happy_path_persona)

        message = "Узнать цену или обсудить функции?"
        assert agent._detect_disambiguation(message) is True

    def test_not_detect_regular_message(self, mock_llm, happy_path_persona):
        """Обычное сообщение не детектится как disambiguation."""
        agent = ClientAgent(mock_llm, happy_path_persona)

        message = "Добрый день! Расскажите про вашу CRM систему."
        assert agent._detect_disambiguation(message) is False

    def test_not_detect_question_without_options(self, mock_llm, happy_path_persona):
        """Вопрос без вариантов не детектится."""
        agent = ClientAgent(mock_llm, happy_path_persona)

        message = "Какой у вас размер команды?"
        assert agent._detect_disambiguation(message) is False


# =============================================================================
# Test Option Extraction
# =============================================================================

class TestOptionExtraction:
    """Тесты извлечения вариантов."""

    def test_extract_numbered_options(self, mock_llm, happy_path_persona):
        """Извлечение нумерованных опций."""
        agent = ClientAgent(mock_llm, happy_path_persona)

        message = """Уточните, пожалуйста:
1. Узнать цену
2. Узнать о функциях
3. Другое
Или напишите ваш вопрос своими словами."""

        options = agent._extract_options(message)

        assert len(options) == 3
        assert "Узнать цену" in options
        assert "Узнать о функциях" in options
        assert "Другое" in options

    def test_extract_inline_options(self, mock_llm, happy_path_persona):
        """Извлечение inline опций."""
        agent = ClientAgent(mock_llm, happy_path_persona)

        message = "Вы хотите узнать цену или записаться на демо?"
        options = agent._extract_options(message)

        assert len(options) == 2
        assert "узнать цену" in options
        assert "записаться на демо" in options

    def test_extract_simple_or_options(self, mock_llm, happy_path_persona):
        """Извлечение простых опций с 'или'."""
        agent = ClientAgent(mock_llm, happy_path_persona)

        message = "Цена или функции?"
        options = agent._extract_options(message)

        assert len(options) == 2

    def test_exclude_instruction_line(self, mock_llm, happy_path_persona):
        """Исключение строки 'напишите своими словами'."""
        agent = ClientAgent(mock_llm, happy_path_persona)

        message = """1. Цена
2. Функции
Или напишите своими словами"""

        options = agent._extract_options(message)

        assert len(options) == 2
        assert "своими словами" not in str(options).lower()


# =============================================================================
# Test Option Choice by Persona
# =============================================================================

class TestOptionChoice:
    """Тесты выбора опции на основе персоны."""

    def test_busy_chooses_first(self, mock_llm, busy_persona):
        """Занятой выбирает первый вариант."""
        agent = ClientAgent(mock_llm, busy_persona)

        options = ["Узнать цену", "Узнать о функциях", "Другое"]
        index, reason = agent._choose_option(options, "")

        assert index == 0
        assert reason == "quick_choice"

    def test_price_sensitive_chooses_price(self, mock_llm, price_sensitive_persona):
        """Ценовик выбирает ценовую опцию."""
        agent = ClientAgent(mock_llm, price_sensitive_persona)

        options = ["Узнать о функциях", "Узнать цену", "Другое"]
        index, reason = agent._choose_option(options, "")

        assert index == 1  # "Узнать цену"
        assert "keyword_match" in reason

    def test_aggressive_chooses_first(self, mock_llm, aggressive_persona):
        """Агрессивный выбирает первый вариант."""
        agent = ClientAgent(mock_llm, aggressive_persona)

        options = ["Вариант 1", "Вариант 2", "Другое"]
        index, reason = agent._choose_option(options, "")

        assert index == 0
        assert reason == "quick_choice"

    def test_default_chooses_first(self, mock_llm, happy_path_persona):
        """По умолчанию выбирается первый вариант."""
        agent = ClientAgent(mock_llm, happy_path_persona)

        options = ["Вариант А", "Вариант Б", "Вариант В"]
        index, reason = agent._choose_option(options, "")

        # happy_path ищет "демо", "функци" - если не находит, берёт первый
        assert index == 0 or "keyword_match" in reason


# =============================================================================
# Test Response Generation
# =============================================================================

class TestResponseGeneration:
    """Тесты генерации ответа."""

    def test_busy_returns_number(self, mock_llm, busy_persona):
        """Занятой возвращает номер."""
        agent = ClientAgent(mock_llm, busy_persona)

        options = ["Цена", "Функции", "Другое"]
        response = agent._generate_disambiguation_response(0, options, "quick_choice")

        assert response == "1"

    def test_response_is_parseable(self, mock_llm, happy_path_persona):
        """Ответ должен быть распознаваем парсером disambiguation."""
        agent = ClientAgent(mock_llm, happy_path_persona)

        options = ["Узнать цену", "Узнать о функциях", "Другое"]

        # Генерируем много ответов и проверяем что все распознаваемы
        valid_patterns = [
            r"^\d$",  # "1", "2", "3"
            r"перв|втор|трет|четв",  # "первое", "второе"
            r"цен|функ|друг",  # ключевые слова
            r"да|ну|хм",  # natural prefixes
            r"говор|давай|рассказ",  # aggressive ignore
        ]

        for _ in range(10):
            response = agent._generate_disambiguation_response(0, options, "default")
            # Должен содержать хотя бы один из паттернов
            import re
            matches_any = any(re.search(p, response.lower()) for p in valid_patterns)
            assert matches_any or response.isdigit(), f"Unexpected response: {response}"


# =============================================================================
# Test Full Flow
# =============================================================================

class TestFullDisambiguationFlow:
    """Интеграционные тесты полного flow."""

    def test_respond_handles_disambiguation(self, mock_llm, busy_persona):
        """respond() правильно обрабатывает disambiguation."""
        agent = ClientAgent(mock_llm, busy_persona)

        message = """Уточните, пожалуйста:
1. Узнать цену
2. Узнать о функциях
3. Другое"""

        response = agent.respond(message)

        # Busy выбирает первый вариант числом
        assert response == "1"

        # LLM не должен был вызываться
        mock_llm.generate.assert_not_called()

    def test_respond_uses_llm_for_regular_message(self, mock_llm, happy_path_persona):
        """respond() использует LLM для обычных сообщений."""
        agent = ClientAgent(mock_llm, happy_path_persona)

        message = "Расскажите про вашу систему."
        agent.respond(message)

        # LLM должен был вызваться
        mock_llm.generate.assert_called_once()

    def test_trace_includes_disambiguation(self, mock_llm, price_sensitive_persona):
        """Trace содержит информацию о disambiguation."""
        agent = ClientAgent(mock_llm, price_sensitive_persona)

        message = """Уточните:
1. Функции
2. Цена
3. Другое"""

        agent.respond(message)
        trace = agent.get_last_trace()

        assert trace is not None
        assert trace.disambiguation_decision.get("detected") is True
        assert trace.disambiguation_decision.get("chosen_index") == 1  # Цена
        assert "keyword_match" in trace.disambiguation_decision.get("reason", "")

    def test_history_records_disambiguation(self, mock_llm, busy_persona):
        """История записывает disambiguation ответы."""
        agent = ClientAgent(mock_llm, busy_persona)

        message = """1. Да
2. Нет"""

        response = agent.respond(message)

        assert len(agent.history) == 1
        assert agent.history[0]["client"] == response
        assert agent.history[0]["bot"] == message


# =============================================================================
# Test Persona Preferences
# =============================================================================

class TestPersonaPreferences:
    """Тесты предпочтений персон."""

    def test_preferences_defined_for_all_personas(self):
        """Все персоны имеют определённые предпочтения."""
        expected_personas = [
            "price_sensitive", "competitor_user", "technical",
            "busy", "aggressive", "happy_path", "skeptic", "tire_kicker"
        ]

        for persona in expected_personas:
            assert persona in PERSONA_OPTION_PREFERENCES

    def test_technical_prefers_api_options(self, mock_llm):
        """Технарь выбирает технические опции."""
        persona = Persona(
            name="technical",
            description="IT директор",
            max_turns=15,
            objection_probability=0.3,
            preferred_objections=["technical"],
            conversation_starters=["Есть API?"]
        )
        agent = ClientAgent(mock_llm, persona)

        options = ["Узнать цену", "API и интеграции", "Другое"]
        index, reason = agent._choose_option(options, "")

        assert index == 1  # "API и интеграции"
        assert "keyword_match" in reason

    def test_competitor_user_prefers_comparison(self, mock_llm):
        """Пользователь конкурента выбирает сравнение."""
        persona = Persona(
            name="competitor_user",
            description="Использует Poster",
            max_turns=12,
            objection_probability=0.5,
            preferred_objections=["competitor"],
            conversation_starters=["у нас Poster"]
        )
        agent = ClientAgent(mock_llm, persona)

        options = ["Узнать цену", "Сравнить с Poster", "Другое"]
        index, reason = agent._choose_option(options, "")

        assert index == 1  # "Сравнить с Poster"
        assert "keyword_match" in reason
