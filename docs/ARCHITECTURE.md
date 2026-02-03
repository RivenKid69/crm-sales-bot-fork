# Архитектура CRM Sales Bot

## Обзор

CRM Sales Bot — чат-бот для продажи CRM-системы Wipon. Использует методологию SPIN Selling для квалификации клиентов и ведёт диалог от приветствия до закрытия сделки.

**Технологический стек:**
- **LLM**: Qwen3 14B через Ollama (native API)
- **Structured Output**: Ollama native structured output (format parameter)
- **Эмбеддинги**: ai-forever/FRIDA (ruMTEB avg ~71, лучшая модель для русского)
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
| **Flow selection** | Hardcoded SPIN | Configurable via `settings.yaml` |
| **Domain** | SPIN-specific hardcodes | Domain-independent, config-driven |

### Ключевые файлы v2.0

```
src/
├── settings.yaml             # Настройки бота (LLM, retriever, flow.active)
├── config_loader.py          # ConfigLoader, FlowConfig, LoadedConfig
├── yaml_config/
│   ├── constants.yaml        # Единый источник констант (SPIN, limits, intents)
│   ├── constants.py          # Python-обёртка для constants.yaml
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
# v1.x (deprecated)
from state_machine import SPIN_PHASES, SPIN_STATES, SPIN_PROGRESS_INTENTS

# v2.0
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
    │ • LLMClassifier (Ollama)  │   │ • SPIN flow логика        │
    │ • Structured output       │   │ • Priority-driven rules   │
    │ • HybridClassifier fallback│  │ • FlowConfig (YAML)       │
    │ • 150+ интентов           │   │ • on_enter actions        │
    └───────────────────────────┘   └─────────────┬─────────────┘
                                                  │
                  ┌───────────────────────────────▼───────────────┐
                  │           ResponseGenerator                   │
                  │            (generator.py)                     │
                  │                                               │
                  │ • Генерация ответов через Ollama              │
                  │ • Промпт-инжиниринг по action                 │
                  │ • Интеграция с базой знаний                   │
                  │ • Retry при иностранном тексте                │
                  │ • ResponseVariations (вариативность)          │
                  └────────────────┬──────────────────────────────┘
                                   │
          ┌────────────────────────┼────────────────────────┐
          │                        │                        │
┌─────────▼─────────┐   ┌──────────▼──────────┐   ┌─────────▼─────────┐
│   OllamaClient    │   │  CascadeRetriever   │   │      config       │
│    (llm.py)       │   │   (knowledge/)      │   │    (config.py)    │
│                   │   │                     │   │                   │
│ • Qwen3 14B       │   │ • 3-этапный поиск   │   │ • INTENT_ROOTS    │
│ • Structured JSON │   │ • 1969 YAML секций  │   │ • SALES_STATES    │
│ • Native format   │   │ • ai-forever/FRIDA  │   │ • Промпт-шаблоны  │
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

### Ollama Server

```bash
# Установка Ollama
curl -fsSL https://ollama.ai/install.sh | sh

# Скачать модель
ollama pull qwen3:14b

# Запуск сервера
ollama serve
```

**Требования:**
- ~12-16 GB VRAM (для 14B модели)
- CUDA совместимая GPU
- Python 3.10+

### OllamaClient (llm.py)

Единый клиент для всех LLM операций:

```python
from llm import OllamaClient

llm = OllamaClient()

# Free-form генерация
response = llm.generate(prompt, state="greeting")

# Structured output (Ollama native)
result = llm.generate_structured(prompt, PydanticSchema)
```

**Возможности:**
- **Structured Output** — 100% валидный JSON через Pydantic схемы (native format parameter)
- **Circuit Breaker** — 5 ошибок → 60 сек cooldown
- **Retry** — exponential backoff (1s → 2s → 4s)
- **Fallback responses** — по состояниям FSM
- **Health check** — проверка доступности Ollama

**Конфигурация** (settings.yaml):
```yaml
llm:
  model: "qwen3:14b"
  base_url: "http://localhost:11434"
  timeout: 120
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
│   │ (Ollama)      │         │ (regex+lemma)   │          │
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
- 150+ интентов в 26 категориях (из constants.yaml)
- Structured output через Ollama native format
- Извлечение данных (company_size, pain_point, etc.)
- Контекстная классификация (учёт SPIN фазы)
- Fallback на HybridClassifier при ошибке Ollama

