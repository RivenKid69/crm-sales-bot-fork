# Knowledge Base — База знаний Wipon

## Обзор

База знаний содержит структурированную информацию о продуктах и услугах Wipon. Используется для предоставления точных ответов на вопросы клиентов.

**Статистика:**
- **1969 секций** в **17 YAML файлах**
- **17 категорий** знаний
- Компания: Wipon (Казахстанская IT-компания с 2014 года, 50,000+ клиентов)

## Структура модуля

```
knowledge/
├── __init__.py         # Публичный API (WIPON_KNOWLEDGE, get_retriever)
├── base.py             # Структуры данных (KnowledgeSection, KnowledgeBase)
├── loader.py           # Загрузчик YAML файлов
├── lemmatizer.py       # Лемматизация для поиска
├── retriever.py        # CascadeRetriever (3-этапный поиск)
├── category_router.py  # LLM-классификация категорий
├── reranker.py         # Cross-encoder переоценка результатов
└── data/               # YAML-файлы базы знаний
    ├── _meta.yaml      # Метаданные (company, stats)
    ├── equipment.yaml  # Оборудование (316 секций)
    ├── pricing.yaml    # Тарифы (286 секций)
    ├── products.yaml   # Продукты (273 секции)
    ├── support.yaml    # Техподдержка (201 секция)
    ├── tis.yaml        # Товарно-информационная система (191 секция)
    ├── regions.yaml    # Регионы (130 секций)
    ├── inventory.yaml  # Складской учёт (93 секции)
    ├── features.yaml   # Функции (90 секций)
    ├── integrations.yaml   # Интеграции (86 секций)
    ├── fiscal.yaml     # Фискализация (68 секций)
    ├── analytics.yaml  # Аналитика (63 секции)
    ├── employees.yaml  # Управление персоналом (55 секций)
    ├── stability.yaml  # Стабильность (45 секций)
    ├── mobile.yaml     # Мобильное приложение (35 секций)
    ├── promotions.yaml # Акции и скидки (26 секций)
    ├── competitors.yaml # Конкуренты (7 секций)
    └── faq.yaml        # Часто задаваемые вопросы (4 секции)
```

## Категории знаний

| Категория | Секций | Описание |
|-----------|--------|----------|
| equipment | 316 | Оборудование (кассы, принтеры, сканеры) |
| pricing | 286 | Тарифы и стоимость |
| products | 273 | Продукты Wipon |
| support | 201 | Техподдержка и обслуживание |
| tis | 191 | Товарно-информационная система (ТИС) |
| regions | 130 | Регионы Казахстана |
| inventory | 93 | Складской учёт |
| features | 90 | Функции системы |
| integrations | 86 | Интеграции (1С, Kaspi, Telegram) |
| fiscal | 68 | Фискализация |
| analytics | 63 | Аналитика и отчёты |
| employees | 55 | Управление персоналом |
| stability | 45 | Стабильность и надёжность |
| mobile | 35 | Мобильное приложение |
| promotions | 26 | Акции и скидки |
| competitors | 7 | Конкуренты |
| faq | 4 | Часто задаваемые вопросы |

## Формат YAML секции

```yaml
sections:
- topic: unique_topic_id       # Уникальный идентификатор темы
  priority: 5                  # Приоритет 1-10 (выше = важнее)
  category: pricing            # Категория (опционально, берётся из файла)
  keywords:                    # Ключевые слова для поиска
  - ключевое слово 1
  - ключевое слово 2
  - опечатка ключевого слова   # Можно добавлять опечатки
  facts: |                     # Факты (многострочный текст)
    Информация о теме.

    Можно использовать:
    • Списки
    • Таблицы в markdown
    | Столбец 1 | Столбец 2 |
    |-----------|-----------|
    | Значение  | Значение  |
```

### Пример секции (pricing.yaml)

