"""Pydantic schemas for structured LLM output."""

from typing import List, Literal, Optional
from pydantic import BaseModel, Field, field_validator

# Category types from crm_sales_bot
CategoryType = Literal[
    "analytics",
    "competitors",
    "employees",
    "equipment",
    "faq",
    "features",
    "fiscal",
    "integrations",
    "inventory",
    "mobile",
    "pricing",
    "products",
    "promotions",
    "regions",
    "stability",
    "support",
    "tis",
]


class ExtractedKeywordsRaw(BaseModel):
    """Raw keywords extracted from text (first LLM pass)."""

    primary_keywords: List[str] = Field(
        ...,
        min_length=3,
        max_length=15,
        description="Основные ключевые слова из текста (существительные, глаголы, термины)",
    )
    synonyms: List[str] = Field(
        default_factory=list,
        max_length=10,
        description="Синонимы основных слов (цена → стоимость, прайс)",
    )
    question_phrases: List[str] = Field(
        default_factory=list,
        max_length=10,
        description="Вопросительные фразы (сколько стоит, как работает, можно ли)",
    )


class KeywordExpansion(BaseModel):
    """Expanded keywords with variations."""

    base_keyword: str = Field(..., description="Исходное слово")

    morphological: List[str] = Field(
        default_factory=list,
        description="Морфологические формы (тариф → тарифы, тарифа, тарифом)",
    )
    typos: List[str] = Field(
        default_factory=list,
        description="Опечатки (скока, сколко, праис, безплатно)",
    )
    colloquial: List[str] = Field(
        default_factory=list,
        description="Разговорные формы (бесплатно → халява, даром)",
    )
    transliteration: List[str] = Field(
        default_factory=list,
        description="Транслитерация (price ↔ прайс, free ↔ фри)",
    )


class CategoryClassification(BaseModel):
    """Category classification result."""

    primary_category: CategoryType = Field(
        ...,
        description="Основная категория контента",
    )
    secondary_categories: List[CategoryType] = Field(
        default_factory=list,
        max_length=2,
        description="Дополнительные категории (0-2)",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Уверенность в классификации",
    )


class ExtractedFacts(BaseModel):
    """Extracted facts from chunk."""

    facts_markdown: str = Field(
        ...,
        min_length=50,
        max_length=3000,
        description="Структурированные факты в markdown",
    )
    topic_suggestion: str = Field(
        ...,
        min_length=3,
        max_length=50,
        description="Предложение для topic ID (snake_case)",
    )
    priority: int = Field(
        ...,
        ge=7,
        le=10,
        description="Приоритет (10=критичное, 7=дополнительное)",
    )


class ExtractedSection(BaseModel):
    """Complete knowledge section for output."""

    topic: str = Field(
        ...,
        min_length=3,
        max_length=60,
        pattern=r"^[a-z][a-z0-9_]*$",
        description="Уникальный идентификатор (snake_case, латиница)",
    )

    priority: int = Field(
        ...,
        ge=7,
        le=10,
        description="Приоритет секции (7-10, выше = важнее)",
    )

    category: CategoryType = Field(
        ...,
        description="Категория для роутинга в файл",
    )

    keywords: List[str] = Field(
        ...,
        min_length=20,
        max_length=50,
        description="Ключевые слова с вариациями (20-50 штук)",
    )

    facts: str = Field(
        ...,
        min_length=50,
        description="Markdown-форматированные факты",
    )

    @field_validator("keywords")
    @classmethod
    def validate_keywords(cls, v: List[str]) -> List[str]:
        """Ensure keywords are unique and lowercase."""
        cleaned = []
        seen = set()
        for kw in v:
            kw_clean = kw.strip().lower()
            if kw_clean and kw_clean not in seen:
                cleaned.append(kw_clean)
                seen.add(kw_clean)
        return cleaned

    @field_validator("facts")
    @classmethod
    def validate_facts(cls, v: str) -> str:
        """Ensure facts are self-contained (no references to other sections)."""
        forbidden = ["см. выше", "см. ниже", "как указано", "в предыдущем", "в следующем"]
        v_lower = v.lower()
        for phrase in forbidden:
            if phrase in v_lower:
                raise ValueError(f"Facts содержат ссылку: '{phrase}'")
        return v.strip()

    @field_validator("topic")
    @classmethod
    def validate_topic(cls, v: str) -> str:
        """Ensure topic is valid snake_case."""
        return v.lower().strip()


class QualityAssessment(BaseModel):
    """Quality assessment of a section."""

    keywords_quality: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Качество keywords (покрытие, разнообразие)",
    )
    facts_quality: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Качество facts (полнота, структура)",
    )
    completeness: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Полнота информации",
    )
    issues: List[str] = Field(
        default_factory=list,
        description="Найденные проблемы",
    )
    suggestions: List[str] = Field(
        default_factory=list,
        description="Предложения по улучшению",
    )

    @property
    def overall_score(self) -> float:
        """Calculate overall quality score."""
        return (self.keywords_quality + self.facts_quality + self.completeness) / 3

    @property
    def is_acceptable(self) -> bool:
        """Check if quality is acceptable."""
        return self.overall_score >= 0.7 and len(self.issues) == 0


class FullExtractionResult(BaseModel):
    """Complete extraction result from LLM."""

    topic: str = Field(
        ...,
        description="Topic ID в формате snake_case",
    )
    priority: int = Field(
        ...,
        ge=7,
        le=10,
        description="Приоритет 7-10",
    )
    category: CategoryType = Field(
        ...,
        description="Категория",
    )
    primary_keywords: List[str] = Field(
        ...,
        min_length=5,
        max_length=15,
        description="Основные ключевые слова",
    )
    synonyms: List[str] = Field(
        default_factory=list,
        description="Синонимы",
    )
    question_phrases: List[str] = Field(
        default_factory=list,
        description="Вопросительные фразы",
    )
    facts: str = Field(
        ...,
        min_length=50,
        description="Факты в markdown",
    )