**Категории интентов:**
- objection (18), positive (24), question (18)
- equipment_questions (12), tariff_questions (8), tis_questions (10)
- tax_questions (8), accounting_questions (8), integration_specific (8)
- operations_questions (10), delivery_service (6), business_scenarios (18)
- technical_problems (6), conversational (10), fiscal_questions (8)
- analytics_questions (8), wipon_products (6), employee_questions (6+)

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

### RefinementPipeline NEW

Универсальная архитектура уточнения классификации через расширяемый pipeline:

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                           RefinementPipeline                                   │
│                                                                                │
│   message → LLM/Hybrid Classifier → RefinementPipeline → Disambiguation        │
│                                            │                                   │
│              ┌─────────────────────────────┼─────────────────────────────┐    │
│              │                             │                             │    │
│        ┌─────▼─────┐   ┌─────────────┐   ┌──────▼──────┐   ┌──────────┐ │    │
│        │Confidence │ → │ShortAnswer  │ → │Composite    │ → │Objection │ │    │
│        │Calibration│   │Refinement   │   │Message      │   │Refinement│ │    │
│        │(CRITICAL) │   │(HIGH)       │   │(HIGH)       │   │(NORMAL)  │ │    │
│        └───────────┘   └─────────────┘   └─────────────┘   └──────────┘ │    │
│              NEW                                                       │    │
│   Architecture:                                                                │
│   • Protocol Pattern (IRefinementLayer) — единый интерфейс для слоёв          │
│   • Registry Pattern — динамическая регистрация слоёв                         │
│   • Pipeline Pattern — последовательная обработка по приоритетам              │
│   • Fail-Safe — ошибки слоя не ломают весь pipeline                           │
│   • Scientific Calibration — entropy, gap, heuristic strategies               │
│                                                                                │
└──────────────────────────────────────────────────────────────────────────────┘
```

**Компоненты:**

| Файл | Описание |
|------|----------|
| `refinement_pipeline.py` | Core: RefinementContext, IRefinementLayer, Registry, Pipeline |
| `refinement_layers.py` | Адаптеры: ShortAnswerRefinementLayer, CompositeMessageLayer, ObjectionRefinementLayerAdapter |

**Слои уточнения:**

| Слой | Приоритет | Описание |
|------|-----------|----------|
| `confidence_calibration` | CRITICAL | Научная калибровка LLM confidence (entropy, gap, heuristics) |
| `short_answer` | HIGH | Уточнение коротких ответов ("да", "1") по контексту SPIN фазы |
| `composite_message` | HIGH | Приоритет извлечения данных в составных сообщениях |
| `objection` | NORMAL | Контекстная валидация objection-классификаций |

**Конфигурация** (constants.yaml):
```yaml
refinement_pipeline:
  enabled: true
  layers:
    - name: confidence_calibration
      enabled: true
      priority: CRITICAL  # 100 - runs first      feature_flag: confidence_calibration
    - name: short_answer
      enabled: true
      priority: HIGH
      feature_flag: classification_refinement
    - name: composite_message
      enabled: true
      priority: HIGH
      feature_flag: composite_refinement
    - name: objection
      enabled: true
      priority: NORMAL
      feature_flag: objection_refinement

# NEW: Scientific confidence calibration
confidence_calibration:
  enabled: true
  entropy_enabled: true       # Shannon entropy
  gap_enabled: true           # Gap between top-1 and top-2
  heuristic_enabled: true     # Pattern-based rules
