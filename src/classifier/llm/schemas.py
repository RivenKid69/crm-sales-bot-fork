"""Pydantic schemas для LLM классификатора."""
from typing import Optional, Literal, List
from pydantic import BaseModel, Field, field_validator

# 80 интентов для CRM Sales Bot
IntentType = Literal[
    # =================================================================
    # ПРИВЕТСТВИЯ И ОБЩЕНИЕ (5)
    # =================================================================
    "greeting",      # приветствие
    "agreement",     # согласие
    "gratitude",     # благодарность
    "farewell",      # прощание
    "small_talk",    # болтовня/small talk

    # =================================================================
    # ЦЕНОВЫЕ ВОПРОСЫ (3)
    # =================================================================
    "price_question",   # вопрос о цене
    "pricing_details",  # детали тарифов
    "objection_price",  # возражение по цене

    # =================================================================
    # ВОПРОСЫ О ПРОДУКТЕ (14) - расширено с 3 до 14
    # =================================================================
    "question_features",       # вопрос о функциях
    "question_integrations",   # вопрос об интеграциях
    "comparison",              # сравнение с конкурентами
    # Новые вопросы о продукте:
    "question_security",       # вопросы о безопасности данных
    "question_support",        # вопросы о техподдержке
    "question_implementation", # вопросы о процессе внедрения
    "question_training",       # вопросы об обучении персонала
    "question_updates",        # вопросы об обновлениях системы
    "question_mobile",         # вопросы о мобильном приложении
    "question_offline",        # вопросы об офлайн-режиме
    "question_data_migration", # вопросы о миграции данных
    "question_customization",  # вопросы о кастомизации
    "question_reports",        # вопросы об отчётах и аналитике
    "question_automation",     # вопросы об автоматизации процессов
    "question_scalability",    # вопросы о масштабируемости

    # =================================================================
    # ЗАПРОСЫ НА КОНТАКТ/ДЕЙСТВИЕ (4)
    # =================================================================
    "callback_request",       # запрос перезвона
    "contact_provided",       # предоставление контакта
    "demo_request",           # запрос демо
    "consultation_request",   # запрос консультации

    # =================================================================
    # SPIN ДАННЫЕ (7)
    # =================================================================
    "situation_provided",         # информация о ситуации (S)
    "problem_revealed",           # описание проблемы (P)
    "implication_acknowledged",   # осознание последствий (I)
    "need_expressed",             # выражение потребности (N)
    "no_problem",                 # отрицание проблемы
    "no_need",                    # отрицание потребности
    "info_provided",              # предоставление информации

    # =================================================================
    # ВОЗРАЖЕНИЯ (18) - расширено с 8 до 18
    # =================================================================
    "objection_no_time",          # нет времени
    "objection_timing",           # неподходящее время
    "objection_think",            # нужно подумать
    "objection_complexity",       # сложность внедрения
    "objection_competitor",       # уже есть конкурент
    "objection_trust",            # недоверие
    "objection_no_need",          # не нужно
    "rejection",                  # жёсткий отказ
    # Новые возражения:
    "objection_risk",             # боязнь рисков
    "objection_team_resistance",  # сопротивление команды
    "objection_security",         # опасения по безопасности
    "objection_bad_experience",   # негативный опыт с CRM
    "objection_priority",         # сейчас другие приоритеты
    "objection_scale",            # масштаб не подходит
    "objection_change_management",# сложность управления изменениями
    "objection_contract_bound",   # связаны контрактом
    "objection_company_policy",   # политика компании
    "objection_roi_doubt",        # сомнения в окупаемости

    # =================================================================
    # ПОЗИТИВНЫЕ СИГНАЛЫ (8) - новая категория
    # =================================================================
    "ready_to_buy",               # готовность к покупке
    "budget_approved",            # бюджет одобрен
    "decision_maker_identified",  # определён ЛПР
    "urgency_expressed",          # срочная потребность
    "competitor_dissatisfied",    # недоволен текущим решением
    "expansion_planned",          # планируется расширение
    "positive_feedback",          # позитивный отзыв о демо/продукте
    "internal_champion",          # внутренний адвокат продукта

    # =================================================================
    # ЭТАПЫ ПОКУПКИ (8) - новая категория
    # =================================================================
    "request_proposal",           # запрос коммерческого предложения
    "request_contract",           # запрос договора
    "request_invoice",            # запрос счёта
    "request_discount",           # запрос скидки
    "negotiate_terms",            # переговоры по условиям
    "request_trial_extension",    # запрос продления триала
    "request_references",         # запрос референсов/отзывов
    "request_sla",                # запрос SLA/гарантий

    # =================================================================
    # ВОПРОСЫ О КОМПАНИИ (4) - новая категория
    # =================================================================
    "company_info_question",      # вопросы о компании Wipon
    "experience_question",        # вопросы об опыте работы
    "case_study_request",         # запрос кейсов
    "roi_question",               # вопрос о ROI/окупаемости

    # =================================================================
    # УПРАВЛЕНИЕ ДИАЛОГОМ (8) - расширено с 4 до 8
    # =================================================================
    "unclear",                    # непонятное сообщение
    "go_back",                    # вернуться назад
    "correct_info",               # исправление информации
    "request_brevity",            # запрос краткости
    # Новые:
    "clarification_request",      # просьба уточнить
    "repeat_request",             # просьба повторить
    "example_request",            # просьба привести пример
    "summary_request",            # просьба подытожить
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


class IntentAlternative(BaseModel):
    """Альтернативный интент с confidence."""
    intent: IntentType = Field(..., description="Интент")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Уверенность 0-1")


class ClassificationResult(BaseModel):
    """Результат классификации интента."""
    intent: IntentType = Field(..., description="Определённый интент (top-1)")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Уверенность 0-1")
    reasoning: str = Field(..., description="Объяснение выбора интента")
    extracted_data: ExtractedData = Field(default_factory=ExtractedData)
    alternatives: List[IntentAlternative] = Field(
        default_factory=list,
        max_length=2,
        description="Альтернативные интенты (top-2, top-3)"
    )


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
    "regions",       # Регионы и доставка
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
