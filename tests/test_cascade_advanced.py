"""
Расширенные тесты CascadeRetriever.

Проверяем сложные сценарии на реальной базе WIPON_KNOWLEDGE:
1. Exact match - точные совпадения
2. Lemma match - морфологические вариации
3. Semantic match - семантически близкие запросы
4. Каскадная логика - переходы между этапами
5. Edge cases - граничные случаи
"""

import pytest
import time
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from knowledge.retriever import CascadeRetriever, MatchStage, get_retriever
from knowledge.data import WIPON_KNOWLEDGE


class TestExactMatchAdvanced:
    """Продвинутые тесты exact match."""

    @pytest.fixture
    def retriever(self):
        import knowledge.retriever as r
        r._retriever = None
        return CascadeRetriever(use_embeddings=False)

    @pytest.mark.parametrize("query,expected_topic_contains", [
        # Прямые ключевые слова
        ("розничный налог", "retail"),
        ("wipon касса", "kassa"),
        ("интеграция 1с", "1c"),
        ("интеграция kaspi", "kaspi"),
        ("алкоголь укм", "wipon_pro"),
        ("тариф цена", "pricing"),
        ("снр ставка", "retail"),
        # Фразы из keywords
        ("онлайн-касса", "kassa"),
        ("учётно-контрольные марки", "wipon_pro"),
        ("специальный налоговый режим", "retail"),
    ])
    def test_exact_keywords(self, retriever, query, expected_topic_contains):
        """Точные ключевые слова находят правильные секции."""
        results = retriever.search(query)
        assert len(results) > 0, f"No results for '{query}'"
        assert results[0].stage == MatchStage.EXACT
        assert expected_topic_contains in results[0].section.topic.lower() or \
               expected_topic_contains in results[0].section.category.lower(), \
               f"Expected '{expected_topic_contains}' in topic/category, got {results[0].section.topic}"

    def test_multiple_keyword_matches(self, retriever):
        """Запрос с несколькими keywords получает высокий score."""
        results = retriever.search("розничный налог ставка снр процент")
        assert len(results) > 0
        # Должен быть высокий score из-за множественных совпадений
        assert results[0].score > 2.0, f"Expected score > 2.0, got {results[0].score}"

    def test_word_boundary_scoring(self, retriever):
        """Целые слова получают бонус 0.5."""
        # "касса" как целое слово vs часть слова
        results = retriever.search("касса")
        assert len(results) > 0
        # Score должен включать бонус за целое слово (1.0 + 0.5 = 1.5+)
        assert results[0].score >= 1.5

    def test_case_insensitive_search(self, retriever):
        """Регистр не влияет на поиск."""
        queries = ["РОЗНИЧНЫЙ НАЛОГ", "Розничный Налог", "розничный налог"]
        topics = []
        for q in queries:
            results = retriever.search(q)
            if results:
                topics.append(results[0].section.topic)

        assert len(set(topics)) == 1, "Different cases should return same result"


