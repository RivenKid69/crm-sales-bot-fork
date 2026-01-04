# Архитектура CRM Sales Bot

## Обзор

CRM Sales Bot — чат-бот для продажи CRM-системы Wipon. Использует методологию SPIN Selling для квалификации клиентов и ведёт диалог от приветствия до закрытия сделки.

## Компоненты системы

```
┌─────────────────────────────────────────────────────────────────┐
│                         SalesBot                                │
│                        (bot.py)                                 │
│  Оркестрация: classifier → state_machine → generator            │
└─────────────────┬───────────────────────────────┬───────────────┘
                  │                               │
    ┌─────────────▼─────────────┐   ┌─────────────▼─────────────┐
    │    HybridClassifier       │   │     StateMachine          │
    │    (classifier/)          │   │   (state_machine.py)      │
    │                           │   │                           │
    │ • Определение интента     │   │ • SPIN flow логика        │
    │ • Извлечение данных       │   │ • Приоритеты обработки    │
    │ • Нормализация текста     │   │ • Умное пропускание фаз   │
    └───────────────────────────┘   └─────────────┬─────────────┘
                                                  │
                  ┌───────────────────────────────▼───────────────┐
                  │           ResponseGenerator                   │
                  │            (generator.py)                     │
                  │                                               │
                  │ • Генерация ответов через LLM                 │
                  │ • Промпт-инжиниринг по action                 │
                  │ • Интеграция с базой знаний                   │
                  └────────────────┬──────────────────────────────┘
                                   │
          ┌────────────────────────┼────────────────────────┐
          │                        │                        │
┌─────────▼─────────┐   ┌──────────▼──────────┐   ┌─────────▼─────────┐
│    OllamaLLM      │   │  KnowledgeRetriever │   │      config       │
│    (llm.py)       │   │   (knowledge/)      │   │    (config.py)    │
│                   │   │                     │   │                   │
│ • Qwen3:8b        │   │ • Keyword search    │   │ • INTENT_ROOTS    │
│ • /no_think mode  │   │ • Embeddings        │   │ • SALES_STATES    │
│ • Streaming       │   │ • 400+ секций       │   │ • Промпт-шаблоны  │
└───────────────────┘   └─────────────────────┘   └───────────────────┘
```

## Поток данных

### 1. Входящее сообщение → Классификация

```python
# bot.py:process()
user_message = "нас 10 человек, теряем клиентов"

# Нормализация (опечатки, сленг, слитный текст)
normalized = "нас 10 человек теряем клиентов"

# Классификация интента
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

# Выбор промпт-шаблона по action
template = PROMPTS["transition_to_spin_problem"]

# Подстановка контекста + LLM генерация
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
| 0 | `price_question`, `question_features`, `question_integrations` | Ответить на вопрос, остаться в состоянии |
| 1 | `rejection` | Немедленный переход в `soft_close` |
| 2 | SPIN-интенты | Проверка прогресса, переход по фазам |
| 3 | Правила состояния | Специфичные для состояния действия |
| 4 | Переходы по интенту | Стандартные переходы |

## Модули

### classifier/ — Классификация интентов

```
classifier/
├── __init__.py          # Публичный API
├── normalizer.py        # TextNormalizer, TYPO_FIXES, SPLIT_PATTERNS
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
├── base.py          # KnowledgeSection, SearchResult
├── data.py          # 400+ секций о продуктах Wipon
└── retriever.py     # KnowledgeRetriever (keyword + embeddings)
```

Категории знаний:
- `inventory` — Учёт товаров
- `pos` — Кассовое оборудование
- `mobile` — Мобильное приложение
- `pricing` — Тарифы
- `integrations` — Интеграции (1С, Telegram, и др.)
- `support` — Техподдержка

### state_machine.py — Управление состояниями

Конечный автомат с SPIN-логикой:
- 10 состояний (greeting → success/soft_close)
- Проверка required_data и optional_data для каждого состояния
- Умное пропускание фаз I/N при high_interest

### generator.py — Генерация ответов

- Выбор промпт-шаблона по action
- Подстановка контекста (collected_data, history)
- Интеграция с KnowledgeRetriever для вопросов о продукте
- Вызов LLM (Ollama/Qwen3)

### config.py — Конфигурация

Центральное хранилище:
- `INTENT_ROOTS` — корни слов для быстрой классификации
- `INTENT_PHRASES` — фразы для лемматизации
- `SALES_STATES` — конфигурация состояний SPIN
- `PROMPTS` — шаблоны промптов для LLM

## Расширение системы

### Добавление нового интента

1. Добавить корни в `config.INTENT_ROOTS`
2. Добавить фразы в `config.INTENT_PHRASES`
3. (опционально) Добавить паттерн в `classifier/intents/patterns.py`
4. Добавить правила обработки в `state_machine.py`
5. Добавить промпт-шаблон в `config.PROMPTS`

### Добавление новой SPIN-фазы

1. Создать состояние в `config.SALES_STATES`
2. Указать `spin_phase`, `required_data`, `optional_data`
3. Добавить переходы в state_machine
4. Создать промпт-шаблоны

### Расширение базы знаний

1. Добавить секции в `knowledge/data.py`:
```python
KnowledgeSection(
    id="unique_id",
    category="category_name",
    title="Заголовок",
    content="Содержимое...",
    keywords=["ключевые", "слова"]
)
```

## Тестирование

```bash
# Все тесты (145)
pytest tests/ -v

# Тесты классификатора
pytest tests/test_classifier.py -v

# Тесты SPIN
pytest tests/test_spin.py -v

# Тесты базы знаний
pytest tests/test_knowledge.py -v
```

## Зависимости

| Пакет | Назначение |
|-------|------------|
| `ollama` | Локальная LLM |
| `pymorphy3` | Морфология русского языка |
| `sentence-transformers` | Embeddings (опционально) |
| `requests` | HTTP-клиент |
| `pytest` | Тестирование |
