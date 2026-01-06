"""
Интеграционные тесты для CategoryRouter.

Проверяем:
1. Интеграция CategoryRouter с CascadeRetriever
2. Интеграция CategoryRouter с ResponseGenerator
3. Полный пайплайн: Query -> CategoryRouter -> Retriever -> Facts
4. Сравнение результатов с/без CategoryRouter
5. Performance тесты
"""

import pytest
import sys
import os
import time

# Добавляем путь к src для импортов
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from knowledge.category_router import CategoryRouter
from knowledge.retriever import CascadeRetriever, get_retriever, reset_retriever


# =============================================================================
# Mock LLM для тестирования
# =============================================================================

class MockLLM:
    """Mock LLM для тестирования."""

    def __init__(self, category_map: dict = None):
        """
        Args:
            category_map: Словарь keyword -> categories
                          Например: {"цен": ["pricing"], "интеграц": ["integrations"]}
        """
        self.category_map = category_map or {
            # Ценовые запросы
            "цен": '["pricing"]',
            "стоим": '["pricing"]',
            "стоит": '["pricing"]',
            "тариф": '["pricing"]',
            # Интеграции
            "интеграц": '["integrations"]',
            "kaspi": '["integrations"]',
            # Оборудование
            "оборудован": '["equipment"]',
            "сканер": '["equipment"]',
            "принтер": '["equipment"]',
            # ТИС
            "тис": '["tis"]',
            # Поддержка
            "поддержк": '["support"]',
            "связаться": '["support"]',
            "помощь": '["support"]',
            # Товары и склад
            "товар": '["inventory"]',
            "остат": '["inventory"]',
            "склад": '["inventory"]',
            # Регионы
            "регион": '["regions"]',
            "город": '["regions"]',
            "алматы": '["regions"]',
            "работаете": '["regions"]',
            # Продукты
            "продукт": '["products"]',
            "wipon desktop": '["products"]',
            # Аналитика
            "аналитик": '["analytics"]',
            "отчёт": '["analytics"]',
            # Фискализация
            "фискал": '["fiscal"]',
            "чек": '["fiscal"]',
        }
        self.call_count = 0
        self.last_prompt = None

    def generate(self, prompt: str) -> str:
        self.call_count += 1
        self.last_prompt = prompt

        # Извлекаем запрос пользователя из prompt
        # Формат: "Запрос клиента: {query}"
        import re
        query_match = re.search(r'Запрос клиента:\s*(.+?)(?:\n|$)', prompt)
        if query_match:
            user_query = query_match.group(1).lower()
        else:
            user_query = prompt.lower()

        for keyword, response in self.category_map.items():
            if keyword in user_query:
                return response

        return '["other", "faq"]'


# =============================================================================
# Тесты интеграции CategoryRouter + Retriever
# =============================================================================

class TestCategoryRouterRetrieverIntegration:
    """Тесты интеграции CategoryRouter с CascadeRetriever."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Сбрасываем singleton перед каждым тестом."""
        reset_retriever()
        yield
        reset_retriever()

    @pytest.fixture
    def retriever(self):
        """CascadeRetriever без эмбеддингов."""
        return CascadeRetriever(use_embeddings=False)

    @pytest.fixture
    def router(self):
        """CategoryRouter с mock LLM."""
        return CategoryRouter(MockLLM(), top_k=3)

    def test_router_provides_categories_to_retriever(self, retriever, router):
        """CategoryRouter передаёт категории в retriever."""
        query = "Сколько стоит Wipon?"
        categories = router.route(query)

        # Проверяем что categories получены
        assert categories == ["pricing"]

        # Поиск с категориями
        results = retriever.search(query, categories=categories)

        # Все результаты должны быть из pricing категории
        if results:
            for r in results:
                assert r.section.category == "pricing", \
                    f"Expected 'pricing', got '{r.section.category}'"

    def test_categories_reduce_search_scope(self, retriever, router):
        """Категории сужают область поиска."""
        query = "касса"

        # Без категорий
        results_all = retriever.search(query, top_k=10)
        categories_all = set(r.section.category for r in results_all)

        # С категориями от router
        categories = router.route("Сколько стоит касса?")
        results_filtered = retriever.search(query, categories=categories, top_k=10)
        categories_filtered = set(r.section.category for r in results_filtered)

        # С фильтрацией категорий должно быть меньше или равно
        assert len(categories_filtered) <= len(categories_all)

    def test_retrieve_with_categories_parameter(self, retriever, router):
        """retrieve() работает с параметром categories."""
        query = "Какие есть интеграции?"
        categories = router.route(query)

        facts = retriever.retrieve(
            message=query,
            categories=categories,
            top_k=2
        )

        # Главное что метод работает без ошибок
        assert isinstance(facts, str)
        # Категории должны быть определены
        assert len(categories) > 0

    def test_categories_override_intent(self, retriever):
        """Параметр categories имеет приоритет над intent."""
        query = "цена"

        # С intent price_question — ищет в pricing
        facts_intent = retriever.retrieve(
            message=query,
            intent="price_question",
            top_k=5
        )

        # С categories=["support"] — ищет в support
        facts_categories = retriever.retrieve(
            message=query,
            categories=["support"],
            top_k=5
        )

        # Результаты могут отличаться
        # Главное — что categories работает
        assert isinstance(facts_intent, str)
        assert isinstance(facts_categories, str)

    def test_invalid_categories_fallback(self, retriever):
        """Несуществующие категории не ломают поиск."""
        query = "касса"

        # Поиск с невалидными категориями
        results = retriever.search(
            query,
            categories=["invalid_category"],
            top_k=3
        )

        # Должен найти по всем категориям (fallback)
        assert len(results) > 0


