"""
Подпакет классификации интентов

Экспортирует:
- RootClassifier: быстрая классификация по корням слов
- LemmaClassifier: fallback классификация через pymorphy
- SemanticClassifier: семантическая классификация через эмбеддинги
- PRIORITY_PATTERNS, COMPILED_PRIORITY_PATTERNS: приоритетные паттерны
- INTENT_EXAMPLES: примеры для семантической классификации
"""

from src.classifier.intents.patterns import PRIORITY_PATTERNS, COMPILED_PRIORITY_PATTERNS
from src.classifier.intents.root_classifier import RootClassifier
from src.classifier.intents.lemma_classifier import LemmaClassifier
from src.classifier.intents.semantic import SemanticClassifier, get_semantic_classifier, SemanticResult
from src.classifier.intents.examples import INTENT_EXAMPLES, get_all_intents, get_examples_for_intent

__all__ = [
    'RootClassifier',
    'LemmaClassifier',
    'SemanticClassifier',
    'get_semantic_classifier',
    'SemanticResult',
    'PRIORITY_PATTERNS',
    'COMPILED_PRIORITY_PATTERNS',
    'INTENT_EXAMPLES',
    'get_all_intents',
    'get_examples_for_intent',
]
