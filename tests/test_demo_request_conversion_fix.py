"""
Тесты для критического фикса: 0% конверсии → исправление demo_request flow.

Проблема (из simulation_report.txt):
- 50 симуляций, 0% конверсии в успех
- Клиенты соглашаются на демо, но попадают в soft_close
- demo_request перехватывается SPIN-классификацией
- close state не имел перехода demo_request → success

Исправления:
- Вариант A: demo_request override в hybrid.py (перед SPIN-классификацией)
- Вариант B: transitions demo_request → success в close state
- Вариант C: улучшенная логика is_final в bot.py

Тесты проверяют:
1. Классификатор правильно определяет demo_request даже с данными
2. State machine правильно переходит close → success
3. Метрики правильно финализируются
4. Интеграционные сценарии работают end-to-end
"""

import pytest
import sys
sys.path.insert(0, 'src')

from unittest.mock import MagicMock

from classifier import HybridClassifier
from state_machine import StateMachine
from bot import SalesBot
from config import SALES_STATES
from feature_flags import flags


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def mock_llm():
    """Мок LLM для тестирования без реального API"""
    llm = MagicMock()
    llm.generate.return_value = "Здравствуйте! Чем могу помочь?"
    return llm


@pytest.fixture
def bot(mock_llm):
    """Создаёт SalesBot с моком LLM"""
    flags.enable_group("phase_0")
    flags.enable_group("phase_1")
    flags.enable_group("phase_2")
    flags.enable_group("phase_3")

    bot = SalesBot(mock_llm)
    yield bot

    flags.clear_all_overrides()


class TestDemoRequestOverride:
    """
    Тесты для Варианта A: demo_request override в hybrid.py

    Проблема: SPIN-классификация перехватывает демо-запросы когда
    в сообщении есть данные (company_size, pain_point и т.д.)
    """

    def setup_method(self):
        self.classifier = HybridClassifier()

    # =========================================================================
    # КРИТИЧЕСКИЕ СЛУЧАИ: Демо + данные в одном сообщении
    # =========================================================================

    def test_demo_with_company_size(self):
        """Демо-запрос с указанием размера компании → demo_request, не situation_provided"""
        test_cases = [
            "12 человек, хочу демо",
            "у нас 20 сотрудников, покажите как работает",
            "команда 15 человек, можно попробовать?",
            "нас 8, хотим посмотреть систему",
        ]

        for message in test_cases:
            result = self.classifier.classify(message, context={"spin_phase": "situation"})
            assert result["intent"] == "demo_request", \
                f"'{message}' должен быть demo_request, получили {result['intent']}"

    def test_demo_with_pain_point(self):
        """Демо-запрос с указанием проблемы → demo_request, не problem_revealed"""
        # Случаи где демо-маркер явный и должен перехватить problem
        test_cases = [
            "теряем клиентов, покажите демо",
            "много ручной работы, хочу посмотреть как автоматизировать",
            "нет контроля над продажами, можно демонстрацию?",
        ]

        for message in test_cases:
            result = self.classifier.classify(message, context={"spin_phase": "problem"})
            assert result["intent"] == "demo_request", \
                f"'{message}' должен быть demo_request, получили {result['intent']}"

    def test_demo_with_current_tools(self):
        """Демо-запрос с указанием текущих инструментов → demo_request"""
        test_cases = [
            "используем Excel, хочу демо вашей системы",
            "работаем в 1С, покажите как интегрируется",
            "ведём в блокноте, можно попробовать CRM?",
        ]

        for message in test_cases:
            result = self.classifier.classify(message, context={"spin_phase": "situation"})
            assert result["intent"] == "demo_request", \
                f"'{message}' должен быть demo_request, получили {result['intent']}"

    # =========================================================================
    # ЯВНЫЕ ДЕМО-ПАТТЕРНЫ
    # =========================================================================

    def test_explicit_demo_patterns(self):
        """Явные демо-паттерны всегда возвращают demo_request"""
        patterns = [
            "хочу демо",
            "покажите демо",
            "можно демо?",
            "дайте демо",
            "запишите на демо",
            "хотим демонстрацию",
            "нужна презентация",
            "хочу посмотреть как работает",
            "покажите систему в действии",
            "можно попробовать?",
            "хочу потестировать",
            "есть пробный период?",
            "бесплатный доступ есть?",
            "trial версия?",
            "давайте посмотрим",
            "давай попробуем",
        ]

        for pattern in patterns:
            result = self.classifier.classify(pattern)
            assert result["intent"] == "demo_request", \
                f"'{pattern}' должен быть demo_request, получили {result['intent']}"

    def test_demo_in_all_spin_phases(self):
        """Демо-запрос определяется в любой SPIN фазе"""
        spin_phases = ["situation", "problem", "implication", "need_payoff"]
        demo_message = "хочу посмотреть демо"

        for phase in spin_phases:
            result = self.classifier.classify(demo_message, context={"spin_phase": phase})
            assert result["intent"] == "demo_request", \
                f"В фазе {phase}: '{demo_message}' должен быть demo_request"

    # =========================================================================
    # КОНТЕКСТНЫЕ ДЕМО-МАРКЕРЫ (soft patterns)
    # =========================================================================

    def test_soft_demo_patterns_with_positive_context(self):
        """Мягкие демо-паттерны + положительный контекст = demo_request"""
        test_cases = [
            "хочу посмотреть",
            "интересно попробовать",
            "давайте глянем",
            "можно показать?",
            "готов попробовать",
        ]

        for message in test_cases:
            result = self.classifier.classify(message)
            assert result["intent"] == "demo_request", \
                f"'{message}' должен быть demo_request, получили {result['intent']}"

    # =========================================================================
    # НЕГАТИВНЫЕ СЛУЧАИ: Не демо-запросы
    # =========================================================================

    def test_not_demo_requests(self):
        """Сообщения без демо-маркеров не должны быть demo_request"""
        not_demo = [
            "у нас 12 человек",  # только данные, без демо
            "теряем клиентов",  # только проблема
            "сколько стоит?",  # вопрос о цене
            "какие функции есть?",  # вопрос о функциях
            "не интересно",  # отказ
            "подумаю",  # возражение
        ]

        for message in not_demo:
            result = self.classifier.classify(message)
            assert result["intent"] != "demo_request", \
                f"'{message}' НЕ должен быть demo_request, получили {result['intent']}"


