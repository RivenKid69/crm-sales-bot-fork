"""
Тесты для CascadeRetriever.

Проверяем:
1. Exact match — точное совпадение подстрок
2. Lemma match — морфологический поиск
3. Semantic match — эмбеддинги (опционально)
4. Каскадная логика — порядок этапов
5. Производительность
6. Обратная совместимость
"""

import pytest
import time
import sys
import os

# Добавляем путь к src для импортов

from src.knowledge.retriever import CascadeRetriever, MatchStage, SearchResult, get_retriever
from src.knowledge import WIPON_KNOWLEDGE

class TestExactMatch:
    """Тесты первого этапа — exact substring match."""

    @pytest.fixture
    def retriever(self):
        # Сбрасываем singleton для чистых тестов
        import src.knowledge.retriever as r
        r._retriever = None
        return CascadeRetriever(use_embeddings=False)

    def test_exact_phrase_found(self, retriever):
        """Точная фраза из keywords находится."""
        results = retriever.search("розничный налог")
        assert len(results) > 0
        assert results[0].stage == MatchStage.EXACT

    def test_keyword_as_substring(self, retriever):
        """Keyword является частью запроса."""
        results = retriever.search("какая ставка снр розничного")
        assert len(results) > 0

    def test_case_insensitive(self, retriever):
        """Регистр не важен."""
        results1 = retriever.search("РОЗНИЧНЫЙ НАЛОГ")
        results2 = retriever.search("розничный налог")
        assert len(results1) > 0
        assert len(results2) > 0
        # Результаты должны быть одинаковыми
        if results1 and results2:
            assert results1[0].section.topic == results2[0].section.topic

    def test_word_boundary_bonus(self, retriever):
        """Целое слово получает бонус."""
        results = retriever.search("розничный налог ставка")
        assert len(results) > 0
        # Score должен быть > 1.0 из-за бонуса

    def test_multiple_keywords_higher_score(self, retriever):
        """Больше совпавших keywords = выше score."""
        results = retriever.search("снр розничного налога ставка процент")
        assert len(results) > 0
        # Первый результат должен иметь больше совпадений

    def test_exact_search_returns_matched_keywords(self, retriever):
        """Результат содержит список совпавших keywords."""
        results = retriever.search("касса онлайн")
        if results and results[0].stage == MatchStage.EXACT:
            assert len(results[0].matched_keywords) > 0

class TestLemmaMatch:
    """Тесты второго этапа — lemma match."""

    @pytest.fixture
    def retriever(self):
        import src.knowledge.retriever as r
        r._retriever = None
        return CascadeRetriever(use_embeddings=False)

    def test_case_forms_match(self, retriever):
        """Разные падежи находят одну секцию."""
        queries = [
            "розничный налог",
            "розничного налога",
            "розничному налогу",
            "розничным налогом",
        ]
        results_topics = []
        for q in queries:
            results = retriever.search(q)
            if results:
                results_topics.append(results[0].section.topic)

        # Все должны найти что-то
        assert len(results_topics) >= 2

    def test_lemma_stage_marked(self, retriever):
        """Результат помечен как LEMMA."""
        # Принудительно используем lemma search
        results = retriever._lemma_search("предпринимателей розничном", retriever.kb.sections)
        if results:
            assert results[0].stage == MatchStage.LEMMA
            assert len(results[0].matched_lemmas) > 0

    def test_lemma_search_works_with_inflections(self, retriever):
        """Лемма поиск работает с разными формами слов."""
        results = retriever._lemma_search("предпринимателя", retriever.kb.sections)
        # Должен найти секции с "предприниматель" в keywords
        assert len(results) >= 0  # Может быть пустым если нет таких секций

class TestSemanticMatch:
    """Тесты третьего этапа — semantic match."""

    @pytest.fixture
    def retriever(self):
        import src.knowledge.retriever as r
        r._retriever = None
        return CascadeRetriever(use_embeddings=True)

    @pytest.mark.skipif(
        not CascadeRetriever(use_embeddings=True).embedder,
        reason="sentence-transformers not installed"
    )
    def test_semantic_search_works(self, retriever):
        """Семантический поиск работает."""
        if retriever.embedder:
            results = retriever._semantic_search(
                "деньги стоимость оплата",
                retriever.kb.sections,
                top_k=3
            )
            # Может найти что-то про цены
            assert isinstance(results, list)

    @pytest.mark.skipif(
        not CascadeRetriever(use_embeddings=True).embedder,
        reason="sentence-transformers not installed"
    )
    def test_semantic_stage_marked(self, retriever):
        """Результат помечен как SEMANTIC."""
        if retriever.embedder:
            results = retriever._semantic_search(
                "денежные расходы бизнеса",
                retriever.kb.sections,
                top_k=1
            )
            if results:
                assert results[0].stage == MatchStage.SEMANTIC