```yaml
- topic: tariffs
  priority: 10
  keywords:
  - тариф
  - цена
  - стоимость
  - сколько стоит
  - прайс
  - скока          # опечатка
  - ценник
  facts: |
    Тарифы Wipon:

    | Тариф | Торговых точек | Возможности |
    |-------|----------------|-------------|
    | **Mini** | 1 | Базовый учёт и касса |
    | **Lite** | 1-2 | Расширенный функционал |
    | **Standard** | до 3 | + Кадры, аналитика |
    | **Pro** | до 5 | Полный функционал |

    • Wipon Kassa — БЕСПЛАТНО (входит во все тарифы)
    • Дополнительные услуги: обучение, интеграции, выезд специалиста
    • Рассрочка на оборудование до 12 месяцев
```

## CascadeRetriever — 3-этапный поиск

```
Запрос пользователя
         │
         ▼
┌────────────────────┐
│  1. Exact Match    │  keyword как подстрока в запросе
│  (score >= 1.0)    │  + бонус за целое слово (+0.5)
└────────┬───────────┘
         │ не найдено
         ▼
┌────────────────────┐
│  2. Lemma Match    │  пересечение лемматизированных множеств
│  (score >= 0.15)   │  Формула: query_coverage * 0.5 + jaccard * 0.3 + keyword_coverage * 0.2
└────────┬───────────┘
         │ не найдено
         ▼
┌────────────────────┐
│  3. Semantic Match │  cosine similarity эмбеддингов
│  (score >= 0.5)    │  Модель: ai-forever/ru-en-RoSBERTa
└────────┬───────────┘
         │ низкий score
         ▼
┌────────────────────┐
│  4. CategoryRouter │  LLM-классификация категорий (опционально)
│  (fallback)        │  Qwen3:8b-fast определяет релевантные категории
└────────┬───────────┘
         │ при необходимости
         ▼
┌────────────────────┐
│  5. Reranker       │  Cross-encoder переоценка (опционально)
│  (BAAI/bge-v2-m3)  │  Переранжирование top-k результатов
└────────────────────┘
```

### Этап 1: Exact Match

Поиск keywords как подстрок в запросе:

```python
# Запрос: "сколько стоит тариф"
# Keyword: "тариф"
# → keyword.lower() in query.lower() → True
# → score += 1.0
# → Если целое слово (\b) → score += 0.5
# → Итого: 1.5
```

### Этап 2: Lemma Match

Сравнение лемматизированных множеств:

```python
# Запрос: "какие есть возможности?"
# → query_lemmas: {"какой", "быть", "возможность"}

# Секция keywords: ["возможности", "функции"]
# → entry_lemmas: {"возможность", "функция"}

# Пересечение: {"возможность"}
# query_coverage = 1/3 = 0.33
# keyword_coverage = 1/2 = 0.5
# jaccard = 1/4 = 0.25

# score = 0.5 * 0.33 + 0.3 * 0.25 + 0.2 * 0.5 = 0.34
```

### Этап 3: Semantic Match

Косинусное сходство эмбеддингов:

```python
# Модель: ai-forever/ru-en-RoSBERTa
# query_embedding = model.encode("как автоматизировать склад?")
# section_embedding = section.embedding

# score = cosine_similarity(query_embedding, section_embedding)
# Если score >= 0.5 → секция включается в результаты
```

### Этап 4: CategoryRouter (LLM-классификация)

При низком score или сложных запросах включается LLM-классификатор:

```python
# Запрос: "как подключить 1С к Wipon?"
# CategoryRouter (Qwen3:8b-fast) определяет: ["integrations", "features"]
# Поиск сужается до релевантных категорий
# Результаты переоцениваются в контексте определённых категорий

# Настройки (settings.yaml):
category_router:
  enabled: true
  top_k: 3  # количество возвращаемых категорий
  fallback_categories:
    - "faq"
```

### Этап 5: Reranker (Cross-encoder)

При низком score результаты переоцениваются cross-encoder моделью:

```python
# Модель: BAAI/bge-reranker-v2-m3 (мультиязычный)
# Берём top-k кандидатов и переранжируем
# Cross-encoder учитывает взаимодействие query и document

# Настройки (settings.yaml):
reranker:
  enabled: true
  model: "BAAI/bge-reranker-v2-m3"
  threshold: 0.5  # порог ниже которого включается
  candidates_count: 10  # сколько кандидатов переоценивать
```

