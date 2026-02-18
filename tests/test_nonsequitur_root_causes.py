"""
Диагностические тесты для нон-секвитуров из симуляции.

Три корневых случая:
  SIM #11 Turn 4 — "не уверен, что стоит тратить время" → answer_with_pricing
  SIM #4  Turn 5 — казахский вопрос после серии прайс-вопросов → answer_with_pricing
  SIM #28 Turn 1 — "Что продаётся лучше всего за последний месяц?" → compare_with_competitor

Каждый класс тестов воспроизводит конкретную точку отказа в цепи:
  secondary_intent_detection → PriceQuestionSource.should_contribute → action selection
"""

import pytest
from unittest.mock import MagicMock, patch


# =============================================================================
# SIM #11 ROOT CAUSE: Омоним "стоит" в keywords для price_question
# =============================================================================

class TestStoit_Homonym_False_Price_Detection:
    """
    "стоит" в русском — омоним:
      - "сколько стоит?" → PRICE (правильно)
      - "стоит ли это делать?" / "не стоит тратить время" → VALUE/DOUBT (ложное срабатывание)

    secondary_intent_detection.py включает "стоит" в frozenset keywords для price_question.
    Это вызывает ложный secondary intent → PriceQuestionSource HIGH priority override.
    """

    def _detect_secondary(self, text: str) -> list[str]:
        """Запускает secondary_intent_detection на тексте и возвращает список secondary intents.

        Зеркалит логику реального слоя (_do_refine):
          1. keyword_match = bool(words & pattern.keywords)
          2. Если keywords пустой (frozenset()) — паттерны всегда запускаются
          3. Если keyword_match ИЛИ keywords пустой — проверяем regex-паттерны
        """
        import re
        from src.classifier.secondary_intent_detection import (
            DEFAULT_SECONDARY_INTENT_PATTERNS,
        )
        text_lower = text.lower()
        words = set(re.sub(r'[^\w\s]', ' ', text_lower).split())
        detected = []
        for intent_name, pattern in DEFAULT_SECONDARY_INTENT_PATTERNS.items():
            keyword_match = bool(words & pattern.keywords)
            run_patterns = keyword_match or pattern.keywords == frozenset()
            if run_patterns:
                for p in pattern.patterns:
                    if re.search(p, text_lower, re.IGNORECASE):
                        detected.append(intent_name)
                        break
            elif keyword_match:
                # keyword-only match (no patterns to confirm)
                detected.append(intent_name)
        return detected

    # --- PRICE ложные срабатывания (должны НЕ содержать price_question) ---

    def test_stoit_doubt_no_false_price(self):
        """'не уверен, что стоит тратить время' — сомнение, не вопрос о цене."""
        msg = "не уверен, что стоит тратить время на это"
        detected = self._detect_secondary(msg)
        assert "price_question" not in detected, (
            f"ЛОЖНОЕ СРАБАТЫВАНИЕ: 'стоит' в смысле 'worth it' распознан как price_question. "
            f"Detected: {detected}"
        )

    def test_stoit_risk_no_false_price(self):
        """'стоит ли рисковать' — оценка риска, не вопрос о цене."""
        msg = "стоит ли рисковать и переходить на новую систему?"
        detected = self._detect_secondary(msg)
        assert "price_question" not in detected, (
            f"'стоит ли' должен классифицироваться как objection_risk, не price_question. "
            f"Detected: {detected}"
        )

    def test_stoit_worth_effort_no_false_price(self):
        """'стоит ли усилий' — оценка, не цена."""
        msg = "вообще стоит ли этим заниматься?"
        detected = self._detect_secondary(msg)
        assert "price_question" not in detected, (
            f"'стоит ли' (is it worth it) != price_question. Detected: {detected}"
        )

    # --- РЕАЛЬНЫЕ прайс-вопросы должны по-прежнему работать ---

    def test_skolko_stoit_is_price(self):
        """'сколько стоит' — настоящий вопрос о цене, должен детектироваться."""
        msg = "сколько стоит ваш продукт?"
        detected = self._detect_secondary(msg)
        assert "price_question" in detected, (
            f"'сколько стоит' должен быть price_question. Detected: {detected}"
        )

    def test_stoimost_is_price(self):
        """'стоимость' — тоже должен детектироваться."""
        msg = "какая стоимость подключения?"
        detected = self._detect_secondary(msg)
        assert "price_question" in detected, (
            f"'стоимость' должен быть price_question. Detected: {detected}"
        )

    # --- Полная цепь нон-секвитура SIM #11 Turn 4 ---

    def test_sim11_full_chain_trust_objection_triggers_price_action(self):
        """
        Воспроизводит полную цепь нон-секвитура из SIM #11 Turn 4:

        Клиент: "вручную в основном. а это точно работает? не уверен, что стоит тратить время на это"
        Primary intent: question_features (классификатор прав)
        Secondary: price_question (ЛОЖНОЕ — через keyword "стоит")
        PriceQuestionSource: fires HIGH priority → action=answer_with_pricing
        Результат: бот выдаёт таблицу тарифов вместо ответа на возражение доверия
        """
        from src.classifier.secondary_intent_detection import (
            DEFAULT_SECONDARY_INTENT_PATTERNS,
        )

        msg = "вручную в основном. а это точно работает? не уверен, что стоит тратить время на это"
        text_lower = msg.lower()

        price_pattern = DEFAULT_SECONDARY_INTENT_PATTERNS.get("price_question")
        assert price_pattern is not None, "price_question pattern должен существовать"

        # Проверяем: какой keyword триггерит ложное срабатывание?
        triggering_keywords = [kw for kw in price_pattern.keywords if kw in text_lower]

        # Если тест ПАДАЕТ — это подтверждает баг
        assert not triggering_keywords, (
            f"КОРЕНЬ НАРУШЕНИЯ НАЙДЕН: keyword(s) {triggering_keywords!r} из price_question "
            f"паттерна совпали с текстом возражения о доверии.\n"
            f"Слово 'стоит' в смысле 'стоит ли/worth it' ложно детектируется как вопрос о ЦЕНЕ.\n"
            f"Цепь: keyword match → secondary_intent=price_question → "
            f"PriceQuestionSource.should_contribute()=True → "
            f"propose(answer_with_pricing, priority=HIGH) → "
            f"AutonomousDecisionSource(NORMAL) вытеснен → action=answer_with_pricing → "
            f"Generator получает шаблон '=== ТАРИФЫ WIPON ===' → dumps pricing table.\n"
            f"Полное сообщение: '{msg}'"
        )


