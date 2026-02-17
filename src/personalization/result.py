"""
Personalization Result — результаты персонализации для генератора.

PersonalizationEngine v2: Адаптивная персонализация на основе поведенческих сигналов.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional


@dataclass
class StyleParameters:
    """
    Параметры стиля коммуникации, выбранные AdaptiveStyleSelector.

    На основе исследований:
    - Adaptive Response Generation (длина/тон → engagement)
    - Empathetic Responses (эмпатия → frustration level)
    """

    # === Базовый стиль ===
    verbosity: str = "normal"  # "concise" | "normal" | "detailed"
    formality: str = "professional"  # "casual" | "professional" | "formal"
    empathy_level: str = "medium"  # "low" | "medium" | "high"

    # === Тактические параметры ===
    pitch_intensity: str = "normal"  # "soft" | "normal" | "assertive"
    question_style: str = "open"  # "open" | "closed" | "leading"
    cta_approach: str = "soft"  # "none" | "soft" | "direct"

    # === Инструкции для генератора ===
    style_instruction: str = ""  # Основная инструкция стиля
    tactical_instruction: str = ""  # Тактическая рекомендация

    # === Style modifier tracking (for style/semantic separation) ===
    applied_modifiers: List[str] = field(default_factory=list)
    modifier_source: str = "behavioral"  # "behavioral"|"classification"|"mixed"|"secondary"

    def to_instruction(self) -> str:
        """Сформировать полную инструкцию для промпта."""
        parts = []

        # Стиль
        if self.style_instruction:
            parts.append(self.style_instruction)

        # Тактика
        if self.tactical_instruction:
            parts.append(self.tactical_instruction)

        # Дополнительные указания по verbosity
        verbosity_hints = {
            "concise": "Будь краток, максимум 2 предложения.",
            "detailed": "Можно дать развёрнутый ответ с примерами.",
        }
        if self.verbosity in verbosity_hints:
            parts.append(verbosity_hints[self.verbosity])

        # Эмпатия
        empathy_hints = {
            "high": "Признай ситуацию клиента, покажи понимание.",
        }
        if self.empathy_level in empathy_hints:
            parts.append(empathy_hints[self.empathy_level])

        return " ".join(parts) if parts else ""


@dataclass
class IndustryContext:
    """Контекст отрасли клиента."""

    industry: Optional[str] = None  # "retail", "services", "horeca", etc.
    confidence: float = 0.0  # 0-1
    method: str = "unknown"  # "keyword" | "semantic" | "llm"

    # === Контент для отрасли ===
    keywords: List[str] = field(default_factory=list)
    examples: List[str] = field(default_factory=list)
    pain_examples: List[str] = field(default_factory=list)

    def to_prompt_variables(self) -> Dict[str, str]:
        """Конвертировать в переменные для промпта (ic_* prefix)."""
        return {
            "industry": self.industry or "не определена",
            "industry_confidence": f"{int(self.confidence * 100)}",
            "ic_keywords": ", ".join(self.keywords) if self.keywords else "",
            "ic_examples": ", ".join(self.examples) if self.examples else "",
            "ic_pain_examples": ", ".join(self.pain_examples) if self.pain_examples else "",
        }


@dataclass
class BusinessContext:
    """Контекст по размеру бизнеса клиента."""

    size_category: str = "small"  # "micro" | "small" | "medium" | "large"
    company_size: int = 0

    # === Контент для размера ===
    size_label: str = ""  # "небольшая команда", "растущая команда", etc.
    pain_focus: str = ""  # Фокус боли для этого размера
    value_prop: str = ""  # Ценностное предложение
    objection_counter: str = ""  # Контраргумент по цене
    demo_pitch: str = ""  # Pitch для демо

    def to_prompt_variables(self) -> Dict[str, str]:
        """Конвертировать в переменные для промпта (bc_* prefix)."""
        return {
            "size_category": self.size_category,
            "bc_size_label": self.size_label or self.size_category,
            "bc_pain_focus": self.pain_focus,
            "bc_value_prop": self.value_prop,
            "bc_objection_counter": self.objection_counter,
            "bc_demo_pitch": self.demo_pitch,
        }


@dataclass
class PersonalizationResult:
    """
    Результат персонализации для передачи в генератор.

    Объединяет:
    - StyleParameters (адаптивный стиль)
    - IndustryContext (контекст отрасли)
    - BusinessContext (контекст по размеру)
    - Tactical hints (из session memory)
    """

    style: StyleParameters = field(default_factory=StyleParameters)
    industry_context: IndustryContext = field(default_factory=IndustryContext)
    business_context: BusinessContext = field(default_factory=BusinessContext)

    # === Session Memory ===
    effective_actions: List[str] = field(default_factory=list)
    ineffective_actions: List[str] = field(default_factory=list)
    effective_actions_hint: str = ""

    # === Pain Reference ===
    pain_reference: str = ""  # "Вы упоминали про потерю клиентов"
    has_pain_point: bool = False

    # === Meta ===
    personalization_applied: bool = False  # Была ли применена персонализация

    def to_prompt_variables(self) -> Dict[str, str]:
        """
        Конвертировать весь результат в переменные для format().

        Returns:
            Словарь переменных для подстановки в промпт
        """
        variables: Dict[str, str] = {}

        # Style instructions
        variables["adaptive_style_instruction"] = self.style.style_instruction
        variables["adaptive_tactical_instruction"] = self.style.tactical_instruction
        variables["style_full_instruction"] = self.style.to_instruction()

        # Industry context (ic_*)
        variables.update(self.industry_context.to_prompt_variables())

        # Business context (bc_*)
        variables.update(self.business_context.to_prompt_variables())

        # Effective actions hint
        variables["effective_actions_hint"] = self.effective_actions_hint

        # Pain reference
        variables["pain_reference"] = self.pain_reference

        # Convenience: combined personalization block
        variables["personalization_block"] = self._build_personalization_block()

        # Style modifier tracking (for debugging/logging)
        if self.style.applied_modifiers:
            variables["applied_style_modifiers"] = ", ".join(self.style.applied_modifiers)

        return variables

    def _build_personalization_block(self) -> str:
        """Собрать блок персонализации для промпта."""
        parts = []

        # Style instruction
        style_instr = self.style.to_instruction()
        if style_instr:
            parts.append(f"Стиль: {style_instr}")

        # Industry
        if self.industry_context.industry and self.industry_context.confidence > 0.5:
            parts.append(f"Отрасль: {self.industry_context.industry}")
            if self.industry_context.pain_examples:
                examples = ", ".join(self.industry_context.pain_examples[:3])
                parts.append(f"Типичные боли: {examples}")

        # Business size
        if self.business_context.size_label:
            parts.append(f"Размер: {self.business_context.size_label}")

        # Effective actions
        if self.effective_actions_hint:
            parts.append(self.effective_actions_hint)

        return "\n".join(parts) if parts else ""

    def merge_with_legacy(self, legacy_vars: Dict[str, Any]) -> Dict[str, str]:
        """
        Объединить с legacy переменными из старого PersonalizationEngine.

        Args:
            legacy_vars: Переменные из v1 PersonalizationEngine

        Returns:
            Объединённый словарь (v2 имеет приоритет)
        """
        # Начинаем с legacy
        result = {k: str(v) if v is not None else "" for k, v in legacy_vars.items()}

        # Перезаписываем v2 переменными
        v2_vars = self.to_prompt_variables()
        for key, value in v2_vars.items():
            if value:  # Только непустые значения
                result[key] = value

        return result
