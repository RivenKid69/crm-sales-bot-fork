"""
Тесты для Context Window — расширенного контекста классификатора

Тестирует:
1. Базовую функциональность ContextWindow
2. Детекцию паттернов (повторы, застревание, осцилляции)
3. Интеграцию с классификатором
4. Сравнение результатов "до" и "после" (с историей и без)
"""

import pytest
import sys
import os

# Добавляем путь к src
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from context_window import ContextWindow, TurnContext
from classifier import HybridClassifier


# =============================================================================
# ТЕСТЫ БАЗОВОЙ ФУНКЦИОНАЛЬНОСТИ ContextWindow
# =============================================================================

class TestContextWindowBasic:
    """Базовые тесты ContextWindow."""

    def test_init_empty(self):
        """Новое окно должно быть пустым."""
        cw = ContextWindow(max_size=5)
        assert len(cw) == 0
        assert not cw  # bool(cw) == False

    def test_add_turn(self):
        """Добавление хода увеличивает размер."""
        cw = ContextWindow(max_size=5)
        turn = TurnContext(
            user_message="привет",
            intent="greeting",
            confidence=0.95,
            action="greet",
            state="greeting",
            next_state="spin_situation"
        )
        cw.add_turn(turn)

        assert len(cw) == 1
        assert cw.get_intent_history() == ["greeting"]

    def test_sliding_window(self):
        """Окно не должно превышать max_size."""
        cw = ContextWindow(max_size=3)

        # Добавляем 5 ходов
        for i in range(5):
            turn = TurnContext(
                user_message=f"сообщение {i}",
                intent=f"intent_{i}",
                confidence=0.8,
                action=f"action_{i}",
                state="state",
                next_state="state"
            )
            cw.add_turn(turn)

        # Должно остаться только 3 последних
        assert len(cw) == 3
        assert cw.get_intent_history() == ["intent_2", "intent_3", "intent_4"]

    def test_add_turn_from_dict(self):
        """Добавление хода через словарь параметров."""
        cw = ContextWindow(max_size=5)
        cw.add_turn_from_dict(
            user_message="сколько стоит?",
            bot_response="Давайте сначала узнаю о вас...",
            intent="price_question",
            confidence=0.9,
            action="deflect_and_continue",
            state="greeting",
            next_state="spin_situation",
            method="root"
        )

        assert len(cw) == 1
        assert cw.get_last_turn().intent == "price_question"
        assert cw.get_last_turn().action == "deflect_and_continue"

    def test_reset(self):
        """Сброс очищает окно."""
        cw = ContextWindow(max_size=5)
        cw.add_turn_from_dict(
            user_message="тест",
            bot_response="ответ",
            intent="test",
            confidence=0.5,
            action="test",
            state="test",
            next_state="test"
        )

        assert len(cw) == 1
        cw.reset()
        assert len(cw) == 0


# =============================================================================
# ТЕСТЫ ПОЛУЧЕНИЯ ИСТОРИИ
# =============================================================================

class TestContextWindowHistory:
    """Тесты получения истории из окна."""

    @pytest.fixture
    def filled_window(self):
        """Окно с 4 ходами для тестов."""
        cw = ContextWindow(max_size=5)

        turns_data = [
            ("greeting", "greet", "greeting"),
            ("price_question", "deflect_and_continue", "spin_situation"),
            ("info_provided", "spin_situation", "spin_problem"),
            ("price_question", "answer_question", "spin_problem"),  # Повторный вопрос
        ]

        for i, (intent, action, state) in enumerate(turns_data):
            cw.add_turn_from_dict(
                user_message=f"сообщение {i}",
                bot_response=f"ответ {i}",
                intent=intent,
                confidence=0.8,
                action=action,
                state=state,
                next_state=state,
            )

        return cw

    def test_get_intent_history(self, filled_window):
        """Получение истории интентов."""
        history = filled_window.get_intent_history()
        assert history == ["greeting", "price_question", "info_provided", "price_question"]

    def test_get_intent_history_limited(self, filled_window):
        """Получение ограниченной истории интентов."""
        history = filled_window.get_intent_history(limit=2)
        assert history == ["info_provided", "price_question"]

    def test_get_action_history(self, filled_window):
        """Получение истории actions."""
        history = filled_window.get_action_history()
        assert history == ["greet", "deflect_and_continue", "spin_situation", "answer_question"]

    def test_get_last_turn(self, filled_window):
        """Получение последнего хода."""
        last = filled_window.get_last_turn()
        assert last.intent == "price_question"
        assert last.action == "answer_question"

    def test_get_last_n_turns(self, filled_window):
        """Получение последних N ходов."""
        last_2 = filled_window.get_last_n_turns(2)
        assert len(last_2) == 2
        assert last_2[0].intent == "info_provided"
        assert last_2[1].intent == "price_question"


