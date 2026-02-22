"""Тесты LLM классификатора."""
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

class TestSchemas:
    """Тесты Pydantic схем."""

    def test_intent_type_valid(self):
        """Проверка валидных интентов."""
        from src.classifier.llm.schemas import ClassificationResult

        result = ClassificationResult(
            intent="greeting",
            confidence=0.95,
            reasoning="Пользователь поздоровался"
        )
        assert result.intent == "greeting"
        assert result.confidence == 0.95

    def test_intent_type_invalid(self):
        """Проверка невалидных интентов."""
        from src.classifier.llm.schemas import ClassificationResult

        with pytest.raises(ValidationError):
            ClassificationResult(
                intent="invalid_intent",  # Не существует
                confidence=0.95,
                reasoning="test"
            )

    def test_confidence_bounds(self):
        """Проверка границ confidence."""
        from src.classifier.llm.schemas import ClassificationResult

        # Валидные границы
        result = ClassificationResult(intent="greeting", confidence=0.0, reasoning="test")
        assert result.confidence == 0.0

        result = ClassificationResult(intent="greeting", confidence=1.0, reasoning="test")
        assert result.confidence == 1.0

        # Невалидные границы
        with pytest.raises(ValidationError):
            ClassificationResult(intent="greeting", confidence=1.5, reasoning="test")

        with pytest.raises(ValidationError):
            ClassificationResult(intent="greeting", confidence=-0.1, reasoning="test")

    def test_extracted_data_optional(self):
        """Проверка опциональности extracted_data."""
        from src.classifier.llm.schemas import ClassificationResult, ExtractedData

        # Без extracted_data
        result = ClassificationResult(
            intent="situation_provided",
            confidence=0.9,
            reasoning="test"
        )
        assert result.extracted_data.company_size is None

        # С extracted_data
        result = ClassificationResult(
            intent="situation_provided",
            confidence=0.9,
            reasoning="test",
            extracted_data=ExtractedData(company_size=15, business_type="ресторан")
        )
        assert result.extracted_data.company_size == 15
        assert result.extracted_data.business_type == "ресторан"

    def test_json_serialization(self):
        """Проверка сериализации в JSON."""
        from src.classifier.llm.schemas import ClassificationResult, ExtractedData

        result = ClassificationResult(
            intent="price_question",
            confidence=0.85,
            reasoning="Клиент спрашивает о цене",
            extracted_data=ExtractedData(company_size=10)
        )

        # Сериализация
        json_str = result.model_dump_json()
        assert "price_question" in json_str
        assert "0.85" in json_str

        # Десериализация
        restored = ClassificationResult.model_validate_json(json_str)
        assert restored.intent == "price_question"
        assert restored.confidence == 0.85

    def test_all_34_intents_exist(self):
        """Проверка что все 34 интента определены (включая request_brevity)."""
        import typing
        from src.classifier.llm.schemas import IntentType

        intents = typing.get_args(IntentType)
        assert len(intents) == 34
        # Проверяем что новый интент request_brevity добавлен
        assert "request_brevity" in intents

    def test_pain_category_valid(self):
        """Проверка валидных категорий боли."""
        from src.classifier.llm.schemas import ExtractedData

        data = ExtractedData(pain_category="losing_clients")
        assert data.pain_category == "losing_clients"

        data = ExtractedData(pain_category="no_control")
        assert data.pain_category == "no_control"

        data = ExtractedData(pain_category="manual_work")
        assert data.pain_category == "manual_work"

    def test_pain_category_invalid(self):
        """Проверка невалидных категорий боли."""
        from src.classifier.llm.schemas import ExtractedData

        with pytest.raises(ValidationError):
            ExtractedData(pain_category="invalid_category")

    def test_extracted_data_all_fields(self):
        """Проверка всех полей ExtractedData."""
        from src.classifier.llm.schemas import ExtractedData

        data = ExtractedData(
            company_size=50,
            business_type="IT компания",
            current_tools="Excel, Битрикс24",
            pain_point="теряем клиентов",
            pain_category="losing_clients",
            pain_impact="снижение выручки",
            financial_impact="потеря 500к в месяц",
            contact_info="+7 999 123 45 67",
            desired_outcome="автоматизация",
            value_acknowledged=True
        )

        assert data.company_size == 50
        assert data.business_type == "IT компания"
        assert data.current_tools == "Excel, Битрикс24"
        assert data.pain_point == "теряем клиентов"
        assert data.pain_category == "losing_clients"
        assert data.pain_impact == "снижение выручки"
        assert data.financial_impact == "потеря 500к в месяц"
        assert data.contact_info == "+7 999 123 45 67"
        assert data.desired_outcome == "автоматизация"
        assert data.value_acknowledged is True

    def test_classification_result_required_fields(self):
        """Проверка обязательных полей ClassificationResult."""
        from src.classifier.llm.schemas import ClassificationResult

        # Без intent - ошибка
        with pytest.raises(ValidationError):
            ClassificationResult(confidence=0.9, reasoning="test")

        # Без confidence - ошибка
        with pytest.raises(ValidationError):
            ClassificationResult(intent="greeting", reasoning="test")

        # Без reasoning - ошибка
        with pytest.raises(ValidationError):
            ClassificationResult(intent="greeting", confidence=0.9)

    def test_module_exports(self):
        """Проверка экспортов модуля."""
        from src.classifier.llm import IntentType, ExtractedData, ClassificationResult, PainCategory

        assert IntentType is not None
        assert ExtractedData is not None
        assert ClassificationResult is not None
        assert PainCategory is not None

