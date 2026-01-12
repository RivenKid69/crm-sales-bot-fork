"""Pydantic schemas для LLM классификатора."""
from typing import Optional, Literal
from pydantic import BaseModel, Field

# 33 интента из текущего INTENT_ROOTS
IntentType = Literal[
    # Приветствия и общение
    "greeting", "agreement", "gratitude", "farewell", "small_talk",
    # Ценовые
    "price_question", "pricing_details", "objection_price",
    # Вопросы о продукте
    "question_features", "question_integrations", "comparison",
    # Запросы на контакт
    "callback_request", "contact_provided", "demo_request", "consultation_request",
    # SPIN данные
    "situation_provided", "problem_revealed", "implication_acknowledged",
    "need_expressed", "no_problem", "no_need", "info_provided",
    # Возражения
    "objection_no_time", "objection_timing", "objection_think",
    "objection_complexity", "objection_competitor", "objection_trust",
    "objection_no_need", "rejection",
    # Управление диалогом
    "unclear", "go_back", "correct_info"
]

PainCategory = Literal["losing_clients", "no_control", "manual_work"]


class ExtractedData(BaseModel):
    """Извлечённые данные из сообщения."""
    company_size: Optional[int] = Field(None, description="Размер компании (число сотрудников)")
    business_type: Optional[str] = Field(None, description="Тип бизнеса/отрасль")
    current_tools: Optional[str] = Field(None, description="Текущие инструменты")
    pain_point: Optional[str] = Field(None, description="Выявленная боль")
    pain_category: Optional[PainCategory] = Field(None, description="Категория боли")
    pain_impact: Optional[str] = Field(None, description="Влияние боли на бизнес")
    financial_impact: Optional[str] = Field(None, description="Финансовое влияние")
    contact_info: Optional[str] = Field(None, description="Контактные данные")
    desired_outcome: Optional[str] = Field(None, description="Желаемый результат")
    value_acknowledged: Optional[bool] = Field(None, description="Признана ли ценность")


class ClassificationResult(BaseModel):
    """Результат классификации интента."""
    intent: IntentType = Field(..., description="Определённый интент")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Уверенность 0-1")
    reasoning: str = Field(..., description="Объяснение выбора интента")
    extracted_data: ExtractedData = Field(default_factory=ExtractedData)
