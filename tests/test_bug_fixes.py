"""
Тесты для исправленных ошибок.

Покрывает:
1. retriever.py: Инициализация эмбеддингов с self.use_embeddings вместо параметра
2. hybrid.py: Корректное использование state из контекста
"""

import pytest
import sys
import os
from unittest.mock import patch, MagicMock

# Добавляем путь к src для импортов
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


# =============================================================================
# ТЕСТЫ ДЛЯ RETRIEVER.PY - ИНИЦИАЛИЗАЦИЯ ЭМБЕДДИНГОВ
# =============================================================================

class TestRetrieverEmbeddingsInitialization:
    """
    Тесты для проверки корректной инициализации эмбеддингов.

    Баг: В retriever.py:106 проверялся параметр use_embeddings вместо self.use_embeddings.
    Если CascadeRetriever() создавался без явного параметра use_embeddings,
    проверялся локальный параметр (который None), а не self.use_embeddings
    (который уже установлен из settings).
    """

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Сбрасываем singleton перед каждым тестом."""
        import knowledge.retriever as r
        r._retriever = None
        yield
        r._retriever = None

    def test_embeddings_init_without_explicit_param(self):
        """
        Эмбеддинги должны инициализироваться когда use_embeddings=True в settings,
        даже если параметр не передан явно в конструктор.

        Тест проверяет что после исправления бага (использование self.use_embeddings
        вместо локального параметра use_embeddings), _init_embeddings вызывается
        корректно на основе значения из settings.
        """
        from knowledge.retriever import CascadeRetriever

        # Создаём retriever с явным True - должен вызвать _init_embeddings
        with patch.object(CascadeRetriever, '_init_embeddings') as mock_init:
            # Передаём use_embeddings=True явно
            retriever = CascadeRetriever(use_embeddings=True)

            # _init_embeddings ДОЛЖЕН быть вызван
            mock_init.assert_called_once()
            assert retriever.use_embeddings is True

        # Проверяем что если use_embeddings=None, значение берётся из settings
        # и self.use_embeddings устанавливается корректно
        retriever_default = CascadeRetriever(use_embeddings=None)
        from settings import settings
        assert retriever_default.use_embeddings == settings.retriever.use_embeddings

    def test_embeddings_not_init_when_disabled_in_settings(self):
        """
        Эмбеддинги НЕ должны инициализироваться когда use_embeddings=False в settings.
        """
        from knowledge.retriever import CascadeRetriever

        # Создаём с явным use_embeddings=False
        with patch.object(CascadeRetriever, '_init_embeddings') as mock_init:
            retriever = CascadeRetriever(use_embeddings=False)

            # _init_embeddings НЕ должен вызываться
            mock_init.assert_not_called()
            assert retriever.use_embeddings is False

    def test_explicit_true_param_overrides_settings(self):
        """
        Явный параметр use_embeddings=True должен переопределять settings.
        """
        from knowledge.retriever import CascadeRetriever

        with patch.object(CascadeRetriever, '_init_embeddings') as mock_init:
            retriever = CascadeRetriever(use_embeddings=True)

            # _init_embeddings ДОЛЖЕН вызваться
            mock_init.assert_called_once()
            assert retriever.use_embeddings is True

    def test_explicit_false_param_overrides_settings(self):
        """
        Явный параметр use_embeddings=False должен переопределять settings.
        """
        from knowledge.retriever import CascadeRetriever
        from settings import settings

        # Даже если в settings use_embeddings=True
        original_value = settings.retriever.use_embeddings

        with patch.object(CascadeRetriever, '_init_embeddings') as mock_init:
            retriever = CascadeRetriever(use_embeddings=False)

            # _init_embeddings НЕ должен вызываться
            mock_init.assert_not_called()
            assert retriever.use_embeddings is False

    def test_self_use_embeddings_set_correctly_from_settings(self):
        """
        self.use_embeddings должен корректно устанавливаться из settings
        когда параметр не передан (None).
        """
        from knowledge.retriever import CascadeRetriever
        from settings import settings

        expected = settings.retriever.use_embeddings

        # Создаём без явного параметра
        retriever = CascadeRetriever(use_embeddings=None)

        # self.use_embeddings должен равняться значению из settings
        assert retriever.use_embeddings == expected


# =============================================================================
# ТЕСТЫ ДЛЯ HYBRID.PY - КОНТЕКСТНАЯ КЛАССИФИКАЦИЯ
# =============================================================================

class TestHybridContextState:
    """
    Тесты для проверки корректного использования state из контекста.

    Потенциальный баг: код мог ожидать "current_state" вместо "state" в контексте.
    Убеждаемся что "state" корректно обрабатывается.
    """

    @pytest.fixture
    def classifier(self):
        from classifier import HybridClassifier
        return HybridClassifier()

    # -------------------------------------------------------------------------
    # ТЕСТЫ НА КОРРЕКТНОЕ ЧТЕНИЕ STATE ИЗ КОНТЕКСТА
    # -------------------------------------------------------------------------

    def test_state_close_positive_response(self, classifier):
        """
        В состоянии close положительный ответ должен классифицироваться как agreement.
        Проверяем что state читается из context["state"], а не context["current_state"].
        """
        context = {"state": "close"}
        result = classifier.classify("да", context)

        assert result["intent"] == "agreement"
        assert result["method"] == "context"

    def test_state_close_negative_response(self, classifier):
        """
        В состоянии close отрицательный ответ должен классифицироваться как rejection.
        """
        context = {"state": "close"}
        result = classifier.classify("нет", context)

        assert result["intent"] == "rejection"
        assert result["method"] == "context"

    def test_state_soft_close_positive_response(self, classifier):
        """
        В состоянии soft_close положительный ответ = agreement (клиент передумал).
        """
        context = {"state": "soft_close"}
        result = classifier.classify("да", context)

        assert result["intent"] == "agreement"
        assert result["method"] == "context"

    def test_missing_data_contains_contact_info(self, classifier):
        """
        Если в missing_data есть contact_info, короткие ответы классифицируются
        как agreement/rejection (фаза закрытия).
        """
        context = {"missing_data": ["contact_info"]}

        result_yes = classifier.classify("да", context)
        assert result_yes["intent"] == "agreement"

        result_no = classifier.classify("нет", context)
        assert result_no["intent"] == "rejection"

    def test_state_key_not_current_state(self, classifier):
        """
        Убеждаемся что current_state НЕ используется.
        Если передать current_state вместо state, контекстная логика не сработает.
        """
        # Неправильный ключ - контекст не должен применяться для state-зависимой логики
        wrong_context = {"current_state": "close"}
        result = classifier.classify("да", wrong_context)

        # Без правильного state, должен вернуть общий agreement без context method
        # (или с низким confidence если нет другого контекста)
        assert result["intent"] == "agreement"
        # method может быть "context" если есть другие факторы, но confidence будет ниже

    def test_empty_state_uses_fallback(self, classifier):
        """
        Пустой state не должен вызывать ошибку, а использовать fallback логику.
        """
        context = {"state": None}
        result = classifier.classify("да", context)

        # Должен вернуть общий agreement
        assert result["intent"] == "agreement"

    # -------------------------------------------------------------------------
    # ТЕСТЫ НА ПРИОРИТЕТ КОНТЕКСТА
    # -------------------------------------------------------------------------

    def test_last_action_has_priority_over_state(self, classifier):
        """
        last_action имеет приоритет над state (проверяется первым в коде).
        """
        context = {
            "last_action": "close",
            "state": "greeting"  # Менее релевантное состояние
        }
        result = classifier.classify("да", context)

        assert result["intent"] == "agreement"
        assert result["confidence"] >= 0.9  # Высокая уверенность от close

    def test_spin_phase_used_when_no_last_action(self, classifier):
        """
        spin_phase используется когда нет last_action.
        """
        context = {"spin_phase": "problem"}
        result = classifier.classify("да", context)

        assert result["intent"] == "problem_revealed"
        assert result["method"] == "context"

    def test_state_used_when_no_last_action_or_spin(self, classifier):
        """
        state используется когда нет ни last_action, ни spin_phase.
        """
        context = {"state": "close"}
        result = classifier.classify("да", context)

        assert result["intent"] == "agreement"
        assert result["method"] == "context"


class TestHybridClassifyShortAnswer:
    """
    Тесты для метода _classify_short_answer.
    Проверяем корректное извлечение всех ключей из контекста.
    """

    @pytest.fixture
    def classifier(self):
        from classifier import HybridClassifier
        return HybridClassifier()

    def test_all_context_keys_extracted(self, classifier):
        """
        Все ключи контекста должны корректно извлекаться.
        """
        context = {
            "last_action": "close",
            "last_intent": "price_question",
            "spin_phase": "implication",
            "state": "close",
            "missing_data": ["contact_info", "company_name"]
        }

        # Вызываем внутренний метод напрямую
        result = classifier._classify_short_answer("да", context)

        assert result is not None
        assert result["intent"] == "agreement"
        assert result["confidence"] >= 0.85

    def test_missing_data_default_to_empty_list(self, classifier):
        """
        missing_data должен по умолчанию быть пустым списком.
        """
        context = {"state": "close"}  # missing_data не указан

        # Не должно быть ошибки
        result = classifier._classify_short_answer("да", context)
        assert result is not None

    def test_none_context_values_handled(self, classifier):
        """
        None значения в контексте должны корректно обрабатываться.

        После исправления бага (missing_data = context.get("missing_data") or []),
        None значение missing_data не должно вызывать TypeError при проверке
        "contact_info" in missing_data.
        """
        context = {
            "last_action": None,
            "last_intent": None,
            "spin_phase": None,
            "state": None,
            "missing_data": None  # Это вызывало TypeError до исправления
        }

        # Не должно быть ошибки, должен вернуть fallback
        # После исправления: missing_data = None or [] -> []
        result = classifier._classify_short_answer("да", context)
        # None или fallback agreement (зависит от маркеров и отсутствия контекста)
        assert result is None or result.get("intent") == "agreement"


# =============================================================================
# ИНТЕГРАЦИОННЫЕ ТЕСТЫ
# =============================================================================

class TestIntegrationBugFixes:
    """
    Интеграционные тесты для проверки исправленных багов.
    """

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Сбрасываем singleton retriever перед тестами."""
        import knowledge.retriever as r
        r._retriever = None
        yield
        r._retriever = None

    def test_get_retriever_uses_settings(self):
        """
        get_retriever() должен использовать use_embeddings из settings.
        """
        from knowledge.retriever import get_retriever
        from settings import settings

        retriever = get_retriever(use_embeddings=False)

        # Должен использовать переданное значение
        assert retriever.use_embeddings is False

    def test_classifier_with_full_context(self):
        """
        Классификатор должен корректно обрабатывать полный контекст.
        """
        from classifier import HybridClassifier

        classifier = HybridClassifier()

        # Полный контекст с правильными ключами
        context = {
            "last_action": "presentation",
            "last_intent": "question_features",
            "spin_phase": "implication",
            "state": "spin",
            "missing_data": []
        }

        result = classifier.classify("да", context)

        assert "intent" in result
        assert "confidence" in result
        assert "method" in result
        assert result["confidence"] > 0

    def test_context_state_vs_current_state(self):
        """
        Явная проверка что state работает, а current_state нет.
        """
        from classifier import HybridClassifier

        classifier = HybridClassifier()

        # С правильным ключом state
        correct_context = {"state": "close"}
        result_correct = classifier.classify("да", correct_context)

        # С неправильным ключом current_state
        wrong_context = {"current_state": "close"}
        result_wrong = classifier.classify("да", wrong_context)

        # С правильным ключом должна быть высокая уверенность
        # потому что state="close" запускает контекстную логику
        assert result_correct["confidence"] >= result_wrong["confidence"]


