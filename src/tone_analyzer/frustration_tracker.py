"""
Трекер накопительного уровня frustration.

Отслеживает изменение frustration в течение диалога:
- Негативные тона увеличивают frustration
- Позитивные/нейтральные тона снижают (decay)
"""

from typing import Dict, List

from .models import Tone
from .markers import (
    FRUSTRATION_WEIGHTS,
    FRUSTRATION_DECAY,
    FRUSTRATION_THRESHOLDS,
    MAX_FRUSTRATION,
)


class FrustrationTracker:
    """
    Трекер накопительного frustration.

    Особенности:
    - Frustration накапливается от негативных тонов
    - Frustration снижается от позитивных тонов (decay)
    - Уровень ограничен [0, MAX_FRUSTRATION]
    - Сохраняет историю изменений
    """

    def __init__(self):
        self._level: int = 0
        self._history: List[Dict] = []

    @property
    def level(self) -> int:
        """Текущий уровень frustration (0-10)."""
        return self._level

    @property
    def history(self) -> List[Dict]:
        """История изменений frustration."""
        return self._history.copy()

    def update(self, tone: Tone) -> int:
        """
        Обновить frustration на основе тона.

        Args:
            tone: Обнаруженный тон сообщения

        Returns:
            Новый уровень frustration
        """
        old_level = self._level

        # Увеличение frustration
        if tone in FRUSTRATION_WEIGHTS:
            weight = FRUSTRATION_WEIGHTS[tone]
            self._level = min(MAX_FRUSTRATION, self._level + weight)

        # Снижение frustration (decay)
        elif tone in FRUSTRATION_DECAY:
            decay = FRUSTRATION_DECAY[tone]
            self._level = max(0, self._level - decay)

        # Сохраняем историю
        self._history.append({
            "tone": tone.value,
            "old_level": old_level,
            "new_level": self._level,
            "delta": self._level - old_level,
        })

        return self._level

    def reset(self) -> None:
        """Сброс состояния для нового диалога."""
        self._level = 0
        self._history = []

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