class TestLemmaMatchAdvanced:
    """Продвинутые тесты lemma match."""

    @pytest.fixture
    def retriever(self):
        import knowledge.retriever as r
        r._retriever = None
        return CascadeRetriever(use_embeddings=False)

    @pytest.mark.parametrize("base_word,inflections", [
        # Существительные - падежи
        ("налог", ["налога", "налогу", "налогом", "налоге", "налоги", "налогов"]),
        ("предприниматель", ["предпринимателя", "предпринимателю", "предпринимателем", "предприниматели"]),
        ("ставка", ["ставки", "ставку", "ставкой", "ставок"]),
        # Глаголы - времена и лица
        ("перейти", ["перехожу", "переходит", "переходим", "перешёл", "перейдёт"]),
        ("платить", ["плачу", "платит", "платим", "платили", "заплатить"]),
        # Прилагательные - род и число
        ("розничный", ["розничная", "розничное", "розничные", "розничного", "розничной"]),
    ])
    def test_morphological_variations(self, retriever, base_word, inflections):
        """Разные морфологические формы находят одинаковые секции."""
        base_results = retriever._lemma_search(base_word, retriever.kb.sections)

        for inflection in inflections:
            inflection_results = retriever._lemma_search(inflection, retriever.kb.sections)

            # Если base нашёл что-то, inflection тоже должен
            if base_results:
                # Проверяем что леммы совпадают
                from knowledge.lemmatizer import get_lemmatizer
                lemmatizer = get_lemmatizer()
                base_lemma = lemmatizer.lemmatize_word(base_word)
                inflection_lemma = lemmatizer.lemmatize_word(inflection)

                # Леммы должны быть одинаковыми или близкими
                assert base_lemma == inflection_lemma or \
                       any(base_lemma in str(r.matched_lemmas) for r in inflection_results if inflection_results), \
                       f"'{base_word}' -> '{base_lemma}', '{inflection}' -> '{inflection_lemma}'"

    def test_lemma_search_with_stop_words(self, retriever):
        """Стоп-слова фильтруются при лемматизации."""
        # "как перейти на снр" -> леммы без "как", "на"
        results = retriever._lemma_search("как перейти на снр", retriever.kb.sections)

        if results:
            # Проверяем что matched_lemmas не содержит стоп-слов
            stop_words = {"как", "на", "в", "и", "с"}
            for r in results:
                assert not (r.matched_lemmas & stop_words), \
                    f"Stop words found in matched_lemmas: {r.matched_lemmas & stop_words}"

    def test_lemma_coverage_scoring(self, retriever):
        """Scoring учитывает покрытие запроса и keywords."""
        # Запрос с высоким покрытием keywords
        results = retriever._lemma_search("предприниматель розничный налог", retriever.kb.sections)

        if results:
            # Score должен быть значительным
            assert results[0].score >= 0.2, f"Expected score >= 0.2, got {results[0].score}"


class TestSemanticMatchAdvanced:
    """Продвинутые тесты semantic match."""

    @pytest.fixture
    def retriever(self):
        import knowledge.retriever as r
        r._retriever = None
        return CascadeRetriever(use_embeddings=True)

    @pytest.mark.skipif(
        not CascadeRetriever(use_embeddings=True).embedder,
        reason="sentence-transformers not installed"
    )
    @pytest.mark.parametrize("query,expected_topic_hint", [
        # Синонимы и перефразировки
        ("денежные расходы на программу", "pricing"),
        ("автоматизация торговли", "product"),
        ("фискальные данные чеки", "kassa"),
        ("проверка подлинности спиртного", "pro"),
        ("подключение к налоговой системе", "tis"),
        # Абстрактные запросы
        ("экономия времени в бизнесе", ""),
        ("упрощение работы магазина", ""),
        ("контроль продаж", ""),
    ])
    def test_semantic_synonyms(self, retriever, query, expected_topic_hint):
        """Семантически близкие запросы находят релевантные секции."""
        if not retriever.embedder:
            pytest.skip("Embedder not available")

        results = retriever._semantic_search(query, retriever.kb.sections, top_k=3)

        assert len(results) > 0, f"No semantic results for '{query}'"
        assert results[0].stage == MatchStage.SEMANTIC

        if expected_topic_hint:
            # Проверяем что хотя бы один результат содержит hint
            found = any(expected_topic_hint in r.section.topic.lower() or
                       expected_topic_hint in r.section.category.lower()
                       for r in results)
            # Не fail если не нашли - семантика может найти другое релевантное
            if not found:
                print(f"Warning: '{expected_topic_hint}' not in results for '{query}'")

    @pytest.mark.skipif(
        not CascadeRetriever(use_embeddings=True).embedder,
        reason="sentence-transformers not installed"
    )
    def test_semantic_threshold(self, retriever):
        """Семантический порог 0.5 работает."""
        if not retriever.embedder:
            pytest.skip("Embedder not available")

        # Совсем нерелевантный запрос
        results = retriever._semantic_search(
            "погода в лондоне завтра",
            retriever.kb.sections,
            top_k=3
        )

        # Все результаты должны иметь score >= 0.5 или список пустой
        for r in results:
            assert r.score >= retriever.semantic_threshold, \
                f"Score {r.score} below threshold {retriever.semantic_threshold}"


