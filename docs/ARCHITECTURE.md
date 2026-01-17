# Архитектура CRM Sales Bot

## Обзор

CRM Sales Bot — чат-бот для продажи CRM-системы Wipon. Использует методологию SPIN Selling для квалификации клиентов и ведёт диалог от приветствия до закрытия сделки.

**Технологический стек:**
- **LLM**: Qwen3-8B-AWQ через vLLM (OpenAI-compatible API)
- **Structured Output**: Outlines (guided decoding) для гарантированного JSON
- **Эмбеддинги**: ai-forever/FRIDA (ранее ru-en-RoSBERTa)
- **Reranker**: BAAI/bge-reranker-v2-m3

---

## 📦 Версия 2.0: Модульная YAML конфигурация

**Дата миграции**: Январь 2026

### Что изменилось

| Компонент | v1.x (Legacy) | v2.0 (Current) |
|-----------|---------------|----------------|
| **StateMachine config** | Python constants (`config.py`) | YAML (`src/yaml_config/`) |
| **Flow definition** | Hardcoded в `state_machine.py` | `FlowConfig` из `flows/spin_selling/` |
| **States** | `SALES_STATES` dict | `states.yaml` с extends/mixins |
| **Constants** | Разбросаны по файлам | `constants.yaml` (single source of truth) |
| **Fallback** | Python → YAML | YAML only (no fallback) |
| **Эмбеддинги** | ru-en-RoSBERTa | ai-forever/FRIDA |

### Ключевые файлы v2.0

```
src/
├── config_loader.py          # ConfigLoader, FlowConfig, LoadedConfig
├── yaml_config/
│   ├── constants.yaml        # Единый источник констант
│   ├── states/
│   │   └── sales_flow.yaml   # Определение состояний
│   ├── flows/
│   │   ├── _base/            # Базовые состояния и mixins
│   │   │   ├── states.yaml
│   │   │   ├── mixins.yaml
│   │   │   └── priorities.yaml
│   │   └── spin_selling/     # SPIN Selling flow
│   │       ├── flow.yaml     # Главная конфигурация
│   │       └── states.yaml   # SPIN-специфичные состояния
│   └── conditions/
│       └── custom.yaml       # Кастомные условия
└── dag/                      # DAG State Machine (параллельные потоки)
```

### Миграция импортов

```python
# ❌ v1.x (deprecated)
from state_machine import SPIN_PHASES, SPIN_STATES, SPIN_PROGRESS_INTENTS

# ✅ v2.0
from src.yaml_config.constants import SPIN_PHASES, SPIN_STATES, SPIN_PROGRESS_INTENTS

# StateMachine теперь автоматически загружает config и flow
sm = StateMachine()  # Auto-loads from YAML
```

### DAG State Machine

v2.0 добавляет поддержку DAG (Directed Acyclic Graph) для:
- **CHOICE nodes** — условные ветвления
- **FORK/JOIN nodes** — параллельные потоки
- **History states** — восстановление после прерываний

Подробнее: [docs/DAG.md](DAG.md)

---

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
│      + Feature Flags + Metrics + Logger + DialoguePolicy                     │
└─────────────────┬───────────────────────────────┬───────────────────────────┘
                  │                               │
    ┌─────────────▼─────────────┐   ┌─────────────▼─────────────┐
    │    UnifiedClassifier      │   │     StateMachine          │
    │    (classifier/)          │   │   (state_machine.py)      │
    │                           │   │                           │
    │ • LLMClassifier (vLLM)    │   │ • SPIN flow логика        │
    │ • Structured output       │   │ • Priority-driven rules   │
    │ • HybridClassifier fallback│  │ • FlowConfig (YAML)       │
    │ • 33 интента              │   │ • on_enter actions        │
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
├── normalizer.py       # TextNormalizer (663 исправления опечаток)
├── cascade.py          # CascadeClassifier (semantic fallback)
├── disambiguation.py   # IntentDisambiguator
├── intents/
│   ├── patterns.py     # PRIORITY_PATTERNS (426 паттернов)
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

