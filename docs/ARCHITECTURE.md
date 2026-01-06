# Архитектура CRM Sales Bot

## Обзор

CRM Sales Bot — чат-бот для продажи CRM-системы Wipon. Использует методологию SPIN Selling для квалификации клиентов и ведёт диалог от приветствия до закрытия сделки.

**Архитектурные принципы:**
1. **FAIL-SAFE** — любой сбой → graceful degradation, не crash
2. **PROGRESSIVE** — feature flags для постепенного включения фич
3. **OBSERVABLE** — логи, метрики, трейсы с первого дня
4. **TESTABLE** — каждый модуль с тестами сразу
5. **REVERSIBLE** — возможность отката любого изменения

## Компоненты системы

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              SalesBot                                        │
│                             (bot.py)                                         │
│      Оркестрация: classifier → state_machine → generator                     │
│      + Feature Flags + Metrics + Logger                                      │
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
                  │ • ResponseVariations (вариативность)          │
                  └────────────────┬──────────────────────────────┘
                                   │
          ┌────────────────────────┼────────────────────────┐
          │                        │                        │
┌─────────▼─────────┐   ┌──────────▼──────────┐   ┌─────────▼─────────┐
│    OllamaLLM      │   │  CascadeRetriever   │   │      config       │
│    (llm.py)       │   │   (knowledge/)      │   │    (config.py)    │
│                   │   │                     │   │                   │
│ • qwen3:8b-fast   │   │ • 3-этапный поиск   │   │ • INTENT_ROOTS    │
│ • /no_think mode  │   │ • 1722 YAML секции  │   │ • SALES_STATES    │
│ • Streaming       │   │ • ru-en-RoSBERTa    │   │ • Промпт-шаблоны  │
│ • Retry + Circuit │   │ • CategoryRouter    │   │                   │
│   Breaker         │   │ • Reranker          │   │                   │
└───────────────────┘   └─────────────────────┘   └───────────────────┘
          │                        │
          │              ┌─────────▼─────────┐
          │              │     settings      │
          │              │  (settings.yaml)  │
          │              │                   │
          │              │ • LLM параметры   │
          │              │ • Retriever пороги│
          │              │ • Feature Flags   │
          └──────────────┴───────────────────┘
```

## Фазы разработки (Phase 0-3)

### Фаза 0: Инфраструктура
```
┌─────────────────────────────────────────────────────────────────┐
│                         Phase 0                                  │
├──────────────────┬──────────────────┬──────────────────────────┤
│   logger.py      │   metrics.py     │   feature_flags.py       │
│                  │                  │                          │
│ • JSON логи      │ • Метрики        │ • Управление фичами      │
│ • Readable логи  │   диалогов       │ • Env override           │
│ • Context        │ • Conversion     │ • Hot reload             │
│   tracking       │   tracking       │                          │
└──────────────────┴──────────────────┴──────────────────────────┘
```

### Фаза 1: Защита и надёжность
```
┌─────────────────────────────────────────────────────────────────┐
│                         Phase 1                                  │
├─────────────────────────────────┬───────────────────────────────┤
│   fallback_handler.py           │   conversation_guard.py       │
│                                 │                               │
│ • 4-уровневый fallback          │ • Защита от зацикливания      │
│   1. Knowledge base             │ • Loop detection              │
│   2. Company facts              │ • Max turns limit             │
│   3. Generic response           │ • State repetition check      │
│   4. Apology                    │                               │
└─────────────────────────────────┴───────────────────────────────┘
```

### Фаза 2: Естественность диалога
```
┌─────────────────────────────────────────────────────────────────┐
│                         Phase 2                                  │
├─────────────────────────────────┬───────────────────────────────┤
│   tone_analyzer.py              │   response_variations.py      │
│                                 │                               │
│ • Анализ тона клиента           │ • Вариативность ответов       │
│ • Sentiment detection           │ • Template variations         │
│ • Urgency level                 │ • Anti-repetition             │
│ • Frustration detection         │                               │
└─────────────────────────────────┴───────────────────────────────┘
```

### Фаза 3: Оптимизация SPIN Flow
```
┌─────────────────────────────────────────────────────────────────┐
│                         Phase 3                                  │
├───────────────────┬───────────────────┬─────────────────────────┤
│  lead_scoring.py  │ objection_handler │  cta_generator.py       │
│                   │       .py         │                         │
│ • Скоринг лидов   │ • Обработка       │ • Call-to-Action        │
│ • Hot/Warm/Cold   │   возражений      │ • Персонализация        │
│ • Priority calc   │ • Price objection │ • Timing optimization   │
│                   │ • Time objection  │                         │
└───────────────────┴───────────────────┴─────────────────────────┘
```

### Фаза 4: Intent Disambiguation
```
┌─────────────────────────────────────────────────────────────────┐
│                         Phase 4                                  │
├─────────────────────────────────────────────────────────────────┤
│   classifier/ (intent_disambiguation)                           │
│                                                                 │
│ • Уточнение при близких scores                                  │
│ • Контекстная disambiguition                                    │
│ • Запрос уточнения у пользователя                               │
└─────────────────────────────────────────────────────────────────┘
```

### Фаза 5: Dynamic CTA Fallback
```
┌─────────────────────────────────────────────────────────────────┐
│                         Phase 5                                  │
├─────────────────────────────┬───────────────────────────────────┤
│   fallback_handler.py       │   data_extractor.py               │
│                             │                                   │
│ • DYNAMIC_CTA_OPTIONS       │ • PAIN_CATEGORY_KEYWORDS          │
│ • Контекстные подсказки     │ • pain_category extraction        │
│ • Приоритеты: competitor(10)│ • losing_clients                  │
│   pain(8), intent(7)        │ • no_control                      │
│   company_size(5)           │ • manual_work                     │
└─────────────────────────────┴───────────────────────────────────┘
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

