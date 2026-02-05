# Архитектура CRM Sales Bot

## Обзор

CRM Sales Bot — чат-бот для продажи CRM-системы Wipon. Использует методологию SPIN Selling для квалификации клиентов и ведёт диалог от приветствия до закрытия сделки.

**Технологический стек:**
- **LLM**: Qwen3 14B через Ollama (native API)
- **Structured Output**: Ollama native structured output (format parameter)
- **Эмбеддинги**: ai-forever/FRIDA (ruMTEB avg ~71, лучшая модель для русского)
- **Reranker**: BAAI/bge-reranker-v2-m3

---

## Session Persistence & Snapshot Pipeline

Цель: гарантированно продолжать диалог после паузы (день/неделя), без смешивания данных между клиентами и сессиями.

**Ключевые принципы:**
- Snapshot загружается **только при cache-miss**, не на каждое сообщение.
- Компакция истории выполняется **только при TTL** (1 час тишины).
- Последние 4 сообщения **не сохраняются в snapshot** — берутся из внешней истории.
- Снапшоты копятся локально и выгружаются пачкой **после первого запроса после 23:00**.
- В мультипроцессе используется общий буфер и lock.
- Каждый snapshot содержит `client_id` и проверяется на match при восстановлении.

```
Incoming message
  └── SessionManager.get_or_create(session_id, client_id, flow, config)
       ├── cache hit → use in-memory bot
       ├── local snapshot → restore + history_tail (last 4 msgs)
       └── external snapshot → restore + history_tail

TTL cleanup (cron/worker каждые 5–10 мин)
  └── bot.to_snapshot(compact_history=True) → LocalSnapshotBuffer

Первый запрос после 23:00
  └── batch flush → внешняя БД → LocalSnapshotBuffer.clear()
```

**Компоненты:**
- `SessionManager` — кеш сессий + TTL cleanup + восстановление + batch flush
- `HistoryCompactor` — LLM‑компакция истории при сохранении снапшота
- `LocalSnapshotBuffer` — SQLite буфер снапшотов (multi-process)
- `SessionLockManager` — межпроцессный lock по `session_id`

**Multi‑Config/Flow:**
- В snapshot сохраняются `flow_name`, `config_name`, `client_id`.
- При восстановлении выбирается правильный flow/config.
- При active session возможен “горячий” switch flow/config (пересборка бота через snapshot).

---

## Версия 3.0: Dialogue Blackboard Architecture

**Дата миграции**: Январь 2026
**Статус**: Production-ready

### Что изменилось

| Компонент | v2.0 (Legacy) | v3.0 (Current) |
|-----------|---------------|----------------|
| **Decision Engine** | `state_machine.apply_rules()` | Dialogue Blackboard System |
| **Architecture** | Procedural rule processing | Blackboard Pattern (knowledge sources) |
| **Knowledge Sources** | Hardcoded в state_machine | 15 независимых KS модулей |
| **Интенты** | 150+ интентов в 26 категориях | 300 интентов в 34 категориях |
| **Flows** | 21 flows | 21 flows + universal phase resolution |
| **State Transitions** | Distributed mutation | Atomic transition_to() |
| **Objection Tracking** | Manual tracking | Automatic _state_before_objection |
| **Go Back Logic** | Scattered | CircularFlowManager as SSOT |
| **Extensibility** | Править state_machine.py | Plugin System (@register_source) |
| **Observability** | Базовые логи | EventBus + MetricsCollector |
| **Protocols** | Прямые зависимости | Hexagonal Architecture (IStateMachine, IIntentTracker) |

### Ключевые компоненты v3.0

```
src/blackboard/
├── orchestrator.py         # DialogueOrchestrator — main coordinator
├── blackboard.py           # DialogueBlackboard — shared workspace
├── knowledge_source.py     # KnowledgeSource ABC
├── source_registry.py      # @register_source decorator
├── protocols.py            # Hexagonal Architecture protocols
├── models.py               # Proposal, ResolvedDecision, ContextSnapshot
├── conflict_resolver.py    # ConflictResolver
├── proposal_validator.py   # ProposalValidator
├── event_bus.py            # DialogueEventBus (observability)
└── sources/                # 15 Knowledge Sources
    ├── autonomous_decision.py    # Priority 100
    ├── price_question.py         # Priority 70
    ├── fact_question.py          # Priority 65
    ├── objection_guard.py        # Priority 90 (CRITICAL)
    ├── stall_guard.py            # Priority 88 (two-tier: soft NORMAL + hard HIGH)
    ├── conversation_guard_ks.py  # Priority 85
    ├── go_back_guard.py          # Priority 82 (deferred counter increment)
    ├── intent_pattern_guard.py   # Priority 80 (comparison fatigue detection)
    ├── objection_return.py       # Priority 75 (all_questions auto-discovery)
    ├── escalation.py             # Priority 70
    ├── phase_exhausted.py        # Priority 60 (migrated from ConversationGuard)
    ├── disambiguation.py         # Priority 55 (blocking, combinable=False)
    ├── data_collector.py         # Priority 50 (persistent extracted_data)
    ├── intent_processor.py       # Priority 40
    └── transition_resolver.py    # Priority 30
```

**Важно:** `StateMachine` остаётся источником состояния, collected_data и snapshot API. Blackboard заменяет только decision engine (`apply_rules()`), а не хранение state.

### Plugin System

Любой Knowledge Source можно зарегистрировать через декоратор:

```python
from src.blackboard import register_source, KnowledgeSource, Proposal

@register_source(name="my_source", priority=50, enabled=True)
class MySource(KnowledgeSource):
    def contribute(self, snapshot: ContextSnapshot) -> List[Proposal]:
        # Analyze context
        if snapshot.intent == "custom_intent":
            return [Proposal(
                source=self.name,
                priority=Priority.HIGH,
                proposal_type=ProposalType.ACTION,
                action="custom_action"
            )]
        return []
```