## DAG State Machine ⭐ NEW

Расширение линейной state machine для поддержки параллельных потоков и условных ветвлений.

### Архитектура DAG

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              StateMachine                                    │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                        DAG Components                                    ││
│  │                                                                          ││
│  │  ┌─────────────────┐   ┌─────────────────┐   ┌─────────────────┐       ││
│  │  │ DAGExecution    │   │   DAGExecutor   │   │  BranchRouter   │       ││
│  │  │    Context      │   │                 │   │                 │       ││
│  │  │ • branches      │   │ • execute_choice│   │ • round_robin   │       ││
│  │  │ • history       │   │ • execute_fork  │   │ • priority      │       ││
│  │  │ • events        │   │ • execute_join  │   │ • first_match   │       ││
│  │  └────────┬────────┘   └────────┬────────┘   └────────┬────────┘       ││
│  │           │                     │                     │                 ││
│  │           └─────────────────────┼─────────────────────┘                 ││
│  │                                 │                                        ││
│  │  ┌─────────────────┐   ┌───────▼─────────┐   ┌─────────────────┐       ││
│  │  │ SyncPointManager│   │   apply_rules() │   │  HistoryManager │       ││
│  │  │                 │   │                 │   │                 │       ││
│  │  │ • ALL_COMPLETE  │   │ • check DAG node│   │ • shallow       │       ││
│  │  │ • ANY_COMPLETE  │   │ • execute DAG   │   │ • deep          │       ││
│  │  │ • MAJORITY      │   │ • event sourcing│   │ • interruptions │       ││
│  │  └─────────────────┘   └─────────────────┘   └─────────────────┘       ││
│  └─────────────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────────────┘
```

### Типы DAG узлов

| Тип | Описание | Use Case |
|-----|----------|----------|
| `CHOICE` | Условное ветвление (XOR) | Маршрутизация по типу запроса |
| `FORK` | Запуск параллельных веток | BANT квалификация |
| `JOIN` | Синхронизация веток | Объединение результатов |
| `PARALLEL` | Compound state | Вложенные регионы |

### Пример DAG Flow

```yaml
states:
  # Условное ветвление
  issue_classifier:
    type: choice
    choices:
      - condition: is_technical_issue
        next: technical_flow
      - condition: is_billing_issue
        next: billing_flow
    default: general_inquiry

  # Параллельные ветки
  qualification_fork:
    type: fork
    branches:
      - id: budget_branch
        start_at: collect_budget
      - id: need_branch
        start_at: assess_needs
    join_at: qualification_complete
    join_condition: all_complete
```

### Файлы DAG модуля

```
src/dag/
├── __init__.py           # Публичный API
├── models.py             # DAGBranch, DAGExecutionContext, NodeType
├── executor.py           # DAGExecutor (CHOICE, FORK, JOIN, PARALLEL)
├── branch_router.py      # BranchRouter, IntentBranchMapping
├── sync_points.py        # SyncPointManager, SyncStrategy
└── history.py            # HistoryManager, ConversationFlowTracker
```

Подробнее: [docs/DAG.md](DAG.md), [docs/state_machine.md#13-dag-state-machine](state_machine.md#13-dag-state-machine)

---

## Modular Flow System

Система модульных flow позволяет создавать кастомные диалоговые сценарии через YAML-конфигурацию.

### Архитектура Flow

```
yaml_config/
├── flows/                      # Модульные flow
│   ├── _base/                  # Базовые компоненты
│   │   ├── states.yaml         # Общие состояния (greeting, success, etc.)
│   │   ├── mixins.yaml         # Переиспользуемые блоки правил
│   │   └── priorities.yaml     # Приоритеты обработки
│   │
│   └── spin_selling/           # SPIN Selling flow
│       ├── flow.yaml           # Конфигурация (phases, entry_points)
│       └── states.yaml         # SPIN-состояния
│
└── templates/                  # Шаблоны промптов
    ├── _base/prompts.yaml      # Базовые шаблоны
    └── spin_selling/prompts.yaml # SPIN шаблоны
