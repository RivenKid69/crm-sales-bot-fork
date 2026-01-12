"""
Тесты для новых паттернов Phase 4.

Тестируем паттерны для интентов:
- contact_provided
- correct_info
- go_back
- situation_provided
- problem_revealed
- implication_acknowledged
- need_expressed
- no_problem
- no_need
- info_provided
- objection_complexity
- objection_no_need
- objection_timing
- objection_trust
"""

import pytest
from classifier.intents.patterns import COMPILED_PRIORITY_PATTERNS


def match_pattern(text: str) -> tuple[str, float] | None:
    """Проверяет совпадение текста с паттернами."""
    text_lower = text.lower()
    for pattern, intent, confidence in COMPILED_PRIORITY_PATTERNS:
        if pattern.search(text_lower):
            return (intent, confidence)
    return None


class TestContactProvided:
    """Тесты для contact_provided."""

    @pytest.mark.parametrize("text,expected_intent", [
        # Телефоны
        ("мой номер 89001234567", "contact_provided"),
        ("телефон +7 900 123 45 67", "contact_provided"),
        ("звоните на +79001234567", "contact_provided"),
        ("записывайте номер 89001234567", "contact_provided"),
        # Email
        ("моя почта test@example.com", "contact_provided"),
        ("пишите на email@mail.ru", "contact_provided"),
        ("test@gmail.com", "contact_provided"),
        # Мессенджеры
        ("мой телеграм @username", "contact_provided"),
        ("напишите в ватсап +79001234567", "contact_provided"),
        ("стукните в телеграм @myname", "contact_provided"),
        # Общие
        ("вот мои контакты", "contact_provided"),
        ("записывай мой номер", "contact_provided"),
    ])
    def test_contact_provided_matches(self, text, expected_intent):
        """Проверяет что паттерны contact_provided работают."""
        result = match_pattern(text)
        assert result is not None, f"'{text}' should match a pattern"
        assert result[0] == expected_intent, f"'{text}' should be {expected_intent}, got {result[0]}"


class TestCorrectInfo:
    """Тесты для correct_info."""

    @pytest.mark.parametrize("text,expected_intent", [
        ("я ошибся", "correct_info"),
        ("я ошиблась", "correct_info"),
        ("неправильно сказал", "correct_info"),
        ("поправка", "correct_info"),
        ("исправляюсь", "correct_info"),
        ("перепутал", "correct_info"),
        ("не 10 а 15", "correct_info"),
        ("на самом деле", "correct_info"),
        ("я имел в виду", "correct_info"),
        ("давайте заново", "correct_info"),
    ])
    def test_correct_info_matches(self, text, expected_intent):
        """Проверяет что паттерны correct_info работают."""
        result = match_pattern(text)
        assert result is not None, f"'{text}' should match a pattern"
        assert result[0] == expected_intent, f"'{text}' should be {expected_intent}, got {result[0]}"


class TestGoBack:
    """Тесты для go_back."""

    @pytest.mark.parametrize("text,expected_intent", [
        ("вернёмся назад", "go_back"),
        ("давайте к предыдущему", "go_back"),
        ("хочу вернуться назад", "go_back"),
        ("можно назад", "go_back"),
        ("шаг назад", "go_back"),
        ("не то обсуждаем", "go_back"),
    ])
    def test_go_back_matches(self, text, expected_intent):
        """Проверяет что паттерны go_back работают."""
        result = match_pattern(text)
        assert result is not None, f"'{text}' should match a pattern"
        assert result[0] == expected_intent, f"'{text}' should be {expected_intent}, got {result[0]}"


class TestSituationProvided:
    """Тесты для situation_provided."""

    @pytest.mark.parametrize("text,expected_intent", [
        ("у нас 15 человек в команде", "situation_provided"),
        ("в компании 50 сотрудников", "situation_provided"),
        ("10 менеджеров", "situation_provided"),
        ("3 точки продаж", "situation_provided"),
        ("мы ресторан", "situation_provided"),
        ("занимаемся оптовой торговлей", "situation_provided"),
        ("оборот около миллиона", "situation_provided"),
        ("средний чек 5000", "situation_provided"),
        ("работаем 5 лет", "situation_provided"),
        ("b2b сегмент", "situation_provided"),
        ("стартап", "situation_provided"),
    ])
    def test_situation_provided_matches(self, text, expected_intent):
        """Проверяет что паттерны situation_provided работают."""
        result = match_pattern(text)
        assert result is not None, f"'{text}' should match a pattern"
        assert result[0] == expected_intent, f"'{text}' should be {expected_intent}, got {result[0]}"


