"""
Генератор ответов — собирает промпт и вызывает LLM

Включает:
- ResponseGenerator: генерация ответов через LLM
- PersonalizationEngine: персонализация на основе собранных данных
- SafeDict: безопасная подстановка переменных в шаблоны
"""

import random
import re
from typing import Dict, List, Optional, TYPE_CHECKING, Any, Set, Tuple
from src.config import SYSTEM_PROMPT, PROMPT_TEMPLATES, KNOWLEDGE
from src.knowledge.retriever import get_retriever
from src.settings import settings
from src.logger import logger
from src.feature_flags import flags
from src.response_diversity import diversity_engine
from src.response_boundary_validator import boundary_validator
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
    "do_not_repeat_responses": "",

    # Question suppression
    "question_instruction": "Задай ОДИН вопрос по цели этапа.",
}

# Actions exempt from trailing question stripping (probe/transition templates need "?")
QUESTION_STRIP_EXEMPT_ACTIONS: set = {
    "probe_situation", "probe_problem", "probe_implication", "probe_need_payoff",
    "clarify_one_question",
    "transition_to_spin_problem", "transition_to_spin_implication",
    "transition_to_spin_need_payoff", "transition_to_presentation",
}

# Hallucination guard: intents requiring KB facts (prefix-based + explicit)
KB_GUARD_FACTUAL_INTENTS_EXPLICIT: set = {
    "price_question", "pricing_details", "cost_inquiry",
    "pricing_comparison", "comparison",
    "request_proposal", "request_invoice", "request_contract",
    "request_sla", "request_references",
    "roi_question", "case_study_request",
    "company_info_question", "experience_question",
}
KB_GUARD_ACTIONS: set = {"autonomous_respond", "continue_current_goal"}

# Actions that reach generator.generate() via the else-branch in bot.py and
# should surface a secondary price answer via blocking_with_pricing template.
# Does NOT include escalate_to_human (covered by its own template in Step 2),
# guard_offer_options or ask_clarification (bot.py bypasses generator for those).
BLOCKING_ACTIONS_FOR_SECONDARY_INJECT: frozenset = frozenset({
    "objection_limit_reached",  # ObjectionGuardSource → else → generator
    "go_back_limit_reached",    # GoBackGuardSource → else → generator
})
SECONDARY_ANSWER_ELIGIBLE: frozenset = frozenset({"price_question"})