### Hexagonal Architecture

v3.0 использует протоколы для развязки зависимостей:

```python
# protocols.py
class IStateMachine(Protocol):
    def get_current_state(self) -> str: ...
    def set_state(self, state: str): ...

class IIntentTracker(Protocol):
    def add_intent(self, intent: str): ...
    def get_intent_count(self, intent: str) -> int: ...
```

Knowledge Sources зависят только от протоколов, не от конкретных реализаций.

---

## Версия 2.0: Модульная YAML конфигурация

**Дата миграции**: Январь 2026 (актуальный слой конфигурации для StateMachine/Blackboard)

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
│                             # NEW: state_to_phase, get_phase_for_state
├── yaml_config/
│   ├── constants.yaml        # Единый источник констант (SPIN, limits, intents)
│   │                         # NEW: composed_categories, configurable limits
│   ├── constants.py          # Python-обёртка для constants.yaml
│   │                         # NEW: _resolve_composed_categories()
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
│   │                         # NEW: prev_phase_state for all flows
│   ├── templates/            # Шаблоны промптов (NEW)
│   │   ├── _base/prompts.yaml        # Базовые шаблоны
│   │   ├── spin_selling/prompts.yaml # SPIN шаблоны
│   │   ├── aida/prompts.yaml         # AIDA шаблоны
│   │   └── ... (21 flows)            # Flow-специфичные промпты
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
│      Оркестрация: classifier → blackboard_orchestrator → generator           │
│      + Feature Flags + Metrics + Logger + DialoguePolicy                     │
└─────────────────┬───────────────────────────────┬───────────────────────────┘
                  │                               │
    ┌─────────────▼─────────────┐   ┌─────────────▼─────────────┐
    │    UnifiedClassifier      │   │   Blackboard System       │
    │    (classifier/)          │   │ (blackboard/)             │
    │                           │   │                           │
    │ • LLMClassifier (Ollama)  │   │ • DialogueOrchestrator    │
    │ • Structured output       │   │ • 15 Knowledge Sources    │
    │ • HybridClassifier fallback│  │ • ConflictResolver        │
    │ • 300 интентов / 34 кат.  │   │ • EventBus (observability)│
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
from src.llm import OllamaClient

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
- 300 интентов в 34 категориях (из constants.yaml)
- Structured output через Ollama native format
- Извлечение данных (company_size, pain_point, etc.)
- Контекстная классификация (учёт SPIN фазы)
- Fallback на HybridClassifier при ошибке Ollama

**34 категории интентов (300 интентов):**
- objection (18), positive (23), question (18)
- equipment_questions (12), tariff_questions (8), tis_questions (10)
- tax_questions (8), accounting_questions (8), integration_specific (8)
- operations_questions (10), delivery_service (6), business_scenarios (18)
- technical_problems (6), conversational (10), fiscal_questions (8)
- analytics_questions (8), wipon_products (6), employee_questions (6)
- price_related (7), purchase_stages (8), company_info (4)
- dialogue_control (8), technical_question (13), promo_loyalty (6)
- region_questions (6), stability_questions (6), informative (16)
- spin_progress (4), exit (2), escalation (8)
- frustration (6), sensitive (7), additional_integrations (6)
- greeting_additional_redirects (2)

**Composed Categories**

Система композитных категорий для автоматической синхронизации:

```yaml
# constants.yaml
composed_categories:
  negative:
    includes: [objection, exit]
  blocking:
    includes: [objection, exit, technical_problems]
  all_questions:
    auto_include:
      intent_prefix: "question_"
      exclude_categories: [positive, informative]
    includes: [price_related, company_info]
```

**Результат:**
- rejection относится к `exit` и не влияет на objection limits
- all_questions собирается автоматически по intent_prefix
- Single Source of Truth для категорий

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

### ClassificationRefinementLayer NEW

Уточнение классификации для коротких ответов на основе контекста SPIN фазы.

**Проблема:** LLM классификатор неверно классифицирует короткие сообщения ("1", "да", "первое") как greeting вместо контекстно-правильных интентов (situation_provided, problem_revealed). Это вызывало зацикливание в greeting state (52 случая в e2e симуляции).

**Решение:**
- ClassificationRefinementLayer анализирует короткие сообщения и уточняет классификацию на основе текущей SPIN фазы
- Feature flag classification_refinement для безопасного роллаута
- Fallback transition в greeting state (turn_number_gte_3 → entry_state)
- Улучшенный LLM prompt с явными инструкциями для коротких ответов

**Результаты:**
- 32/32 unit тестов проходят
- e2e симуляция: 100% успешность (было примерно 48% с 52 State Loop случаями)
- State Loop ошибки: 0 (было 52)

**Компоненты:**
- `src/classifier/refinement.py` - ClassificationRefinementLayer
- `src/yaml_config/constants.yaml` - short_answer_classification config
- `src/feature_flags.py` - classification_refinement flag