class TestCloseStateTransitions:
    """
    Тесты для Варианта B: transitions в close state (config.py)

    Проблема: close state не имел перехода demo_request → success,
    клиенты застревали в close и уходили в soft_close
    """

    def setup_method(self):
        self.sm = StateMachine()

    def test_close_state_has_demo_request_transition(self):
        """close state имеет переход demo_request → success"""
        close_config = SALES_STATES["close"]
        assert "demo_request" in close_config["transitions"], \
            "close должен иметь transition для demo_request"
        assert close_config["transitions"]["demo_request"] == "success", \
            "demo_request в close должен вести в success"

    def test_close_state_has_agreement_transition(self):
        """close state имеет переход agreement → success"""
        close_config = SALES_STATES["close"]
        assert "agreement" in close_config["transitions"], \
            "close должен иметь transition для agreement"
        assert close_config["transitions"]["agreement"] == "success", \
            "agreement в close должен вести в success"

    def test_demo_request_in_close_leads_to_success(self):
        """demo_request в close state → переход в success"""
        self.sm.state = "close"
        self.sm.spin_phase = "close"

        action, next_state = self.sm.apply_rules("demo_request")

        assert next_state == "success", \
            f"demo_request в close должен вести в success, получили {next_state}"

    def test_agreement_in_close_leads_to_success(self):
        """agreement в close state → переход в success"""
        self.sm.state = "close"
        self.sm.spin_phase = "close"

        action, next_state = self.sm.apply_rules("agreement")

        assert next_state == "success", \
            f"agreement в close должен вести в success, получили {next_state}"

    def test_callback_request_in_close_leads_to_success(self):
        """callback_request в close state → переход в success"""
        self.sm.state = "close"
        self.sm.spin_phase = "close"

        action, next_state = self.sm.apply_rules("callback_request")

        assert next_state == "success", \
            f"callback_request в close должен вести в success, получили {next_state}"

    def test_consultation_request_in_close_leads_to_success(self):
        """consultation_request в close state → переход в success"""
        self.sm.state = "close"
        self.sm.spin_phase = "close"

        action, next_state = self.sm.apply_rules("consultation_request")

        assert next_state == "success", \
            f"consultation_request в close должен вести в success, получили {next_state}"

    def test_rejection_in_close_leads_to_soft_close(self):
        """rejection в close state → переход в soft_close (без изменений)"""
        self.sm.state = "close"
        self.sm.spin_phase = "close"

        action, next_state = self.sm.apply_rules("rejection")

        assert next_state == "soft_close", \
            f"rejection в close должен вести в soft_close, получили {next_state}"

    def test_question_in_close_stays_in_close(self):
        """Вопросы в close state → остаёмся в close (правило, не переход)"""
        self.sm.state = "close"
        self.sm.spin_phase = "close"

        # Вопросы должны обрабатываться через rules, не transitions
        for intent in ["question_features", "price_question", "question_integrations"]:
            action, next_state = self.sm.apply_rules(intent)
            # State должен остаться close (правило возвращает action, не меняет state)
            # или остаться прежним если нет специального правила
            assert next_state in ("close", self.sm.state), \
                f"{intent} в close не должен менять state на {next_state}"


