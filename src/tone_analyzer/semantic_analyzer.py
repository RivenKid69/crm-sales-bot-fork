"""
Semantic анализатор тона (Tier 2).

Использует TEI (Qwen3-Embedding-4B) embeddings для вычисления similarity
между сообщением и примерами каждого типа тона.
"""

import threading
import time
from typing import Dict, List, Optional, Tuple, Any

from src.logger import logger

from .models import Tone
from .examples import TONE_EXAMPLES


class SemanticToneAnalyzer:
    """
    Tier 2: Semantic анализатор тона на основе embeddings через TEI.

    Особенности:
    - Lazy loading эмбеддингов через TEI /embed
    - Thread-safe инициализация
    - Проверка неоднозначности (ambiguity)
    """

    # Пороги
    THRESHOLD = 0.70              # Минимальный confidence для возврата
    AMBIGUITY_DELTA = 0.15        # Минимальная разница top-1 vs top-2
    TOP_K = 3                     # Количество примеров для усреднения

    # Маппинг tone string -> Tone enum
    TONE_MAPPING: Dict[str, Tone] = {
        "frustrated": Tone.FRUSTRATED,
        "skeptical": Tone.SKEPTICAL,
        "rushed": Tone.RUSHED,
        "confused": Tone.CONFUSED,
        "positive": Tone.POSITIVE,
        "interested": Tone.INTERESTED,
        "neutral": Tone.NEUTRAL,
    }

    def __init__(self):
        self._np = None
        self._tone_embeddings: Dict[str, Any] = {}
        self._all_embeddings = None
        self._example_to_tone: Dict[int, Tuple[str, str]] = {}
        self._initialized = False
        self._init_lock = threading.Lock()
        self._available: Optional[bool] = None

    def _init_embeddings(self) -> bool:
        """Инициализировать embeddings через TEI (thread-safe)."""
        if self._initialized:
            return True

        with self._init_lock:
            if self._initialized:
                return True

            try:
                import numpy as np
                from src.knowledge.tei_client import embed_texts_cached
                self._np = np

                # Собираем все примеры
                all_examples = []
                example_index = 0

                for tone_str, examples in TONE_EXAMPLES.items():
                    for example in examples:
                        all_examples.append(example)
                        self._example_to_tone[example_index] = (tone_str, example)
                        example_index += 1

                # Batch encode через TEI (с disk-кэшем)
                logger.info("Loading semantic tone embeddings via TEI")
                arr = embed_texts_cached(all_examples, cache_name="tone_examples")
                if arr is None:
                    logger.warning("TEI embed failed for tone analyzer")
                    self._available = False
                    return False

                self._all_embeddings = arr.copy()
                # Нормализуем для dot-product = cosine
                norms = np.linalg.norm(self._all_embeddings, axis=1, keepdims=True)
                norms[norms == 0] = 1
                self._all_embeddings = self._all_embeddings / norms

                self._initialized = True
                logger.info(
                    "Semantic tone analyzer initialized via TEI",
                    examples_count=len(all_examples),
                    tones_count=len(TONE_EXAMPLES)
                )
                return True

            except Exception as e:
                logger.error(f"Semantic tone analyzer init error: {e}")
                self._available = False
                return False

    @property
    def is_available(self) -> bool:
        """Проверить доступен ли анализатор."""
        if self._available is not None:
            return self._available

        result = self._init_embeddings()
        self._available = result
        return result

    def _encode_message(self, message: str):
        """Encode single message via TEI and normalize."""
        from src.knowledge.tei_client import embed_single
        raw = embed_single(message)
        if raw is None:
            return None
        emb = self._np.array(raw)
        norm = self._np.linalg.norm(emb)
        if norm > 0:
            emb = emb / norm
        return emb

    def analyze(
        self,
        message: str
    ) -> Optional[Tuple[Tone, float, Dict[str, float]]]:
        """
        Анализировать тон через semantic similarity.

        Returns:
            Tuple[tone, confidence, all_scores] или None если недоступен
        """
        if not self._init_embeddings():
            return None

        if not message or not message.strip():
            return None

        try:
            start_time = time.perf_counter()

            message_emb = self._encode_message(message)
            if message_emb is None:
                return None

            # Cosine similarity со всеми примерами
            similarities = self._np.dot(self._all_embeddings, message_emb)

            # Группируем scores по тонам
            tone_scores: Dict[str, List[float]] = {}

            for idx, sim in enumerate(similarities):
                tone_str, _ = self._example_to_tone[idx]
                if tone_str not in tone_scores:
                    tone_scores[tone_str] = []
                tone_scores[tone_str].append(float(sim))

            # Для каждого тона берём top_k лучших scores и усредняем
            tone_avg_scores: Dict[str, float] = {}

            for tone_str, scores in tone_scores.items():
                top_scores = sorted(scores, reverse=True)[:self.TOP_K]
                tone_avg_scores[tone_str] = sum(top_scores) / len(top_scores)

            if not tone_avg_scores:
                return None

            sorted_tones = sorted(
                tone_avg_scores.items(),
                key=lambda x: x[1],
                reverse=True
            )

            best_tone_str = sorted_tones[0][0]
            best_score = sorted_tones[0][1]

            # Проверяем неоднозначность
            is_ambiguous = False
            if len(sorted_tones) > 1:
                second_score = sorted_tones[1][1]
                delta = best_score - second_score
                if delta < self.AMBIGUITY_DELTA:
                    is_ambiguous = True
                    logger.debug(
                        "Ambiguous tone detection",
                        top=best_tone_str,
                        top_score=round(best_score, 3),
                        second=sorted_tones[1][0],
                        second_score=round(second_score, 3),
                        delta=round(delta, 3)
                    )
                    best_score *= 0.85

            confidence = max(0.0, min(1.0, best_score))

            tone = self.TONE_MAPPING.get(best_tone_str, Tone.NEUTRAL)

            latency_ms = (time.perf_counter() - start_time) * 1000
            logger.debug(
                "Semantic tone analysis",
                tone=tone.value,
                confidence=round(confidence, 3),
                ambiguous=is_ambiguous,
                latency_ms=round(latency_ms, 2)
            )

            return (tone, confidence, tone_avg_scores)

        except Exception as e:
            logger.error(f"Semantic tone analysis failed: {e}")
            return None

    def get_similar_examples(
        self,
        message: str,
        top_k: int = 5
    ) -> List[Tuple[str, str, float]]:
        """
        Получить наиболее похожие примеры.

        Returns:
            List[(example, tone, similarity)]
        """
        if not self._init_embeddings():
            return []

        try:
            message_emb = self._encode_message(message)
            if message_emb is None:
                return []

            similarities = self._np.dot(self._all_embeddings, message_emb)
            top_indices = self._np.argsort(similarities)[-top_k:][::-1]

            results = []
            for idx in top_indices:
                tone_str, example = self._example_to_tone[int(idx)]
                results.append((example, tone_str, float(similarities[idx])))

            return results

        except Exception as e:
            logger.error(f"Get similar examples failed: {e}")
            return []

    def reset(self) -> None:
        """Сброс не требуется (stateless)."""
        pass


# =============================================================================
# Thread-safe Singleton
# =============================================================================

_semantic_tone_analyzer: Optional[SemanticToneAnalyzer] = None
_analyzer_lock = threading.Lock()


def get_semantic_tone_analyzer() -> SemanticToneAnalyzer:
    """Получить singleton экземпляр SemanticToneAnalyzer."""
    global _semantic_tone_analyzer

    if _semantic_tone_analyzer is not None:
        return _semantic_tone_analyzer

    with _analyzer_lock:
        if _semantic_tone_analyzer is None:
            _semantic_tone_analyzer = SemanticToneAnalyzer()

        return _semantic_tone_analyzer


def reset_semantic_tone_analyzer() -> None:
    """Сбросить singleton (для тестирования)."""
    global _semantic_tone_analyzer

    with _analyzer_lock:
        _semantic_tone_analyzer = None