# =============================================================================
# SIM #4 ROOT CAUSE: repeated_question переносится через ходы
# =============================================================================

class TestRepeatedQuestion_Stale_Carryover:
    """
    PriceQuestionSource.should_contribute() имеет 3 проверки:
      1. Primary intent
      2. Secondary intents
      3. context_envelope.repeated_question (historical fallback)

    Проверка #3 вызывает нон-секвитур: если в предыдущих ходах клиент задавал прайс-вопросы,
    repeated_question=price_question остаётся в envelope. Когда клиент задаёт ДРУГОЙ вопрос
    (напр., на казахском), PriceQuestionSource.should_contribute()=True через check #3,
    и бот снова выдаёт прайс.
    """

    def _make_blackboard(self, primary_intent: str, secondary_intents: list,
                         repeated_question: str | None) -> MagicMock:
        """Создаёт мок blackboard с заданными параметрами."""
        bb = MagicMock()
        bb.current_intent = primary_intent

        # context envelope
        envelope = MagicMock()
        envelope.secondary_intents = secondary_intents
        envelope.repeated_question = repeated_question

        ctx = MagicMock()
        ctx.current_intent = primary_intent
        ctx.context_envelope = envelope
        bb.get_context.return_value = ctx

        return bb

    def test_repeated_question_price_triggers_for_non_price_primary(self):
        """
        Воспроизводит SIM #4 Turn 5:
        Primary intent = question_features (казахский вопрос)
        Secondary intents = [] (нет price ключевых слов в казахском)
        repeated_question = price_question (из предыдущих ходов)

        Ожидаемый результат: PriceQuestionSource.should_contribute() = True (через check #3)
        Это НЕПРАВИЛЬНОЕ поведение — repeated_question из прошлого не должен форсировать прайс-ответ
        на качественно другой вопрос.
        """
        from src.blackboard.sources.price_question import PriceQuestionSource

        source = PriceQuestionSource()
        bb = self._make_blackboard(
            primary_intent="question_features",   # казахский вопрос
            secondary_intents=[],                  # нет price сигналов
            repeated_question="price_question",    # устаревший из предыдущих ходов
        )

        result = source.should_contribute(bb)

        # Этот assert ПРОВАЛИТСЯ если баг существует (что и ожидается)
        assert not result, (
            f"КОРЕНЬ НАРУШЕНИЯ НАЙДЕН: PriceQuestionSource.should_contribute()=True "
            f"несмотря на то что:\n"
            f"  primary_intent='question_features' (не прайс)\n"
            f"  secondary_intents=[] (нет прайс-сигналов)\n"
            f"  repeated_question='price_question' (УСТАРЕВШИЙ из предыдущих ходов)\n\n"
            f"Check #3 в should_contribute() использует repeated_question как fallback "
            f"даже когда текущий вопрос (казахский) вообще не связан с ценой.\n"
            f"Цепь SIM #4 Turn 5: "
            f"'ок. Есепті қалай оңай жүргізуге болады?' → question_features primary → "
            f"check3(repeated_question=price_question) → HIGH priority → answer_with_pricing."
        )

    def test_non_price_message_no_repeated_price_not_triggered(self):
        """Без repeated_question=price_question — PriceQuestionSource не срабатывает."""
        from src.blackboard.sources.price_question import PriceQuestionSource

        source = PriceQuestionSource()
        bb = self._make_blackboard(
            primary_intent="question_features",
            secondary_intents=[],
            repeated_question=None,
        )

        result = source.should_contribute(bb)
        assert not result, "Без price signals PriceQuestionSource не должен срабатывать"

    def test_genuine_repeated_price_question_is_valid(self):
        """
        Легитимный сценарий: клиент настойчиво переспрашивает цену.
        repeated_question=price_question + primary=unclear → should fire.
        """
        from src.blackboard.sources.price_question import PriceQuestionSource

        source = PriceQuestionSource()
        bb = self._make_blackboard(
            primary_intent="unclear",
            secondary_intents=[],
            repeated_question="price_question",
        )

        # В этом случае repeated_question ДОПУСТИМ — клиент реально переспрашивает цену
        # Этот тест документирует что функция работает, но нужна контекстная проверка
        result = source.should_contribute(bb)
        # Не assertим — просто документируем поведение
        # Тест для будущей дифференциации: "unclear после price" vs "новая тема после price"