class TestPrompts:
    """Тесты промптов."""

    def test_system_prompt_has_no_think(self):
        """Проверка  в начале."""
        from src.classifier.llm.prompts import SYSTEM_PROMPT
        assert SYSTEM_PROMPT.startswith("")

    def test_system_prompt_has_all_intents(self):
        """Проверка что все интенты описаны."""
        from src.classifier.llm.prompts import SYSTEM_PROMPT
        from src.classifier.llm.schemas import IntentType
        import typing

        # Получаем все интенты из Literal
        intents = typing.get_args(IntentType)

        for intent in intents:
            assert intent in SYSTEM_PROMPT, f"Intent {intent} not in SYSTEM_PROMPT"

    def test_build_classification_prompt(self):
        """Проверка построения промпта."""
        from src.classifier.llm.prompts import build_classification_prompt

        prompt = build_classification_prompt(
            message="Привет",
            context={"state": "greeting", "spin_phase": "situation"}
        )

        assert "Привет" in prompt
        assert "greeting" in prompt
        assert "situation" in prompt
        assert "" in prompt

    def test_build_classification_prompt_no_context(self):
        """Проверка промпта без контекста."""
        from src.classifier.llm.prompts import build_classification_prompt

        prompt = build_classification_prompt(message="Тест")

        assert "Тест" in prompt
        assert "Нет контекста" in prompt

    def test_build_classification_prompt_all_context_fields(self):
        """Проверка всех полей контекста."""
        from src.classifier.llm.prompts import build_classification_prompt

        prompt = build_classification_prompt(
            message="Сообщение",
            context={
                "state": "spin_situation",
                "spin_phase": "problem",
                "last_action": "задал вопрос",
                "last_intent": "greeting"
            }
        )

        assert "spin_situation" in prompt
        assert "problem" in prompt
        assert "задал вопрос" in prompt
        assert "greeting" in prompt