```

### ConfigLoader и FlowConfig

```python
from src.config_loader import ConfigLoader
from src.state_machine import StateMachine

loader = ConfigLoader()
flow = loader.load_flow("spin_selling")

# FlowConfig содержит:
# - states: Dict[str, Dict] — resolved состояния
# - phases: Dict — фазы и их конфигурация
# - priorities: List[Dict] — приоритеты обработки
# - templates: Dict — шаблоны промптов
# - entry_points: Dict — точки входа

sm = StateMachine(flow=flow)
```

### Extends и Mixins

```yaml
# Наследование от базового состояния
states:
  spin_situation:
    extends: _base_phase      # Наследует rules, transitions
    mixins:
      - price_handling        # Добавляет правила для цен
      - exit_intents          # Добавляет обработку отказов
    goal: "Понять ситуацию"   # Переопределяет goal
```

### Priority-driven apply_rules()

StateMachine поддерживает приоритизацию через YAML:

```yaml
# priorities.yaml
default_priorities:
  - name: final_state
    priority: 0
    condition: is_final
    action: final

  - name: rejection
    priority: 1
    intents: [rejection]
    use_transitions: true

  - name: questions
    priority: 2
    intent_category: question
    default_action: answer_question
```

При наличии FlowConfig, `apply_rules()` итерирует по приоритетам вместо hardcoded логики.

### on_enter Actions

Состояния могут определять action при входе:

```yaml
states:
  ask_activity:
    on_enter:
      action: show_activity_options
    transitions:
      activity_selected: next_state
```

При переходе в это состояние, action автоматически устанавливается в `show_activity_options`.

### Параметризация

Flow variables подставляются в конфигурацию:

```yaml
# flow.yaml
flow:
  variables:
    entry_state: spin_situation
    default_action: deflect_and_continue

# states.yaml — используем {{param}}
transitions:
  agreement: "{{entry_state}}"    # → spin_situation
rules:
  price_question: "{{default_action}}"  # → deflect_and_continue
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
| `context_full_envelope` | `True` | Полный ContextEnvelope |
| `context_policy_overlays` | `True` | DialoguePolicy overrides |
| `cascade_classifier` | `True` | Каскадный классификатор |
| `semantic_objection_detection` | `True` | Семантическая детекция возражений |
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
| `config_loader.py` | ConfigLoader, FlowConfig для YAML flow |
| `yaml_config/` | YAML конфигурация (states, flows, templates) |
| `dag/` | **DAG State Machine** (CHOICE, FORK/JOIN, History) ⭐ |
| `context_window.py` | Расширенный контекст диалога |
| `dialogue_policy.py` | Context-aware policy overlays |
| `context_envelope.py` | Построение контекста для подсистем |
| `intent_tracker.py` | Трекинг интентов и паттернов |
| `response_directives.py` | Директивы для генератора |
| `tone_analyzer/` | Каскадный анализатор тона (3 уровня) |

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

### Создание нового Flow (без кода)

1. Создать директорию `yaml_config/flows/my_flow/`
2. Создать `flow.yaml`:
```yaml
flow:
  name: my_flow
  version: "1.0"
  phases:
    order: [phase1, phase2]
    mapping:
      phase1: state_phase1
      phase2: state_phase2
    post_phases_state: closing
  entry_points:
    default: greeting
```
3. Создать `states.yaml`:
```yaml
states:
  state_phase1:
    extends: _base_phase
    mixins: [price_handling]
    goal: "Phase 1 goal"
    phase: phase1
```
4. Загрузить flow:
```python
loader = ConfigLoader()
flow = loader.load_flow("my_flow")
sm = StateMachine(flow=flow)
```

Подробнее: [src/yaml_config/flows/README.md](../src/yaml_config/flows/README.md)
