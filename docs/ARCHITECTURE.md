# Архитектура CRM Sales Bot

## Обзор

CRM Sales Bot — чат-бот для продажи CRM-системы Wipon. Использует методологию SPIN Selling для квалификации клиентов и ведёт диалог от приветствия до закрытия сделки.

## Компоненты системы

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              SalesBot                                        │
│                             (bot.py)                                         │
│      Оркестрация: classifier → state_machine → generator                     │
└─────────────────┬───────────────────────────────┬───────────────────────────┘
                  │                               │
    ┌─────────────▼─────────────┐   ┌─────────────▼─────────────┐
    │    HybridClassifier       │   │     StateMachine          │
    │    (classifier/)          │   │   (state_machine.py)      │
    │                           │   │                           │
    │ • Определение интента     │   │ • SPIN flow логика        │
    │ • Извлечение данных       │   │ • Приоритеты обработки    │
    │ • Нормализация текста     │   │ • Умное пропускание фаз   │
    │ • Контекстная классификация│  │ • 10 состояний            │
    └───────────────────────────┘   └─────────────┬─────────────┘
                                                  │
                  ┌───────────────────────────────▼───────────────┐
                  │           ResponseGenerator                   │
                  │            (generator.py)                     │
                  │                                               │
                  │ • Генерация ответов через LLM                 │
                  │ • Промпт-инжиниринг по action                 │
                  │ • Интеграция с базой знаний                   │
                  │ • Retry при иностранном тексте                │
                  └────────────────┬──────────────────────────────┘
                                   │
          ┌────────────────────────┼────────────────────────┐
          │                        │                        │
┌─────────▼─────────┐   ┌──────────▼──────────┐   ┌─────────▼─────────┐
│    OllamaLLM      │   │  CascadeRetriever   │   │      config       │
│    (llm.py)       │   │   (knowledge/)      │   │    (config.py)    │
│                   │   │                     │   │                   │
│ • qwen3:8b-fast   │   │ • 3-этапный поиск   │   │ • INTENT_ROOTS    │
│ • /no_think mode  │   │ • 446 YAML секций   │   │ • SALES_STATES    │
│ • Streaming       │   │ • ru-en-RoSBERTa    │   │ • Промпт-шаблоны  │
└───────────────────┘   └─────────────────────┘   └───────────────────┘
          │                        │
          │              ┌─────────▼─────────┐
          │              │     settings      │
          │              │  (settings.yaml)  │
          │              │                   │
          │              │ • LLM параметры   │
          │              │ • Retriever пороги│
          │              │ • Classifier веса │
          └──────────────┴───────────────────┘
```

## Поток данных

### 1. Входящее сообщение → Классификация

```python
# bot.py:process()
user_message = "нас 10 человек, теряем клиентов"

# Нормализация (опечатки, сленг, слитный текст)
normalized = "нас 10 человек теряем клиентов"

# Классификация интента с контекстом SPIN-фазы
{
    "intent": "situation_provided",
    "confidence": 0.85,
    "extracted_data": {
        "company_size": 10,
        "pain_point": "теряем клиентов"
    }
}
```

### 2. Классификация → State Machine

```python
# state_machine.py:process()
input: intent="situation_provided", extracted_data={...}

# Проверка приоритетов:
# 1. Вопросы (price_question, etc.) → answer_question
# 2. Rejection → soft_close
# 3. SPIN прогресс → переход к следующей фазе

output: {
    "action": "transition_to_spin_problem",
    "next_state": "spin_problem",
    "collected_data": {"company_size": 10, "pain_point": "теряем клиентов"},
    "spin_phase": "problem"
}
```

### 3. State Machine → Generator

```python
# generator.py:generate()
action = "transition_to_spin_problem"
context = {
    "user_message": "нас 10 человек, теряем клиентов",
    "collected_data": {"company_size": 10, "pain_point": "теряем клиентов"},
    "spin_phase": "problem"
}

# 1. Получение фактов из CascadeRetriever
retrieved_facts = retriever.retrieve(message, intent, state)

# 2. Выбор промпт-шаблона по action
template = PROMPT_TEMPLATES["spin_problem"]

# 3. Подстановка контекста + LLM генерация
response = "Понял, команда из 10 человек. Расскажите подробнее — как именно теряете клиентов?"
```

## SPIN Selling Flow

```
greeting
    │
    ▼
