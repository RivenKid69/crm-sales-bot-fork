"""
Модуль базы знаний Wipon.
"""

from .base import KnowledgeBase, KnowledgeSection
from .retriever import (
    CascadeRetriever,
    KnowledgeRetriever,  # Alias для обратной совместимости
    MatchStage,
    SearchResult,
    get_retriever,
)
from .lemmatizer import Lemmatizer, get_lemmatizer

__all__ = [
    "KnowledgeBase",
    "KnowledgeSection",
    "CascadeRetriever",
    "KnowledgeRetriever",
    "MatchStage",
    "SearchResult",
    "get_retriever",
    "Lemmatizer",
    "get_lemmatizer",
]