class TestFewShot:
    """Тесты few-shot примеров."""

    def test_few_shot_examples_valid(self):
        """Проверка валидности few-shot примеров."""
        from src.classifier.llm.few_shot import FEW_SHOT_EXAMPLES
        from src.classifier.llm.schemas import IntentType
        import typing

        valid_intents = set(typing.get_args(IntentType))

        for ex in FEW_SHOT_EXAMPLES:
            assert "message" in ex
            assert "result" in ex
            assert ex["result"]["intent"] in valid_intents, f"Invalid intent: {ex['result']['intent']}"
            assert 0 <= ex["result"]["confidence"] <= 1

    def test_few_shot_examples_count(self):
        """Проверка количества примеров."""
        from src.classifier.llm.few_shot import FEW_SHOT_EXAMPLES

        assert len(FEW_SHOT_EXAMPLES) >= 10

    def test_get_few_shot_prompt(self):
        """Проверка генерации few-shot промпта."""
        from src.classifier.llm.few_shot import get_few_shot_prompt

        prompt = get_few_shot_prompt(n_examples=3)

        assert "Пример 1" in prompt
        assert "Пример 2" in prompt
        assert "Пример 3" in prompt
        assert "Сообщение:" in prompt

    def test_get_few_shot_prompt_limit(self):
        """Проверка лимита примеров."""
        from src.classifier.llm.few_shot import get_few_shot_prompt

        prompt = get_few_shot_prompt(n_examples=2)

        assert "Пример 1" in prompt
        assert "Пример 2" in prompt
        assert "Пример 3" not in prompt

    def test_few_shot_covers_main_categories(self):
        """Проверка покрытия основных категорий."""
        from src.classifier.llm.few_shot import FEW_SHOT_EXAMPLES

        intents = {ex["result"]["intent"] for ex in FEW_SHOT_EXAMPLES}

        # Проверяем что есть примеры для основных категорий
        assert "greeting" in intents
        assert "price_question" in intents
        assert "objection_price" in intents
        assert "situation_provided" in intents
        assert "problem_revealed" in intents
        assert "contact_provided" in intents