```python
# Пример: фаза "situation", сообщение "1"
# LLM: greeting (0.8)
# После refinement: situation_provided (0.9) с company_size=1
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
│   ├── patterns.py     # PRIORITY_PATTERNS (491 паттерн)
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
├── templates/                  # Шаблоны промптов (NEW: flow-specific)
│   ├── _base/prompts.yaml      # Базовые шаблоны
│   ├── spin_selling/prompts.yaml # SPIN шаблоны
│   ├── aida/prompts.yaml       # AIDA flow prompts
│   ├── bant/prompts.yaml       # BANT flow prompts
│   ├── challenger/prompts.yaml # Challenger Sale prompts
│   └── ... (21 flows total)    # Flow-специфичные промпты с goal-aware continuation
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

## Ключевые улучшения системы (январь 2026)

### ObjectionReturnSource NEW

Knowledge Source для автоматического возврата к фазам после разрешения возражений.

**Проблема:** До внедрения _state_before_objection сохранялся, но никогда не использовался. Бот застревал в handle_objection loop, не возвращаясь к sales flow phases (coverage: 0.0, phases_reached: []).

**Решение:**
- Автоматическое сохранение состояния при входе в handle_objection
- Детекция успешного разрешения через POSITIVE_INTENTS + QUESTION_RETURN_INTENTS
- HIGH priority предложение перехода обратно к saved_state
- Objection loop escape mechanism (total-based + consecutive)

**Особенности:**
- Priority 75 (HIGH) — побеждает YAML transitions (NORMAL priority)
- Phase restoration — возврат к bant_budget, spin_problem, etc.
- Total-based escape — автоматический выход при total >= max_total - 1
- Question return support — uncertainty patterns → question intents → return to phase

**Результаты:**
- Objection return rate: **81% stuck → 95%+ успешных возвратов**
- Phase coverage: **0% → 25%+** для skeptic/tire_kicker personas
- Застреваний в handle_objection: **0** (было множество cases)

**SSoT:** [src/blackboard/sources/objection_return.py](../src/blackboard/sources/objection_return.py)

### FactQuestionSource NEW

Universal Knowledge Source для обработки фактических вопросов из всех 17 категорий KB.

**Проблема:** Составные сообщения типа "100 человек. Сколько стоит?" теряли secondary question intent (price_question), так как LLM выбирает ОДИН primary intent (info_provided).

**Решение:**
- SecondaryIntentDetectionLayer — pattern-based detection без изменения primary intent
- FactQuestionSource — проверяет primary + secondary_intents
- Count-based conditions (price_total_count_3x, etc.) — не сбрасываются

**Поддерживаемые категории (17):**
- price_question (50+ patterns)
- demo_request (25+ patterns)
- callback_request (25+ patterns)
- question_features (30+ patterns)
- question_integrations (40+ patterns, Kaspi, 1C, API)
- question_support (20+ patterns)
- question_equipment (25+ patterns)
- question_analytics, question_competitors, question_employees
- question_fiscal, question_inventory, question_mobile
- question_products, question_promotions, question_regions
- question_stability, question_tis

**Результаты:**
- Lost questions: **25 игнорирований → <2%**
- Secondary intent detection: **365 patterns** covering KB question intents
- Composite message handling: **95%+ success rate**

**SSoT:** [src/blackboard/sources/fact_question.py](../src/blackboard/sources/fact_question.py), [src/classifier/secondary_intent_detection.py](../src/classifier/secondary_intent_detection.py)

### FrustrationIntensityCalculator NEW

Intensity-based frustration calculation для точной детекции и pre-intervention.

**Проблема:** До внедрения только ОДНА сигнал per tone per message считалась. "быстрее, не тяни, некогда" (3 RUSHED signals) = +1/turn → после 4 turns frustration = 4 < threshold 7 → no intervention.

**Решение:**
- Count ALL signals per message
- Intensity multipliers: 1 signal = base weight, 2 signals = base * 1.5, 3+ signals = base * 2.0
- Pre-intervention detection: RUSHED with high signal count triggers WARNING level early
- Updated RUSHED weight: 1 → 2 для адекватного влияния

**Примеры:**
```python
# Пример 1: "быстрее, не тяни, некогда" (3 RUSHED signals)
# Было: +1 (одна сигнал)
# Стало: base(2) * intensity(2.0) = +4 per turn
# Результат: After 2 turns → intervention triggered

