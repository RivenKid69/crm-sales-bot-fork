"""Тесты LLM классификатора."""
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


class TestSchemas:
    """Тесты Pydantic схем."""

    def test_intent_type_valid(self):
        """Проверка валидных интентов."""
        from classifier.llm.schemas import ClassificationResult

        result = ClassificationResult(
            intent="greeting",
            confidence=0.95,
            reasoning="Пользователь поздоровался"
        )
        assert result.intent == "greeting"
        assert result.confidence == 0.95

    def test_intent_type_invalid(self):
        """Проверка невалидных интентов."""
        from classifier.llm.schemas import ClassificationResult

        with pytest.raises(ValidationError):
            ClassificationResult(
                intent="invalid_intent",  # Не существует
                confidence=0.95,
                reasoning="test"
            )

    def test_confidence_bounds(self):
        """Проверка границ confidence."""
        from classifier.llm.schemas import ClassificationResult

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
        from classifier.llm.schemas import ClassificationResult, ExtractedData

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
        from classifier.llm.schemas import ClassificationResult, ExtractedData

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

    def test_all_33_intents_exist(self):
        """Проверка что все 33 интента определены."""
        import typing
        from classifier.llm.schemas import IntentType

        intents = typing.get_args(IntentType)
        assert len(intents) == 33

    def test_pain_category_valid(self):
        """Проверка валидных категорий боли."""
        from classifier.llm.schemas import ExtractedData

        data = ExtractedData(pain_category="losing_clients")
        assert data.pain_category == "losing_clients"

        data = ExtractedData(pain_category="no_control")
        assert data.pain_category == "no_control"

        data = ExtractedData(pain_category="manual_work")
        assert data.pain_category == "manual_work"

    def test_pain_category_invalid(self):
        """Проверка невалидных категорий боли."""
        from classifier.llm.schemas import ExtractedData

        with pytest.raises(ValidationError):
            ExtractedData(pain_category="invalid_category")

    def test_extracted_data_all_fields(self):
        """Проверка всех полей ExtractedData."""
        from classifier.llm.schemas import ExtractedData

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
        from classifier.llm.schemas import ClassificationResult

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
        from classifier.llm import IntentType, ExtractedData, ClassificationResult, PainCategory

        assert IntentType is not None
        assert ExtractedData is not None
        assert ClassificationResult is not None
        assert PainCategory is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