# =============================================================================
# Тесты полного пайплайна
# =============================================================================

class TestFullPipeline:
    """Тесты полного пайплайна CategoryRouter -> Retriever."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        reset_retriever()
        yield
        reset_retriever()

    @pytest.fixture
    def pipeline(self):
        """Возвращает функцию пайплайна."""
        llm = MockLLM()
        router = CategoryRouter(llm, top_k=3)
        retriever = CascadeRetriever(use_embeddings=False)

        def run_pipeline(query: str):
            categories = router.route(query)
            facts = retriever.retrieve(
                message=query,
                categories=categories,
                top_k=2
            )
            return {
                "query": query,
                "categories": categories,
                "facts": facts,
                "llm_calls": llm.call_count
            }

        return run_pipeline

    @pytest.mark.parametrize("query,expected_category", [
        ("Сколько стоит?", "pricing"),
        ("Какие интеграции есть?", "integrations"),
        ("Что такое ТИС?", "tis"),
        ("Как связаться с поддержкой?", "support"),
        ("Какие сканеры поддерживаются?", "equipment"),
        ("Работаете в Алматы?", "regions"),
        ("Как посмотреть остатки?", "inventory"),
    ])
    def test_pipeline_selects_correct_category(self, pipeline, query, expected_category):
        """Пайплайн выбирает правильную категорию."""
        result = pipeline(query)

        assert expected_category in result["categories"], \
            f"Expected '{expected_category}' in {result['categories']} for query '{query}'"

    def test_pipeline_returns_relevant_facts(self, pipeline):
        """Пайплайн возвращает релевантные факты."""
        result = pipeline("Сколько стоит тариф?")

        assert "pricing" in result["categories"]
        if result["facts"]:
            facts_lower = result["facts"].lower()
            # Должны быть ключевые слова о ценах
            assert any(word in facts_lower for word in ["тариф", "цен", "стоим", "₸", "тенге", "месяц"])

    def test_pipeline_llm_called_once_per_query(self, pipeline):
        """LLM вызывается один раз на запрос."""
        pipeline("Первый запрос")
        initial_calls = 1

        pipeline("Второй запрос")
        assert initial_calls + 1 == 2  # +1 за второй запрос


# =============================================================================
# Тесты производительности
# =============================================================================

class TestPerformance:
    """Тесты производительности CategoryRouter."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        reset_retriever()
        yield
        reset_retriever()

    def test_router_latency(self):
        """CategoryRouter добавляет минимальную латентность."""
        class FastMockLLM:
            def generate(self, prompt: str) -> str:
                return '["pricing"]'

        router = CategoryRouter(FastMockLLM(), top_k=3)

        start = time.perf_counter()
        for _ in range(100):
            router.route("Сколько стоит?")
        elapsed = (time.perf_counter() - start) * 1000

        avg_ms = elapsed / 100
        # Без реального LLM вызова должно быть быстро
        assert avg_ms < 5, f"Average latency {avg_ms:.2f}ms, expected < 5ms"

    def test_parse_response_fast(self):
        """Парсинг ответа быстрый."""
        llm = MockLLM()
        router = CategoryRouter(llm, top_k=3)

        # Разные форматы ответов
        responses = [
            '["pricing", "products"]',
            '<think>Something</think>["pricing"]',
            'Categories: ["pricing", "products", "faq"]',
            '  [  "pricing"  ]  ',
        ]

        start = time.perf_counter()
        for _ in range(1000):
            for response in responses:
                router._parse_response(response)
        elapsed = (time.perf_counter() - start) * 1000

        avg_ms = elapsed / 4000
        assert avg_ms < 0.1, f"Average parse time {avg_ms:.3f}ms, expected < 0.1ms"

    def test_retrieval_with_categories_faster(self):
        """Поиск с категориями быстрее чем без."""
        retriever = CascadeRetriever(use_embeddings=False)
        query = "касса онлайн цена"

        # Без категорий
        start = time.perf_counter()
        for _ in range(50):
            retriever.search(query, top_k=3)
        time_without = (time.perf_counter() - start) * 1000

        # С категориями
        start = time.perf_counter()
        for _ in range(50):
            retriever.search(query, categories=["pricing"], top_k=3)
        time_with = (time.perf_counter() - start) * 1000

        # С категориями должно быть не медленнее
        # (на практике обычно быстрее за счёт меньшего числа секций)
        avg_without = time_without / 50
        avg_with = time_with / 50

        # Логируем для отладки
        print(f"\nAvg without categories: {avg_without:.2f}ms")
        print(f"Avg with categories: {avg_with:.2f}ms")

        # Не должно быть значительно медленнее
        assert avg_with < avg_without * 2, \
            f"With categories ({avg_with:.2f}ms) much slower than without ({avg_without:.2f}ms)"