class TestLLMClassifier:
    """Тесты LLMClassifier."""

    def test_classify_success(self):
        """Успешная классификация через LLM."""
        from unittest.mock import Mock, MagicMock
        from src.classifier.llm import LLMClassifier, ClassificationResult, ExtractedData

        # Мок VLLMClient
        mock_vllm = Mock()
        mock_result = ClassificationResult(
            intent="greeting",
            confidence=0.95,
            reasoning="Приветствие",
            extracted_data=ExtractedData()
        )
        mock_vllm.generate_structured.return_value = mock_result

        classifier = LLMClassifier(vllm_client=mock_vllm)
        result = classifier.classify("Привет!")

        assert result["intent"] == "greeting"
        assert result["confidence"] == 0.95
        assert result["method"] == "llm"
        assert result["reasoning"] == "Приветствие"
        mock_vllm.generate_structured.assert_called_once()

    def test_classify_fallback_on_none(self):
        """Fallback когда LLM возвращает None."""
        from unittest.mock import Mock
        from src.classifier.llm import LLMClassifier

        # Мок VLLMClient возвращает None
        mock_vllm = Mock()
        mock_vllm.generate_structured.return_value = None

        # Мок fallback классификатора
        mock_fallback = Mock()
        mock_fallback.classify.return_value = {
            "intent": "greeting",
            "confidence": 0.8,
            "extracted_data": {}
        }

        classifier = LLMClassifier(vllm_client=mock_vllm, fallback_classifier=mock_fallback)
        result = classifier.classify("Привет!")

        assert result["method"] == "llm_fallback"
        mock_fallback.classify.assert_called_once()

    def test_classify_fallback_on_exception(self):
        """Fallback при исключении LLM."""
        from unittest.mock import Mock
        from src.classifier.llm import LLMClassifier

        # Мок VLLMClient выбрасывает исключение
        mock_vllm = Mock()
        mock_vllm.generate_structured.side_effect = Exception("LLM Error")

        # Мок fallback классификатора
        mock_fallback = Mock()
        mock_fallback.classify.return_value = {
            "intent": "unclear",
            "confidence": 0.5,
            "extracted_data": {}
        }

        classifier = LLMClassifier(vllm_client=mock_vllm, fallback_classifier=mock_fallback)
        result = classifier.classify("Test message")

        assert result["method"] == "llm_fallback"
        mock_fallback.classify.assert_called_once()

    def test_classify_no_fallback(self):
        """Без fallback возвращает unclear."""
        from unittest.mock import Mock
        from src.classifier.llm import LLMClassifier

        # Мок VLLMClient возвращает None
        mock_vllm = Mock()
        mock_vllm.generate_structured.return_value = None

        classifier = LLMClassifier(vllm_client=mock_vllm, fallback_classifier=None)
        result = classifier.classify("Test")

        assert result["intent"] == "unclear"
        assert result["confidence"] == 0.5
        assert result["method"] == "llm_fallback"

    def test_classify_fallback_also_fails(self):
        """Когда и LLM и fallback падают."""
        from unittest.mock import Mock
        from src.classifier.llm import LLMClassifier

        # Мок VLLMClient возвращает None
        mock_vllm = Mock()
        mock_vllm.generate_structured.return_value = None

        # Мок fallback тоже падает
        mock_fallback = Mock()
        mock_fallback.classify.side_effect = Exception("Fallback Error")

        classifier = LLMClassifier(vllm_client=mock_vllm, fallback_classifier=mock_fallback)
        result = classifier.classify("Test")

        assert result["intent"] == "unclear"
        assert result["confidence"] == 0.3
        assert result["method"] == "llm_fallback"

    def test_stats(self):
        """Проверка статистики."""
        from unittest.mock import Mock
        from src.classifier.llm import LLMClassifier, ClassificationResult, ExtractedData

        mock_vllm = Mock()
        mock_vllm.get_stats_dict.return_value = {"total_requests": 5}

        # Первый вызов - успех
        mock_result = ClassificationResult(
            intent="greeting",
            confidence=0.95,
            reasoning="test",
            extracted_data=ExtractedData()
        )
        mock_vllm.generate_structured.return_value = mock_result

        classifier = LLMClassifier(vllm_client=mock_vllm)
        classifier.classify("Test 1")

        # Второй вызов - None → fallback
        mock_vllm.generate_structured.return_value = None
        classifier.classify("Test 2")

        stats = classifier.get_stats()

        assert stats["llm_calls"] == 2
        assert stats["llm_successes"] == 1
        assert stats["fallback_calls"] == 1
        assert stats["llm_success_rate"] == 50.0
        assert stats["vllm_stats"]["total_requests"] == 5

    def test_classify_with_context(self):
        """Классификация с контекстом."""
        from unittest.mock import Mock, call
        from src.classifier.llm import LLMClassifier, ClassificationResult, ExtractedData

        mock_vllm = Mock()
        mock_result = ClassificationResult(
            intent="agreement",
            confidence=0.9,
            reasoning="Согласие после предложения демо",
            extracted_data=ExtractedData()
        )
        mock_vllm.generate_structured.return_value = mock_result

        classifier = LLMClassifier(vllm_client=mock_vllm)
        result = classifier.classify(
            "Да",
            context={"state": "demo_offer", "last_action": "предложил демо"}
        )

        assert result["intent"] == "agreement"
        # Проверяем что контекст был передан в промпт
        call_args = mock_vllm.generate_structured.call_args
        prompt = call_args[0][0]
        assert "demo_offer" in prompt
        assert "предложил демо" in prompt

    def test_extracted_data_serialization(self):
        """Проверка сериализации extracted_data."""
        from unittest.mock import Mock
        from src.classifier.llm import LLMClassifier, ClassificationResult, ExtractedData

        mock_vllm = Mock()
        mock_result = ClassificationResult(
            intent="situation_provided",
            confidence=0.92,
            reasoning="Клиент описал ситуацию",
            extracted_data=ExtractedData(
                company_size=25,
                business_type="ресторан",
                pain_point=None  # None должен быть исключён
            )
        )
        mock_vllm.generate_structured.return_value = mock_result

        classifier = LLMClassifier(vllm_client=mock_vllm)
        result = classifier.classify("У нас 25 человек, мы ресторан")

        assert result["extracted_data"]["company_size"] == 25
        assert result["extracted_data"]["business_type"] == "ресторан"
        assert "pain_point" not in result["extracted_data"]  # None исключён

    def test_module_exports_classifier(self):
        """Проверка экспорта LLMClassifier из модуля."""
        from src.classifier.llm import LLMClassifier

        assert LLMClassifier is not None

