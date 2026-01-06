"""
End-to-end тесты для CategoryRouter с реальным LLM.

Эти тесты требуют запущенного Ollama сервера.
Пропускаются автоматически если Ollama недоступен.

Запуск: pytest tests/test_category_router_e2e.py -v
"""

import pytest
import sys
import os
import time
import requests

# Добавляем путь к src для импортов
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from knowledge.category_router import CategoryRouter
from knowledge.retriever import CascadeRetriever, reset_retriever


# =============================================================================
# Проверка доступности Ollama
# =============================================================================

def is_ollama_available():
    """Проверить что Ollama запущен."""
    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=2)
        return response.status_code == 200
    except:
        return False


def get_available_models():
    """Получить список доступных моделей."""
    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=2)
        if response.status_code == 200:
            data = response.json()
            return [m["name"] for m in data.get("models", [])]
    except:
        pass
    return []


# =============================================================================
# Реальный LLM клиент
# =============================================================================

class OllamaLLM:
    """Минимальный LLM клиент для тестов."""

    def __init__(self, model: str = "qwen3:8b-fast"):
        self.model = model
        self.base_url = "http://localhost:11434/api/generate"

    def generate(self, prompt: str) -> str:
        """Генерация ответа."""
        response = requests.post(
            self.base_url,
            json={
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "think": False,  # Отключаем thinking mode для Qwen3
                "options": {
                    "temperature": 0.0,  # Детерминированный ответ
                    "num_predict": 100,
                }
            },
            timeout=60
        )

        if response.status_code == 200:
            return response.json().get("response", "")
        else:
            raise RuntimeError(f"Ollama error: {response.status_code}")


# =============================================================================
# E2E тесты
# =============================================================================

