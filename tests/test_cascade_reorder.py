"""
Тесты нового порядка каскадного retriever'а:
  1. Semantic (FRIDA) → 2. Exact → 3. Lemma

Проверяем:
- Порядок этапов (semantic первый)
- Threshold 0.25 даёт ≥85% hit rate
- Fallback на exact/lemma когда semantic не сработал
- device из settings (embedder_device)
- Обратная совместимость API
"""

import pytest
import time
import sys
import os

from src.knowledge.retriever import (
    CascadeRetriever, MatchStage, SearchResult, get_retriever, reset_retriever,
)
from src.knowledge.loader import load_knowledge_base
from src.settings import settings


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def kb():
    """Shared KB for all tests (loads once)."""
    return load_knowledge_base()


@pytest.fixture(scope="module")
def retriever_emb(kb):
    """Retriever с эмбеддингами (FRIDA)."""
    import src.knowledge.retriever as r
    r._retriever = None
    return CascadeRetriever(knowledge_base=kb, use_embeddings=True, semantic_threshold=0.25)


@pytest.fixture
def retriever_no_emb(kb):
    """Retriever без эмбеддингов (exact+lemma only)."""
    import src.knowledge.retriever as r
    r._retriever = None
    return CascadeRetriever(knowledge_base=kb, use_embeddings=False)


# ─── 1. Порядок этапов ──────────────────────────────────────────────────────

class TestCascadeOrder:
    """Semantic первый, exact и lemma — fallback."""

    def test_semantic_is_first_stage(self, retriever_emb):
        """При включённых эмбеддингах semantic срабатывает первым."""
        results, stats = retriever_emb.search_with_stats("Сколько стоит ваша система?")
        assert len(results) > 0
        assert stats["stage_used"] == "semantic"
        assert stats["semantic_time_ms"] > 0

    def test_exact_fallback_when_no_embeddings(self, retriever_no_emb):
        """Без эмбеддингов fallback на exact."""
        results, stats = retriever_no_emb.search_with_stats("розничный налог")
        if results:
            assert stats["stage_used"] in ("exact", "lemma")

    def test_semantic_blocks_exact(self, retriever_emb):
        """Если semantic нашёл — exact не вызывается."""
        results, stats = retriever_emb.search_with_stats("какие тарифы у вас есть?")
        assert len(results) > 0
        assert stats["stage_used"] == "semantic"
        # exact не должен был запускаться
        assert stats["exact_time_ms"] == 0

    def test_fallback_to_exact_on_low_semantic(self, retriever_emb):
        """При очень высоком semantic threshold — fallback на exact."""
        # Сохраняем и ставим нереально высокий threshold
        orig = retriever_emb.semantic_threshold
        retriever_emb.semantic_threshold = 0.99
        try:
            results, stats = retriever_emb.search_with_stats("розничный налог")
            if results:
                assert stats["stage_used"] in ("exact", "lemma")
        finally:
            retriever_emb.semantic_threshold = orig


# ─── 2. Качество semantic поиска ─────────────────────────────────────────────

class TestSemanticQuality:
    """Hit rate на типичных запросах."""

    QUERIES = [
        ("Сколько стоит ваша система?", ["pricing"]),
        ("Какие тарифы у вас есть?", ["pricing", "tariff"]),
        ("какие отчёты можно строить?", ["analytics"]),
        ("как работает учёт товаров?", ["inventory"]),
        ("можно ли управлять сотрудниками?", ["employees"]),
        ("есть ли мобильное приложение?", ["mobile"]),
        ("интеграция с 1С есть?", ["1c", "integrations"]),
        ("работает ли с Kaspi?", ["kaspi"]),
        ("какое оборудование нужно?", ["equipment"]),
        ("как работает фискализация?", ["fiscal"]),
        ("что такое ТИС?", ["tis"]),
        ("что будет если интернет пропадёт?", ["stability", "offline"]),
        ("какие продукты у вас есть?", ["products"]),
        ("работаете ли вы в Алматы?", ["regions"]),
        ("как обучить сотрудников?", ["support", "training", "onboarding"]),
        ("рассрочка есть?", ["pricing", "payment", "installment"]),
        ("как настроить систему лояльности?", ["promotions", "loyalty", "bonus"]),
        ("как вести инвентаризацию?", ["inventory"]),
        ("можно ли импортировать товары из Excel?", ["inventory", "import", "excel"]),
        ("есть ли техническая поддержка 24/7?", ["support"]),
    ]

    def test_hit_rate_above_85(self, retriever_emb):
        """Hit rate ≥ 85% на 20 типичных запросах."""
        hits = 0
        for query, expected in self.QUERIES:
            results = retriever_emb._semantic_search(query, retriever_emb.kb.sections, top_k=3)
            for r in results:
                key = f"{r.section.category}/{r.section.topic}".lower()
                if any(p.lower() in key for p in expected):
                    hits += 1
                    break

        hit_rate = hits / len(self.QUERIES)
        assert hit_rate >= 0.85, (
            f"Hit rate {hit_rate:.1%} < 85%. "
            f"Hits: {hits}/{len(self.QUERIES)}"
        )

    def test_mrr_above_07(self, retriever_emb):
        """MRR ≥ 0.7 (первый результат обычно правильный)."""
        mrr_sum = 0.0
        for query, expected in self.QUERIES:
            results = retriever_emb._semantic_search(query, retriever_emb.kb.sections, top_k=3)
            for rank, r in enumerate(results, 1):
                key = f"{r.section.category}/{r.section.topic}".lower()
                if any(p.lower() in key for p in expected):
                    mrr_sum += 1.0 / rank
                    break

        mrr = mrr_sum / len(self.QUERIES)
        assert mrr >= 0.7, f"MRR {mrr:.3f} < 0.7"