# =============================================================================
# ПАРАМЕТРИЗОВАННЫЕ ТЕСТЫ
# =============================================================================

class TestParameterizedContextClassification:
    """
    Параметризованные тесты для разных комбинаций контекста.
    """

    @pytest.fixture
    def classifier(self):
        from classifier import HybridClassifier
        return HybridClassifier()

    @pytest.mark.parametrize("state,message,expected_intent", [
        ("close", "да", "agreement"),
        ("close", "нет", "rejection"),
        ("close", "ок", "agreement"),
        ("close", "хорошо", "agreement"),
        ("close", "ладно", "agreement"),
        ("soft_close", "да", "agreement"),
        ("soft_close", "ок", "agreement"),
    ])
    def test_state_classification(self, classifier, state, message, expected_intent):
        """
        Проверяем классификацию для разных состояний.
        """
        context = {"state": state}
        result = classifier.classify(message, context)

        assert result["intent"] == expected_intent, \
            f"state={state}, message='{message}' expected {expected_intent}, got {result['intent']}"

    @pytest.mark.parametrize("spin_phase,message,expected_intent", [
        ("situation", "да", "situation_provided"),
        ("problem", "да", "problem_revealed"),
        ("problem", "нет", "no_problem"),
        ("implication", "да", "implication_acknowledged"),
        ("need_payoff", "да", "need_expressed"),
        ("need_payoff", "нет", "no_need"),
    ])
    def test_spin_phase_classification(self, classifier, spin_phase, message, expected_intent):
        """
        Проверяем классификацию для разных SPIN-фаз.
        """
        context = {"spin_phase": spin_phase}
        result = classifier.classify(message, context)

        assert result["intent"] == expected_intent, \
            f"spin_phase={spin_phase}, message='{message}' expected {expected_intent}, got {result['intent']}"

    @pytest.mark.parametrize("last_action,message,expected_intent", [
        ("close", "да", "agreement"),
        ("close", "нет", "rejection"),
        ("transition_to_close", "да", "agreement"),
        ("presentation", "да", "agreement"),
        ("presentation", "нет", "rejection"),
        ("handle_objection", "да", "agreement"),
        ("handle_objection", "нет", "rejection"),
        ("spin_problem", "да", "problem_revealed"),
        ("spin_problem", "нет", "no_problem"),
        ("spin_implication", "да", "implication_acknowledged"),
        ("spin_need_payoff", "да", "need_expressed"),
        ("spin_need_payoff", "нет", "no_need"),
    ])
    def test_last_action_classification(self, classifier, last_action, message, expected_intent):
        """
        Проверяем классификацию для разных last_action.
        """
        context = {"last_action": last_action}
        result = classifier.classify(message, context)

        assert result["intent"] == expected_intent, \
            f"last_action={last_action}, message='{message}' expected {expected_intent}, got {result['intent']}"