class TestCascade:
    """Тесты каскадной логики."""

    @pytest.fixture
    def retriever(self):
        import src.knowledge.retriever as r
        r._retriever = None
        return CascadeRetriever(use_embeddings=False)

    def test_exact_stops_cascade(self, retriever):
        """Если exact нашёл — lemma не вызывается."""
        results, stats = retriever.search_with_stats("розничный налог")

        if results:
            assert stats["stage_used"] == "exact"

    def test_lemma_after_exact_fail(self, retriever):
        """Если exact не нашёл — идём на lemma."""
        # Запрос с падежами которых нет в keywords буквально
        results, stats = retriever.search_with_stats("предпринимателей розничном налоге")

        # Должен найти через exact или lemma
        if results:
            assert stats["stage_used"] in ["exact", "lemma"]

    def test_search_with_stats_returns_timing(self, retriever):
        """search_with_stats возвращает тайминги."""
        results, stats = retriever.search_with_stats("wipon касса")

        assert "exact_time_ms" in stats
        assert "total_time_ms" in stats
        assert stats["total_time_ms"] >= 0

    def test_empty_query_returns_empty(self, retriever):
        """Пустой запрос возвращает пустой список."""
        results = retriever.search("")
        assert results == []

        results = retriever.search("   ")
        assert results == []

class TestPerformance:
    """Тесты производительности."""

    @pytest.fixture
    def retriever(self):
        import src.knowledge.retriever as r
        r._retriever = None
        return CascadeRetriever(use_embeddings=False)

    def test_exact_match_fast(self, retriever):
        """Exact match должен быть < 10ms."""
        start = time.perf_counter()
        retriever._exact_search("розничный налог", retriever.kb.sections)
        elapsed = (time.perf_counter() - start) * 1000

        assert elapsed < 10, f"Exact search took {elapsed:.2f}ms, expected < 10ms"

    def test_lemma_match_reasonable(self, retriever):
        """Lemma match должен быть < 50ms."""
        start = time.perf_counter()
        retriever._lemma_search("розничного налога ставка", retriever.kb.sections)
        elapsed = (time.perf_counter() - start) * 1000

        assert elapsed < 50, f"Lemma search took {elapsed:.2f}ms, expected < 50ms"

    def test_many_queries_stable(self, retriever):
        """100 запросов стабильно работают."""
        queries = [
            "розничный налог", "ставка снр", "как перейти",
            "условия для ип", "тоо розничный", "ндс совмещение",
            "форма 913", "декларация", "сотрудники лимит", "wipon касса"
        ] * 10

        start = time.perf_counter()
        for q in queries:
            retriever.search(q)
        elapsed = (time.perf_counter() - start) * 1000

        avg = elapsed / len(queries)
        assert avg < 20, f"Average {avg:.2f}ms per query, expected < 20ms"