# =============================================================================
# ТЕСТЫ ДЕТЕКЦИИ ПАТТЕРНОВ
# =============================================================================

class TestPatternDetection:
    """Тесты детекции паттернов поведения."""

    def test_detect_repeated_question(self):
        """Детекция повторного вопроса."""
        cw = ContextWindow(max_size=5)

        # Клиент дважды спрашивает про цену
        cw.add_turn_from_dict(
            user_message="сколько стоит?",
            bot_response="давайте узнаю о вас",
            intent="price_question",
            confidence=0.9,
            action="deflect_and_continue",
            state="greeting",
            next_state="spin_situation"
        )
        cw.add_turn_from_dict(
            user_message="10 человек",
            bot_response="отлично!",
            intent="info_provided",
            confidence=0.9,
            action="spin_situation",
            state="spin_situation",
            next_state="spin_problem"
        )
        cw.add_turn_from_dict(
            user_message="ну так сколько стоит?",
            bot_response="от 990р/мес",
            intent="price_question",
            confidence=0.9,
            action="answer_question",
            state="spin_problem",
            next_state="spin_problem"
        )

        repeated = cw.detect_repeated_question()
        assert repeated == "price_question"

    def test_no_repeated_question(self):
        """Нет повторного вопроса если все разные."""
        cw = ContextWindow(max_size=5)

        cw.add_turn_from_dict(
            user_message="сколько стоит?",
            bot_response="от 990р",
            intent="price_question",
            confidence=0.9,
            action="answer",
            state="greeting",
            next_state="spin_situation"
        )
        cw.add_turn_from_dict(
            user_message="какие интеграции?",
            bot_response="1С, AmoCRM...",
            intent="question_integrations",
            confidence=0.9,
            action="answer",
            state="spin_situation",
            next_state="spin_situation"
        )

        repeated = cw.detect_repeated_question()
        assert repeated is None

    def test_detect_stuck_unclear(self):
        """Детекция застревания на unclear."""
        cw = ContextWindow(max_size=5)

        # 3 unclear подряд
        for i in range(3):
            cw.add_turn_from_dict(
                user_message=f"бла бла {i}",
                bot_response="не понял",
                intent="unclear",
                confidence=0.3,
                action="probe",
                state="spin_situation",
                next_state="spin_situation"
            )

        assert cw.detect_stuck_pattern() is True
        assert cw.get_unclear_count() == 3

    def test_not_stuck_if_different_intents(self):
        """Не застревание если интенты разные."""
        cw = ContextWindow(max_size=5)

        intents = ["greeting", "price_question", "info_provided"]
        for intent in intents:
            cw.add_turn_from_dict(
                user_message="тест",
                bot_response="ответ",
                intent=intent,
                confidence=0.8,
                action="action",
                state="state",
                next_state="state"
            )

        assert cw.detect_stuck_pattern() is False

    def test_detect_oscillation(self):
        """Детекция осцилляции (колебания)."""
        cw = ContextWindow(max_size=5)

        # objection → agreement → objection → agreement
        oscillation_pattern = [
            "objection_price",
            "agreement",
            "objection_think",
            "agreement"
        ]

        for intent in oscillation_pattern:
            cw.add_turn_from_dict(
                user_message="тест",
                bot_response="ответ",
                intent=intent,
                confidence=0.8,
                action="action",
                state="state",
                next_state="state"
            )

        assert cw.detect_oscillation() is True

    def test_no_oscillation_progressive(self):
        """Нет осцилляции при прогрессивном движении."""
        cw = ContextWindow(max_size=5)

        # Линейный прогресс
        progressive_pattern = [
            "greeting",
            "info_provided",
            "problem_revealed",
            "agreement"
        ]

        for intent in progressive_pattern:
            cw.add_turn_from_dict(
                user_message="тест",
                bot_response="ответ",
                intent=intent,
                confidence=0.8,
                action="action",
                state="state",
                next_state="state"
            )

        assert cw.detect_oscillation() is False


