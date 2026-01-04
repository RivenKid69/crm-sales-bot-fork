"""
Модуль базы знаний Wipon.

Использование:
    from knowledge import WIPON_KNOWLEDGE

    # Получить все секции
    sections = WIPON_KNOWLEDGE.sections

    # Получить по категории
    pricing = WIPON_KNOWLEDGE.get_by_category("pricing")

    # Получить по теме
    kassa = WIPON_KNOWLEDGE.get_by_topic("wipon_kassa")
"""

from .base import KnowledgeBase, KnowledgeSection
from .loader import load_knowledge_base
from .retriever import (
    CascadeRetriever,
    KnowledgeRetriever,  # Alias для обратной совместимости
    MatchStage,
    SearchResult,
    get_retriever,
)
from .lemmatizer import Lemmatizer, get_lemmatizer

# Глобальный экземпляр (ленивая загрузка)
_knowledge_base = None


def _get_knowledge_base() -> KnowledgeBase:
    """Получить или загрузить базу знаний"""
    global _knowledge_base
    if _knowledge_base is None:
        _knowledge_base = load_knowledge_base()
    return _knowledge_base


class _LazyKnowledgeBase:
    """Ленивая обёртка для отложенной загрузки"""

    def __getattr__(self, name):
        return getattr(_get_knowledge_base(), name)

    @property
    def sections(self):
        return _get_knowledge_base().sections

    @property
    def company_name(self):
        return _get_knowledge_base().company_name

    @property
    def company_description(self):
        return _get_knowledge_base().company_description

    def get_by_category(self, category: str):
        return _get_knowledge_base().get_by_category(category)

    def get_by_topic(self, topic: str):
        return _get_knowledge_base().get_by_topic(topic)


WIPON_KNOWLEDGE = _LazyKnowledgeBase()

__all__ = [
    "KnowledgeBase",
    "KnowledgeSection",
    "WIPON_KNOWLEDGE",
    "load_knowledge_base",
    "CascadeRetriever",
    "KnowledgeRetriever",
    "MatchStage",
    "SearchResult",
    "get_retriever",
    "Lemmatizer",
    "get_lemmatizer",
]
