"""
Reranker через TEI (text-embeddings-inference) — Qwen3-Reranker-4B.

TEI API: POST /rerank { query, texts, raw_scores }
"""

import threading
from typing import List, Optional

import requests

from src.settings import settings


class Reranker:
    """
    Reranker через TEI HTTP API.

    TEI /rerank endpoint принимает query + texts и возвращает scores.
    """

    def __init__(self, url: str = None, timeout: float = None):
        if url is None:
            url = getattr(
                getattr(settings, 'reranker', None),
                'url',
                'http://tei-rerank:80'
            )
        self.url = url.rstrip('/')
        self.timeout = timeout
        self._available = None

    def rerank(
        self,
        query: str,
        candidates: List,
        top_k: int = 2
    ) -> List:
        """
        Переоценить кандидатов через TEI /rerank.

        Args:
            query: Запрос пользователя
            candidates: Список SearchResult из CascadeRetriever
            top_k: Сколько лучших вернуть

        Returns:
            Список SearchResult, отсортированный по rerank score
        """
        if not candidates:
            return []

        texts = [c.section.facts for c in candidates]

        try:
            resp = requests.post(
                f"{self.url}/rerank",
                json={"query": query, "texts": texts, "raw_scores": False},
                timeout=self.timeout,
            )
            resp.raise_for_status()
            results = resp.json()
            # TEI returns: [{"index": 0, "score": 0.95}, ...]
            scored = [(candidates[r["index"]], r["score"]) for r in results]
            scored.sort(key=lambda x: x[1], reverse=True)
            return [c for c, _ in scored[:top_k]]
        except Exception as e:
            print(f"[Reranker] TEI request failed: {e}")
            return candidates[:top_k]

    def is_available(self) -> bool:
        """Проверить доступность TEI reranker."""
        if self._available is not None:
            return self._available
        try:
            resp = requests.get(f"{self.url}/health", timeout=3.0)
            self._available = resp.status_code == 200
        except Exception:
            self._available = False
        return self._available


# =============================================================================
# Thread-safe Singleton
# =============================================================================

_reranker: Optional[Reranker] = None
_reranker_lock = threading.Lock()


def get_reranker() -> Reranker:
    """Получить singleton-экземпляр reranker (thread-safe)."""
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
