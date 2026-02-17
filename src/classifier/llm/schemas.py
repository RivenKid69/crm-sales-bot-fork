"""Pydantic schemas для LLM классификатора."""
from typing import Optional, Literal, List
from pydantic import BaseModel, Field, field_validator

# 220 интентов для CRM Sales Bot Wipon
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
    "cost_inquiry",          # запрос стоимости
    "discount_request",      # запрос скидки
    "payment_terms",         # условия оплаты
    "pricing_comparison",    # сравнение цен/тарифов
    "budget_question",       # вопрос о бюджете

    # =================================================================
    # ВОПРОСЫ О ПРОДУКТЕ (14)
    # =================================================================
    "question_features",       # вопрос о функциях
    "question_integrations",   # вопрос об интеграциях
    "comparison",              # сравнение с конкурентами
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
    "question_technical",      # технические вопросы (SSL, API, webhook)

    # =================================================================
    # ЗАПРОСЫ НА КОНТАКТ/ДЕЙСТВИЕ (4)
    # =================================================================
    "callback_request",       # запрос перезвона
    "contact_provided",       # предоставление контакта
    "demo_request",           # запрос демо
    "consultation_request",   # запрос консультации
    "request_human",         # запрос оператора/менеджера
    "need_help",             # нужна помощь

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
    # ВОЗРАЖЕНИЯ (18)
    # =================================================================
    "objection_no_time",          # нет времени
    "objection_timing",           # неподходящее время
    "objection_think",            # нужно подумать
    "objection_complexity",       # сложность внедрения
    "objection_competitor",       # уже есть конкурент
    "objection_trust",            # недоверие
    "objection_no_need",          # не нужно
    "rejection",                  # жёсткий отказ
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
    # ПОЗИТИВНЫЕ СИГНАЛЫ (8)
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
    # ЭТАПЫ ПОКУПКИ (8)
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
    # ВОПРОСЫ О КОМПАНИИ (4)
    # =================================================================
    "company_info_question",      # вопросы о компании Wipon
    "experience_question",        # вопросы об опыте работы
    "case_study_request",         # запрос кейсов
    "roi_question",               # вопрос о ROI/окупаемости

    # =================================================================
    # УПРАВЛЕНИЕ ДИАЛОГОМ (8)
    # =================================================================
    "unclear",                    # непонятное сообщение
    "go_back",                    # вернуться назад
    "correct_info",               # исправление информации
    "request_brevity",            # запрос краткости
    "clarification_request",      # просьба уточнить
    "repeat_request",             # просьба повторить
    "example_request",            # просьба привести пример
    "summary_request",            # просьба подытожить

    # =================================================================
    # ВОПРОСЫ ОБ ОБОРУДОВАНИИ (12) - НОВЫЕ
    # =================================================================
    "question_equipment_general",    # общие вопросы об оборудовании
    "question_pos_monoblock",        # вопросы о моноблоках/кассах POS
    "question_scales",               # вопросы о весах (умные весы, Rongta)
    "question_scanner",              # вопросы о сканерах штрих-кодов
    "question_printer",              # вопросы о принтерах чеков/этикеток
    "question_cash_drawer",          # вопросы о денежном ящике
    "question_equipment_bundle",     # вопросы о комплектах оборудования
    "question_equipment_specs",      # характеристики оборудования
    "question_equipment_warranty",   # гарантия на оборудование
    "question_equipment_install",    # установка/настройка оборудования
    "question_equipment_compat",     # совместимость оборудования
    "question_second_screen",        # вопросы о втором экране покупателя

    # =================================================================
    # ВОПРОСЫ О ТАРИФАХ (8) - НОВЫЕ
    # =================================================================
    "question_tariff_mini",          # тариф Mini (5000₸/мес)
    "question_tariff_lite",          # тариф Lite
    "question_tariff_standard",      # тариф Standard
    "question_tariff_pro",           # тариф Pro
    "question_tariff_comparison",    # сравнение тарифов
    "question_installment",          # вопросы о рассрочке
    "question_trial_period",         # вопросы о тестовом периоде
    "question_ofd_payment",          # оплата ОФД

    # =================================================================
    # ВОПРОСЫ О ТИС (10) - НОВЫЕ
    # =================================================================
    "question_tis_general",          # общие вопросы о ТИС
    "question_tis_limits",           # лимиты ТИС (НДС, доход)
    "question_tis_price",            # стоимость подключения ТИС
    "question_tis_requirements",     # требования для подключения ТИС
    "question_tis_benefits",         # преимущества ТИС
    "question_tis_2026",             # ТИС в 2026 году
    "question_tis_components",       # компоненты ТИС
    "question_tis_multi_location",   # ТИС для нескольких точек
    "question_tis_transition",       # переход на/с ТИС
    "question_tis_reports",          # отчётность по ТИС

    # =================================================================
    # ВОПРОСЫ О НАЛОГАХ (8) - НОВЫЕ
    # =================================================================
    "question_retail_tax_general",   # общие вопросы о розничном налоге
    "question_retail_tax_rates",     # ставки розничного налога
    "question_retail_tax_oked",      # ОКЭД для розничного налога
    "question_retail_tax_reports",   # отчётность по розничному налогу
    "question_retail_tax_transition",# переход на розничный налог
    "question_snr_comparison",       # сравнение СНР режимов
    "question_vat_registration",     # регистрация по НДС
    "question_tax_optimization",     # оптимизация налогов

    # =================================================================
    # БУХГАЛТЕРИЯ И ДОКУМЕНТЫ (8) - НОВЫЕ
    # =================================================================
    "question_accounting_services",  # бухгалтерские услуги Wipon
    "question_esf_snt",              # ЭСФ и СНТ
    "question_form_910",             # форма 910
    "question_form_200",             # форма 200 (зарплата)
    "question_form_300",             # форма 300 (НДС)
    "question_business_registration",# регистрация ИП/ТОО
    "question_business_closure",     # закрытие ИП/ТОО
    "question_document_flow",        # документооборот

    # =================================================================
    # ИНТЕГРАЦИИ СПЕЦИФИЧНЫЕ (8) - НОВЫЕ
    # =================================================================
    "question_bank_terminal",        # интеграция с POS-терминалами банков
    "question_kaspi_integration",    # интеграция с Kaspi
    "question_halyk_integration",    # интеграция с Halyk Market
    "question_1c_integration",       # интеграция с 1С
    "question_iiko_integration",     # интеграция с iiko/r_keeper
    "question_ofd_connection",       # подключение к ОФД
    "question_marking_ismet",        # маркировка товаров (ISMET)
    "question_cashback_loyalty",     # Wipon Cashback/программа лояльности

    # =================================================================
    # УЧЁТ И ОПЕРАЦИИ (10) - НОВЫЕ
    # =================================================================
    "question_inventory",            # складской учёт
    "question_revision",             # ревизия/инвентаризация
    "question_purchase_mgmt",        # управление закупками
    "question_sales_mgmt",           # управление продажами
    "question_cash_operations",      # кассовые операции
    "question_returns_mgmt",         # управление возвратами
    "question_employee_control",     # контроль сотрудников
    "question_multi_location",       # работа с несколькими точками
    "question_promo_discounts",      # скидки и акции
    "question_price_labels",         # печать ценников/этикеток

    # =================================================================
    # ДОСТАВКА И СЕРВИС (6) - НОВЫЕ
    # =================================================================
    "question_delivery",             # вопросы о доставке
    "question_delivery_time",        # сроки доставки
    "question_office_location",      # расположение офисов
    "question_working_hours",        # часы работы
    "request_refund",                # запрос возврата средств
    "request_equipment_return",      # возврат оборудования

    # =================================================================
    # БИЗНЕС-СЦЕНАРИИ (10) - НОВЫЕ
    # =================================================================
    "question_grocery_store",        # для продуктового магазина
    "question_restaurant_cafe",      # для ресторана/кафе
    "question_pharmacy",             # для аптеки
    "question_clothing_store",       # для магазина одежды
    "question_small_business",       # для малого бизнеса
    "question_network_stores",       # для сети магазинов
    "question_market_stall",         # для рынка/ларька
    "question_alcohol_tobacco",      # для алкоголя/табака
    "question_beauty_salon",         # для салона красоты
    "question_construction",         # для стройматериалов

    # =================================================================
    # ТЕХНИЧЕСКИЕ ПРОБЛЕМЫ (6) - НОВЫЕ
    # =================================================================
    "problem_technical",             # общие технические проблемы
    "problem_connection",            # проблемы с подключением
    "problem_sync",                  # проблемы синхронизации
    "problem_fiscal",                # проблемы с фискализацией
    "request_technical_support",     # запрос техподдержки
    "request_configuration",         # запрос настройки

    # =================================================================
    # ЧУВСТВИТЕЛЬНЫЕ/ЮРИДИЧЕСКИЕ (6)
    # =================================================================
    "legal_question",            # юридические вопросы
    "formal_complaint",          # жалоба/претензия
    "contract_dispute",          # спор по договору
    "data_deletion",             # удаление данных/аккаунта
    "gdpr_request",              # запрос по персональным данным
    "compliance_question",       # сертификация/соответствие

    # =================================================================
    # ЯЗЫК И ПРОЧЕЕ (2) - НОВЫЕ
    # =================================================================
    "language_kazakh",               # сообщение на казахском языке
    "payment_confirmation",          # подтверждение оплаты

    # =================================================================
    # РАЗГОВОРНЫЕ/ЭМОЦИОНАЛЬНЫЕ (10) - НОВЫЕ
    # =================================================================
    "compliment",                    # комплимент ("классный сервис", "молодцы")
    "joke_response",                 # ответ на шутку/юмор
    "surprise_expression",           # удивление ("ого", "ничего себе", "вау")
    "frustration_expression",        # раздражение ("надоело", "достало")
    "skepticism_expression",         # скептицизм ("сомневаюсь", "не верится")
    "curiosity_expression",          # любопытство ("а что если", "интересно")
    "empathy_request",               # запрос понимания ("войдите в положение")
    "confusion_expression",          # замешательство ("запутался", "не понимаю")
    "impatience_expression",         # нетерпение ("сколько ждать", "быстрее")
    "relief_expression",             # облегчение ("ну слава богу", "наконец-то")

    # =================================================================
    # ВОПРОСЫ О ФИСКАЛИЗАЦИИ (8) - НОВЫЕ
    # =================================================================
    "question_fiscal_general",       # общие вопросы о фискализации
    "question_fiscal_receipt",       # вопросы о чеках
    "question_fiscal_z_report",      # вопросы о Z-отчёте
    "question_fiscal_x_report",      # вопросы о X-отчёте
    "question_fiscal_kkm",           # вопросы о ККМ/контрольно-кассовой машине
    "question_fiscal_ofd_wipon",     # вопросы об ОФД Wipon
    "question_fiscal_correction",    # вопросы о чеке коррекции
    "question_fiscal_replacement",   # замена фискального накопителя

    # =================================================================
    # ВОПРОСЫ ОБ АНАЛИТИКЕ (8) - НОВЫЕ
    # =================================================================
    "question_analytics_sales",      # аналитика продаж
    "question_analytics_abc",        # ABC-анализ товаров
    "question_analytics_profit",     # анализ прибыли
    "question_analytics_comparison", # сравнительная аналитика
    "question_analytics_realtime",   # аналитика в реальном времени
    "question_analytics_export",     # экспорт отчётов
    "question_analytics_custom",     # кастомные отчёты
    "question_analytics_dashboard",  # дашборд и графики

    # =================================================================
    # ВОПРОСЫ О ПРОДУКТАХ WIPON (6) - НОВЫЕ
    # =================================================================
    "question_wipon_pro",            # вопросы о Wipon Pro
    "question_wipon_desktop",        # вопросы о Wipon Desktop
    "question_wipon_kassa",          # вопросы о Wipon Kassa
    "question_wipon_consulting",     # вопросы о Wipon Consulting
    "question_wipon_cashback_app",   # приложение Wipon Cashback
    "question_product_comparison",   # сравнение продуктов Wipon

    # =================================================================
    # ВОПРОСЫ О СОТРУДНИКАХ/КАДРАХ (6) - НОВЫЕ
    # =================================================================
    "question_employees_salary",     # расчёт зарплаты
    "question_employees_schedule",   # графики работы
    "question_employees_permissions",# настройка прав доступа
    "question_employees_tracking",   # отслеживание работы сотрудников
    "question_employees_motivation", # мотивация и KPI
    "question_employees_onboarding", # обучение новых сотрудников

    # =================================================================
    # ДОПОЛНИТЕЛЬНЫЕ БИЗНЕС-СЦЕНАРИИ (8) - НОВЫЕ
    # =================================================================
    "question_wholesale",            # оптовая торговля
    "question_auto_parts",           # автозапчасти
    "question_electronics",          # электроника и техника
    "question_pet_shop",             # зоомагазин
    "question_flower_shop",          # цветочный магазин
    "question_hotel",                # гостиница/хостел
    "question_service_center",       # сервисный центр
    "question_sports_shop",          # спортивные товары

    # =================================================================
    # ДОПОЛНИТЕЛЬНЫЕ ИНТЕГРАЦИИ (6) - НОВЫЕ
    # =================================================================
    "question_glovo_wolt",           # интеграция с Glovo/Wolt
    "question_telegram_bot",         # Telegram бот
    "question_whatsapp_business",    # WhatsApp Business
    "question_instagram_shop",       # Instagram магазин
    "question_website_widget",       # виджет для сайта
    "question_delivery_services",    # службы доставки (СДЭК и др.)

    # =================================================================
    # ВОПРОСЫ О ПРОМО/ЛОЯЛЬНОСТИ (6) - НОВЫЕ
    # =================================================================
    "question_loyalty_program",      # программа лояльности
    "question_bonus_system",         # бонусная система
    "question_discount_cards",       # дисконтные карты
    "question_gift_cards",           # подарочные карты/сертификаты
    "question_customer_database",    # база клиентов
    "question_sms_marketing",        # SMS-рассылки клиентам

    # =================================================================
    # ВОПРОСЫ О СТАБИЛЬНОСТИ/НАДЁЖНОСТИ (6) - НОВЫЕ
    # =================================================================
    "question_backup_restore",       # резервное копирование/восстановление
    "question_uptime_sla",           # время работы/SLA
    "question_server_location",      # расположение серверов
    "question_data_encryption",      # шифрование данных
    "question_disaster_recovery",    # восстановление после сбоя
    "question_system_requirements",  # системные требования

    # =================================================================
    # ВОПРОСЫ О РЕГИОНАХ/ПРИСУТСТВИИ (6) - НОВЫЕ
    # =================================================================
    "question_region_almaty",        # работа в Алматы
    "question_region_astana",        # работа в Астане
    "question_region_shymkent",      # работа в Шымкенте
    "question_region_other",         # другие регионы Казахстана
    "question_pickup_office",        # самовывоз из офиса
    "question_courier_service",      # курьерская служба Wipon
]

PainCategory = Literal["losing_clients", "no_control", "manual_work"]


class ExtractedData(BaseModel):
    """Извлечённые данные из сообщения."""
    company_name: Optional[str] = Field(None, description="Название компании клиента")
    contact_name: Optional[str] = Field(None, description="Полное имя контактного лица")
    budget_range: Optional[str] = Field(None, description="Бюджет клиента (сумма или оценка)")
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
