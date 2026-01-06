"""
Тесты для CategoryRouter.

Проверяем:
1. Парсинг JSON ответов
2. Фильтрацию невалидных категорий
3. Fallback при ошибках
4. Ограничение top_k
5. Edge cases (пустой запрос, thinking tags)
"""

import pytest
import sys
import os

# Добавляем путь к src для импортов
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from knowledge.category_router import CategoryRouter


# =============================================================================
# Mock LLM для тестирования
# =============================================================================

class MockLLM:
    """Mock LLM для тестирования CategoryRouter."""

    def __init__(self, response: str = '["pricing", "products"]'):
        self.response = response
        self.last_prompt = None
        self.call_count = 0

    def generate(self, prompt: str) -> str:
        self.last_prompt = prompt
        self.call_count += 1
        return self.response


class ErrorLLM:
    """LLM который выбрасывает исключение."""

    def generate(self, prompt: str) -> str:
        raise RuntimeError("LLM connection error")


# =============================================================================
# Тесты парсинга JSON
# =============================================================================

class TestJsonParsing:
    """Тесты парсинга JSON ответов LLM."""

    def test_parse_clean_json(self):
        """Чистый JSON массив."""
        llm = MockLLM('["pricing", "products"]')
        router = CategoryRouter(llm, top_k=3)
        result = router.route("Сколько стоит?")

        assert result == ["pricing", "products"]

    def test_parse_json_with_text(self):
        """JSON с текстом вокруг."""
        llm = MockLLM('Категории для запроса: ["pricing", "products"]. Это лучший выбор.')
        router = CategoryRouter(llm, top_k=3)
        result = router.route("Сколько стоит?")

        assert result == ["pricing", "products"]

    def test_parse_json_with_thinking_tags(self):
        """JSON с Qwen thinking tags."""
        llm = MockLLM('<think>Нужно определить категории...</think>["pricing", "products"]')
        router = CategoryRouter(llm, top_k=3)
        result = router.route("Сколько стоит?")

        assert result == ["pricing", "products"]

    def test_parse_json_with_newlines(self):
        """JSON с переносами строк."""
        llm = MockLLM('["pricing",\n"products",\n"faq"]')
        router = CategoryRouter(llm, top_k=3)
        result = router.route("Сколько стоит?")

        assert result == ["pricing", "products", "faq"]

    def test_parse_single_category(self):
        """Одна категория."""
        llm = MockLLM('["pricing"]')
        router = CategoryRouter(llm, top_k=3)
        result = router.route("Цена?")

        assert result == ["pricing"]

    def test_parse_invalid_json(self):
        """Невалидный JSON возвращает fallback."""
        llm = MockLLM('pricing, products')  # Не JSON
        router = CategoryRouter(llm, top_k=3)
        result = router.route("Цена?")

        assert result == ["other", "faq"]  # fallback

    def test_parse_empty_response(self):
        """Пустой ответ возвращает fallback."""
        llm = MockLLM('')
        router = CategoryRouter(llm, top_k=3)
        result = router.route("Цена?")

        assert result == ["other", "faq"]  # fallback


# =============================================================================
# Тесты валидации категорий
# =============================================================================

class TestCategoryValidation:
    """Тесты валидации категорий."""

    def test_filter_invalid_categories(self):
        """Невалидные категории фильтруются."""
        llm = MockLLM('["pricing", "invalid_category", "products"]')
        router = CategoryRouter(llm, top_k=3)
        result = router.route("Цена?")

        assert result == ["pricing", "products"]
        assert "invalid_category" not in result

    def test_all_invalid_returns_fallback(self):
        """Если все категории невалидны — fallback."""
        llm = MockLLM('["invalid1", "invalid2"]')
        router = CategoryRouter(llm, top_k=3)
        result = router.route("Цена?")

        assert result == ["other", "faq"]

    def test_all_categories_are_valid(self):
        """Проверка что все CATEGORIES валидны."""
        llm = MockLLM()
        router = CategoryRouter(llm)

        expected_categories = [
            "analytics", "employees", "equipment", "faq", "features",
            "fiscal", "integrations", "inventory", "mobile", "other",
            "pricing", "products", "promotions", "regions", "stability",
            "support", "tis"
        ]

        assert router.CATEGORIES == expected_categories

    def test_get_all_categories(self):
        """get_all_categories() возвращает копию списка."""
        llm = MockLLM()
        router = CategoryRouter(llm)
        categories = router.get_all_categories()

        assert categories == router.CATEGORIES
        assert categories is not router.CATEGORIES  # Копия


# =============================================================================
# Тесты top_k
# =============================================================================

class TestTopK:
    """Тесты ограничения top_k."""

    def test_top_k_limits_results(self):
        """top_k ограничивает количество категорий."""
        llm = MockLLM('["pricing", "products", "faq", "other", "support"]')
        router = CategoryRouter(llm, top_k=2)
        result = router.route("Цена?")

        assert len(result) <= 2
        assert result == ["pricing", "products"]

    def test_top_k_default_is_3(self):
        """По умолчанию top_k = 3."""
        llm = MockLLM()
        router = CategoryRouter(llm)

        assert router.top_k == 3

    def test_top_k_1(self):
        """top_k = 1 возвращает одну категорию."""
        llm = MockLLM('["pricing", "products"]')
        router = CategoryRouter(llm, top_k=1)
        result = router.route("Цена?")

        assert len(result) == 1
        assert result == ["pricing"]