# Пример 2: Pre-intervention mechanism
# WARNING level (5-6) with RUSHED/FRUSTRATED tone → pre_intervention_triggered = True
# Propagates through: ContextEnvelope → PolicyContext → GuardContext → protective measures
```

**Результаты:**
- False negatives (missed frustration): **20%+ → <5%**
- Pre-intervention activation: **+35%** раньше обнаружение
- Ложные TIER_3 вмешательства: **18% → <2%** (благодаря structural_frustration)

**SSoT:** [src/tone_analyzer/frustration_intensity.py](../src/tone_analyzer/frustration_intensity.py), [src/tone_analyzer/structural_frustration.py](../src/tone_analyzer/structural_frustration.py)

### KB-Grounded Questions System NEW

Система фактических вопросов из базы знаний для реалистичных E2E симуляций.

**Компоненты:**
- **KBQuestionPool** - пул из 5344 вопросов, сгенерированных из 1969 секций KB
- **Persona affinity** - каждая персона имеет kb_question_probability 0.2-0.8
- **Стартеры** - до 40% диалогов начинаются с KB вопроса вместо generic starter
- **Mid-conversation injection** - max 4 KB вопроса per dialogue когда бот не спрашивает
- **17 категорий** - вопросы по всем категориям KB (pricing, features, integrations, etc.)

**Генерация:**
```bash
python scripts/generate_kb_questions.py
# Генерирует 5904 вопросов, дедупликация до 5344
# Checkpoint/resume поддержка для больших KB
```

**Интеграция в симулятор:**
```python
# ClientAgent использует KB вопросы автоматически
result = runner.run_simulation(persona="happy_path")
# kb_question_used, kb_question_source в ClientAgentTrace
```

**Результаты:**
- Реалистичные вопросы вместо generic persona starters
- KB coverage отчет в e2e summary
- 61 тестов покрывают всю функциональность

**SSoT:** [src/simulator/kb_questions.py](../src/simulator/kb_questions.py), [scripts/generate_kb_questions.py](../scripts/generate_kb_questions.py)

### Refinement Layers NEW

Семь слоев уточнения классификации для решения контекстных проблем.

**FirstContactRefinementLayer** (Priority: HIGH)

Уточнение классификации на первом контакте (turn <= 2).

**Проблема:** LLM классифицирует cautious interest как objection на turn=1.
- Example: "слушайте мне тут посоветовали... но я не уверен"
- LLM: objection_trust → handle_objection
- Expected: consultation_request → greeting + dialog start

**Решение:**
- Детекция referral patterns ("посоветовали", "рекомендовали")
- Детекция cautious interest patterns ("не уверен", "хочу понять")
- Рефайнмент objection → consultation_request на turn <= 2

**OptionSelectionRefinementLayer** (Priority: HIGH)

Обработка выбора из предложенных опций.

**Проблема:** Ответы "1", "2", "первое" на inline questions классифицировались как request_brevity.

**Решение:**
- Детекция option patterns в last_bot_message ("или", numbered lists)
- Refinement к info_provided при numeric answer
- Fixed ClientAgent disambiguation detection (removed broad r"или\s+.+\?$" pattern)

**ComparisonRefinementLayer NEW**

Refinement comparison интентов в objection_competitor.

**Проблема:** Сравнительные вопросы классифицировались как question_features вместо objection_competitor.

**Решение:**
- Детекция comparison patterns ("чем лучше", "отличие от", "vs")
- Refinement к objection_competitor когда упомянут конкурент
- Интеграция с composed categories через direct_intents

**Примеры:**
```python
# "чем Wipon лучше Poster"
# LLM: question_features
# After refinement: objection_competitor (competitor="Poster")
```

**Приоритет:** HIGH
**Feature flag:** comparison_refinement (off by default)
**SSoT:** [src/classifier/comparison_refinement.py](../src/classifier/comparison_refinement.py)

**DataAwareRefinementLayer NEW**

Promotion unclear → info_provided когда DataExtractor находит business data.

**Проблема:** "не знаю точно но около 15 человек" классифицировался как unclear вместо info_provided.

**Решение:**
- Проверка extracted_data от DataExtractor
- Refinement unclear → info_provided если есть company_size, pain_point, business_type
- 7 новых info_provided patterns как defense-in-depth backup

**Результаты:**
- Stall rate: **54% → <10%** (false stall detection eliminated)
- Data collection: **улучшено извлечение при uncertain language**

**Приоритет:** HIGH
**Feature flag:** data_aware_refinement
**SSoT:** [src/classifier/data_aware_refinement.py](../src/classifier/data_aware_refinement.py)

**Composite Message Handling**

Приоритизация извлечения данных в составных сообщениях.

**ShortAnswer + Objection Refinement**

Контекстная валидация на основе SPIN фазы и последнего действия бота.

**Результаты:**
- First contact misclassification: **37 dialogs → 0**
- Option selection errors: **fixed 100%**
- Lost data in composite messages: **25% → <2%**
- Stall rate: **54% → <10%** (DataAwareRefinement fix)
- Comparison handling: **95%+** accuracy

**SSoT:** [src/classifier/refinement_layers.py](../src/classifier/refinement_layers.py), [src/classifier/comparison_refinement.py](../src/classifier/comparison_refinement.py), [src/classifier/data_aware_refinement.py](../src/classifier/data_aware_refinement.py)

### All-Flows Data Infrastructure

Поддержка extraction, dedup, required_data для всех 19 non-SPIN flows.

**Проблема:** Все non-SPIN flows работали в degraded mode без data infrastructure:
- No extraction fields (decision_maker, budget_range, etc.)
- No question dedup (повторяющиеся вопросы)
- No required_data transitions (data_complete не срабатывал)
- No prompt templates с {do_not_ask}, {available_questions}

**Решение:**
- Added 7 extraction fields в constants.yaml
- Extended phase_fields, phase_classification для MEDDIC, BANT, 17 shared phases
- Added generic_dedup fallback для flows без phase-specific config
- Updated 19 flow states.yaml с required_data, optional_data, on_enter flags
- Updated 19 flow prompts.yaml с {do_not_ask}, {available_questions} variables

**Новые extraction fields:**
- decision_maker, budget_range, decision_timeline
- decision_criteria, success_metrics
- champion_info, decision_process

**Результаты:**
- BANT flow data collection: **0% → 95%+**
- MEDDIC flow data collection: **0% → 95%+**
- Question dedup для всех flows: **enabled**
- Data-driven transitions: **работают для всех flows**

**SSoT:** [src/extraction_ssot.py](../src/extraction_ssot.py), [src/question_dedup.py](../src/question_dedup.py), [src/yaml_config/question_dedup.yaml](../src/yaml_config/question_dedup.yaml)

### Composed Categories with Auto-Discovery NEW

Автоматическое обнаружение категорий интентов через intent_prefix механизм.

**Проблема:** objection_return_questions содержал только 2 интента, но должен был включать все ~154 question_* интента. Вручную поддерживать такие списки невозможно.

**Решение:**
```yaml
# constants.yaml
composed_categories:
  all_questions:
    auto_include:
      intent_prefix: "question_"      # Auto-discover all question_* intents
      exclude_categories:             # Исключаем не-вопросные категории с question_* интентами
        - positive
        - informative
    includes: [price_related, company_info]

  objection_return_triggers:
    includes: [positive, price_related, all_questions]
