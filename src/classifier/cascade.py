"""
Каскадный классификатор интентов.

Реализует 3-этапный пайплайн классификации:
1. Priority Patterns — regex паттерны высокого приоритета
2. Root/Lemma Match — классификация по ключевым словам
3. Semantic Match — эмбеддинги как fallback

Каждый этап возвращает результат только при высокой уверенности,
иначе передаёт управление следующему этапу.
"""

import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple, Any

from .intents import (
    COMPILED_PRIORITY_PATTERNS,
    RootClassifier,
    LemmaClassifier,
    SemanticClassifier,
    get_semantic_classifier,
)


class ClassificationStage(Enum):
    """Этап классификации."""
    PRIORITY_PATTERN = "priority_pattern"
    ROOT = "root"
    LEMMA = "lemma"
    SEMANTIC = "semantic"
    FALLBACK = "fallback"


@dataclass
class CascadeResult:
    """Результат каскадной классификации."""
    intent: str
    confidence: float
    stage: ClassificationStage
    method: str  # Для обратной совместимости с HybridClassifier

    # Детали классификации
    pattern_matched: Optional[str] = None
    root_scores: Dict[str, float] = field(default_factory=dict)
    lemma_scores: Dict[str, float] = field(default_factory=dict)
    semantic_scores: Dict[str, float] = field(default_factory=dict)

    # Метрики производительности
    stage_times_ms: Dict[str, float] = field(default_factory=dict)
    total_time_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Конвертация в словарь для совместимости."""
        return {
            "intent": self.intent,
            "confidence": self.confidence,
            "stage": self.stage.value,
            "method": self.method,
            "pattern_matched": self.pattern_matched,
            "debug_scores": {
                "root": self.root_scores,
                "lemma": self.lemma_scores,
                "semantic": self.semantic_scores,
            },
            "timing": {
                "stages": self.stage_times_ms,
                "total_ms": self.total_time_ms,
            },
        }


class CascadeIntentClassifier:
    """
    Каскадный классификатор интентов.

    Пайплайн:
    1. Priority Patterns (regex) — confidence >= 0.85
    2. Root Classifier (stems) — confidence >= high_threshold
    3. Lemma Classifier (pymorphy) — confidence >= medium_threshold
    4. Semantic Classifier (embeddings) — confidence >= semantic_threshold
    5. Fallback — возвращает лучший результат или "unclear"

    Attributes:
        high_threshold: Порог для немедленного возврата (Stage 1-2)
        medium_threshold: Порог для Root/Lemma (Stage 2-3)
        semantic_threshold: Минимальный порог для semantic (Stage 4)
        enable_semantic: Включить семантический этап
    """

    def __init__(
        self,
        high_threshold: float = 0.85,
        medium_threshold: float = 0.65,
        semantic_threshold: float = 0.55,
        min_confidence: float = 0.3,
        enable_semantic: bool = True
    ):
        """
        Инициализация каскадного классификатора.

        Args:
            high_threshold: Порог высокой уверенности (early return)
            medium_threshold: Порог средней уверенности
            semantic_threshold: Порог для семантического классификатора
            min_confidence: Минимальная уверенность для возврата интента
            enable_semantic: Использовать семантический fallback
        """
        self.high_threshold = high_threshold
        self.medium_threshold = medium_threshold
        self.semantic_threshold = semantic_threshold
        self.min_confidence = min_confidence
        self.enable_semantic = enable_semantic

        # Инициализируем классификаторы
        self.root_classifier = RootClassifier()
        self.lemma_classifier = LemmaClassifier()
        self._semantic_classifier: Optional[SemanticClassifier] = None

    @property
    def semantic_classifier(self) -> Optional[SemanticClassifier]:
        """Lazy initialization семантического классификатора."""
        if not self.enable_semantic:
            return None

        if self._semantic_classifier is None:
            self._semantic_classifier = get_semantic_classifier()

        return self._semantic_classifier

    def classify(self, message: str) -> CascadeResult:
        """
        Классифицировать сообщение через каскад.

        Args:
            message: Текст сообщения

        Returns:
            CascadeResult с результатом классификации
        """
        start_total = time.perf_counter()
        stage_times: Dict[str, float] = {}

        message_lower = message.lower().strip()

        # =====================================================================
        # STAGE 1: Priority Patterns
        # =====================================================================
        start = time.perf_counter()
        pattern_result = self._stage_priority_patterns(message_lower)
        stage_times["priority_pattern"] = (time.perf_counter() - start) * 1000

        if pattern_result:
            return CascadeResult(
                intent=pattern_result[0],
                confidence=pattern_result[1],
                stage=ClassificationStage.PRIORITY_PATTERN,
                method="priority_pattern",
                pattern_matched=pattern_result[2],
                stage_times_ms=stage_times,
                total_time_ms=(time.perf_counter() - start_total) * 1000,
            )

        # =====================================================================
        # STAGE 2: Root Classifier
        # =====================================================================
        start = time.perf_counter()
        root_intent, root_conf, root_scores = self.root_classifier.classify(message)
        stage_times["root"] = (time.perf_counter() - start) * 1000

        if root_conf >= self.high_threshold:
            return CascadeResult(
                intent=root_intent,
                confidence=root_conf,
                stage=ClassificationStage.ROOT,
                method="root",
                root_scores=root_scores,
                stage_times_ms=stage_times,
                total_time_ms=(time.perf_counter() - start_total) * 1000,
            )

        # =====================================================================
        # STAGE 3: Lemma Classifier
        # =====================================================================
        start = time.perf_counter()
        lemma_intent, lemma_conf, lemma_scores = self.lemma_classifier.classify(message)
        stage_times["lemma"] = (time.perf_counter() - start) * 1000

        # Выбираем лучший между root и lemma
        if lemma_conf > root_conf:
            best_keyword_intent = lemma_intent
            best_keyword_conf = lemma_conf
            best_keyword_stage = ClassificationStage.LEMMA
            best_keyword_method = "lemma"
        else:
            best_keyword_intent = root_intent
            best_keyword_conf = root_conf
            best_keyword_stage = ClassificationStage.ROOT
            best_keyword_method = "root"

        # Если medium threshold достигнут — возвращаем
        if best_keyword_conf >= self.medium_threshold:
            return CascadeResult(
                intent=best_keyword_intent,
                confidence=best_keyword_conf,
                stage=best_keyword_stage,
                method=best_keyword_method,
                root_scores=root_scores,
                lemma_scores=lemma_scores,
                stage_times_ms=stage_times,
                total_time_ms=(time.perf_counter() - start_total) * 1000,
            )

        # =====================================================================
        # STAGE 4: Semantic Classifier (fallback)
        # =====================================================================
        semantic_intent = None
        semantic_conf = 0.0
        semantic_scores: Dict[str, float] = {}

        if self.enable_semantic and self.semantic_classifier:
            start = time.perf_counter()

            if self.semantic_classifier.is_available:
                semantic_intent, semantic_conf, semantic_scores = \
                    self.semantic_classifier.classify(message)

            stage_times["semantic"] = (time.perf_counter() - start) * 1000

            # Если семантика дала хороший результат
            if semantic_conf >= self.semantic_threshold:
                # Сравниваем с keyword результатом
                if semantic_conf > best_keyword_conf:
                    return CascadeResult(
                        intent=semantic_intent,
                        confidence=semantic_conf,
                        stage=ClassificationStage.SEMANTIC,
                        method="semantic",
                        root_scores=root_scores,
                        lemma_scores=lemma_scores,
                        semantic_scores=semantic_scores,
                        stage_times_ms=stage_times,
                        total_time_ms=(time.perf_counter() - start_total) * 1000,
                    )

        # =====================================================================
        # STAGE 5: Fallback — лучший из доступных или unclear
        # =====================================================================
        # Собираем все результаты
        candidates = [
            (best_keyword_intent, best_keyword_conf, best_keyword_stage, best_keyword_method),
        ]

        if semantic_intent and semantic_conf > 0:
            candidates.append((
                semantic_intent,
                semantic_conf,
                ClassificationStage.SEMANTIC,
                "semantic"
            ))

        # Выбираем лучший
        best = max(candidates, key=lambda x: x[1])
        best_intent, best_conf, best_stage, best_method = best

        # Если ниже min_confidence — unclear
        if best_conf < self.min_confidence:
            return CascadeResult(
                intent="unclear",
                confidence=best_conf,
                stage=ClassificationStage.FALLBACK,
                method="fallback",
                root_scores=root_scores,
                lemma_scores=lemma_scores,
                semantic_scores=semantic_scores,
                stage_times_ms=stage_times,
                total_time_ms=(time.perf_counter() - start_total) * 1000,
            )

        return CascadeResult(
            intent=best_intent,
            confidence=best_conf,
            stage=best_stage,
            method=best_method,
            root_scores=root_scores,
            lemma_scores=lemma_scores,
            semantic_scores=semantic_scores,
            stage_times_ms=stage_times,
            total_time_ms=(time.perf_counter() - start_total) * 1000,
        )

    def _stage_priority_patterns(
        self,
        message_lower: str
    ) -> Optional[Tuple[str, float, str]]:
        """
        Stage 1: Проверка приоритетных паттернов.

        Returns:
            (intent, confidence, pattern) или None
        """
        for pattern, intent, confidence in COMPILED_PRIORITY_PATTERNS:
            if pattern.search(message_lower):
                return (intent, confidence, pattern.pattern)

        return None

    def classify_with_stats(
        self,
        message: str
    ) -> Tuple[CascadeResult, Dict[str, Any]]:
        """
        Классификация с детальной статистикой.

        Returns:
            (result, stats)
        """
        result = self.classify(message)

        stats = {
            "message_length": len(message),
            "stage_used": result.stage.value,
            "stages_checked": list(result.stage_times_ms.keys()),
            "timing": result.stage_times_ms,
            "total_time_ms": result.total_time_ms,
            "confidence": result.confidence,
        }

        return result, stats

    def explain(self, message: str) -> Dict[str, Any]:
        """
        Объяснить классификацию (для отладки).

        Args:
            message: Текст сообщения

        Returns:
            Детальное объяснение
        """
        result = self.classify(message)

        # Top 3 по каждому методу
        def top_3(scores: Dict[str, float]) -> List[Dict]:
            sorted_items = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:3]
            return [{"intent": k, "score": round(v, 4)} for k, v in sorted_items]

        explanation = {
            "message": message,
            "final_intent": result.intent,
            "final_confidence": round(result.confidence, 4),
            "stage_used": result.stage.value,
            "method": result.method,
            "stages": {
                "root": {
                    "top_intents": top_3(result.root_scores),
                },
                "lemma": {
                    "top_intents": top_3(result.lemma_scores),
                },
                "semantic": {
                    "top_intents": top_3(result.semantic_scores),
                } if result.semantic_scores else {"available": False},
            },
            "timing_ms": result.stage_times_ms,
            "total_time_ms": round(result.total_time_ms, 2),
        }

        if result.pattern_matched:
            explanation["pattern_matched"] = result.pattern_matched

        return explanation


# =============================================================================
# Factory function
# =============================================================================

_cascade_classifier: Optional[CascadeIntentClassifier] = None


def get_cascade_classifier(
    enable_semantic: bool = True,
    **kwargs
) -> CascadeIntentClassifier:
    """
    Получить singleton экземпляр CascadeIntentClassifier.

    Args:
        enable_semantic: Включить семантический fallback
        **kwargs: Дополнительные параметры конструктора

    Returns:
        CascadeIntentClassifier
    """
    global _cascade_classifier

    if _cascade_classifier is None:
        _cascade_classifier = CascadeIntentClassifier(
            enable_semantic=enable_semantic,
            **kwargs
        )

    return _cascade_classifier


def reset_cascade_classifier() -> None:
    """Сбросить singleton (для тестирования)."""
    global _cascade_classifier
    _cascade_classifier = None