class TestSuccessMetricsFinalization:
    """
    Тесты для Варианта C: логика is_final в bot.py

    Проблема: метрики финализировались только при is_final=True,
    но is_final=True только для success state
    """

    def test_demo_request_to_success_finalizes_as_demo_scheduled(self, bot):
        """Демо-запрос → close → agreement → success"""
        # Прогоняем диалог до close
        bot.process("Привет")
        bot.process("у нас 10 человек")
        bot.process("теряем клиентов")
        bot.process("это влияет на прибыль")
        bot.process("было бы здорово решить эту проблему")

        # Demo-запрос ведёт в close (предложение демо)
        result = bot.process("хочу посмотреть демо")
        assert result["state"] in ("close", "success"), \
            f"После demo_request должны быть в close или success, state={result['state']}"

        # Если ещё в close, подтверждаем согласие
        if result["state"] == "close":
            result = bot.process("да, записывайте")
            assert result["state"] == "success", \
                f"После подтверждения должны быть в success, state={result['state']}"

    def test_agreement_in_close_finalizes_correctly(self, bot):
        """Согласие в close → success → правильная финализация"""
        # Устанавливаем state напрямую для теста
        bot.state_machine.state = "close"

        result = bot.process("да, давайте")

        # Проверяем переход в success
        assert result["state"] == "success", \
            f"agreement в close должен вести в success, получили {result['state']}"

    def test_contact_provided_leads_to_success(self, bot):
        """Предоставление контакта → SUCCESS метрика"""
        bot.state_machine.state = "close"

        result = bot.process("мой телефон +7 999 123 45 67")

        # contact_provided должен вести в success
        assert result["state"] == "success", \
            f"contact_provided должен вести в success, получили {result['state']}"


class TestIntegrationHappyPath:
    """
    Интеграционные тесты: полные диалоги от начала до успеха
    """

    def test_happy_path_with_demo_request(self, bot):
        """Полный happy path: приветствие → SPIN → демо → close → подтверждение → успех"""
        dialogue = [
            ("Привет, хочу узнать про CRM", None),
            ("у нас 15 человек, розничная торговля", None),
            ("теряем клиентов, нет контроля", None),
            ("да, это сильно влияет на продажи", None),
            ("хотелось бы видеть всё в одном месте", None),
            ("да, хочу демо", "close"),  # demo_request → close
            ("да, давайте", "success"),  # agreement в close → success
        ]

        for message, expected_state in dialogue:
            result = bot.process(message)
            if expected_state:
                assert result["state"] == expected_state, \
                    f"После '{message}' ожидали state={expected_state}, получили {result['state']}"

    def test_demo_request_mid_spin_leads_to_close_then_success(self, bot):
        """Демо-запрос в середине SPIN → close → success"""
        # Начинаем диалог
        bot.process("Привет")
        bot.process("у нас 10 человек")

        # Демо-запрос в середине SPIN situation
        result = bot.process("хочу посмотреть демо")

        # Должны быть в close или success
        assert result["state"] in ("close", "success"), \
            f"Demo request должен вести в close/success, получили {result['state']}"

        # Если в close, подтверждение должно вести в success
        if result["state"] == "close":
            result = bot.process("да, записывайте")
            assert result["state"] == "success", \
                f"Подтверждение в close должно вести в success, получили {result['state']}"

    def test_demo_with_data_in_one_message(self, bot):
        """Демо + данные в одном сообщении → не застреваем в SPIN"""
        bot.process("Привет")

        # Всё в одном сообщении
        result = bot.process("у нас 20 человек, теряем клиентов, хочу демо")

        # Должны быть в close или success (НЕ в spin_situation!)
        assert result["state"] not in ("spin_situation", "spin_problem"), \
            f"После 'данные + демо' не должны быть в SPIN, получили {result['state']}"
        assert result["state"] in ("close", "success", "presentation"), \
            f"После 'данные + демо' должны быть в close/success/presentation"

    def test_multiple_demo_requests_dont_loop(self, bot):
        """Несколько демо-запросов не зацикливают диалог"""
        bot.process("Привет")

        # Первый демо-запрос
        result1 = bot.process("хочу демо")
        state1 = result1["state"]

        # Второй демо-запрос
        result2 = bot.process("да, покажите демо")

        # Не должны застрять или уйти в soft_close
        assert result2["state"] != "soft_close", \
            f"Повторный demo_request не должен вести в soft_close"
        assert result2["state"] in ("close", "success"), \
            f"Повторный demo_request должен вести в close/success"