```

**Механизм:**
- Сканирует базовые категории `intents.categories` в `constants.yaml` по префиксу `question_`
- Auto-discovers 19+ base categories: question_features, question_integrations, question_equipment, etc.
- Warnings для ghost intents (question_* not in INTENT_ROOTS)
- 7 SSOT completeness CI guard tests (test_ssot_completeness.py)

**Результаты:**
- Objection return triggers: **2 intents → ~154 intents** (all question_* + edge cases)
- question_requires_facts: converted to composed category
- OBJECTION_RETURN_QUESTIONS constant removed (DRY)

**SSoT:** [src/yaml_config/constants.py](../src/yaml_config/constants.py) (_resolve_composed_categories), [tests/test_ssot_completeness.py](../tests/test_ssot_completeness.py)

### Category Streak Tracking

Intent category streak tracking для паттерн-детекции (price, escalation, technical).

**Проблема:** Price Deflect Loop — infinite deflection cycle.
```
Turn 1: "а какая цена?" → price_question → streak=1
Turn 2: "и скидка есть?" → discount_request → streak=0 (RESET!)
Turn 3: "скажи цену" → price_question → streak=1 (RESTART!)
... infinite loop - streak never reaches 3 ...
```

**Root Cause:** intent_streak учитывает только КОНКРЕТНЫЙ intent, а не category.

**Решение:**
- Added category_streak tracking в IntentTracker
- Updated conditions: price_repeated_3x uses get_category_streak("price_related") >= 3
- Extended categories в constants.yaml:
  - price_related (7 intents)
  - escalation (8 intents)
  - frustration (6 intents)
  - sensitive (7 intents)
  - technical_question (13 intents)
- EscalationSource, PriceQuestionSource используют category_streak

**Результаты:**
- Price Deflect Loop: **141 случаев → 0**
- Price pattern detection: **55% → 95%+**
- Escalation pattern detection: **+40%** точности

**SSoT:** [src/intent_tracker.py](../src/intent_tracker.py), [src/yaml_config/constants.yaml](../src/yaml_config/constants.yaml)

### PhaseExhaustedSource NEW

Knowledge Source для обработки исчерпанных фаз, мигрированный из ConversationGuard.

**Проблема:** ConversationGuard check 6 (phase_exhausted → TIER_2) создавал race condition с DisambiguationSource. Guard fallback перезаписывал ask_clarification generic menu.

**Решение:**
- PhaseExhaustedSource (priority 60, NORMAL, combinable=True)
- Exclusive window: [phase_exhaust_threshold, stall_soft)
- ConversationGuard check 6 removed
- offer_options handler в bot.py с transition-aware logic
- generate_options_menu() в FallbackHandler

**Конфигурация:**
```yaml
# _base/states.yaml
_base_phase:
  phase_exhaust_threshold: 4  # NEW field
  max_turns_in_state: 5       # Was 6, now 5
```

**Defense-in-depth:**
- Disambiguation clears guard fallback
- Empty options guard в DisambiguationSource, bot.py, disambiguation_ui

**Результаты:**
- Race condition: **eliminated**
- Generic menu overwrite: **fixed**
- disambiguation_ui gaps fixed (подробн, систем, позже)

**Feature flag:** phase_exhausted_source
**SSoT:** [src/blackboard/sources/phase_exhausted.py](../src/blackboard/sources/phase_exhausted.py)

### StallGuard Two-Tier System NEW

Двухуровневая система детекции застревания для устранения 4-turn dead zone.

**Проблема:** 54% stall rate (3+ turns в одном state). 4-turn dead zone между nudge и eject.

**4 Root Fixes:**

**Fix 1:** Off-by-one в consecutive_same_state - компенсация timing gap где build_context_envelope() runs before add_turn_from_dict()

**Fix 1b:** has_extracted_data guard - предотвращает false stall когда user provides data но context_window has timing lag

**Fix 2:** Two-tier StallGuardSource:
- Soft tier (NORMAL priority, max_turns - 1) - предупреждение
- Hard tier (HIGH priority, max_turns) - eject
- Closes 4-turn dead zone

**Fix 3:** max_turns_in_state: **6 → 5** в _base_phase

**Fix 4:** DataAwareRefinementLayer - promotes unclear → info_provided когда DataExtractor finds business data

**Результаты:**
- Stall rate: **54% → <10%**
- 31 new targeted tests (76 total pass)

**SSoT:** [src/blackboard/sources/stall_guard.py](../src/blackboard/sources/stall_guard.py), [src/classifier/data_aware_refinement.py](../src/classifier/data_aware_refinement.py)

### Disambiguation via Blackboard NEW

Устранение ~540 lines дублированного кода через unified Blackboard pipeline.

**Проблема:** bot.py содержал параллельный disambiguation pipeline (check disambiguation, wait for response, resolve response) дублирующий Blackboard logic.

**Решение:**
- **DisambiguationSource** (KnowledgeSource) - proposes blocking ask_clarification action
- **DisambiguationResolutionLayer** (CRITICAL priority RefinementLayer) - resolves via 3 paths:
  1. Critical intent override (rejection, escalation, etc.)
  2. Option selection (1, 2, первый, второй)
  3. Custom input pass-through
- All disambiguation flows through single process() path

**Компоненты:**
- DisambiguationSource (priority 55, combinable=False blocking)
- DisambiguationResolutionLayer (CRITICAL priority layer)
- disambiguation_options, disambiguation_question в ContextEnvelope

**Результаты:**
- Code reduction: **~540 lines removed from bot.py**
- Unified pipeline: **all disambiguation через Blackboard**
- Gap cascade fixed: **GapCalibrationStrategy uses ctx.confidence**
- compound_bypass_intents: **Bypass 5 для social messages**

**SSoT:** [src/blackboard/sources/disambiguation.py](../src/blackboard/sources/disambiguation.py), [src/classifier/disambiguation_resolution_layer.py](../src/classifier/disambiguation_resolution_layer.py)

### Guard/Fallback/FSM Fixes

Комплекс из 7 interconnected fixes для guard, fallback, и FSM систем.

**Fix 1:** Classification before guard — guard использует current intent вместо stale last_intent

**Fix 2:** Valid skip target chain walker — _find_valid_skip_target() validates required_data before tier_3 skip

**Fix 3:** Tier_2 self-loop breaker — consecutive counter escalates to tier_3 after threshold (default=3)

**Fix 4:** Soft_close regression fix — removed price transitions from soft_close that regressed to presentation

**Fix 5:** Disambiguation visited_states — all 4 return dicts include visited_states/initial_state

**Fix 6:** Skip action handling — _continue_with_classification() handles skip + records progress

**Fix 7:** Guard-aware price overlay — explicit override when guard fallback pending

**Результаты:**
- E2E failures: **26 случаев → 0**
- Tier_2 self-loops: **fixed 100%**
- Soft_close regression: **fixed**
- Valid skip transitions: **95%+ корректных**

**SSoT:** [src/bot.py](../src/bot.py), [src/conversation_guard.py](../src/conversation_guard.py), [src/fallback_handler.py](../src/fallback_handler.py), [src/dialogue_policy.py](../src/dialogue_policy.py)

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
from src.feature_flags import flags

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

**NEW Feature Flags (январь-февраль 2026):**

| Флаг | Описание | Статус |
|------|----------|--------|
| `phase_exhausted_source` | PhaseExhaustedSource в Blackboard | Production |
| `data_aware_refinement` | DataAwareRefinementLayer | Production |
| `comparison_refinement` | ComparisonRefinementLayer | Off (risky) |
| `intent_pattern_guard` | IntentPatternGuardSource | Off (risky) |
| `conversation_guard_in_pipeline` | ConversationGuard as KnowledgeSource | Off (gradual rollout) |
| `kb_sourced_cta_options` | KB-sourced CTA fallback options | Production |
| `cta_backoff_gating` | Gate CTA при backing-off language | Production |
| `stall_guard_dual_proposal` | StallGuard dual proposal (action + transition) | Production |
| `phase_completion_gating` | has_completed_minimum_phases condition | Production |

**Флаги в тестировании (выключены):**

| Флаг | Описание |
|------|----------|
| `lead_scoring` | Скоринг лидов |
| `objection_handler` | Продвинутая обработка возражений |
| `cta_generator` | Генерация Call-to-Action |
| `personalization_v2` | V2 engine с behavioral adaptation |
| `comparison_refinement` | ComparisonRefinementLayer (off by default) |
| `intent_pattern_guard` | IntentPatternGuardSource (off by default) |

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

## Ключевые изменения v3.0 (Январь 2026)

### Configurable Objection Limits

Лимиты возражений теперь читаются из `constants.yaml` вместо хардкода:

```yaml
# constants.yaml
limits:
  max_consecutive_objections: 3
  max_total_objections: 5
