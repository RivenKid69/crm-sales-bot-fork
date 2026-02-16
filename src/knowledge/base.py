"""
Структура базы знаний.
Каждый раздел (Section) содержит:
- category: категория (pricing, features, integrations, etc.)
- topic: конкретная тема внутри категории
- keywords: список ключевых слов для поиска
- facts: текст с фактами (будет передан в LLM)
- priority: приоритет при множественных совпадениях (1-10)
- urls: структурированные ссылки на документацию
"""

from dataclasses import dataclass, field
from typing import List, Optional, Set, Dict, Any


@dataclass
class KnowledgeSection:
    """Один раздел знаний"""
    category: str           # "pricing", "features", "integrations", "competitors", "support"
    topic: str              # "tariffs", "wipon_kassa", "1c", "kaspi", etc.
    keywords: List[str]     # ["тариф", "цена", "стоимость", "сколько"]
    facts: str              # Текст с фактами
    priority: int = 5       # 1-10, выше = важнее при конфликтах

    # NEW: Structured URLs for documentation links
    # Format: [{"url": "https://...", "label": "Description", "type": "doc|spec|guide"}]
    urls: List[Dict[str, str]] = field(default_factory=list)

    # If True, section facts are never passed to the LLM prompt
    sensitive: bool = False

    # Для эмбеддингов (заполняется автоматически)
    embedding: Optional[List[float]] = field(default=None, repr=False)
    # Лемматизированные keywords (заполняется CascadeRetriever при инициализации)
    lemmatized_keywords: Set[str] = field(default_factory=set)


@dataclass
class KnowledgeBase:
    """База знаний целиком"""
    company_name: str
    company_description: str
    sections: List[KnowledgeSection]

    def get_by_category(self, category: str) -> List[KnowledgeSection]:
        """Получить все разделы категории"""
        return [s for s in self.sections if s.category == category]

    def get_by_topic(self, topic: str) -> Optional[KnowledgeSection]:
        """Получить раздел по теме"""
        for s in self.sections:
            if s.topic == topic:
                return s
        return None
