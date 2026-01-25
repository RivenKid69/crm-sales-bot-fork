"""
Трекер накопительного уровня frustration.

Отслеживает изменение frustration в течение диалога:
- Негативные тона увеличивают frustration
- Позитивные/нейтральные тона снижают (decay)

Enhanced with intensity-based calculation:
- Multiple signals of same tone = higher weight
- Consecutive turns with negative tone = faster escalation
- Pre-intervention at WARNING level for RUSHED users

Part of Frustration System Unification (fixing guard intervention bug).
"""

from typing import Dict, List, Optional
import logging

from .models import Tone
from .markers import (
    FRUSTRATION_WEIGHTS,
    FRUSTRATION_DECAY,
    FRUSTRATION_THRESHOLDS,
    MAX_FRUSTRATION,
)

logger = logging.getLogger(__name__)


class FrustrationTracker:
    """
    Трекер накопительного frustration.

    Особенности:
    - Frustration накапливается от негативных тонов
    - Frustration снижается от позитивных тонов (decay)
    - Уровень ограничен [0, MAX_FRUSTRATION]
    - Сохраняет историю изменений
    - Enhanced: Intensity-based calculation for multiple signals

    Intensity Enhancement:
    - Multiple signals of same tone = higher weight
    - "быстрее, не тяни, некогда" (3 RUSHED signals) = base * 2.0 multiplier
    - Consecutive negative turns = 1.2x escalation
    """

    def __init__(self):
        self._level: int = 0
        self._history: List[Dict] = []
        self._consecutive_negative_turns: int = 0
        self._last_tone: Optional[Tone] = None
        self._intensity_calculator = None  # Lazy load to avoid circular imports
        self._pre_intervention_triggered: bool = False

    @property
    def level(self) -> int:
        """Текущий уровень frustration (0-10)."""
        return self._level

    @property
    def history(self) -> List[Dict]:
        """История изменений frustration."""
        return self._history.copy()

    @property
    def pre_intervention_triggered(self) -> bool:
        """Whether pre-intervention has been triggered."""
        return self._pre_intervention_triggered

    @property
    def consecutive_negative_turns(self) -> int:
        """Number of consecutive turns with negative tone."""
        return self._consecutive_negative_turns

    def _get_intensity_calculator(self):
        """Lazy load intensity calculator to avoid circular imports."""
        if self._intensity_calculator is None:
            try:
                from .frustration_intensity import FrustrationIntensityCalculator
                self._intensity_calculator = FrustrationIntensityCalculator()
            except ImportError:
                logger.warning("FrustrationIntensityCalculator not available")
                self._intensity_calculator = None
        return self._intensity_calculator

    def update(self, tone: Tone, signal_count: int = 1) -> int:
        """
        Обновить frustration на основе тона.

        Args:
            tone: Обнаруженный тон сообщения
            signal_count: Количество сигналов (default: 1 for backward compatibility)

        Returns:
            Новый уровень frustration
        """
        # Use intensity-based calculation if available and signal_count > 1
        calculator = self._get_intensity_calculator()
        if calculator is not None and signal_count > 1:
            return self.update_with_intensity(tone, signal_count)

        # Original logic for backward compatibility
        old_level = self._level

        # Track consecutive negative turns
        negative_tones = {Tone.FRUSTRATED, Tone.RUSHED, Tone.SKEPTICAL, Tone.CONFUSED}
        if tone in negative_tones:
            if self._last_tone in negative_tones:
                self._consecutive_negative_turns += 1
            else:
                self._consecutive_negative_turns = 1
        else:
            self._consecutive_negative_turns = 0
        self._last_tone = tone

        # Увеличение frustration
        if tone in FRUSTRATION_WEIGHTS:
            weight = FRUSTRATION_WEIGHTS[tone]
            self._level = min(MAX_FRUSTRATION, self._level + weight)

        # Снижение frustration (decay)
        elif tone in FRUSTRATION_DECAY:
            decay = FRUSTRATION_DECAY[tone]
            self._level = max(0, self._level - decay)

        # Сохраняем историю только если уровень изменился
        # (избегаем засорения нулевыми записями для нейтральных тонов)
        delta = self._level - old_level
        if delta != 0:
            self._history.append({
                "tone": tone.value,
                "old_level": old_level,
                "new_level": self._level,
                "delta": delta,
                "signal_count": signal_count,
            })

        return self._level

    def update_with_intensity(self, tone: Tone, signal_count: int) -> int:
        """
        Update frustration using intensity-based calculation.

        This method calculates frustration delta based on:
        - Tone type
        - Signal count (intensity)
        - Consecutive turns with negative tone

        Args:
            tone: Detected tone
            signal_count: Number of signals detected for this tone

        Returns:
            New frustration level
        """
        calculator = self._get_intensity_calculator()
        if calculator is None:
            # Fallback to standard update
            return self.update(tone, signal_count=1)

        old_level = self._level

        # Track consecutive negative turns
        negative_tones = {Tone.FRUSTRATED, Tone.RUSHED, Tone.SKEPTICAL, Tone.CONFUSED}
        if tone in negative_tones:
            if self._last_tone in negative_tones:
                self._consecutive_negative_turns += 1
            else:
                self._consecutive_negative_turns = 1
        else:
            self._consecutive_negative_turns = 0
        self._last_tone = tone

        # Calculate delta using intensity calculator
        delta = calculator.calculate(
            tone=tone,
            signal_count=signal_count,
            consecutive_turns=self._consecutive_negative_turns,
        )

        # Apply delta
        self._level = max(0, min(MAX_FRUSTRATION, self._level + delta))

        # Check for pre-intervention
        if calculator.should_pre_intervene(tone, signal_count, self._level):
            self._pre_intervention_triggered = True
            logger.info(
                "Pre-intervention triggered",
                tone=tone.value,
                signal_count=signal_count,
                frustration_level=self._level,
            )

        # Record history
        actual_delta = self._level - old_level
        if actual_delta != 0:
            urgency = calculator.get_intervention_urgency(tone, signal_count, self._level)
            self._history.append({
                "tone": tone.value,
                "old_level": old_level,
                "new_level": self._level,
                "delta": actual_delta,
                "signal_count": signal_count,
                "intensity_based": True,
                "consecutive_turns": self._consecutive_negative_turns,
                "urgency": urgency,
            })

        return self._level

    def get_intervention_urgency(self) -> str:
        """
        Get current intervention urgency level.

        Returns:
            Urgency level: "none", "low", "medium", "high", "critical"
        """
        calculator = self._get_intensity_calculator()
        if calculator is None:
            # Fallback to threshold-based urgency
            if self.is_critical():
                return "critical"
            elif self.is_high():
                return "high"
            elif self.is_warning():
                return "medium"
            else:
                return "none"

        # Use last tone and signal count from history
        last_entry = self._history[-1] if self._history else None
        if last_entry:
            tone = Tone(last_entry["tone"])
            signal_count = last_entry.get("signal_count", 1)
            return calculator.get_intervention_urgency(tone, signal_count, self._level)
        return "none"

    def should_offer_exit(self) -> bool:
        """
        Check if exit should be offered to user.

        Exit is offered when:
        - Pre-intervention triggered (RUSHED with high intensity)
        - OR high frustration level
        """
        return self._pre_intervention_triggered or self.is_high()

    def reset(self) -> None:
        """Сброс состояния для нового диалога."""
        self._level = 0
        self._history = []
        self._consecutive_negative_turns = 0
        self._last_tone = None
        self._pre_intervention_triggered = False

    def is_warning(self) -> bool:
        """Достигнут ли порог предупреждения (elevated frustration)."""
        return self._level >= FRUSTRATION_THRESHOLDS["warning"]

    def is_high(self) -> bool:
        """Достигнут ли высокий уровень frustration."""
        return self._level >= FRUSTRATION_THRESHOLDS["high"]

    def is_critical(self) -> bool:
        """Достигнут ли критический уровень frustration."""
        return self._level >= FRUSTRATION_THRESHOLDS["critical"]

    def get_threshold(self, name: str) -> int:
        """Получить значение порога по имени."""
        return FRUSTRATION_THRESHOLDS.get(name, 0)

    def set_level(self, level: int) -> None:
        """
        Установить уровень напрямую.

        Используется для синхронизации с внешними системами.
        """
        self._level = max(0, min(MAX_FRUSTRATION, level))