```

**Было:** Хардкод в 12+ местах кода
**Стало:** SSOT в YAML, автоматическая загрузка через EvaluatorContext и PolicyContext

### Atomic State Transitions

Новый метод `transition_to()` для атомарных изменений состояний:

```python
# Было (distributed mutation)
state_machine.state = "spin_problem"  # только state
state_machine.current_phase = "problem"  # отдельно phase

# Стало (atomic)
state_machine.transition_to("spin_problem")  # state + phase + last_action atomically
```

**Проблема:** Orchestrator и bot.py изменяли state независимо, приводя к несогласованности state/phase/last_action.
**Решение:** transition_to() обеспечивает атомарные изменения, sync_phase_from_state() как safety net.

### State Before Objection Tracking

Автоматическое отслеживание состояния до возражения:

```python
# Orchestrator._apply_side_effects()
def _update_state_before_objection(prev_state, next_state, intent):
    if next_state == "handle_objection":
        self._state_before_objection = prev_state  # Save
    elif intent in POSITIVE_INTENTS:
        self._state_before_objection = None  # Clear on positive intent
```

**Проблема:** _state_before_objection никогда не устанавливался, get_return_state() всегда возвращал None.
**Решение:** Автоматическое сохранение при входе в handle_objection, очистка при разрешении.

### Universal Phase Resolution

Все 21 flows теперь работают с phase detection:

```python
# FlowConfig.state_to_phase property (reverse mapping)
# FlowConfig.get_phase_for_state() - canonical method