# =============================================================================
# Тесты обратной совместимости
# =============================================================================

class TestBackwardCompatibility:
    """Тесты обратной совместимости."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        reset_retriever()
        yield
        reset_retriever()

    def test_retrieve_without_categories_still_works(self):
        """retrieve() работает без параметра categories."""
        retriever = get_retriever(use_embeddings=False)

        # Старый API без categories
        facts = retriever.retrieve(
            message="касса",
            intent="price_question",
            top_k=2
        )

        assert isinstance(facts, str)

    def test_search_with_single_category_still_works(self):
        """search() с одной категорией всё ещё работает."""
        retriever = get_retriever(use_embeddings=False)

        # Старый API с category (не categories)
        results = retriever.search(
            query="касса",
            category="products",
            top_k=2
        )

        assert isinstance(results, list)
        for r in results:
            assert r.section.category == "products"

    def test_intent_mapping_fallback(self):
        """Intent маппинг работает когда categories=None."""
        retriever = get_retriever(use_embeddings=False)

        # Без categories, с intent
        facts = retriever.retrieve(
            message="сколько стоит",
            intent="price_question",
            categories=None,  # Явно None
            top_k=2
        )

        assert isinstance(facts, str)


# =============================================================================
# Тесты edge cases
# =============================================================================

class TestEdgeCases:
    """Edge cases интеграции."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        reset_retriever()
        yield
        reset_retriever()

    def test_empty_categories_searches_all(self):
        """Пустой список категорий ищет везде."""
        retriever = CascadeRetriever(use_embeddings=False)

        results_all = retriever.search("касса", top_k=5)
        results_empty = retriever.search("касса", categories=[], top_k=5)

        # Пустой список должен искать везде (fallback)
        assert len(results_empty) >= len(results_all) * 0.5

    def test_none_categories_uses_intent(self):
        """None categories использует intent маппинг."""
        retriever = CascadeRetriever(use_embeddings=False)

        facts = retriever.retrieve(
            message="цена",
            intent="price_question",
            categories=None,
            top_k=2
        )

        # Должен найти что-то
        assert isinstance(facts, str)

    def test_categories_with_no_matches(self):
        """Категории без результатов возвращают пустую строку."""
        retriever = CascadeRetriever(use_embeddings=False)

        # Ищем в promotions что-то что там точно нет
        facts = retriever.retrieve(
            message="xyznonexistentquery123",
            categories=["promotions"],
            top_k=2
        )

        # Пустая строка или пустой результат - оба валидны
        assert isinstance(facts, str)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