# =============================================================================
# SIM #28 ROOT CAUSE: question_sales_mgmt → compare_with_competitor в greeting
# =============================================================================

class TestSalesManagement_Action_Selection:
    """
    SIM #28 Turn 1:
    Клиент: "Что продаётся лучше всего за последний месяц?"
    state=greeting, intent=question_sales_mgmt, action=compare_with_competitor (нон-секвитур)

    Ожидаемый action: answer_with_facts (из taxonomy fallback)
    Реальный action: compare_with_competitor

    Исследуем откуда берётся compare_with_competitor.
    """

    def test_question_sales_mgmt_not_in_fact_question_source_default_intents(self):
        """question_sales_mgmt не должен быть в DEFAULT_FACT_INTENTS — убеждаемся."""
        from src.blackboard.sources.fact_question import FactQuestionSource

        assert "question_sales_mgmt" not in FactQuestionSource.DEFAULT_FACT_INTENTS, (
            "question_sales_mgmt не должен быть в DEFAULT_FACT_INTENTS FactQuestionSource"
        )

    def test_secondary_detection_has_no_comparison_pattern(self):
        """
        secondary_intent_detection.py не имеет паттерна для 'comparison'.
        Если 'продаётся лучше' срабатывает как comparison — это должно быть явно.
        """
        from src.classifier.secondary_intent_detection import DEFAULT_SECONDARY_INTENT_PATTERNS

        # Убеждаемся что нет comparison паттерна
        assert "comparison" not in DEFAULT_SECONDARY_INTENT_PATTERNS, (
            "Паттерна comparison нет в secondary_intent_detection — "
            "значит compare_with_competitor не может прийти через этот путь"
        )

    def test_prodaetsya_luchshe_secondary_intents(self):
        """
        'Что продаётся лучше всего за последний месяц?' — проверяем все secondary intents.
        Определяем какой путь реально триггерит compare_with_competitor.
        """
        from src.classifier.secondary_intent_detection import DEFAULT_SECONDARY_INTENT_PATTERNS

        msg = "Что продаётся лучше всего за последний месяц?"
        text_lower = msg.lower()

        detected = []
        triggering_keywords = {}
        for intent_name, pattern in DEFAULT_SECONDARY_INTENT_PATTERNS.items():
            for kw in pattern.keywords:
                if kw in text_lower:
                    detected.append(intent_name)
                    triggering_keywords[intent_name] = kw
                    break

        # Документируем что детектируется
        # Если compare_with_competitor-связанный интент (comparison) в detected — нашли путь
        assert "price_question" not in detected, (
            f"'продаётся лучше' не должен содержать ценовых сигналов. "
            f"Detected: {detected}, keywords: {triggering_keywords}"
        )

    def test_taxonomy_fallback_for_question_sales_mgmt_is_answer_with_facts(self):
        """
        По taxonomy (constants.yaml), question_sales_mgmt → answer_with_facts.
        Проверяем что fallback_action правильный.
        """
        from src.yaml_config.constants import INTENT_ACTION_OVERRIDES, INTENT_CATEGORIES

        # question_sales_mgmt должен быть в операционных вопросах (answer_with_facts group)
        ops_intents = INTENT_CATEGORIES.get("operations_questions", [])
        assert "question_sales_mgmt" in ops_intents, (
            f"question_sales_mgmt должен быть в operations_questions category, "
            f"которая маппится на answer_with_facts. "
            f"Текущие operations_questions: {ops_intents}"
        )

        # Не должен быть в overrides на compare_with_competitor
        override = INTENT_ACTION_OVERRIDES.get("question_sales_mgmt", "")
        assert override != "compare_with_competitor", (
            f"question_sales_mgmt не должен иметь override на compare_with_competitor, "
            f"но имеет: '{override}'"
        )