# Было: только SPIN flow поддерживал фазы
# Стало: все flows (BANT, MEDDIC, etc.) с автоопределением current_phase
```

### CircularFlowManager as Single Source of Truth

Весь go_back logic в одном месте:

```python
# NEW methods:
CircularFlowManager.is_limit_reached() - explicit limit check
CircularFlowManager.can_go_back(yaml_transitions) - check availability
CircularFlowManager.get_go_back_target() - get target from YAML or allowed_gobacks
CircularFlowManager.record_go_back() - deferred counter increment
```

**Deferred Increment:** GoBackGuardSource больше не инкрементирует счетчик до conflict resolution. Инкремент происходит только если go_back действительно произошел.

## Модули системы

| Модуль | Назначение |
|--------|------------|
| `bot.py` | Оркестрация: classifier → state_machine → generator + DecisionTracing + visited_states |
| `llm.py` | OllamaClient с circuit breaker, retry, LLMTrace |
| `state_machine.py` | FSM с модульной YAML конфигурацией + atomic transitions |
| `generator.py` | Генерация ответов + SafeDict template substitution + response deduplication |
| `decision_trace.py` | **DecisionTrace, DecisionTraceBuilder, LLMTrace, ClientAgentTrace** — комплексная трассировка решений |
| `classifier/unified.py` | Адаптер для переключения классификаторов |
| `classifier/llm/` | LLM классификатор (300 интентов в 34 категориях) |
| `classifier/llm/few_shot.py` | **Few-shot примеры** для улучшения классификации (request_brevity, objection_competitor) |
| `classifier/hybrid.py` | Regex-based классификатор (fallback) |
| `classifier/refinement_pipeline.py` | RefinementPipeline (Protocol, Registry, Pipeline) |
| `classifier/refinement_layers.py` | **5 refinement layers** (FirstContact, OptionSelection, ShortAnswer, Composite, Objection) |
| `classifier/confidence_calibration.py` | **ConfidenceCalibrationLayer** (научная калибровка: entropy, gap, heuristics) |
| `classifier/secondary_intent_detection.py` | **SecondaryIntentDetectionLayer** (обработка составных сообщений, 365 patterns) |
| `knowledge/retriever.py` | CascadeRetriever (3-этапный поиск) |
| `knowledge/category_router.py` | LLM-классификация категорий |
| `knowledge/reranker.py` | Cross-encoder переоценка |
| `feature_flags.py` | **Управление фичами** (42+ флагов, +7 новых) |
| `settings.py` | Конфигурация из YAML |
| `config.py` | Интенты, состояния, промпты |
| `config_loader.py` | ConfigLoader, FlowConfig для YAML flow + intent category/action overrides |
| `rules/resolver.py` | RuleResolver с taxonomy-based fallback |
| `rules/intent_taxonomy.py` | IntentTaxonomyRegistry (5-level fallback chain) |
| `validation/intent_coverage.py` | IntentCoverageValidator (zero unmapped intents) |
| `yaml_config/` | **YAML конфигурация** (97+ files: states, flows, templates, +27 новых) |
| `yaml_config/constants.yaml` | **SSOT** (~6600+ строк taxonomy + secondary_intent + category definitions) |
| `dag/` | DAG State Machine (CHOICE, FORK/JOIN, History) |
| `context_window.py` | **Расширенный контекст диалога** (secondary_intents, repeated_question lag fix) |
| `dialogue_policy.py` | Context-aware policy overlays + price question override |
| `context_envelope.py` | **Построение контекста** (pre_intervention_triggered propagation) |
| `intent_tracker.py` | **Трекинг интентов** (category_streak для price_related, escalation, technical_question) |
| `response_directives.py` | Директивы для генератора + repair_mode context enrichment |
| `conversation_guard.py` | **Защита от зацикливания** (tier_2 self-loop breaker, informative intent check) |
| `fallback_handler.py` | **Multi-tier fallback** (flow-aware skip_map, valid skip target chain walker) |
| `tone_analyzer/frustration_tracker.py` | **Трекинг фрустрации** (FrustrationIntensityCalculator integration) |
| `tone_analyzer/frustration_intensity.py` | **FrustrationIntensityCalculator** (intensity-based scoring, pre-intervention) |
| `tone_analyzer/structural_frustration.py` | **Структурная детекция** (unanswered repeats, deflection loops, tonal decay) |
| `question_dedup.py` | **Question deduplication** (all-flows support, generic fallback, 20 phase_questions) |
| `extraction_ssot.py` | **Data extraction** (7 новых полей для MEDDIC/BANT, flow-agnostic) |
| `cta_generator.py` | **CTA generation** (STATE_TO_CTA_PHASE mapping для 21 flows, phase-based templates) |
| `blackboard/sources/objection_return.py` | **ObjectionReturnSource** (HIGH priority, total-based escape, phase restoration) |
| `blackboard/sources/fact_question.py` | **FactQuestionSource** (17 KB categories, secondary_intents, count-based conditions) |
| `blackboard/sources/price_question.py` | **PriceQuestionSource** (category_streak для 7 price_related intents) |
| `blackboard/sources/escalation.py` | **EscalationSource** (category_streak для 8 escalation intents) |
| `blackboard/sources/objection_guard.py` | **ObjectionGuardSource** (persona-based limits: tire_kicker 6/12, skeptic 4/7) |
| `simulator/` | **Симулятор диалогов** (100 dialogs, 8 threads, 90% pass rate, 0.750 avg score) |
| `simulator/client_agent.py` | **ClientAgent** (persona insistence, disambiguation fix, contact collection) |
| `simulator/metrics.py` | Сбор метрик с visited_states для точного phase coverage |
| `simulator/runner.py` | SimulationRunner с visited_states tracking + persona passing |
| `simulator/personas.py` | **8 personas** (с calibrated objection limits и insistence probability) |

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
    spin_coverage: float   # 0.0 - 1.0 (NEW: based on visited_states)
    objections_count: int
    fallback_count: int
    collected_data: Dict
    rule_traces: List[Dict]  # Трассировка условных правил
    decision_traces: List[DecisionTrace]  # Полная трассировка решений
    client_traces: List[ClientAgentTrace]  # Трассировка поведения клиента
    visited_states: List[str]  # NEW: все посещенные состояния за ход
    initial_state: str        # NEW: начальное состояние хода
```

### Phase Coverage Fix

**Проблема:** Fallback skip вызывал переходы через промежуточные состояния (greeting → spin_situation → spin_problem), но записывалось только финальное состояние. Phase coverage показывал 0.0-0.25 вместо 0.6+.

**Решение:**
- bot.py: добавлен visited_states list для отслеживания всех состояний за ход
- runner.py: записывает visited_states и initial_state в turn_data
- metrics.py: использует visited_states для извлечения фаз (с fallback на decision_trace)

**Результат:** Корректный phase coverage даже при множественных fallback skips.

### Параллельное выполнение

Симулятор поддерживает параллельное выполнение через ThreadPoolExecutor:

```bash
# Параллельный запуск 8 потоков (по умолчанию)
python -m src.simulator --parallel 8 -n 100

# GPU pre-warming для embedding models
# FRIDA semantic tone analyzer и BGE reranker предварительно загружаются
# перед параллельным выполнением для избежания "Cannot copy out of meta tensor" ошибок
```

**Улучшения производительности:**
- GPU поддержка для embedding models (FRIDA, BGE)
- Pre-warming моделей перед параллельным выполнением
- ~2x ускорение при parallel=8 с OLLAMA_NUM_PARALLEL=8

## Decision Tracing System

Комплексная система трассировки всех решений бота для анализа и отладки (коммит 10f90c1).

### Компоненты

| Компонент | Назначение |
|-----------|------------|
| `DecisionTrace` | Полная трассировка одного хода диалога |
| `DecisionTraceBuilder` | Builder pattern для построения трассировки |
| `ClassificationTrace` | Трассировка классификации интента |
| `ToneAnalysisTrace` | Трассировка анализа тона |
| `GuardCheckTrace` | Трассировка проверок ConversationGuard |
| `StateMachineTrace` | Трассировка state machine решений |
| `FallbackTrace` | Трассировка fallback механизмов |
| `LeadScoreTrace` | Трассировка скоринга лидов |
| `LLMTrace` | Трассировка LLM вызовов (tokens, latency) |
| `ClientAgentTrace` | Трассировка поведения симулируемого клиента |
| `DecisionStatistics` | Агрегированная статистика по трассировкам |

