"""
Каскадный Retriever с 3-этапным поиском.

Этапы:
1. Semantic Match — cosine similarity эмбеддингов (Qwen3-Embedding-4B через TEI)
2. Exact Match — поиск keyword как подстроки в запросе
3. Lemma Match — сравнение лемматизированных множеств
"""

import re
import sys
import time
import warnings
import threading
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Set, Dict, Any
from enum import Enum
from pathlib import Path

from src.settings import settings
from src.logger import logger

from .base import KnowledgeSection, KnowledgeBase, section_embed_text
from .loader import load_knowledge_base
from .lemmatizer import get_lemmatizer
from .reranker import get_reranker


# Маппинг интентов на категории базы знаний
# Принцип: каждый интент связан с категориями, которые могут содержать релевантные факты
#
# ВАЖНО: Используйте только существующие категории из knowledge/data/:
# equipment, products, tis, support, pricing, inventory, features, delivery,
# integrations, analytics, employees, fiscal, stability, mobile, promotions,
# competitors, faq
#
# Интенты не требующие поиска по БЗ перечислены в SKIP_RETRIEVAL_INTENTS ниже.
INTENT_TO_CATEGORY = {
    # =================================================================
    # ВОПРОСЫ О ПРОДУКТЕ/ЦЕНЕ (требуют информации из базы)
    # =================================================================
    "price_question": ["pricing"],
    "pricing_details": ["pricing", "promotions"],
    "question_features": [
        "features", "products", "tis", "analytics", "inventory",
        "support", "integrations",
        "equipment", "employees", "fiscal", "stability", "faq",
    ],
    "question_integrations": ["integrations"],
    "comparison": ["competitors", "products", "features"],

    # =================================================================
    # ВОЗРАЖЕНИЯ (требуют аргументов из базы)
    # =================================================================
    "objection_competitor": ["competitors", "products", "features"],
    "objection_price": ["pricing", "products", "promotions"],
    "objection_no_time": ["support", "mobile"],  # быстрый старт в support, мобильность
    "objection_think": ["products", "features", "support"],  # преимущества в products/features

    # =================================================================
    # ЗАПРОСЫ НА ДЕЙСТВИЕ (требуют контактной информации)
    # =================================================================
    "callback_request": ["support", "delivery"],  # контакты в support и delivery
    "demo_request": ["support", "products"],
    "consultation_request": ["support", "features", "products"],
    "contact_provided": ["support", "delivery"],

    # =================================================================
    # СОГЛАСИЕ/ИНТЕРЕС (общая информация)
    # =================================================================
    "agreement": ["pricing", "support", "products"],

    # =================================================================
    # SPIN ИНТЕНТЫ
    # =================================================================
    # need_expressed: клиент хочет решение - можно показать преимущества
    "need_expressed": ["features", "products"],
    # no_problem/no_need: отрицание проблемы/потребности - показать ценность продукта
    "no_problem": ["products", "features"],
    "no_need": ["products", "features"],

    # =================================================================
    # МЕТА-ИНТЕНТЫ (request_brevity может потребовать фактов для краткого ответа)
    # =================================================================
    "request_brevity": [
        "features", "products", "pricing", "equipment", "employees",
        "support", "integrations",
    ],
}

# Интенты, для которых поиск по базе знаний НЕ нужен.
# При встрече этих интентов retrieve() возвращает "" сразу (без обращения к KB).
SKIP_RETRIEVAL_INTENTS = frozenset({
    "greeting", "farewell", "gratitude", "small_talk", "rejection", "unclear",
    "go_back", "correct_info", "disambiguation_needed", "fallback_close",
    "situation_provided", "problem_revealed", "implication_acknowledged", "info_provided",
})


class MatchStage(Enum):
    """Этап, на котором найден результат."""
    EXACT = "exact"
    LEMMA = "lemma"
    SEMANTIC = "semantic"
    NONE = "none"


@dataclass
class SearchResult:
    """Результат поиска."""
    section: KnowledgeSection
    score: float
    stage: MatchStage
    matched_keywords: List[str] = field(default_factory=list)
    matched_lemmas: Set[str] = field(default_factory=set)


