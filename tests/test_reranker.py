"""
Тесты для Reranker.

Проверяем:
1. Инициализация и загрузка модели
2. Метод rerank() переоценивает кандидатов
3. Fallback при недоступности модели
4. Интеграция с CascadeRetriever
"""

import pytest
import sys
import os

# Добавляем путь к src для импортов
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from knowledge.reranker import Reranker, get_reranker, reset_reranker
from knowledge.retriever import CascadeRetriever, MatchStage, SearchResult
from knowledge.base import KnowledgeSection


class TestRerankerBasic:
    """Базовые тесты для Reranker."""

    @pytest.fixture
    def reranker(self):
        """Создать reranker для тестов."""
        reset_reranker()
        return Reranker()

    def test_reranker_creation(self, reranker):
        """Reranker создаётся без ошибок."""
        assert reranker is not None
        assert reranker.model_name == "BAAI/bge-reranker-v2-m3"

    def test_reranker_lazy_init(self, reranker):
        """Модель загружается лениво."""
        # До вызова методов модель не загружена
        assert reranker._initialized is False

    def test_reranker_singleton(self):
        """get_reranker возвращает singleton."""
        reset_reranker()
        r1 = get_reranker()
        r2 = get_reranker()
        assert r1 is r2


class TestRerankerWithMockCandidates:
    """Тесты rerank с mock-кандидатами."""

    @pytest.fixture
    def mock_sections(self):
        """Создать mock секции для тестов."""
        return [
            KnowledgeSection(
                category="pricing",
                topic="tariffs",
                keywords=["тариф", "цена"],
                facts="Тарифы Wipon: Mini 5000, Lite 10000, Pro 20000.",
                priority=10
            ),
            KnowledgeSection(
                category="features",
                topic="analytics",
                keywords=["аналитика", "отчёты"],
                facts="Аналитика продаж: графики, отчёты, ABC-анализ.",
                priority=5
            ),
            KnowledgeSection(
                category="support",
                topic="training",
                keywords=["обучение", "курс"],
                facts="Обучение персонала: онлайн-курсы, видео.",
                priority=3
            ),
        ]

    @pytest.fixture
    def mock_candidates(self, mock_sections):
        """Создать mock SearchResult для тестов."""
        return [
            SearchResult(
                section=mock_sections[0],
                score=0.3,
                stage=MatchStage.LEMMA,
                matched_keywords=["тариф"]
            ),
            SearchResult(
                section=mock_sections[1],
                score=0.25,
                stage=MatchStage.LEMMA,
                matched_keywords=["аналитика"]
            ),
            SearchResult(
                section=mock_sections[2],
                score=0.2,
                stage=MatchStage.LEMMA,
                matched_keywords=["обучение"]
            ),
        ]

    def test_rerank_returns_candidates(self, mock_candidates):
        """rerank возвращает кандидатов."""
        reranker = Reranker()
        query = "сколько стоит подключение"

        results = reranker.rerank(query, mock_candidates, top_k=2)

        assert len(results) <= 2
        # Результаты должны быть из исходных кандидатов
        for r in results:
            assert r in mock_candidates

    def test_rerank_empty_candidates(self):
        """rerank с пустым списком возвращает пустой список."""
        reranker = Reranker()
        results = reranker.rerank("query", [], top_k=2)
        assert results == []

    def test_rerank_top_k_limit(self, mock_candidates):
        """rerank возвращает не больше top_k."""
        reranker = Reranker()

        results = reranker.rerank("query", mock_candidates, top_k=1)
        assert len(results) == 1

        results = reranker.rerank("query", mock_candidates, top_k=5)
        assert len(results) <= len(mock_candidates)


class TestRerankerIntegration:
    """Интеграционные тесты reranker + CascadeRetriever."""

    @pytest.fixture
    def retriever_with_reranker(self):
        """Создать retriever с включённым reranker."""
        import knowledge.retriever as r
        r._retriever = None
        reset_reranker()
        return CascadeRetriever(use_embeddings=False)

    def test_retriever_has_reranker_settings(self, retriever_with_reranker):
        """Retriever загружает настройки reranker."""
        r = retriever_with_reranker
        assert hasattr(r, 'reranker_enabled')
        assert hasattr(r, 'rerank_threshold')
        assert hasattr(r, 'rerank_candidates')

    def test_retrieve_with_low_score_uses_reranker(self, retriever_with_reranker):
        """При низком score должен использоваться reranker."""
        # Этот тест проверяет что код не падает
        # Реальная проверка reranking требует модель
        result = retriever_with_reranker.retrieve("некий сложный запрос без точных совпадений")
        # Должен вернуть строку (пустую или с фактами)
        assert isinstance(result, str)


class TestRerankerAvailability:
    """Тесты доступности reranker."""

    def test_is_available_before_init(self):
        """is_available инициализирует модель."""
        reset_reranker()
        reranker = Reranker()

        # Вызов is_available должен инициализировать модель
        available = reranker.is_available()

        assert reranker._initialized is True
        # available зависит от того установлена ли модель
        assert isinstance(available, bool)

    def test_rerank_fallback_when_unavailable(self):
        """Если модель недоступна, возвращаем кандидатов как есть."""
        reranker = Reranker()
        reranker._initialized = True
        reranker.model = None  # Симулируем отсутствие модели

        section = KnowledgeSection(
            category="test",
            topic="test",
            keywords=["test"],
            facts="Test facts",
            priority=5
        )
        candidates = [
            SearchResult(section=section, score=0.5, stage=MatchStage.LEMMA)
        ]

        results = reranker.rerank("query", candidates, top_k=2)

        # Должен вернуть исходных кандидатов
        assert len(results) == 1
        assert results[0] is candidates[0]
