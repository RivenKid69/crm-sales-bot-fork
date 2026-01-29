"""
Industry Detector v2 — улучшенное определение отрасли клиента.

Стратегия каскадного определения:
1. Tier 1: Keyword matching (быстрый, если confidence >0.8)
2. Tier 2: Semantic matching через FRIDA embeddings
3. Накопление уверенности по ходу диалога

На основе исследований:
- Dialogue State Tracking: использование истории диалога
- User Modeling: построение профиля по ходу беседы
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, TYPE_CHECKING
import re

from src.logger import logger

if TYPE_CHECKING:
    from knowledge.retriever import CascadeRetriever


@dataclass
class IndustryDetectionResult:
    """Результат определения отрасли."""

    industry: Optional[str] = None  # "retail", "services", "horeca", etc.
    confidence: float = 0.0  # 0-1
    method: str = "unknown"  # "keyword" | "semantic" | "combined"

    # Детали для логирования
    keyword_score: float = 0.0
    semantic_score: float = 0.0
    matched_keywords: List[str] = field(default_factory=list)


class IndustryDetectorV2:
    """
    Улучшенный детектор отрасли с semantic matching.

    Использует:
    1. Keyword matching (из v1 PersonalizationEngine)
    2. Semantic matching через FRIDA embeddings (если доступен)
    3. Накопление confidence по ходу диалога

    Usage:
        detector = IndustryDetectorV2(retriever)
        result = detector.detect(collected_data, messages)
        if result.confidence > 0.6:
            print(f"Industry: {result.industry}")
    """

    # === Industry Profiles ===
    # Расширенные профили для semantic matching
    INDUSTRY_PROFILES: Dict[str, Dict[str, Any]] = {
        "retail": {
            "description": "Розничная торговля, магазины, продажа товаров, учёт остатков, работа с поставщиками",
            "keywords": ["магазин", "розница", "торговля", "товар", "остатки", "склад", "продавец"],
            "pain_examples": ["пересортица", "недостачи", "списания", "учет товаров", "инвентаризация"],
            "business_types": ["магазин", "торговля", "ритейл", "розничный"],
        },
        "services": {
            "description": "Сфера услуг, салоны красоты, студии, клиники, запись клиентов, расписание",
            "keywords": ["услуг", "сервис", "салон", "студия", "клиник", "запись", "мастер"],
            "pain_examples": ["пропущенные записи", "накладки", "расписание", "забытые клиенты"],
            "business_types": ["салон", "студия", "клиника", "услуги", "сервис"],
        },
        "horeca": {
            "description": "Рестораны, кафе, общепит, доставка еды, бронирование столиков, заказы",
            "keywords": ["ресторан", "кафе", "общепит", "бар", "доставка еды", "столик", "повар"],
            "pain_examples": ["потерянные заказы", "очереди", "учёт продуктов", "бронирование"],
            "business_types": ["ресторан", "кафе", "бар", "пиццерия", "доставка"],
        },
        "b2b": {
            "description": "B2B продажи, оптовая торговля, дистрибуция, работа с контрактами, дебиторка",
            "keywords": ["опт", "b2b", "дилер", "дистрибут", "поставщик", "контракт", "тендер"],
            "pain_examples": ["долгие сделки", "потерянные контакты", "забытые follow-up", "дебиторка"],
            "business_types": ["опт", "оптовая", "дистрибьютор", "поставщик", "b2b"],
        },
        "real_estate": {
            "description": "Недвижимость, риелторы, застройщики, показы объектов, сделки с недвижимостью",
            "keywords": ["недвижимост", "риелтор", "застройщик", "агентство недвиж", "квартир", "объект"],
            "pain_examples": ["потерянные лиды", "забытые показы", "конкуренция", "срыв сделок"],
            "business_types": ["недвижимость", "риелтор", "застройщик", "агентство"],
        },
        "it": {
            "description": "IT компании, разработка, digital агентства, проекты, задачи, клиенты",
            "keywords": ["it", "разработ", "софт", "digital", "агентство", "проект", "программ"],
            "pain_examples": ["срывы сроков", "потеря контекста", "нет прозрачности", "коммуникация"],
            "business_types": ["it", "разработка", "digital", "агентство", "студия разработки"],
        },
    }

    # Веса для комбинирования scores
    KEYWORD_WEIGHT = 0.6
    SEMANTIC_WEIGHT = 0.4

    # Минимальные пороги
    KEYWORD_MIN_CONFIDENCE = 0.3
    SEMANTIC_MIN_CONFIDENCE = 0.4
    COMBINED_MIN_CONFIDENCE = 0.5

    def __init__(self, retriever: "CascadeRetriever" = None):
        """
        Initialize industry detector.

        Args:
            retriever: CascadeRetriever instance for semantic matching (optional)
        """
        self.retriever = retriever
        self._embeddings_cache: Dict[str, Any] = {}
        self._init_embeddings()

    def _init_embeddings(self) -> None:
        """Pre-compute embeddings for industry profiles."""
        if not self.retriever or not hasattr(self.retriever, "embedder"):
            return

        embedder = self.retriever.embedder
        if not embedder:
            return

        try:
            # Use FRIDA prefix if available
            use_prefixes = getattr(self.retriever, "_use_prefixes", False)

            for industry, profile in self.INDUSTRY_PROFILES.items():
                text = profile["description"]
                if use_prefixes:
                    text = f"search_document: {text}"

                embedding = embedder.encode(text)
                self._embeddings_cache[industry] = embedding

            logger.debug(
                "Industry embeddings initialized",
                industries=list(self._embeddings_cache.keys()),
            )
        except Exception as e:
            logger.warning(f"Failed to initialize industry embeddings: {e}")

    def detect(
        self,
        collected_data: Dict[str, Any],
        messages: List[str] = None,
        previous_confidence: float = 0.0,
        previous_industry: Optional[str] = None,
    ) -> IndustryDetectionResult:
        """
        Определить отрасль клиента.

        Args:
            collected_data: Собранные данные о клиенте (business_type, pain_point, etc.)
            messages: Список последних сообщений клиента (для semantic matching)
            previous_confidence: Предыдущая уверенность (для накопления)
            previous_industry: Предыдущая определённая отрасль

        Returns:
            IndustryDetectionResult с отраслью и уверенностью
        """
        # Stage 1: Keyword matching (fast path)
        keyword_result = self._keyword_match(collected_data)

        # Early return if high confidence keyword match
        if keyword_result.confidence >= 0.8:
            logger.debug(
                "Industry detected via keywords (high confidence)",
                industry=keyword_result.industry,
                confidence=keyword_result.confidence,
            )
            return keyword_result

        # Stage 2: Semantic matching (if available and messages provided)
        semantic_result = None
        if messages and self._embeddings_cache:
            semantic_result = self._semantic_match(messages)

        # Stage 3: Combine results
        if semantic_result and semantic_result.confidence > self.SEMANTIC_MIN_CONFIDENCE:
            combined = self._combine_results(keyword_result, semantic_result)
        else:
            combined = keyword_result

        # Stage 4: Apply confidence accumulation
        if previous_industry and previous_industry == combined.industry:
            # Same industry detected again - boost confidence
            boost = min(0.1, (1 - combined.confidence) * 0.3)
            combined.confidence = min(1.0, combined.confidence + boost)

        logger.debug(
            "Industry detection completed",
            industry=combined.industry,
            confidence=combined.confidence,
            method=combined.method,
            keyword_score=combined.keyword_score,
            semantic_score=combined.semantic_score,
        )

        return combined

    def _keyword_match(self, collected_data: Dict[str, Any]) -> IndustryDetectionResult:
        """
        Keyword-based industry detection (Tier 1).

        Проверяет business_type и pain_point на ключевые слова.
        """
        result = IndustryDetectionResult(method="keyword")

        # Собираем текст для анализа
        business_type = str(collected_data.get("business_type") or "").lower()
        pain_point = str(collected_data.get("pain_point") or "").lower()
        combined_text = f"{business_type} {pain_point}"

        if not combined_text.strip():
            return result

        # Считаем совпадения по каждой отрасли
        industry_scores: Dict[str, float] = {}
        industry_matches: Dict[str, List[str]] = {}

        for industry, profile in self.INDUSTRY_PROFILES.items():
            score = 0.0
            matches = []

            # Проверяем keywords
            for keyword in profile["keywords"]:
                if keyword.lower() in combined_text:
                    score += 0.3
                    matches.append(keyword)

            # Проверяем business_types (более высокий вес)
            for bt in profile["business_types"]:
                if bt.lower() in business_type:
                    score += 0.5
                    matches.append(f"business:{bt}")

            # Проверяем pain_examples
            for pain in profile["pain_examples"]:
                if pain.lower() in pain_point:
                    score += 0.2
                    matches.append(f"pain:{pain}")

            if score > 0:
                industry_scores[industry] = min(1.0, score)
                industry_matches[industry] = matches

        # Выбираем лучшее совпадение
        if industry_scores:
            best_industry = max(industry_scores, key=industry_scores.get)
            result.industry = best_industry
            result.confidence = industry_scores[best_industry]
            result.keyword_score = result.confidence
            result.matched_keywords = industry_matches.get(best_industry, [])

        return result

    def _semantic_match(self, messages: List[str]) -> IndustryDetectionResult:
        """
        Semantic-based industry detection (Tier 2).

        Использует FRIDA embeddings для сравнения сообщений с профилями отраслей.
        """
        result = IndustryDetectionResult(method="semantic")

        if not self._embeddings_cache or not self.retriever:
            return result

        embedder = self.retriever.embedder
        if not embedder:
            return result

        try:
            # Объединяем последние сообщения
            combined_text = " ".join(messages[-5:])  # Последние 5 сообщений
            if not combined_text.strip():
                return result

            # Применяем FRIDA prefix если нужно
            use_prefixes = getattr(self.retriever, "_use_prefixes", False)
            if use_prefixes:
                combined_text = f"search_query: {combined_text}"

            # Получаем embedding для сообщений
            query_embedding = embedder.encode(combined_text)

            # Сравниваем с профилями отраслей
            scores = {}
            for industry, industry_embedding in self._embeddings_cache.items():
                similarity = self._cosine_similarity(query_embedding, industry_embedding)
                scores[industry] = similarity

            # Выбираем лучшее совпадение
            if scores:
                best_industry = max(scores, key=scores.get)
                best_score = scores[best_industry]

                # Нормализуем score (cosine similarity может быть низким)
                # Типичные значения 0.3-0.7 для похожих текстов
                normalized_score = min(1.0, max(0.0, (best_score - 0.2) / 0.5))

                result.industry = best_industry
                result.confidence = normalized_score
                result.semantic_score = normalized_score

        except Exception as e:
            logger.warning(f"Semantic industry detection failed: {e}")

        return result

    def _combine_results(
        self,
        keyword_result: IndustryDetectionResult,
        semantic_result: IndustryDetectionResult,
    ) -> IndustryDetectionResult:
        """
        Combine keyword and semantic results.

        Если обе методы указывают на одну отрасль - boost confidence.
        Если разные - выбираем по весам.
        """
        result = IndustryDetectionResult(method="combined")
        result.keyword_score = keyword_result.keyword_score
        result.semantic_score = semantic_result.semantic_score

        # Если обе методы согласны
        if (
            keyword_result.industry
            and semantic_result.industry
            and keyword_result.industry == semantic_result.industry
        ):
            result.industry = keyword_result.industry
            # Boost confidence when both methods agree
            combined_confidence = (
                keyword_result.confidence * self.KEYWORD_WEIGHT
                + semantic_result.confidence * self.SEMANTIC_WEIGHT
                + 0.1  # Agreement bonus
            )
            result.confidence = min(1.0, combined_confidence)
            result.matched_keywords = keyword_result.matched_keywords
            return result

        # Если методы не согласны - выбираем по взвешенному score
        keyword_weighted = keyword_result.confidence * self.KEYWORD_WEIGHT
        semantic_weighted = semantic_result.confidence * self.SEMANTIC_WEIGHT

        if keyword_weighted >= semantic_weighted and keyword_result.industry:
            result.industry = keyword_result.industry
            result.confidence = keyword_result.confidence
            result.matched_keywords = keyword_result.matched_keywords
        elif semantic_result.industry:
            result.industry = semantic_result.industry
            result.confidence = semantic_result.confidence
        elif keyword_result.industry:
            result.industry = keyword_result.industry
            result.confidence = keyword_result.confidence
            result.matched_keywords = keyword_result.matched_keywords

        return result

    def _cosine_similarity(self, vec1, vec2) -> float:
        """Calculate cosine similarity between two vectors."""
        try:
            import numpy as np

            dot_product = np.dot(vec1, vec2)
            norm1 = np.linalg.norm(vec1)
            norm2 = np.linalg.norm(vec2)

            if norm1 == 0 or norm2 == 0:
                return 0.0

            return float(dot_product / (norm1 * norm2))
        except ImportError:
            # Fallback without numpy
            dot_product = sum(a * b for a, b in zip(vec1, vec2))
            norm1 = sum(a * a for a in vec1) ** 0.5
            norm2 = sum(b * b for b in vec2) ** 0.5

            if norm1 == 0 or norm2 == 0:
                return 0.0

            return dot_product / (norm1 * norm2)

    def get_industry_context(self, industry: str) -> Dict[str, Any]:
        """
        Get context for a specific industry.

        Args:
            industry: Industry name

        Returns:
            Dictionary with keywords, examples, pain_examples
        """
        profile = self.INDUSTRY_PROFILES.get(industry, {})
        return {
            "keywords": profile.get("keywords", []),
            "examples": profile.get("business_types", []),
            "pain_examples": profile.get("pain_examples", []),
        }
