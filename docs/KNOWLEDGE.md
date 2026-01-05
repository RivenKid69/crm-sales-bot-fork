# Knowledge Base — База знаний Wipon

## Обзор

База знаний содержит структурированную информацию о продуктах и услугах Wipon. Используется для предоставления точных ответов на вопросы клиентов.

**Статистика:**
- **446 секций** в **18 YAML файлах**
- **27 категорий** знаний
- Компания: Wipon (Казахстанская IT-компания с 2014 года, 50,000+ клиентов)

## Структура модуля

```
knowledge/
├── __init__.py         # Публичный API (WIPON_KNOWLEDGE, get_retriever)
├── base.py             # Структуры данных (KnowledgeSection, KnowledgeBase)
├── loader.py           # Загрузчик YAML файлов
├── lemmatizer.py       # Лемматизация для поиска
├── retriever.py        # CascadeRetriever (3-этапный поиск)
└── data/               # YAML-файлы базы знаний
    ├── _meta.yaml      # Метаданные (company, stats)
    ├── pricing.yaml    # Тарифы (24 секции)
    ├── products.yaml   # Продукты (10 секций)
    ├── features.yaml   # Функции (3 секции)
    ├── integrations.yaml   # Интеграции (24 секции)
    ├── support.yaml    # Техподдержка (70 секций)
    ├── equipment.yaml  # Оборудование (60 секций)
    ├── tis.yaml        # Товарно-информационная система (132 секции)
    ├── analytics.yaml  # Аналитика (27 секций)
    ├── inventory.yaml  # Складской учёт (21 секция)
    ├── employees.yaml  # Управление персоналом (21 секция)
    ├── fiscal.yaml     # Фискализация (7 секций)
    ├── mobile.yaml     # Мобильное приложение (5 секций)
    ├── promotions.yaml # Акции и скидки (10 секций)
    ├── stability.yaml  # Стабильность (14 секций)
    ├── regions.yaml    # Регионы (4 секции)
    ├── faq.yaml        # Часто задаваемые вопросы (3 секции)
    └── other.yaml      # Прочее (11 секций)
```

## Категории знаний

| Категория | Секций | Описание |
|-----------|--------|----------|
| tis | 132 | Товарно-информационная система (ТИС) |
| support | 70 | Техподдержка и обслуживание |
| equipment | 60 | Оборудование (кассы, принтеры, сканеры) |
| analytics | 27 | Аналитика и отчёты |
| pricing | 24 | Тарифы и стоимость |
| integrations | 24 | Интеграции (1С, Kaspi, Telegram) |
| inventory | 21 | Складской учёт |
| employees | 21 | Управление персоналом |
| stability | 14 | Стабильность и надёжность |
| products | 10 | Продукты Wipon |
| promotions | 10 | Акции и скидки |
| fiscal | 7 | Фискализация |
| mobile | 5 | Мобильное приложение |
| regions | 4 | Регионы присутствия |
| features | 3 | Функции системы |
| faq | 3 | Часто задаваемые вопросы |
| audience | 1 | Целевая аудитория |
| benefits | 1 | Преимущества |
| competitors | 1 | Конкуренты |
| getting_started | 1 | Начало работы |
| contacts | 1 | Контакты |
| partnership | 1 | Партнёрство |
| updates | 1 | Обновления |
| cases | 1 | Кейсы |
| requirements | 1 | Требования |
| security | 1 | Безопасность |
| migration | 1 | Миграция |

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

## Публичный API

### Использование WIPON_KNOWLEDGE

```python
from knowledge import WIPON_KNOWLEDGE

# Информация о компании
print(WIPON_KNOWLEDGE.company_name)  # "Wipon"
print(WIPON_KNOWLEDGE.company_description)

# Все секции
print(f"Всего секций: {len(WIPON_KNOWLEDGE.sections)}")  # 446

# По категории
pricing = WIPON_KNOWLEDGE.get_by_category("pricing")
print(f"Секций о тарифах: {len(pricing)}")  # 24

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

В `_meta.yaml` увеличить `total_sections`:

```yaml
stats:
  total_sections: 447  # было 446
  last_updated: '2026-01-05'
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
# [OK] pricing.yaml: 24 секции
# [OK] products.yaml: 10 секций
# ...
# [OK] Всего: 446 секций (ожидалось: 446)
```

## Производительность

| Операция | Время |
|----------|-------|
| Загрузка базы знаний | ~100ms |
| Индексация эмбеддингов | ~30s (один раз при старте) |
| Exact search (1 запрос) | ~1ms |
| Lemma search (1 запрос) | ~5ms |
| Semantic search (1 запрос) | ~50ms |

Рекомендации:
- Exact match покрывает 70%+ запросов
- Для ускорения старта: `use_embeddings: false`
- Для максимальной точности: оставить все 3 этапа
