"""
Генератор ответов — собирает промпт и вызывает LLM

Включает:
- ResponseGenerator: генерация ответов через LLM
- PersonalizationEngine: персонализация на основе собранных данных
"""

from typing import Dict, List, Optional
from config import SYSTEM_PROMPT, SYSTEM_PROMPT_BASE, PROMPT_TEMPLATES, KNOWLEDGE
from knowledge.retriever import get_retriever
from settings import settings
from logger import logger


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
    def __init__(self, llm):
        self.llm = llm
        # Параметры из settings
        self.max_retries = settings.generator.max_retries
        self.history_length = settings.generator.history_length
        self.retriever_top_k = settings.generator.retriever_top_k
        self.allowed_english = set(settings.generator.allowed_english_words)

        # CategoryRouter: LLM-классификация категорий перед поиском
        self.category_router = None
        if settings.get_nested("category_router.enabled", False):
            from knowledge.category_router import CategoryRouter
            self.category_router = CategoryRouter(
                llm=llm,
                top_k=settings.get_nested("category_router.top_k", 3),
                fallback_categories=settings.get_nested(
                    "category_router.fallback_categories",
                    ["faq", "features"]
                )
            )
            logger.info("CategoryRouter initialized", top_k=self.category_router.top_k)
    
    def get_facts(self, company_size: int = None) -> str:
        """Получить факты о продукте"""
        # Явная проверка на None, чтобы 0 не считался False
        # (хотя бизнес с 0 сотрудников нереален, лучше быть явным)
        if company_size is not None and company_size > 0:
            # Подбираем тариф
            if company_size <= 5:
                tariff = KNOWLEDGE["pricing"]["basic"]
            elif company_size <= 25:
                tariff = KNOWLEDGE["pricing"]["team"]
            else:
                tariff = KNOWLEDGE["pricing"]["business"]
            
            total = tariff["price"] * company_size
            discount = KNOWLEDGE["discount_annual"]
            annual = total * (1 - discount / 100)
            
            return f"""Тариф: {tariff['name']}
Цена: {tariff['price']}₽/мес за человека
На {company_size} чел: {total}₽/мес
При оплате за год: {annual:.0f}₽/мес (скидка {discount}%)"""
        
        return ", ".join(KNOWLEDGE["features"])
    
    def format_history(self, history: List[Dict]) -> str:
        """Форматируем историю"""
        if not history:
            return "(начало разговора)"

        lines = []
        # Используем параметр из settings
        for turn in history[-self.history_length:]:
            lines.append(f"Клиент: {turn.get('user', '')}")
            if turn.get("bot"):
                lines.append(f"Вы: {turn['bot']}")
        
        return "\n".join(lines)
    
    def _has_chinese(self, text: str) -> bool:
        """Проверяем есть ли китайские/японские/корейские символы"""
        import re
        return bool(re.search(r'[\u4e00-\u9fff\u3400-\u4dbf\u3040-\u309f\u30a0-\u30ff]', text))

    def _has_english(self, text: str) -> bool:
        """Проверяем есть ли английские слова (минимум 2 буквы подряд)"""
        import re
        # Ищем английские слова (минимум 2 латинские буквы подряд)
        # Исключаем: CRM, API, OK, ID и подобные аббревиатуры из settings

        # Находим все английские слова
        english_words = re.findall(r'\b[a-zA-Z]{2,}\b', text)

        # Проверяем есть ли недопустимые английские слова
        for word in english_words:
            if word.lower() not in self.allowed_english:
                return True
        return False

    def _has_foreign_language(self, text: str) -> bool:
        """Проверяем есть ли иностранный текст (китайский или английский)"""
        return self._has_chinese(text) or self._has_english(text)

    def generate(self, action: str, context: Dict, max_retries: int = None) -> str:
        """Генерируем ответ с retry при китайских символах"""

        # Используем параметр из settings если не указано явно
        if max_retries is None:
            max_retries = self.max_retries

        # Получаем релевантные факты из базы знаний
        retriever = get_retriever()
        intent = context.get("intent", "")
        state = context.get("state", "")
        user_message = context.get("user_message", "")

        # Определяем категории через LLM (если CategoryRouter включён)
        categories = None
        if self.category_router and user_message:
            categories = self.category_router.route(user_message)
            logger.debug(
                "CategoryRouter selected categories",
                categories=categories,
                query=user_message[:50]
            )

        # Вызываем retriever с категориями
        retrieved_facts = retriever.retrieve(
            message=user_message,
            intent=intent,
            state=state,
            categories=categories,
            top_k=self.retriever_top_k
        )

        # Выбираем шаблон
        if action.startswith("transition_to_"):
            template_key = action.replace("transition_to_", "")
        else:
            template_key = action

        # Для SPIN-фаз: если action == "continue_current_goal" и есть spin_phase,
        # используем специфический SPIN-шаблон вместо generic continue_current_goal
        spin_phase = context.get("spin_phase", "")
        if template_key == "continue_current_goal" and spin_phase:
            spin_template_key = f"spin_{spin_phase}"
            if spin_template_key in PROMPT_TEMPLATES:
                template_key = spin_template_key

        template = PROMPT_TEMPLATES.get(template_key, PROMPT_TEMPLATES["continue_current_goal"])

        # Собираем переменные
        collected = context.get("collected_data", {})
        facts = self.get_facts(collected.get("company_size"))

        # SPIN-специфичные данные
        current_tools = collected.get("current_tools", "не указано")
        business_type = collected.get("business_type", "не указано")
        pain_impact = collected.get("pain_impact", "не определено")
        financial_impact = collected.get("financial_impact", "")
        desired_outcome = collected.get("desired_outcome", "не сформулирован")
        spin_phase = context.get("spin_phase", "")

        # Tone instruction из контекста (Phase 2: Естественность диалога)
        tone_instruction = context.get("tone_instruction", "")

        # Формируем SYSTEM_PROMPT с tone_instruction
        # Если tone_instruction пустой - используем пустую строку
        system_prompt = SYSTEM_PROMPT.format(tone_instruction=tone_instruction)

        variables = {
            "system": system_prompt,
            "user_message": user_message,
            "history": self.format_history(context.get("history", [])),
            "goal": context.get("goal", ""),
            "collected_data": str(collected),
            "missing_data": ", ".join(context.get("missing_data", [])) or "всё собрано",
            "company_size": collected.get("company_size", "?"),
            "pain_point": collected.get("pain_point", "?"),
            "facts": facts,
            # База знаний
            "retrieved_facts": retrieved_facts or "Информация по этому вопросу будет уточнена.",
            "company_info": retriever.get_company_info(),
            # SPIN-специфичные данные
            "current_tools": current_tools,
            "business_type": business_type,
            "pain_impact": pain_impact,
            "financial_impact": financial_impact,
            "desired_outcome": desired_outcome,
            "spin_phase": spin_phase,
            # Phase 2: Tone instruction (для обратной совместимости в шаблонах)
            "tone_instruction": tone_instruction,
        }

        # Подставляем в шаблон
        try:
            prompt = template.format(**variables)
        except KeyError as e:
            print(f"Missing variable: {e}")
            prompt = template

        # Генерируем с retry при китайских символах
        best_response = ""
        for attempt in range(max_retries):
            response = self.llm.generate(prompt)

            # Если нет иностранного текста — сразу возвращаем
            if not self._has_foreign_language(response):
                return self._clean(response)

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
        return best_response if best_response else "Чем могу помочь?"
    
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

        # Удаляем английские слова (кроме разрешённых из settings)
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


if __name__ == "__main__":
    from llm import OllamaLLM
    
    llm = OllamaLLM()
    gen = ResponseGenerator(llm)
    
    print("=== Тест генератора ===\n")
    
    # Тест 1: Приветствие
    ctx1 = {"user_message": "Привет"}
    print(f"Клиент: Привет")
    print(f"Бот: {gen.generate('greeting', ctx1)}\n")
    
    # Тест 2: Deflect price
    ctx2 = {
        "user_message": "Сколько стоит?",
        "history": [{"user": "Привет", "bot": "Здравствуйте!"}],
        "goal": "Узнать размер и боль",
        "missing_data": ["company_size", "pain_point"]
    }
    print(f"Клиент: Сколько стоит?")
    print(f"Бот: {gen.generate('deflect_and_continue', ctx2)}\n")