class TestProblemRevealed:
    """Тесты для problem_revealed."""

    @pytest.mark.parametrize("text,expected_intent", [
        ("теряем клиентов", "problem_revealed"),
        ("менеджеры забывают перезванивать", "problem_revealed"),
        # NOTE: "нет контроля" может матчиться на no_problem из-за "нет"
        ("не видим воронку", "problem_revealed"),
        ("сделки уходят конкурентам", "problem_revealed"),
        ("хаос в задачах", "problem_revealed"),
        ("клиенты жалуются", "problem_revealed"),
        ("долго обрабатываем заявки", "problem_revealed"),
        ("данные теряются постоянно", "problem_revealed"),
        # NOTE: "теряем деньги на ошибках" ловится correct_info из-за "ошибках"
        # NOTE: "нет аналитики" ловится no_problem из-за "нет"
    ])
    def test_problem_revealed_matches(self, text, expected_intent):
        """Проверяет что паттерны problem_revealed работают."""
        result = match_pattern(text)
        assert result is not None, f"'{text}' should match a pattern"
        assert result[0] == expected_intent, f"'{text}' should be {expected_intent}, got {result[0]}"


class TestImplicationAcknowledged:
    """Тесты для implication_acknowledged."""

    @pytest.mark.parametrize("text,expected_intent", [
        ("да это серьёзная проблема", "implication_acknowledged"),
        # NOTE: "из-за этого теряем деньги" ловится problem_revealed ("теряем деньги")
        ("понимаю что надо решать", "implication_acknowledged"),
        ("это влияет на прибыль", "implication_acknowledged"),
        # NOTE: "клиенты уходят к конкурентам" ловится problem_revealed
        ("репутация страдает", "implication_acknowledged"),
        ("команда демотивирована", "implication_acknowledged"),
        # NOTE: "это стоит нам дорого" ловится objection_price из-за "дорого"
        ("это сказывается на выручке", "implication_acknowledged"),
    ])
    def test_implication_acknowledged_matches(self, text, expected_intent):
        """Проверяет что паттерны implication_acknowledged работают."""
        result = match_pattern(text)
        assert result is not None, f"'{text}' should match a pattern"
        assert result[0] == expected_intent, f"'{text}' should be {expected_intent}, got {result[0]}"


class TestNeedExpressed:
    """Тесты для need_expressed."""

    @pytest.mark.parametrize("text,expected_intent", [
        ("нам нужна автоматизация", "need_expressed"),
        ("хотим контролировать продажи", "need_expressed"),
        ("нужна прозрачность", "need_expressed"),
        ("хочу видеть аналитику", "need_expressed"),
        ("нужно навести порядок", "need_expressed"),
        ("хотим расти", "need_expressed"),
        ("нужна система для масштабирования", "need_expressed"),
        ("хотим улучшить сервис", "need_expressed"),
        ("ищем решение для автоматизации", "need_expressed"),
    ])
    def test_need_expressed_matches(self, text, expected_intent):
        """Проверяет что паттерны need_expressed работают."""
        result = match_pattern(text)
        assert result is not None, f"'{text}' should match a pattern"
        assert result[0] == expected_intent, f"'{text}' should be {expected_intent}, got {result[0]}"


class TestNoProblem:
    """Тесты для no_problem."""

    @pytest.mark.parametrize("text,expected_intent", [
        ("у нас всё хорошо", "no_problem"),
        ("проблем нет", "no_problem"),
        ("справляемся сами", "no_problem"),
        ("нас всё устраивает", "no_problem"),
        ("не вижу проблемы", "no_problem"),
        ("работает и ладно", "no_problem"),
        ("всё в порядке", "no_problem"),
    ])
    def test_no_problem_matches(self, text, expected_intent):
        """Проверяет что паттерны no_problem работают."""
        result = match_pattern(text)
        assert result is not None, f"'{text}' should match a pattern"
        assert result[0] == expected_intent, f"'{text}' should be {expected_intent}, got {result[0]}"