class CascadeRetriever:
    """
    Каскадный retriever с 3-этапным поиском.

    Этапы:
    1. Semantic match — cosine similarity эмбеддингов (Qwen3-Embedding-4B через TEI)
    2. Exact match — поиск keyword как подстроки в запросе
    3. Lemma match — сравнение лемматизированных множеств
    """
    _FACTUAL_QUERY_RE = re.compile(
        r"(?:\?|сколько|какие?|какой|расскажите|посоветуй|поч[её]м|цен[аы]|стоимост"
        r"|можно\s+ли|есть\s+ли|как\s+работает|как\s+это\s+работает|чем\s+отлич"
        r"|какие\s+банки|какой\s+тариф|какие\s+тарифы|рассрочк|офд|маркировк|1[cс]\b)",
        re.IGNORECASE,
    )

    # Qwen3-Embedding-4B query instruction for asymmetric retrieval
    _QUERY_INSTRUCTION = (
        "Instruct: Given a user query, retrieve relevant knowledge base passages "
        "that answer the query.\nQuery: "
    )

    def __init__(
        self,
        knowledge_base: KnowledgeBase = None,
        use_embeddings: bool = None,
        exact_threshold: float = None,
        lemma_threshold: float = None,
        semantic_threshold: float = None,
        cache_name: str = "kb_sections",
    ):
        """
        Инициализация retriever.
        Параметры берутся из settings.yaml если не указаны явно.

        Args:
            knowledge_base: База знаний (по умолчанию загружается из YAML)
            use_embeddings: Использовать ли семантический поиск
            exact_threshold: Минимальный score для exact match
            lemma_threshold: Минимальный score для lemma match
            semantic_threshold: Минимальный score для semantic match
        """
        self.kb = knowledge_base if knowledge_base is not None else load_knowledge_base()

        # Параметры из settings (с возможностью переопределения)
        self.use_embeddings = use_embeddings if use_embeddings is not None else settings.retriever.use_embeddings
        self.exact_threshold = exact_threshold if exact_threshold is not None else settings.retriever.thresholds.exact
        self.lemma_threshold = lemma_threshold if lemma_threshold is not None else settings.retriever.thresholds.lemma
        self.semantic_threshold = semantic_threshold if semantic_threshold is not None else settings.retriever.thresholds.semantic

        # Лемматизатор
        self.lemmatizer = get_lemmatizer()

        # Эмбеддинги через TEI
        self._cache_name = cache_name
        self._tei_url = getattr(
            getattr(settings, 'retriever', None),
            'embedder_url',
            'http://tei-embed:80'
        ).rstrip('/')
        self._embeddings_ready = False
        self.np = None

        # Reranker параметры из settings
        self.reranker_enabled = getattr(
            getattr(settings, 'reranker', None),
            'enabled',
            False
        )
        self.rerank_threshold = getattr(
            getattr(settings, 'reranker', None),
            'threshold',
            0.5
        )
        self.rerank_candidates = getattr(
            getattr(settings, 'reranker', None),
            'candidates_count',
            10
        )

        # Предвычисляем леммы для всех keywords
        self._index_lemmas()

        # Инициализируем эмбеддинги если нужно
        if self.use_embeddings:
            self._init_embeddings()

    def _index_lemmas(self):
        """Предвычислить леммы для всех keywords при инициализации."""
        for section in self.kb.sections:
            all_lemmas = set()
            for keyword in section.keywords:
                lemmas = self.lemmatizer.lemmatize_to_set(keyword, remove_stop_words=True)
                all_lemmas.update(lemmas)
            section.lemmatized_keywords = all_lemmas

    def _init_embeddings(self):
        """Индексировать секции через TEI /embed endpoint (с disk-кэшем)."""
        import numpy as np
        from src.knowledge.tei_client import embed_texts_cached
        self.np = np

        texts = [section_embed_text(s) for s in self.kb.sections]

        try:
            arr = embed_texts_cached(
                texts,
                cache_name=self._cache_name,
                tei_url=self._tei_url,
            )
            if arr is None:
                raise RuntimeError("TEI embed returned None")

            for i, section in enumerate(self.kb.sections):
                section.embedding = arr[i].tolist()

            self._embeddings_ready = True
            print(f"[CascadeRetriever] Indexed {len(texts)} sections via TEI ({self._tei_url})")
        except Exception as e:
            print(f"[CascadeRetriever] TEI embedding failed: {e}, using keywords only")
            self.use_embeddings = False

    def retrieve(
        self,
        message: str,
        intent: str = None,
        state: str = None,
        categories: List[str] = None,
        top_k: int = None
    ) -> str:
        """
        Найти релевантные факты (совместимость с текущим API).

        При низком score использует reranker для переоценки кандидатов.

        Args:
            message: Сообщение пользователя
            intent: Классифицированный интент (для fallback на INTENT_TO_CATEGORY)
            state: Текущее состояние (не используется, для совместимости)
            categories: Список категорий для поиска (приоритет над intent)
            top_k: Максимум секций для возврата (по умолчанию из settings)

        Returns:
            Строка с фактами, разделёнными "---", или пустая строка
        """
        if not message or not message.strip():
            return ""
        _looks_factual = bool(self._FACTUAL_QUERY_RE.search(message or ""))

        # Интенты не требующие поиска — возвращаем сразу
        if intent and intent in SKIP_RETRIEVAL_INTENTS and not _looks_factual:
            return ""

        # Используем default_top_k из settings если не указано
        if top_k is None:
            top_k = settings.retriever.default_top_k

        # ИЗМЕНЕНИЕ: Приоритет categories > intent
        # Если categories переданы явно (от CategoryRouter), используем их
        # Иначе fallback на старый маппинг INTENT_TO_CATEGORY
        if categories is None:
            if intent:
                if intent in INTENT_TO_CATEGORY:
                    intent_categories = INTENT_TO_CATEGORY[intent]
                    if intent_categories:
                        categories = intent_categories
                else:
                    # Неизвестный интент — логируем и используем fallback категории
                    logger.warning(
                        "Unknown intent for INTENT_TO_CATEGORY mapping",
                        intent=intent,
                        fallback="using broad search for factual query"
                    )
                    categories = None if _looks_factual else ["faq", "features"]

        # Если reranker включён — берём больше кандидатов
        search_top_k = self.rerank_candidates if self.reranker_enabled else top_k

        # Ищем
        results = self.search(message, categories=categories, top_k=search_top_k)
        if not results and categories is not None and _looks_factual:
            results = self.search(message, categories=None, top_k=search_top_k)

        if not results:
            return ""

        # Проверяем нужен ли reranking
        if self.reranker_enabled and results[0].score < self.rerank_threshold:
            # Низкий score — используем reranker
            reranker = get_reranker()
            if reranker.is_available():
                results = reranker.rerank(message, results, top_k)
            else:
                results = results[:top_k]
        else:
            # Высокий score — берём как есть
            results = results[:top_k]

        # Filter out sensitive sections
        results = [r for r in results if not r.section.sensitive]
        # Формируем строку
        facts = [r.section.facts.strip() for r in results]
        return "\n\n---\n\n".join(facts)

    def retrieve_with_urls(
        self,
        message: str,
        intent: str = None,
        state: str = None,
        categories: List[str] = None,
        top_k: int = None
    ) -> Tuple[str, List[Dict[str, str]]]:
        """
        Найти релевантные факты с URL-ссылками.

        Возвращает как текстовые факты, так и структурированные URL
        из найденных секций базы знаний.

        Args:
            message: Сообщение пользователя
            intent: Классифицированный интент
            state: Текущее состояние
            categories: Список категорий для поиска
            top_k: Максимум секций

        Returns:
            Tuple[str, List[Dict[str, str]]]:
                - Строка с фактами, разделёнными "---"
                - Список URL-объектов [{"url": ..., "label": ..., "type": ...}]
        """
        if not message or not message.strip():
            return "", []
        _looks_factual = bool(self._FACTUAL_QUERY_RE.search(message or ""))

        # Интенты не требующие поиска — возвращаем сразу
        if intent and intent in SKIP_RETRIEVAL_INTENTS and not _looks_factual:
            return "", []

        if top_k is None:
            top_k = settings.retriever.default_top_k

        # Определяем категории
        if categories is None:
            if intent:
                if intent in INTENT_TO_CATEGORY:
                    intent_categories = INTENT_TO_CATEGORY[intent]
                    if intent_categories:
                        categories = intent_categories
                else:
                    categories = None if _looks_factual else ["faq", "features"]

        search_top_k = self.rerank_candidates if self.reranker_enabled else top_k
        results = self.search(message, categories=categories, top_k=search_top_k)
        if not results and categories is not None and _looks_factual:
            results = self.search(message, categories=None, top_k=search_top_k)

        if not results:
            return "", []

        # Reranking if needed
        if self.reranker_enabled and results[0].score < self.rerank_threshold:
            reranker = get_reranker()
            if reranker.is_available():
                results = reranker.rerank(message, results, top_k)
            else:
                results = results[:top_k]
        else:
            results = results[:top_k]

        # Filter out sensitive sections
        results = [r for r in results if not r.section.sensitive]
        # Собираем факты
        facts = [r.section.facts.strip() for r in results]

        # Собираем URLs из всех найденных секций
        urls: List[Dict[str, str]] = []
        seen_urls = set()  # Дедупликация
        for r in results:
            section_urls = getattr(r.section, 'urls', []) or []
            for url_info in section_urls:
                url = url_info.get('url', '')
                if url and url not in seen_urls:
                    urls.append(url_info)
                    seen_urls.add(url)

        return "\n\n---\n\n".join(facts), urls

    def search(
        self,
        query: str,
        category: Optional[str] = None,
        categories: Optional[List[str]] = None,
        top_k: int = 3
    ) -> List[SearchResult]:
        """
        Поиск с детальными результатами.

        Args:
            query: Текст запроса
            category: Фильтр по одной категории (опционально, для обратной совместимости)
            categories: Фильтр по списку категорий (опционально)
            top_k: Максимум результатов

        Returns:
            Список SearchResult с информацией о каждом результате
        """
        if not query or not query.strip():
            return []

        # Фильтруем секции по категориям если указаны
        sections = self.kb.sections

        # Приоритет: categories > category
        if categories:
            sections = [s for s in sections if s.category in categories]
        elif category:
            sections = [s for s in sections if s.category == category]

        if not sections:
            requested = categories if categories else ([category] if category else [])
            logger.warning(
                "Category filter produced zero sections, returning empty results",
                requested_categories=requested,
                available_categories=list({s.category for s in self.kb.sections}),
            )
            return []

        # Всегда запускаем все 3 этапа и объединяем через RRF.
        semantic_results: List[SearchResult] = []
        if self.use_embeddings and self._embeddings_ready:
            semantic_results = self._semantic_search(query, sections, top_k=top_k * 3)
        exact_results = self._exact_search(query, sections)
        lemma_results = self._lemma_search(query, sections)

        if not semantic_results and not exact_results and not lemma_results:
            return []

        return self._rrf_merge([semantic_results, exact_results, lemma_results], k=60)[:top_k]

    def search_with_stats(
        self,
        query: str,
        top_k: int = 3
    ) -> Tuple[List[SearchResult], dict]:
        """
        Поиск с статистикой (для отладки и мониторинга).

        Returns:
            (results, stats) где stats содержит:
            - stage_used: какой этап сработал
            - semantic_time_ms: время semantic match (этап 1)
            - exact_time_ms: время exact match (этап 2)
            - lemma_time_ms: время lemma match (этап 3)
            - total_time_ms: общее время
        """
        stats = {
            "stage_used": "none",
            "exact_time_ms": 0,
            "lemma_time_ms": 0,
            "semantic_time_ms": 0,
            "total_time_ms": 0,
        }

        if not query or not query.strip():
            return [], stats

        start_total = time.perf_counter()
        sections = self.kb.sections

        # Этап 1: Semantic match
        semantic_results: List[SearchResult] = []
        if self.use_embeddings and self._embeddings_ready:
            start = time.perf_counter()
            semantic_results = self._semantic_search(query, sections, top_k=top_k * 3)
            stats["semantic_time_ms"] = (time.perf_counter() - start) * 1000

        # Этап 2: Exact match
        start = time.perf_counter()
        exact_results = self._exact_search(query, sections)
        stats["exact_time_ms"] = (time.perf_counter() - start) * 1000

        # Этап 3: Lemma match
        start = time.perf_counter()
        lemma_results = self._lemma_search(query, sections)
        stats["lemma_time_ms"] = (time.perf_counter() - start) * 1000

        if not semantic_results and not exact_results and not lemma_results:
            stats["total_time_ms"] = (time.perf_counter() - start_total) * 1000
            return [], stats

        results = self._rrf_merge([semantic_results, exact_results, lemma_results], k=60)[:top_k]
        stats["stage_used"] = "hybrid"
        stats["total_time_ms"] = (time.perf_counter() - start_total) * 1000
        return results, stats

    def _rrf_merge(
        self,
        result_lists: List[List[SearchResult]],
        k: int = 60,
    ) -> List[SearchResult]:
        scores: Dict[str, float] = {}
        best_result: Dict[str, SearchResult] = {}

        for results in result_lists:
            for rank, result in enumerate(results):
                key = f"{result.section.category}/{result.section.topic}"
                rrf_score = 1.0 / (k + rank + 1)
                scores[key] = scores.get(key, 0.0) + rrf_score
                if key not in best_result or result.score > best_result[key].score:
                    best_result[key] = result

        merged: List[SearchResult] = []
        for key in sorted(scores, key=scores.get, reverse=True):
            result = best_result[key]
            merged.append(SearchResult(
                section=result.section,
                score=scores[key],
                stage=result.stage,
                matched_keywords=result.matched_keywords,
                matched_lemmas=result.matched_lemmas,
            ))

        return merged

    def _exact_search(
        self,
        query: str,
        sections: List[KnowledgeSection]
    ) -> List[SearchResult]:
        """
        Этап 2: Exact substring match (fallback после semantic).

        Логика:
        - Для каждой секции проверяем все keywords
        - Если keyword.lower() in query.lower() → score += 1.0
        - Если keyword — целое слово (regex \\b) → score += 0.5 бонус
        - Возвращаем секции с score >= exact_threshold
        """
        query_lower = query.lower()
        results = []

        for section in sections:
            score = 0.0
            matched_keywords = []

            for keyword in section.keywords:
                keyword_lower = keyword.lower()

                # Проверяем: keyword является подстрокой query
                if keyword_lower in query_lower:
                    # Бонус за длину: длинные фразы-ключевые слова важнее коротких
                    word_count = len(keyword.split())
                    score += 1.0 + (word_count - 1) * 0.5
                    matched_keywords.append(keyword)

                    # Бонус если keyword — целое слово/фраза (не часть другого слова)
                    pattern = rf'\b{re.escape(keyword_lower)}\b'
                    if re.search(pattern, query_lower):
                        score += 0.5

            if score >= self.exact_threshold:
                # Specificity factor: penalize umbrella topics with many keywords
                # 1 match out of 42 kw → factor 1.024 (almost no boost)
                # 1 match out of 5 kw → factor 1.20 (+20% boost)
                # 3/5 matches → factor 1.60; 5/5 → factor 2.00
                unique_matches = len(set(matched_keywords))
                unique_total = len(set(section.keywords))
                match_ratio = unique_matches / max(unique_total, 1)
                specificity = 1.0 + match_ratio  # [1.0 … 2.0]
                final_score = score * specificity + (section.priority * 0.01)

                results.append(SearchResult(
                    section=section,
                    score=final_score,
                    stage=MatchStage.EXACT,
                    matched_keywords=matched_keywords
                ))

        # Сортируем по score (убывание)
        results.sort(key=lambda r: r.score, reverse=True)
        return results

    def _lemma_search(
        self,
        query: str,
        sections: List[KnowledgeSection]
    ) -> List[SearchResult]:
        """
        Этап 3: Lemma-based search (fallback после exact).

        Логика:
        - Лемматизируем query → query_lemmas (Set[str])
        - Для каждой секции используем предвычисленные lemmatized_keywords
        - Считаем пересечение множеств
        - Scoring: query_coverage * 0.5 + jaccard * 0.3 + keyword_coverage * 0.2
        - Бонус за количество совпадений
        - Возвращаем секции с score >= lemma_threshold
        """
        # Лемматизируем запрос
        query_lemmas = self.lemmatizer.lemmatize_to_set(query, remove_stop_words=True)

        if not query_lemmas:
            return []

        results = []

        for section in sections:
            # Используем предвычисленные леммы секции
            entry_lemmas = section.lemmatized_keywords

            if not entry_lemmas:
                continue

            # Пересечение множеств
            matched = query_lemmas & entry_lemmas

            if not matched:
                continue

            # Scoring
            query_coverage = len(matched) / len(query_lemmas)
            keyword_coverage = len(matched) / len(entry_lemmas)

            union = query_lemmas | entry_lemmas
            jaccard = len(matched) / len(union) if union else 0

            score = (
                0.5 * query_coverage +
                0.3 * jaccard +
                0.2 * keyword_coverage
            )

            # Бонус за количество совпадений
            match_bonus = min(0.2, len(matched) * 0.05)
            score += match_bonus

            # Учитываем priority
            score += section.priority * 0.01

            if score >= self.lemma_threshold:
                results.append(SearchResult(
                    section=section,
                    score=min(1.0, score),
                    stage=MatchStage.LEMMA,
                    matched_lemmas=matched
                ))

        results.sort(key=lambda r: r.score, reverse=True)
        return results

    def _semantic_search(
        self,
        query: str,
        sections: List[KnowledgeSection],
        top_k: int
    ) -> List[SearchResult]:
        """
        Этап 1: Semantic search — Qwen3-Embedding-4B через TEI.

        Логика:
        - Получаем embedding запроса через TEI /embed
        - Считаем cosine similarity с каждой секцией
        - Возвращаем top_k с score >= semantic_threshold
        """
        if not self._embeddings_ready or not self.np:
            return []

        import requests as req
        try:
            # Prepend Qwen3-Embedding instruction for asymmetric retrieval
            instructed_query = self._QUERY_INSTRUCTION + query
            resp = req.post(
                f"{self._tei_url}/embed",
                json={"inputs": [instructed_query]},
                timeout=10.0,
            )
            resp.raise_for_status()
            query_emb = self.np.array(resp.json()[0])
        except Exception as e:
            logger.warning(f"TEI embed query failed: {e}")
            return []

        results = []
        for section in sections:
            if section.embedding:
                section_emb = self.np.array(section.embedding)
                score = float(self.np.dot(query_emb, section_emb) / (
                    self.np.linalg.norm(query_emb) * self.np.linalg.norm(section_emb)
                ))

                if score >= self.semantic_threshold:
                    results.append(SearchResult(
                        section=section,
                        score=score,
                        stage=MatchStage.SEMANTIC
                    ))

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]

    def get_company_info(self) -> str:
        """Получить базовую информацию о компании (совместимость)."""
        return f"{self.kb.company_name}: {self.kb.company_description}"