# Layer 1 safety rules for autonomous templates (injected via {safety_rules}).
SAFETY_RULES_V2 = """ГЛАВНЫЕ ПРАВИЛА:
1. Только факты из БАЗЫ ЗНАНИЙ. Нет факта → "Уточню у коллег и вернусь с ответом."
2. Цены: ТОЛЬКО из БАЗЫ ЗНАНИЙ. Нет цифры → "Точную стоимость уточнит менеджер." Не считай, не округляй, не интерполируй. Единицы (в год / в мес) — тоже только из БАЗЫ ЗНАНИЙ.
3. Не утверждай, что уже что-то отправил/подключил/настроил, если этого нет в БАЗЕ ЗНАНИЙ.
4. Не называй конкретные имена компаний-клиентов. Нет имени в БАЗЕ ЗНАНИЙ — это ложь. Говори обобщённо: "наши клиенты".
5. Не придумывай SLA, проценты, сроки, гарантии, количество клиентов, кейсы и показатели эффективности. Любая цифра или метрика — только если она есть в БАЗЕ ЗНАНИЙ.
6. Не обещай "менеджер свяжется через N минут/часов" и не подтверждай уже назначенный звонок/демо, если этого явно нет в БАЗЕ ЗНАНИЙ или сообщении клиента."""


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

    # KB-empty handoff response pools (class-level to avoid recreation per call)
    _KB_EMPTY_CONTACT_KNOWN = [
        "Уточню у коллег и вернусь с ответом.",
        "Хороший вопрос — уточню у команды и напишу вам.",
        "Этот момент уточню у специалиста и вернусь.",
        "Передам ваш вопрос нашему специалисту — он свяжется с вами.",
        "Точный ответ уточню и напишу, как только узнаю.",
        "Проверю у коллег и сразу напишу вам.",
    ]
    _KB_EMPTY_CONTACT_UNKNOWN = [
        "Хороший вопрос — уточню у команды. Как с вами связаться?",
        "Уточню у специалиста — оставьте номер, он вам напишет.",
        "Передам вопрос менеджеру. На какой номер перезвонить?",
        "Этот момент лучше уточнить у специалиста. Оставьте контакт — он свяжется.",
        "Уточню у коллег. Удобнее позвонить или написать?",
        "Дам точный ответ через специалиста — оставьте номер или почту?",
        "Передам вопрос нашему менеджеру. Как вас набрать?",
        "Это уточню у команды — оставьте контакт, чтобы вернуться с ответом быстро.",
    ]

    _CREDENTIAL_PATTERNS = [
        re.compile(
            r'(?:логин|login)[:\s]*\+?\d[\d\s\-]{8,15}[\s,;.]*'
            r'(?:пароль|password|құпиясөз)[:\s]*\S+',
            re.IGNORECASE
        ),
        re.compile(
            r'(?:пароль|password|құпиясөз)[:\s]*\d{4,}',
            re.IGNORECASE
        ),
    ]

    def _redact_credentials(self, text: str) -> str:
        """Remove credential patterns from retrieved facts."""
        result = text
        for pattern in self._CREDENTIAL_PATTERNS:
            result = pattern.sub('[демо-доступ предоставляется по запросу]', result)
        return result

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
        self.SIMILARITY_THRESHOLD = settings.get_nested(
            "generator.similarity_threshold", 0.65
        )
        self.allowed_english = set(settings.generator.allowed_english_words)

        # === НОВОЕ: Deduplication ===
        self._response_history: List[str] = []
        self._max_response_history = 5
        self._last_generation_meta: Dict[str, Any] = {
            "requested_action": None,
            "selected_template_key": None,
            "validation_events": [],
        }
        self._last_response_embedding: Optional[List[float]] = None

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

        # Enhanced retrieval pipeline (lazy init on first autonomous call)
        self._enhanced_pipeline = None

        # Style modifier separation cache (lazy-loaded from YAML config)
        self._style_intents_cache: Optional[Set[str]] = None

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
    
    def _format_client_card(self, collected: dict) -> str:
        """Форматирует collected_data как читаемую карточку клиента для промпта."""
        FIELD_LABELS = {
            "contact_name": "Контактное лицо",
            "client_name": "Контактное лицо",
            "company_name": "Компания",
            "company_size": "Размер компании (сотрудников)",
            "business_type": "Сфера бизнеса",
            "current_tools": "Текущие инструменты",
            "pain_point": "Основная боль",
            "budget_range": "Бюджет",
            "role": "Должность",
            "timeline": "Сроки",
            "desired_outcome": "Желаемый результат",
            "urgency": "Срочность",
            "users_count": "Кол-во пользователей",
            "preferred_channel": "Канал связи",
            "contact_info": "Контакт",
            "financial_impact": "Финансовые потери",
            "pain_impact": "Влияние проблемы",
        }
        SKIP_KEYS = {
            "_dag_results", "_objection_limit_final", "option_index",
            "contact_type", "value_acknowledged", "pain_category",
            "persona", "competitor_mentioned",
        }
        lines = []
        for key, value in collected.items():
            if key in SKIP_KEYS or value is None:
                continue
            if key == "client_name" and "contact_name" in collected:
                continue
            label = FIELD_LABELS.get(key, key)
            lines.append(f"  - {label}: {value}")
        return "\n".join(lines) if lines else "(нет данных)"

    def _has_russian_fiscal_hallucination(self, text: str) -> bool:
        """Detect mention of Russian fiscal standard ФФД in response.

        Wipon is a KZ product and uses ОФД, not ФФД (Russian format).
        Any mention of 'ФФД' followed by a digit (version number) signals hallucination.
        """
        import re
        return bool(re.search(r'ФФД\s*\d', text))

    # Official Wipon tariff prices (always legitimate, even when not in retrieved_facts)
    _OFFICIAL_PRICES = frozenset({"5000", "150000", "220000", "500000", "1000000"})

    def _has_price_hallucination(self, response: str, retrieved_facts: str) -> bool:
        """Detect pricing figures in response that are NOT found in retrieved_facts.

        Fires when the response contains a price (digits + ₸/тг/тенге) that is NOT
        present in retrieved_facts AND is not an official Wipon tariff price.
        Only fires when retrieved_facts is non-empty (empty KB case handled separately).
        """
        import re
        if not retrieved_facts or len(retrieved_facts.strip()) < 30:
            return False

        price_pattern = re.compile(
            r'(\d[\d\s]{1,9}\d|\d{3,})'
            r'(?:\s*(?:₸|тг|тенге))',
            re.IGNORECASE
        )
        for m in price_pattern.finditer(response):
            raw = re.sub(r'\s+', '', m.group(1))
            if not raw.isdigit():
                continue
            # Official tariff prices are always allowed (they're in CRITICAL RULES)
            if raw in self._OFFICIAL_PRICES:
                continue
            # Check both compact ("80000") and spaced ("80 000") forms in KB.
            # Use lookbehind/lookahead to avoid "50000" matching inside "150000"
            # and "50 000" matching inside "150 000".
            spaced = f"{int(raw):,}".replace(',', ' ')
            raw_in_kb = bool(re.search(r'(?<!\d)' + raw + r'(?!\d)', retrieved_facts))
            spaced_in_kb = bool(re.search(r'(?<!\d)' + re.escape(spaced) + r'(?!\d)', retrieved_facts))
            if not raw_in_kb and not spaced_in_kb:
                logger.debug("price_hallucination_candidate", price=raw)
                return True
        return False

    @staticmethod
    def _has_iin_hallucination(response: str, user_message: str, collected_data: dict) -> bool:
        """Detect if response contains a 12-digit IIN not provided by the user.

        Returns True when the response echoes a specific 12-digit IIN that was NOT
        in the user's current message and NOT in collected_data. This prevents the
        LLM from inventing IINs like "123456789012".
        """
        # Find any 12-digit IIN-like numbers in the response
        iin_in_response = re.findall(r'\b(\d{12})\b', response)
        if not iin_in_response:
            return False
        # Collect all legitimate IINs (from user + collected_data)
        legitimate_iins = set()
        for m in re.finditer(r'\b(\d{12})\b', user_message):
            legitimate_iins.add(m.group(1))
        if collected_data.get("iin"):
            legitimate_iins.add(str(collected_data["iin"]))
        # Flag if response has an IIN not found in legitimate sources
        for iin in iin_in_response:
            if iin not in legitimate_iins:
                logger.debug("iin_hallucination_detected", fake_iin=iin)
                return True
        return False

    def _has_chinese(self, text: str) -> bool:
        """Проверяем есть ли китайские/японские/корейские/иврит/арабские символы"""
        import re
        return bool(re.search(
            r'[\u4e00-\u9fff\u3400-\u4dbf\u3040-\u309f\u30a0-\u30ff'
            r'\u0590-\u05ff\u0600-\u06ff\u0750-\u077f]',  # + Hebrew + Arabic
            text,
        ))

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

    def get_last_generation_meta(self) -> Dict[str, Any]:
        """Return metadata from the latest generate() call."""
        return dict(self._last_generation_meta)

    def get_last_response_embedding(self) -> Optional[List[float]]:
        """Embedding последнего сгенерированного ответа (кэш)."""
        return self._last_response_embedding

    def _compute_and_cache_response_embedding(self, response: str) -> Optional[List[float]]:
        """Вычисляет embedding ответа, кэширует, возвращает."""
        self._last_response_embedding = None  # Reset BEFORE attempt (prevents stale data on failure)
        try:
            retriever = get_retriever()
            if retriever is None or retriever.embedder is None:
                return None
            emb = retriever.embedder.encode(response)
            self._last_response_embedding = emb.tolist() if emb is not None else None
            return self._last_response_embedding
        except Exception:
            return None

    def _get_style_intents(self) -> Set[str]:
        """Lazy-load style intents from config (cached)."""
        if self._style_intents_cache is None:
            try:
                from src.yaml_config.constants import get_style_modifier_detection_config
                config = get_style_modifier_detection_config()
                self._style_intents_cache = set(config.get("style_intents", []))
            except Exception:
                self._style_intents_cache = set()
        return self._style_intents_cache

    def _apply_style_modifiers(
        self,
        context: Dict[str, Any],
        personalization: Any,
    ) -> Any:
        """Apply style modifiers from classification to PersonalizationResult.

        Merges TWO sources:
        1. style_modifiers from StyleModifierDetectionLayer (primary intent was style)
        2. secondary_signals from SecondaryIntentDetectionLayer (style as secondary)

        Priority: classification > behavioral signals (already applied by PersonalizationEngine v2)
        """
        if not flags.is_enabled("separate_style_modifiers"):
            return personalization

        STYLE_INTENTS = self._get_style_intents()

        # Source 1: style_modifiers from layer (via context, propagated in bot.py)
        style_modifiers = set(context.get("style_modifiers", []))

        # Source 2: secondary_signals that are style-related
        secondary_signals = context.get("secondary_signals", [])
        style_from_secondary = set(s for s in secondary_signals if s in STYLE_INTENTS)

        # Merge both sources (set removes duplicates)
        all_modifiers = style_modifiers | style_from_secondary

        if not all_modifiers:
            return personalization

        # Apply with priority: brevity > examples > summary
        if "request_brevity" in all_modifiers:
            personalization.style.verbosity = "concise"
            personalization.style.tactical_instruction += " Будь краток и по делу."
            personalization.style.applied_modifiers.append("brevity")
            all_modifiers -= {"request_examples", "example_request"}

        for modifier in all_modifiers:
            if modifier in ("request_examples", "example_request"):
                personalization.style.verbosity = "detailed"
                personalization.style.tactical_instruction += " Приведи конкретные примеры."
                personalization.style.applied_modifiers.append("examples")
            elif modifier in ("request_summary", "summary_request"):
                personalization.style.tactical_instruction += " Суммируй ключевые моменты."
                personalization.style.applied_modifiers.append("summary")

        # Track source for debugging
        if style_modifiers and not style_from_secondary:
            personalization.style.modifier_source = "classification"
        elif style_modifiers and style_from_secondary:
            personalization.style.modifier_source = "mixed"
        elif style_from_secondary:
            personalization.style.modifier_source = "secondary"

        return personalization

    def _is_factual_action(self, action: str) -> bool:
        """Return True when action already implies factual/pricing answer."""
        from src.yaml_config.constants import PRICING_CORRECT_ACTIONS

        if action in PRICING_CORRECT_ACTIONS:
            return True
        return action.startswith("answer_") or action.startswith("calculate_")

    def _select_template_key(self, intent: str, action: str, context: Dict[str, Any]) -> str:
        """
        Select template key with explicit priority:
        0) ContentRepetitionGuard actions — dedicated templates, never remap (I19)
        1) pricing-correct action from policy
        2) intent-aware pricing routing
        3) objection routing
        4) style intent request_brevity (only for non-factual actions)
        5) transition/default mapping
        """
        state = str(context.get("state", "") or "")
        is_autonomous_flow = bool(
            self._flow
            and self._flow.name == "autonomous"
            and (state.startswith("autonomous_") or state in {"greeting", "handle_objection"})
        )

        # ContentRepetitionGuard actions — dedicated templates, never remap (I19)
        if action in {"redirect_after_repetition", "escalate_repeated_content"}:
            return action

        # Autonomous flow: always use autonomous_respond template (except greeting).
        # Pricing/fact content is injected via retrieved_facts; template routing should
        # not override the autonomous LLM action.
        if is_autonomous_flow:
            passthrough_actions = {
                "soft_close",
                "close",
                "escalate_to_human",
                "guard_soft_close",
                "guard_offer_options",
                "guard_skip_phase",
                "ask_clarification",
                "offer_options",
            }
            if action in passthrough_actions:
                return action
            if intent == "greeting" and state == "greeting":
                return "greet_back"
            return "autonomous_respond"

        from src.yaml_config.constants import PRICING_CORRECT_ACTIONS

        if action in PRICING_CORRECT_ACTIONS:
            template_key = action
            logger.debug(
                "Pricing-correct action takes priority",
                intent=intent,
                action=action,
                template_key=template_key,
            )
        elif intent in self.PRICE_RELATED_INTENTS:
            template_key = self._get_price_template_key(intent, action)
            logger.debug(
                "Price-related intent detected, using pricing template",
                intent=intent,
                original_action=action,
                template_key=template_key
            )
        elif intent in self.OBJECTION_RELATED_INTENTS:
            template_key = self._get_objection_template_key(intent, action)
            logger.debug(
                "Objection-related intent detected, using specific template",
                intent=intent,
                original_action=action,
                template_key=template_key
            )
        elif intent == "request_brevity" and not self._is_factual_action(action):
            # Legacy behavior: only when style separation is OFF
            if not flags.is_enabled("separate_style_modifiers"):
                template_key = "respond_briefly"
                logger.debug(
                    "Brevity request detected, using respond_briefly template",
                    intent=intent,
                    original_action=action,
                    template_key=template_key
                )
            # With flag ON: request_brevity already refined to semantic intent by layer,
            # so this branch won't be reached. Guard clause for safety only.
        elif action.startswith("transition_to_"):
            template_key = action.replace("transition_to_", "")
        else:
            template_key = action

        # Universal answer-template forcing for repeated questions.
        # Skip for autonomous_respond: autonomous flow decides in LLM.
        _ctx_envelope = context.get("context_envelope")
        if action != "autonomous_respond" and _ctx_envelope and getattr(_ctx_envelope, 'repeated_question', None):
            from src.yaml_config.constants import INTENT_CATEGORIES, REPAIR_PROTECTED_ACTIONS
            _rq = _ctx_envelope.repeated_question
            _answerable = (
                set(INTENT_CATEGORIES.get("question", []))
                | set(INTENT_CATEGORIES.get("price_related", []))
            )
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

        spin_phase = context.get("spin_phase", "")
        if template_key == "continue_current_goal" and spin_phase and intent not in self.PRICE_RELATED_INTENTS:
            spin_template_key = f"spin_{spin_phase}"
            if self._flow and self._flow.get_template(spin_template_key):
                template_key = spin_template_key
            elif spin_template_key in PROMPT_TEMPLATES:
                template_key = spin_template_key

        return template_key

    def generate(self, action: str, context: Dict, max_retries: int = None) -> str:
        """Генерируем ответ с retry при китайских символах"""

        # Используем параметр из settings если не указано явно
        if max_retries is None:
            max_retries = self.max_retries

        # Reset metadata for this generation attempt.
        self._last_generation_meta = {
            "requested_action": action,
            "selected_template_key": None,
            "validation_events": [],
        }

        # Получаем релевантные факты из базы знаний
        intent = context.get("intent", "")
        state = context.get("state", "")
        user_message = context.get("user_message", "")

        # Prompt/policy exfiltration guard: never route such requests through LLM.
        # Keep response deterministic and safe while redirecting to business context.
        if self._is_policy_attack_message(user_message):
            response = self._policy_attack_safe_response()
            self._last_generation_meta = {
                "requested_action": action,
                "selected_template_key": "policy_attack_guard",
                "validation_events": [],
                "fact_keys": [],
            }
            self._add_to_response_history(response)
            return response

        # === AUTONOMOUS FLOW: EnhancedRetrievalPipeline (bypass CategoryRouter + CascadeRetriever) ===
        _is_autonomous = bool(
            self._flow
            and self._flow.name == "autonomous"
            and (state.startswith("autonomous_") or state == "handle_objection")
        )
        _fact_keys: List[str] = []  # Track which fact sections were used (for rotation)
        if _is_autonomous:
            from src.knowledge.autonomous_kb import load_facts_for_state

            # Keep autonomous state-context and query-context on the same KB snapshot.
            _kb = get_retriever().kb
            recently_used = set(context.get("recent_fact_keys", []))

            try:
                if self._enhanced_pipeline is None:
                    from src.knowledge.enhanced_retrieval import EnhancedRetrievalPipeline
                    self._enhanced_pipeline = EnhancedRetrievalPipeline(
                        llm=self.llm,
                        category_router=self.category_router,
                    )

                retrieved_facts, retrieved_urls, _fact_keys = self._enhanced_pipeline.retrieve(
                    user_message=user_message,
                    intent=intent,
                    state=state,
                    flow_config=self._flow,
                    kb=_kb,
                    recently_used_keys=recently_used,
                    history=context.get("history", []),
                    secondary_intents=self._get_secondary_intents(context),
                )
            except Exception as e:
                logger.error("Enhanced retrieval failed, falling back", error=str(e))
                retrieved_facts, retrieved_urls, _fact_keys = load_facts_for_state(
                    state=state,
                    flow_config=self._flow,
                    kb=_kb,
                    recently_used_keys=recently_used,
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

        # Runtime safety net: redact any credentials that slipped through
        if retrieved_facts:
            retrieved_facts = self._redact_credentials(retrieved_facts)
            # Safety net: strip conversational greeting openers injected verbatim into KB facts
            retrieved_facts = re.sub(r'(?m)^Здравствуйте[!.]?\s*', '', retrieved_facts)

        # --- KB-empty hallucination guard ---
        # Short-circuit before LLM when KB returned nothing for a factual question.
        # No LLM call, no state change — blackboard decisions remain intact.
        _kb_empty = not retrieved_facts
        _is_factual = (
            intent.startswith("question_")
            or intent.startswith("problem_")
            or intent in KB_GUARD_FACTUAL_INTENTS_EXPLICIT
        )
        if _is_autonomous and _kb_empty and _is_factual and action in KB_GUARD_ACTIONS:
            logger.info(
                "kb_empty_guard_triggered",
                intent=intent,
                action=action,
            )
            self._last_generation_meta = {
                "requested_action": action,
                "selected_template_key": "kb_empty_handoff",
                "validation_events": [],
                "fact_keys": [],
            }
            return self._kb_empty_handoff(context)

        # Форматируем URLs для включения в ответ
        formatted_urls = self._format_urls_for_response(retrieved_urls) if retrieved_urls else ""

        requested_action = action
        template_key = self._select_template_key(intent=intent, action=action, context=context)
        # Inject blocking_with_pricing when a blocking action has a secondary price question.
        if _is_autonomous and self._should_inject_secondary_answer(action, context):
            template_key = "blocking_with_pricing"
        selected_template_key = template_key

        # Mirror real template selection when fallback is triggered in _get_template().
        has_flow_template = bool(self._flow and self._flow.get_template(template_key))
        if not has_flow_template and template_key not in PROMPT_TEMPLATES:
            selected_template_key = "continue_current_goal"

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
            "collected_data": self._format_client_card(collected) if _is_autonomous else str(collected),
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
            # Autonomous flow: objection-specific framework instructions (4P/3F)
            "objection_instructions": "",
            # Question suppression (default — overridden by ResponseDirectives block)
            "question_instruction": "Задай ОДИН вопрос по цели этапа.",
            # Closing-specific data request (injected below)
            "closing_data_request": "",
            # Layer 1: shared safety rules for autonomous templates
            "safety_rules": SAFETY_RULES_V2,
            # Layer 2: dynamic state/intent rules (computed below)
            "state_gated_rules": "",
            # Hotel-staff politeness: ask name at most once, then stop repeating
            "address_instruction": self._build_address_instruction(
                collected=collected,
                history=context.get("history", []),
                intent=intent,
                frustration_level=context.get("frustration_level", 0),
                state=context.get("state", ""),
                user_message=user_message,
            ),
            "language_instruction": self._build_language_instruction(user_message),
            "stress_instruction": self._build_stress_instruction(
                intent=intent,
                frustration_level=context.get("frustration_level", 0),
                user_message=user_message,
            ),
        })
        variables["state_gated_rules"] = self._build_state_gated_rules(
            state=context.get("state", ""),
            intent=intent,
            user_message=user_message,
            history=context.get("history", []),
            collected=collected,
        )
        # Respect explicit no-contact requests: answer without pushing questions.
        _hard_no_contact_markers = (
            "контакты не дам",
            "контакт не дам",
            "не дам контакт",
            "не проси мои контакты",
            "без контакта",
            "без контактов",
        )
        _hard_no_contact = any(m in user_message.lower() for m in _hard_no_contact_markers)
        if _is_autonomous and _hard_no_contact:
            variables["question_instruction"] = (
                "⚠️ Клиент отказался давать контакты: НЕ задавай встречных вопросов в этом сообщении. "
                "Дай полезный ответ и мягко оставь открытой возможность вернуться позже."
            )
            variables["missing_data"] = ""
            variables["available_questions"] = ""

        # Human-readable labels for terminal data fields (used in closing_data_request).
        _FIELD_LABELS: dict = {
            "contact_info": "контакт (телефон или email)",
            "kaspi_phone": "номер Kaspi (для Kaspi Pay)",
            "iin": "ИИН",
            "preferred_call_time": "удобное время для созвона",
            "company_name": "название компании",
        }

        def _field_label(f: str) -> str:
            return _FIELD_LABELS.get(f, f)

        # === Autonomous closing: inject data-collection instruction ===
        # Reads terminal_state_requirements from YAML (via context) — no hardcoded field names.
        # Tiered urgency:
        #   URGENT  (⚠️ ПРЯМО ПОПРОСИ) — NO terminal is reachable yet; bot must collect.
        #   SOFT    (💡 желательно) — at least one terminal is reachable; bot may upgrade.
        #   SILENT  (empty string) — all terminals already reachable; nothing to ask.
        if _is_autonomous and context.get("state") == "autonomous_closing":
            # Anti-contact-hallucination: if we don't have contact_info yet, warn LLM
            # not to fabricate a phone number or email (e.g. "+77751234567")
            _has_contact = (
                collected.get("contact_info")
                or collected.get("kaspi_phone")
                or collected.get("phone")
                or collected.get("email")
            )
            if not _has_contact:
                _no_contact_hint = (
                    "⚠️ КОНТАКТ НЕ ПОЛУЧЕН: клиент ещё не давал телефон или email.\n"
                    "   КАТЕГОРИЧЕСКИ НЕЛЬЗЯ называть, угадывать или подтверждать "
                    "выдуманный номер телефона или email. Не пиши никаких контактных данных.\n"
                    "   Просто попроси: 'Оставьте, пожалуйста, телефон или email.'"
                )
                _existing_dna = variables.get("do_not_ask", "")
                variables["do_not_ask"] = f"{_existing_dna}\n{_no_contact_hint}" if _existing_dna else _no_contact_hint
            # Anti-IIN-hallucination: if no IIN yet, explicitly forbid mentioning any 12-digit number
            if not collected.get("iin"):
                _no_iin_hint = (
                    "⚠️ ИИН НЕ ПОЛУЧЕН: клиент ещё не давал ИИН.\n"
                    "   КАТЕГОРИЧЕСКИ НЕЛЬЗЯ называть, угадывать или «подтверждать» "
                    "выдуманный ИИН (12-значное число). Не пиши никаких 12-значных чисел.\n"
                    "   Если нужен ИИН — просто попроси: 'Укажите, пожалуйста, ваш ИИН.'"
                )
                _existing_dna = variables.get("do_not_ask", "")
                variables["do_not_ask"] = f"{_existing_dna}\n{_no_iin_hint}" if _existing_dna else _no_iin_hint
            terminal_reqs: dict = context.get("terminal_state_requirements", {})
            if terminal_reqs:
                soften_closing_request = self._should_soften_closing_request(
                    intent=intent,
                    frustration_level=context.get("frustration_level", 0),
                    user_message=user_message,
                )
                # Evaluate each terminal: reachable = all required fields present in collected_data
                reachable = [
                    t for t, fields in terminal_reqs.items()
                    if all(collected.get(f) for f in fields)
                ]
                not_reachable = [t for t in terminal_reqs if t not in reachable]

                # Iterate easiest terminal first (fewest required fields) so the
                # bot asks for the simplest blocking fields before harder ones.
                # e.g. video_call_scheduled (1 field) before payment_ready (2 fields).
                not_reachable.sort(key=lambda t: len(terminal_reqs.get(t, [])))

                # Ask only for one target terminal at a time.
                # Default = easiest terminal (usually video_call_scheduled/contact).
                target_terminal = not_reachable[0] if not_reachable else None
                if (
                    target_terminal
                    and self._is_payment_closing_signal(intent, user_message)
                    and "payment_ready" in not_reachable
                ):
                    target_terminal = "payment_ready"
                urgent_fields = [
                    f for f in (terminal_reqs.get(target_terminal, []) if target_terminal else [])
                    if not collected.get(f)
                ]

                # Snapshot isolation guard: if client JUST provided payment data in
                # this turn's message, don't ask for it again — DataExtractor will
                # extract it after response. Acknowledge receipt instead.
                _just_provided_payment_data = self._client_just_provided_payment_data(user_message)

                if urgent_fields and not reachable:
                    if _just_provided_payment_data:
                        # Client provided IIN+phone in this message — acknowledge, don't re-ask
                        variables["closing_data_request"] = (
                            "💡 Клиент только что предоставил платёжные данные (ИИН и телефон Kaspi).\n"
                            "   Поблагодари и подтверди получение. Не спрашивай снова то, что уже дали.\n"
                            "   Следующий шаг: подтверди что всё принято и менеджер свяжется.\n"
                        )
                    # URGENT: no terminal reachable — collect blocking fields,
                    # but do not force hard asks when client is in stress mode.
                    elif (
                        soften_closing_request
                        and not self._is_payment_closing_signal(intent, user_message)
                    ):
                        variables["closing_data_request"] = (
                            "⚠️ Клиент сейчас не готов к оформлению или просит без давления.\n"
                            "   Сначала коротко ответь по сути запроса.\n"
                            "   Затем мягко предложи вернуться к оформлению позже, "
                            "без требования ИИН/телефона в этом же сообщении.\n"
                        )
                    else:
                        readable_fields = ", ".join(_field_label(f) for f in urgent_fields)
                        variables["closing_data_request"] = (
                            "⚠️ ОБЯЗАТЕЛЬНО: твой ответ ДОЛЖЕН содержать вопрос про "
                            + readable_fields + ".\n"
                            "   Это единственный способ продвинуться к оформлению.\n"
                            "   Попроси кратко и естественно. Пример: '...Оставьте, пожалуйста, телефон или email.'\n"
                        )
                elif urgent_fields and reachable:
                    # SOFT: at least one terminal reachable — suggest upgrade without forcing
                    if soften_closing_request:
                        variables["closing_data_request"] = (
                            "💡 Клиент в напряжении: не форсируй сбор данных.\n"
                            "   При уместности кратко предложи вернуться к оформлению, когда будет удобно.\n"
                        )
                    else:
                        readable_fields = ", ".join(_field_label(f) for f in urgent_fields)
                        variables["closing_data_request"] = (
                            "💡 Если уместно, уточни: "
                            + readable_fields + ".\n"
                            "   Спроси в конце ответа, только если это не выглядит навязчиво.\n"
                        )
                # else: all terminals reachable — closing_data_request stays empty

        # === Autonomous flow: inject objection-specific framework instructions ===
        if _is_autonomous and intent.startswith("objection_"):
            variables["objection_instructions"] = self._build_autonomous_objection_instructions(intent)

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

        # Repeated price-question safety: answer directly with facts and avoid
        # another clarifying loop. This improves dialogue coherence under stress.
        envelope = context.get("context_envelope")
        repeated_question = getattr(envelope, "repeated_question", None) if envelope else None
        from src.yaml_config.constants import INTENT_CATEGORIES
        price_related = set(INTENT_CATEGORIES.get("price_related", []))
        has_price_signal = self._has_price_signal(user_message)
        if _is_autonomous and (
            intent in price_related
            or (repeated_question in price_related and has_price_signal)
        ):
            same_user_repeat_count = self._count_recent_same_user_message(
                context.get("history", []),
                user_message,
            )
            variables["question_instruction"] = (
                "Клиент повторно спрашивает о цене: дай конкретный ответ по стоимости "
                "из БАЗЫ ЗНАНИЙ (цифры/диапазон/тариф), БЕЗ встречных вопросов."
            )
            existing_do_not_ask = variables.get("do_not_ask", "")
            no_ask = (
                "⚠️ НЕ задавай уточняющих вопросов в этом ответе. "
                "Сначала закрой ценовой запрос фактом."
            )
            variables["do_not_ask"] = (
                f"{existing_do_not_ask}\n{no_ask}" if existing_do_not_ask else no_ask
            )
            if same_user_repeat_count >= 2:
                repeat_hint = (
                    "⚠️ Это уже повтор одного и того же ценового вопроса. "
                    "Ответь КОРОТКО (1-2 предложения), не повторяй прошлый ответ дословно, "
                    "добавь новую полезную деталь (например, 1-2 альтернативы тарифа "
                    "или формат оплаты, если есть в БЗ)."
                )
                existing_no_repeat = variables.get("do_not_repeat_responses", "")
                variables["do_not_repeat_responses"] = (
                    f"{existing_no_repeat}\n{repeat_hint}".strip()
                    if existing_no_repeat
                    else repeat_hint
                )
            prior_price_hint = self._get_last_bot_price_hint(context.get("history", []))
            if prior_price_hint:
                consistency_hint = (
                    "⚠️ Держи консистентность цен в диалоге: "
                    f"ранее уже называл(а) «{prior_price_hint}». "
                    "Не меняй цифры без явного уточнения от клиента."
                )
                existing_no_repeat = variables.get("do_not_repeat_responses", "")
                variables["do_not_repeat_responses"] = (
                    f"{existing_no_repeat}\n{consistency_hint}".strip()
                    if existing_no_repeat
                    else consistency_hint
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
                # Apply style modifiers from classification BEFORE to_prompt_variables()
                p_result = self._apply_style_modifiers(context, p_result)

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

            # Apply style instruction in legacy mode (modify variables directly).
            # Do NOT use PersonalizationResult().to_prompt_variables() here —
            # it would overwrite legacy industry/business variables with empty defaults.
            if flags.is_enabled("separate_style_modifiers"):
                style_mods = set(context.get("style_modifiers", []))
                style_additions = []
                if "request_brevity" in style_mods:
                    style_additions.append("Будь краток и по делу.")
                elif any(m in style_mods for m in ("request_examples", "example_request")):
                    style_additions.append("Приведи конкретные примеры.")
                if any(m in style_mods for m in ("request_summary", "summary_request")):
                    style_additions.append("Суммируй ключевые моменты.")
                if style_additions:
                    existing = variables.get("style_full_instruction", "")
                    variables["style_full_instruction"] = (
                        existing + " " + " ".join(style_additions)
                    ).strip()

        # === ResponseDirectives integration ===
        response_directives = context.get("response_directives")
        if response_directives and flags.context_response_directives:
            try:
                # Override directives for style modifiers BEFORE to_dict()
                if flags.is_enabled("separate_style_modifiers"):
                    style_mods = set(context.get("style_modifiers", []))
                    if "request_brevity" in style_mods:
                        response_directives.max_words = 30
                        response_directives.be_brief = True

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

                # Anti-repetition: inject previous bot responses as structured block
                if memory.get("do_not_repeat_responses"):
                    recent_responses = memory["do_not_repeat_responses"]
                    # Responses already truncated to 100 chars by _get_recent_bot_responses()
                    formatted = "\n".join(f"- {r}" for r in recent_responses[-3:])
                    variables["do_not_repeat_responses"] = (
                        "⚠️ НЕ ПОВТОРЯЙ дословно эти свои предыдущие ответы:\n"
                        f"{formatted}\n"
                        "Сформулируй мысль ДРУГИМИ словами."
                    )

                # Structured данные для templates
                variables["directives_style"] = directives_dict.get("style", {})
                variables["directives_moves"] = directives_dict.get("dialogue_moves", {})

                # Question suppression: override question_instruction + hide implicit triggers
                if response_directives.question_mode == "suppress":
                    variables["question_instruction"] = (
                        "\u26a0\ufe0f Клиент активно задаёт вопросы — НЕ задавай свои вопросы в ответ. "
                        "Отвечай развёрнуто и полезно, демонстрируя экспертизу. "
                        "Можешь добавить пример, факт или преимущество продукта."
                    )
                    variables["address_instruction"] = (
                        "ОБРАЩЕНИЕ: имя клиента неизвестно. В этом ответе НЕ спрашивай имя, "
                        "продолжай по сути запроса."
                    )
                    # Hide implicit question triggers
                    variables["missing_data"] = ""
                    variables["available_questions"] = ""
                elif response_directives.question_mode == "optional":
                    variables["question_instruction"] = (
                        "Можешь задать один вопрос если это уместно и естественно, "
                        "но НЕ обязательно."
                    )

                logger.debug(
                    "ResponseDirectives applied",
                    tone=directives_dict.get("style", {}).get("tone"),
                    max_words=directives_dict.get("style", {}).get("max_words"),
                    repair_mode=directives_dict.get("dialogue_moves", {}).get("repair_mode"),
                    question_mode=response_directives.question_mode,
                )
            except Exception as e:
                logger.warning(f"ResponseDirectives integration failed: {e}")

        # Question dedup: extract questions from last 3 full bot turns and inject into do_not_ask
        # Done OUTSIDE response_directives block so it always fires when history exists.
        # This prevents the LLM from repeating "Хотите посмотреть?" or similar CTA questions.
        _full_history_for_dedup = context.get("history", [])
        _recent_questions = self._extract_question_phrases_from_history(_full_history_for_dedup, n_turns=3)
        if _recent_questions:
            _q_lines = "\n".join(f"- {q}" for q in _recent_questions)
            _q_block = f"⚠️ Эти вопросы уже задавались — НЕ ПОВТОРЯЙ их снова:\n{_q_lines}"
            # Inject into do_not_ask (pre-user-message guard)
            _existing_dna = variables.get("do_not_ask", "")
            variables["do_not_ask"] = f"{_existing_dna}\n{_q_block}" if _existing_dna else _q_block
            # Also inject into do_not_repeat_responses (triggers the explicit line 108 rule:
            # "Если в {do_not_repeat_responses} есть ответы с похожим вопросом — смени тему")
            _existing_dnr = variables.get("do_not_repeat_responses", "")
            variables["do_not_repeat_responses"] = (
                f"{_existing_dnr}\n{_q_block}" if _existing_dnr else _q_block
            )

        # Подставляем в шаблон с безопасной подстановкой
        # SafeDict возвращает пустую строку для отсутствующих ключей,
        # предотвращая KeyError и показ {переменных} клиенту
        prompt = template.format_map(SafeDict(variables))

        # Генерируем с retry при китайских символах
        best_response = ""
        history = context.get("history", [])

        # Intervention actions have dedicated templates — skip dedup to preserve semantics (I20)
        DEDUP_EXEMPT_ACTIONS = {"redirect_after_repetition", "escalate_repeated_content",
                                "escalate_to_human", "guard_soft_close"}
        skip_dedup = requested_action in DEDUP_EXEMPT_ACTIONS

        _retrieved_facts_str = str(variables.get("retrieved_facts", ""))

        for attempt in range(max_retries):
            response = self.llm.generate(prompt)

            # Domain hallucination check: ФФД — Russian fiscal standard, not KZ
            if self._has_russian_fiscal_hallucination(response):
                logger.info("russian_fiscal_hallucination_detected", attempt=attempt)
                if attempt == 0:
                    prompt += (
                        "\n\nВАЖНО: Твой предыдущий ответ содержал 'ФФД' — это РОССИЙСКИЙ стандарт,"
                        " Wipon работает в Казахстане только с ОФД. Перепиши ответ без ФФД."
                        " Если клиент спросил про ФФД — объясни разницу ОФД/ФФД."
                    )
                continue

            # Price hallucination check: fabricated prices not present in KB facts
            if self._has_price_hallucination(response, _retrieved_facts_str):
                logger.info("price_hallucination_detected", attempt=attempt)
                if attempt == 0:
                    prompt += (
                        "\n\nВАЖНО: Твой предыдущий ответ содержал конкретные суммы в тенге,"
                        " которых НЕТ в БАЗЕ ЗНАНИЙ выше. КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО придумывать цены."
                        " Перепиши ответ: если нужной цены нет в БАЗЕ ЗНАНИЙ — скажи:"
                        " 'Точную стоимость уточнит менеджер.' Не называй никаких цифр кроме тех,"
                        " что явно указаны в БАЗЕ ЗНАНИЙ."
                    )
                continue

            # IIN hallucination check: LLM must not invent 12-digit IINs
            if self._has_iin_hallucination(response, user_message, collected):
                logger.info("iin_hallucination_detected", attempt=attempt)
                if attempt == 0:
                    prompt += (
                        "\n\nВАЖНО: Твой предыдущий ответ содержал выдуманный ИИН (12-значный номер)."
                        " КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО придумывать или повторять ИИН клиента."
                        " Перепиши ответ: вместо ИИН напиши просто 'ИИН получен'."
                        " Никаких цифр ИИН в ответе."
                    )
                continue

            # Если нет иностранного текста — проверяем на дубликаты
            if not self._has_foreign_language(response):
                cleaned = self._clean(response)

                # === НОВОЕ: Проверка на дубликаты ===
                if flags.is_enabled("response_deduplication") and not skip_dedup and self._is_duplicate(cleaned, history):
                    logger.info(
                        "Duplicate response detected, regenerating",
                        response_preview=cleaned[:50]
                    )
                    cleaned = self._regenerate_with_diversity(prompt, context, cleaned)

                # Сохраняем в историю для отслеживания
                self._add_to_response_history(cleaned)
                processed, validation_events = self._post_process_response(
                    cleaned,
                    context=context,
                    requested_action=requested_action,
                    selected_template_key=selected_template_key,
                    retrieved_facts=retrieved_facts,
                )
                self._compute_and_cache_response_embedding(processed)
                self._last_generation_meta = {
                    "requested_action": requested_action,
                    "selected_template_key": selected_template_key,
                    "validation_events": validation_events,
                    "fact_keys": _fact_keys,
                }
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
        if flags.is_enabled("response_deduplication") and not skip_dedup and self._is_duplicate(final_response, history):
            final_response = self._regenerate_with_diversity(prompt, context, final_response)

        self._add_to_response_history(final_response)
        processed, validation_events = self._post_process_response(
            final_response,
            context=context,
            requested_action=requested_action,
            selected_template_key=selected_template_key,
            retrieved_facts=retrieved_facts,
        )
        self._compute_and_cache_response_embedding(processed)
        self._last_generation_meta = {
            "requested_action": requested_action,
            "selected_template_key": selected_template_key,
            "validation_events": validation_events,
            "fact_keys": _fact_keys,
        }
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

        # Collapse obvious repetitive loops (e.g. clause repeated 3+ times).
        text = self._collapse_repetition_loops(text)

        # Убираем лишние пробелы
        text = re.sub(r'\s+', ' ', text).strip()

        return text

    @staticmethod
    def _collapse_repetition_loops(text: str) -> str:
        """Collapse repeated clauses and repeated sentence loops."""
        import re
        from collections import Counter

        if not text:
            return text

        collapsed = text

        # Case 1: exact long clause repeated many times.
        # Keep a single occurrence.
        pattern = re.compile(r'(.{18,140}?[?.!])(?:\s*\1){2,}', re.IGNORECASE)
        collapsed = pattern.sub(r'\1', collapsed)

        # Case 2: high repeated trigram density -> keep first 2 unique sentences.
        words = re.findall(r'\w+', collapsed.lower(), re.UNICODE)
        if len(words) >= 18:
            trigrams = [" ".join(words[i:i + 3]) for i in range(len(words) - 2)]
            if trigrams:
                max_tri = Counter(trigrams).most_common(1)[0][1]
                if max_tri >= 4:
                    sentences = re.split(r'(?<=[.!?])\s+', collapsed.strip())
                    unique_sentences = []
                    seen = set()
                    for s in sentences:
                        key = re.sub(r'\s+', ' ', s.strip().lower())
                        if not key or key in seen:
                            continue
                        seen.add(key)
                        unique_sentences.append(s.strip())
                        if len(unique_sentences) >= 2:
                            break
                    if unique_sentences:
                        collapsed = " ".join(unique_sentences)

        return collapsed

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
            state = str(context.get("state", "") or "")
            # Autonomous flow relies on a stable high-trust voice; avoid opener rewrites.
            if state.startswith("autonomous_") or state == "greeting":
                return response

            # In stress/conflict turns, keep wording stable and avoid "playful"
            # opening rewrites that can look dismissive.
            intent = str(context.get("intent", context.get("last_intent", "")) or "")
            frustration = int(context.get("frustration_level", 0) or 0)
            if (
                frustration >= 3
                or intent in {"request_brevity", "price_question", "rejection_soft", "farewell"}
                or intent.startswith("objection_")
            ):
                return response

            # Формируем контекст для diversity engine
            diversity_context = {
                "intent": intent,
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

        # SSoT: suppress generic canned apology for non-allowed intent domains
        # At HIGH+ frustration, safety net is preserved (function returns False)
        from src.apology_ssot import should_suppress_for_intent
        if should_suppress_for_intent(
            context.get("intent", ""),
            frustration_level=context.get("frustration_level", 0),
        ):
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

    def _post_process_response(
        self,
        response: str,
        context: Dict[str, Any],
        requested_action: str,
        selected_template_key: str,
        retrieved_facts: str,
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Apply all post-processing layers, including final response boundary validation.
        """
        processed = self._apply_diversity(response, context)
        processed = self._ensure_apology(processed, context)

        validation_events: List[Dict[str, Any]] = []
        validation_context = {
            "intent": context.get("intent", ""),
            "action": requested_action,
            "state": context.get("state", ""),
            "selected_template": selected_template_key,
            "retrieved_facts": retrieved_facts,
            "user_message": context.get("user_message", ""),
            "collected_data": context.get("collected_data", {}),
        }
        validation_result = boundary_validator.validate_response(
            processed,
            context=validation_context,
            llm=self.llm,
        )
        processed = validation_result.response
        validation_events = validation_result.validation_events

        processed = self._compress_repeated_price_response(processed, context)
        if self._should_force_no_question(context):
            processed = self._strip_trailing_question(processed)
        if self._is_low_quality_artifact(processed):
            processed = self._low_quality_fallback(context)

        # Layer 5: Post-processing safety net — strip trailing question when suppressed
        rd = context.get("response_directives")
        should_strip = (
            rd and getattr(rd, 'suppress_question', False)
            and requested_action not in QUESTION_STRIP_EXEMPT_ACTIONS
            and not getattr(rd, 'should_offer_exit', False)
            and not getattr(rd, 'prioritize_contact', False)
        )
        if should_strip:
            processed = self._strip_trailing_question(processed)

        return processed, validation_events

    def _compress_repeated_price_response(self, response: str, context: Dict[str, Any]) -> str:
        """
        Keep repeated price answers concise to avoid long loop-like responses.
        """
        try:
            intent = str(context.get("intent", "") or "")
            envelope = context.get("context_envelope")
            repeated_question = getattr(envelope, "repeated_question", None) if envelope else None
            has_price_signal = self._has_price_signal(str(context.get("user_message", "") or ""))

            from src.yaml_config.constants import INTENT_CATEGORIES
            price_related = set(INTENT_CATEGORIES.get("price_related", []))
            if (
                intent not in price_related
                and not (repeated_question in price_related and has_price_signal)
            ):
                return response

            repeat_count = self._count_recent_same_user_message(
                context.get("history", []),
                context.get("user_message", ""),
            )
            if repeat_count < 2:
                return response

            sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', response.strip()) if s.strip()]
            if not sentences:
                return response

            compact = " ".join(sentences[:2])
            if len(compact) > 280:
                compact = compact[:277].rstrip(" ,.;:") + "..."
            return compact
        except Exception:
            return response

    def _strip_trailing_question(self, text: str) -> str:
        """Remove trailing question from response when suppress_question is active."""
        sentences = re.split(r'(?<=[.!?])\s+', text.strip())
        if len(sentences) > 1 and sentences[-1].rstrip().endswith('?'):
            return ' '.join(sentences[:-1])
        return text

    @staticmethod
    def _should_force_no_question(context: Dict[str, Any]) -> bool:
        """Force no-question ending for explicit user directness/no-question requests."""
        msg = str(context.get("user_message", "") or "").lower()
        if not msg:
            return False
        hard_markers = (
            "не задавай вопрос",
            "не задавай вопросы",
            "без вопросов",
            "если еще раз задашь вопрос",
            "без лишнего",
            "контакты не дам",
            "контакт не дам",
            "без контактов",
            "без контакта",
        )
        soft_markers = (
            "без воды",
            "по делу",
            "коротко",
            "быстрее",
            "за 1 сообщение",
            "одним сообщением",
        )
        if any(m in msg for m in hard_markers):
            return True
        if any(m in msg for m in soft_markers) and int(context.get("frustration_level", 0) or 0) >= 3:
            return True
        return False

    @staticmethod
    def _is_low_quality_artifact(text: str) -> bool:
        """Detect obvious garbage/glitch outputs (e.g. 'SGDAdam')."""
        value = str(text or "").strip()
        if not value:
            return True
        cyr = len(re.findall(r"[а-яА-ЯёЁ]", value))
        latin = len(re.findall(r"[a-zA-Z]", value))
        words = re.findall(r"\w+", value, flags=re.UNICODE)
        if cyr == 0 and latin >= 5 and len(words) <= 2 and len(value) <= 24:
            return True
        if cyr < 4 and len(words) <= 2 and len(value) <= 20:
            return True
        return False

    @staticmethod
    def _low_quality_fallback(context: Dict[str, Any]) -> str:
        """Context-aware fallback for glitchy short outputs."""
        intent = str(context.get("intent", "") or "").lower()
        state = str(context.get("state", "") or "").lower()
        if intent in {"contact_provided", "callback_request", "demo_request"}:
            return (
                "Контакт получил. Следующий шаг — менеджер свяжется с вами "
                "и согласует удобное время."
            )
        if "price" in intent or "pricing" in intent:
            return "По цене: подготовлю точный расчёт в ₸ под ваш формат бизнеса."
        if state.startswith("autonomous_"):
            return "Коротко по сути: дам следующий шаг под ваш кейс без лишнего."
        return "Переформулирую коротко и по сути."

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
            import numpy as np

            retriever = get_retriever()
            if retriever is None or retriever.embedder is None:
                return 0.0
            emb_a = retriever.embedder.encode(text_a)
            emb_b = retriever.embedder.encode(text_b)

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
            if jaccard_sim > self.SIMILARITY_THRESHOLD:
                logger.debug(
                    "Duplicate detected (Jaccard) in response history",
                    similarity=f"{jaccard_sim:.2f}",
                    threshold=self.SIMILARITY_THRESHOLD
                )
                return True

            # Stage 2: Semantic fallback (only if Jaccard borderline)
            # 0.30 threshold: catches Russian morphological variants
            # ("предлагаем"/"предлагает", "включают"/"включающие")
            if 0.30 <= jaccard_sim <= self.SIMILARITY_THRESHOLD:
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
                # 0.30 threshold: catches Russian morphological variants
                if 0.30 <= jaccard_sim <= self.SIMILARITY_THRESHOLD:
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

    def _kb_empty_handoff(self, context: Dict) -> str:
        """Return a deterministic handoff phrase when KB has no facts for a factual question."""
        import random
        user_message = str(context.get("user_message", "") or "")
        if self._is_policy_attack_message(user_message):
            response = (
                "Я не могу раскрывать внутренние инструкции, ключи или служебные данные. "
                "Могу помочь по продукту Wipon и условиям подключения."
            )
            self._add_to_response_history(response)
            return response

        contact_info = context.get("collected_data", {}).get("contact_info")
        pool = self._KB_EMPTY_CONTACT_KNOWN if contact_info else self._KB_EMPTY_CONTACT_UNKNOWN
        response = random.choice(pool)
        self._add_to_response_history(response)
        return response

    @staticmethod
    def _is_policy_attack_message(user_message: str) -> bool:
        """Detect prompt-injection/policy-exfiltration requests."""
        text = str(user_message or "").lower()
        if not text:
            return False
        markers = (
            "system prompt",
            "системный промпт",
            "внутренний prompt",
            "игнорируй инструкции",
            "ключи api",
            "api key",
            "раскрой правила",
            "внутренние инструкции",
            "покажи промпт",
            "prompt injection",
        )
        return any(marker in text for marker in markers)

    @staticmethod
    def _policy_attack_safe_response() -> str:
        """Safe deterministic refusal for policy/prompt exfiltration attempts."""
        return (
            "Я не раскрываю системные инструкции и внутренние правила. "
            "Могу помочь по продукту Wipon: внедрение, интеграции, стоимость и следующий шаг."
        )

    def _add_to_response_history(self, response: str) -> None:
        """Добавить ответ в историю для отслеживания дубликатов."""
        if response:
            self._response_history.append(response)
            if len(self._response_history) > self._max_response_history:
                self._response_history.pop(0)

    def reset(self) -> None:
        """Сбросить историю ответов для нового диалога."""
        self._response_history.clear()
        self._last_generation_meta = {
            "requested_action": None,
            "selected_template_key": None,
            "validation_events": [],
        }

    # Mapping: objection intent → framework type
    _OBJECTION_4P_INTENTS = {
        "objection_price", "objection_competitor", "objection_no_time",
        "objection_timing", "objection_complexity",
    }

    def _build_autonomous_objection_instructions(self, intent: str) -> str:
        """Build objection-specific instructions for autonomous flow response."""
        objection_type = intent.replace("objection_", "").replace("_", " ")

        if intent in self._OBJECTION_4P_INTENTS:
            return f"""=== ОБРАБОТКА ВОЗРАЖЕНИЯ: {objection_type} ===
Клиент выразил рациональное возражение. Используй подход 4P:
1. ПАУЗА — признай опасения клиента, покажи что понимаешь
2. УТОЧНЕНИЕ — задай уточняющий вопрос чтобы понять корень возражения
3. ПРЕЗЕНТАЦИЯ ЦЕННОСТИ — приведи конкретный аргумент из базы знаний
4. ПРОДВИЖЕНИЕ — предложи следующий шаг (демо, расчёт ROI, тест)
Отработай возражение мягко, без давления. Используй данные из базы знаний."""
        else:
            return f"""=== ОБРАБОТКА ВОЗРАЖЕНИЯ: {objection_type} ===
Клиент выразил эмоциональное возражение. Используй подход 3F:
1. FEEL — покажи что понимаешь чувства клиента ("Да, это важный момент...")
2. FELT — приведи социальное доказательство ("Многие клиенты изначально думали так же...")
3. FOUND — покажи результат ("Но после внедрения они отметили...")
Проявляй эмпатию. Не спорь с эмоциями. Приведи конкретный пример из базы знаний."""

    def _build_state_gated_rules(
        self,
        state: str,
        intent: str,
        user_message: str,
        history: List[Dict[str, Any]],
        collected: Dict[str, Any],
    ) -> str:
        """Build Layer-2 rules that appear only when state/intent makes them relevant."""
        rules: List[str] = []
        state_value = str(state or "")
        intent_value = str(intent or "")
        message_lower = str(user_message or "").lower()
        is_autonomous_context = state_value.startswith("autonomous_") or state_value == "greeting"

        history_tail = history[-4:] if isinstance(history, list) else []
        history_user_lower = " ".join(
            str(turn.get("user", "") or "")
            for turn in history_tail
            if isinstance(turn, dict)
        ).lower()

        # Closing-only IIN guard. Conditional wording avoids conflict with anti-IIN hint
        # when IIN is still absent in collected_data.
        if state_value == "autonomous_closing":
            rules.append(
                "⚠️ ИИН: Если клиент даёт ИИН, не повторяй 12-значное число в ответе — "
                "подтверди фразой «ИИН получен». Если клиент ИИН не давал — не придумывай и не подтверждай выдуманные цифры."
            )

        discount_keywords = ("скидку", "скидка", "скидок", "скидки", "дешевле", "акция", "акции")
        discount_triggered = (
            intent_value == "request_discount"
            or any(keyword in message_lower for keyword in discount_keywords)
        )
        if discount_triggered and len(rules) < 2:
            rules.append(
                "⚠️ СКИДКИ: не придумывай индивидуальные акции или проценты. "
                "Если в БАЗЕ ЗНАНИЙ нет точных условий скидки, скажи: "
                "«Актуальные условия скидок уточнит менеджер»."
            )

        competitor_names = ("iiko", "poster", "r-keeper", "1с", "1c", "умаг", "beksar", "paloma")
        price_concession_words = ("дороже", "дешевле", "цена", "стоимость")
        has_competitor_context = any(
            name in message_lower or name in history_user_lower
            for name in competitor_names
        )
        has_price_concession = any(word in message_lower for word in price_concession_words)
        if has_competitor_context and has_price_concession and len(rules) < 2:
            rules.append(
                "⚠️ КОНКУРЕНТЫ: не придумывай сравнительные цифры по конкурентам. "
                "Если в БАЗЕ ЗНАНИЙ нет точного сравнения цен/условий — признай это и предложи "
                "уточнить детали у менеджера."
            )

        explicit_buy_markers = (
            "готов покупать",
            "готов купить",
            "хочу купить",
            "выставляйте счет",
            "выставьте счет",
            "выставь счет",
            "хочу счет",
            "счёт выставляйте",
            "оплачу",
            "как оплатить",
            "оформим",
            "оформляйте",
        )
        if (
            is_autonomous_context
            and state_value != "autonomous_closing"
            and any(marker in message_lower for marker in explicit_buy_markers)
        ):
            rules.append(
                "⚠️ КЛИЕНТ ГОТОВ ПОКУПАТЬ: не возвращайся в discovery/квалификацию. "
                "Подтверди готовность, коротко опиши следующий шаг и мягко переведи к оформлению "
                "(контакт/счёт), без лишних вопросов о бизнесе или боли."
            )

        hard_no_contact_markers = (
            "контакты не дам",
            "контакт не дам",
            "не дам контакт",
            "не проси мои контакты",
            "без контакта",
            "без контактов",
        )
        if is_autonomous_context and any(marker in message_lower for marker in hard_no_contact_markers):
            rules.append(
                "⚠️ КЛИЕНТ ОТКАЗАЛСЯ ОТ КОНТАКТОВ: не запрашивай телефон/email повторно в этом ответе. "
                "Дай полезный следующий шаг без обязательной передачи контактов."
            )

        if is_autonomous_context and (
            intent_value in {"request_sla", "request_references", "question_security", "question_integrations"}
            or any(k in message_lower for k in ("sla", "rpo", "rto", "шифрован", "безопас", "аудит"))
        ):
            rules.append(
                "⚠️ ТЕХНИЧЕСКИЕ ФАКТЫ: отвечай только тем, что есть в БАЗЕ ЗНАНИЙ. "
                "Если конкретного параметра нет (SLA, RPO/RTO, стандарты) — прямо скажи, что уточнишь."
            )

        if not rules:
            return ""

        formatted = "\n".join(f"- {rule}" for rule in rules)
        return f"STATE-GATED ПРАВИЛА:\n{formatted}"

    @staticmethod
    def _has_address_question_in_history(history: list) -> bool:
        """Return True if bot already asked how to address the client."""
        if not isinstance(history, list):
            return False
        markers = (
            "к вам обращаться",
            "как вас зовут",
            "как к вам обращаться",
            "как могу к вам обращаться",
        )
        for turn in history:
            if not isinstance(turn, dict):
                continue
            bot_text = str(turn.get("bot", "") or "").lower()
            if any(m in bot_text for m in markers):
                return True
        return False

    @staticmethod
    def _build_address_instruction(
        collected: dict,
        history: list = None,
        intent: str = "",
        frustration_level: int = 0,
        state: str = "",
        user_message: str = "",
    ) -> str:
        """Build conditional ОБРАЩЕНИЕ instruction with one-time ask behavior."""
        name = collected.get("contact_name") or collected.get("client_name") or ""
        if name:
            return (f'ОБРАЩЕНИЕ: клиента зовут "{name}" — '
                    f'используй "господин/госпожа {name}" или "{name}".')

        # In stressful/direct exchanges, avoid asking name and keep focus.
        stressful_intents = {
            "request_brevity",
            "price_question",
            "pricing_details",
            "rejection",
            "rejection_soft",
            "no_need",
            "no_problem",
            "farewell",
        }
        if (
            frustration_level >= 3
            or intent in stressful_intents
            or intent.startswith("objection_")
            or str(state).startswith("autonomous_closing")
        ):
            return (
                "ОБРАЩЕНИЕ: имя клиента неизвестно. НЕ спрашивай имя в этом ответе; "
                "продолжай по сути запроса."
            )

        # In autonomous stages outside greeting, keep momentum and avoid
        # re-centering the dialog around the name.
        if str(state).startswith("autonomous_") and intent not in {"greeting", "small_talk"}:
            return (
                "ОБРАЩЕНИЕ: имя клиента неизвестно. Не спрашивай имя; "
                "сфокусируйся на текущем запросе."
            )

        directness_markers = (
            "без воды",
            "коротко",
            "быстрее",
            "по делу",
            "за 1 сообщение",
            "одним сообщением",
            "не задавай вопрос",
            "контакты не дам",
            "контакт не дам",
            "без контактов",
            "без контакта",
        )
        low_msg = str(user_message or "").lower()
        if any(marker in low_msg for marker in directness_markers):
            return (
                "ОБРАЩЕНИЕ: клиент просит максимально кратко. "
                "Не спрашивай имя в этом ответе."
            )

        if ResponseGenerator._has_address_question_in_history(history or []):
            return (
                "ОБРАЩЕНИЕ: имя клиента неизвестно, но ты уже спрашивал его ранее. "
                "НЕ повторяй вопрос про имя; продолжай диалог по сути."
            )
        return (
            'ОБРАЩЕНИЕ: имя клиента НЕИЗВЕСТНО — один раз мягко вплети '
            '"как к вам обращаться?" в ответ. НЕ придумывай имя/фамилию.'
        )

    @staticmethod
    def _is_payment_closing_signal(intent: str, user_message: str) -> bool:
        """Detect explicit purchase/payment intent during autonomous closing.

        NOTE: `agreement` is intentionally excluded — it's too broad (covers both
        "I agree to a demo" and "I agree to buy"). Payment routing requires
        explicit payment words or dedicated payment-specific intents.
        """
        explicit_intents = {
            "request_invoice",
            "request_contract",
            "payment_terms",
            "ready_to_buy",
        }
        if intent in explicit_intents:
            return True
        msg = str(user_message or "").lower()
        lexical_triggers = ("оплат", "счет", "договор", "купить", "иин", "бин", "kaspi pay", "каспи пей")
        return any(token in msg for token in lexical_triggers)

    @staticmethod
    def _client_just_provided_payment_data(user_message: str) -> bool:
        """Detect if client message appears to contain payment data (IIN, Kaspi phone).

        Used to avoid re-asking for data that was literally just provided.
        Snapshot isolation means DataExtractor hasn't run yet — trust the message.
        """
        import re
        msg = str(user_message or "")
        has_iin = bool(re.search(r'ИИН\s*:?\s*\d{12}', msg, re.IGNORECASE))
        has_kaspi = bool(re.search(r'(?:kaspi|каспи|касса)\s*:?\s*[+\d]{10,}', msg, re.IGNORECASE))
        has_plain_iin = bool(re.search(r'\b\d{12}\b', msg))  # 12 consecutive digits = IIN
        return (has_iin or has_plain_iin) and (has_kaspi or bool(re.search(r'\b8\d{9}\b', msg)))

    @staticmethod
    def _should_soften_closing_request(
        intent: str,
        frustration_level: int,
        user_message: str,
    ) -> bool:
        """Decide whether closing data collection should be softened this turn."""
        if int(frustration_level or 0) >= 3:
            return True

        if intent in {"rejection", "rejection_soft", "farewell"} or intent.startswith("objection_"):
            return True

        # Snapshot isolation: if client JUST provided payment data, don't ask again.
        # DataExtractor will handle extraction after this turn.
        if intent == "contact_provided" and ResponseGenerator._client_just_provided_payment_data(user_message):
            return True

        msg = str(user_message or "").lower()
        resistance_markers = (
            "без воды",
            "без вопросов",
            "не задавай",
            "не спрашивай",
            "контакты не дам",
            "контакт не дам",
            "телефон потом",
            "телефон позже",
            "телефон кейін",
            "не сейчас",
            "иначе пока",
            "заканчиваем",
            "не трать время",
            "быстрее",
            "по делу",
        )
        return any(marker in msg for marker in resistance_markers)

    @staticmethod
    def _build_language_instruction(user_message: str) -> str:
        """
        Build lightweight language guidance to reduce code-switch degradation.
        """
        import re

        msg = str(user_message or "").lower()
        kz_letters = bool(re.search(r"[әіңғүұқөһ]", msg))
        ru_letters = bool(re.search(r"[а-яё]", msg))
        kz_words = (
            "сәлем", "салем", "бағасы", "қанша", "жоқ", "керек",
            "ұсынасыз", "кейін", "маған", "нақты", "қазақша",
        )
        has_kz_words = sum(1 for w in kz_words if w in msg) >= 2

        if (kz_letters or has_kz_words) and ru_letters:
            return (
                "ЯЗЫК: сообщение смешанное (казахский+русский). "
                "Отвечай ПОНЯТНО на русском (можно вкрапить 1-2 казахских слова по смыслу), "
                "без повторяющихся фраз."
            )
        if kz_letters or has_kz_words:
            return (
                "ЯЗЫК: отвечай на казахском простыми короткими фразами. "
                "Не повторяй одинаковые предложения."
            )
        return ""

    @staticmethod
    def _build_stress_instruction(intent: str, frustration_level: int, user_message: str) -> str:
        """Build brevity/sales focus hint for rushed or high-friction turns."""
        text = str(user_message or "").lower()
        direct_markers = (
            "без воды",
            "по делу",
            "коротко",
            "быстрее",
            "в 1 сообщение",
            "за 1 сообщение",
            "докажи",
        )
        instructions: list[str] = []
        if (
            int(frustration_level or 0) >= 3
            or intent in {"request_brevity", "price_question", "pricing_details"}
            or any(m in text for m in direct_markers)
        ):
            instructions.append(
                "РЕЖИМ КРАТКОСТИ: 1-2 предложения, сначала ключевой факт из БАЗЫ ЗНАНИЙ. "
                "Затем добавь ОДНУ выгоду только если она явно подтверждена фактами. Без лишней воды и "
                "без встречных вопросов, если клиент просит быстрее/кратко."
            )

        contact_refusal_markers = (
            "контакты не дам",
            "контакт не дам",
            "без контактов",
            "без контакта",
            "номер не дам",
            "телефон не дам",
        )
        if any(m in text for m in contact_refusal_markers):
            instructions.append(
                "КОНТАКТ-ОГРАНИЧЕНИЕ: клиент не даёт контакт. НЕ обещай отправить демо/документы "
                "и НЕ обещай счёт/оформление без обязательных данных. "
                "Дай полезный ответ в чате и мягко предложи вернуться к оформлению позже."
            )

        return "\n".join(instructions)

    @staticmethod
    def _count_recent_same_user_message(history: list, user_message: str) -> int:
        """Count consecutive identical user messages at the end of history."""
        if not isinstance(history, list) or not user_message:
            return 0

        def _norm(text: str) -> str:
            return re.sub(r"\s+", " ", str(text or "").strip().lower())

        target = _norm(user_message)
        count = 0
        for turn in reversed(history):
            if not isinstance(turn, dict):
                break
            if _norm(turn.get("user", "")) == target:
                count += 1
            else:
                break
        return count

    @staticmethod
    def _has_price_signal(user_message: str) -> bool:
        """Detect explicit price cues in current user message."""
        text = str(user_message or "").lower()
        if not text:
            return False
        keywords = (
            "цена",
            "сколько",
            "стоим",
            "тариф",
            "₸",
            "тг",
            "тенге",
            "баға",
            "бағасы",
            "қанша",
        )
        return any(k in text for k in keywords)

    @staticmethod
    def _get_last_bot_price_hint(history: list) -> str:
        """Extract the most recent price-like snippet from bot history."""
        if not isinstance(history, list):
            return ""

        patterns = [
            r"(\d[\d\s]{1,12}\s*(?:₸|тг|тенге)\s*(?:/?\s*(?:мес|месяц|год|в год|в месяц))?)",
            r"(от\s+\d[\d\s]{1,12}\s*(?:₸|тг|тенге))",
        ]
        for turn in reversed(history):
            if not isinstance(turn, dict):
                continue
            bot_text = str(turn.get("bot", "") or "")
            if not bot_text:
                continue
            for pattern in patterns:
                m = re.search(pattern, bot_text, flags=re.IGNORECASE)
                if m:
                    return re.sub(r"\s+", " ", m.group(1)).strip()
        return ""

    @staticmethod
    def _extract_question_phrases_from_history(history: list, n_turns: int = 3) -> list:
        """Extract question sentences from the last N bot turns in full history.

        Uses full (non-truncated) bot responses so questions at the end of long
        responses are captured. Returns deduplicated list of questions (≤80 chars)
        to inject into do_not_ask so the LLM won't repeat the same questions.
        """
        questions = []
        seen: set = set()
        bot_turns = [t for t in history if isinstance(t, dict) and t.get("bot")]
        for turn in bot_turns[-n_turns:]:
            text = str(turn.get("bot", "")).strip()
            # Split into sentence fragments on sentence-ending punctuation
            parts = re.split(r"(?<=[.!?])\s+", text)
            for part in parts:
                part = part.strip()
                if part.endswith("?") and len(part) > 10:
                    key = part.lower()[:60]
                    if key not in seen:
                        seen.add(key)
                        questions.append(part[:80])
        return questions

    def _get_secondary_intents(self, context: dict) -> list:
        """Return secondary_intents list from context_envelope, or empty list."""
        envelope = context.get("context_envelope")
        return list(getattr(envelope, "secondary_intents", None) or [])

    def _should_inject_secondary_answer(self, action_key: str, context: dict) -> bool:
        """
        Return True when a blocking action should be overridden with
        blocking_with_pricing to answer a secondary price question.

        Conditions:
        - action_key is in BLOCKING_ACTIONS_FOR_SECONDARY_INJECT
        - At least one secondary intent is in SECONDARY_ANSWER_ELIGIBLE
        """
        si = self._get_secondary_intents(context)
        return (
            action_key in BLOCKING_ACTIONS_FOR_SECONDARY_INJECT
            and any(s in SECONDARY_ANSWER_ELIGIBLE for s in si)
        )

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