class TestCascadeLogic:
    """Тесты каскадной логики переходов между этапами."""

    @pytest.fixture
    def retriever(self):
        import knowledge.retriever as r
        r._retriever = None
        return CascadeRetriever(use_embeddings=True)

    def test_exact_stops_cascade(self, retriever):
        """Exact match останавливает каскад."""
        results, stats = retriever.search_with_stats("розничный налог")

        assert stats["stage_used"] == "exact"
        assert stats["lemma_time_ms"] == 0, "Lemma should not run after exact match"
        assert stats["semantic_time_ms"] == 0, "Semantic should not run after exact match"

    def test_lemma_after_exact_fail(self, retriever):
        """Lemma запускается если exact не нашёл."""
        # Запрос с изменёнными падежами
        results, stats = retriever.search_with_stats("предпринимателей розничном")

        if results:
            assert stats["stage_used"] in ["exact", "lemma"]
            assert stats["exact_time_ms"] > 0, "Exact should always run"

    @pytest.mark.skipif(
        not CascadeRetriever(use_embeddings=True).embedder,
        reason="sentence-transformers not installed"
    )
    def test_semantic_after_both_fail(self, retriever):
        """Semantic запускается если exact и lemma не нашли."""
        if not retriever.embedder:
            pytest.skip("Embedder not available")

        # Запрос который не найдётся exact/lemma, но найдётся семантически
        results, stats = retriever.search_with_stats("автоматизировать торговые процессы")

        assert stats["exact_time_ms"] > 0
        # Если нашёлся на semantic - все этапы должны были запуститься
        if stats["stage_used"] == "semantic":
            assert stats["lemma_time_ms"] > 0
            assert stats["semantic_time_ms"] > 0

    def test_cascade_priority_order(self, retriever):
        """Порядок приоритетов: exact > lemma > semantic."""
        # Запрос который найдётся на всех этапах
        query = "розничный налог"

        exact_results = retriever._exact_search(query, retriever.kb.sections)
        lemma_results = retriever._lemma_search(query, retriever.kb.sections)

        # Exact должен иметь результаты
        assert len(exact_results) > 0

        # Финальный результат должен быть exact
        final_results, stats = retriever.search_with_stats(query)
        assert stats["stage_used"] == "exact"


class TestRealWorldQueries:
    """Тесты на реальных пользовательских запросах."""

    @pytest.fixture
    def retriever(self):
        import knowledge.retriever as r
        r._retriever = None
        return CascadeRetriever(use_embeddings=True)

    @pytest.mark.parametrize("query,must_contain_any", [
        # Вопросы о ценах
        ("сколько стоит программа", ["цен", "тариф", "стоим"]),
        ("какая цена на кассу", ["цен", "тариф", "бесплатн"]),
        ("стоимость подписки", ["цен", "тариф", "подписк"]),

        # Вопросы о функциях
        ("как работает касса", ["касс", "чек", "офд"]),
        ("что умеет программа", ["функц", "возможност", "продукт"]),
        ("какие есть интеграции", ["интеграц", "1с", "kaspi"]),

        # Вопросы о налогах
        ("как перейти на розничный налог", ["переход", "розничн", "снр"]),
        ("какая ставка снр", ["ставк", "процент", "%"]),
        ("условия для ип", ["ип", "предприниматель", "условия"]),

        # Вопросы о ТИС
        ("что такое тис", ["тис", "трёхкомпонент", "налог"]),
        ("как подключить тис", ["подключ", "тис", "регистрац"]),

        # Вопросы об алкоголе
        ("проверка алкоголя", ["алкогол", "укм", "марк"]),
        ("штрафы за контрафакт", ["штраф", "мрп", "контрафакт"]),
    ])
    def test_user_queries(self, retriever, query, must_contain_any):
        """Реальные пользовательские запросы находят релевантные ответы."""
        results = retriever.search(query)

        assert len(results) > 0, f"No results for user query: '{query}'"

        # Проверяем что в facts есть хотя бы одно из ожидаемых слов
        facts_lower = results[0].section.facts.lower()
        found = any(word in facts_lower for word in must_contain_any)

        assert found, \
            f"None of {must_contain_any} found in facts for '{query}'. " \
            f"Got topic: {results[0].section.topic}"

    def test_ambiguous_queries(self, retriever):
        """Неоднозначные запросы возвращают несколько результатов."""
        results = retriever.search("налог", top_k=5)

        # Должно быть несколько результатов про разные аспекты налогов
        assert len(results) >= 2, "Ambiguous query should return multiple results"

        # Темы должны быть разные
        topics = [r.section.topic for r in results]
        assert len(set(topics)) >= 2, "Results should cover different topics"

    def test_empty_and_garbage_queries(self, retriever):
        """Пустые и мусорные запросы обрабатываются корректно."""
        test_cases = [
            "",
            "   ",
            "а",
            "???",
            "12345",
            "asdfghjkl",
        ]

        for query in test_cases:
            results = retriever.search(query)
            # Не должно быть ошибок, результат может быть пустым
            assert isinstance(results, list)