spin_situation ──────── Собираем: company_size, current_tools, business_type
    │
    ▼
spin_problem ─────────── Собираем: pain_point
    │
    ▼
spin_implication ─────── Собираем: pain_impact, financial_impact
    │                    (пропускается при high_interest=True)
    ▼
spin_need_payoff ─────── Собираем: desired_outcome, value_acknowledged
    │                    (пропускается при high_interest=True)
    ▼
presentation ─────────── Персонализированная презентация Wipon
    │
    ├──► handle_objection ──► presentation (если "дорого")
    │
    ▼
close ────────────────── Запрос контакта
    │
    ├──► success (получили контакт)
    └──► soft_close (отказ)
```

## Приоритеты обработки интентов

State Machine обрабатывает интенты в порядке приоритета:

| Приоритет | Интенты | Действие |
|-----------|---------|----------|
| 0 | Финальное состояние | Остаться в состоянии |
| 1 | `rejection` | Немедленный переход в `soft_close` |
| 2 | State-specific rules | `deflect_and_continue` для SPIN |
| 3 | `price_question`, `question_features`, `question_integrations` | Ответить на вопрос |
| 4 | SPIN-интенты | Проверка прогресса, переход по фазам |
| 5 | Переходы по интенту | Стандартные переходы |
| 6 | `data_complete` | Автопереход при сборе данных |
| 7 | `any` | Автопереход (для greeting) |
| 8 | Default | Остаться в текущем состоянии |

## Модули

### classifier/ — Классификация интентов

```
classifier/
├── __init__.py          # Публичный API
├── normalizer.py        # TextNormalizer, TYPO_FIXES (663), SPLIT_PATTERNS (170)
├── hybrid.py            # HybridClassifier (оркестратор)
├── intents/
│   ├── patterns.py      # PRIORITY_PATTERNS (214 паттернов)
│   ├── root_classifier.py   # Быстрая классификация по корням
│   └── lemma_classifier.py  # Fallback через pymorphy
└── extractors/
    └── data_extractor.py    # Извлечение structured data
```

Подробнее: [CLASSIFIER.md](./CLASSIFIER.md)

### knowledge/ — База знаний

```
knowledge/
├── __init__.py         # Публичный API (WIPON_KNOWLEDGE, get_retriever)
├── base.py             # KnowledgeSection, KnowledgeBase
├── loader.py           # Загрузчик YAML файлов
├── lemmatizer.py       # Лемматизация для поиска
├── retriever.py        # CascadeRetriever (3-этапный поиск)
└── data/               # 18 YAML файлов (446 секций)
    ├── _meta.yaml      # Метаданные
    ├── pricing.yaml    # Тарифы
    ├── products.yaml   # Продукты
    ├── tis.yaml        # Товарно-информационная система (132)
    ├── support.yaml    # Техподдержка (70)
    ├── equipment.yaml  # Оборудование (60)
    └── ...
```

**Категории знаний (топ-10 по размеру):**
- `tis` — Товарно-информационная система (132 секции)
- `support` — Техподдержка (70 секций)
- `equipment` — Оборудование (60 секций)
- `analytics` — Аналитика (27 секций)
- `pricing` — Тарифы (24 секции)
- `integrations` — Интеграции (24 секции)
- `inventory` — Складской учёт (21 секция)
- `employees` — Управление персоналом (21 секция)
- `stability` — Стабильность (14 секций)
- `products` — Продукты (10 секций)

Подробнее: [KNOWLEDGE.md](./KNOWLEDGE.md)

### CascadeRetriever — 3-этапный поиск

```
Запрос пользователя
         │
         ▼
┌────────────────────┐
│  1. Exact Match    │  keyword как подстрока в запросе
│  (score >= 1.0)    │  + бонус за целое слово
└────────┬───────────┘
         │ не найдено
         ▼
┌────────────────────┐
│  2. Lemma Match    │  пересечение лемматизированных множеств
│  (score >= 0.15)   │  query_coverage * 0.5 + jaccard * 0.3 + keyword_coverage * 0.2
└────────┬───────────┘
         │ не найдено
         ▼