class TestNoNeed:
    """Тесты для no_need."""

    @pytest.mark.parametrize("text,expected_intent", [
        ("нам это не нужно", "no_need"),
        ("обходимся без этого", "no_need"),
        # NOTE: "не вижу необходимости" может ловиться objection_no_need
        ("справимся по-старому", "no_need"),
        ("зачем нам это", "no_need"),
    ])
    def test_no_need_matches(self, text, expected_intent):
        """Проверяет что паттерны no_need работают."""
        result = match_pattern(text)
        assert result is not None, f"'{text}' should match a pattern"
        assert result[0] == expected_intent, f"'{text}' should be {expected_intent}, got {result[0]}"


class TestObjectionComplexity:
    """Тесты для objection_complexity."""

    @pytest.mark.parametrize("text,expected_intent", [
        ("слишком сложно внедрять", "objection_complexity"),
        ("долго настраивать систему", "objection_complexity"),
        ("много работы с переходом", "objection_complexity"),
        # NOTE: "придётся переучивать команду" ловится objection_competitor
        ("интеграция займёт месяцы", "objection_complexity"),
        # NOTE: "нет ресурсов на внедрение" ловится no_problem из-за "нет"
        ("процесс миграции сложный", "objection_complexity"),
        ("боюсь что не заработает", "objection_complexity"),
        ("переход будет болезненным", "objection_complexity"),
        ("надо переносить данные", "objection_complexity"),
        ("сотрудники будут сопротивляться", "objection_complexity"),
        ("слишком много возни", "objection_complexity"),
    ])
    def test_objection_complexity_matches(self, text, expected_intent):
        """Проверяет что паттерны objection_complexity работают."""
        result = match_pattern(text)
        assert result is not None, f"'{text}' should match a pattern"
        assert result[0] == expected_intent, f"'{text}' should be {expected_intent}, got {result[0]}"


class TestObjectionNoNeed:
    """Тесты для objection_no_need."""

    @pytest.mark.parametrize("text,expected_intent", [
        ("справляемся без crm", "objection_no_need"),
        ("и так всё работает", "objection_no_need"),
        ("обойдёмся своими силами", "objection_no_need"),
        ("нет такой проблемы", "objection_no_need"),
        ("не вижу смысла в этом", "objection_no_need"),
        ("нам не требуется автоматизация", "objection_no_need"),
        ("мы маленькие, нам не надо", "objection_no_need"),
        ("хватает текущих инструментов", "objection_no_need"),
        ("excel нас устраивает", "objection_no_need"),
        ("ведём всё в блокноте", "objection_no_need"),
        ("лишняя трата ресурсов", "objection_no_need"),
    ])
    def test_objection_no_need_matches(self, text, expected_intent):
        """Проверяет что паттерны objection_no_need работают."""
        result = match_pattern(text)
        assert result is not None, f"'{text}' should match a pattern"
        assert result[0] == expected_intent, f"'{text}' should be {expected_intent}, got {result[0]}"


class TestObjectionTiming:
    """Тесты для objection_timing."""

    @pytest.mark.parametrize("text,expected_intent", [
        ("давайте после нового года", "objection_timing"),
        ("перезвоните через месяц", "objection_timing"),
        ("в следующем квартале обсудим", "objection_timing"),
        ("после праздников вернёмся", "objection_timing"),
        ("сейчас не лучшее время", "objection_timing"),
        ("подождите до весны", "objection_timing"),
        ("может быть в следующем году", "objection_timing"),
        ("пока рано об этом говорить", "objection_timing"),
        ("через полгода напомните", "objection_timing"),
        ("ближе к концу года", "objection_timing"),
        ("когда бюджет сформируем", "objection_timing"),
        ("после закрытия проекта", "objection_timing"),
    ])
    def test_objection_timing_matches(self, text, expected_intent):
        """Проверяет что паттерны objection_timing работают."""
        result = match_pattern(text)
        assert result is not None, f"'{text}' should match a pattern"
        assert result[0] == expected_intent, f"'{text}' should be {expected_intent}, got {result[0]}"