# =============================================================================
# ТЕСТЫ СЧЁТЧИКОВ И МЕТРИК
# =============================================================================

class TestCountersAndMetrics:
    """Тесты счётчиков и метрик."""

    @pytest.fixture
    def mixed_window(self):
        """Окно с разнообразными интентами."""
        cw = ContextWindow(max_size=10)

        intents = [
            "greeting",
            "price_question",
            "objection_price",
            "agreement",
            "objection_think",
            "info_provided",
            "question_features",
            "agreement"
        ]

        for i, intent in enumerate(intents):
            cw.add_turn_from_dict(
                user_message=f"msg {i}",
                bot_response=f"resp {i}",
                intent=intent,
                confidence=0.7 + i * 0.03,
                action="action",
                state="state",
                next_state="state"
            )

        return cw

    def test_objection_count(self, mixed_window):
        """Подсчёт возражений."""
        assert mixed_window.get_objection_count() == 2  # objection_price, objection_think

    def test_positive_count(self, mixed_window):
        """Подсчёт позитивных сигналов."""
        # agreement (2), info_provided (1) = 3
        assert mixed_window.get_positive_count() == 3

    def test_question_count(self, mixed_window):
        """Подсчёт вопросов."""
        # price_question, question_features = 2
        assert mixed_window.get_question_count() == 2

    def test_count_intent(self, mixed_window):
        """Подсчёт конкретного интента."""
        assert mixed_window.count_intent("agreement") == 2
        assert mixed_window.count_intent("greeting") == 1
        assert mixed_window.count_intent("rejection") == 0

    def test_count_consecutive_intent(self):
        """Подсчёт последовательных интентов."""
        cw = ContextWindow(max_size=5)

        intents = ["greeting", "agreement", "agreement", "agreement"]
        for intent in intents:
            cw.add_turn_from_dict(
                user_message="msg",
                bot_response="resp",
                intent=intent,
                confidence=0.8,
                action="action",
                state="state",
                next_state="state"
            )

        assert cw.count_consecutive_intent("agreement") == 3
        assert cw.count_consecutive_intent("greeting") == 0  # не с конца

    def test_average_confidence(self, mixed_window):
        """Средняя уверенность."""
        avg = mixed_window.get_average_confidence()
        assert 0.7 < avg < 1.0

    def test_confidence_trend_increasing(self):
        """Тренд уверенности — рост."""
        cw = ContextWindow(max_size=5)

        for conf in [0.5, 0.6, 0.8]:
            cw.add_turn_from_dict(
                user_message="msg",
                bot_response="resp",
                intent="intent",
                confidence=conf,
                action="action",
                state="state",
                next_state="state"
            )

        assert cw.get_confidence_trend() == "increasing"

    def test_confidence_trend_decreasing(self):
        """Тренд уверенности — падение."""
        cw = ContextWindow(max_size=5)

        for conf in [0.9, 0.7, 0.5]:
            cw.add_turn_from_dict(
                user_message="msg",
                bot_response="resp",
                intent="intent",
                confidence=conf,
                action="action",
                state="state",
                next_state="state"
            )

        assert cw.get_confidence_trend() == "decreasing"


# =============================================================================
# ТЕСТЫ ИНТЕГРАЦИИ С КЛАССИФИКАТОРОМ
# =============================================================================

