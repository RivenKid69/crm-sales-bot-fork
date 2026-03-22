"""Pydantic schemas для LLM классификатора."""
from typing import Optional, Literal, List, get_args
from pydantic import BaseModel, ConfigDict, Field, field_validator

# 224 интента для CRM Sales Bot Wipon
IntentType = Literal[
    "greeting",
    "situation_provided",
    "question_specific_product",
    "question_features",
    "question_security",
    "price_question",
    "info_provided",
    "contact_provided",
    "comparison",
    "agreement",
    "question_integrations",
    "consultation_request",
    "pricing_details",
    "rejection",
    "question_customization",
    "no_problem",
    "objection_price",
    "objection_think",
    "clarification_request",
    "objection_security",
    "request_sla",
    "demo_request",
    "objection_trust",
    "objection_competitor",
    "objection_no_time",
    "need_expressed",
    "objection_priority",
    "objection_contract_bound",
    "farewell",
    "question_support",
    "internal_champion",
    "payment_terms",
    "request_human",
    "question_trial_period",
    "small_talk",
    "request_brevity",
    "question_retail_tax_general",
    "question_automation",
    "question_data_migration",
    "problem_revealed",
    "go_back",
    "compliance_question",
    "misroute_wipon_outage",
    "misroute_pending_delivery",
    "misroute_training_support",
    "misroute_technical_support",
]

VALID_INTENTS = frozenset(get_args(IntentType))

# Canonical aliases that the model tends to invent when prompt/schema drift appears.
INTENT_ALIASES = {
    "explicit_product_request": "question_specific_product",
    "named_product_request": "question_specific_product",
    "specific_product_request": "question_specific_product",
    "product_selection_request": "question_specific_product",
    "question_compliance": "compliance_question",
    "question_tax": "question_retail_tax_general",
    "question_taxes": "question_retail_tax_general",
    "question_taxation": "question_retail_tax_general",
    "objection_compliance": "compliance_question",
    "objection_no_knowledge": "need_help",
    "objection_no_expertise": "need_help",
    "pain_point": "problem_revealed",
    "objection_reliability": "objection_trust",
    "delivery_request": "question_delivery",
    "referral_mentioned": "info_provided",
    "referral_source": "info_provided",
    "skepticism": "skepticism_expression",
}


def normalize_intent_label(value: str) -> str:
    """Normalize model-produced intent aliases to canonical schema labels."""
    normalized = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if normalized.startswith("question_tax"):
        return "question_retail_tax_general"
    return INTENT_ALIASES.get(normalized, normalized)


PainCategory = Literal[
    "losing_clients",
    "no_control",
    "manual_work",
    "manager_issues",
    "chaos",
]
VALID_PAIN_CATEGORIES = frozenset(get_args(PainCategory))

PAIN_CATEGORY_ALIASES = {
    "inventory_mismatch": "no_control",
    "team_chaos": "chaos",
    "no_analytics": "no_control",
    "manager_issue": "manager_issues",
    "manual": "manual_work",
    "manual_process": "manual_work",
    "manual_processes": "manual_work",
    "client_loss": "losing_clients",
}


def normalize_pain_category(value: str) -> str:
    """Normalize model-produced pain categories to canonical schema labels."""
    normalized = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    return PAIN_CATEGORY_ALIASES.get(normalized, normalized)


class ExtractedData(BaseModel):
    """Извлечённые данные из сообщения."""
    model_config = ConfigDict(extra="ignore")

    company_name: Optional[str] = Field(None, description="Название компании клиента")
    contact_name: Optional[str] = Field(None, description="Полное имя контактного лица")
    city: Optional[str] = Field(None, description="Город клиента")
    budget_range: Optional[str] = Field(None, description="Бюджет клиента (сумма или оценка)")
    company_size: Optional[int] = Field(None, description="Размер компании (число сотрудников)")
    business_type: Optional[str] = Field(None, description="Тип бизнеса/отрасль")
    current_tools: Optional[str] = Field(None, description="Текущие инструменты")
    automation_before: Optional[bool] = Field(None, description="Была ли автоматизация раньше")
    automation_now: Optional[bool] = Field(None, description="Есть ли автоматизация сейчас")
    pain_point: Optional[str] = Field(None, description="Выявленная боль")
    pain_category: Optional[PainCategory] = Field(None, description="Категория боли")
    pain_impact: Optional[str] = Field(None, description="Влияние боли на бизнес")
    financial_impact: Optional[str] = Field(None, description="Финансовое влияние")
    contact_info: Optional[str] = Field(None, description="Контактные данные")
    kaspi_phone: Optional[str] = Field(None, description="Номер Kaspi телефона (87xxx или +77xxx)")
    iin: Optional[str] = Field(None, description="ИИН клиента (12 цифр)")
    desired_outcome: Optional[str] = Field(None, description="Желаемый результат")
    value_acknowledged: Optional[bool] = Field(None, description="Признана ли ценность")

    @field_validator("pain_category", mode="before")
    @classmethod
    def _normalize_pain_category(cls, value):
        if value is None:
            return None
        return normalize_pain_category(value)


class IntentAlternative(BaseModel):
    """Альтернативный интент с confidence."""
    model_config = ConfigDict(extra="ignore")

    intent: str = Field(..., description="Интент")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Уверенность 0-1")

    @field_validator("intent", mode="before")
    @classmethod
    def _normalize_intent(cls, value):
        return normalize_intent_label(value)


class ClassificationResult(BaseModel):
    """Результат классификации интента."""
    model_config = ConfigDict(extra="ignore")

    intent: IntentType = Field(..., description="Определённый интент (top-1)")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Уверенность 0-1")
    reasoning: str = Field(..., description="Объяснение выбора интента")
    extracted_data: ExtractedData = Field(default_factory=ExtractedData)
    alternatives: List[IntentAlternative] = Field(
        default_factory=list,
        max_length=2,
        description="Альтернативные интенты (top-2, top-3)"
    )

    @field_validator("intent", mode="before")
    @classmethod
    def _normalize_intent(cls, value):
        return normalize_intent_label(value)


# =============================================================================
# CategoryRouter schema
# =============================================================================

# 17 категорий базы знаний
CategoryType = Literal[
    "analytics",     # Аналитика и отчёты
    "competitors",   # Сравнение с конкурентами
    "employees",     # Сотрудники и кадры
    "equipment",     # Оборудование и периферия
    "faq",           # Общие частые вопросы
    "features",      # Функции системы
    "fiscal",        # Фискализация
    "integrations",  # Интеграции
    "inventory",     # Товары и склад
    "mobile",        # Мобильное приложение
    "pricing",       # Цены и тарифы
    "products",      # Продукты Wipon
    "promotions",    # Акции и скидки
    "delivery",      # Доставка и регионы
    "stability",     # Надёжность и стабильность
    "support",       # Техподдержка и обучение
    "tis",           # Трёхкомпонентная система для ИП
]


class CategoryResult(BaseModel):
    """Результат роутинга по категориям."""
    categories: List[CategoryType] = Field(
        ...,
        min_length=1,
        max_length=5,
        description="Список категорий для поиска (1-5)"
    )
