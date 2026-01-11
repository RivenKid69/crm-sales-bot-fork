"""
Семантический классификатор интентов на основе эмбеддингов.

Использует sentence-transformers для вычисления cosine similarity
между сообщением пользователя и примерами интентов.

Этапы работы:
1. При инициализации: вычисляем эмбеддинги для всех примеров
2. При классификации: вычисляем эмбеддинг сообщения
3. Считаем cosine similarity с каждым примером
4. Группируем по интентам и выбираем лучший
"""

import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
from enum import Enum

from .examples import INTENT_EXAMPLES


class SemanticMatchType(Enum):
    """Тип семантического совпадения."""
    EXACT = "exact"           # Очень высокое сходство (>0.9)
    STRONG = "strong"         # Сильное сходство (>0.75)
    MODERATE = "moderate"     # Умеренное сходство (>0.6)
    WEAK = "weak"             # Слабое сходство (>0.4)
    NONE = "none"             # Нет совпадения


@dataclass
class SemanticResult:
    """Результат семантической классификации."""
    intent: str
    confidence: float
    match_type: SemanticMatchType
    top_similar_examples: List[Tuple[str, float]] = field(default_factory=list)
    all_scores: Dict[str, float] = field(default_factory=dict)


class SemanticClassifier:
    """
    Семантический классификатор на основе эмбеддингов.

    Использует предвычисленные эмбеддинги примеров для быстрой
    классификации новых сообщений.

    Attributes:
        embedder: Модель sentence-transformers
        intent_embeddings: Словарь {intent: List[embedding]}
        thresholds: Пороги для разных уровней уверенности
    """

    # Пороги уверенности
    THRESHOLD_EXACT = 0.90
    THRESHOLD_STRONG = 0.75
    THRESHOLD_MODERATE = 0.60
    THRESHOLD_WEAK = 0.40

    def __init__(
        self,
        model_name: str = None,
        examples: Dict[str, List[str]] = None,
        min_confidence: float = 0.5
    ):
        """
        Инициализация классификатора.

        Args:
            model_name: Название модели sentence-transformers
                       (по умолчанию из settings)
            examples: Словарь примеров {intent: [examples]}
                     (по умолчанию INTENT_EXAMPLES)
            min_confidence: Минимальный порог уверенности
        """
        self.model_name = model_name
        self.examples = examples or INTENT_EXAMPLES
        self.min_confidence = min_confidence

        # Lazy initialization
        self._embedder = None
        self._np = None
        self._intent_embeddings: Dict[str, Any] = {}
        self._example_to_intent: Dict[int, Tuple[str, str]] = {}
        self._all_embeddings = None
        self._initialized = False
        self._init_lock = threading.Lock()

    def _get_model_name(self) -> str:
        """Получить имя модели из settings или default."""
        if self.model_name:
            return self.model_name

        try:
            from settings import settings
            return getattr(
                getattr(settings, 'retriever', None),
                'embedder_model',
                'ai-forever/ru-en-RoSBERTa'
            )
        except ImportError:
            return 'ai-forever/ru-en-RoSBERTa'

    def _init_embeddings(self) -> bool:
        """
        Инициализировать эмбеддинги (thread-safe).

        Returns:
            True если инициализация успешна
        """
        if self._initialized:
            return True

        with self._init_lock:
            # Double-check после получения lock
            if self._initialized:
                return True

            try:
                from sentence_transformers import SentenceTransformer
                import numpy as np
                self._np = np

                model_name = self._get_model_name()
                self._embedder = SentenceTransformer(model_name)

                # Собираем все примеры
                all_examples = []
                example_index = 0

                for intent, examples in self.examples.items():
                    intent_example_indices = []
                    for example in examples:
                        all_examples.append(example)
                        self._example_to_intent[example_index] = (intent, example)
                        intent_example_indices.append(example_index)
                        example_index += 1
                    self._intent_embeddings[intent] = intent_example_indices

                # Batch encode все примеры
                self._all_embeddings = self._embedder.encode(
                    all_examples,
                    convert_to_numpy=True,
                    normalize_embeddings=True
                )

                self._initialized = True
                return True

            except ImportError:
                return False
            except Exception as e:
                print(f"[SemanticClassifier] Init error: {e}")
                return False

    @property
    def is_available(self) -> bool:
        """Проверить доступен ли классификатор."""
        return self._init_embeddings()

    def classify(
        self,
        message: str,
        top_k: int = 3
    ) -> Tuple[str, float, Dict[str, float]]:
        """
        Классифицировать сообщение.

        Args:
            message: Текст сообщения
            top_k: Количество примеров для усреднения по интенту

        Returns:
            Tuple[intent, confidence, all_scores]
        """
        if not self._init_embeddings():
            return "unclear", 0.0, {}

        if not message or not message.strip():
            return "unclear", 0.0, {}

        # Encode сообщение
        message_emb = self._embedder.encode(
            message,
            convert_to_numpy=True,
            normalize_embeddings=True
        )

        # Cosine similarity со всеми примерами
        # (embeddings уже нормализованы, так что dot product = cosine)
        similarities = self._np.dot(self._all_embeddings, message_emb)

        # Группируем scores по интентам
        intent_scores: Dict[str, List[float]] = {}

        for idx, sim in enumerate(similarities):
            intent, _ = self._example_to_intent[idx]
            if intent not in intent_scores:
                intent_scores[intent] = []
            intent_scores[intent].append(float(sim))

        # Для каждого интента берём top_k лучших scores и усредняем
        intent_avg_scores: Dict[str, float] = {}

        for intent, scores in intent_scores.items():
            top_scores = sorted(scores, reverse=True)[:top_k]
            intent_avg_scores[intent] = sum(top_scores) / len(top_scores)

        # Находим лучший интент
        if not intent_avg_scores:
            return "unclear", 0.0, {}

        best_intent = max(intent_avg_scores, key=intent_avg_scores.get)
        best_score = intent_avg_scores[best_intent]

        # Нормализуем confidence (similarity может быть от -1 до 1)
        confidence = max(0.0, min(1.0, best_score))

        return best_intent, confidence, intent_avg_scores

    def classify_detailed(
        self,
        message: str,
        top_k: int = 3
    ) -> SemanticResult:
        """
        Детальная классификация с информацией о совпадениях.

        Args:
            message: Текст сообщения
            top_k: Количество top примеров

        Returns:
            SemanticResult с детальной информацией
        """
        if not self._init_embeddings():
            return SemanticResult(
                intent="unclear",
                confidence=0.0,
                match_type=SemanticMatchType.NONE
            )

        if not message or not message.strip():
            return SemanticResult(
                intent="unclear",
                confidence=0.0,
                match_type=SemanticMatchType.NONE
            )

        # Encode сообщение
        message_emb = self._embedder.encode(
            message,
            convert_to_numpy=True,
            normalize_embeddings=True
        )

        # Cosine similarity
        similarities = self._np.dot(self._all_embeddings, message_emb)

        # Собираем top похожие примеры
        top_indices = self._np.argsort(similarities)[-top_k * 3:][::-1]
        top_similar = []

        for idx in top_indices:
            intent, example = self._example_to_intent[int(idx)]
            top_similar.append((example, float(similarities[idx]), intent))

        # Группируем по интентам
        intent_scores: Dict[str, List[float]] = {}

        for idx, sim in enumerate(similarities):
            intent, _ = self._example_to_intent[idx]
            if intent not in intent_scores:
                intent_scores[intent] = []
            intent_scores[intent].append(float(sim))

        # Усредняем top_k scores
        all_scores: Dict[str, float] = {}

        for intent, scores in intent_scores.items():
            top_scores = sorted(scores, reverse=True)[:top_k]
            all_scores[intent] = sum(top_scores) / len(top_scores)

        # Лучший интент
        best_intent = max(all_scores, key=all_scores.get)
        best_score = all_scores[best_intent]
        confidence = max(0.0, min(1.0, best_score))

        # Определяем тип совпадения
        if confidence >= self.THRESHOLD_EXACT:
            match_type = SemanticMatchType.EXACT
        elif confidence >= self.THRESHOLD_STRONG:
            match_type = SemanticMatchType.STRONG
        elif confidence >= self.THRESHOLD_MODERATE:
            match_type = SemanticMatchType.MODERATE
        elif confidence >= self.THRESHOLD_WEAK:
            match_type = SemanticMatchType.WEAK
        else:
            match_type = SemanticMatchType.NONE

        return SemanticResult(
            intent=best_intent,
            confidence=confidence,
            match_type=match_type,
            top_similar_examples=[(ex, score) for ex, score, _ in top_similar[:top_k]],
            all_scores=all_scores
        )

    def get_similar_examples(
        self,
        message: str,
        top_k: int = 5
    ) -> List[Tuple[str, str, float]]:
        """
        Получить наиболее похожие примеры.

        Args:
            message: Текст сообщения
            top_k: Количество примеров

        Returns:
            List[(example, intent, similarity)]
        """
        if not self._init_embeddings():
            return []

        message_emb = self._embedder.encode(
            message,
            convert_to_numpy=True,
            normalize_embeddings=True
        )

        similarities = self._np.dot(self._all_embeddings, message_emb)
        top_indices = self._np.argsort(similarities)[-top_k:][::-1]

        results = []
        for idx in top_indices:
            intent, example = self._example_to_intent[int(idx)]
            results.append((example, intent, float(similarities[idx])))

        return results

    def explain(self, message: str) -> Dict:
        """
        Объяснить классификацию (для отладки).

        Args:
            message: Текст сообщения

        Returns:
            Словарь с объяснением
        """
        result = self.classify_detailed(message, top_k=5)

        # Top 3 интента
        sorted_intents = sorted(
            result.all_scores.items(),
            key=lambda x: x[1],
            reverse=True
        )[:3]

        return {
            "message": message,
            "predicted_intent": result.intent,
            "confidence": round(result.confidence, 4),
            "match_type": result.match_type.value,
            "top_intents": [
                {"intent": intent, "score": round(score, 4)}
                for intent, score in sorted_intents
            ],
            "top_similar_examples": [
                {"example": ex, "similarity": round(sim, 4)}
                for ex, sim in result.top_similar_examples
            ],
        }


# =============================================================================
# Thread-safe Singleton
# =============================================================================

_semantic_classifier: Optional[SemanticClassifier] = None
_classifier_lock = threading.Lock()


def get_semantic_classifier() -> SemanticClassifier:
    """
    Получить singleton экземпляр SemanticClassifier.

    Thread-safe с Double-Checked Locking.
    """
    global _semantic_classifier

    if _semantic_classifier is not None:
        return _semantic_classifier

    with _classifier_lock:
        if _semantic_classifier is None:
            _semantic_classifier = SemanticClassifier()

        return _semantic_classifier


def reset_semantic_classifier() -> None:
    """Сбросить singleton (для тестирования)."""
    global _semantic_classifier

    with _classifier_lock:
        _semantic_classifier = None