@pytest.mark.skipif(
    not is_ollama_available(),
    reason="Ollama not available"
)
class TestCategoryRouterE2E:
    """End-to-end тесты с реальным LLM."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        reset_retriever()
        yield
        reset_retriever()

    @pytest.fixture
    def llm(self):
        """Реальный LLM клиент."""
        models = get_available_models()
        # Предпочитаем быструю модель
        if "qwen3:8b-fast" in models:
            return OllamaLLM("qwen3:8b-fast")
        elif "qwen3:8b" in models:
            return OllamaLLM("qwen3:8b")
        elif "qwen3:1.7b" in models:
            return OllamaLLM("qwen3:1.7b")
        else:
            pytest.skip("No suitable Qwen model available")

    @pytest.fixture
    def router(self, llm):
        """CategoryRouter с реальным LLM."""
        return CategoryRouter(llm, top_k=3)

    @pytest.fixture
    def retriever(self):
        """CascadeRetriever."""
        return CascadeRetriever(use_embeddings=False)

    # -------------------------------------------------------------------------
    # Тесты классификации
    # -------------------------------------------------------------------------

    @pytest.mark.parametrize("query,expected_category", [
        ("Сколько стоит Wipon?", "pricing"),
        ("Какие тарифы есть?", "pricing"),
        ("Что такое ТИС?", "tis"),
        ("Какие сканеры поддерживаются?", "equipment"),
        ("Как подключить Kaspi?", "integrations"),
        ("Работаете ли в Караганде?", "regions"),
    ])
    def test_llm_classifies_correctly(self, router, query, expected_category):
        """LLM правильно классифицирует запросы."""
        categories = router.route(query)

        assert len(categories) > 0, f"No categories for '{query}'"
        assert expected_category in categories, \
            f"Expected '{expected_category}' in {categories} for query '{query}'"

    def test_llm_returns_valid_categories(self, router):
        """LLM возвращает только валидные категории."""
        queries = [
            "Сколько стоит?",
            "Какие интеграции есть?",
            "Что умеет Wipon?",
            "Как связаться с поддержкой?",
        ]

        for query in queries:
            categories = router.route(query)
            for cat in categories:
                assert cat in router.CATEGORIES, \
                    f"Invalid category '{cat}' returned for query '{query}'"

    def test_llm_respects_top_k(self, llm):
        """LLM уважает top_k."""
        router = CategoryRouter(llm, top_k=2)
        categories = router.route("Сколько стоит Wipon Desktop и какие у него функции?")

        assert len(categories) <= 2, \
            f"Expected <= 2 categories, got {len(categories)}: {categories}"

    # -------------------------------------------------------------------------
    # Тесты полного пайплайна
    # -------------------------------------------------------------------------

    def test_full_pipeline_pricing(self, router, retriever):
        """Полный пайплайн: вопрос о ценах."""
        query = "Сколько стоит Wipon?"

        # Шаг 1: Классификация
        categories = router.route(query)
        assert "pricing" in categories

        # Шаг 2: Поиск
        facts = retriever.retrieve(
            message=query,
            categories=categories,
            top_k=2
        )

        # Шаг 3: Проверка результата
        assert isinstance(facts, str)
        assert len(facts) > 0, "No facts found for pricing query"

        # Факты должны содержать ценовую информацию
        facts_lower = facts.lower()
        assert any(w in facts_lower for w in ["₸", "тенге", "тариф", "месяц", "год", "стоимость"]), \
            f"Facts don't contain pricing info: {facts[:200]}"

    def test_full_pipeline_tis(self, router, retriever):
        """Полный пайплайн: вопрос о ТИС."""
        query = "Что такое ТИС и кому нужен?"

        categories = router.route(query)
        assert "tis" in categories

        facts = retriever.retrieve(
            message=query,
            categories=categories,
            top_k=2
        )

        assert isinstance(facts, str)
        assert len(facts) > 0, "No facts found for TIS query"

        facts_lower = facts.lower()
        assert any(w in facts_lower for w in ["тис", "упрощён", "ип", "налог"]), \
            f"Facts don't contain TIS info: {facts[:200]}"

    def test_full_pipeline_equipment(self, router, retriever):
        """Полный пайплайн: вопрос об оборудовании."""
        query = "Какой сканер штрихкодов выбрать?"

        categories = router.route(query)
        assert "equipment" in categories

        facts = retriever.retrieve(
            message=query,
            categories=categories,
            top_k=2
        )

        assert isinstance(facts, str)
        assert len(facts) > 0, "No facts found for equipment query"

    # -------------------------------------------------------------------------
    # Тесты производительности
    # -------------------------------------------------------------------------

    def test_latency_acceptable(self, router):
        """Латентность классификации приемлема."""
        query = "Сколько стоит Wipon Desktop?"

        # Прогреваем
        router.route("тест")

        # Измеряем
        start = time.perf_counter()
        categories = router.route(query)
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert len(categories) > 0
        # Должно быть меньше 1 секунды
        assert elapsed_ms < 1000, f"Classification took {elapsed_ms:.0f}ms, expected < 1000ms"

        print(f"\n[E2E] Classification latency: {elapsed_ms:.0f}ms")
        print(f"[E2E] Categories: {categories}")

    def test_multiple_queries_performance(self, router):
        """Множество запросов работают стабильно."""
        queries = [
            "Сколько стоит?",
            "Какие интеграции есть?",
            "Что такое ТИС?",
            "Работаете ли в Алматы?",
            "Какой сканер выбрать?",
        ]

        total_time = 0
        for query in queries:
            start = time.perf_counter()
            categories = router.route(query)
            total_time += (time.perf_counter() - start) * 1000

            assert len(categories) > 0, f"No categories for '{query}'"

        avg_time = total_time / len(queries)
        print(f"\n[E2E] Average latency: {avg_time:.0f}ms per query")

        # Среднее должно быть меньше 1 секунды
        assert avg_time < 1000, f"Average latency {avg_time:.0f}ms too high"


@pytest.mark.skipif(
    not is_ollama_available(),
    reason="Ollama not available"
)
class TestCategoryRouterEdgeCasesE2E:
    """Edge cases с реальным LLM."""

    @pytest.fixture
    def llm(self):
        models = get_available_models()
        if "qwen3:8b-fast" in models:
            return OllamaLLM("qwen3:8b-fast")
        elif models:
            return OllamaLLM(models[0])
        else:
            pytest.skip("No models available")

    @pytest.fixture
    def router(self, llm):
        return CategoryRouter(llm, top_k=3)

    def test_ambiguous_query(self, router):
        """Неоднозначный запрос получает несколько категорий."""
        query = "Сколько стоит Wipon Desktop с интеграцией Kaspi?"

        categories = router.route(query)

        # Должен вернуть несколько категорий
        assert len(categories) >= 2, \
            f"Expected multiple categories for complex query, got: {categories}"

        # Могут быть разные комбинации, но логично ожидать pricing или products
        possible = {"pricing", "products", "integrations"}
        assert any(c in possible for c in categories), \
            f"Expected at least one of {possible}, got: {categories}"

    def test_unclear_query(self, router):
        """Неясный запрос получает fallback категории."""
        query = "хмм ну не знаю что-то там"

        categories = router.route(query)

        # Должен вернуть что-то
        assert len(categories) > 0
        # Скорее всего other или faq
        assert any(c in ["other", "faq", "support"] for c in categories), \
            f"Expected fallback categories, got: {categories}"

    def test_typos_handled(self, router):
        """Опечатки обрабатываются."""
        query = "сколька стоит випон?"

        categories = router.route(query)

        # LLM должен понять что это о ценах
        assert len(categories) > 0
        # Скорее всего pricing или products
        assert any(c in ["pricing", "products", "other"] for c in categories), \
            f"Expected pricing-related category for typo query, got: {categories}"


if __name__ == "__main__":
    if is_ollama_available():
        print("Ollama is available. Running E2E tests...")
        pytest.main([__file__, "-v"])
    else:
        print("Ollama is not available. Skipping E2E tests.")
        print("Start Ollama with: ollama serve")
