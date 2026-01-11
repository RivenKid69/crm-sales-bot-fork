"""
Модуль каскадного детектора возражений.

Архитектура:
    Tier 1: Regex (существующий ObjectionHandler) - быстрый, точный
    Tier 2: Semantic (SemanticClassifier) - fallback для опечаток/перефразировок

Использование:
    from objection import get_cascade_objection_detector

    detector = get_cascade_objection_detector()
    result = detector.detect("это слишком дорого")

    if result.is_objection:
        print(f"Тип: {result.primary_type}, Tier: {result.tier_used}")
"""

from objection.cascade_detector import (
    CascadeObjectionDetector,
    ObjectionDetectionResult,
    get_cascade_objection_detector,
    INTENT_TO_OBJECTION,
)

__all__ = [
    "CascadeObjectionDetector",
    "ObjectionDetectionResult",
    "get_cascade_objection_detector",
    "INTENT_TO_OBJECTION",
]