# =============================================================================
# Тесты fallback
# =============================================================================

class TestFallback:
    """Тесты fallback поведения."""

    def test_empty_query_returns_fallback(self):
        """Пустой запрос возвращает fallback."""
        llm = MockLLM()
        router = CategoryRouter(llm, top_k=3)

        assert router.route("") == ["other", "faq"]
        assert router.route("   ") == ["other", "faq"]
        assert llm.call_count == 0  # LLM не вызывался

    def test_llm_error_returns_fallback(self):
        """Ошибка LLM возвращает fallback."""
        llm = ErrorLLM()
        router = CategoryRouter(llm, top_k=3)
        result = router.route("Сколько стоит?")

        assert result == ["other", "faq"]

    def test_custom_fallback_categories(self):
        """Кастомные fallback категории."""
        llm = MockLLM('')
        router = CategoryRouter(llm, top_k=3, fallback_categories=["support", "products"])
        result = router.route("Помогите")

        assert result == ["support", "products"]

    def test_invalid_fallback_raises_error(self):
        """Невалидные fallback категории вызывают ошибку."""
        llm = MockLLM()

        with pytest.raises(ValueError, match="Invalid fallback category"):
            CategoryRouter(llm, fallback_categories=["invalid_category"])


# =============================================================================
# Тесты интеграции с LLM
# =============================================================================

class TestLLMIntegration:
    """Тесты взаимодействия с LLM."""

    def test_prompt_contains_query(self):
        """Промпт содержит запрос пользователя."""
        llm = MockLLM()
        router = CategoryRouter(llm, top_k=3)
        router.route("Сколько стоит Wipon Desktop?")

        assert "Сколько стоит Wipon Desktop?" in llm.last_prompt

    def test_prompt_contains_top_k(self):
        """Промпт содержит top_k."""
        llm = MockLLM()
        router = CategoryRouter(llm, top_k=2)
        router.route("Цена?")

        assert "2" in llm.last_prompt

    def test_llm_called_once(self):
        """LLM вызывается один раз за route()."""
        llm = MockLLM()
        router = CategoryRouter(llm, top_k=3)
        router.route("Цена?")

        assert llm.call_count == 1


# =============================================================================
# Тесты edge cases
# =============================================================================

class TestEdgeCases:
    """Тесты граничных случаев."""

    def test_unicode_query(self):
        """Unicode в запросе."""
        llm = MockLLM('["pricing"]')
        router = CategoryRouter(llm, top_k=3)
        result = router.route("Қанша тұрады?")  # Казахский

        assert result == ["pricing"]

    def test_very_long_query(self):
        """Очень длинный запрос."""
        llm = MockLLM('["products"]')
        router = CategoryRouter(llm, top_k=3)
        long_query = "Расскажите подробно " * 100
        result = router.route(long_query)

        assert result == ["products"]

    def test_special_characters(self):
        """Специальные символы в запросе."""
        llm = MockLLM('["support"]')
        router = CategoryRouter(llm, top_k=3)
        result = router.route("Помощь??? (срочно!!!)")

        assert result == ["support"]

    def test_json_with_extra_whitespace(self):
        """JSON с лишними пробелами."""
        llm = MockLLM('  [  "pricing"  ,  "products"  ]  ')
        router = CategoryRouter(llm, top_k=3)
        result = router.route("Цена?")

        assert result == ["pricing", "products"]

    def test_nested_json_array(self):
        """Вложенный массив — берём первый."""
        llm = MockLLM('{"categories": ["pricing"]} ["products"]')
        router = CategoryRouter(llm, top_k=3)
        result = router.route("Цена?")

        # Должен найти первый массив ["pricing"]
        assert result == ["pricing"]

    def test_non_string_elements_filtered(self):
        """Нестроковые элементы фильтруются."""
        llm = MockLLM('[123, "pricing", null, "products", true]')
        router = CategoryRouter(llm, top_k=3)
        result = router.route("Цена?")

        assert result == ["pricing", "products"]


# =============================================================================
# Тесты реальных сценариев
# =============================================================================

class TestRealScenarios:
    """Тесты на реальных сценариях использования."""

    @pytest.mark.parametrize("query,expected_categories", [
        ("Сколько стоит?", ["pricing"]),
        ("Какие есть интеграции?", ["integrations"]),
        ("Как связаться с поддержкой?", ["support"]),
        ("Что такое ТИС?", ["tis"]),
        ("Какое оборудование нужно?", ["equipment"]),
        ("Работаете ли в Алматы?", ["regions"]),
        ("Как посмотреть остатки?", ["inventory"]),
    ])
    def test_common_queries(self, query, expected_categories):
        """Типичные запросы получают правильные категории."""
        # Mock LLM возвращает ожидаемые категории
        llm = MockLLM(f'["{expected_categories[0]}"]')
        router = CategoryRouter(llm, top_k=3)
        result = router.route(query)

        assert expected_categories[0] in result

    def test_multiple_categories_for_complex_query(self):
        """Сложный запрос может вернуть несколько категорий."""
        llm = MockLLM('["pricing", "products", "features"]')
        router = CategoryRouter(llm, top_k=3)
        result = router.route("Сколько стоит Wipon Desktop и какие у него функции?")

        assert len(result) == 3
        assert "pricing" in result
        assert "products" in result
        assert "features" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
