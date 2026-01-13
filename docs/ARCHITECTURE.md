# Архитектура CRM Sales Bot

## Обзор

CRM Sales Bot — чат-бот для продажи CRM-системы Wipon. Использует методологию SPIN Selling для квалификации клиентов и ведёт диалог от приветствия до закрытия сделки.

**Технологический стек:**
- **LLM**: Qwen3-8B-AWQ через vLLM (OpenAI-compatible API)
- **Structured Output**: Outlines (guided decoding) для гарантированного JSON
- **Эмбеддинги**: ai-forever/ru-en-RoSBERTa
- **Reranker**: BAAI/bge-reranker-v2-m3

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
    │    UnifiedClassifier      │   │     StateMachine          │
    │    (classifier/)          │   │   (state_machine.py)      │
    │                           │   │                           │
    │ • LLMClassifier (vLLM)    │   │ • SPIN flow логика        │
    │ • Structured output       │   │ • Приоритеты обработки    │
    │ • HybridClassifier fallback│  │ • Умное пропускание фаз   │
    │ • 33 интента              │   │ • 10 состояний            │
    └───────────────────────────┘   └─────────────┬─────────────┘
                                                  │
                  ┌───────────────────────────────▼───────────────┐
                  │           ResponseGenerator                   │
                  │            (generator.py)                     │
                  │                                               │
                  │ • Генерация ответов через vLLM                │
                  │ • Промпт-инжиниринг по action                 │
                  │ • Интеграция с базой знаний                   │
                  │ • Retry при иностранном тексте                │
                  │ • ResponseVariations (вариативность)          │
                  └────────────────┬──────────────────────────────┘
                                   │
          ┌────────────────────────┼────────────────────────┐
          │                        │                        │
┌─────────▼─────────┐   ┌──────────▼──────────┐   ┌─────────▼─────────┐
│    VLLMClient     │   │  CascadeRetriever   │   │      config       │
│    (llm.py)       │   │   (knowledge/)      │   │    (config.py)    │
│                   │   │                     │   │                   │
│ • Qwen3-8B-AWQ    │   │ • 3-этапный поиск   │   │ • INTENT_ROOTS    │
│ • Structured JSON │   │ • 1969 YAML секций  │   │ • SALES_STATES    │
│ • Outlines backend│   │ • ru-en-RoSBERTa    │   │ • Промпт-шаблоны  │
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

## LLM Архитектура

### vLLM Server

```bash
# Запуск vLLM
vllm serve Qwen/Qwen3-8B-AWQ \
    --host 0.0.0.0 \
    --port 8000 \
    --guided-decoding-backend outlines \
    --max-model-len 4096 \
    --gpu-memory-utilization 0.9
```

**Требования:**
- ~5-6 GB VRAM
- CUDA совместимая GPU
- Python 3.10+

### VLLMClient (llm.py)

Единый клиент для всех LLM операций:

```python
from llm import VLLMClient

llm = VLLMClient()

# Free-form генерация
response = llm.generate(prompt, state="greeting")

# Structured output (Outlines)
result = llm.generate_structured(prompt, PydanticSchema)
```

**Возможности:**
- **Structured Output** — 100% валидный JSON через Pydantic схемы
- **Circuit Breaker** — 5 ошибок → 60 сек cooldown
- **Retry** — exponential backoff (1s → 2s → 4s)
- **Fallback responses** — по состояниям FSM
- **Health check** — проверка доступности vLLM

**Конфигурация** (settings.yaml):
```yaml
llm:
  model: "Qwen/Qwen3-8B-AWQ"
  base_url: "http://localhost:8000/v1"
  timeout: 60
```

## Классификация интентов

### UnifiedClassifier

Адаптер для переключения между классификаторами:

```
┌──────────────────────────────────────────────────────────┐
│                   UnifiedClassifier                       │
│                                                          │
│   flags.llm_classifier == True     False                 │
│           │                          │                   │
│           ▼                          ▼                   │
│   ┌───────────────┐         ┌────────────────┐          │
│   │ LLMClassifier │         │ HybridClassifier│          │
│   │ (vLLM+Outlines)│        │ (regex+lemma)   │          │
│   └───────┬───────┘         └────────────────┘          │
│           │                                              │
│           │ fallback при ошибке                          │
│           ▼                                              │
│   ┌────────────────┐                                     │
│   │ HybridClassifier│                                    │
│   └────────────────┘                                     │
└──────────────────────────────────────────────────────────┘
```