# Alias для обратной совместимости
KnowledgeRetriever = CascadeRetriever


def _validate_category_coverage(kb_categories: Set[str]) -> None:
    """Warn if any KB category is not referenced in INTENT_TO_CATEGORY."""
    mapped: Set[str] = set()
    for cats in INTENT_TO_CATEGORY.values():
        mapped.update(cats)
    orphans = kb_categories - mapped
    if orphans:
        warnings.warn(
            f"KB categories not in INTENT_TO_CATEGORY: {orphans}. "
            "Add them to an intent mapping or they'll only be reachable via CategoryRouter.",
            stacklevel=2,
        )


# =============================================================================
# Thread-safe Singleton для retriever
# =============================================================================
# Используем Double-Checked Locking pattern для эффективности:
# - Первая проверка без lock для быстрого возврата в случае если уже инициализировано
# - Lock только при необходимости инициализации
# - Вторая проверка внутри lock для защиты от race condition
# =============================================================================

_retriever: Optional[CascadeRetriever] = None
_retriever_config: Optional[dict] = None
_retriever_lock = threading.Lock()


def get_retriever(use_embeddings: bool = None) -> CascadeRetriever:
    """
    Получить инстанс retriever'а (thread-safe).

    При изменении параметров создаётся новый экземпляр.
    Для явного сброса используйте reset_retriever().

    Thread Safety:
        Использует Double-Checked Locking pattern для безопасной
        инициализации при многопоточном доступе.

    Args:
        use_embeddings: Использовать ли семантический поиск с эмбеддингами.
                       По умолчанию берётся из settings.retriever.use_embeddings

    Returns:
        CascadeRetriever: Singleton-экземпляр retriever'а.
    """
    global _retriever, _retriever_config

    # Читаем из settings если не указано явно
    if use_embeddings is None:
        use_embeddings = settings.retriever.use_embeddings

    current_config = {"use_embeddings": use_embeddings}

    # Fast path: если уже инициализировано с правильной конфигурацией
    if _retriever is not None and _retriever_config == current_config:
        return _retriever

    # Slow path: нужна инициализация или переконфигурация
    with _retriever_lock:
        # Повторная проверка внутри lock (другой поток мог инициализировать)
        if _retriever is None or _retriever_config != current_config:
            _retriever = CascadeRetriever(use_embeddings=use_embeddings)
            _retriever_config = current_config
            # Validate KB category coverage on first init
            kb_cats = {s.category for s in _retriever.kb.sections if s.category}
            _validate_category_coverage(kb_cats)

        return _retriever


def reset_retriever() -> None:
    """
    Сбросить singleton-экземпляр retriever'а (thread-safe).

    Следующий вызов get_retriever() создаст новый экземпляр.
    Полезно для тестирования или при изменении конфигурации.

    Thread Safety:
        Использует lock для безопасного сброса при многопоточном доступе.
    """
    global _retriever, _retriever_config

    with _retriever_lock:
        _retriever = None
        _retriever_config = None