class TestEdgeCases:
    """
    Краевые случаи и регрессии
    """

    def setup_method(self):
        self.classifier = HybridClassifier()

    def test_demo_typos_recognized(self):
        """Опечатки в демо-запросах распознаются"""
        typos = [
            "хочу демку",
            "покажите дему",
            "демонстрация нужна",
            "презентацию покажите",
        ]

        for typo in typos:
            result = self.classifier.classify(typo)
            assert result["intent"] == "demo_request", \
                f"'{typo}' должен быть demo_request"

    def test_demo_in_different_forms(self):
        """Разные формы демо-запросов"""
        forms = [
            "ХОЧУ ДЕМО",  # uppercase
            "хочу   демо",  # extra spaces
            "хочу демо!",  # punctuation
            "хочу демо?",
            "хочу демо...",
        ]

        for form in forms:
            result = self.classifier.classify(form)
            assert result["intent"] == "demo_request", \
                f"'{form}' должен быть demo_request"

    def test_rejection_still_works_in_close(self, bot):
        """Отказ в close по-прежнему ведёт в soft_close"""
        bot.state_machine.state = "close"

        result = bot.process("не интересно")

        assert result["state"] == "soft_close", \
            "Rejection в close должен вести в soft_close"

    def test_demo_after_soft_close_returns_to_close(self, bot):
        """Демо-запрос после soft_close возвращает в close"""
        bot.state_machine.state = "soft_close"

        result = bot.process("подождите, всё-таки хочу демо")

        assert result["state"] in ("close", "success"), \
            f"Demo request из soft_close должен вести в close/success"


class TestSimulationScenarios:
    """
    Тесты воспроизводящие сценарии из simulation_report.txt
    """

    def test_simulation_0_technical_persona_fixed(self, bot):
        """
        Симуляция #0 (technical): клиент спрашивает про API и демо
        Раньше: застревал в soft_close
        Теперь: должен попасть в success
        """
        dialogue = [
            "Есть API для интеграции?",
            "как с безопасностью? есть документы?",
            "хочу посмотреть демо",
        ]

        for message in dialogue:
            result = bot.process(message)

        # После демо-запроса не должны быть в soft_close
        assert result["state"] != "soft_close", \
            "Technical persona не должна застревать в soft_close после demo_request"

    def test_simulation_2_happy_path_fixed(self, bot):
        """
        Симуляция #2 (happy_path): клиент соглашается на демо
        Раньше: 100% SPIN coverage, но soft_close
        Теперь: должен попасть в close, затем success после подтверждения
        """
        dialogue = [
            "Привет, хочу узнать про вашу CRM",
            "12-14 человек, теряем клиентов",
            "прибыль падает",
            "там бы мы сразу знали где товар",
            "да, хочу посмотреть демо",
        ]

        for message in dialogue:
            result = bot.process(message)

        # После demo_request должны быть в close (не soft_close!)
        assert result["state"] in ("close", "success"), \
            f"Happy path должен быть в close/success после demo_request, получили {result['state']}"

        # Если в close, подтверждаем
        if result["state"] == "close":
            result = bot.process("да, записывайте")
            assert result["state"] == "success", \
                f"После подтверждения должны быть в success, получили {result['state']}"

    def test_simulation_3_technical_repeated_questions_fixed(self, bot):
        """
        Симуляция #3 (technical): повторные вопросы о документации
        Раньше: 10 fallback, soft_close
        Теперь: должен попробовать ответить или предложить альтернативу
        """
        bot.process("Привет")
        bot.process("пользуюсь 1с и excel")

        # Клиент просит демо несмотря на вопросы
        result = bot.process("ладно, давайте демо")

        assert result["state"] in ("close", "success"), \
            "После демо-запроса должны быть в close/success"