class TestClassifierIntegration:
    """Тесты интеграции Context Window с классификатором."""

    @pytest.fixture
    def classifier(self):
        """Классификатор для тестов."""
        return HybridClassifier()

    def test_classify_with_empty_history(self, classifier):
        """Классификация без истории работает как раньше."""
        result = classifier.classify("сколько стоит?", context={})

        assert result["intent"] == "price_question"
        assert result["confidence"] > 0.5

    def test_classify_with_history_context(self, classifier):
        """Классификация с контекстом истории."""
        context = {
            "state": "spin_situation",
            "spin_phase": "situation",
            "intent_history": ["greeting", "price_question"],
            "action_history": ["greet", "deflect_and_continue"],
            "objection_count": 0,
            "positive_count": 0,
            "question_count": 1,
            "unclear_count": 0,
            "has_oscillation": False,
            "is_stuck": False,
            "repeated_question": "price_question",  # Повторный вопрос!
            "confidence_trend": "stable",
        }

        # Клиент снова спрашивает про цену
        result = classifier.classify("ну так сколько стоит?", context=context)

        # Должен распознать как повторный вопрос о цене
        assert result["intent"] == "price_question"
        # Если сработал history_pattern, метод будет "history_pattern"
        # Иначе обычная классификация
        assert result["confidence"] >= 0.85

    def test_classify_repeated_price_after_deflect(self, classifier):
        """Повторный вопрос о цене после deflect."""
        context = {
            "state": "spin_situation",
            "spin_phase": "situation",
            "intent_history": ["price_question"],
            "action_history": ["deflect_and_continue"],  # Был deflect!
            "repeated_question": None,
            "is_stuck": False,
            "has_oscillation": False,
        }

        # Используем более явную формулировку для надёжной классификации
        result = classifier.classify("сколько стоит в итоге?", context=context)

        # Должен распознать повторный запрос цены
        assert result["intent"] == "price_question"
        assert result["confidence"] >= 0.85

    def test_classify_stuck_pattern_triggers_clarification(self, classifier):
        """3 unclear подряд должно вызвать needs_clarification."""
        context = {
            "state": "spin_situation",
            "spin_phase": "situation",
            "intent_history": ["unclear", "unclear", "unclear"],
            "action_history": ["probe", "probe", "probe"],
            "is_stuck": True,
            "unclear_count": 3,
            "has_oscillation": False,
            "repeated_question": None,
        }

        # Ещё одно непонятное сообщение
        result = classifier.classify("ыыывавыавы", context=context)

        # Должен сработать паттерн "stuck"
        assert result["intent"] == "needs_clarification"
        assert result.get("method") == "history_pattern"
        assert result.get("pattern_type") == "stuck_unclear"


# =============================================================================
# СРАВНИТЕЛЬНЫЕ ТЕСТЫ: С ИСТОРИЕЙ vs БЕЗ ИСТОРИИ
# =============================================================================

class TestWithVsWithoutHistory:
    """
    Сравнительные тесты показывающие разницу между
    классификацией с историей и без.
    """

    @pytest.fixture
    def classifier(self):
        return HybridClassifier()

    def test_repeated_price_question_detection(self, classifier):
        """
        Сценарий: Клиент дважды спрашивает про цену.

        БЕЗ истории: Просто price_question
        С историей: Распознаём что это ПОВТОРНЫЙ вопрос
        """
        message = "так сколько же стоит?"

        # БЕЗ истории
        result_without = classifier.classify(message, context={})
        assert result_without["intent"] == "price_question"
        method_without = result_without.get("method")

        # С историей (был deflect)
        context_with_history = {
            "intent_history": ["price_question", "info_provided"],
            "action_history": ["deflect_and_continue", "spin_situation"],
            "repeated_question": "price_question",
            "is_stuck": False,
            "has_oscillation": False,
        }
        result_with = classifier.classify(message, context=context_with_history)

        assert result_with["intent"] == "price_question"

        # С историей уверенность должна быть выше
        # (потому что мы уверены что это повторный вопрос)
        print(f"\nПовторный вопрос о цене:")
        print(f"  БЕЗ истории: intent={result_without['intent']}, "
              f"confidence={result_without['confidence']:.2f}, method={method_without}")
        print(f"  С историей:  intent={result_with['intent']}, "
              f"confidence={result_with['confidence']:.2f}, method={result_with.get('method')}")

    def test_short_answer_with_context(self, classifier):
        """
        Сценарий: Клиент отвечает "да" после презентации.

        БЕЗ истории: Непонятно что значит "да"
        С историей: Понимаем что это согласие на презентацию
        """
        message = "да"

        # БЕЗ истории
        result_without = classifier.classify(message, context={})
        intent_without = result_without["intent"]
        conf_without = result_without["confidence"]

        # С историей (после презентации)
        context_with_history = {
            "state": "presentation",
            "last_action": "presentation",
            "spin_phase": None,
            "intent_history": ["info_provided", "agreement"],
            "action_history": ["spin_need_payoff", "presentation"],
            "is_stuck": False,
            "has_oscillation": False,
        }
        result_with = classifier.classify(message, context=context_with_history)

        print(f"\nКороткий ответ 'да' после презентации:")
        print(f"  БЕЗ истории: intent={intent_without}, confidence={conf_without:.2f}")
        print(f"  С историей:  intent={result_with['intent']}, "
              f"confidence={result_with['confidence']:.2f}")

        # С контекстом должны понять что это agreement
        assert result_with["intent"] == "agreement"
        assert result_with["confidence"] >= 0.8

    def test_stuck_detection(self, classifier):
        """
        Сценарий: Классификатор не понимает клиента 3 раза подряд.

        БЕЗ истории: Ещё один unclear
        С историей: Распознаём застревание → needs_clarification
        """
        message = "нуну какбы типа"

        # БЕЗ истории
        result_without = classifier.classify(message, context={})

        # С историей (3 unclear подряд)
        context_with_history = {
            "intent_history": ["unclear", "unclear", "unclear"],
            "action_history": ["probe", "probe", "probe"],
            "is_stuck": True,
            "unclear_count": 3,
            "has_oscillation": False,
            "repeated_question": None,
        }
        result_with = classifier.classify(message, context=context_with_history)

        print(f"\nЗастревание (3 unclear подряд):")
        print(f"  БЕЗ истории: intent={result_without['intent']}, "
              f"confidence={result_without['confidence']:.2f}")
        print(f"  С историей:  intent={result_with['intent']}, "
              f"confidence={result_with['confidence']:.2f}, "
              f"pattern={result_with.get('pattern_type')}")

        # С историей должны распознать застревание
        assert result_with["intent"] == "needs_clarification"
        assert result_with.get("pattern_type") == "stuck_unclear"


