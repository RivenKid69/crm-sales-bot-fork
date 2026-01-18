"""
Каскадный анализатор тона.

Оркестрирует 3-уровневый каскад:
1. Tier 1: Regex (быстрый, явные сигналы)
2. Tier 2: Semantic (FRIDA, неявные сигналы)
3. Tier 3: LLM (сарказм, ирония)
"""

import threading
import time
from typing import Dict, List, Optional

from logger import logger
from feature_flags import flags

from .models import Tone, Style, ToneAnalysis
from .regex_analyzer import RegexToneAnalyzer
from .semantic_analyzer import SemanticToneAnalyzer, get_semantic_tone_analyzer
from .llm_analyzer import LLMToneAnalyzer
from .frustration_tracker import FrustrationTracker


class CascadeToneConfig:
    """Конфигурация каскадного анализатора."""

    # Tier 1: Explicit markers (fast path)
    TIER1_HIGH_CONFIDENCE = 0.85      # Early return threshold
    TIER1_MIN_SIGNALS = 1             # Минимум сигналов для high confidence

    # Tier 2: Semantic (FRIDA)
    TIER2_THRESHOLD = 0.70            # Min confidence для return

    # Tier 3: LLM
    TIER3_THRESHOLD = 0.65            # Min confidence

    # Fallback
    MIN_CONFIDENCE = 0.30             # Ниже → NEUTRAL


