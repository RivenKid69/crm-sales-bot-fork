"""
Пакет гибридного классификатора интентов

Экспортирует:
- HybridClassifier: главный класс классификации
- UnifiedClassifier: адаптер с feature flag (LLM/Hybrid)
- TextNormalizer: нормализатор текста
- DataExtractor: извлечение структурированных данных
- TYPO_FIXES, SPLIT_PATTERNS, PRIORITY_PATTERNS: словари и паттерны
- LLMClassifier, IntentType, ClassificationResult: LLM классификатор
"""

from .normalizer import TextNormalizer, TYPO_FIXES, SPLIT_PATTERNS
from .hybrid import HybridClassifier
from .unified import UnifiedClassifier
from .extractors import DataExtractor
from .intents import PRIORITY_PATTERNS, COMPILED_PRIORITY_PATTERNS

# LLM классификатор
from .llm import LLMClassifier, IntentType, ClassificationResult

# Refinement layer (State Loop Fix)
from .refinement import ClassificationRefinementLayer, RefinementContext

__all__ = [
    # Классификаторы
    'HybridClassifier',
    'UnifiedClassifier',
    'LLMClassifier',
    # Нормализация и извлечение
    'TextNormalizer',
    'DataExtractor',
    # Словари и паттерны
    'TYPO_FIXES',
    'SPLIT_PATTERNS',
    'PRIORITY_PATTERNS',
    'COMPILED_PRIORITY_PATTERNS',
    # LLM типы
    'IntentType',
    'ClassificationResult',
    # Refinement (State Loop Fix)
    'ClassificationRefinementLayer',
    'RefinementContext',
]