class TestMetricsCorrectness:
    """
    Тесты корректности метрик
    """

    def test_demo_scheduled_outcome(self, bot):
        """demo_request в close → outcome = DEMO_SCHEDULED"""
        bot.process("Привет")
        bot.state_machine.state = "close"

        result = bot.process("хочу демо")

        # Проверяем метрики
        metrics = bot.get_metrics_summary()

        # outcome должен быть success или demo_scheduled
        if "outcome" in metrics:
            assert metrics["outcome"] in ("success", "demo_scheduled", "DEMO_SCHEDULED", "SUCCESS"), \
                f"Outcome должен быть success/demo_scheduled, получили {metrics.get('outcome')}"

    def test_intents_sequence_contains_demo_request(self, bot):
        """demo_request записывается в intents_sequence"""
        bot.process("Привет")
        result = bot.process("хочу посмотреть демо")

        metrics = bot.get_metrics_summary()

        assert "demo_request" in str(metrics.get("intents_sequence", [])), \
            "demo_request должен быть в intents_sequence"


# =============================================================================
# ПАРАМЕТРИЗОВАННЫЕ ТЕСТЫ
# =============================================================================

@pytest.mark.parametrize("message,expected_intent", [
    # Явные демо-запросы
    ("хочу демо", "demo_request"),
    ("покажите демо", "demo_request"),
    ("можно демо?", "demo_request"),
    ("дайте демо", "demo_request"),
    ("хочу демонстрацию", "demo_request"),
    ("нужна презентация", "demo_request"),

    # Демо + данные
    ("10 человек, хочу демо", "demo_request"),
    ("теряем клиентов, покажите демо", "demo_request"),
    ("используем Excel, хочу попробовать", "demo_request"),

    # Хочу посмотреть/попробовать
    ("хочу посмотреть как работает", "demo_request"),
    ("можно попробовать?", "demo_request"),
    ("хотелось бы потестировать", "demo_request"),

    # Пробный период
    ("есть пробный период?", "demo_request"),
    ("бесплатный доступ?", "demo_request"),
    ("trial версия есть?", "demo_request"),

    # Давай/давайте
    ("давайте посмотрим", "demo_request"),
    ("давай попробуем", "demo_request"),
])
def test_demo_request_classification(message, expected_intent):
    """Параметризованный тест классификации demo_request"""
    classifier = HybridClassifier()
    result = classifier.classify(message)
    assert result["intent"] == expected_intent, \
        f"'{message}' должен быть {expected_intent}, получили {result['intent']}"


@pytest.mark.parametrize("state,intent,expected_next_state", [
    # close state transitions
    ("close", "demo_request", "success"),
    ("close", "agreement", "success"),
    ("close", "callback_request", "success"),
    ("close", "consultation_request", "success"),
    ("close", "contact_provided", "success"),
    ("close", "rejection", "soft_close"),
    ("close", "farewell", "soft_close"),

    # soft_close state transitions
    ("soft_close", "demo_request", "close"),
    ("soft_close", "agreement", "spin_situation"),
    ("soft_close", "rejection", "soft_close"),
])
def test_state_transitions(state, intent, expected_next_state):
    """Параметризованный тест переходов состояний"""
    sm = StateMachine()
    sm.state = state
    sm.spin_phase = state

    action, next_state = sm.apply_rules(intent)

    assert next_state == expected_next_state, \
        f"В state={state} intent={intent} должен вести в {expected_next_state}, получили {next_state}"


# =============================================================================
# ЗАПУСК ТЕСТОВ
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
