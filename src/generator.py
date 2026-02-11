"""
Генератор ответов — собирает промпт и вызывает LLM

Включает:
- ResponseGenerator: генерация ответов через LLM
- PersonalizationEngine: персонализация на основе собранных данных
- SafeDict: безопасная подстановка переменных в шаблоны
"""

import random
from typing import Dict, List, Optional, TYPE_CHECKING, Any, Set
from src.config import SYSTEM_PROMPT, PROMPT_TEMPLATES, KNOWLEDGE
from src.knowledge.retriever import get_retriever
from src.settings import settings
from src.logger import logger
from src.feature_flags import flags
from src.response_diversity import diversity_engine
from src.question_dedup import question_dedup_engine

if TYPE_CHECKING:
    from src.config_loader import FlowConfig
    from src.personalization import PersonalizationEngineV2


# =============================================================================
# SAFE TEMPLATE SUBSTITUTION
# =============================================================================

class SafeDict(dict):
    """
    Словарь с безопасной подстановкой для template.format().

    Возвращает пустую строку для отсутствующих ключей вместо KeyError.
    Это предотвращает падение форматирования и показ {переменных} клиенту.

    Usage:
        template = "Hello {name}, your pain is {pain_point}"
        result = template.format_map(SafeDict({"name": "John"}))
        # Result: "Hello John, your pain is "
    """

    def __missing__(self, key: str) -> str:
        """Возвращает пустую строку для отсутствующих ключей."""
        logger.debug(f"SafeDict: missing key '{key}', returning empty string")
        return ""


# Fallback значения для персонализационных переменных
# Используются когда PersonalizationEngine v2 отключен или недоступен
PERSONALIZATION_DEFAULTS: Dict[str, str] = {
    # Style instructions (from PersonalizationResult)
    "style_full_instruction": "",
    "adaptive_style_instruction": "",
    "adaptive_tactical_instruction": "",

    # Business context (bc_* prefix)
    "size_category": "small",
    "bc_size_label": "",
    "bc_pain_focus": "",
    "bc_value_prop": "",
    "bc_objection_counter": "",
    "bc_demo_pitch": "",

    # Industry context (ic_* prefix)
    "industry": "",
    "industry_confidence": "0",
    "ic_keywords": "",
    "ic_examples": "",
    "ic_pain_examples": "",

    # Session memory
    "effective_actions_hint": "",

    # Pain reference
    "pain_reference": "",
    "personalization_block": "",

    # ResponseDirectives memory fields
    "client_card": "",
    "do_not_repeat": "",
    "reference_pain": "",
    "objection_summary": "",
}


# =============================================================================
# PERSONALIZATION ENGINE
# =============================================================================