# 4. ResponseVariations (если включено)
response = variations.apply(response, action)
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
├── normalizer.py        # TextNormalizer, TYPO_FIXES (699+), SPLIT_PATTERNS (170)
├── hybrid.py            # HybridClassifier (оркестратор)
├── intents/
│   ├── patterns.py      # PRIORITY_PATTERNS (214 паттернов)
│   ├── root_classifier.py   # Быстрая классификация по корням
│   └── lemma_classifier.py  # Fallback через pymorphy
└── extractors/
    └── data_extractor.py    # Извлечение данных + pain_category
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
├── category_router.py  # LLM-классификация категорий
├── reranker.py         # Cross-encoder переоценка
└── data/               # 18 YAML файлов (1722 секции)
    ├── _meta.yaml      # Метаданные
    ├── equipment.yaml  # Оборудование (275)
    ├── products.yaml   # Продукты (253)
    ├── tis.yaml        # Товарно-информационная система (192)
    ├── support.yaml    # Техподдержка (189)
    ├── pricing.yaml    # Тарифы (184)
    ├── inventory.yaml  # Складской учёт (103)
    ├── features.yaml   # Функции (93)
    ├── integrations.yaml   # Интеграции (83)
    ├── regions.yaml    # Регионы (75)
    ├── analytics.yaml  # Аналитика (62)
    ├── employees.yaml  # Управление персоналом (56)
    ├── fiscal.yaml     # Фискализация (46)
    ├── stability.yaml  # Стабильность (42)
    ├── mobile.yaml     # Мобильное приложение (35)
    ├── promotions.yaml # Акции и скидки (24)
    ├── competitors.yaml # Конкуренты (7)
    └── faq.yaml        # FAQ (4)