## Публичный API

### Использование WIPON_KNOWLEDGE

```python
from knowledge import WIPON_KNOWLEDGE

# Информация о компании
print(WIPON_KNOWLEDGE.company_name)  # "Wipon"
print(WIPON_KNOWLEDGE.company_description)

# Все секции
print(f"Всего секций: {len(WIPON_KNOWLEDGE.sections)}")  # 1969

# По категории
pricing = WIPON_KNOWLEDGE.get_by_category("pricing")
print(f"Секций о тарифах: {len(pricing)}")  # 286

# По теме
tariffs = WIPON_KNOWLEDGE.get_by_topic("tariffs")
print(tariffs.facts)
```

### Использование CascadeRetriever

```python
from knowledge import get_retriever

retriever = get_retriever()

# Простой поиск (возвращает строку для LLM)
facts = retriever.retrieve("сколько стоит Wipon", intent="price_question")
print(facts)

# Детальный поиск (возвращает SearchResult)
results = retriever.search("интеграция с 1С", category="integrations")
for r in results:
    print(f"{r.section.topic}: {r.score:.2f} ({r.stage.value})")
    print(f"  Keywords: {r.matched_keywords}")

# Поиск со статистикой
results, stats = retriever.search_with_stats("аналитика продаж")
print(f"Этап: {stats['stage_used']}")
print(f"Время: {stats['total_time_ms']:.2f}ms")
```

### Использование CategoryRouter

```python
from knowledge.category_router import CategoryRouter

router = CategoryRouter()

# Классификация запроса
categories = router.classify("как подключить 1С?")
print(categories)  # ['integrations', 'features', 'support']

# С учётом контекста
categories = router.classify(
    "сколько стоит?",
    context={"spin_phase": "situation"}
)
```

### Использование Reranker

```python
from knowledge.reranker import Reranker

reranker = Reranker()

# Переоценка результатов
query = "как настроить интеграцию?"
candidates = retriever.search(query, top_k=10)
reranked = reranker.rerank(query, candidates)

for r in reranked[:3]:
    print(f"{r.section.topic}: {r.score:.2f}")
```

## Добавление новых секций

### 1. Выбрать файл или создать новый

Выберите существующий YAML файл по категории или создайте новый в `knowledge/data/`.

### 2. Добавить секцию

```yaml
# В конец файла, например support.yaml
- topic: new_support_topic      # Уникальный идентификатор
  priority: 5                   # 1-10
  keywords:
  - ключевое слово
  - синоним
  - опечатка ключевго слова
  facts: |
    Факты о новой теме.

    • Пункт 1
    • Пункт 2
```

### 3. Обновить метаданные

В `_meta.yaml` увеличить `total_sections` и обновить count категории:

```yaml
stats:
  total_sections: 1240  # было 1239
  last_updated: '2026-01-06'
  categories:
  - name: support
    count: 157  # было 156
```

### 4. Проверить валидность

```bash
python scripts/validate_knowledge_yaml.py
```

### 5. Запустить тесты

```bash
pytest tests/test_knowledge_yaml.py -v
pytest tests/test_cascade_retriever.py -v
```

## Рекомендации по keywords

### Хорошие keywords

```yaml
keywords:
- тариф              # Основное слово
- тарифы             # Множественное число
- цена               # Синоним
- стоимость          # Синоним
- сколько стоит      # Фраза
- прайс              # Сленг
- ценник             # Разговорное
- скока              # Опечатка
- сколко             # Опечатка
```

### Плохие keywords

```yaml
keywords:
- Wipon              # Слишком общее (совпадёт везде)
- система            # Слишком общее
- для                # Стоп-слово
- и                  # Стоп-слово
```

## Настройки retriever (settings.yaml)