class PersonalizationEngine:
    """
    Персонализация ответов на основе собранных данных о клиенте.

    Учитывает:
    - Размер компании (micro, small, medium, large)
    - Тип бизнеса/отрасль
    - Выявленные боли (pain_points)

    Использование:
        engine = PersonalizationEngine()
        context = engine.get_context(collected_data)
        # context содержит персонализированные поля для промптов
    """

    # Контексты по размеру компании
    BUSINESS_CONTEXTS: Dict[str, Dict[str, str]] = {
        "micro": {  # 1-5 человек
            "size_label": "небольшая команда",
            "pain_focus": "простота и экономия времени",
            "value_prop": "всё в одном месте, без сложных настроек",
            "objection_counter": "окупается за счёт сэкономленного времени",
            "demo_pitch": "покажу как работает — займёт 15 минут",
        },
        "small": {  # 6-15 человек
            "size_label": "растущая команда",
            "pain_focus": "контроль и координация команды",
            "value_prop": "видите работу каждого сотрудника",
            "objection_counter": "стоимость на человека ниже чем у конкурентов",
            "demo_pitch": "покажу как следить за командой — это удобно",
        },
        "medium": {  # 16-50 человек
            "size_label": "средний бизнес",
            "pain_focus": "масштабирование и автоматизация",
            "value_prop": "автоматизация рутины, аналитика в реальном времени",
            "objection_counter": "enterprise функции по цене малого бизнеса",
            "demo_pitch": "покажу автоматизацию и отчёты — экономит часы",
        },
        "large": {  # 50+ человек
            "size_label": "крупная компания",
            "pain_focus": "интеграция и кастомизация",
            "value_prop": "API, кастомные отчёты, dedicated поддержка",
            "objection_counter": "гибкие условия, индивидуальные тарифы",
            "demo_pitch": "обсудим ваши требования — подготовлю предложение",
        },
    }

    # Контексты по отрасли
    INDUSTRY_CONTEXTS: Dict[str, Dict[str, List[str]]] = {
        "retail": {
            "keywords": ["магазин", "розница", "торговля", "товар"],
            "examples": ["учёт товаров", "остатки", "поставщики"],
            "pain_examples": ["пересортица", "недостачи", "списания"],
        },
        "services": {
            "keywords": ["услуг", "сервис", "салон", "студия", "клиник"],
            "examples": ["запись клиентов", "расписание", "услуги"],
            "pain_examples": ["пропущенные записи", "накладки", "забытые клиенты"],
        },
        "horeca": {
            "keywords": ["ресторан", "кафе", "общепит", "бар", "доставка еды"],
            "examples": ["столики", "заказы", "меню"],
            "pain_examples": ["потерянные заказы", "очереди", "учёт продуктов"],
        },
        "b2b": {
            "keywords": ["опт", "b2b", "дилер", "дистрибут", "поставщик"],
            "examples": ["контракты", "отгрузки", "дебиторка"],
            "pain_examples": ["долгие сделки", "потерянные контакты", "забытые follow-up"],
        },
        "real_estate": {
            "keywords": ["недвижимост", "риелтор", "застройщик", "агентство недвиж"],
            "examples": ["объекты", "показы", "сделки"],
            "pain_examples": ["потерянные лиды", "забытые показы", "конкуренция"],
        },
        "it": {
            "keywords": ["it", "разработ", "софт", "digital", "агентство"],
            "examples": ["проекты", "задачи", "клиенты"],
            "pain_examples": ["срывы сроков", "потеря контекста", "нет прозрачности"],
        },
    }

    # Размерные категории
    SIZE_THRESHOLDS = {
        "micro": (1, 5),
        "small": (6, 15),
        "medium": (16, 50),
        "large": (51, float("inf")),
    }

    @classmethod
    def get_size_category(cls, company_size: int) -> str:
        """Определить категорию размера компании"""
        for category, (min_size, max_size) in cls.SIZE_THRESHOLDS.items():
            if min_size <= company_size <= max_size:
                return category
        return "small"  # default

    @classmethod
    def detect_industry(cls, collected_data: Dict) -> Optional[str]:
        """Определить отрасль по собранным данным"""
        # Проверяем business_type
        business_type = collected_data.get("business_type") or ""
        if isinstance(business_type, str):
            business_type = business_type.lower()
        else:
            business_type = ""

        for industry, data in cls.INDUSTRY_CONTEXTS.items():
            for keyword in data["keywords"]:
                if keyword in business_type:
                    return industry

        # Проверяем pain_point
        pain_point = collected_data.get("pain_point") or ""
        if isinstance(pain_point, str):
            pain_point = pain_point.lower()
        else:
            pain_point = ""

        for industry, data in cls.INDUSTRY_CONTEXTS.items():
            for pain_example in data["pain_examples"]:
                if pain_example in pain_point:
                    return industry

        return None

    @classmethod
    def get_context(cls, collected_data: Dict) -> Dict:
        """
        Возвращает контекст для персонализации промпта.

        Args:
            collected_data: Собранные данные о клиенте

        Returns:
            Словарь с полями для персонализации:
            - business_context: контекст по размеру
            - industry_context: контекст по отрасли (если определена)
            - pain_reference: ссылка на боль клиента
            - size_category: категория размера
            - personalized_value_prop: персонализированное ценностное предложение
        """
        context: Dict = {}

        # По размеру компании
        company_size = collected_data.get("company_size")
        if company_size is None:
            company_size = 0
        elif isinstance(company_size, str):
            try:
                company_size = int(company_size)
            except ValueError:
                company_size = 0
        elif not isinstance(company_size, (int, float)):
            company_size = 0

        size_category = cls.get_size_category(int(company_size)) if company_size > 0 else "small"
        context["size_category"] = size_category
        context["business_context"] = cls.BUSINESS_CONTEXTS.get(size_category, cls.BUSINESS_CONTEXTS["small"])

        # По отрасли
        industry = cls.detect_industry(collected_data)
        if industry:
            context["industry"] = industry
            context["industry_context"] = cls.INDUSTRY_CONTEXTS[industry]
        else:
            context["industry"] = None
            context["industry_context"] = None

        # Ссылка на боль
        pain_point = collected_data.get("pain_point")
        if pain_point:
            context["pain_reference"] = f"Вы упоминали про {pain_point}"
            context["has_pain_point"] = True
        else:
            context["pain_reference"] = ""
            context["has_pain_point"] = False

        # Персонализированное ценностное предложение
        context["personalized_value_prop"] = cls._build_value_prop(
            size_category, industry, pain_point
        )

        logger.debug(
            "Personalization context built",
            size_category=size_category,
            industry=industry,
            has_pain_point=bool(pain_point)
        )

        return context

    @classmethod
    def _build_value_prop(
        cls,
        size_category: str,
        industry: Optional[str],
        pain_point: Optional[str]
    ) -> str:
        """Собирает персонализированное ценностное предложение"""
        parts: List[str] = []

        # Базовое предложение по размеру
        business_ctx = cls.BUSINESS_CONTEXTS.get(size_category, cls.BUSINESS_CONTEXTS["small"])
        parts.append(business_ctx["value_prop"])

        # Добавляем отраслевую специфику
        if industry and industry in cls.INDUSTRY_CONTEXTS:
            industry_ctx = cls.INDUSTRY_CONTEXTS[industry]
            example = industry_ctx["examples"][0] if industry_ctx["examples"] else None
            if example:
                parts.append(f"включая {example}")

        return ", ".join(parts) if parts else ""

    @classmethod
    def get_objection_counter(cls, collected_data: Dict, objection_type: str = "price") -> str:
        """
        Возвращает контраргумент для возражения.

        Args:
            collected_data: Собранные данные
            objection_type: Тип возражения (price, competitor, no_time, etc.)

        Returns:
            Контраргумент, персонализированный под клиента
        """
        company_size = collected_data.get("company_size", 0)
        if isinstance(company_size, str):
            try:
                company_size = int(company_size)
            except ValueError:
                company_size = 0

        size_category = cls.get_size_category(company_size) if company_size > 0 else "small"
        business_ctx = cls.BUSINESS_CONTEXTS.get(size_category, cls.BUSINESS_CONTEXTS["small"])

        if objection_type == "price":
            return business_ctx["objection_counter"]
        elif objection_type == "no_time":
            return business_ctx["demo_pitch"]
        else:
            return business_ctx["value_prop"]

    @classmethod
    def format_prompt_with_personalization(
        cls,
        prompt_template: str,
        collected_data: Dict,
        **kwargs
    ) -> str:
        """
        Форматирует промпт с персонализированными данными.

        Args:
            prompt_template: Шаблон промпта
            collected_data: Собранные данные о клиенте
            **kwargs: Дополнительные переменные для форматирования

        Returns:
            Отформатированный промпт
        """
        context = cls.get_context(collected_data)

        # Объединяем все переменные
        variables = {
            **kwargs,
            "size_category": context["size_category"],
            "pain_reference": context["pain_reference"],
            "personalized_value_prop": context["personalized_value_prop"],
        }

        # Добавляем business_context поля
        if context["business_context"]:
            for key, value in context["business_context"].items():
                variables[f"bc_{key}"] = value

        # Добавляем industry_context поля
        if context["industry_context"]:
            for key, value in context["industry_context"].items():
                if isinstance(value, list):
                    variables[f"ic_{key}"] = ", ".join(value)
                else:
                    variables[f"ic_{key}"] = value

        try:
            return prompt_template.format(**variables)
        except KeyError as e:
            logger.warning(f"Missing variable in personalization: {e}")
            return prompt_template


