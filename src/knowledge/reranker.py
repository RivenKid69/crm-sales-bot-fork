"""
Cross-encoder Reranker для переоценки кандидатов при низком score.

Использует BAAI/bge-reranker-v2-m3 для точной оценки релевантности
пары (query, document).
"""

import threading
from typing import List, Optional
from dataclasses import dataclass

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from settings import settings


@dataclass
class RerankedResult:
    """Результат reranking с новым score."""
    section: any  # KnowledgeSection
    original_score: float
    rerank_score: float


class Reranker:
    """
    Cross-encoder reranker для переоценки кандидатов.

    Cross-encoder видит query и document вместе, поэтому точнее
    оценивает релевантность чем bi-encoder (semantic search).
    """

    def __init__(self, model_name: str = None):
        """
        Инициализация reranker.

        Args:
            model_name: Название модели (по умолчанию из settings)
        """
        if model_name is None:
            model_name = getattr(
                getattr(settings, 'reranker', None),
                'model',
                'BAAI/bge-reranker-v2-m3'
            )

        self.model_name = model_name
        self.model = None
        self._initialized = False

    def _ensure_initialized(self):
        """Ленивая инициализация модели."""
        if self._initialized:
            return

        try:
            from sentence_transformers import CrossEncoder
            print(f"[Reranker] Loading model: {self.model_name}")
            self.model = CrossEncoder(self.model_name)
            self._initialized = True
            print("[Reranker] Model loaded successfully")
        except ImportError:
            print("[Reranker] sentence-transformers not installed")
            self._initialized = True  # Не пытаемся снова
        except Exception as e:
            print(f"[Reranker] Failed to load model: {e}")
            self._initialized = True

    def rerank(
        self,
        query: str,
        candidates: List,
        top_k: int = 2
    ) -> List:
        """
        Переоценить кандидатов с помощью cross-encoder.

        Args:
            query: Запрос пользователя
            candidates: Список SearchResult из CascadeRetriever
            top_k: Сколько лучших вернуть

        Returns:
            Список SearchResult, отсортированный по rerank score
        """
        if not candidates:
            return []

        self._ensure_initialized()

        if self.model is None:
            # Если модель не загружена, возвращаем как есть
            return candidates[:top_k]

        # Формируем пары (query, document)
        pairs = [(query, c.section.facts) for c in candidates]

        # Получаем scores от cross-encoder
        scores = self.model.predict(pairs)

        # Сортируем по новым scores
        scored_candidates = list(zip(candidates, scores))
        scored_candidates.sort(key=lambda x: x[1], reverse=True)

        # Возвращаем top_k
        return [c for c, _ in scored_candidates[:top_k]]

    def is_available(self) -> bool:
        """Проверить доступность reranker."""
        self._ensure_initialized()
        return self.model is not None


# =============================================================================
# Thread-safe Singleton
# =============================================================================

_reranker: Optional[Reranker] = None
_reranker_lock = threading.Lock()


def get_reranker() -> Reranker:
    """
    Получить singleton-экземпляр reranker (thread-safe).

    Returns:
        Reranker: Singleton-экземпляр.
    """
    global _reranker

    if _reranker is not None:
        return _reranker

    with _reranker_lock:
        if _reranker is None:
            _reranker = Reranker()
        return _reranker


def reset_reranker() -> None:
    """Сбросить singleton для тестирования."""
    global _reranker

    with _reranker_lock:
        _reranker = None