```

**Категории знаний (по размеру):**
- `equipment` — Оборудование (275 секций)
- `products` — Продукты (253 секции)
- `tis` — Товарно-информационная система (192 секции)
- `support` — Техподдержка (189 секций)
- `pricing` — Тарифы (184 секции)
- `inventory` — Складской учёт (103 секции)
- `features` — Функции (93 секции)
- `integrations` — Интеграции (83 секции)
- `regions` — Регионы (75 секций)
- `analytics` — Аналитика (62 секции)

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
└────────┬───────────┘
         │ низкий score
         ▼
┌────────────────────┐
│  4. CategoryRouter │  LLM-классификация категорий
│  (fallback)        │  Qwen3:8b-fast определяет категории
└────────┬───────────┘
         │ при необходимости
         ▼
┌────────────────────┐
│  5. Reranker       │  Cross-encoder переоценка
│  (BAAI/bge-v2-m3)  │  Переранжирование top-k результатов
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
- ResponseVariations для вариативности (если включено)

### Модули Phase 0-5

| Модуль | Фаза | Назначение | Флаг |
|--------|------|------------|------|
| logger.py | 0 | Структурированное логирование | `structured_logging` |
| metrics.py | 0 | Трекинг метрик диалогов | `metrics_tracking` |
| feature_flags.py | 0 | Управление фичами | всегда включен |
| fallback_handler.py | 1 | 4-уровневый fallback | `multi_tier_fallback` |
| conversation_guard.py | 1 | Защита от зацикливания | `conversation_guard` |
| tone_analyzer.py | 2 | Анализ тона клиента | `tone_analysis` |
| response_variations.py | 2 | Вариативность ответов | `response_variations` |
| lead_scoring.py | 3 | Скоринг лидов | `lead_scoring` |
| objection_handler.py | 3 | Обработка возражений | `objection_handler` |
| cta_generator.py | 3 | Call-to-Action | `cta_generator` |
| classifier/ | 4 | Intent Disambiguation | `intent_disambiguation` |
| fallback_handler.py | 5 | Dynamic CTA Fallback | `dynamic_cta_fallback` |
| data_extractor.py | 5 | Pain category extraction | — (всегда включено) |

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

reranker:
  enabled: true
  model: "BAAI/bge-reranker-v2-m3"
  threshold: 0.5

category_router:
  enabled: true
  top_k: 3

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

feature_flags:
  structured_logging: true
  metrics_tracking: true
  multi_tier_fallback: true
  conversation_guard: true
  tone_analysis: false
  response_variations: true
  lead_scoring: false
  objection_handler: false
  cta_generator: false
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

## Voice Bot (voice_bot/)

Голосовой интерфейс для разговорного взаимодействия:

```
┌───────────────────┐     ┌───────────────────┐     ┌───────────────────┐
│   faster-whisper  │ ──► │    SalesBot       │ ──► │   F5-TTS Russian  │
│   (STT)           │     │   (text mode)     │     │   + RUAccent      │
└───────────────────┘     └───────────────────┘     └───────────────────┘
      Голос клиента              Обработка               Голос бота
```

Компоненты:
- **STT** (Speech-to-Text): faster-whisper с GPU поддержкой
- **LLM**: Ollama (Qwen3:8b-fast)
- **TTS** (Text-to-Speech): F5-TTS Russian + RUAccent для ударений
- Обработка audio: sounddevice, soundfile, numpy

Подробнее: [VOICE.md](./VOICE.md)

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

### Добавление нового Feature Flag

1. Добавить флаг в `settings.yaml`:
```yaml
feature_flags:
  new_feature: false
```

2. Использовать в коде:
```python
from feature_flags import is_enabled

if is_enabled("new_feature"):
    # новая функциональность
```

3. Переопределить через env: `FF_NEW_FEATURE=true`

### Изменение параметров

Все параметры вынесены в `settings.yaml`:
- LLM модель и таймауты
- Пороги retriever'а
- Веса классификатора
- Длина истории и количество retry
- Feature flags

## Тестирование

```bash
# Все тесты (1285+)
pytest tests/ -v

# Тесты классификатора
pytest tests/test_classifier.py -v

# Тесты SPIN
pytest tests/test_spin.py -v

# Тесты базы знаний
pytest tests/test_knowledge.py -v

# Тесты каскадного retriever
pytest tests/test_cascade_retriever.py tests/test_cascade_advanced.py -v

# Тесты CategoryRouter
pytest tests/test_category_router*.py -v

# Тесты настроек
pytest tests/test_settings.py -v

# Тесты фаз 0-4
pytest tests/test_phase*_integration.py -v
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

Voice Bot:
| Пакет | Назначение |
|-------|------------|
| `faster-whisper` | Speech-to-Text |
| `f5-tts` | Text-to-Speech |
| `RUAccent` | Расстановка ударений |
| `sounddevice` | Работа с аудио |
| `torch` | GPU поддержка |