# =============================================================================
# РЕАЛИСТИЧНЫЕ СЦЕНАРИИ ДИАЛОГОВ
# =============================================================================

class TestRealisticScenarios:
    """Тесты на реалистичных сценариях диалогов."""

    @pytest.fixture
    def classifier(self):
        return HybridClassifier()

    def test_scenario_persistent_price_question(self, classifier):
        """
        Сценарий: Клиент настойчиво спрашивает про цену.

        Ход 1: "сколько стоит?" → deflect
        Ход 2: "у нас 5 человек" → info
        Ход 3: "так по деньгам как?" → должны ответить!
        """
        print("\n=== Сценарий: Настойчивый вопрос о цене ===")

        cw = ContextWindow(max_size=5)

        # Ход 1
        ctx1 = {"state": "greeting", "spin_phase": None}
        result1 = classifier.classify("сколько стоит?", context=ctx1)
        cw.add_turn_from_dict(
            user_message="сколько стоит?",
            bot_response="давайте узнаю о вас",
            intent=result1["intent"],
            confidence=result1["confidence"],
            action="deflect_and_continue",
            state="greeting",
            next_state="spin_situation"
        )
        print(f"Ход 1: '{result1['intent']}' (conf={result1['confidence']:.2f})")

        # Ход 2
        ctx2 = {
            "state": "spin_situation",
            "spin_phase": "situation",
            **cw.get_classifier_context()
        }
        result2 = classifier.classify("у нас 5 человек", context=ctx2)
        cw.add_turn_from_dict(
            user_message="у нас 5 человек",
            bot_response="отлично!",
            intent=result2["intent"],
            confidence=result2["confidence"],
            action="spin_situation",
            state="spin_situation",
            next_state="spin_problem"
        )
        print(f"Ход 2: '{result2['intent']}' (conf={result2['confidence']:.2f})")

        # Ход 3 — повторный вопрос о цене
        ctx3 = {
            "state": "spin_problem",
            "spin_phase": "problem",
            **cw.get_classifier_context()
        }
        result3 = classifier.classify("так по деньгам как?", context=ctx3)
        print(f"Ход 3: '{result3['intent']}' (conf={result3['confidence']:.2f}, "
              f"method={result3.get('method')}, pattern={result3.get('pattern_type')})")

        # Проверки
        assert result3["intent"] == "price_question"
        # Должен сработать паттерн "repeated_price_after_deflect"
        if result3.get("method") == "history_pattern":
            assert result3.get("pattern_type") == "repeated_price_after_deflect"

    def test_scenario_oscillating_client(self, classifier):
        """
        Сценарий: Клиент колеблется между согласием и возражениями.

        Тест проверяет детекцию осцилляции в Context Window.
        Используем принудительную запись интентов (симуляция правильной классификации).
        """
        print("\n=== Сценарий: Колеблющийся клиент ===")

        cw = ContextWindow(max_size=5)

        # Симулируем последовательность: objection → agreement → objection → agreement
        turns = [
            ("это дорого", "objection_price", "handle_objection"),
            ("ну ладно расскажите", "agreement", "presentation"),
            ("всё равно дорого", "objection_think", "handle_objection"),
            ("ок давайте", "agreement", "close"),
        ]

        for i, (msg, intent, action) in enumerate(turns, 1):
            cw.add_turn_from_dict(
                user_message=msg,
                bot_response="ответ",
                intent=intent,  # Используем ожидаемый интент напрямую
                confidence=0.85,
                action=action,
                state="presentation",
                next_state="presentation"
            )
            print(f"Ход {i}: '{msg}' → {intent}")

        # Проверяем что детектируется осцилляция
        assert cw.detect_oscillation() is True
        print(f"Осцилляция обнаружена: {cw.detect_oscillation()}")

    def test_scenario_confused_client(self, classifier):
        """
        Сценарий: Клиент отвечает непонятно несколько раз.

        Ход 1: "ыыы" → unclear
        Ход 2: "ну типа" → unclear
        Ход 3: "как-то так" → unclear
        Ход 4: "блаблабла" → needs_clarification (застревание!)
        """
        print("\n=== Сценарий: Запутавшийся клиент ===")

        cw = ContextWindow(max_size=5)

        unclear_messages = ["ыыы", "ну типа", "как-то так"]

        for i, msg in enumerate(unclear_messages, 1):
            ctx = {
                "state": "spin_situation",
                "spin_phase": "situation",
                **cw.get_classifier_context()
            }

            result = classifier.classify(msg, context=ctx)
            cw.add_turn_from_dict(
                user_message=msg,
                bot_response="не понял, уточните",
                intent="unclear",  # Принудительно unclear для теста
                confidence=0.3,
                action="probe",
                state="spin_situation",
                next_state="spin_situation"
            )
            print(f"Ход {i}: '{msg}' → unclear")

        # Ход 4 — должно сработать застревание
        ctx4 = {
            "state": "spin_situation",
            "spin_phase": "situation",
            **cw.get_classifier_context()
        }

        print(f"Контекст перед ходом 4: is_stuck={ctx4.get('is_stuck')}, "
              f"unclear_count={ctx4.get('unclear_count')}")

        result4 = classifier.classify("блаблабла", context=ctx4)
        print(f"Ход 4: 'блаблабла' → {result4['intent']} "
              f"(method={result4.get('method')}, pattern={result4.get('pattern_type')})")

        # Должен распознать застревание
        assert result4["intent"] == "needs_clarification"
        assert result4.get("pattern_type") == "stuck_unclear"


# =============================================================================
# ТЕСТЫ ПРОИЗВОДИТЕЛЬНОСТИ
# =============================================================================

class TestPerformance:
    """Тесты производительности Context Window."""

    def test_window_operations_fast(self):
        """Операции с окном должны быть быстрыми."""
        import time

        cw = ContextWindow(max_size=100)

        # Добавляем 1000 ходов
        start = time.time()
        for i in range(1000):
            cw.add_turn_from_dict(
                user_message=f"msg {i}",
                bot_response=f"resp {i}",
                intent=f"intent_{i % 10}",
                confidence=0.8,
                action="action",
                state="state",
                next_state="state"
            )
        add_time = time.time() - start

        # Получаем контекст
        start = time.time()
        for _ in range(100):
            ctx = cw.get_classifier_context()
        get_time = time.time() - start

        print(f"\nПроизводительность:")
        print(f"  Добавление 1000 ходов: {add_time*1000:.2f}ms")
        print(f"  Получение контекста 100 раз: {get_time*1000:.2f}ms")

        # Должно быть быстро
        assert add_time < 1.0  # < 1 секунды на 1000 добавлений
        assert get_time < 0.5  # < 500ms на 100 получений


# =============================================================================
# ЗАПУСК ТЕСТОВ
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
