"""
Adaptive Style Selector — выбор стиля коммуникации на основе поведенческих сигналов.

На основе исследований:
- Adaptive Response Generation: адаптация длины/тона под engagement
- Empathetic Responses: адаптация эмпатии под frustration level
- Contextual Bandits: выбор оптимальной стратегии на основе feedback
"""

from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass

from src.personalization.result import StyleParameters


@dataclass
class BehavioralSignals:
    """
    Поведенческие сигналы из ContextEnvelope.

    Упрощённая структура для передачи в StyleSelector.
    """

    # === Engagement ===
    engagement_level: str = "medium"  # "high" | "medium" | "low" | "disengaged"
    engagement_score: float = 0.5  # 0-1
    engagement_trend: str = "stable"  # "improving" | "declining" | "stable"

    # === Momentum ===
    momentum: float = 0.0  # -1 to +1
    momentum_direction: str = "neutral"  # "positive" | "negative" | "neutral"
    is_progressing: bool = False
    is_regressing: bool = False

    # === Frustration ===
    frustration_level: int = 0  # 0-10

    # === Breakthrough ===
    has_breakthrough: bool = False
    turns_since_breakthrough: Optional[int] = None

    # === Patterns ===
    is_stuck: bool = False
    has_oscillation: bool = False

    @classmethod
    def from_envelope(cls, envelope) -> "BehavioralSignals":
        """
        Создать из ContextEnvelope.

        Args:
            envelope: ContextEnvelope instance

        Returns:
            BehavioralSignals
        """
        return cls(
            engagement_level=getattr(envelope, "engagement_level", "medium"),
            engagement_score=getattr(envelope, "engagement_score", 0.5),
            engagement_trend=getattr(envelope, "engagement_trend", "stable"),
            momentum=getattr(envelope, "momentum", 0.0),
            momentum_direction=getattr(envelope, "momentum_direction", "neutral"),
            is_progressing=getattr(envelope, "is_progressing", False),
            is_regressing=getattr(envelope, "is_regressing", False),
            frustration_level=getattr(envelope, "frustration_level", 0),
            has_breakthrough=getattr(envelope, "has_breakthrough", False),
            turns_since_breakthrough=getattr(envelope, "turns_since_breakthrough", None),
            is_stuck=getattr(envelope, "is_stuck", False),
            has_oscillation=getattr(envelope, "has_oscillation", False),
        )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BehavioralSignals":
        """Создать из словаря."""
        return cls(
            engagement_level=data.get("engagement_level", "medium"),
            engagement_score=data.get("engagement_score", 0.5),
            engagement_trend=data.get("engagement_trend", "stable"),
            momentum=data.get("momentum", 0.0),
            momentum_direction=data.get("momentum_direction", "neutral"),
            is_progressing=data.get("is_progressing", False),
            is_regressing=data.get("is_regressing", False),
            frustration_level=data.get("frustration_level", 0),
            has_breakthrough=data.get("has_breakthrough", False),
            turns_since_breakthrough=data.get("turns_since_breakthrough"),
            is_stuck=data.get("is_stuck", False),
            has_oscillation=data.get("has_oscillation", False),
        )


