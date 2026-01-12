"""LLM-based classifier module."""
# ВАЖНО: LLMClassifier добавляется на этапе 5!
# Сначала только schemas
from .schemas import IntentType, ExtractedData, ClassificationResult, PainCategory

__all__ = ["IntentType", "ExtractedData", "ClassificationResult", "PainCategory"]
