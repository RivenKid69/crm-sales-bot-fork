"""
Каскадный детектор возражений.

Архитектура:
    Tier 1: Regex (быстрый, точный) - существующий ObjectionHandler
    Tier 2: Semantic (fallback) - для опечаток и перефразировок

Tier 2 включается только если:
1. Tier 1 не нашёл совпадения
2. Feature flag semantic_objection_detection включён

Это обеспечивает:
- Обратную совместимость (regex работает как раньше)
- Дополнительное покрытие для нестандартных формулировок
- Минимальный overhead (semantic вызывается только при необходимости)
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import time

from src.objection_handler import ObjectionHandler, ObjectionType
from src.classifier.intents.semantic import get_semantic_classifier
from src.feature_flags import flags
from src.logger import logger


@dataclass
class ObjectionDetectionResult:
    """Результат детекции возражения."""

    primary_type: Optional[ObjectionType]
    confidence: float
    tier_used: str  # "regex" | "semantic"
    latency_ms: float
    all_scores: List[Tuple[str, float]] = field(default_factory=list)

    @property
    def is_objection(self) -> bool:
        """Обнаружено ли возражение."""
        return self.primary_type is not None


# Маппинг intent → ObjectionType
INTENT_TO_OBJECTION: Dict[str, ObjectionType] = {
    "objection_price": ObjectionType.PRICE,
    "objection_competitor": ObjectionType.COMPETITOR,
    "objection_no_time": ObjectionType.NO_TIME,
    "objection_think": ObjectionType.THINK,
    "objection_no_need": ObjectionType.NO_NEED,
    "objection_trust": ObjectionType.TRUST,
    "objection_timing": ObjectionType.TIMING,
    "objection_complexity": ObjectionType.COMPLEXITY,
}


class CascadeObjectionDetector:
    """
    Каскадный детектор возражений.

    Использует существующие компоненты:
    - ObjectionHandler (regex) как Tier 1
    - SemanticClassifier (zero-shot embeddings) как Tier 2

    Tier 2 активируется только если Tier 1 не нашёл совпадений
    и feature flag semantic_objection_detection включён.
    """

    # Пороги для Tier 2
    SEMANTIC_THRESHOLD = 0.75  # Минимальная уверенность (повышен для снижения false positives)
    SEMANTIC_AMBIGUITY_DELTA = 0.10  # Разница между top-1 и top-2

    def __init__(self):
        """Инициализация детектора."""
        self._regex_handler = ObjectionHandler()
        self._semantic = None  # lazy init

    @property
    def semantic_classifier(self):
        """Lazy init семантического классификатора."""
        if self._semantic is None:
            self._semantic = get_semantic_classifier()
        return self._semantic

    def detect(self, message: str) -> ObjectionDetectionResult:
        """
        Детектировать возражение через каскад.

        Порядок:
        1. Tier 1: Regex (ObjectionHandler)
        2. Tier 2: Semantic (если regex не сработал и флаг включён)

        Args:
            message: Сообщение клиента

        Returns:
            ObjectionDetectionResult с типом возражения и метаданными
        """
        start = time.perf_counter()

        # ========== TIER 1: Regex ==========
        regex_result = self._regex_handler.detect_objection(message)

        if regex_result is not None:
            latency = (time.perf_counter() - start) * 1000
            logger.debug(
                "Objection detected by regex",
                type=regex_result.value,
                latency_ms=round(latency, 2),
            )
            return ObjectionDetectionResult(
                primary_type=regex_result,
                confidence=0.95,  # regex = высокая уверенность
                tier_used="regex",
                latency_ms=latency,
            )

        # ========== TIER 2: Semantic ==========
        if not flags.semantic_objection_detection:
            # Semantic выключен — возвращаем "не найдено"
            return ObjectionDetectionResult(
                primary_type=None,
                confidence=0.0,
                tier_used="regex",
                latency_ms=(time.perf_counter() - start) * 1000,
            )

        semantic_result = self._detect_semantic(message)

        if semantic_result:
            latency = (time.perf_counter() - start) * 1000
            logger.debug(
                "Objection detected by semantic",
                type=semantic_result[0].value,
                confidence=round(semantic_result[1], 3),
                latency_ms=round(latency, 2),
            )
            return ObjectionDetectionResult(
                primary_type=semantic_result[0],
                confidence=semantic_result[1],
                tier_used="semantic",
                latency_ms=latency,
                all_scores=semantic_result[2],
            )

        # ========== No objection detected ==========
        return ObjectionDetectionResult(
            primary_type=None,
            confidence=0.0,
            tier_used="semantic",
            latency_ms=(time.perf_counter() - start) * 1000,
        )

    def _detect_semantic(
        self, message: str
    ) -> Optional[Tuple[ObjectionType, float, List[Tuple[str, float]]]]:
        """
        Tier 2: Semantic detection.

        Returns:
            Tuple[ObjectionType, confidence, all_objection_scores] или None
        """
        try:
            # Проверяем доступность классификатора
            if not self.semantic_classifier.is_available:
                logger.warning("Semantic classifier not available")
                return None

            # Классифицируем сообщение
            intent, confidence, all_scores = self.semantic_classifier.classify(
                message, top_k=3
            )

            # Фильтруем только objection интенты
            objection_scores = [
                (intent_name, score)
                for intent_name, score in all_scores.items()
                if intent_name.startswith("objection_")
            ]

            if not objection_scores:
                return None

            # Сортируем по score
            objection_scores.sort(key=lambda x: x[1], reverse=True)
            top_intent, top_score = objection_scores[0]

            # Проверяем порог уверенности
            if top_score < self.SEMANTIC_THRESHOLD:
                logger.debug(
                    "Semantic objection below threshold",
                    top_intent=top_intent,
                    top_score=round(top_score, 3),
                    threshold=self.SEMANTIC_THRESHOLD,
                )
                return None

            # Проверяем неоднозначность (top-1 vs top-2)
            if len(objection_scores) > 1:
                second_score = objection_scores[1][1]
                delta = top_score - second_score

                if delta < self.SEMANTIC_AMBIGUITY_DELTA:
                    logger.info(
                        "Ambiguous objection detection",
                        top=top_intent,
                        top_score=round(top_score, 3),
                        second=objection_scores[1][0],
                        second_score=round(second_score, 3),
                        delta=round(delta, 3),
                    )
                    # Понижаем уверенность при неоднозначности
                    top_score *= 0.85

            # Маппим intent на ObjectionType
            objection_type = INTENT_TO_OBJECTION.get(top_intent)
            if objection_type:
                return (objection_type, top_score, objection_scores)

            return None

        except Exception as e:
            logger.error("Semantic objection detection failed", error=str(e))
            return None

    def reset(self) -> None:
        """Сброс состояния (для нового разговора)."""
        self._regex_handler.reset()

    @property
    def regex_handler(self) -> ObjectionHandler:
        """Доступ к regex handler для обратной совместимости."""
        return self._regex_handler


# =============================================================================
# Singleton
# =============================================================================

_detector: Optional[CascadeObjectionDetector] = None


def get_cascade_objection_detector() -> CascadeObjectionDetector:
    """Получить singleton экземпляр детектора."""
    global _detector
    if _detector is None:
        _detector = CascadeObjectionDetector()
    return _detector


def reset_cascade_objection_detector() -> None:
    """Сбросить singleton (для тестирования)."""
    global _detector
    _detector = None


# =============================================================================
# CLI для тестирования
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("CASCADE OBJECTION DETECTOR DEMO")
    print("=" * 60)

    # Включаем semantic для демо
    flags.set_override("semantic_objection_detection", True)

    detector = CascadeObjectionDetector()

    test_messages = [
        # Tier 1: Regex должен ловить
        "Это слишком дорого",
        "Мы используем Битрикс",
        "Нет времени сейчас",
        "Надо подумать",
        # Tier 2: Semantic должен ловить (перефразировки)
        "Высокая цена",
        "Пользуемся другой программой",
        "Совсем нет свободного времени",
        # Не возражения
        "Сколько стоит?",
        "Расскажите подробнее",
        "Хочу посмотреть демо",
    ]

    for message in test_messages:
        result = detector.detect(message)
        obj_type = result.primary_type.value if result.primary_type else "None"
        print(
            f"{message:40} → {obj_type:15} "
            f"tier={result.tier_used:8} conf={result.confidence:.2f}"
        )

    # Убираем override
    flags.clear_override("semantic_objection_detection")