class AdaptiveStyleSelector:
    """
    Выбирает стиль коммуникации на основе поведенческих сигналов.

    Правила адаптации:

    | Сигнал              | Значение    | Адаптация                            |
    |---------------------|-------------|--------------------------------------|
    | engagement HIGH     | >0.7        | verbosity=normal, cta=direct         |
    | engagement LOW      | <0.3        | verbosity=concise, cta=none          |
    | momentum positive   | >0.3        | pitch=assertive, question=leading    |
    | momentum negative   | <-0.3       | pitch=soft, question=closed          |
    | frustration 4-6     | warning     | empathy=high, acknowledge frustration|
    | frustration 7+      | critical    | empathy=high, offer exit             |
    | breakthrough        | recent      | cta=direct, capitalize opportunity   |
    | stuck               | True        | offer_choices, simplify              |
    """

    # === Engagement → Style mapping ===
    ENGAGEMENT_STYLES: Dict[str, Dict[str, str]] = {
        "high": {
            "verbosity": "normal",
            "pitch_intensity": "assertive",
            "cta_approach": "direct",
            "question_style": "leading",
        },
        "medium": {
            "verbosity": "normal",
            "pitch_intensity": "normal",
            "cta_approach": "soft",
            "question_style": "open",
        },
        "low": {
            "verbosity": "concise",
            "pitch_intensity": "soft",
            "cta_approach": "none",
            "question_style": "closed",
        },
        "disengaged": {
            "verbosity": "concise",
            "pitch_intensity": "soft",
            "cta_approach": "none",
            "question_style": "closed",
        },
    }

    # === Momentum → Tactical adjustments ===
    MOMENTUM_TACTICS: Dict[str, Dict[str, str]] = {
        "positive": {
            "question_style": "leading",
            "pitch_intensity": "assertive",
            "tactical_instruction": "Momentum положительный — предложи следующий шаг.",
        },
        "neutral": {
            "question_style": "open",
            "pitch_intensity": "normal",
            "tactical_instruction": "",
        },
        "negative": {
            "question_style": "closed",
            "pitch_intensity": "soft",
            "tactical_instruction": "Momentum отрицательный — упрости, признай опасения.",
        },
    }

    # === Frustration thresholds and responses ===
    FRUSTRATION_THRESHOLDS: list[Tuple[Tuple[int, int], Dict[str, Any]]] = [
        # (min, max), adjustments
        (
            (0, 3),
            {
                "empathy_level": "medium",
                "formality": "professional",
                "style_instruction": "",
            },
        ),
        (
            (4, 6),
            {
                "empathy_level": "high",
                "formality": "professional",
                "style_instruction": "Клиент проявляет нетерпение — признай ситуацию, будь терпелив.",
            },
        ),
        (
            (7, 10),
            {
                "empathy_level": "high",
                "formality": "formal",
                "verbosity": "concise",
                "style_instruction": "Клиент раздражён — извинись если уместно, предложи помощь или завершение.",
            },
        ),
    ]

    # === Breakthrough window ===
    BREAKTHROUGH_WINDOW = 3  # Turns after breakthrough for CTA opportunity

    def select_style(self, signals: BehavioralSignals) -> StyleParameters:
        """
        Выбрать стиль на основе поведенческих сигналов.

        Args:
            signals: BehavioralSignals с данными из ContextEnvelope

        Returns:
            StyleParameters с выбранным стилем
        """
        # Start with engagement-based defaults
        base = self._get_engagement_style(signals.engagement_level)

        # Apply momentum adjustments
        momentum_adj = self._get_momentum_adjustments(signals.momentum_direction)

        # Apply frustration-based empathy
        frustration_adj = self._get_frustration_adjustments(signals.frustration_level)

        # Check for special conditions
        special_adj = self._get_special_adjustments(signals)

        # Merge all adjustments
        return self._merge_style_params(base, momentum_adj, frustration_adj, special_adj)

    def _get_engagement_style(self, engagement_level: str) -> Dict[str, str]:
        """Get base style from engagement level."""
        return self.ENGAGEMENT_STYLES.get(
            engagement_level, self.ENGAGEMENT_STYLES["medium"]
        ).copy()

    def _get_momentum_adjustments(self, momentum_direction: str) -> Dict[str, str]:
        """Get tactical adjustments from momentum."""
        return self.MOMENTUM_TACTICS.get(
            momentum_direction, self.MOMENTUM_TACTICS["neutral"]
        ).copy()

    def _get_frustration_adjustments(self, frustration_level: int) -> Dict[str, Any]:
        """Get empathy/formality adjustments from frustration level."""
        for (min_level, max_level), adjustments in self.FRUSTRATION_THRESHOLDS:
            if min_level <= frustration_level <= max_level:
                return adjustments.copy()
        return {}

    def _get_special_adjustments(self, signals: BehavioralSignals) -> Dict[str, Any]:
        """Get adjustments for special conditions."""
        adjustments: Dict[str, Any] = {}

        # Breakthrough window - opportunity for CTA
        if signals.has_breakthrough:
            if (
                signals.turns_since_breakthrough is not None
                and signals.turns_since_breakthrough <= self.BREAKTHROUGH_WINDOW
            ):
                adjustments["cta_approach"] = "direct"
                adjustments["pitch_intensity"] = "assertive"
                if not adjustments.get("tactical_instruction"):
                    adjustments["tactical_instruction"] = (
                        "Недавний прорыв — хороший момент для CTA."
                    )

        # Stuck - offer choices
        if signals.is_stuck:
            adjustments["question_style"] = "closed"
            adjustments["style_instruction"] = (
                adjustments.get("style_instruction", "")
                + " Клиент застрял — предложи 2-3 конкретных варианта."
            ).strip()

        # Oscillation - client is uncertain
        if signals.has_oscillation:
            adjustments["pitch_intensity"] = "soft"
            adjustments["empathy_level"] = "high"
            if not adjustments.get("style_instruction"):
                adjustments["style_instruction"] = (
                    "Клиент колеблется — не дави, дай время подумать."
                )

        # Declining engagement - need to simplify
        if signals.engagement_trend == "declining":
            adjustments["verbosity"] = "concise"
            if not adjustments.get("tactical_instruction"):
                adjustments["tactical_instruction"] = (
                    "Engagement падает — сократи ответ, упрости."
                )

        return adjustments

    def _merge_style_params(
        self,
        base: Dict[str, str],
        momentum: Dict[str, str],
        frustration: Dict[str, Any],
        special: Dict[str, Any],
    ) -> StyleParameters:
        """
        Merge all adjustments into final StyleParameters.

        Priority: special > frustration > momentum > base
        """
        # Start with defaults
        params = StyleParameters()

        # Apply in order of priority (lowest first)
        for adj in [base, momentum, frustration, special]:
            for key, value in adj.items():
                if value and hasattr(params, key):
                    setattr(params, key, value)

        # Combine instructions
        instructions = []
        if frustration.get("style_instruction"):
            instructions.append(frustration["style_instruction"])
        if special.get("style_instruction"):
            instructions.append(special["style_instruction"])
        params.style_instruction = " ".join(instructions) if instructions else ""

        # Combine tactical instructions
        tactical = []
        if momentum.get("tactical_instruction"):
            tactical.append(momentum["tactical_instruction"])
        if special.get("tactical_instruction"):
            tactical.append(special["tactical_instruction"])
        params.tactical_instruction = " ".join(tactical) if tactical else ""

        return params

    def select_style_from_envelope(self, envelope) -> StyleParameters:
        """
        Convenience method to select style directly from ContextEnvelope.

        Args:
            envelope: ContextEnvelope instance

        Returns:
            StyleParameters
        """
        signals = BehavioralSignals.from_envelope(envelope)
        return self.select_style(signals)

    def select_style_from_dict(self, data: Dict[str, Any]) -> StyleParameters:
        """
        Convenience method to select style from dictionary.

        Args:
            data: Dictionary with behavioral signals

        Returns:
            StyleParameters
        """
        signals = BehavioralSignals.from_dict(data)
        return self.select_style(signals)