```

**SSoT:**
- Pipeline: `src/classifier/refinement_pipeline.py`
- Layers: `src/classifier/refinement_layers.py`
- Confidence Calibration: `src/classifier/confidence_calibration.py`- Config: `src/yaml_config/constants.yaml` (секции `refinement_pipeline`, `confidence_calibration`)

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

# 3. Генерация через Ollama
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

## DAG State Machine NEW

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
├── flows/                      # 22 модульных flow
│   ├── _base/                  # Базовые компоненты
│   │   ├── states.yaml         # Общие состояния (greeting, success, etc.)
│   │   ├── mixins.yaml         # Переиспользуемые блоки правил
│   │   └── priorities.yaml     # Приоритеты обработки
│   │
│   ├── spin_selling/           # SPIN Selling flow (по умолчанию)
│   ├── aida/                   # AIDA flow
│   ├── bant/                   # BANT flow
│   ├── challenger/             # Challenger Sale
│   ├── consultative/           # Consultative Selling
│   ├── customer_centric/       # Customer Centric
│   ├── demo_first/             # Demo First
│   ├── fab/                    # Features-Advantages-Benefits
│   ├── gap/                    # GAP Selling
│   ├── inbound/                # Inbound Sales
│   ├── meddic/                 # MEDDIC
│   ├── neat/                   # NEAT Selling
│   ├── relationship/           # Relationship Selling
│   ├── sandler/                # Sandler
│   ├── snap/                   # SNAP Selling
│   ├── social/                 # Social Selling
│   ├── solution/               # Solution Selling
│   ├── transactional/          # Transactional Sales
│   ├── value/                  # Value Selling
│   └── examples/               # Примеры конфигураций
│
├── templates/                  # Шаблоны промптов
│   ├── _base/prompts.yaml      # Базовые шаблоны
│   └── spin_selling/prompts.yaml # SPIN шаблоны
│
└── constants.yaml              # ЕДИНЫЙ ИСТОЧНИК ИСТИНЫ (38K)
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

## Intent Taxonomy System NEW

**"Zero Unmapped Intents by Design"** — архитектура для устранения 81% failure rate через intelligent fallback.

### Проблема

До taxonomy system unmapped intents fallback к generic `continue_current_goal`:

```yaml
# State rules (no mapping for price_question)
rules:
  greeting: greet_back
  # price_question — NOT MAPPED

# Resolution:
price_question → (no match) → DEFAULT_ACTION = continue_current_goal
# Result: WRONG ACTION (should be answer_with_pricing)
# Failure Rate: 81%
```

### Решение: Hierarchical Taxonomy

Каждый intent имеет **taxonomy metadata**:

```yaml
intent_taxonomy:
  price_question:
    category: question                    # Primary category
    super_category: user_input            # Higher-level grouping
    semantic_domain: pricing              # Semantic domain
    fallback_action: answer_with_pricing  # Intelligent fallback
    priority: high
```

### 5-Level Fallback Chain

```
Intent Resolution Pipeline:

1. Exact Match        ─── state/global rules mapping
       │
       ▼ (not found)
2. Category Fallback  ─── question → answer_and_continue
       │
       ▼ (not found)
3. Super-Category     ─── user_input → acknowledge_and_continue
       │
       ▼ (not found)
4. Domain Fallback    ─── pricing → answer_with_pricing  [MATCH]
       │
       ▼ (not found)
5. DEFAULT_ACTION     ─── continue_current_goal
```

**Example:**
```yaml
# price_question not mapped in state rules
# Fallback chain:
# 1. Exact match — NOT FOUND
# 2. Category (question) — answer_and_continue (available)
# 3. Super-category (user_input) — acknowledge_and_continue (available)
# 4. Domain (pricing) — answer_with_pricing USED (strongest semantic signal)
# Result: answer_with_pricing (CORRECT!)
```

### Universal Base Mixin

**Guaranteed coverage** для критических intents:

```yaml
_universal_base:
  rules:
    # Price intents (7 intents)
    price_question: answer_with_pricing
    pricing_details: answer_with_pricing
    # ...

    # Meta intents
    request_brevity: respond_briefly
    unclear: clarify_one_question

  transitions:
    contact_provided: success
    demo_request: close
    request_references: close
```

**Integration:**
```yaml
_base_phase:
  mixins:
    - _universal_base     # FIRST for guaranteed coverage
    - phase_progress
    - price_handling      # Can override with conditional logic
```

### Validation System

**Static validation (CI):**
```python
from src.validation import IntentCoverageValidator

validator = IntentCoverageValidator(config, flow)
issues = validator.validate_all()
# Checks:
# - All critical intents have mappings in _universal_base
# - All intents have taxonomy entries
# - Price intents use answer_with_pricing (not answer_with_facts)
```

**Runtime monitoring:**
```python
from src.metrics import FallbackMetrics

