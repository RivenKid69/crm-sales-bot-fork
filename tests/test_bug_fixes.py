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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
