"""
Модели данных для анализатора тона.

Содержит:
- Tone: Enum типов эмоционального тона
- Style: Enum стилей общения
- ToneAnalysis: Результат анализа тона
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class Tone(Enum):
    """Типы эмоционального тона."""
    NEUTRAL = "neutral"         # Нейтральный
    POSITIVE = "positive"       # Позитивный
    FRUSTRATED = "frustrated"   # Раздражён
    SKEPTICAL = "skeptical"     # Сомневается
    RUSHED = "rushed"           # Торопится
    CONFUSED = "confused"       # Не понимает
    INTERESTED = "interested"   # Заинтересован


class Style(Enum):
    """Стиль общения."""
    FORMAL = "formal"       # Формальный
    INFORMAL = "informal"   # Неформальный


@dataclass
class ToneAnalysis:
    """Результат анализа тона."""
    tone: Tone                          # Основной тон сообщения
    style: Style                        # Стиль общения
    confidence: float                   # Уверенность в определении (0-1)
    frustration_level: int              # Накопительный уровень frustration (0-10)
    signals: List[str] = field(default_factory=list)  # Обнаруженные сигналы
    tier_used: str = "regex"            # Какой tier использовался: "regex" | "semantic" | "llm"
    tier_scores: Dict[str, float] = field(default_factory=dict)  # Scores от разных tiers
    latency_ms: float = 0.0             # Время анализа в мс
