"""
Regex-based анализатор тона (Tier 1).

Быстрый анализ на основе ключевых слов и паттернов.
Используется как первый уровень каскада.
"""

import re
import time
from typing import Dict, List, Optional, Tuple

from src.logger import logger
from src.settings import settings

from .models import Tone, Style, ToneAnalysis
from .markers import (
    TONE_MARKERS,
    INFORMAL_MARKERS,
    FRUSTRATION_THRESHOLDS,
)
from .frustration_tracker import FrustrationTracker


class RegexToneAnalyzer:
    """
    Tier 1: Regex-based анализатор тона.

    Особенности:
    - Быстрый анализ по ключевым словам и эмодзи
    - Определение стиля (formal/informal)
    - Приоритет тонов (FRUSTRATED самый важный)
    - Расчёт confidence на основе количества сигналов
    """

    # Порядок приоритетов тонов
    TONE_PRIORITY = [
        Tone.FRUSTRATED,
        Tone.RUSHED,
        Tone.SKEPTICAL,
        Tone.CONFUSED,
        Tone.POSITIVE,
        Tone.INTERESTED,
    ]

    # Пороги confidence
    BASE_CONFIDENCE = 0.80
    SIGNAL_BOOST = 0.05
    MAX_CONFIDENCE = 0.95
    NO_SIGNAL_CONFIDENCE = 0.30

    def __init__(self, frustration_tracker: Optional[FrustrationTracker] = None):
        """
        Инициализация анализатора.

        Args:
            frustration_tracker: Внешний FrustrationTracker для использования.
                                 Если None, создаётся собственный.
        """
        self._compiled_patterns: Dict[Tone, List[re.Pattern]] = {}
        self._compiled_informal: List[re.Pattern] = []
        self._owns_frustration_tracker = frustration_tracker is None
        self._frustration_tracker = frustration_tracker or FrustrationTracker()
        self._compile_patterns()

    def _compile_patterns(self) -> None:
        """Компилируем regex паттерны для производительности."""
        for tone, markers in TONE_MARKERS.items():
            self._compiled_patterns[tone] = [
                re.compile(m, re.IGNORECASE | re.UNICODE) for m in markers
            ]

        self._compiled_informal = [
            re.compile(m, re.IGNORECASE | re.UNICODE) for m in INFORMAL_MARKERS
        ]

    def analyze(
        self,
        message: str,
        history: Optional[List[str]] = None
    ) -> ToneAnalysis:
        """
        Анализировать тон сообщения.

        Args:
            message: Текст сообщения
            history: История сообщений (не используется напрямую)

        Returns:
            ToneAnalysis с результатами
        """
        start_time = time.perf_counter()

        message_lower = message.lower()
        signals: List[str] = []
        detected_tones: List[Tone] = []
        tone_scores: Dict[Tone, int] = {}

        # Поиск сигналов тона
        # NOTE: Count ALL signals for intensity-based frustration calculation
        # (Previous bug: break after first signal missed multi-signal intensity)
        for tone, patterns in self._compiled_patterns.items():
            for pattern in patterns:
                if pattern.search(message_lower):
                    if tone not in detected_tones:
                        detected_tones.append(tone)
                    tone_scores[tone] = tone_scores.get(tone, 0) + 1
                    signals.append(f"{tone.value}:{pattern.pattern}")
                    # DO NOT break here - count all signals for intensity calculation

        # Выбираем доминирующий тон по приоритету
        primary_tone = self._select_primary_tone(detected_tones)

        # Определяем стиль
        style = self._detect_style(message_lower)

        # Get signal count for primary tone (for intensity-based calculation)
        primary_signal_count = tone_scores.get(primary_tone, 1)

        # Обновляем frustration tracker with signal count for intensity
        self._frustration_tracker.update(primary_tone, signal_count=primary_signal_count)

        # Расчёт confidence
        if signals:
            confidence = min(
                self.BASE_CONFIDENCE + len(signals) * self.SIGNAL_BOOST,
                self.MAX_CONFIDENCE
            )
        else:
            confidence = self.NO_SIGNAL_CONFIDENCE

        latency_ms = (time.perf_counter() - start_time) * 1000

        # Get intensity-based information from tracker
        pre_intervention = self._frustration_tracker.pre_intervention_triggered
        urgency = self._frustration_tracker.get_intervention_urgency()
        should_exit = self._frustration_tracker.should_offer_exit()
        consecutive_turns = self._frustration_tracker.consecutive_negative_turns

        result = ToneAnalysis(
            tone=primary_tone,
            style=style,
            confidence=confidence,
            frustration_level=self._frustration_tracker.level,
            signals=signals,
            tier_used="regex",
            tier_scores={t.value: s for t, s in tone_scores.items()},
            latency_ms=latency_ms,
            # Intensity-based fields
            signal_count=primary_signal_count,
            pre_intervention_triggered=pre_intervention,
            intervention_urgency=urgency,
            should_offer_exit=should_exit,
            consecutive_negative_turns=consecutive_turns,
        )

        # Логируем высокий frustration
        if self._frustration_tracker.is_warning():
            logger.warning(
                "Elevated frustration detected",
                frustration_level=self._frustration_tracker.level,
                tone=primary_tone.value,
                signals_count=len(signals)
            )

        if self._frustration_tracker.is_critical():
            logger.error(
                "Critical frustration level reached",
                frustration_level=self._frustration_tracker.level
            )

        return result

    def _select_primary_tone(self, detected_tones: List[Tone]) -> Tone:
        """
        Выбрать доминирующий тон по приоритету.

        Приоритет:
        1. FRUSTRATED - самый важный, нужно реагировать
        2. RUSHED - клиент торопится
        3. SKEPTICAL - сомневается
        4. CONFUSED - не понимает
        5. POSITIVE - позитивный
        6. INTERESTED - заинтересован
        7. NEUTRAL - по умолчанию
        """
        for tone in self.TONE_PRIORITY:
            if tone in detected_tones:
                return tone
        return Tone.NEUTRAL

    def _detect_style(self, message_lower: str) -> Style:
        """Определить стиль общения (formal/informal)."""
        informal_count = sum(
            1 for pattern in self._compiled_informal
            if pattern.search(message_lower)
        )

        # Если есть 2+ неформальных маркера — неформальный стиль
        if informal_count >= 2:
            return Style.INFORMAL

        # Или если есть 1 маркер и сообщение короткое
        if informal_count >= 1 and len(message_lower) < 50:
            return Style.INFORMAL

        return Style.FORMAL

    def get_response_guidance(self, analysis: ToneAnalysis) -> Dict:
        """
        Получить рекомендации для генерации ответа.

        Enhanced with intensity-based pre-intervention logic.

        Args:
            analysis: Результат анализа тона

        Returns:
            Словарь с рекомендациями
        """
        # Получаем style_instruction из конфига
        style_key = "informal" if analysis.style == Style.INFORMAL else "formal"
        style_instruction = settings.get_nested(
            f"tone_analyzer.style_instructions.{style_key}",
            default=""
        )

        guidance = {
            "max_words": 50,
            "tone_instruction": "",
            "style_instruction": style_instruction,
            "should_apologize": False,
            "should_offer_exit": False,
            "formality": "formal" if analysis.style == Style.FORMAL else "casual",
            # New intensity-based fields
            "intervention_urgency": analysis.intervention_urgency,
            "pre_intervention_triggered": analysis.pre_intervention_triggered,
        }

        # Use urgency-based guidance for consistency
        urgency = analysis.intervention_urgency

        # Critical urgency = immediate soft close
        if urgency == "critical":
            guidance["max_words"] = 20
            guidance["tone_instruction"] = (
                "Будь МАКСИМАЛЬНО кратким. Одно предложение. "
                "Извинись и предложи завершить разговор."
            )
            guidance["should_apologize"] = True
            guidance["should_offer_exit"] = True

        # High urgency = very short, offer exit
        elif urgency == "high":
            guidance["max_words"] = 25
            guidance["tone_instruction"] = (
                "Будь максимально кратким и по делу. "
                "Не задавай лишних вопросов. Извинись за неудобства."
            )
            guidance["should_apologize"] = True
            guidance["should_offer_exit"] = True

        # Medium urgency = short, empathetic
        elif urgency == "medium":
            guidance["max_words"] = 35
            if analysis.tone == Tone.SKEPTICAL:
                # Skepticism is not frustration. Facts, not apology.
                guidance["tone_instruction"] = (
                    "Будь кратким и деловым. "
                    "Приведи конкретные факты и цифры. "
                    "НЕ извиняйся — клиент задаёт деловые вопросы."
                )
                guidance["should_apologize"] = False
            else:
                guidance["tone_instruction"] = (
                    "Будь кратким и деловым. "
                    "Признай возможные неудобства."
                )
                # Only FRUSTRATED tone at medium urgency warrants apology flag.
                # RUSHED/CONFUSED = not bot-directed frustration.
                guidance["should_apologize"] = (analysis.tone == Tone.FRUSTRATED)
                # Offer exit for RUSHED users with medium urgency
                if analysis.tone == Tone.RUSHED:
                    guidance["should_offer_exit"] = True

        # Low urgency = slightly shorter
        elif urgency == "low":
            guidance["max_words"] = 45
            guidance["tone_instruction"] = (
                "Будь немного более кратким. "
                "Клиент может быть слегка раздражён."
            )

        # Pre-intervention triggered but no urgency match = RUSHED special case
        elif analysis.pre_intervention_triggered:
            # User said something like "быстрее, не тяни, некогда" (3 RUSHED signals)
            # but frustration level hasn't reached thresholds yet
            guidance["max_words"] = 30
            guidance["tone_instruction"] = (
                "Клиент торопится. Отвечай коротко, без воды и вступлений. "
                "Переходи к сути."
            )
            guidance["should_offer_exit"] = True
            logger.info(
                "Pre-intervention guidance applied",
                tone=analysis.tone.value,
                signal_count=analysis.signal_count,
                frustration=analysis.frustration_level,
            )

        # Fallback to threshold-based for backward compatibility
        # Критический frustration — минимальные ответы, предложить выход
        elif analysis.frustration_level >= FRUSTRATION_THRESHOLDS["critical"]:
            guidance["max_words"] = 20
            guidance["tone_instruction"] = (
                "Будь МАКСИМАЛЬНО кратким. Одно предложение. "
                "Извинись и предложи завершить разговор."
            )
            guidance["should_apologize"] = True
            guidance["should_offer_exit"] = True

        # Высокий frustration — короткие ответы, возможен выход
        elif analysis.frustration_level >= FRUSTRATION_THRESHOLDS["high"]:
            guidance["max_words"] = 30
            guidance["tone_instruction"] = (
                "Будь максимально кратким и по делу. "
                "Не задавай лишних вопросов. Извинись за неудобства."
            )
            guidance["should_apologize"] = True
            guidance["should_offer_exit"] = True

        # Повышенный frustration — сокращаем ответы
        elif analysis.frustration_level >= FRUSTRATION_THRESHOLDS["warning"]:
            guidance["max_words"] = 40
            if analysis.tone == Tone.SKEPTICAL:
                # Skepticism is not frustration. Facts, not apology.
                guidance["tone_instruction"] = (
                    "Будь кратким и деловым. "
                    "Приведи конкретные факты и цифры. "
                    "НЕ извиняйся — клиент задаёт деловые вопросы."
                )
                guidance["should_apologize"] = False
            else:
                guidance["tone_instruction"] = (
                    "Будь кратким и деловым. "
                    "Признай возможные неудобства."
                )
                # Only FRUSTRATED tone at medium urgency warrants apology flag.
                # RUSHED/CONFUSED = not bot-directed frustration.
                guidance["should_apologize"] = (analysis.tone == Tone.FRUSTRATED)

        # Специфика по тону (если frustration низкий)
        elif analysis.tone == Tone.RUSHED:
            # RUSHED users get shorter responses even at low frustration
            guidance["max_words"] = 30
            guidance["tone_instruction"] = (
                "Коротко и по делу, без вступлений и воды."
            )
            # Offer exit if multiple RUSHED signals (pre-intervention path)
            if analysis.signal_count >= 2:
                guidance["should_offer_exit"] = True

        elif analysis.tone == Tone.SKEPTICAL:
            guidance["tone_instruction"] = (
                "Приведи конкретные факты и цифры. "
                "Не используй общие фразы."
            )

        elif analysis.tone == Tone.CONFUSED:
            guidance["tone_instruction"] = (
                "Объясни просто и понятно. "
                "Используй короткие предложения и примеры."
            )

        elif analysis.tone == Tone.POSITIVE:
            guidance["max_words"] = 60
            guidance["tone_instruction"] = (
                "Можно быть чуть более разговорным. "
                "Поддержи позитивный настрой."
            )

        elif analysis.tone == Tone.INTERESTED:
            guidance["max_words"] = 60
            guidance["tone_instruction"] = (
                "Клиент заинтересован — дай полезную информацию. "
                "Можно быть подробнее."
            )

        return guidance

    def reset(self) -> None:
        """Сброс состояния для нового диалога."""
        # Сбрасываем frustration tracker только если владеем им
        if self._owns_frustration_tracker:
            self._frustration_tracker.reset()

    def get_frustration_level(self) -> int:
        """Получить текущий уровень frustration."""
        return self._frustration_tracker.level

    def is_frustrated(self) -> bool:
        """Проверка на повышенный frustration."""
        return self._frustration_tracker.is_warning()

    def is_critically_frustrated(self) -> bool:
        """Проверка на критический frustration."""
        return self._frustration_tracker.is_critical()

    def get_frustration_history(self) -> List[Dict]:
        """Получить историю изменения frustration."""
        return self._frustration_tracker.history

    @property
    def frustration_tracker(self) -> FrustrationTracker:
        """Доступ к трекеру frustration."""
        return self._frustration_tracker