### Использование

```python
from src.bot import SalesBot

bot = SalesBot()

# Обработка с трассировкой
response = bot.process("сколько стоит?")

# Получить последнюю трассировку
trace = bot.get_last_decision_trace()
print(f"Classification: {trace.classification.intent} ({trace.classification.confidence})")
print(f"State machine: {trace.state_machine.action} → {trace.state_machine.next_state}")
print(f"Total LLM tokens: {sum(llm.total_tokens for llm in trace.llm_calls)}")

# Агрегированная статистика
stats = bot.get_decision_statistics()
print(f"Classification accuracy: {stats.classification_stats['accuracy']}")
print(f"Average response time: {stats.timing_stats['avg_total_ms']}ms")
```

### DecisionTrace структура

```python
@dataclass
class DecisionTrace:
    turn_number: int
    timestamp: float

    # Classification
    classification: ClassificationTrace

    # Tone Analysis
    tone_analysis: Optional[ToneAnalysisTrace]

    # Guard Checks
    guard_checks: List[GuardCheckTrace]

    # State Machine
    state_machine: StateMachineTrace

    # Fallback
    fallback: Optional[FallbackTrace]

    # Lead Scoring
    lead_score: Optional[LeadScoreTrace]

    # LLM Calls (все вызовы за ход)
    llm_calls: List[LLMTrace]

    # Timing
    timing: Dict[str, float]  # ms по этапам
```

### LLMTrace для профилирования

```python
@dataclass
class LLMTrace:
    model: str
    operation: str  # "classify", "generate", "tone_analyze"

    # Tokens (оценка)
    input_tokens: int
    output_tokens: int
    total_tokens: int

    # Latency
    latency_ms: float

    # Result
    success: bool
    error: Optional[str]
```

### Интеграция в отчеты симулятора

Симулятор автоматически собирает decision traces и генерирует аналитику:

```
========================================
DECISION ANALYSIS
========================================

Classification Statistics:
- Total classifications: 2336
- Accuracy: 94.2%
- Top intents: price_question (423), situation_provided (312)

State Machine Statistics:
- Total transitions: 2336
- Policy overrides: 127 (5.4%)
- Fallback usage: 23 (1.0%)

Timing Analysis:
- Avg classification: 124ms
- Avg generation: 856ms
- Avg total turn: 1034ms
```

## Response Quality Improvements

### 1. Template Variable Substitution (коммит 39c7109)

**Проблема:** Переменные шаблонов отображались как `{style_full_instruction}` в ответах клиенту.

**Решение:**
- **SafeDict** — безопасная подстановка возвращает пустую строку вместо KeyError
- **PERSONALIZATION_DEFAULTS** — fallback значения для всех переменных персонализации
- **_apply_legacy_personalization()** — заполнение переменных при выключенной personalization_v2

```python
# generator.py
class SafeDict(dict):
    def __missing__(self, key):
        return ""  # Вместо KeyError

PERSONALIZATION_DEFAULTS = {
    "style_full_instruction": "",
    "bc_value_prop": "увеличите эффективность бизнеса",
    "pain_point": "текущие сложности",
    # ...
}

# Безопасная подстановка
template.format_map(SafeDict({**PERSONALIZATION_DEFAULTS, **variables}))
```

**Результаты:**
- `{pain_point}`: 75 → 0 вхождений
- `{bc_value_prop}`: 9 → 0 вхождений
- `{style_full_instruction}`: 145 → 0 предупреждений

### 2. Response Deduplication (коммит 13d820e)

**Проблема:** Повторяющиеся ответы ("Понимаю, сейчас это не приоритет" x393).

**Решение:**
- **Jaccard similarity** — вычисление схожести между ответами
- **Response history** — отслеживание последних 5 ответов
- **_regenerate_with_diversity** — регенерация при обнаружении дубликата
- **do_not_repeat_responses** директива для генератора

```python
# generator.py
def _is_duplicate(self, text: str, threshold: float = 0.7) -> bool:
    """Проверка на дубликат через Jaccard similarity."""
    words = set(text.lower().split())
    for prev in self._response_history[-5:]:
        prev_words = set(prev.lower().split())
        if not words or not prev_words:
            continue
        similarity = len(words & prev_words) / len(words | prev_words)
        if similarity >= threshold:
            return True
    return False
```

**Результаты:**
- Уникальность ответов: 76% → 94%
- Повторы: 82 → 11 случаев

### 3. Price Question Override (коммит 13d820e)

**Проблема:** Вопросы о цене игнорировались в 25 случаях.

**Решение:**
- **Intent-aware override** в DialoguePolicy
- **price_related intent category** в constants.yaml
- **is_price_question policy condition** с overlay
- **answer_with_pricing template** с явными инструкциями

```python
# dialogue_policy.py
def _check_price_override(self, intent: str) -> Optional[PolicyDecision]:
    """Intent-aware override для вопросов о цене."""
    if self.flow_config.is_intent_in_category(intent, "price_related"):
        return PolicyDecision.PRICE_QUESTION
    return None
```

**Результаты:**
- Вопросы о цене: 81% игнорирование → **95%+** правильные ответы

### 4. Guard/Fallback Fixes (коммит 4d5bad9)

**Проблема:** Ложные TIER_3 вмешательства при информативных ответах клиента.

**Решение:**
- **Informative intent check** перед TIER_3
- **fallback_response reset** после skip action
- **guard_informative_intent_check** feature flag

```python
# conversation_guard.py
def _is_informative_response(self, last_intent: str) -> bool:
    """Проверка на информативный интент."""
    INFORMATIVE_INTENTS = {
        "info_provided", "situation_provided", "problem_revealed",
        "need_expressed", "implication_acknowledged", "contact_provided"
    }
    return last_intent in INFORMATIVE_INTENTS or \
           self._is_intent_category(last_intent, "informative")
```

**Результаты:**
- Ложные TIER_3: 18% → **<2%**

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
