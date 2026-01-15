"""Prompts for LLM extraction."""

SYSTEM_PROMPT = """Ты — эксперт по извлечению структурированной информации из текста для создания баз знаний.
Твоя задача — преобразовать текстовый фрагмент в секцию базы знаний в строго заданном формате.

Важно:
- Все ключевые слова на русском языке (или English термины если уместно)
- Факты должны быть самодостаточными — не ссылаться на другие секции
- Используй markdown форматирование для facts
- Включай опечатки и разговорные формы в keywords"""


EXTRACT_SECTION_PROMPT = """Преобразуй следующий текст в секцию базы знаний.

## Текст:
{chunk_text}

{context_section}

## Требования к полям:

### topic (идентификатор):
- Формат: snake_case, только латиница и цифры
- Длина: 3-60 символов
- Отражает суть контента
- Примеры: "tariffs", "wipon_pro_pricing_123", "integration_1c"

### priority (7-10):
- 10 = критически важная информация (цены, основные функции, FAQ)
- 9 = важная информация (детали продуктов, ключевые интеграции)
- 8 = стандартная информация (дополнительные функции)
- 7 = дополнительная информация (редкие кейсы)

### category:
Выбери ОДНУ из: {categories}

### key_phrases (20-35 ФРАЗ из 2-5 слов) — ЭТО ГЛАВНОЕ!
КРИТИЧЕСКИ ВАЖНО: 75% keywords должны быть ФРАЗАМИ из нескольких слов!
Извлекай ТОЧНЫЕ фразы из текста, а не отдельные слова:

Примеры ПРАВИЛЬНЫХ фраз:
- "тариф бизнес 29900" (а не просто "тариф")
- "интеграция с 1С" (а не просто "интеграция")
- "бесплатный период 14 дней"
- "WhatsApp Business API"
- "техподдержка работает 24/7"
- "до 10000 сообщений в месяц"
- "шифрование AES-256"
- "поддержка русского языка"

### single_keywords (5-8 слов):
Только самые важные ОДИНОЧНЫЕ слова (25% от общего числа):
- Термины: api, crm, офд, aes
- Бренды: Telegram, WhatsApp, Битрикс24

### question_phrases (15-20 вопросов-фраз):
Полные вопросы которые может задать пользователь:
- "сколько стоит тариф бизнес"
- "как подключить WhatsApp Business"
- "есть ли бесплатный пробный период"
- "как интегрировать с 1С"
- "сколько сообщений можно отправить"
- "какие языки поддерживает бот"

### facts (markdown):
- Структурированный текст с информацией
- Используй **жирный** для заголовков
- Используй • маркеры для списков
- Используй таблицы | для сравнений
- Минимум 50 символов
- НЕ ссылайся на другие секции!

Ответь в JSON формате согласно schema."""


EXPAND_KEYWORDS_PROMPT = """Расширь список ключевых слов для поиска.

Базовые слова: {base_keywords}
Контекст: {context}

Сгенерируй для каждого базового слова:

1. morphological — морфологические формы (падежи, числа):
   тариф → тарифы, тарифа, тарифу, тарифом, тарифов

2. typos — частые опечатки:
   сколько → скока, сколко, скоко
   цена → ценна, цна
   бесплатно → безплатно, беслатно

3. colloquial — разговорные/сленговые формы:
   бесплатно → халява, даром, за так
   дорого → кусается, не по карману

4. transliteration — транслитерация (если применимо):
   price → прайс
   free → фри
   api → апи

Язык: русский и казахский
Ответь в JSON формате согласно schema."""


CATEGORIZE_PROMPT = """Определи категорию для следующего контента.

## Контент:
{content}

## Категории:
- analytics: аналитика, отчёты, статистика, графики
- competitors: сравнение с конкурентами, альтернативы
- employees: сотрудники, кадры, зарплата, роли
- equipment: оборудование, кассы, сканеры, принтеры
- faq: часто задаваемые вопросы, общие вопросы
- features: функции системы, возможности
- fiscal: фискальность, ОФД, чеки, налоги
- integrations: интеграции, API, подключения
- inventory: склад, товары, остатки
- mobile: мобильное приложение
- pricing: цены, тарифы, стоимость
- products: продукты, обзор системы
- promotions: акции, скидки, бонусы
- regions: регионы, доставка, города
- stability: стабильность, безопасность, бэкапы
- support: поддержка, обучение, помощь
- tis: ТИС, трёхкомпонентная система, ИП

Выбери primary_category и до 2 secondary_categories.
Укажи confidence (0.0-1.0).

Ответь в JSON формате согласно schema."""


QUALITY_CHECK_PROMPT = """Оцени качество секции базы знаний.

## Секция:
topic: {topic}
keywords: {keywords}
facts: {facts}

## Критерии оценки:

### keywords_quality (0.0-1.0):
- Покрывают ли keywords все важные слова из facts?
- Есть ли синонимы, опечатки, вопросительные формы?
- Достаточно ли разнообразие?

### facts_quality (0.0-1.0):
- Структурированы ли facts (markdown)?
- Информативны ли они?
- Самодостаточны ли (нет ссылок на другие секции)?

### completeness (0.0-1.0):
- Полная ли информация извлечена?
- Нет ли пропущенных важных деталей?

### issues:
Список проблем (если есть):
- "Мало keywords"
- "Facts содержат ссылку"
- "Нет опечаток в keywords"

### suggestions:
Предложения по улучшению (если есть).

Ответь в JSON формате согласно schema."""


def format_extract_prompt(
    chunk_text: str,
    context: str = "",
    categories: list = None,
) -> str:
    """Format extraction prompt with variables."""
    from ..config import CATEGORIES

    categories = categories or CATEGORIES

    context_section = ""
    if context:
        context_section = f"## Контекст (окружающий текст):\n{context}\n"

    return EXTRACT_SECTION_PROMPT.format(
        chunk_text=chunk_text,
        context_section=context_section,
        categories=", ".join(categories),
    )


def format_expand_keywords_prompt(base_keywords: list, context: str = "") -> str:
    """Format keyword expansion prompt."""
    return EXPAND_KEYWORDS_PROMPT.format(
        base_keywords=", ".join(base_keywords),
        context=context or "Нет контекста",
    )


def format_categorize_prompt(content: str) -> str:
    """Format categorization prompt."""
    return CATEGORIZE_PROMPT.format(content=content[:2000])


def format_quality_check_prompt(topic: str, keywords: list, facts: str) -> str:
    """Format quality check prompt."""
    return QUALITY_CHECK_PROMPT.format(
        topic=topic,
        keywords=", ".join(keywords[:30]),  # Limit for prompt size
        facts=facts[:1500],
    )