# ─── 3. Threshold корректный ─────────────────────────────────────────────────

class TestThreshold:
    """Проверки threshold из settings."""

    def test_settings_threshold_is_025(self):
        """settings.yaml содержит semantic threshold 0.25."""
        assert settings.retriever.thresholds.semantic == 0.25

    def test_all_results_above_threshold(self, retriever_emb):
        """Все результаты semantic поиска имеют score ≥ threshold."""
        results = retriever_emb._semantic_search(
            "стоимость подключения", retriever_emb.kb.sections, top_k=5
        )
        for r in results:
            assert r.score >= 0.25, f"Score {r.score:.3f} < threshold 0.25"

    def test_no_garbage_at_025(self, retriever_emb):
        """При 0.25 не возвращается мусор (score слишком близкий к порогу)."""
        results = retriever_emb._semantic_search(
            "погода завтра в Астане", retriever_emb.kb.sections, top_k=3
        )
        # Нерелевантный запрос — ожидаем мало или 0 результатов
        # (FRIDA не должна найти секции про погоду в KB)
        if results:
            # Если что-то нашлось, score должен быть разумным
            assert results[0].score < 0.5, (
                f"Garbage query got suspiciously high score: {results[0].score:.3f}"
            )


# ─── 4. Производительность ───────────────────────────────────────────────────

class TestPerformance:
    """Тайминги semantic поиска."""

    def test_semantic_search_under_500ms(self, retriever_emb):
        """Один semantic поиск < 500ms."""
        start = time.perf_counter()
        retriever_emb._semantic_search("цена за 5 точек", retriever_emb.kb.sections, top_k=3)
        elapsed = (time.perf_counter() - start) * 1000
        assert elapsed < 500, f"Semantic search took {elapsed:.0f}ms, expected < 500ms"

    def test_full_cascade_under_600ms(self, retriever_emb):
        """Полный каскад (semantic first) < 600ms."""
        start = time.perf_counter()
        retriever_emb.search("интеграция с 1С", top_k=3)
        elapsed = (time.perf_counter() - start) * 1000
        assert elapsed < 600, f"Full cascade took {elapsed:.0f}ms, expected < 600ms"


# ─── 5. Обратная совместимость ────────────────────────────────────────────────

class TestBackwardCompat:
    """API не сломан."""

    def test_retrieve_returns_string(self, retriever_emb):
        """retrieve() возвращает строку."""
        result = retriever_emb.retrieve("сколько стоит")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_retrieve_with_urls(self, retriever_emb):
        """retrieve_with_urls() возвращает (str, list)."""
        facts, urls = retriever_emb.retrieve_with_urls("тарифы")
        assert isinstance(facts, str)
        assert isinstance(urls, list)

    def test_search_result_has_stage(self, retriever_emb):
        """SearchResult содержит stage."""
        results = retriever_emb.search("цена за 5 точек")
        assert len(results) > 0
        assert results[0].stage in (MatchStage.SEMANTIC, MatchStage.EXACT, MatchStage.LEMMA)

    def test_category_filter_works(self, retriever_emb):
        """Фильтрация по категории."""
        results = retriever_emb.search("касса", categories=["products"])
        for r in results:
            assert r.section.category == "products"

    def test_empty_query(self, retriever_emb):
        """Пустой запрос."""
        assert retriever_emb.search("") == []
        assert retriever_emb.search("   ") == []
        assert retriever_emb.retrieve("") == ""

    def test_singleton(self, kb):
        """get_retriever() singleton работает."""
        import src.knowledge.retriever as r
        r._retriever = None
        r1 = get_retriever(use_embeddings=False)
        r2 = get_retriever(use_embeddings=False)
        assert r1 is r2
        r._retriever = None


# ─── 6. Device config ────────────────────────────────────────────────────────

class TestDeviceConfig:
    """embedder_device читается из settings."""

    def test_settings_has_embedder_device(self):
        """settings.yaml содержит embedder_device."""
        device = getattr(settings.retriever, 'embedder_device', None)
        assert device is not None, "embedder_device not in settings"
        assert device in ("cpu", "cuda"), f"Invalid device: {device}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