class CascadeToneAnalyzer:
    """
    Каскадный анализатор тона с RuBERT + LLM fallback.

    Архитектура:
        Tier 1: Regex (быстрый) → если confidence >= 0.85 и есть сигналы → return
        Tier 2: Semantic (FRIDA) → если confidence >= 0.70 → return
        Tier 3: LLM → если confidence >= 0.65 → return
        Fallback: NEUTRAL

    Особенности:
    - Полная совместимость с legacy ToneAnalyzer API
    - Lazy loading для Tier 2 и Tier 3
    - Feature flags для управления уровнями
    - Общий FrustrationTracker для всех уровней
    """

    # Class attributes для обратной совместимости с legacy ToneAnalyzer
    from .markers import (
        MAX_FRUSTRATION,
        FRUSTRATION_THRESHOLDS,
        FRUSTRATION_WEIGHTS,
        FRUSTRATION_DECAY,
        TONE_MARKERS,
        INFORMAL_MARKERS,
    )

    def __init__(self, llm=None):
        """
        Инициализация каскадного анализатора.

        Args:
            llm: Экземпляр OllamaLLM для Tier 3 (опционально)
        """
        # Общий frustration tracker (создаём СНАЧАЛА)
        self._frustration = FrustrationTracker()

        # Tier 1: Regex (передаём общий frustration tracker)
        # Это устраняет дублирование трекеров
        self._regex = RegexToneAnalyzer(frustration_tracker=self._frustration)

        # Tier 2: Semantic (lazy)
        self._semantic: Optional[SemanticToneAnalyzer] = None

        # Tier 3: LLM (lazy)
        self._llm_analyzer: Optional[LLMToneAnalyzer] = None
        self._external_llm = llm

        # Конфигурация
        self.config = CascadeToneConfig()

    @property
    def semantic_analyzer(self) -> Optional[SemanticToneAnalyzer]:
        """Lazy initialization Tier 2."""
        if not flags.tone_semantic_tier2:
            return None

        if self._semantic is None:
            self._semantic = get_semantic_tone_analyzer()

        return self._semantic

    @property
    def llm_analyzer(self) -> Optional[LLMToneAnalyzer]:
        """Lazy initialization Tier 3."""
        if not flags.tone_llm_tier3:
            return None

        if self._llm_analyzer is None:
            self._llm_analyzer = LLMToneAnalyzer(llm=self._external_llm)

        return self._llm_analyzer

    def analyze(
        self,
        message: str,
        history: Optional[List[str]] = None
    ) -> ToneAnalysis:
        """
        Анализировать тон через каскад.

        Совместимый интерфейс с legacy ToneAnalyzer.

        Args:
            message: Текст сообщения
            history: История сообщений (опционально)

        Returns:
            ToneAnalysis с результатами
        """
        start_time = time.perf_counter()

        # ================================================================
        # TIER 1: Regex
        # ================================================================
        tier1_result = self._regex.analyze(message, history)

        # Fast path: явные сигналы с высокой уверенностью
        if (tier1_result.signals
            and tier1_result.confidence >= self.config.TIER1_HIGH_CONFIDENCE):

            # NOTE: frustration tracker уже обновлён в RegexToneAnalyzer.analyze()
            # так как используется общий трекер (передан в конструктор)
            tier1_result.latency_ms = (time.perf_counter() - start_time) * 1000

            logger.debug(
                "Tier 1 fast path",
                tone=tier1_result.tone.value,
                confidence=round(tier1_result.confidence, 3),
                signals=len(tier1_result.signals)
            )

            return tier1_result

        # ================================================================
        # TIER 2: Semantic (если включён и Tier 1 не уверен)
        # ================================================================
        tier2_result = None

        if self.semantic_analyzer and self.semantic_analyzer.is_available:
            tier2_result = self.semantic_analyzer.analyze(message)

            if tier2_result:
                tone, confidence, scores = tier2_result

                if confidence >= self.config.TIER2_THRESHOLD:
                    # Tier 2 достаточно уверен
                    self._frustration.update(tone)

                    result = ToneAnalysis(
                        tone=tone,
                        style=tier1_result.style,  # Стиль от Tier 1
                        confidence=confidence,
                        frustration_level=self._frustration.level,
                        signals=tier1_result.signals,  # Сигналы от Tier 1
                        tier_used="semantic",
                        tier_scores=scores,
                        latency_ms=(time.perf_counter() - start_time) * 1000,
                    )

                    logger.debug(
                        "Tier 2 semantic",
                        tone=tone.value,
                        confidence=round(confidence, 3)
                    )

                    return result

        # ================================================================
        # TIER 3: LLM (если включён и Tier 1-2 не уверены)
        # ================================================================
        tier3_result = None

        if self.llm_analyzer:
            tier3_result = self.llm_analyzer.analyze(message)

            if tier3_result:
                tone, confidence = tier3_result

                if confidence >= self.config.TIER3_THRESHOLD:
                    # Tier 3 дал результат
                    self._frustration.update(tone)

                    result = ToneAnalysis(
                        tone=tone,
                        style=tier1_result.style,
                        confidence=confidence,
                        frustration_level=self._frustration.level,
                        signals=tier1_result.signals,
                        tier_used="llm",
                        tier_scores={tone.value: confidence},
                        latency_ms=(time.perf_counter() - start_time) * 1000,
                    )

                    logger.debug(
                        "Tier 3 LLM",
                        tone=tone.value,
                        confidence=round(confidence, 3)
                    )

                    return result

        # ================================================================
        # FALLBACK: Возвращаем результат Tier 1 или выбираем лучший
        # ================================================================

        # Собираем все результаты
        candidates = [(tier1_result.tone, tier1_result.confidence, "regex")]

        if tier2_result:
            tone, confidence, _ = tier2_result
            candidates.append((tone, confidence, "semantic"))

        if tier3_result:
            tone, confidence = tier3_result
            candidates.append((tone, confidence, "llm"))

        # Выбираем лучший по confidence
        best = max(candidates, key=lambda x: x[1])
        best_tone, best_confidence, best_tier = best

        # Если confidence слишком низкий — NEUTRAL
        if best_confidence < self.config.MIN_CONFIDENCE:
            best_tone = Tone.NEUTRAL
            best_tier = "fallback"

        # Обновляем frustration ТОЛЬКО если выбрали другой тон
        # (RegexToneAnalyzer уже обновил frustration с tier1_result.tone)
        if best_tone != tier1_result.tone:
            self._frustration.update(best_tone)

        result = ToneAnalysis(
            tone=best_tone,
            style=tier1_result.style,
            confidence=best_confidence,
            frustration_level=self._frustration.level,
            signals=tier1_result.signals,
            tier_used=best_tier,
            tier_scores=tier1_result.tier_scores,
            latency_ms=(time.perf_counter() - start_time) * 1000,
        )

        logger.debug(
            "Cascade fallback",
            tone=best_tone.value,
            confidence=round(best_confidence, 3),
            tier=best_tier
        )

        return result

    def get_response_guidance(self, analysis: ToneAnalysis) -> Dict:
        """
        Получить рекомендации для генерации ответа.

        Делегирует в RegexToneAnalyzer для совместимости.
        """
        return self._regex.get_response_guidance(analysis)

    def reset(self) -> None:
        """Сброс состояния для нового диалога."""
        self._regex.reset()
        self._frustration.reset()

    def get_frustration_level(self) -> int:
        """Получить текущий уровень frustration."""
        return self._frustration.level

    def is_frustrated(self) -> bool:
        """Проверка на повышенный frustration."""
        return self._frustration.is_warning()

    def is_critically_frustrated(self) -> bool:
        """Проверка на критический frustration."""
        return self._frustration.is_critical()

    def get_frustration_history(self) -> List[Dict]:
        """Получить историю изменения frustration."""
        return self._frustration.history

    @property
    def frustration_tracker(self) -> FrustrationTracker:
        """Доступ к трекеру frustration."""
        return self._frustration

    def explain(self, message: str) -> Dict:
        """
        Объяснить классификацию (для отладки).

        Args:
            message: Текст сообщения

        Returns:
            Детальное объяснение
        """
        result = self.analyze(message)

        explanation = {
            "message": message,
            "final_tone": result.tone.value,
            "final_confidence": round(result.confidence, 4),
            "tier_used": result.tier_used,
            "style": result.style.value,
            "frustration_level": result.frustration_level,
            "signals": result.signals,
            "tier_scores": {k: round(v, 4) for k, v in result.tier_scores.items()},
            "latency_ms": round(result.latency_ms, 2),
        }

        # Добавляем similar examples если semantic доступен
        if self.semantic_analyzer and self.semantic_analyzer.is_available:
            similar = self.semantic_analyzer.get_similar_examples(message, top_k=3)
            explanation["similar_examples"] = [
                {"example": ex, "tone": tone, "similarity": round(sim, 4)}
                for ex, tone, sim in similar
            ]

        return explanation


# =============================================================================
# Thread-safe Singleton
# =============================================================================

_cascade_tone_analyzer: Optional[CascadeToneAnalyzer] = None
_analyzer_lock = threading.Lock()


def get_cascade_tone_analyzer(llm=None) -> CascadeToneAnalyzer:
    """
    Получить singleton экземпляр CascadeToneAnalyzer.

    Args:
        llm: Экземпляр OllamaLLM для Tier 3 (опционально)

    Returns:
        CascadeToneAnalyzer
    """
    global _cascade_tone_analyzer

    if _cascade_tone_analyzer is not None:
        return _cascade_tone_analyzer

    with _analyzer_lock:
        if _cascade_tone_analyzer is None:
            _cascade_tone_analyzer = CascadeToneAnalyzer(llm=llm)

        return _cascade_tone_analyzer


def reset_cascade_tone_analyzer() -> None:
    """Сбросить singleton (для тестирования)."""
    global _cascade_tone_analyzer

    with _analyzer_lock:
        if _cascade_tone_analyzer is not None:
            _cascade_tone_analyzer.reset()
        _cascade_tone_analyzer = None