metrics = FallbackMetrics()
# Tracks:
# - Fallback rate by level (category, domain, default)
# - DEFAULT_ACTION usage (<1% target)
# - Intelligent fallback rate (40-60% target)
```

### Results

| Intent | Before | After |
|--------|--------|-------|
| `price_question` | 81% failure | **95%+** success (domain fallback) |
| `contact_provided` | 81% failure | **95%+** success (_universal_base) |
| `request_brevity` | 55% spurious | **<5%** spurious transitions |
| `request_references` | 54% failure | **95%+** success (_universal_base) |

**Документация:** [docs/INTENT_TAXONOMY.md](INTENT_TAXONOMY.md)

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
│  (score >= 0.5)    │  ai-forever/FRIDA
└────────┬───────────┘
         │ низкий score
         ▼
┌────────────────────┐
│  4. CategoryRouter │  LLM-классификация категорий
│  (fallback)        │  Ollama определяет релевантные категории
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
- Structured Output (Ollama native format) — 100% валидный JSON
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

**Ключевые флаги (включённые по умолчанию):**

| Флаг | Описание |
|------|----------|
| `llm_classifier` | LLM классификатор вместо Hybrid |
| `multi_tier_fallback` | 4-уровневый fallback |
| `conversation_guard` | Защита от зацикливания |
| `tone_analysis` | Анализ тона клиента |
| `response_variations` | Вариативность ответов |
| `cascade_tone_analyzer` | Каскадный анализатор тона |
| `tone_semantic_tier2` | Tier 2: FRIDA semantic |
| `tone_llm_tier3` | Tier 3: LLM fallback |
| `cascade_classifier` | Каскадный классификатор |
| `semantic_objection_detection` | Семантическая детекция возражений |
| `context_full_envelope` | Полный ContextEnvelope |
| `context_response_directives` | ResponseDirectives для генератора |
| `context_policy_overlays` | DialoguePolicy overrides |
| `response_deduplication` | Проверка на дублирующиеся ответы |
| `price_question_override` | Intent-aware override для вопросов о цене |
| `guard_informative_intent_check` | Проверка информативных интентов |
| `guard_skip_resets_fallback` | Сброс fallback_response после skip |
| `confidence_router` | Gap-based решения и graceful degradation |
| `refinement_pipeline` | Универсальный RefinementPipeline вместо отдельных слоёв |
| `confidence_calibration` | Научная калибровка LLM confidence (entropy, gap, heuristics) NEW |
| `classification_refinement` | Уточнение классификации коротких ответов |
| `composite_refinement` | Приоритет данных в составных сообщениях |
| `objection_refinement` | Контекстная валидация objection-классификаций |

**Флаги в тестировании (выключены):**

| Флаг | Описание |
|------|----------|
| `lead_scoring` | Скоринг лидов |
| `objection_handler` | Продвинутая обработка возражений |
| `cta_generator` | Генерация Call-to-Action |
| `personalization_v2` | V2 engine с behavioral adaptation |

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
| `llm.py` | OllamaClient с circuit breaker и retry |
| `state_machine.py` | FSM с модульной YAML конфигурацией |
| `generator.py` | Генерация ответов через Ollama |
| `classifier/unified.py` | Адаптер для переключения классификаторов |
| `classifier/llm/` | LLM классификатор (150+ интентов) |
| `classifier/hybrid.py` | Regex-based классификатор (fallback) |
| `classifier/refinement_pipeline.py` | **RefinementPipeline** (Protocol, Registry, Pipeline) |
| `classifier/refinement_layers.py` | **Адаптеры слоёв уточнения** (Short, Composite, Objection) |
| `classifier/confidence_calibration.py` | **ConfidenceCalibrationLayer** (научная калибровка LLM confidence) NEW |
| `knowledge/retriever.py` | CascadeRetriever (3-этапный поиск) |
| `knowledge/category_router.py` | LLM-классификация категорий |
| `knowledge/reranker.py` | Cross-encoder переоценка |
| `feature_flags.py` | Управление фичами |
| `settings.py` | Конфигурация из YAML |
| `config.py` | Интенты, состояния, промпты |
| `config_loader.py` | ConfigLoader, FlowConfig для YAML flow |
| `rules/resolver.py` | **RuleResolver с taxonomy-based fallback** NEW |
| `rules/intent_taxonomy.py` | **IntentTaxonomyRegistry (5-level fallback chain)** NEW |
| `validation/intent_coverage.py` | **IntentCoverageValidator (zero unmapped intents)** NEW |
| `yaml_config/` | YAML конфигурация (states, flows, templates) |
| `dag/` | **DAG State Machine** (CHOICE, FORK/JOIN, History) |
| `context_window.py` | Расширенный контекст диалога |
| `dialogue_policy.py` | Context-aware policy overlays |
| `context_envelope.py` | Построение контекста для подсистем |
| `intent_tracker.py` | Трекинг интентов и паттернов |
| `response_directives.py` | Директивы для генератора |
| `tone_analyzer/` | Каскадный анализатор тона (3 уровня) |
| `simulator/` | Симулятор диалогов (batch-тестирование с LLM-клиентом) |

## Симулятор диалогов

Модуль `simulator/` обеспечивает массовое тестирование бота с эмуляцией различных типов клиентов:

```bash
# Запуск 50 симуляций
python -m src.simulator -n 50 -o report.txt

