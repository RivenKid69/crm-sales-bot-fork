"""
Тесты для CompositeMessageRefinementLayer.

Покрытие:
- Детекция составных сообщений (данные + мета-сигналы)
- Приоритизация извлечения данных над мета-интентами
- Разрешение амбигуозных паттернов
- Flow-agnostic работа (SPIN, BANT, custom flows)
- Fail-safe поведение
- Интеграция с UnifiedClassifier pipeline

Примеры проблемных кейсов:
- "5 человек, больше не нужно, быстрее" → info_provided (не objection_think)
- "10, хватит" → info_provided (не rejection)
- "Команда из 3, достаточно" → situation_provided (не unclear)
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from classifier.composite_refinement import (
    CompositeMessageRefinementLayer,
    CompositeMessageContext,
    CompositeRefinementResult,
    create_composite_message_context,
)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def layer():
    """Create CompositeMessageRefinementLayer instance."""
    return CompositeMessageRefinementLayer()


@pytest.fixture
def mock_config():
    """Mock configuration for testing."""
    return {
        "enabled": True,
        "min_confidence_for_refinement": 0.75,
        "default_data_intent": "info_provided",
        "action_expects_data": {
            "ask_about_company": "company_size",
            "ask_about_team_size": "company_size",
            "ask_situation": "company_size",
            "ask_about_problem": "pain_point",
        },
        "action_data_intent": {
            "ask_about_company": "situation_provided",
            "ask_about_team_size": "situation_provided",
            "ask_situation": "situation_provided",
            "ask_about_problem": "problem_revealed",
        },
        "data_expecting_states": [
            "spin_situation",
            "spin_problem",
            "data_collection",
        ],
        "data_expecting_phases": [
            "situation",
            "problem",
            "data_collection",
        ],
        "data_fields": {
            "company_size": {
                "type": "int",
                "min": 1,
                "max": 10000,
                "extract_patterns": [
                    r"(\d+)\s*(?:человек|чел\.?|сотрудник)",
                ],
            },
        },
        "meta_signals": {
            "request_brevity": {
                "patterns": ["быстр", "коротк"],
            },
        },
        "ambiguous_patterns": {
            "bolshe_ne_nuzhno": {
                "patterns": [r"больше\s+не\s+(?:нужно|надо)"],
                "data_resolving_actions": ["ask_about_company", "ask_about_team_size"],
                "rejection_resolving_actions": ["offer_demo", "ask_for_contact"],
            },
        },
    }


# =============================================================================
# Basic Initialization Tests
# =============================================================================

class TestCompositeRefinementLayerInit:
    """Тесты инициализации CompositeMessageRefinementLayer."""

    def test_create_layer(self, layer):
        """Создание экземпляра."""
        assert layer is not None
        assert layer._enabled is True

    def test_layer_has_compiled_patterns(self, layer):
        """Паттерны скомпилированы при инициализации."""
        # Should have at least some compiled patterns from config
        assert isinstance(layer._compiled_patterns, dict)

    def test_layer_has_config(self, layer):
        """Конфигурация загружена."""
        assert layer._config is not None
        assert isinstance(layer._config, dict)

    def test_layer_stats_initialized(self, layer):
        """Статистика инициализирована."""
        stats = layer.get_stats()
        assert stats["refinements_total"] == 0
        assert stats["enabled"] is True


# =============================================================================
# Context Creation Tests
# =============================================================================

class TestCompositeMessageContext:
    """Тесты создания контекста."""

    def test_create_context_minimal(self):
        """Минимальный контекст."""
        ctx = CompositeMessageContext(
            message="5 человек",
            intent="objection_think",
            confidence=0.7,
        )
        assert ctx.message == "5 человек"
        assert ctx.intent == "objection_think"
        assert ctx.confidence == 0.7
        assert ctx.current_phase is None
        assert ctx.last_action is None

    def test_create_context_full(self):
        """Полный контекст."""
        ctx = CompositeMessageContext(
            message="5 человек, больше не нужно",
            intent="objection_think",
            confidence=0.75,
            current_phase="situation",
            state="spin_situation",
            last_action="ask_about_company",
            extracted_data={"key": "value"},
            turn_number=3,
            expects_data_type="company_size",
        )
        assert ctx.current_phase == "situation"
        assert ctx.state == "spin_situation"
        assert ctx.last_action == "ask_about_company"
        assert ctx.extracted_data == {"key": "value"}
        assert ctx.turn_number == 3
        assert ctx.expects_data_type == "company_size"

    def test_context_is_frozen(self):
        """Контекст неизменяемый (frozen dataclass)."""
        ctx = CompositeMessageContext(
            message="test",
            intent="test",
            confidence=0.5,
        )
        with pytest.raises(Exception):  # FrozenInstanceError
            ctx.message = "new"

    def test_create_context_from_dict(self):
        """Создание контекста из словаря."""
        context_dict = {
            "spin_phase": "situation",
            "state": "spin_situation",
            "last_action": "ask_about_company",
            "extracted_data": {},
            "turn_number": 5,
        }
        ctx = create_composite_message_context(
            message="5 человек",
            intent="objection_think",
            confidence=0.7,
            context=context_dict,
        )
        assert ctx.current_phase == "situation"  # Extracted from spin_phase
        assert ctx.state == "spin_situation"
        assert ctx.last_action == "ask_about_company"


# =============================================================================
# Should Refine Tests
# =============================================================================

class TestShouldRefine:
    """Тесты метода should_refine."""

    def test_should_not_refine_when_disabled(self, layer):
        """Не рефайнит когда отключен."""
        layer._enabled = False
        ctx = CompositeMessageContext(
            message="5 человек",
            intent="objection_think",
            confidence=0.7,
            last_action="ask_about_company",
        )
        assert layer.should_refine(ctx) is False

    def test_should_not_refine_non_refinable_intent(self, layer):
        """Не рефайнит не-refinable интенты."""
        ctx = CompositeMessageContext(
            message="5 человек",
            intent="situation_provided",  # Already correct intent
            confidence=0.9,
            last_action="ask_about_company",
        )
        assert layer.should_refine(ctx) is False

    def test_should_not_refine_without_data(self, layer):
        """Не рефайнит если нет данных в сообщении."""
        ctx = CompositeMessageContext(
            message="не интересно",  # No extractable data
            intent="objection_think",
            confidence=0.7,
            last_action="ask_about_company",
        )
        assert layer.should_refine(ctx) is False

    def test_should_refine_with_data_and_action(self, layer):
        """Рефайнит при наличии данных и data-expecting action."""
        ctx = CompositeMessageContext(
            message="5 человек",
            intent="objection_think",
            confidence=0.7,
            last_action="ask_about_company",
        )
        assert layer.should_refine(ctx) is True

    def test_should_refine_with_data_and_state(self, layer):
        """Рефайнит при наличии данных и data-expecting state."""
        ctx = CompositeMessageContext(
            message="5 человек",
            intent="objection_think",
            confidence=0.7,
            state="spin_situation",
        )
        assert layer.should_refine(ctx) is True

    def test_should_refine_with_data_and_phase(self, layer):
        """Рефайнит при наличии данных и data-expecting phase."""
        ctx = CompositeMessageContext(
            message="5 человек",
            intent="objection_think",
            confidence=0.7,
            current_phase="situation",
        )
        assert layer.should_refine(ctx) is True

    def test_should_refine_with_expects_data_type_hint(self, layer):
        """Рефайнит при наличии явного hints expects_data_type."""
        ctx = CompositeMessageContext(
            message="5 человек",
            intent="objection_think",
            confidence=0.7,
            expects_data_type="company_size",
        )
        assert layer.should_refine(ctx) is True


# =============================================================================
# Core Refinement Tests - Main Use Cases
# =============================================================================

class TestCompositeRefinementCore:
    """Основные тесты рефайнмента составных сообщений."""

    def test_refine_company_size_with_ambiguity(self, layer):
        """
        Ключевой тест: "5 человек, больше не нужно, быстрее"
        Должно быть: situation_provided с company_size=5
        НЕ: objection_think
        """
        ctx = CompositeMessageContext(
            message="5 человек, больше не нужно, быстрее",
            intent="objection_think",
            confidence=0.75,
            current_phase="situation",
            state="spin_situation",
            last_action="ask_about_company",
        )
        llm_result = {
            "intent": "objection_think",
            "confidence": 0.75,
            "extracted_data": {},
        }

        result = layer.refine("5 человек, больше не нужно, быстрее", llm_result, ctx)

        assert result["refined"] is True
        assert result["intent"] == "situation_provided"
        assert result["extracted_data"]["company_size"] == 5
        assert result["original_intent"] == "objection_think"
        assert result["refinement_layer"] == "composite"

    def test_refine_number_only_in_data_context(self, layer):
        """Просто число в контексте ожидания данных → info_provided."""
        ctx = CompositeMessageContext(
            message="10",
            intent="unclear",
            confidence=0.3,
            last_action="ask_about_company",
        )
        llm_result = {
            "intent": "unclear",
            "confidence": 0.3,
            "extracted_data": {},
        }

        result = layer.refine("10", llm_result, ctx)

        assert result["refined"] is True
        assert result["extracted_data"].get("company_size") == 10

    def test_refine_preserves_secondary_signals(self, layer):
        """Мета-сигналы сохраняются в secondary_signals."""
        ctx = CompositeMessageContext(
            message="5 человек, быстрее пожалуйста",
            intent="objection_think",
            confidence=0.7,
            last_action="ask_about_company",
        )
        llm_result = {
            "intent": "objection_think",
            "confidence": 0.7,
            "extracted_data": {},
        }

        result = layer.refine("5 человек, быстрее пожалуйста", llm_result, ctx)

        assert result["refined"] is True
        # Should detect request_brevity as secondary signal
        if "secondary_signals" in result:
            assert "request_brevity" in result["secondary_signals"]

    def test_no_refine_when_no_data_context(self, layer):
        """Не рефайнит если нет data-expecting контекста."""
        ctx = CompositeMessageContext(
            message="5 человек",
            intent="objection_think",
            confidence=0.7,
            last_action="offer_demo",  # Not a data-expecting action
        )
        llm_result = {
            "intent": "objection_think",
            "confidence": 0.7,
            "extracted_data": {},
        }

        result = layer.refine("5 человек", llm_result, ctx)

        assert result.get("refined", False) is False
        assert result["intent"] == "objection_think"

    def test_refine_merges_with_existing_extracted_data(self, layer):
        """Новые данные мержатся с существующими."""
        ctx = CompositeMessageContext(
            message="5 человек",
            intent="objection_think",
            confidence=0.7,
            last_action="ask_about_company",
            extracted_data={"existing_field": "value"},
        )
        llm_result = {
            "intent": "objection_think",
            "confidence": 0.7,
            "extracted_data": {"existing_field": "value"},
        }

        result = layer.refine("5 человек", llm_result, ctx)

        assert result["refined"] is True
        assert result["extracted_data"]["existing_field"] == "value"
        assert result["extracted_data"]["company_size"] == 5


# =============================================================================
# Ambiguity Resolution Tests
# =============================================================================

class TestAmbiguityResolution:
    """Тесты разрешения амбигуозных паттернов."""

    def test_bolshe_ne_nuzhno_as_quantity_clarification(self, layer):
        """
        "больше не нужно" после вопроса о количестве → quantity clarification.
        """
        ctx = CompositeMessageContext(
            message="5, больше не нужно",
            intent="rejection",
            confidence=0.8,
            last_action="ask_about_company",
        )
        llm_result = {
            "intent": "rejection",
            "confidence": 0.8,
            "extracted_data": {},
        }

        result = layer.refine("5, больше не нужно", llm_result, ctx)

        assert result["refined"] is True
        # Should resolve as quantity clarification, not rejection
        assert result["intent"] != "rejection"

    def test_hvatit_as_quantity_limit(self, layer):
        """
        "10, хватит" → quantity limit (info_provided).
        """
        ctx = CompositeMessageContext(
            message="10, хватит",
            intent="rejection",
            confidence=0.7,
            last_action="ask_about_team_size",
        )
        llm_result = {
            "intent": "rejection",
            "confidence": 0.7,
            "extracted_data": {},
        }

        result = layer.refine("10, хватит", llm_result, ctx)

        assert result["refined"] is True
        assert result["extracted_data"].get("company_size") == 10


# =============================================================================
# Flow-Agnostic Tests
# =============================================================================

class TestFlowAgnostic:
    """Тесты универсальности (работа с любым flow)."""

    def test_works_with_spin_phase(self, layer):
        """Работает с SPIN phase."""
        ctx = CompositeMessageContext(
            message="5 человек",
            intent="objection_think",
            confidence=0.7,
            current_phase="situation",  # SPIN phase
        )
        llm_result = {"intent": "objection_think", "confidence": 0.7}

        result = layer.refine("5 человек", llm_result, ctx)
        assert result["refined"] is True

    def test_works_with_generic_phase(self, layer):
        """Работает с generic phase (data_collection)."""
        ctx = CompositeMessageContext(
            message="5 человек",
            intent="objection_think",
            confidence=0.7,
            current_phase="data_collection",
        )
        llm_result = {"intent": "objection_think", "confidence": 0.7}

        result = layer.refine("5 человек", llm_result, ctx)
        assert result["refined"] is True

    def test_works_with_action_only(self, layer):
        """Работает только с action, без phase/state."""
        ctx = CompositeMessageContext(
            message="5 человек",
            intent="objection_think",
            confidence=0.7,
            last_action="ask_about_company",
            # No phase, no state
        )
        llm_result = {"intent": "objection_think", "confidence": 0.7}

        result = layer.refine("5 человек", llm_result, ctx)
        assert result["refined"] is True

    def test_works_with_expects_data_type_only(self, layer):
        """Работает только с expects_data_type hint."""
        ctx = CompositeMessageContext(
            message="5 человек",
            intent="objection_think",
            confidence=0.7,
            expects_data_type="company_size",
            # No action, no phase, no state
        )
        llm_result = {"intent": "objection_think", "confidence": 0.7}

        result = layer.refine("5 человек", llm_result, ctx)
        assert result["refined"] is True


# =============================================================================
# Fail-Safe Tests
# =============================================================================

class TestFailSafe:
    """Тесты отказоустойчивости."""

    def test_returns_original_on_exception(self, layer):
        """Возвращает оригинальный результат при исключении."""
        ctx = CompositeMessageContext(
            message="5 человек",
            intent="objection_think",
            confidence=0.7,
            last_action="ask_about_company",
        )
        llm_result = {
            "intent": "objection_think",
            "confidence": 0.7,
        }

        # Mock _analyze_message to raise exception
        with patch.object(layer, "_analyze_message", side_effect=Exception("Test error")):
            result = layer.refine("5 человек", llm_result, ctx)

        # Should return original result
        assert result["intent"] == "objection_think"
        assert result.get("refined") is not True

    def test_handles_empty_config(self):
        """Работает с пустой конфигурацией."""
        with patch("src.classifier.composite_refinement.get_composite_refinement_config",
                   return_value={}):
            layer = CompositeMessageRefinementLayer()
            assert layer is not None
            assert layer._enabled is True  # Default

    def test_handles_invalid_pattern(self):
        """Обрабатывает невалидные regex паттерны."""
        with patch("src.classifier.composite_refinement.get_composite_refinement_config",
                   return_value={
                       "enabled": True,
                       "data_fields": {
                           "test": {
                               "type": "int",
                               "extract_patterns": ["[invalid(regex"],  # Invalid
                           }
                       }
                   }):
            # Should not crash, just log warning
            layer = CompositeMessageRefinementLayer()
            assert layer is not None


# =============================================================================
# Statistics Tests
# =============================================================================

class TestStatistics:
    """Тесты статистики."""

    def test_stats_increment_on_refinement(self, layer):
        """Статистика увеличивается при рефайнменте."""
        initial_stats = layer.get_stats()
        initial_total = initial_stats["refinements_total"]

        ctx = CompositeMessageContext(
            message="5 человек",
            intent="objection_think",
            confidence=0.7,
            last_action="ask_about_company",
        )
        llm_result = {"intent": "objection_think", "confidence": 0.7}

        layer.refine("5 человек", llm_result, ctx)

        new_stats = layer.get_stats()
        assert new_stats["refinements_total"] == initial_total + 1

    def test_stats_by_type_tracked(self, layer):
        """Статистика по типам отслеживается."""
        ctx = CompositeMessageContext(
            message="5 человек",
            intent="objection_think",
            confidence=0.7,
            last_action="ask_about_company",
        )
        llm_result = {"intent": "objection_think", "confidence": 0.7}

        layer.refine("5 человек", llm_result, ctx)

        stats = layer.get_stats()
        assert "objection_think" in stats["refinements_by_type"]


# =============================================================================
# Data Extraction Tests
# =============================================================================

class TestDataExtraction:
    """Тесты извлечения данных."""

    def test_extract_company_size_with_chelovek(self, layer):
        """Извлечение company_size: 'N человек'."""
        ctx = CompositeMessageContext(
            message="у нас 15 человек",
            intent="unclear",
            confidence=0.3,
            last_action="ask_about_company",
        )
        llm_result = {"intent": "unclear", "confidence": 0.3}

        result = layer.refine("у нас 15 человек", llm_result, ctx)

        assert result["refined"] is True
        assert result["extracted_data"]["company_size"] == 15

    def test_extract_company_size_number_only(self, layer):
        """Извлечение company_size: просто число."""
        ctx = CompositeMessageContext(
            message="5",
            intent="unclear",
            confidence=0.3,
            last_action="ask_about_company",
        )
        llm_result = {"intent": "unclear", "confidence": 0.3}

        result = layer.refine("5", llm_result, ctx)

        assert result["refined"] is True
        assert result["extracted_data"]["company_size"] == 5

    def test_extract_company_size_with_comma(self, layer):
        """Извлечение company_size: '5, ...'."""
        ctx = CompositeMessageContext(
            message="5, больше не нужно",
            intent="rejection",
            confidence=0.7,
            last_action="ask_about_company",
        )
        llm_result = {"intent": "rejection", "confidence": 0.7}

        result = layer.refine("5, больше не нужно", llm_result, ctx)

        assert result["refined"] is True
        assert result["extracted_data"]["company_size"] == 5

    def test_validates_company_size_bounds(self, layer):
        """Валидация границ company_size (1-10000)."""
        # Too small (0)
        ctx = CompositeMessageContext(
            message="0 человек",
            intent="unclear",
            confidence=0.3,
            last_action="ask_about_company",
        )
        llm_result = {"intent": "unclear", "confidence": 0.3}

        result = layer.refine("0 человек", llm_result, ctx)
        # Should not extract invalid value
        assert result.get("extracted_data", {}).get("company_size") is None or result.get("refined") is False


# =============================================================================
# Integration with UnifiedClassifier
# =============================================================================

class TestUnifiedClassifierIntegration:
    """Тесты интеграции с UnifiedClassifier."""

    def test_unified_classifier_has_composite_refinement_layer(self):
        """UnifiedClassifier имеет composite_refinement_layer."""
        from classifier.unified import UnifiedClassifier
        from feature_flags import flags

        classifier = UnifiedClassifier()

        # Enable composite_refinement
        flags.set_override("composite_refinement", True)

        # Access lazy-loaded layer
        layer = classifier.composite_refinement_layer

        assert layer is not None
        assert isinstance(layer, CompositeMessageRefinementLayer)

        # Cleanup
        flags.clear_override("composite_refinement")

    def test_pipeline_position(self):
        """Composite refinement в правильной позиции pipeline."""
        from classifier.unified import UnifiedClassifier

        classifier = UnifiedClassifier()

        # Check docstring mentions composite refinement in correct order
        docstring = classifier.classify.__doc__
        assert "Composite message refinement" in docstring

        # Verify step numbers in comments (optional - implementation detail)
        import inspect
        source = inspect.getsource(classifier.classify)
        assert "Step 3: Composite message refinement" in source


# =============================================================================
# Edge Cases
# =============================================================================

class TestEdgeCases:
    """Краевые случаи."""

    def test_very_long_message(self, layer):
        """Очень длинное сообщение."""
        long_message = "5 человек " + "бла " * 1000
        ctx = CompositeMessageContext(
            message=long_message,
            intent="objection_think",
            confidence=0.7,
            last_action="ask_about_company",
        )
        llm_result = {"intent": "objection_think", "confidence": 0.7}

        result = layer.refine(long_message, llm_result, ctx)

        # Should still work
        assert result is not None

    def test_unicode_message(self, layer):
        """Сообщение с Unicode."""
        ctx = CompositeMessageContext(
            message="5 человек 😊",
            intent="objection_think",
            confidence=0.7,
            last_action="ask_about_company",
        )
        llm_result = {"intent": "objection_think", "confidence": 0.7}

        result = layer.refine("5 человек 😊", llm_result, ctx)

        assert result["refined"] is True
        assert result["extracted_data"]["company_size"] == 5

    def test_empty_message(self, layer):
        """Пустое сообщение."""
        ctx = CompositeMessageContext(
            message="",
            intent="unclear",
            confidence=0.3,
            last_action="ask_about_company",
        )
        llm_result = {"intent": "unclear", "confidence": 0.3}

        result = layer.refine("", llm_result, ctx)

        # Should not crash, no refinement
        assert result.get("refined", False) is False

    def test_whitespace_only_message(self, layer):
        """Сообщение только из пробелов."""
        ctx = CompositeMessageContext(
            message="   ",
            intent="unclear",
            confidence=0.3,
            last_action="ask_about_company",
        )
        llm_result = {"intent": "unclear", "confidence": 0.3}

        result = layer.refine("   ", llm_result, ctx)

        # Should not crash, no refinement
        assert result.get("refined", False) is False

    def test_multiple_numbers_takes_first_valid(self, layer):
        """Несколько чисел - берётся первое валидное."""
        ctx = CompositeMessageContext(
            message="5 человек, а раньше было 10",
            intent="objection_think",
            confidence=0.7,
            last_action="ask_about_company",
        )
        llm_result = {"intent": "objection_think", "confidence": 0.7}

        result = layer.refine("5 человек, а раньше было 10", llm_result, ctx)

        assert result["refined"] is True
        # Should take 5 (first match with "человек")
        assert result["extracted_data"]["company_size"] == 5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