### LLMClassifier (classifier/llm/)

Основной классификатор на базе LLM:

```
classifier/llm/
├── __init__.py         # Публичный API
├── classifier.py       # LLMClassifier
├── prompts.py          # System prompt + few-shot примеры
└── schemas.py          # Pydantic схемы (ClassificationResult, ExtractedData)
```

**Возможности:**
- 33 интента с описаниями и примерами
- Structured output через Outlines
- Извлечение данных (company_size, pain_point, etc.)
- Контекстная классификация (учёт SPIN фазы)
- Fallback на HybridClassifier при ошибке

**Пример результата:**
```json
{
    "intent": "situation_provided",
    "confidence": 0.95,
    "extracted_data": {
        "company_size": 10,
        "pain_point": "теряем клиентов"
    },
    "method": "llm",
    "reasoning": "Клиент указал размер команды и проблему"
}
```

### HybridClassifier (fallback)

Быстрый regex-based классификатор:

```
classifier/
├── hybrid.py           # HybridClassifier (оркестратор)
├── normalizer.py       # TextNormalizer (692 исправления опечаток)
├── disambiguation.py   # IntentDisambiguator
├── intents/
│   ├── patterns.py     # PRIORITY_PATTERNS (212 паттернов)
│   ├── root_classifier.py   # Классификация по корням
│   └── lemma_classifier.py  # Fallback через pymorphy
└── extractors/
    └── data_extractor.py    # Извлечение данных + pain_category
```

## Поток данных

### 1. Входящее сообщение → Классификация

```python
# bot.py:process()
user_message = "нас 10 человек, теряем клиентов"

# UnifiedClassifier (LLM mode)
{
    "intent": "situation_provided",
    "confidence": 0.95,
    "extracted_data": {
        "company_size": 10,
        "pain_point": "теряем клиентов"
    },
    "method": "llm",
    "reasoning": "..."
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

# 3. Генерация через vLLM
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

## База знаний

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
│  (fallback)        │  vLLM определяет релевантные категории
└────────┬───────────┘
         │ при необходимости
         ▼
┌────────────────────┐
│  5. Reranker       │  Cross-encoder переоценка
│  (BAAI/bge-v2-m3)  │  Переранжирование top-k результатов
└────────────────────┘
```

### CategoryRouter

LLM-классификация запросов по 17 категориям:

```python
router = CategoryRouter(llm, top_k=3)
categories = router.route("Сколько стоит Wipon Desktop?")
# ["pricing", "products"]
```

**Поддерживает:**
- Structured Output (vLLM + Outlines) — 100% валидный JSON
- Legacy режим (generate + parsing) — обратная совместимость

### Категории знаний

| Категория | Секций | Описание |
|-----------|--------|----------|
| equipment | 316 | Оборудование и периферия |
| pricing | 286 | Тарифы и цены |
| products | 273 | Продукты Wipon |
| support | 201 | Техподдержка |
| tis | 191 | Товарно-информационная система |
| regions | 130 | Регионы и доставка |
| inventory | 93 | Складской учёт |
| features | 90 | Функции системы |
| integrations | 86 | Интеграции |
| fiscal | 68 | Фискализация |
| analytics | 63 | Аналитика |
| employees | 55 | Управление персоналом |
| stability | 45 | Стабильность |
| mobile | 35 | Мобильное приложение |
| promotions | 26 | Акции и скидки |
| competitors | 7 | Сравнение с конкурентами |
| faq | 4 | Общие вопросы |

## Feature Flags

Система управления фичами для постепенного включения:

```python
from feature_flags import flags

if flags.llm_classifier:
    # Использовать LLM классификатор
    pass
```

**Ключевые флаги:**

| Флаг | Default | Описание |
|------|---------|----------|
| `llm_classifier` | `True` | LLM классификатор вместо Hybrid |
| `multi_tier_fallback` | `True` | 4-уровневый fallback |
| `conversation_guard` | `True` | Защита от зацикливания |
| `response_variations` | `True` | Вариативность ответов |
| `cascade_tone_analyzer` | `True` | Каскадный анализатор тона |
| `tone_analysis` | `False` | Анализ тона клиента |
| `lead_scoring` | `False` | Скоринг лидов |