# С конкретной персоной
python -m src.simulator -n 10 --persona happy_path

# Параллельный запуск
python -m src.simulator -n 100 --parallel 4
```

### Компоненты

| Модуль | Описание |
|--------|----------|
| `runner.py` | `SimulationRunner` — оркестратор batch-симуляций |
| `client_agent.py` | `ClientAgent` — LLM-агент, эмулирующий клиента |
| `personas.py` | Профили поведения (happy_path, objector, price_focused) |
| `noise.py` | Добавление реалистичного шума в сообщения |
| `metrics.py` | Сбор метрик (SPIN coverage, outcome, duration) |
| `report.py` | Генерация отчётов в текстовом формате |

### Персоны

- **happy_path** — идеальный клиент, следует SPIN flow
- **objector** — часто возражает (цена, конкуренты)
- **price_focused** — фокусируется на стоимости
- **quick_decision** — быстро принимает решение
- **skeptic** — скептически настроен

### Метрики симуляции

```python
@dataclass
class SimulationResult:
    simulation_id: int
    persona: str
    outcome: str           # success, rejection, soft_close, error
    turns: int
    duration_seconds: float
    phases_reached: List[str]
    spin_coverage: float   # 0.0 - 1.0
    objections_count: int
    fallback_count: int
    collected_data: Dict
    rule_traces: List[Dict]  # Трассировка условных правил
```

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

# Тесты конфигурации (1780+ тестов)
pytest tests/test_config_*.py -v
```

**Покрытие тестами конфигурации (1780+ тестов):**

| Категория | Файл | Описание |
|-----------|------|----------|
| **Базовые тесты** | | |
| Constants YAML | `test_config_constants_yaml.py` | Валидация constants.yaml |
| Settings YAML | `test_config_settings_yaml.py` | Валидация settings.yaml |
| Flow YAML | `test_config_flow_yaml.py` | Валидация flow конфигураций |
| Behavior | `test_config_behavior_*.py` | Поведенческие тесты |
| Coverage | `test_config_coverage_*.py` | 100% покрытие параметров |
| **Edge Case тесты** | | |
| Edge Cases | `test_config_edge_cases.py` | Граничные значения, unicode, concurrent |
| Property-based | `test_config_property_based.py` | Hypothesis автогенерация |
| **Расширенные тесты (190 тестов)** | | |
| Dynamic Changes | `test_config_dynamic_changes.py` | Runtime-изменение конфигурации |
| Conflicts | `test_config_conflicts.py` | Конфликты между параметрами |
| Complex Conditions | `test_config_complex_conditions.py` | Вложенные AND/OR/NOT условия |
| Unreachable States | `test_config_unreachable_states.py` | Недостижимые состояния (BFS/DFS) |
| Template Interpolation | `test_config_template_interpolation.py` | {{variable}} и circular refs |
| Multi-tenant | `test_config_multi_tenant.py` | Изоляция конфигов между tenant |
| Stress/Performance | `test_config_stress_performance.py` | Нагрузочные тесты |
| Migration | `test_config_migration.py` | Миграция между версиями конфига |

## Зависимости

| Пакет | Назначение |
|-------|------------|
| `ollama` | Ollama сервер для LLM (устанавливается системно) |
| `requests` | HTTP-клиент для Ollama API |
| `pydantic` | Схемы для structured output |
| `pymorphy3` | Морфология русского языка |
| `sentence-transformers` | Эмбеддинги (FRIDA) |
| `pyyaml` | Парсинг YAML |
| `pytest` | Тестирование |

## Расширение системы

### Добавление нового интента

1. Добавить в `yaml_config/constants.yaml` → `intents.categories`:
   - Категория и список интентов
2. Добавить в `classifier/llm/prompts.py`:
   - Описание интента
   - Few-shot примеры
3. (опционально) Добавить в `config.INTENT_ROOTS` и `config.INTENT_PHRASES`
4. Добавить правила в соответствующий flow (`yaml_config/flows/*/states.yaml`)
5. Добавить промпт-шаблон в `yaml_config/templates/`

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