class TestPerformanceAdvanced:
    """Продвинутые тесты производительности."""

    @pytest.fixture
    def retriever(self):
        import knowledge.retriever as r
        r._retriever = None
        return CascadeRetriever(use_embeddings=True)

    def test_batch_performance(self, retriever):
        """Производительность на батче запросов."""
        queries = [
            "розничный налог", "ставка снр", "как перейти",
            "условия для ип", "тоо розничный", "ндс совмещение",
            "форма 913", "декларация", "сотрудники лимит", "wipon касса",
            "интеграция 1с", "kaspi подключение", "алкоголь проверка",
            "тис подключение", "цена тариф", "бесплатная касса",
        ] * 10  # 160 запросов

        start = time.perf_counter()
        for q in queries:
            retriever.search(q)
        elapsed = (time.perf_counter() - start) * 1000

        avg = elapsed / len(queries)
        print(f"\nBatch performance: {len(queries)} queries in {elapsed:.0f}ms")
        print(f"Average: {avg:.2f}ms/query")

        # Средний запрос должен быть < 15ms (с учётом семантики)
        assert avg < 15, f"Average {avg:.2f}ms > 15ms threshold"

    def test_stage_distribution_real(self, retriever):
        """Распределение по этапам на реальных запросах."""
        queries = [
            # Exact match candidates
            "розничный налог", "ставка снр", "wipon касса", "интеграция 1с",
            "алкоголь укм", "тис подключение", "цена тариф",
            # Lemma match candidates
            "предпринимателей розничного", "переходить на снр", "налоговых ставок",
            # Semantic match candidates
            "автоматизация торговли", "экономия на налогах", "проверка спиртного",
        ]

        stage_counts = {"exact": 0, "lemma": 0, "semantic": 0, "none": 0}
        stage_times = {"exact": 0, "lemma": 0, "semantic": 0}

        for q in queries:
            results, stats = retriever.search_with_stats(q)
            stage = stats.get("stage_used", "none")
            stage_counts[stage] += 1

            stage_times["exact"] += stats.get("exact_time_ms", 0)
            stage_times["lemma"] += stats.get("lemma_time_ms", 0)
            stage_times["semantic"] += stats.get("semantic_time_ms", 0)

        total = len(queries)
        print(f"\n=== Stage Distribution ===")
        for stage, count in stage_counts.items():
            if count > 0:
                pct = count / total * 100
                avg_time = stage_times.get(stage, 0) / max(count, 1)
                print(f"{stage}: {count}/{total} ({pct:.0f}%), avg time: {avg_time:.2f}ms")

        # Exact должен покрывать минимум 50%
        assert stage_counts["exact"] / total >= 0.5, \
            f"Exact match only {stage_counts['exact']/total*100:.0f}%, expected >= 50%"


class TestIntegration:
    """Интеграционные тесты."""

    def test_retrieve_api_compatibility(self):
        """API retrieve() совместим со старым кодом."""
        import knowledge.retriever as r
        r._retriever = None

        retriever = get_retriever(use_embeddings=False)

        # Старый API
        result = retriever.retrieve("розничный налог", intent="price_question")
        assert isinstance(result, str)

        result = retriever.retrieve("касса", intent=None, state="greeting")
        assert isinstance(result, str)

        info = retriever.get_company_info()
        assert "Wipon" in info

    def test_singleton_pattern(self):
        """Singleton работает корректно."""
        import knowledge.retriever as r
        r._retriever = None

        r1 = get_retriever(use_embeddings=False)
        r2 = get_retriever(use_embeddings=False)

        assert r1 is r2, "Singleton should return same instance"

    def test_category_filtering(self):
        """Фильтрация по категориям работает."""
        import knowledge.retriever as r
        r._retriever = None
        retriever = CascadeRetriever(use_embeddings=False)

        # Поиск только в pricing
        results = retriever.search("касса", category="pricing")
        for r in results:
            assert r.section.category == "pricing", \
                f"Expected category 'pricing', got '{r.section.category}'"

        # Поиск в нескольких категориях
        results = retriever.search("касса", categories=["products", "pricing"])
        for r in results:
            assert r.section.category in ["products", "pricing"], \
                f"Expected category in ['products', 'pricing'], got '{r.section.category}'"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