class TestUnifiedClassifier:
    """Тесты UnifiedClassifier."""

    def test_uses_llm_when_flag_true(self):
        """Использует LLM когда флаг включен."""
        from src.classifier.unified import UnifiedClassifier
        from unittest.mock import patch, Mock

        with patch('classifier.unified.flags') as mock_flags:
            mock_flags.llm_classifier = True

            classifier = UnifiedClassifier()

            # Mock LLM classifier
            mock_llm = Mock()
            mock_llm.classify.return_value = {"intent": "greeting", "method": "llm"}
            classifier._llm = mock_llm

            result = classifier.classify("привет")

            assert result["method"] == "llm"
            mock_llm.classify.assert_called_once()

    def test_uses_hybrid_when_flag_false(self):
        """Использует Hybrid когда флаг выключен."""
        from src.classifier.unified import UnifiedClassifier
        from unittest.mock import patch, Mock

        with patch('classifier.unified.flags') as mock_flags:
            mock_flags.llm_classifier = False

            classifier = UnifiedClassifier()

            # Mock Hybrid classifier
            mock_hybrid = Mock()
            mock_hybrid.classify.return_value = {"intent": "greeting", "method": "root"}
            classifier._hybrid = mock_hybrid

            result = classifier.classify("привет")

            mock_hybrid.classify.assert_called_once()

    def test_lazy_loading_hybrid(self):
        """Проверка lazy loading HybridClassifier."""
        from src.classifier.unified import UnifiedClassifier
        from unittest.mock import patch

        with patch('classifier.unified.flags') as mock_flags:
            mock_flags.llm_classifier = False

            classifier = UnifiedClassifier()

            # До первого вызова _hybrid должен быть None
            assert classifier._hybrid is None

            # После обращения к property создаётся
            with patch('classifier.hybrid.HybridClassifier') as MockHybrid:
                MockHybrid.return_value.classify.return_value = {"intent": "greeting"}
                _ = classifier.hybrid
                # Теперь _hybrid должен быть установлен
                assert classifier._hybrid is not None

    def test_lazy_loading_llm(self):
        """Проверка lazy loading LLMClassifier."""
        from src.classifier.unified import UnifiedClassifier
        from unittest.mock import patch, Mock

        with patch('classifier.unified.flags') as mock_flags:
            mock_flags.llm_classifier = True

            classifier = UnifiedClassifier()

            # До первого вызова _llm должен быть None
            assert classifier._llm is None

            # Mock hybrid чтобы избежать реальной инициализации
            classifier._hybrid = Mock()

            with patch('classifier.llm.LLMClassifier') as MockLLM:
                MockLLM.return_value.classify.return_value = {"intent": "greeting"}
                _ = classifier.llm
                assert classifier._llm is not None

    def test_get_stats(self):
        """Проверка получения статистики."""
        from src.classifier.unified import UnifiedClassifier
        from unittest.mock import patch, Mock

        with patch('classifier.unified.flags') as mock_flags:
            mock_flags.llm_classifier = True

            classifier = UnifiedClassifier()

            # Без инициализации LLM
            stats = classifier.get_stats()
            assert stats["active_classifier"] == "llm"
            assert "llm_stats" not in stats

            # С инициализированным LLM
            mock_llm = Mock()
            mock_llm.get_stats.return_value = {"llm_calls": 5}
            classifier._llm = mock_llm

            stats = classifier.get_stats()
            assert stats["llm_stats"]["llm_calls"] == 5

    def test_get_stats_hybrid_mode(self):
        """Проверка статистики в режиме Hybrid."""
        from src.classifier.unified import UnifiedClassifier
        from unittest.mock import patch

        with patch('classifier.unified.flags') as mock_flags:
            mock_flags.llm_classifier = False

            classifier = UnifiedClassifier()
            stats = classifier.get_stats()

            assert stats["active_classifier"] == "hybrid"

    def test_module_exports_unified(self):
        """Проверка экспорта UnifiedClassifier из модуля."""
        from src.classifier import UnifiedClassifier

        assert UnifiedClassifier is not None

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