# =============================================================================
# ИНТЕГРАЦИОННЫЙ ТЕСТ: полная цепь нон-секвитура
# =============================================================================

class TestNonSequitur_Integration:
    """
    Интеграционные тесты, воспроизводящие точные условия нон-секвитуров из симуляции
    без мокирования внутренних компонентов.
    """

    def test_trust_objection_message_does_not_trigger_price_secondary(self):
        """
        Полный тест с реальным secondary_intent_detection layer.
        'а это точно работает? не уверен, что стоит тратить время' →
        НЕ должен давать price_question secondary.
        """
        from src.classifier.secondary_intent_detection import DEFAULT_SECONDARY_INTENT_PATTERNS

        trust_objection_messages = [
            "а это точно работает? не уверен, что стоит тратить время на это",
            "вручную в основном. а это точно работает? не уверен, что стоит тратить время",
            "не уверен что стоит этим заниматься",
            "стоит ли вообще на это тратить деньги и время?",
        ]

        price_kw = DEFAULT_SECONDARY_INTENT_PATTERNS["price_question"].keywords
        false_positives = []

        for msg in trust_objection_messages:
            triggered = [kw for kw in price_kw if kw in msg.lower()]
            if triggered:
                false_positives.append((msg, triggered))

        assert not false_positives, (
            f"ЛОЖНЫЕ СРАБАТЫВАНИЯ price_question для возражений доверия/ценности:\n"
            + "\n".join(f"  '{msg}' → keyword: {kw}" for msg, kw in false_positives)
            + f"\n\nКорень: слово 'стоит' в keywords для price_question является омонимом. "
            f"Нужно убрать 'стоит' из keywords и оставить только в patterns (с контекстом: 'сколько стоит')."
        )

    def test_price_keywords_have_no_value_judgment_homonyms(self):
        """
        Проверяет что все keywords для price_question однозначно указывают на цену,
        а не на оценку/суждение.

        Слова-омонимы которые могут ложно срабатывать:
        - "стоит" (costs vs. is worth/should)
        - "давайте" (let's — не имеет отношения к цене)
        """
        from src.classifier.secondary_intent_detection import DEFAULT_SECONDARY_INTENT_PATTERNS

        price_pattern = DEFAULT_SECONDARY_INTENT_PATTERNS["price_question"]

        # Слова которые являются омонимами и должны быть убраны из keywords
        HOMONYM_KEYWORDS = {
            "стоит",   # "сколько стоит" (price) vs "стоит ли" (should/worth it)
            "давайте", # "давайте по цене" (price context) vs "давайте обсудим" (generic)
        }

        found_homonyms = HOMONYM_KEYWORDS & price_pattern.keywords
        assert not found_homonyms, (
            f"Омонимы в keywords price_question: {found_homonyms}\n"
            f"Эти слова вызывают ложные срабатывания price_question secondary intent.\n"
            f"Решение: убрать из keywords, перенести 'стоит' только в patterns "
            f"с контекстом: r'сколько\\s+стоит' (уже есть в patterns)."
        )