┌────────────────────┐
│  3. Semantic Match │  cosine similarity эмбеддингов
│  (score >= 0.5)    │  ai-forever/ru-en-RoSBERTa
└────────────────────┘
```

### state_machine.py — Управление состояниями

Конечный автомат с SPIN-логикой:
- 10 состояний (greeting → success/soft_close)
- Проверка `required_data` и `optional_data` для каждого состояния
- Умное пропускание фаз I/N при `high_interest`
- Контекст для классификатора (`last_action`, `last_intent`)

### generator.py — Генерация ответов

- Выбор промпт-шаблона по action
- Подстановка контекста (collected_data, history)
- Интеграция с CascadeRetriever для вопросов о продукте
- Вызов LLM (Ollama/Qwen3:8b-fast)
- Retry при китайских символах или английском тексте (max 3 попытки)
- Фильтрация нерусского текста из ответа

### settings.py + settings.yaml — Конфигурация

Централизованное хранилище параметров:

```yaml
llm:
  model: "qwen3:8b-fast"
  base_url: "http://localhost:11434"
  timeout: 60

retriever:
  use_embeddings: true
  embedder_model: "ai-forever/ru-en-RoSBERTa"
  thresholds:
    exact: 1.0
    lemma: 0.15
    semantic: 0.5

generator:
  max_retries: 3
  history_length: 4
  retriever_top_k: 2

classifier:
  weights:
    root_match: 1.0
    phrase_match: 2.0
    lemma_match: 1.5
  thresholds:
    high_confidence: 0.7
    min_confidence: 0.3
```

Подробнее: [SETTINGS.md](./SETTINGS.md)

### config.py — Конфигурация интентов и промптов

Центральное хранилище:
- `INTENT_ROOTS` — корни слов для быстрой классификации
- `INTENT_PHRASES` — фразы для лемматизации
- `SALES_STATES` — конфигурация состояний SPIN
- `PROMPT_TEMPLATES` — шаблоны промптов для LLM
- `SYSTEM_PROMPT` — системный промпт
- `KNOWLEDGE` — встроенные факты о тарифах
- `QUESTION_INTENTS` — интенты-вопросы

## Расширение системы

### Добавление нового интента

1. Добавить корни в `config.INTENT_ROOTS`
2. Добавить фразы в `config.INTENT_PHRASES`
3. (опционально) Добавить паттерн в `classifier/intents/patterns.py`
4. Добавить правила обработки в `state_machine.py` (transitions/rules)
5. Добавить промпт-шаблон в `config.PROMPT_TEMPLATES`

### Добавление новой SPIN-фазы

1. Создать состояние в `config.SALES_STATES`:
```python
"spin_new_phase": {
    "goal": "Цель фазы",
    "spin_phase": "new_phase",
    "required_data": ["field1"],
    "optional_data": ["field2"],
    "transitions": {
        "relevant_intent": "next_state",
        "data_complete": "next_state",
        "rejection": "soft_close"
    },
    "rules": {
        "price_question": "deflect_and_continue"
    }
}
```
2. Добавить в `SPIN_PHASES` и `SPIN_STATES` в `state_machine.py`
3. Создать промпт-шаблоны в `config.PROMPT_TEMPLATES`

### Расширение базы знаний

1. Создать/редактировать YAML файл в `knowledge/data/`:
```yaml
sections:
- topic: unique_topic_id
  priority: 5
  keywords:
  - ключевое слово 1
  - ключевое слово 2
  facts: |
    Факты о теме.
    Многострочный текст.
```
2. Обновить `_meta.yaml` — увеличить `total_sections`
3. Запустить валидацию: `python scripts/validate_knowledge_yaml.py`

### Изменение параметров

Все параметры вынесены в `settings.yaml`:
- LLM модель и таймауты
- Пороги retriever'а
- Веса классификатора
- Длина истории и количество retry

## Тестирование

```bash
# Все тесты (294)
pytest tests/ -v

# Тесты классификатора
pytest tests/test_classifier.py -v

# Тесты SPIN
pytest tests/test_spin.py -v

# Тесты базы знаний
pytest tests/test_knowledge.py -v

# Тесты каскадного retriever
pytest tests/test_cascade_retriever.py tests/test_cascade_advanced.py -v

# Тесты настроек
pytest tests/test_settings.py -v
```

## Зависимости

| Пакет | Назначение |
|-------|------------|
| `ollama` | Локальная LLM (qwen3:8b-fast) |
| `pymorphy3` | Морфология русского языка |
| `sentence-transformers` | Эмбеддинги (ai-forever/ru-en-RoSBERTa) |
| `requests` | HTTP-клиент |
| `pyyaml` | Парсинг YAML |
| `pytest` | Тестирование |