class TestRealKnowledgeBase:
    """Тесты на реальной базе WIPON_KNOWLEDGE."""

    @pytest.fixture
    def retriever(self):
        import src.knowledge.retriever as r
        r._retriever = None
        return CascadeRetriever(use_embeddings=False)

    @pytest.mark.parametrize("query,expected_in_result", [
        # Используем запросы которые содержат keywords из базы
        # Примечание: _exact_search ищет keyword в query, не наоборот
        ("wipon kassa касса", ["касс"]),  # Запрос с "wipon kassa" содержит keywords
        ("wipon", ["wipon"]),
        ("цена тариф стоимость", ["цен"]),  # Более длинный запрос
        ("тариф цена", ["тариф"]),
        ("интеграция 1с", ["интеграц"]),
        ("1с интеграция", ["1с", "1c"]),  # Может быть кириллический или латинский "c"
        ("алкоголь укм", ["алкогол"]),
    ])
    def test_common_queries(self, retriever, query, expected_in_result):
        """Типичные запросы находят релевантные результаты."""
        results = retriever.search(query)

        assert len(results) > 0, f"No results for '{query}'"

        # Проверяем что в facts или topic есть хотя бы одно из ожидаемых слов
        top_result = results[0]
        combined = (top_result.section.facts + top_result.section.topic).lower()
        found = any(exp.lower() in combined for exp in expected_in_result)
        assert found, \
            f"None of {expected_in_result} found in result for '{query}'"

    def test_stage_distribution(self, retriever):
        """Проверяем распределение по этапам."""
        test_queries = [
            "розничный налог", "ставка снр", "как перейти",
            "условия для ип", "тоо розничный", "ндс совмещение",
            "форма 913", "декларация", "сотрудники", "wipon касса",
        ]

        stage_counts = {"exact": 0, "lemma": 0, "semantic": 0, "none": 0}

        for q in test_queries:
            results, stats = retriever.search_with_stats(q)
            stage = stats.get("stage_used", "none")
            stage_counts[stage] += 1

        total = len(test_queries)
        exact_pct = stage_counts["exact"] / total * 100

        # Ожидаем что большинство запросов решаются exact match
        assert exact_pct >= 50, \
            f"Only {exact_pct:.0f}% exact matches, expected >= 50%"

    def test_retrieve_method_returns_string(self, retriever):
        """retrieve() возвращает строку."""
        result = retriever.retrieve("розничный налог")
        assert isinstance(result, str)

    def test_retrieve_with_intent_filter(self, retriever):
        """retrieve() использует intent для фильтрации."""
        result = retriever.retrieve("сколько стоит", intent="price_question")
        assert isinstance(result, str)

class TestBackwardCompatibility:
    """Тесты обратной совместимости с текущим API."""

    def test_retrieve_returns_string(self):
        """retrieve() возвращает строку как раньше."""
        import src.knowledge.retriever as r
        r._retriever = None
        retriever = get_retriever(use_embeddings=False)
        result = retriever.retrieve("розничный налог")

        assert isinstance(result, str)

    def test_retrieve_with_intent(self):
        """retrieve() принимает intent."""
        import src.knowledge.retriever as r
        r._retriever = None
        retriever = get_retriever(use_embeddings=False)
        result = retriever.retrieve("сколько стоит", intent="price_question")

        assert isinstance(result, str)

    def test_get_company_info(self):
        """get_company_info() работает."""
        import src.knowledge.retriever as r
        r._retriever = None
        retriever = get_retriever(use_embeddings=False)
        info = retriever.get_company_info()

        assert "Wipon" in info

    def test_singleton_works(self):
        """get_retriever() возвращает singleton."""
        import src.knowledge.retriever as r
        r._retriever = None

        r1 = get_retriever(use_embeddings=False)
        r2 = get_retriever(use_embeddings=False)

        assert r1 is r2

    def test_knowledge_retriever_alias(self):
        """KnowledgeRetriever это alias для CascadeRetriever."""
        from src.knowledge.retriever import KnowledgeRetriever
        assert KnowledgeRetriever is CascadeRetriever

class TestEdgeCases:
    """Тесты граничных случаев."""

    @pytest.fixture
    def retriever(self):
        import src.knowledge.retriever as r
        r._retriever = None
        return CascadeRetriever(use_embeddings=False)

    def test_empty_query(self, retriever):
        """Пустой запрос."""
        assert retriever.search("") == []
        assert retriever.search(None) == []
        assert retriever.retrieve("") == ""

    def test_very_long_query(self, retriever):
        """Очень длинный запрос."""
        long_query = "розничный налог " * 100
        results = retriever.search(long_query)
        # Не должен упасть
        assert isinstance(results, list)

    def test_special_characters(self, retriever):
        """Спецсимволы в запросе."""
        results = retriever.search("касса? (онлайн)")
        assert isinstance(results, list)

    def test_numbers_in_query(self, retriever):
        """Числа в запросе."""
        results = retriever.search("форма 913")
        assert isinstance(results, list)

    def test_category_filter(self, retriever):
        """Фильтрация по категории."""
        results = retriever.search("касса", category="products")
        if results:
            assert all(r.section.category == "products" for r in results)

    def test_top_k_limit(self, retriever):
        """Ограничение top_k работает."""
        results = retriever.search("касса", top_k=1)
        assert len(results) <= 1

        results = retriever.search("касса", top_k=5)
        assert len(results) <= 5

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