**Override через env:**
```bash
export FF_LLM_CLASSIFIER=false  # Переключиться на HybridClassifier
```

## Resilience Patterns

### Circuit Breaker

```
                    ┌───────────┐
              ┌────►│  CLOSED   │◄────┐
              │     └─────┬─────┘     │
              │           │           │
         success    5 failures    success
              │           │           │
              │     ┌─────▼─────┐     │
              │     │   OPEN    │     │
              │     └─────┬─────┘     │
              │           │           │
              │      60 sec           │
              │           │           │
              │     ┌─────▼─────┐     │
              └─────│ HALF-OPEN │─────┘
                    └───────────┘
```

### Retry с Exponential Backoff

```
Attempt 1 → fail → wait 1s
Attempt 2 → fail → wait 2s
Attempt 3 → fail → wait 4s
All failed → use fallback
```

### Fallback Responses

При полном отказе LLM — предопределённые ответы по состояниям:

```python
FALLBACK_RESPONSES = {
    "greeting": "Здравствуйте! Чем могу помочь?",
    "spin_situation": "Расскажите, сколько человек работает в вашей команде?",
    "spin_problem": "С какими сложностями сталкиваетесь сейчас?",
    # ...
}
```

## Модули системы

| Модуль | Назначение |
|--------|------------|
| `bot.py` | Оркестрация: classifier → state_machine → generator |
| `llm.py` | VLLMClient с circuit breaker и retry |
| `state_machine.py` | FSM с 10 состояниями и SPIN-логикой |
| `generator.py` | Генерация ответов через vLLM |
| `classifier/unified.py` | Адаптер для переключения классификаторов |
| `classifier/llm/` | LLM классификатор (33 интента) |
| `classifier/hybrid.py` | Regex-based классификатор (fallback) |
| `knowledge/retriever.py` | CascadeRetriever (3-этапный поиск) |
| `knowledge/category_router.py` | LLM-классификация категорий |
| `knowledge/reranker.py` | Cross-encoder переоценка |
| `feature_flags.py` | Управление фичами |
| `settings.py` | Конфигурация из YAML |
| `config.py` | Интенты, состояния, промпты |

## Тестирование

```bash
# Все тесты
pytest tests/ -v

# Тесты классификатора
pytest tests/test_classifier.py -v

# Тесты SPIN
pytest tests/test_spin.py -v

# Тесты базы знаний
pytest tests/test_knowledge.py tests/test_cascade*.py -v

# Тесты CategoryRouter
pytest tests/test_category_router*.py -v
```

## Зависимости

| Пакет | Назначение |
|-------|------------|
| `vllm` | vLLM сервер для LLM |
| `outlines` | Structured output (guided decoding) |
| `pydantic` | Схемы для structured output |
| `pymorphy3` | Морфология русского языка |
| `sentence-transformers` | Эмбеддинги (RoSBERTa) |
| `requests` | HTTP-клиент |
| `pyyaml` | Парсинг YAML |
| `pytest` | Тестирование |

## Расширение системы

### Добавление нового интента

1. Добавить в `classifier/llm/prompts.py`:
   - Описание интента
   - Few-shot примеры
2. (опционально) Добавить в `config.INTENT_ROOTS` и `config.INTENT_PHRASES`
3. Добавить правила в `state_machine.py`
4. Добавить промпт-шаблон в `config.PROMPT_TEMPLATES`

### Расширение базы знаний

1. Создать/редактировать YAML в `knowledge/data/`:
```yaml
sections:
- topic: unique_topic_id
  priority: 5
  keywords:
  - ключевое слово
  facts: |
    Факты о теме.
```
2. Запустить валидацию: `python scripts/validate_knowledge_yaml.py`

### Добавление нового Feature Flag

1. Добавить в `feature_flags.py:DEFAULTS`:
```python
"new_feature": False,
```
2. Добавить property (опционально):
```python
@property
def new_feature(self) -> bool:
    return self.is_enabled("new_feature")
```
3. Использовать: `if flags.new_feature: ...`
4. Override через env: `FF_NEW_FEATURE=true`
