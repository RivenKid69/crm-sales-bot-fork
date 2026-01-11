"""
Каскадный Retriever с 3-этапным поиском.

Этапы:
1. Exact Match — поиск keyword как подстроки в запросе
2. Lemma Match — сравнение лемматизированных множеств
3. Semantic Match — cosine similarity эмбеддингов (fallback)
"""

import re
import sys
import time
import threading
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Set
from enum import Enum
from pathlib import Path

# Добавляем родительскую директорию для импорта settings
sys.path.insert(0, str(Path(__file__).parent.parent))
from settings import settings
from logger import logger

from .base import KnowledgeSection, KnowledgeBase
from .loader import load_knowledge_base
from .lemmatizer import get_lemmatizer
from .reranker import get_reranker


# Маппинг интентов на категории базы знаний
# Принцип: каждый интент связан с категориями, которые могут содержать релевантные факты
# Пустой список [] означает, что для этого интента не нужен поиск по базе знаний
#
# ВАЖНО: Используйте только существующие категории из knowledge/data/:
# equipment, products, tis, support, pricing, inventory, features, regions,
# integrations, analytics, employees, fiscal, stability, mobile, promotions,
# competitors, faq
INTENT_TO_CATEGORY = {
    # =================================================================
    # ВОПРОСЫ О ПРОДУКТЕ/ЦЕНЕ (требуют информации из базы)
    # =================================================================
    "price_question": ["pricing"],
    "pricing_details": ["pricing", "promotions"],
    "question_features": ["features", "products", "tis", "analytics", "inventory"],
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
    "callback_request": ["support", "regions"],  # контакты в support и regions
    "demo_request": ["support", "products"],
    "consultation_request": ["support", "features", "products"],
    "contact_provided": ["support", "regions"],

    # =================================================================
    # СОГЛАСИЕ/ИНТЕРЕС (общая информация)
    # =================================================================
    "agreement": ["pricing", "support", "products"],

    # =================================================================
    # SPIN ИНТЕНТЫ
    # =================================================================
    # situation_provided: клиент рассказывает о себе - факты не нужны
    "situation_provided": [],
    # problem_revealed: клиент озвучивает проблемы - факты не нужны
    "problem_revealed": [],
    # implication_acknowledged: клиент признает последствия - факты не нужны
    "implication_acknowledged": [],
    # need_expressed: клиент хочет решение - можно показать преимущества
    "need_expressed": ["features", "products"],
    # no_problem/no_need: отрицание проблемы/потребности - показать ценность продукта
    "no_problem": ["products", "features"],
    "no_need": ["products", "features"],
    # info_provided: общая информация от клиента
    "info_provided": [],

    # =================================================================
    # НЕЙТРАЛЬНЫЕ ИНТЕНТЫ (факты не нужны)
    # =================================================================
    "greeting": [],
    "rejection": [],
    "farewell": [],
    "gratitude": [],
    "small_talk": [],
    "unclear": [],

    # =================================================================
    # НАВИГАЦИОННЫЕ ИНТЕНТЫ (возврат/исправление)
    # =================================================================
    "go_back": [],      # Вернуться к предыдущей фазе
    "correct_info": [], # Исправить ранее предоставленную информацию

    # =================================================================
    # СИСТЕМНЫЕ ИНТЕНТЫ (не требуют базы знаний)
    # =================================================================
    "disambiguation_needed": [],  # Требуется уточнение у пользователя
    "fallback_close": [],         # Мягкое завершение после fallback
}


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
    1. Exact match — поиск keyword как подстроки в запросе
    2. Lemma match — сравнение лемматизированных множеств
    3. Semantic match — cosine similarity эмбеддингов
    """

    def __init__(
        self,
        knowledge_base: KnowledgeBase = None,
        use_embeddings: bool = None,
        exact_threshold: float = None,
        lemma_threshold: float = None,
        semantic_threshold: float = None
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

        # Эмбеддинги (инициализируются лениво)
        self.embedder = None
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
        """Инициализировать sentence-transformers и индексировать секции."""
        try:
            from sentence_transformers import SentenceTransformer
            import numpy as np
            self.np = np
            # Модель из settings (по умолчанию: ai-forever/ru-en-RoSBERTa)
            embedder_model = settings.retriever.embedder_model
            self.embedder = SentenceTransformer(embedder_model)

            # Индексируем все секции
            texts = [s.facts for s in self.kb.sections]
            embeddings = self.embedder.encode(texts)
            for i, section in enumerate(self.kb.sections):
                section.embedding = embeddings[i].tolist()

            print(f"[CascadeRetriever] Indexed {len(texts)} sections with embeddings")
        except ImportError:
            print("[CascadeRetriever] sentence-transformers not installed, using keywords only")
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
                        fallback="using default categories: faq, features"
                    )
                    categories = ["faq", "features"]  # Fallback категории

        # Если reranker включён — берём больше кандидатов
        search_top_k = self.rerank_candidates if self.reranker_enabled else top_k

        # Ищем
        results = self.search(message, categories=categories, top_k=search_top_k)

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

        # Формируем строку
        facts = [r.section.facts.strip() for r in results]
        return "\n\n---\n\n".join(facts)

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
            # Если категория не найдена, ищем по всем
            sections = self.kb.sections

        # Этап 1: Exact match
        results = self._exact_search(query, sections)
        if results:
            return results[:top_k]

        # Этап 2: Lemma match
        results = self._lemma_search(query, sections)
        if results:
            return results[:top_k]

        # Этап 3: Semantic match (если включено)
        if self.use_embeddings and self.embedder:
            results = self._semantic_search(query, sections, top_k)
            return results

        return []

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
            - exact_time_ms: время exact match
            - lemma_time_ms: время lemma match
            - semantic_time_ms: время semantic match (если использовался)
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

        # Этап 1: Exact match
        start = time.perf_counter()
        results = self._exact_search(query, sections)
        stats["exact_time_ms"] = (time.perf_counter() - start) * 1000

        if results:
            stats["stage_used"] = "exact"
            stats["total_time_ms"] = (time.perf_counter() - start_total) * 1000
            return results[:top_k], stats

        # Этап 2: Lemma match
        start = time.perf_counter()
        results = self._lemma_search(query, sections)
        stats["lemma_time_ms"] = (time.perf_counter() - start) * 1000

        if results:
            stats["stage_used"] = "lemma"
            stats["total_time_ms"] = (time.perf_counter() - start_total) * 1000
            return results[:top_k], stats

        # Этап 3: Semantic match
        if self.use_embeddings and self.embedder:
            start = time.perf_counter()
            results = self._semantic_search(query, sections, top_k)
            stats["semantic_time_ms"] = (time.perf_counter() - start) * 1000

            if results:
                stats["stage_used"] = "semantic"

        stats["total_time_ms"] = (time.perf_counter() - start_total) * 1000
        return results, stats

    def _exact_search(
        self,
        query: str,
        sections: List[KnowledgeSection]
    ) -> List[SearchResult]:
        """
        Этап 1: Exact substring match.

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
                # Учитываем priority секции
                final_score = score + (section.priority * 0.01)

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
        Этап 2: Lemma-based search.

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
        Этап 3: Semantic search (embeddings).

        Логика:
        - Если embedder не инициализирован → return []
        - Получаем embedding запроса
        - Считаем cosine similarity с каждой секцией
        - Возвращаем top_k с score >= semantic_threshold
        """
        if not self.embedder or not self.np:
            return []

        query_emb = self.embedder.encode(query)
        results = []

        for section in sections:
            if section.embedding:
                # Косинусное сходство
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


def get_retriever(use_embeddings: bool = True) -> CascadeRetriever:
    """
    Получить инстанс retriever'а (thread-safe).

    При изменении параметров создаётся новый экземпляр.
    Для явного сброса используйте reset_retriever().

    Thread Safety:
        Использует Double-Checked Locking pattern для безопасной
        инициализации при многопоточном доступе.

    Args:
        use_embeddings: Использовать ли семантический поиск с эмбеддингами.

    Returns:
        CascadeRetriever: Singleton-экземпляр retriever'а.
    """
    global _retriever, _retriever_config

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