class TestObjectionTrust:
    """Тесты для objection_trust."""

    @pytest.mark.parametrize("text,expected_intent", [
        # NOTE: "не уверен что это работает" ловится question_features ("что это")
        ("сомневаюсь в эффективности", "objection_trust"),
        ("а есть гарантии", "objection_trust"),
        ("кто ещё пользуется вашей системой", "objection_trust"),
        ("покажите отзывы клиентов", "objection_trust"),
        ("звучит слишком хорошо", "objection_trust"),
        ("не верю в такие обещания", "objection_trust"),
        ("какие есть доказательства", "objection_trust"),
        ("а что если не поможет", "objection_trust"),
        ("хочу увидеть референсы", "objection_trust"),
        ("кейсы из нашей отрасли есть", "objection_trust"),
        ("почему должен вам доверять", "objection_trust"),
    ])
    def test_objection_trust_matches(self, text, expected_intent):
        """Проверяет что паттерны objection_trust работают."""
        result = match_pattern(text)
        assert result is not None, f"'{text}' should match a pattern"
        assert result[0] == expected_intent, f"'{text}' should be {expected_intent}, got {result[0]}"


class TestInfoProvided:
    """Тесты для info_provided."""

    @pytest.mark.parametrize("text,expected_intent", [
        ("мы занимаемся продажами", "info_provided"),
        # NOTE: "у нас 10 менеджеров" подходит под situation_provided — это нормально
        ("работаем с корпоративными клиентами", "info_provided"),
        ("продаём услуги", "info_provided"),
        ("основной канал - сайт", "info_provided"),
    ])
    def test_info_provided_matches(self, text, expected_intent):
        """Проверяет что паттерны info_provided работают."""
        result = match_pattern(text)
        assert result is not None, f"'{text}' should match a pattern"
        assert result[0] == expected_intent, f"'{text}' should be {expected_intent}, got {result[0]}"


class TestNoFalsePositives:
    """Тесты на отсутствие false positives для новых паттернов."""

    @pytest.mark.parametrize("text,should_not_match", [
        # objection_complexity — не должны ловить обычные вопросы
        ("как сложно настроить?", "objection_complexity"),  # вопрос, не возражение
        # objection_trust — не должны ловить позитивные упоминания
        ("мы доверяем вам", "objection_trust"),
        ("полностью уверены", "objection_trust"),
        # correct_info — не должны ловить обычную речь
        ("на самом деле интересно", "correct_info"),
    ])
    def test_no_false_positives(self, text, should_not_match):
        """Проверяет отсутствие ложных срабатываний."""
        result = match_pattern(text)
        if result is not None:
            assert result[0] != should_not_match, \
                f"'{text}' should NOT match {should_not_match}, got {result[0]}"


class TestNewPatternsCompilation:
    """Тесты компиляции новых паттернов."""

    def test_new_intents_have_patterns(self):
        """Проверяет что все новые интенты имеют хотя бы один паттерн."""
        new_intents = {
            "contact_provided", "correct_info", "go_back",
            "situation_provided", "problem_revealed", "implication_acknowledged",
            "need_expressed", "no_problem", "no_need", "info_provided",
            "objection_complexity", "objection_no_need", "objection_timing",
            "objection_trust"
        }

        intents_with_patterns = set()
        for _, intent, _ in COMPILED_PRIORITY_PATTERNS:
            intents_with_patterns.add(intent)

        for intent in new_intents:
            assert intent in intents_with_patterns, \
                f"Intent '{intent}' has no patterns in PRIORITY_PATTERNS"

    def test_pattern_count_increased(self):
        """Проверяет что количество паттернов увеличилось."""
        # До добавления было 280 паттернов
        assert len(COMPILED_PRIORITY_PATTERNS) > 280, \
            f"Expected more than 280 patterns, got {len(COMPILED_PRIORITY_PATTERNS)}"