```yaml
retriever:
  # Включить семантический поиск
  use_embeddings: true

  # Модель для эмбеддингов
  embedder_model: "ai-forever/ru-en-RoSBERTa"

  # Пороги для каждого этапа
  thresholds:
    exact: 1.0      # Минимальный score для exact match
    lemma: 0.15     # Минимальный score для lemma match
    semantic: 0.5   # Минимальный score для semantic match

  # Количество результатов по умолчанию
  default_top_k: 2

reranker:
  # Включить reranker fallback
  enabled: true

  # Модель cross-encoder
  model: "BAAI/bge-reranker-v2-m3"

  # Порог score ниже которого включается reranker
  threshold: 0.5

  # Сколько кандидатов брать для reranking
  candidates_count: 10

category_router:
  # Включить LLM-классификацию категорий
  enabled: true

  # Количество категорий для возврата
  top_k: 3

  # Категории по умолчанию при ошибке LLM
  fallback_categories:
    - "faq"
```

## Маппинг интентов на категории

При поиске CascadeRetriever использует маппинг интентов на категории:

```python
INTENT_TO_CATEGORY = {
    "price_question": ["pricing"],
    "question_features": ["features", "products"],
    "question_integrations": ["integrations"],
    "objection_competitor": ["competitors", "benefits"],
    "objection_price": ["pricing", "benefits"],
    "agreement": ["pricing", "support", "contacts"],
    "greeting": [],      # Поиск по всем категориям
    "rejection": [],     # Поиск по всем категориям
}
```

Это позволяет сузить область поиска и повысить точность.

## Тестирование

```bash
# Валидация YAML файлов
pytest tests/test_knowledge_yaml.py -v

# Тесты базы знаний
pytest tests/test_knowledge.py -v

# Тесты CascadeRetriever
pytest tests/test_cascade_retriever.py -v

# Продвинутые тесты каскадного поиска
pytest tests/test_cascade_advanced.py -v

# Тесты CategoryRouter
pytest tests/test_category_router*.py -v

# Тесты Reranker
pytest tests/test_reranker.py -v

# Стресс-тест базы знаний
python scripts/stress_test_knowledge.py
```

## Валидация YAML

Скрипт `scripts/validate_knowledge_yaml.py` проверяет:

1. **Корректность YAML** — синтаксис файлов
2. **Наличие обязательных полей** — topic, keywords, facts
3. **Уникальность topics** — нет дубликатов
4. **Соответствие total_sections** — количество в _meta.yaml
5. **Наличие keywords** — минимум 1 keyword на секцию

```bash
python scripts/validate_knowledge_yaml.py

# Вывод:
# [OK] equipment.yaml: 183 секции
# [OK] tis.yaml: 166 секций
# [OK] support.yaml: 156 секций
# ...
# [OK] Всего: 1239 секций (ожидалось: 1239)
```

## Производительность

| Операция | Время |
|----------|-------|
| Загрузка базы знаний | ~100ms |
| Индексация эмбеддингов | ~100s (один раз при старте, 1969 секций) |
| Exact search (1 запрос) | ~1ms |
| Lemma search (1 запрос) | ~5ms |
| Semantic search (1 запрос) | ~50ms |
| CategoryRouter (1 запрос) | ~500ms (LLM call) |
| Reranker (10 кандидатов) | ~100ms |

Рекомендации:
- Exact match покрывает 70%+ запросов
- Для ускорения старта: `use_embeddings: false`
- Для максимальной точности: включить все этапы + reranker
- CategoryRouter включать при сложных запросах

## История изменений

| Дата | Секций | Изменения |
|------|--------|-----------|
| 2026-01-07 | 1969 | Расширены все категории, особенно equipment, pricing, regions |
| 2026-01-06 | 1722 | Расширены все категории, добавлены секции 1200-1700 |
| 2026-01-06 | 1239 | Добавлены секции 1100-1200, competitors вместо other |
| 2026-01-05 | 1100 | Оптимизация keywords для 83%+ точности |
| 2026-01-04 | 1000 | Добавлен CategoryRouter (98.8% точность) |
| 2026-01-03 | 900 | Добавлены секции 800-900 |
