"""
Подпакет классификации интентов

Экспортирует:
- RootClassifier: быстрая классификация по корням слов
- LemmaClassifier: fallback классификация через pymorphy
- PRIORITY_PATTERNS, COMPILED_PRIORITY_PATTERNS: приоритетные паттерны
"""

from .patterns import PRIORITY_PATTERNS, COMPILED_PRIORITY_PATTERNS
from .root_classifier import RootClassifier
from .lemma_classifier import LemmaClassifier

__all__ = [
    'RootClassifier',
    'LemmaClassifier',
    'PRIORITY_PATTERNS',
    'COMPILED_PRIORITY_PATTERNS',
]