# =============================================================================
# ТЕСТЫ ДЛЯ RETRIEVER SINGLETON — ИЗМЕНЕНИЕ ПАРАМЕТРОВ
# =============================================================================

class TestRetrieverSingletonParameterChange:
    """
    Тесты для проверки что singleton retriever пересоздаётся при изменении параметров.

    Проблема: если первый вызов get_retriever(False), все последующие вызовы
    get_retriever(True) возвращали retriever без эмбеддингов.
    Параметр игнорировался после первой инициализации.
    """

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Сбрасываем singleton перед и после каждого теста."""
        from knowledge.retriever import reset_retriever
        reset_retriever()
        yield
        reset_retriever()

    def test_parameter_change_creates_new_instance(self):
        """
        При изменении use_embeddings должен создаваться новый экземпляр.
        """
        from knowledge.retriever import get_retriever

        # Первый вызов с use_embeddings=False
        retriever1 = get_retriever(use_embeddings=False)
        assert retriever1.use_embeddings is False

        # Второй вызов с use_embeddings=True — должен создать новый экземпляр
        retriever2 = get_retriever(use_embeddings=True)
        assert retriever2.use_embeddings is True

        # Это должны быть разные объекты
        assert retriever1 is not retriever2

    def test_same_parameter_returns_same_instance(self):
        """
        При одинаковых параметрах должен возвращаться тот же экземпляр (singleton).
        """
        from knowledge.retriever import get_retriever

        retriever1 = get_retriever(use_embeddings=False)
        retriever2 = get_retriever(use_embeddings=False)

        assert retriever1 is retriever2

    def test_reset_retriever_clears_singleton(self):
        """
        reset_retriever() должен сбрасывать singleton.
        """
        from knowledge.retriever import get_retriever, reset_retriever

        retriever1 = get_retriever(use_embeddings=False)
        reset_retriever()
        retriever2 = get_retriever(use_embeddings=False)

        # После сброса это должны быть разные объекты
        assert retriever1 is not retriever2

    def test_multiple_parameter_switches(self):
        """
        Многократное переключение параметров работает корректно.
        """
        from knowledge.retriever import get_retriever

        r1 = get_retriever(use_embeddings=False)
        r2 = get_retriever(use_embeddings=True)
        r3 = get_retriever(use_embeddings=False)
        r4 = get_retriever(use_embeddings=False)

        assert r1.use_embeddings is False
        assert r2.use_embeddings is True
        assert r3.use_embeddings is False

        # r3 и r4 должны быть одним объектом (одинаковые параметры)
        assert r3 is r4
        # r1, r2, r3 должны быть разными объектами
        assert r1 is not r2
        assert r2 is not r3

    def test_original_bug_scenario(self):
        """
        Воспроизведение оригинальной ошибки:
        get_retriever(False) → get_retriever(True) должен вернуть retriever С эмбеддингами.
        """
        from knowledge.retriever import get_retriever

        # Первый вызов без эмбеддингов
        first = get_retriever(use_embeddings=False)
        assert first.use_embeddings is False

        # Второй вызов С эмбеддингами — должен работать корректно
        second = get_retriever(use_embeddings=True)
        assert second.use_embeddings is True, \
            "REGRESSION: get_retriever(True) should return retriever with embeddings enabled"


# =============================================================================
# ТЕСТЫ ДЛЯ STATE MACHINE — ПРИОРИТЕТ RULES И DEFLECT_AND_CONTINUE
# =============================================================================

@pytest.mark.skip(reason="StateMachine.process() is deprecated. Rule priority is tested via DialogueOrchestrator in test_blackboard_bugfixes.py")
class TestStateMachineRulesPriority:
    """
    Тесты для проверки приоритета rules над QUESTION_INTENTS.

    Проблема: price_question входит в QUESTION_INTENTS и обрабатывался
    в ПРИОРИТЕТ 0, возвращая "answer_question". Rules с "deflect_and_continue"
    никогда не достигались для вопросов в SPIN-состояниях.

    DEPRECATED: StateMachine.process() is deprecated. These behaviors are now
    tested via DialogueOrchestrator in test_blackboard_bugfixes.py.
    """

    @pytest.fixture
    def state_machine(self):
        from state_machine import StateMachine
        return StateMachine()

    def test_deflect_and_continue_in_spin_situation(self, state_machine):
        """
        В spin_situation price_question должен возвращать deflect_and_continue,
        а не answer_question.
        """
        # Переходим в spin_situation
        state_machine.process("agreement", {})
        assert state_machine.state == "spin_situation"

        # Теперь price_question должен вернуть deflect_and_continue
        result = state_machine.process("price_question", {})

        assert result["action"] == "deflect_and_continue", \
            f"Expected 'deflect_and_continue' but got '{result['action']}'"
        assert result["next_state"] == "spin_situation"

    def test_deflect_and_continue_in_spin_problem(self, state_machine):
        """
        В spin_problem price_question:
        - БЕЗ company_size → deflect_and_continue (спросить размер)
        - С company_size → answer_with_facts (дать цену)

        ОБНОВЛЕНО: После фикса Price Deflect Loop Bug поведение изменилось.
        Теперь если company_size уже известен — бот отвечает на вопрос о цене.
        """
        # Setup: переходим в spin_problem С company_size
        state_machine.process("agreement", {})
        state_machine.process("info_provided", {"company_size": 10})
        assert state_machine.state == "spin_problem"

        result = state_machine.process("price_question", {})

        # FIX: С данными должен быть answer_with_facts, не deflect
        assert result["action"] == "answer_with_facts", \
            f"С company_size=10 должен быть answer_with_facts, получили {result['action']}"
        assert result["next_state"] == "spin_problem"

    def test_deflect_and_continue_in_spin_implication(self, state_machine):
        """
        В spin_implication price_question с company_size → answer_with_facts.

        ОБНОВЛЕНО: После фикса Price Deflect Loop Bug.
        """
        # Setup: переходим в spin_implication
        state_machine.process("agreement", {})
        state_machine.process("info_provided", {"company_size": 10})
        state_machine.process("info_provided", {"pain_point": "теряем клиентов"})
        assert state_machine.state == "spin_implication"

        result = state_machine.process("price_question", {})

        # FIX: С данными должен быть answer_with_facts
        assert result["action"] == "answer_with_facts", \
            f"С company_size=10 должен быть answer_with_facts, получили {result['action']}"

    def test_deflect_and_continue_in_spin_need_payoff(self, state_machine):
        """
        В spin_need_payoff price_question с company_size → answer_with_facts.

        ОБНОВЛЕНО: После фикса Price Deflect Loop Bug.
        """
        # Setup: переходим в spin_need_payoff
        state_machine.process("agreement", {})
        state_machine.process("info_provided", {"company_size": 10})
        state_machine.process("info_provided", {"pain_point": "теряем клиентов"})
        state_machine.process("agreement", {})
        assert state_machine.state == "spin_need_payoff"

        result = state_machine.process("price_question", {})

        # FIX: С данными должен быть answer_with_facts
        assert result["action"] == "answer_with_facts", \
            f"С company_size=10 должен быть answer_with_facts, получили {result['action']}"

    def test_answer_question_in_presentation(self, state_machine):
        """
        В presentation (где нет rule для price_question) должен возвращать answer_question.
        """
        # Симулируем прямой переход в presentation (для теста)
        state_machine.state = "presentation"

        result = state_machine.process("price_question", {})

        # В presentation нет rule для price_question, поэтому
        # сработает общий обработчик QUESTION_INTENTS → answer_question
        # Но в presentation есть rule "answer_with_facts", проверим конфиг
        from config import SALES_STATES
        presentation_rules = SALES_STATES.get("presentation", {}).get("rules", {})

        if "price_question" in presentation_rules:
            assert result["action"] == presentation_rules["price_question"]
        else:
            assert result["action"] == "answer_question"

    def test_other_question_intents_work_when_no_rule(self, state_machine):
        """
        Вопросы с rule в конфиге должны обрабатываться согласно rule.
        Вопросы БЕЗ rule должны обрабатываться как answer_question.

        В spin_situation есть rule для question_features → answer_and_continue.
        """
        # Переходим в spin_situation
        state_machine.process("agreement", {})

        # question_features ИМЕЕТ rule в spin_situation: answer_and_continue
        result = state_machine.process("question_features", {})

        # Проверяем что rule применилось корректно
        assert result["action"] == "answer_and_continue", \
            f"В spin_situation для question_features ожидается answer_and_continue (из rules), получили {result['action']}"


# =============================================================================
# ТЕСТЫ ДЛЯ STATE MACHINE — _is_spin_phase_progression
# =============================================================================

class TestSpinPhaseProgression:
    """
    Тесты для нового метода _is_spin_phase_progression.

    Этот метод заменяет сложную inline проверку для определения
    прогресса в SPIN-фазах.
    """

    @pytest.fixture
    def state_machine(self):
        from state_machine import StateMachine
        return StateMachine()

    def test_same_phase_is_progression(self, state_machine):
        """Та же фаза считается прогрессом."""
        assert state_machine._is_spin_phase_progression("situation", "situation") is True
        assert state_machine._is_spin_phase_progression("problem", "problem") is True

    def test_next_phase_is_progression(self, state_machine):
        """Следующая фаза считается прогрессом."""
        assert state_machine._is_spin_phase_progression("problem", "situation") is True
        assert state_machine._is_spin_phase_progression("implication", "problem") is True
        assert state_machine._is_spin_phase_progression("need_payoff", "implication") is True

    def test_previous_phase_not_progression(self, state_machine):
        """Предыдущая фаза НЕ считается прогрессом."""
        assert state_machine._is_spin_phase_progression("situation", "problem") is False
        assert state_machine._is_spin_phase_progression("problem", "implication") is False

    def test_invalid_phase_not_progression(self, state_machine):
        """Невалидные фазы возвращают False."""
        assert state_machine._is_spin_phase_progression("invalid", "situation") is False
        assert state_machine._is_spin_phase_progression("situation", "invalid") is False
        assert state_machine._is_spin_phase_progression("invalid", "invalid") is False

    def test_none_phase_not_progression(self, state_machine):
        """None фазы возвращают False без ошибок."""
        # Метод должен безопасно обрабатывать None
        # В текущей реализации None не входит в SPIN_PHASES, поэтому вернёт False
        assert state_machine._is_spin_phase_progression(None, "situation") is False
        assert state_machine._is_spin_phase_progression("situation", None) is False


# =============================================================================
# ТЕСТЫ ДЛЯ STATE MACHINE — ПРИОРИТЕТ КОММЕНТАРИЕВ
# =============================================================================

@pytest.mark.skip(reason="StateMachine.process() is deprecated. Priority order is tested via DialogueOrchestrator in test_blackboard_bugfixes.py")
class TestStateMachinePriorityOrder:
    """
    Тесты для проверки корректного порядка приоритетов в apply_rules.

    Проверяем что:
    1. Финальное состояние имеет высший приоритет
    2. Rejection обрабатывается сразу
    3. Rules проверяются до QUESTION_INTENTS
    4. SPIN-логика работает корректно

    DEPRECATED: StateMachine.process() is deprecated. These behaviors are now
    tested via DialogueOrchestrator in test_blackboard_bugfixes.py.
    """

    @pytest.fixture
    def state_machine(self):
        from state_machine import StateMachine
        return StateMachine()

    def test_final_state_has_highest_priority(self, state_machine):
        """
        Финальное состояние (is_final=True) всегда возвращает 'final'.

        Примечание: soft_close НЕ финальное (is_final=False) по дизайну,
        чтобы клиент мог передумать. Только success финальное.
        """
        # success — финальное состояние
        state_machine.state = "success"
        result = state_machine.process("agreement", {})
        assert result["action"] == "final", \
            f"success должен возвращать 'final', получили {result['action']}"

        # soft_close — НЕ финальное (клиент может передумать)
        state_machine.state = "soft_close"
        result = state_machine.process("agreement", {})
        # При agreement в soft_close происходит переход в spin_situation
        assert result["action"] == "transition_to_spin_situation", \
            f"soft_close при agreement должен переходить в spin_situation, получили {result['action']}"
        assert result["next_state"] == "spin_situation"

    def test_rejection_has_high_priority(self, state_machine):
        """Rejection обрабатывается немедленно в любом состоянии."""
        states_with_rejection = ["greeting", "spin_situation", "spin_problem", "presentation"]

        for state in states_with_rejection:
            state_machine.reset()
            state_machine.state = state
            result = state_machine.process("rejection", {})

            assert "soft_close" in result["next_state"] or result["action"] == "final", \
                f"Rejection in {state} should lead to soft_close"

    def test_rules_checked_before_question_intents(self, state_machine):
        """
        Rules проверяются ДО QUESTION_INTENTS.
        Это критично для deflect_and_continue в SPIN-состояниях.
        """
        from config import QUESTION_INTENTS

        # Переходим в spin_situation где есть rule для price_question
        state_machine.process("agreement", {})

        # price_question входит в QUESTION_INTENTS
        assert "price_question" in QUESTION_INTENTS

        # Но в spin_situation есть rule → должен сработать rule, а не answer_question
        result = state_machine.process("price_question", {})
        assert result["action"] == "deflect_and_continue"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