class ResponseGenerator:
    # Интенты связанные с ценой - требуют специального шаблона
    PRICE_RELATED_INTENTS = {"price_question", "pricing_details"}

    # Интенты связанные с возражениями - требуют специфичного шаблона
    OBJECTION_RELATED_INTENTS = {
        "objection_competitor",
        "objection_price",
        "objection_no_time",
        "objection_think",
        "objection_complexity",
        "objection_trust",
        "objection_no_need",
        "objection_timing",
    }

    # Порог схожести для детекции дубликатов
    # Lowered from 0.80 to 0.70 after adding punctuation normalization
    SIMILARITY_THRESHOLD = 0.70

    def __init__(self, llm, flow: "FlowConfig" = None):
        """
        Initialize ResponseGenerator.

        Args:
            llm: LLM instance for generation
            flow: Optional FlowConfig for YAML-based templates
        """
        self.llm = llm
        self._flow = flow

        # Параметры из settings
        self.max_retries = settings.generator.max_retries
        self.history_length = settings.generator.history_length
        self.retriever_top_k = settings.generator.retriever_top_k
        self.allowed_english = set(settings.generator.allowed_english_words)

        # === НОВОЕ: Deduplication ===
        self._response_history: List[str] = []
        self._max_response_history = 5

        # CategoryRouter: LLM-классификация категорий перед поиском
        self.category_router = None
        if settings.get_nested("category_router.enabled", False):
            from src.knowledge.category_router import CategoryRouter
            self.category_router = CategoryRouter(
                llm=llm,
                top_k=settings.get_nested("category_router.top_k", 3),
                fallback_categories=settings.get_nested(
                    "category_router.fallback_categories",
                    ["faq", "features"]
                )
            )
            logger.info("CategoryRouter initialized", top_k=self.category_router.top_k)

        # PersonalizationEngineV2: адаптивная персонализация на основе поведения
        self.personalization_engine: Optional["PersonalizationEngineV2"] = None
        if flags.personalization_v2:
            from src.personalization import PersonalizationEngineV2
            retriever = get_retriever()
            self.personalization_engine = PersonalizationEngineV2(retriever)
            logger.info("PersonalizationEngineV2 initialized")

        # Auto-discovered product overview from knowledge base (SSOT)
        self._product_overview: List[str] = []
        self._init_product_overview()

    def _init_product_overview(self) -> None:
        """
        Load product overview labels from KB sections with priority <= 8.

        These are overview sections (not detailed FAQ entries with priority 10).
        Each section's .facts first line serves as a short summary label.
        Runs ONCE at startup — O(n) scan of sections, cached forever.
        """
        try:
            retriever = get_retriever()
            kb = retriever.kb
            overviews = []
            seen = set()
            for section in kb.sections:
                if section.priority <= 8:
                    first_line = section.facts.split("\n")[0].strip()
                    # Clean up trailing colons for label use
                    label = first_line.rstrip(":")
                    # Skip very short labels (FAQ answers like "Да", "Нет")
                    # and skip duplicates
                    if label and len(label) >= 10 and label not in seen:
                        overviews.append(label)
                        seen.add(label)
            self._product_overview = overviews
            logger.info(
                "Product overview initialized from KB",
                overview_count=len(overviews),
            )
        except Exception as e:
            logger.warning("Failed to init product overview from KB", error=str(e))
            self._product_overview = []

    def _get_product_overview(self) -> str:
        """
        Return a random subset of 6 product overview labels.

        Each call returns a DIFFERENT random subset to prevent LLM fixation.
        """
        if not self._product_overview:
            return ""
        sample_size = min(6, len(self._product_overview))
        return ", ".join(random.sample(self._product_overview, sample_size))

    def get_product_overview(self, company_size: int = None, intent: str = "") -> str:
        """
        Получить обзор продукта (случайная выборка из KB).

        ВАЖНО: Это НЕ факты для ответа на вопросы клиента!
        Для ответа на вопросы используйте {retrieved_facts} из retriever.
        Этот метод возвращает общий обзор продукта для презентаций и возражений.

        Context-aware:
        - Для price-related интентов → возвращаем пустую строку (данные в retrieved_facts)
        - Для других → product overview из KB

        Args:
            company_size: Размер компании (НЕ используется, сохранено для обратной совместимости)
            intent: Текущий интент диалога

        Returns:
            Пустая строка для price интентов, product overview для остальных
        """
        # Price-related интенты → НЕ генерируем обзор
        # Данные уже в {retrieved_facts} из основного retriever вызова (generate:652)
        if intent in self.PRICE_RELATED_INTENTS:
            return ""

        # Default: dynamic product overview from KB (SSOT)
        return self._get_product_overview()

    def _format_urls_for_response(self, urls: List[Dict[str, str]]) -> str:
        """
        Format URLs for inclusion in LLM response.

        Takes structured URL data from knowledge base and formats it
        as markdown links that can be included in the response.

        Args:
            urls: List of URL dicts with 'url', 'label', and optional 'type' keys

        Returns:
            Formatted string with URLs for the response, or empty string
        """
        if not urls:
            return ""

        lines = ["\n**Полезные ссылки:**"]
        for url_info in urls[:5]:  # Limit to 5 URLs max
            url = url_info.get("url", "")
            label = url_info.get("label", "Подробнее")
            url_type = url_info.get("type", "doc")

            if url:
                lines.append(f"• [{label}]({url})")

        if len(lines) > 1:  # If we have any URLs
            return "\n".join(lines)
        return ""

    def format_history(self, history: List[Dict], use_full: bool = False) -> str:
        """Форматируем историю.

        Args:
            history: Список словарей с ключами 'user' и 'bot'
            use_full: Если True — передаём ВСЮ историю (до 30 ходов),
                      иначе обрезаем по self.history_length (settings).
        """
        if not history:
            return "(начало разговора)"

        limit = min(len(history), 30) if use_full else self.history_length
        lines = []
        for turn in history[-limit:]:
            lines.append(f"Клиент: {turn.get('user', '')}")
            if turn.get("bot"):
                lines.append(f"Вы: {turn['bot']}")

        return "\n".join(lines)
    
    def _has_chinese(self, text: str) -> bool:
        """Проверяем есть ли китайские/японские/корейские символы"""
        import re
        return bool(re.search(r'[\u4e00-\u9fff\u3400-\u4dbf\u3040-\u309f\u30a0-\u30ff]', text))

    def _has_english(self, text: str) -> bool:
        """Проверяем есть ли преимущественно английский текст (language switch).

        Возвращает True только когда >50% букв — латиница,
        что указывает на полное переключение языка (Qwen).
        Технические термины в русском тексте (REST, OAuth, JWT) не считаются.
        """
        import re
        russian_chars = len(re.findall(r'[а-яА-ЯёЁ]', text))
        latin_chars = len(re.findall(r'[a-zA-Z]', text))
        total_alpha = russian_chars + latin_chars
        if total_alpha <= 10:
            return False
        return latin_chars / total_alpha > 0.5

    def _has_foreign_language(self, text: str) -> bool:
        """Проверяем есть ли иностранный текст (китайский или английский)"""
        return self._has_chinese(text) or self._has_english(text)

    def _get_template(self, template_key: str) -> str:
        """
        Get template by key, with FlowConfig fallback to PROMPT_TEMPLATES.

        Args:
            template_key: Template name (e.g., 'spin_situation', 'deflect_and_continue')

        Returns:
            Template string
        """
        # Try FlowConfig templates first
        if self._flow:
            template = self._flow.get_template(template_key)
            if template:
                return template

        # Fallback to Python PROMPT_TEMPLATES
        result = PROMPT_TEMPLATES.get(template_key)
        if result:
            return result

        from src.logger import logger
        logger.warning(
            "Template not found, falling back to continue_current_goal",
            requested_template=template_key,
            flow_available=self._flow is not None,
            flow_name=self._flow.name if self._flow else None,
        )
        return PROMPT_TEMPLATES.get("continue_current_goal", "")

    def get_valid_actions(self) -> Set[str]:
        """
        Return the set of all action names resolvable to a template.

        This is the SSOT for action validity — used by ProposalValidator
        to catch invalid actions at proposal time instead of at generation time.
        Mirrors the resolution logic of _get_template(): FlowConfig first,
        then PROMPT_TEMPLATES fallback.
        """
        actions = set(PROMPT_TEMPLATES.keys())
        if self._flow and hasattr(self._flow, 'templates'):
            actions.update(self._flow.templates.keys())
        return actions

    def generate(self, action: str, context: Dict, max_retries: int = None) -> str:
        """Генерируем ответ с retry при китайских символах"""

        # Используем параметр из settings если не указано явно
        if max_retries is None:
            max_retries = self.max_retries

        # Получаем релевантные факты из базы знаний
        intent = context.get("intent", "")
        state = context.get("state", "")
        user_message = context.get("user_message", "")

        # === AUTONOMOUS FLOW: Direct KB access (bypass CategoryRouter + CascadeRetriever) ===
        _is_autonomous = self._flow and self._flow.name == "autonomous" and state.startswith("autonomous_")
        if _is_autonomous:
            from src.knowledge.autonomous_kb import load_facts_for_state
            from src.knowledge.loader import load_knowledge_base
            _kb = load_knowledge_base()
            retrieved_facts, retrieved_urls = load_facts_for_state(
                state=state,
                flow_config=self._flow,
                kb=_kb,
            )
            _company_info = f"{_kb.company_name}: {_kb.company_description}"
        else:
            retriever = get_retriever()
            _company_info = retriever.get_company_info()
            # Определяем категории через LLM (если CategoryRouter включён)
            categories = None
            if self.category_router and user_message:
                categories = self.category_router.route(user_message)
                logger.debug(
                    "CategoryRouter selected categories",
                    categories=categories,
                    query=user_message[:50]
                )

            # Вызываем retriever с категориями и URLs
            retrieved_facts, retrieved_urls = retriever.retrieve_with_urls(
                message=user_message,
                intent=intent,
                state=state,
                categories=categories,
                top_k=self.retriever_top_k
            )

        # Форматируем URLs для включения в ответ
        formatted_urls = self._format_urls_for_response(retrieved_urls) if retrieved_urls else ""

        # Выбираем шаблон
        # === Intent-aware выбор шаблона для price-related вопросов ===
        # Price-related интенты ВСЕГДА получают pricing шаблон, независимо от action
        if intent in self.PRICE_RELATED_INTENTS:
            template_key = self._get_price_template_key(intent, action)
            logger.debug(
                "Price-related intent detected, using pricing template",
                intent=intent,
                original_action=action,
                template_key=template_key
            )
        # === Intent-aware выбор шаблона для objection-related интентов ===
        # Objection интенты получают специфичный шаблон для типа возражения
        elif intent in self.OBJECTION_RELATED_INTENTS:
            template_key = self._get_objection_template_key(intent, action)
            logger.debug(
                "Objection-related intent detected, using specific template",
                intent=intent,
                original_action=action,
                template_key=template_key
            )
        # === Intent-aware выбор шаблона для request_brevity ===
        # Мета-интент: клиент хочет более краткие ответы
        elif intent == "request_brevity":
            template_key = "respond_briefly"
            logger.debug(
                "Brevity request detected, using respond_briefly template",
                intent=intent,
                original_action=action,
                template_key=template_key
            )
        elif action.startswith("transition_to_"):
            template_key = action.replace("transition_to_", "")
        else:
            template_key = action

        # Universal answer-template forcing for repeated questions.
        # When user repeatedly asked a known question but classifier missed it
        # on this turn, force an answering template instead of SPIN/generic.
        # Analogous to existing price template forcing at L664.
        _ctx_envelope = context.get("context_envelope")
        if _ctx_envelope and getattr(_ctx_envelope, 'repeated_question', None):
            from src.yaml_config.constants import INTENT_CATEGORIES, REPAIR_PROTECTED_ACTIONS
            _rq = _ctx_envelope.repeated_question
            _answerable = (
                set(INTENT_CATEGORIES.get("question", []))
                | set(INTENT_CATEGORIES.get("price_related", []))
            )
            # Only force if: (1) repeated question is answerable, (2) current
            # template is NOT already an answering template
            if _rq in _answerable and template_key not in REPAIR_PROTECTED_ACTIONS:
                _price = set(INTENT_CATEGORIES.get("price_related", []))
                if _rq in _price:
                    template_key = self._get_price_template_key(_rq, action)
                else:
                    template_key = "answer_with_knowledge"
                logger.debug(
                    "Repeated question forcing answer template",
                    repeated_question=_rq,
                    original_template=action,
                    forced_template=template_key,
                )

        # NOTE: "spin_phase" is a legacy name. This contains the current phase
        # for ANY active flow (e.g., "situation" for SPIN, "budget" for BANT,
        # "metrics" for MEDDIC). The dedup engine handles all phase names.
        # Если есть phase-specific шаблон, используем его вместо generic continue_current_goal
        # НО только если это не price-related интент (price имеет приоритет)
        spin_phase = context.get("spin_phase", "")
        if template_key == "continue_current_goal" and spin_phase and intent not in self.PRICE_RELATED_INTENTS:
            spin_template_key = f"spin_{spin_phase}"
            # Check if template exists (either in FlowConfig or PROMPT_TEMPLATES)
            if self._flow and self._flow.get_template(spin_template_key):
                template_key = spin_template_key
            elif spin_template_key in PROMPT_TEMPLATES:
                template_key = spin_template_key

        # Get template using the new method with FlowConfig fallback
        template = self._get_template(template_key)

        # Собираем переменные
        collected = context.get("collected_data", {})
        intent = context.get("intent", "")
        product_overview = self.get_product_overview(collected.get("company_size"), intent=intent)

        # SPIN-специфичные данные
        current_tools = collected.get("current_tools", "не указано")
        business_type = collected.get("business_type", "не указано")
        pain_impact = collected.get("pain_impact", "не определено")
        financial_impact = collected.get("financial_impact", "")
        desired_outcome = collected.get("desired_outcome", "не сформулирован")
        spin_phase = context.get("spin_phase", "")

        # Tone and style instructions из контекста (Phase 2: Естественность диалога)
        tone_instruction = context.get("tone_instruction", "")
        style_instruction = context.get("style_instruction", "")

        # Формируем SYSTEM_PROMPT с tone_instruction и style_instruction
        system_prompt = SYSTEM_PROMPT.format(
            tone_instruction=tone_instruction,
            style_instruction=style_instruction
        )

        # Phase 3: Objection context
        objection_info = context.get("objection_info") or {}
        objection_type = objection_info.get("objection_type", "")
        objection_counter = self._get_objection_counter(objection_type, collected)

        # === Собираем pain_point с корректной обработкой пустых значений ===
        raw_pain_point = collected.get("pain_point")
        # Если pain_point не собран или пустой, используем нейтральную формулировку
        if raw_pain_point and raw_pain_point != "?" and str(raw_pain_point).strip():
            pain_point_value = str(raw_pain_point).strip()
        else:
            pain_point_value = "текущие сложности"  # Нейтральная формулировка

        # === Начинаем с fallback значений для персонализации ===
        # Это гарантирует что все переменные определены, даже если personalization_v2 отключен
        variables = dict(PERSONALIZATION_DEFAULTS)

        # === Добавляем базовые переменные (перезаписывают fallback при наличии) ===
        variables.update({
            "system": system_prompt,
            "user_message": user_message,
            "history": self.format_history(context.get("history", []), use_full=_is_autonomous),
            "goal": context.get("goal", ""),
            "collected_data": str(collected),
            "missing_data": ", ".join(context.get("missing_data", [])) or "всё собрано",
            "company_size": collected.get("company_size") or "не указан",
            "pain_point": pain_point_value,
            "product_overview": product_overview,
            # База знаний
            "retrieved_facts": retrieved_facts or "Информация по этому вопросу будет уточнена.",
            "retrieved_urls": formatted_urls,  # NEW: Structured URLs for documentation links
            "company_info": _company_info,
            # SPIN-специфичные данные
            "current_tools": current_tools,
            "business_type": business_type,
            "pain_impact": pain_impact,
            "financial_impact": financial_impact,
            "desired_outcome": desired_outcome,
            "spin_phase": spin_phase,
            # Phase 2: Tone and style instructions
            "tone_instruction": tone_instruction,
            "style_instruction": style_instruction,
            # Phase 3: Objection handling
            "objection_type": objection_type,
            "objection_counter": objection_counter,
            # Apology system (SSoT: src/apology_ssot.py)
            "should_apologize": context.get("should_apologize", False),
            "should_offer_exit": context.get("should_offer_exit", False),
            # Dedup fallback defaults (overwritten by dedup engine when active)
            "do_not_ask": "",
            "collected_fields_list": "",
            "available_questions": "",
        })

        # === Question Deduplication: Prevent asking about already collected data ===
        # SSoT: src/yaml_config/question_dedup.yaml
        # Works for all flows via phase name (SPIN, MEDDIC, BANT, etc.)
        # Universal: inject dedup when collected_data exists, not just when spin_phase is set
        if flags.is_enabled("question_deduplication") and (spin_phase or collected):
            try:
                dedup_phase = spin_phase or context.get("state", "unknown")
                dedup_context = question_dedup_engine.get_prompt_context(
                    phase=dedup_phase,
                    collected_data=collected,
                    missing_data=context.get("missing_data"),
                )
                # Добавляем переменные дедупликации в prompt
                variables.update({
                    "available_questions": dedup_context.get("available_questions", ""),
                    "do_not_ask": dedup_context.get("do_not_ask", ""),
                    "missing_data_questions": dedup_context.get("missing_data_questions", ""),
                    "collected_fields_list": dedup_context.get("collected_fields_list", ""),
                })
                logger.debug(
                    "Question deduplication applied",
                    phase=dedup_phase,
                    available_questions=dedup_context.get("available_questions", "")[:100],
                    do_not_ask=dedup_context.get("do_not_ask", "")[:100],
                )
            except Exception as e:
                logger.warning(f"Question deduplication failed: {e}")

        # Prevent template from asking about already-known data
        if collected.get("company_size") and not variables.get("do_not_ask"):
            variables["do_not_ask"] = (
                "⚠️ НЕ СПРАШИВАЙ о размере команды/количестве сотрудников — "
                f"уже известно: {collected['company_size']} человек."
            )

        # Prevent template from asking about contact when already known
        try:
            from src.conditions.state_machine.contact_validator import has_valid_contact
            if has_valid_contact(collected):
                contact_val = (
                    collected.get("contact_info")
                    or collected.get("email")
                    or collected.get("phone")
                    or "уже получен"
                )
                contact_warning = (
                    "⚠️ НЕ СПРАШИВАЙ контактные данные (телефон/email) — "
                    f"уже известно: {contact_val}."
                )
                existing = variables.get("do_not_ask", "")
                variables["do_not_ask"] = f"{existing}\n{contact_warning}" if existing else contact_warning
        except ImportError:
            pass

        # === Personalization v2: Adaptive personalization ===
        if self.personalization_engine and flags.personalization_v2:
            try:
                from src.personalization import PersonalizationResult
                p_result = self.personalization_engine.personalize(
                    envelope=context.get("context_envelope"),
                    collected_data=collected,
                    action_tracker=context.get("action_tracker"),
                    messages=context.get("user_messages", []),
                )
                # Добавляем переменные персонализации
                personalization_vars = p_result.to_prompt_variables()
                variables.update(personalization_vars)
                logger.debug(
                    "Personalization v2 applied",
                    style_verbosity=p_result.style.verbosity,
                    industry=p_result.industry_context.industry,
                    size_category=p_result.business_context.size_category,
                )
            except Exception as e:
                logger.warning(f"Personalization v2 failed: {e}")
                # Fallback на legacy персонализацию при ошибке
                self._apply_legacy_personalization(variables, collected)
        else:
            # === Legacy Personalization: используем когда v2 отключен ===
            # Это гарантирует что bc_* переменные будут заполнены корректно
            self._apply_legacy_personalization(variables, collected)

        # === ResponseDirectives integration ===
        response_directives = context.get("response_directives")
        if response_directives and flags.context_response_directives:
            try:
                directives_dict = response_directives.to_dict()
                memory = directives_dict.get("memory", {})

                # Memory fields для персонализации
                if memory.get("client_card"):
                    variables["client_card"] = memory["client_card"]
                if memory.get("do_not_repeat"):
                    variables["do_not_repeat"] = ", ".join(memory["do_not_repeat"])
                if memory.get("reference_pain"):
                    variables["reference_pain"] = memory["reference_pain"]
                if memory.get("objection_summary"):
                    variables["objection_summary"] = memory["objection_summary"]

                # Structured данные для templates
                variables["directives_style"] = directives_dict.get("style", {})
                variables["directives_moves"] = directives_dict.get("dialogue_moves", {})

                logger.debug(
                    "ResponseDirectives applied",
                    tone=directives_dict.get("style", {}).get("tone"),
                    max_words=directives_dict.get("style", {}).get("max_words"),
                    repair_mode=directives_dict.get("dialogue_moves", {}).get("repair_mode"),
                )
            except Exception as e:
                logger.warning(f"ResponseDirectives integration failed: {e}")

        # Подставляем в шаблон с безопасной подстановкой
        # SafeDict возвращает пустую строку для отсутствующих ключей,
        # предотвращая KeyError и показ {переменных} клиенту
        prompt = template.format_map(SafeDict(variables))

        # Генерируем с retry при китайских символах
        best_response = ""
        history = context.get("history", [])

        for attempt in range(max_retries):
            response = self.llm.generate(prompt)

            # Если нет иностранного текста — проверяем на дубликаты
            if not self._has_foreign_language(response):
                cleaned = self._clean(response)

                # === НОВОЕ: Проверка на дубликаты ===
                if flags.is_enabled("response_deduplication") and self._is_duplicate(cleaned, history):
                    logger.info(
                        "Duplicate response detected, regenerating",
                        response_preview=cleaned[:50]
                    )
                    cleaned = self._regenerate_with_diversity(prompt, context, cleaned)

                # Сохраняем в историю для отслеживания
                self._add_to_response_history(cleaned)
                # Apply post-processing before returning
                processed = self._apply_diversity(cleaned, context)
                processed = self._ensure_apology(processed, context)
                return processed

            # Иначе чистим и сохраняем лучший результат
            cleaned = self._clean(response)
            if len(cleaned) > len(best_response):
                best_response = cleaned

            # Добавляем усиление в промпт для следующей попытки
            if attempt == 0:
                prompt = prompt.replace(
                    "Ответ на русском",
                    "ВАЖНО: Отвечай ТОЛЬКО на русском языке, без китайских символов и английских слов!\nОтвет на русском"
                )

        # Возвращаем лучший результат из попыток
        final_response = best_response if best_response else "Чем могу помочь?"

        # === НОВОЕ: Проверка на дубликаты для fallback случая ===
        if flags.is_enabled("response_deduplication") and self._is_duplicate(final_response, history):
            final_response = self._regenerate_with_diversity(prompt, context, final_response)

        self._add_to_response_history(final_response)
        # Apply post-processing before returning
        processed = self._apply_diversity(final_response, context)
        processed = self._ensure_apology(processed, context)
        return processed

    def _get_objection_counter(self, objection_type: str, collected_data: Dict) -> str:
        """
        Получить контраргумент для возражения.

        Сначала пытается получить из settings.yaml (objection.counters),
        затем использует PersonalizationEngine для персонализации.

        Args:
            objection_type: Тип возражения (price, competitor, no_time, etc.)
            collected_data: Собранные данные о клиенте

        Returns:
            Контраргумент для использования в промпте
        """
        if not objection_type:
            return ""

        # Пытаемся получить из конфига
        counter = settings.get_nested(
            f"objection.counters.{objection_type}",
            default=""
        )

        if counter:
            return counter

        # Fallback на PersonalizationEngine для персонализированного контраргумента
        return PersonalizationEngine.get_objection_counter(collected_data, objection_type)

    def _apply_legacy_personalization(self, variables: Dict[str, Any], collected_data: Dict) -> None:
        """
        Применить legacy персонализацию когда PersonalizationEngine v2 отключен.

        Заполняет bc_* переменные на основе размера компании и отрасли.
        Это гарантирует что шаблоны с {bc_value_prop} и т.д. будут корректно заполнены.

        Args:
            variables: Словарь переменных для обновления (in-place)
            collected_data: Собранные данные о клиенте
        """
        try:
            context = PersonalizationEngine.get_context(collected_data)

            # Business context (bc_* prefix)
            bc = context.get("business_context") or {}
            variables["size_category"] = context.get("size_category", "small")
            variables["bc_size_label"] = bc.get("size_label", "")
            variables["bc_pain_focus"] = bc.get("pain_focus", "")
            variables["bc_value_prop"] = bc.get("value_prop", "")
            variables["bc_objection_counter"] = bc.get("objection_counter", "")
            variables["bc_demo_pitch"] = bc.get("demo_pitch", "")

            # Industry context (ic_* prefix)
            ic = context.get("industry_context") or {}
            if ic:
                variables["industry"] = context.get("industry", "")
                variables["ic_keywords"] = ", ".join(ic.get("keywords", []))
                variables["ic_examples"] = ", ".join(ic.get("examples", []))
                variables["ic_pain_examples"] = ", ".join(ic.get("pain_examples", []))

            # Pain reference
            variables["pain_reference"] = context.get("pain_reference", "")

            logger.debug(
                "Legacy personalization applied",
                size_category=variables.get("size_category"),
                has_industry=bool(context.get("industry")),
                has_pain_ref=bool(context.get("pain_reference")),
            )
        except Exception as e:
            logger.warning(f"Legacy personalization failed: {e}")
            # Переменные уже имеют fallback значения из PERSONALIZATION_DEFAULTS

    def _clean(self, text: str) -> str:
        """Убираем лишнее и фильтруем нерусский текст"""
        import re

        text = text.strip()

        # Убираем префиксы
        for prefix in ["Ответ:", "Вы:", "Менеджер:"]:
            if text.startswith(prefix):
                text = text[len(prefix):].strip()

        # Удаляем китайские/японские/корейские символы и пунктуацию (Qwen иногда переключается)
        # Иероглифы + китайская пунктуация (。，！？：；「」『』【】)
        text = re.sub(r'[\u4e00-\u9fff\u3400-\u4dbf\u3040-\u309f\u30a0-\u30ff\u3000-\u303f\uff00-\uffef]+', '', text)

        # Удаляем английские слова ТОЛЬКО если текст преимущественно на английском
        # (Qwen language switch: >50% латиницы). Технические термины (REST, OAuth, JWT)
        # в русском тексте (<30% латиницы) сохраняются.
        russian_chars = len(re.findall(r'[а-яА-ЯёЁ]', text))
        latin_chars = len(re.findall(r'[a-zA-Z]', text))
        total_alpha = russian_chars + latin_chars

        if total_alpha > 10 and latin_chars / total_alpha > 0.5:
            # Full-language switch detected — strip non-allowed English
            def replace_english(match):
                word = match.group(0)
                if word.lower() in self.allowed_english:
                    return word
                return ''
            text = re.sub(r'\b[a-zA-Z]{2,}\b', replace_english, text)

        # Удаляем строки начинающиеся с извинений на китайском
        lines = text.split('\n')
        cleaned_lines = []
        for line in lines:
            line = line.strip()
            # Пропускаем пустые строки и строки с "..."
            if not line or line == '...':
                continue
            # Пропускаем строки которые начинаются с китайского извинения
            if '对不起' in line or '抱歉' in line:
                continue
            cleaned_lines.append(line)

        text = '\n'.join(cleaned_lines)

        # Убираем лишние пробелы
        text = re.sub(r'\s+', ' ', text).strip()

        return text

    # =========================================================================
    # Response Diversity Post-Processing
    # =========================================================================

    def _apply_diversity(self, response: str, context: Dict) -> str:
        """
        Применить post-processing для разнообразия ответов.

        Заменяет монотонные вступления (например, "Понимаю") на альтернативы.
        Управляется feature flag `response_diversity`.

        Args:
            response: Оригинальный ответ
            context: Контекст генерации (intent, state, frustration_level)

        Returns:
            Обработанный ответ
        """
        if not flags.response_diversity:
            return response

        try:
            # Формируем контекст для diversity engine
            diversity_context = {
                "intent": context.get("last_intent", ""),
                "state": context.get("state", ""),
                "frustration_level": context.get("frustration_level", 0),
            }

            result = diversity_engine.process_response(response, diversity_context)

            if result.was_modified and flags.response_diversity_logging:
                logger.info(
                    "Response diversity applied",
                    modification_type=result.modification_type,
                    opening_used=result.opening_used,
                    category=result.category_used,
                    original_start=response[:40],
                    new_start=result.processed[:40],
                )

            return result.processed

        except Exception as e:
            # Graceful degradation: return original on error
            logger.warning(f"Response diversity failed: {e}")
            return response

    # =========================================================================
    # Apology Post-Processing (SSoT: src/apology_ssot.py)
    # =========================================================================

    def _ensure_apology(self, response: str, context: Dict) -> str:
        """
        Ensure apology is present when required (guaranteed insertion).

        If LLM didn't include apology despite instruction, prepend it.
        Uses ResponseVariations for phrase selection (LRU rotation).

        SSoT: src/apology_ssot.py

        Args:
            response: Bot response from LLM
            context: Generation context with should_apologize flag

        Returns:
            Response with guaranteed apology if required
        """
        if not flags.is_enabled("apology_system"):
            return response

        if not context.get("should_apologize"):
            return response

        # Check if LLM already included apology
        if self._has_apology(response):
            return response

        try:
            # Get apology from ResponseVariations (LRU rotation)
            from src.response_variations import variations
            apology = variations.get_apology()

            logger.debug(
                "Apology prepended to response",
                apology=apology,
                response_start=response[:50],
            )

            # Prepend apology
            return f"{apology} {response}"

        except Exception as e:
            # Graceful degradation: return original on error
            logger.warning(f"Apology insertion failed: {e}")
            return response

    def _has_apology(self, response: str) -> bool:
        """
        Check if response already contains an apology phrase.

        Uses apology markers from SSoT.

        SSoT: src/apology_ssot.py

        Args:
            response: Bot response text

        Returns:
            True if response contains apology marker
        """
        from src.apology_ssot import has_apology
        return has_apology(response)

    # =========================================================================
    # НОВОЕ: Deduplication методы
    # =========================================================================

    def _compute_similarity(self, text_a: str, text_b: str) -> float:
        """
        Вычислить схожесть двух текстов (Jaccard similarity по словам).

        CRITICAL FIX: Remove punctuation BEFORE splitting to avoid mismatches.
        Russian text: "год," vs "год" vs "год." all become "год".

        Args:
            text_a: Первый текст
            text_b: Второй текст

        Returns:
            Схожесть от 0.0 до 1.0
        """
        import re

        # CRITICAL FIX: Remove punctuation BEFORE splitting
        # Russian text: "год," vs "год" vs "год." all become "год"
        a_norm = re.sub(r'[^\w\s]', '', text_a.lower().strip())
        b_norm = re.sub(r'[^\w\s]', '', text_b.lower().strip())

        # Точное совпадение
        if a_norm == b_norm:
            return 1.0

        # Jaccard similarity по словам
        words_a = set(a_norm.split())
        words_b = set(b_norm.split())

        if not words_a or not words_b:
            return 0.0

        intersection = len(words_a & words_b)
        union = len(words_a | words_b)

        return intersection / union if union > 0 else 0.0

    def _compute_semantic_similarity(self, text_a: str, text_b: str) -> float:
        """
        Вычислить семантическую схожесть текстов через эмбеддинги.

        Использует существующий retriever для генерации эмбеддингов
        и вычисляет cosine similarity.

        Args:
            text_a: Первый текст
            text_b: Второй текст

        Returns:
            Семантическая схожесть от 0.0 до 1.0
        """
        try:
            from src.knowledge_retrieval import get_retriever
            import numpy as np

            retriever = get_retriever()
            emb_a = retriever.embed_query(text_a)
            emb_b = retriever.embed_query(text_b)

            # Cosine similarity
            dot_product = np.dot(emb_a, emb_b)
            norm_a = np.linalg.norm(emb_a)
            norm_b = np.linalg.norm(emb_b)

            if norm_a == 0 or norm_b == 0:
                return 0.0

            return float(dot_product / (norm_a * norm_b))
        except Exception as e:
            logger.warning(f"Semantic similarity calculation failed: {e}")
            return 0.0  # Graceful degradation

    def _is_duplicate(self, response: str, history: List[Dict]) -> bool:
        """
        Проверить является ли ответ дубликатом предыдущих.

        Использует гибридную 2-стадийную детекцию:
        1. Быстрый Jaccard (1ms) - ловит точные/почти-точные совпадения
        2. Семантический fallback (50ms) - ловит перефразировки (только для пограничных случаев)

        Args:
            response: Новый ответ для проверки
            history: История диалога (список словарей с ключами 'user', 'bot')

        Returns:
            True если ответ слишком похож на предыдущие
        """
        if not response:
            return False

        # 1. Проверяем внутренний кэш ответов
        for prev in self._response_history[-3:]:
            # Stage 1: Fast Jaccard similarity
            jaccard_sim = self._compute_similarity(response, prev)
            if jaccard_sim > self.SIMILARITY_THRESHOLD:  # 0.70
                logger.debug(
                    "Duplicate detected (Jaccard) in response history",
                    similarity=f"{jaccard_sim:.2f}",
                    threshold=self.SIMILARITY_THRESHOLD
                )
                return True

            # Stage 2: Semantic fallback (only if Jaccard borderline)
            if 0.50 <= jaccard_sim <= 0.70:
                semantic_sim = self._compute_semantic_similarity(response, prev)
                if semantic_sim > 0.85:  # High semantic threshold
                    logger.debug(
                        "Duplicate detected (Semantic) in response history",
                        jaccard=f"{jaccard_sim:.2f}",
                        semantic=f"{semantic_sim:.2f}"
                    )
                    return True

        # 2. Проверяем историю диалога
        for turn in history[-3:]:
            bot_response = turn.get("bot", "")
            if bot_response:
                # Stage 1: Fast Jaccard similarity
                jaccard_sim = self._compute_similarity(response, bot_response)
                if jaccard_sim > self.SIMILARITY_THRESHOLD:
                    logger.debug(
                        "Duplicate detected (Jaccard) in dialogue history",
                        similarity=f"{jaccard_sim:.2f}",
                        threshold=self.SIMILARITY_THRESHOLD
                    )
                    return True

                # Stage 2: Semantic fallback (only if Jaccard borderline)
                if 0.50 <= jaccard_sim <= 0.70:
                    semantic_sim = self._compute_semantic_similarity(response, bot_response)
                    if semantic_sim > 0.85:
                        logger.debug(
                            "Duplicate detected (Semantic) in dialogue history",
                            jaccard=f"{jaccard_sim:.2f}",
                            semantic=f"{semantic_sim:.2f}"
                        )
                        return True

        return False

    def _regenerate_with_diversity(
        self,
        prompt: str,
        context: Dict,
        original_response: str,
        max_attempts: int = 4
    ) -> str:
        """
        Перегенерировать ответ с инструкцией о разнообразии.

        Args:
            prompt: Исходный промпт
            context: Контекст генерации
            original_response: Оригинальный ответ (дубликат)
            max_attempts: Максимум попыток регенерации

        Returns:
            Новый уникальный ответ или лучший из попыток
        """
        history = context.get("history", [])

        # Собираем предыдущие ответы для инструкции (диалог + внутренний кеш)
        # Увеличиваем лимит символов для лучшего контекста
        recent_responses = []
        
        # 1. Из истории диалога
        for turn in history[-3:]:
            if turn.get("bot"):
                recent_responses.append(turn["bot"][:150])
        
        # 2. Из внутреннего кеша генератора (чтобы не повторять только что сказанное)
        for resp in self._response_history[-3:]:
            if resp[:150] not in recent_responses:
                recent_responses.append(resp[:150])

        diversity_instruction = f"""
⚠️ ВАЖНО: Твой предыдущий ответ слишком похож на уже данные.
НЕ ПОВТОРЯЙ эти ответы (даже частично): {recent_responses}

Сформулируй ответ ИНАЧЕ:
- Используй ДРУГИЕ слова и синонимы
- Измени структуру предложения и порядок слов
- Если задаёшь вопрос — сформулируй его по-новому
- НЕ используй стандартные вступления из предыдущих попыток

"""
        modified_prompt = diversity_instruction + prompt

        best_response = original_response
        best_similarity = 1.0

        for attempt in range(max_attempts):
            try:
                response = self.llm.generate(modified_prompt)
                cleaned = self._clean(response)

                if not cleaned:
                    continue

                # Проверяем уникальность (использует и history, и _response_history)
                if not self._is_duplicate(cleaned, history):
                    logger.info(
                        "Regeneration successful",
                        attempt=attempt + 1
                    )
                    return cleaned

                # Сохраняем лучший результат (наименее похожий на ВСЮ историю)
                # FIX: Теперь учитываем и history, и self._response_history, 
                # чтобы "лучший" вариант не оказался дубликатом из внутреннего кеша.
                max_sim = 0.0
                
                # Сравниваем с историей диалога
                for turn in history[-3:]:
                    if turn.get("bot"):
                        sim = self._compute_similarity(cleaned, turn["bot"])
                        max_sim = max(max_sim, sim)
                
                # Сравниваем с внутренней историей генератора
                for prev in self._response_history[-3:]:
                    sim = self._compute_similarity(cleaned, prev)
                    max_sim = max(max_sim, sim)

                if max_sim < best_similarity:
                    best_similarity = max_sim
                    best_response = cleaned

            except Exception as e:
                logger.warning(f"Regeneration attempt {attempt + 1} failed: {e}")

        logger.warning(
            "Regeneration exhausted, using best attempt",
            best_similarity=f"{best_similarity:.2f}"
        )
        return best_response

    def _add_to_response_history(self, response: str) -> None:
        """Добавить ответ в историю для отслеживания дубликатов."""
        if response:
            self._response_history.append(response)
            if len(self._response_history) > self._max_response_history:
                self._response_history.pop(0)

    def reset(self) -> None:
        """Сбросить историю ответов для нового диалога."""
        self._response_history.clear()

    def _get_price_template_key(self, intent: str, action: str) -> str:
        """
        Select template for price-related questions.
        Priority: action from policy overlay > intent-based default.
        """
        # If policy overlay (price_handling mixin) selected a
        # specific pricing template via conditions (should_answer_directly,
        # price_repeated_2x), honor it. Previously this method always returned
        # answer_with_pricing, making answer_with_pricing_direct dead code.
        from src.yaml_config.constants import PRICING_CORRECT_ACTIONS
        if action in PRICING_CORRECT_ACTIONS:
            return action

        # Fallback: intent-based default (backward compatible)
        if intent == "price_question":
            return "answer_with_pricing"
        elif intent == "pricing_details":
            return "answer_pricing_details"
        return "answer_with_facts"

    def _get_objection_template_key(self, intent: str, action: str) -> str:
        """
        Выбрать шаблон для objection-related интентов.

        Каждый тип возражения получает специфичный шаблон с релевантными
        аргументами и подходом. Это позволяет:
        - objection_competitor → сравнение с конкурентом из retrieved_facts
        - objection_price → ценовые аргументы
        - objection_no_time → предложить удобное время
        - и т.д.

        Args:
            intent: Интент клиента (тип возражения)
            action: Action от state machine

        Returns:
            Ключ шаблона
        """
        # Маппинг интента на специфичный шаблон
        OBJECTION_TEMPLATE_MAP = {
            "objection_competitor": "handle_objection_competitor",
            "objection_price": "handle_objection_price",
            "objection_no_time": "handle_objection_no_time",
            "objection_think": "handle_objection_think",
            "objection_complexity": "handle_objection_complexity",
            "objection_trust": "handle_objection_trust",
            "objection_no_need": "handle_objection_no_need",
            "objection_timing": "handle_objection_timing",
        }

        template_key = OBJECTION_TEMPLATE_MAP.get(intent)

        # Проверяем существует ли специфичный шаблон
        if template_key:
            # Проверяем в FlowConfig (YAML)
            if self._flow and self._flow.get_template(template_key):
                return template_key
            # Проверяем в PROMPT_TEMPLATES (Python)
            if template_key in PROMPT_TEMPLATES:
                return template_key

        # Fallback на generic handle_objection
        return "handle_objection"


if __name__ == "__main__":
    from llm import OllamaLLM
    
    llm = OllamaLLM()
    gen = ResponseGenerator(llm)
    
    print("=== Тест генератора ===\n")
    
    # Тест 1: Приветствие
    ctx1 = {"user_message": "Привет"}
    print("Клиент: Привет")
    print(f"Бот: {gen.generate('greeting', ctx1)}\n")
    
    # Тест 2: Deflect price
    ctx2 = {
        "user_message": "Сколько стоит?",
        "history": [{"user": "Привет", "bot": "Здравствуйте!"}],
        "goal": "Узнать размер и боль",
        "missing_data": ["company_size", "pain_point"]
    }
    print("Клиент: Сколько стоит?")
    print(f"Бот: {gen.generate('deflect_and_continue', ctx2)}\n")