"""
LLM-based Category Router для базы знаний.
Определяет топ-N категорий для поиска на основе запроса клиента.

Использует LLM для классификации запроса по категориям,
что позволяет CascadeRetriever искать только в релевантных файлах.

Поддерживает:
- Structured Output (Ollama) — валидный JSON через format parameter
- Legacy режим (generate + parsing) — обратная совместимость
"""

import json
import re
import time
from typing import List, Optional, Protocol, Type, TypeVar
from pydantic import BaseModel

from src.logger import logger

T = TypeVar('T', bound=BaseModel)


class LLMProtocol(Protocol):
    """Протокол для LLM клиента."""
    def generate(self, prompt: str) -> str:
        """Генерация ответа."""
        ...


class StructuredLLMProtocol(LLMProtocol, Protocol):
    """Протокол для LLM с поддержкой structured output."""
    def generate_structured(self, prompt: str, schema: Type[T]) -> Optional[T]:
        """Генерация структурированного ответа."""
        ...


class CategoryRouter:
    """
    Использует LLM для классификации запроса по категориям базы знаний.

    Преимущества:
    - Более точное определение категорий чем статический маппинг
    - Учитывает контекст и семантику запроса
    - Позволяет сузить область поиска для CascadeRetriever

    Использование:
        router = CategoryRouter(llm, top_k=3)
        categories = router.route("Сколько стоит Wipon Desktop?")
        # ["pricing", "products"]
    """

    # Все доступные категории базы знаний
    CATEGORIES = [
        "analytics",     # Аналитика и отчёты
        "competitors",   # Сравнение с конкурентами
        "employees",     # Сотрудники и кадры
        "equipment",     # Оборудование и периферия
        "faq",           # Общие частые вопросы
        "features",      # Функции системы
        "fiscal",        # Фискализация
        "integrations",  # Интеграции
        "inventory",     # Товары и склад
        "mobile",        # Мобильное приложение
        "pricing",       # Цены и тарифы
        "products",      # Продукты Wipon
        "promotions",    # Акции и скидки
        "regions",       # Регионы и доставка
        "stability",     # Надёжность и стабильность
        "support",       # Техподдержка и обучение
        "tis",           # Трёхкомпонентная система для ИП
    ]

    def __init__(
        self,
        llm: LLMProtocol,
        top_k: int = 3,
        fallback_categories: Optional[List[str]] = None
    ):
        """
        Инициализация CategoryRouter.

        Args:
            llm: LLM клиент с методом generate()
            top_k: Максимальное количество категорий для возврата
            fallback_categories: Категории по умолчанию при ошибке
        """
        self.llm = llm
        self.top_k = top_k
        self.fallback_categories = fallback_categories or ["faq", "features"]

        # Валидация fallback категорий
        for cat in self.fallback_categories:
            if cat not in self.CATEGORIES:
                raise ValueError(f"Invalid fallback category: {cat}")

    def route(self, query: str) -> List[str]:
        """
        Определить топ-N категорий для запроса.

        Автоматически выбирает метод:
        - generate_structured (Ollama) если доступен
        - generate + parsing (legacy) иначе

        Args:
            query: Сообщение клиента

        Returns:
            List[str]: Список категорий, например ["pricing", "products"]
        """
        if not query or not query.strip():
            logger.debug("CategoryRouter: empty query, using fallback")
            return self.fallback_categories[:self.top_k]

        start_time = time.perf_counter()

        try:
            # Проверяем поддержку structured output
            if hasattr(self.llm, 'generate_structured'):
                categories = self._route_structured(query)
                method = "structured"
            else:
                categories = self._route_legacy(query)
                method = "legacy"

            elapsed_ms = (time.perf_counter() - start_time) * 1000

            logger.debug(
                "CategoryRouter result",
                query=query[:50],
                categories=categories,
                method=method,
                latency_ms=round(elapsed_ms, 2)
            )

            return categories if categories else self.fallback_categories[:self.top_k]

        except Exception as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            logger.error(
                "CategoryRouter failed",
                error=str(e),
                query=query[:50],
                latency_ms=round(elapsed_ms, 2)
            )
            return self.fallback_categories[:self.top_k]

    def _route_structured(self, query: str) -> List[str]:
        """
        Роутинг через structured output (Ollama).

        Гарантирует валидный JSON через Pydantic схему.
        """
        from src.config import CATEGORY_ROUTER_PROMPT_STRUCTURED
        from src.classifier.llm import CategoryResult

        prompt = CATEGORY_ROUTER_PROMPT_STRUCTURED.format(
            query=query,
            top_k=self.top_k
        )

        result = self.llm.generate_structured(prompt, CategoryResult)

        if result is None:
            logger.warning("CategoryRouter: structured output returned None")
            return []

        # CategoryResult.categories уже валидировано Pydantic
        return list(result.categories[:self.top_k])

    def _route_legacy(self, query: str) -> List[str]:
        """
        Legacy роутинг через generate + parsing.

        Обратная совместимость для LLM без structured output.
        """
        from src.config import CATEGORY_ROUTER_PROMPT

        prompt = CATEGORY_ROUTER_PROMPT.format(
            query=query,
            top_k=self.top_k
        )

        response = self.llm.generate(prompt)
        return self._parse_response(response)

    def _parse_response(self, response: str) -> List[str]:
        """
        Парсинг JSON массива из ответа LLM.

        Обрабатывает случаи:
        - Чистый JSON: ["pricing", "products"]
        - JSON с текстом: Категории: ["pricing", "products"]
        - Thinking tags: <think>...</think>["pricing"]
        - Невалидный ответ: возвращает пустой список

        Args:
            response: Ответ LLM

        Returns:
            List[str]: Валидные категории или пустой список
        """
        if not response:
            return []

        # Удаляем thinking теги Qwen если есть
        response = re.sub(r'<think>.*?</think>', '', response, flags=re.DOTALL)

        # Пробуем найти JSON массив в ответе
        json_match = re.search(r'\[.*?\]', response, re.DOTALL)
        if not json_match:
            logger.debug("CategoryRouter: no JSON array found", response=response[:100])
            return []

        try:
            categories = json.loads(json_match.group())

            # Валидируем что это список строк
            if not isinstance(categories, list):
                logger.debug("CategoryRouter: parsed value is not a list")
                return []

            # Фильтруем только валидные категории
            valid = [c for c in categories if isinstance(c, str) and c in self.CATEGORIES]

            if len(valid) != len(categories):
                invalid = [c for c in categories if c not in self.CATEGORIES]
                logger.debug(
                    "CategoryRouter: filtered invalid categories",
                    invalid=invalid
                )

            return valid[:self.top_k]

        except json.JSONDecodeError as e:
            logger.debug("CategoryRouter: JSON parse error", error=str(e))
            return []

    def get_all_categories(self) -> List[str]:
        """Получить список всех доступных категорий."""
        return self.CATEGORIES.copy()


# =============================================================================
# Утилита для быстрого тестирования
# =============================================================================

if __name__ == "__main__":
    # Демо с mock LLM
    class MockLLM:
        def generate(self, prompt: str) -> str:
            # Простая эвристика для демо
            if "цен" in prompt.lower() or "стоим" in prompt.lower():
                return '["pricing", "products"]'
            elif "интеграц" in prompt.lower():
                return '["integrations"]'
            else:
                return '["other", "faq"]'

    router = CategoryRouter(MockLLM(), top_k=3)

    test_queries = [
        "Сколько стоит Wipon Desktop?",
        "Какие интеграции есть?",
        "Что такое ТИС?",
        "",
    ]

    print("=" * 60)
    print("CategoryRouter Demo")
    print("=" * 60)

    for query in test_queries:
        categories = router.route(query)
        print(f"Query: {query[:40] if query else '(empty)'}")
        print(f"Categories: {categories}")
        print("-" * 40)
