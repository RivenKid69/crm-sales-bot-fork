# Settings — Конфигурация CRM Sales Bot

## Обзор

Все настраиваемые параметры бота вынесены в файлы конфигурации:

- **`src/settings.yaml`** — основные настройки (LLM, retriever, feature flags)
- **`src/yaml_config/`** — структурированная конфигурация (states, flows, constants)

Это позволяет изменять поведение системы без правки кода.

## Файл настроек

**Расположение:** `src/settings.yaml`

```yaml
# =============================================================================
# НАСТРОЙКИ CRM SALES BOT
# =============================================================================

# -----------------------------------------------------------------------------
# LLM (Language Model) - Ollama Server
# -----------------------------------------------------------------------------
llm:
  model: "qwen3:14b"
  base_url: "http://localhost:11434"
  timeout: 120
  stream: false

# -----------------------------------------------------------------------------
# RETRIEVER (Поиск по базе знаний)
# -----------------------------------------------------------------------------
retriever:
  use_embeddings: true
  embedder_model: "ai-forever/FRIDA"
  thresholds:
    exact: 1.0
    lemma: 0.15
    semantic: 0.5
  default_top_k: 2

# -----------------------------------------------------------------------------
# RERANKER (Переоценка результатов при низком score)
# -----------------------------------------------------------------------------
reranker:
  enabled: true
  model: "BAAI/bge-reranker-v2-m3"
  threshold: 0.5
  candidates_count: 10

# -----------------------------------------------------------------------------
# CATEGORY ROUTER (LLM-классификация категорий)
# -----------------------------------------------------------------------------
category_router:
  enabled: true
  top_k: 3
  fallback_categories:
    - "faq"
    - "features"

# -----------------------------------------------------------------------------
# GENERATOR (Генерация ответов)
# -----------------------------------------------------------------------------
generator:
  max_retries: 3
  history_length: 4
  retriever_top_k: 2
  allowed_english_words:
    - "crm"
    - "api"
    - "ok"
    - "id"
    - "ip"
    - "sms"
    - "email"
    - "excel"
    - "whatsapp"
    - "telegram"
    - "hr"
    - "pos"
    - "erp"

# -----------------------------------------------------------------------------
# CLASSIFIER (Классификация интентов)
# -----------------------------------------------------------------------------
classifier:
  weights:
    root_match: 1.0
    phrase_match: 2.0
    lemma_match: 1.5
  merge_weights:
    root_classifier: 0.6
    lemma_classifier: 0.4
  thresholds:
    high_confidence: 0.7
    min_confidence: 0.3

# -----------------------------------------------------------------------------
# LOGGING (Логирование)
# -----------------------------------------------------------------------------
logging:
  level: "INFO"
  log_llm_requests: false
  log_retriever_results: false

# -----------------------------------------------------------------------------
# CONDITIONAL RULES (Phase 8: Условные правила)
# -----------------------------------------------------------------------------
conditional_rules:
  enable_tracing: true
  log_level: "INFO"
  log_context: false
  log_each_condition: false
  validate_on_startup: true
  coverage_threshold: 0.8

# -----------------------------------------------------------------------------
# FEATURE FLAGS (Управление фичами)
# -----------------------------------------------------------------------------
feature_flags:
  # LLM классификатор
  llm_classifier: true

  # Фаза 0: Инфраструктура
  structured_logging: true
  metrics_tracking: true

  # Фаза 1: Защита и надёжность
  multi_tier_fallback: true
  conversation_guard: true

  # Фаза 2: Естественность диалога
  tone_analysis: false
  response_variations: true
  personalization: false

  # Фаза 3: Оптимизация SPIN Flow
  lead_scoring: false
  circular_flow: false
  objection_handler: false
  cta_generator: false

# -----------------------------------------------------------------------------
# FLOW (Конфигурация диалогового flow)
# -----------------------------------------------------------------------------
flow:
  # Активный flow (имя директории в yaml_config/flows/)
  active: "spin_selling"

# -----------------------------------------------------------------------------
# DEVELOPMENT (Режим разработки)
# -----------------------------------------------------------------------------
development:
  debug: false
  skip_embeddings: false
```

## Параметры

### LLM (Ollama Server)

| Параметр | Тип | По умолчанию | Описание |
|----------|-----|--------------|----------|
| `model` | string | `"qwen3:14b"` | Модель Ollama (qwen3:14b - стандарт проекта) |
| `base_url` | string | `"http://localhost:11434"` | URL Ollama сервера (native API) |
| `timeout` | int | `120` | Таймаут запроса в секундах |
| `stream` | bool | `false` | Режим стриминга |

**Запуск Ollama сервера:**
```bash
# Установка
curl -fsSL https://ollama.ai/install.sh | sh

# Скачать модель
ollama pull qwen3:14b

# Запуск
ollama serve
```

**Требования:** ~12-16 GB VRAM, CUDA GPU

### RETRIEVER (Поиск по базе знаний)

| Параметр | Тип | По умолчанию | Описание |
|----------|-----|--------------|----------|
| `use_embeddings` | bool | `true` | Использовать семантический поиск |
| `embedder_model` | string | `"ai-forever/FRIDA"` | Модель для эмбеддингов (ruMTEB avg ~71) |
| `thresholds.exact` | float | `1.0` | Порог для exact match |
| `thresholds.lemma` | float | `0.15` | Порог для lemma match |
| `thresholds.semantic` | float | `0.5` | Порог для semantic match |
| `default_top_k` | int | `2` | Количество результатов по умолчанию |

**Пороги:**
- `exact: 1.0` — требуется минимум 1 полное совпадение keyword
- `lemma: 0.15` — низкий порог для широкого охвата
- `semantic: 0.5` — средний порог для баланса точности/охвата

### RERANKER (Переоценка результатов)

| Параметр | Тип | По умолчанию | Описание |
|----------|-----|--------------|----------|
| `enabled` | bool | `true` | Включить reranker fallback |
| `model` | string | `"BAAI/bge-reranker-v2-m3"` | Модель cross-encoder |
| `threshold` | float | `0.5` | Порог score ниже которого включается |
| `candidates_count` | int | `10` | Сколько кандидатов переоценивать |

### CATEGORY ROUTER (LLM-классификация)

| Параметр | Тип | По умолчанию | Описание |
|----------|-----|--------------|----------|
| `enabled` | bool | `true` | Включить LLM-классификацию |
| `top_k` | int | `3` | Количество возвращаемых категорий |
| `fallback_categories` | list | `["faq", "features"]` | Категории по умолчанию при ошибке |

### GENERATOR (Генерация ответов)

| Параметр | Тип | По умолчанию | Описание |
|----------|-----|--------------|----------|
| `max_retries` | int | `3` | Количество retry при иностранном тексте |
| `history_length` | int | `4` | Количество сообщений в контексте |
| `retriever_top_k` | int | `2` | Количество фактов из базы знаний |
| `allowed_english_words` | list | см. выше | Разрешённые английские слова |

### CLASSIFIER (Классификация интентов)

| Параметр | Тип | По умолчанию | Описание |
|----------|-----|--------------|----------|
| `weights.root_match` | float | `1.0` | Вес совпадения по корню (для HybridClassifier) |
| `weights.phrase_match` | float | `2.0` | Вес точного совпадения фразы |
| `weights.lemma_match` | float | `1.5` | Вес совпадения по лемме |
| `merge_weights.root_classifier` | float | `0.6` | Вес RootClassifier при слиянии |
| `merge_weights.lemma_classifier` | float | `0.4` | Вес LemmaClassifier при слиянии |
| `thresholds.high_confidence` | float | `0.7` | Порог высокой уверенности |
| `thresholds.min_confidence` | float | `0.3` | Минимальная уверенность |

### LOGGING (Логирование)

| Параметр | Тип | По умолчанию | Описание |
|----------|-----|--------------|----------|
| `level` | string | `"INFO"` | Уровень логирования |
| `log_llm_requests` | bool | `false` | Логировать запросы к LLM |
| `log_retriever_results` | bool | `false` | Логировать результаты retriever |

### CONDITIONAL RULES (Условные правила)

| Параметр | Тип | По умолчанию | Описание |
|----------|-----|--------------|----------|
| `enable_tracing` | bool | `true` | Включить трассировку правил |
| `log_level` | string | `"INFO"` | Уровень логирования правил |
| `log_context` | bool | `false` | Логировать контекст при проверке |
| `log_each_condition` | bool | `false` | Логировать каждую проверку |
| `validate_on_startup` | bool | `true` | Валидация при старте |
| `coverage_threshold` | float | `0.8` | Минимальное покрытие условий в тестах |

### FEATURE FLAGS (Управление фичами)

Feature flags позволяют постепенно включать новые возможности без изменения кода.

| Флаг | По умолчанию | Описание |
|------|--------------|----------|
| **LLM Classifier** | | |
| `llm_classifier` | `true` | LLM классификатор вместо Hybrid |
| **Фаза 0: Инфраструктура** | | |
| `structured_logging` | `true` | JSON логи для production |
| `metrics_tracking` | `true` | Трекинг метрик диалогов |
| **Фаза 1: Защита** | | |
| `multi_tier_fallback` | `true` | 4-уровневый fallback |
| `conversation_guard` | `true` | Защита от зацикливания |
| **Фаза 2: Естественность** | | |
| `tone_analysis` | `true` | Анализ тона клиента |
| `response_variations` | `true` | Вариативность ответов |
| `cascade_tone_analyzer` | `true` | Каскадный анализатор тона |
| `tone_semantic_tier2` | `true` | Tier 2: FRIDA semantic |
| `tone_llm_tier3` | `true` | Tier 3: LLM fallback |
| **Фаза 3: SPIN Optimization** | | |
| `personalization` | `false` | Персонализация |
| `lead_scoring` | `false` | Скоринг лидов |
| `circular_flow` | `false` | Возврат назад по фазам |
| `objection_handler` | `false` | Обработка возражений |
| `cta_generator` | `false` | Call-to-Action |
| **Фаза 4: Classification** | | |
| `cascade_classifier` | `true` | Каскадный классификатор |
| `semantic_objection_detection` | `true` | Семантическая детекция возражений |
| `intent_disambiguation` | `false` | Уточнение намерения при близких scores |
| **Фаза 5: Context Policy** | | |
| `context_full_envelope` | `true` | Полный ContextEnvelope |
| `context_response_directives` | `true` | ResponseDirectives для генератора |
| `context_policy_overlays` | `true` | DialoguePolicy overrides |
| `context_shadow_mode` | `false` | Shadow mode для policy |
| `context_engagement_v2` | `false` | Улучшенный расчёт engagement |
| `context_cta_memory` | `false` | CTA с учётом episodic memory |
| `dynamic_cta_fallback` | `false` | Динамические CTA в fallback |
| **Response Quality** | | |
| `response_deduplication` | `true` | Проверка на дублирующиеся ответы |
| `price_question_override` | `true` | Intent-aware override для вопросов о цене |
| **Guard/Fallback Fixes** | | |
| `guard_informative_intent_check` | `true` | Проверка информативных интентов перед TIER_3 |
| `guard_skip_resets_fallback` | `true` | Сброс fallback_response после skip action |
| **Robust Classification** | | |
| `confidence_router` | `true` | Gap-based решения и graceful degradation |
| `confidence_router_logging` | `true` | Логирование слепых зон для self-learning |
| **Personalization V2** | | |
| `personalization_v2` | `false` | V2 engine с behavioral adaptation |
| `personalization_adaptive_style` | `false` | AdaptiveStyleSelector |
| `personalization_semantic_industry` | `false` | IndustryDetectorV2 semantic matching |
| `personalization_session_memory` | `false` | EffectiveActionTracker |

**Переопределение через env:**
```bash
# Переключиться на HybridClassifier
FF_LLM_CLASSIFIER=false python bot.py

# Включить tone_analysis
FF_TONE_ANALYSIS=true python bot.py
```

### FLOW (Конфигурация диалогового flow)

| Параметр | Тип | По умолчанию | Описание |
|----------|-----|--------------|----------|
| `active` | string | `"spin_selling"` | Активный flow из `yaml_config/flows/` |

**Доступные flows:**
- `spin_selling` — SPIN Selling methodology (Situation, Problem, Implication, Need-Payoff)
- Создайте собственный flow в `yaml_config/flows/<name>/`

**Структура flow:**
```
yaml_config/flows/<name>/
├── flow.yaml       # Конфигурация flow (phases, skip_conditions)
└── states.yaml     # Специфичные состояния для этого flow
```

### DEVELOPMENT (Режим разработки)

| Параметр | Тип | По умолчанию | Описание |
|----------|-----|--------------|----------|
| `debug` | bool | `false` | Режим отладки (больше логов) |
| `skip_embeddings` | bool | `false` | Пропустить инициализацию эмбеддингов |

## Использование в коде

### Импорт настроек

```python
from settings import settings

# Доступ через точку
model = settings.llm.model
threshold = settings.retriever.thresholds.lemma
allowed = settings.generator.allowed_english_words
```

### Получение по пути

```python
from settings import settings

value = settings.get_nested("retriever.thresholds.semantic")
# -> 0.5

value = settings.get_nested("nonexistent.path", default="fallback")
# -> "fallback"
```

### Перезагрузка настроек

```python
from settings import reload_settings

# После изменения settings.yaml
reload_settings()
```

### Использование Feature Flags

```python
from feature_flags import flags

# Проверка флага (property)
if flags.llm_classifier:
    # использовать LLM классификатор

# Проверка флага (метод)
if flags.is_enabled("tone_analysis"):
    analyzer = ToneAnalyzer()

# Получить все флаги
all_flags = flags.get_all_flags()

# Получить включённые флаги
enabled = flags.get_enabled_flags()

# Override в runtime
flags.set_override("tone_analysis", True)
flags.clear_override("tone_analysis")

# Группы
flags.enable_group("phase_3")
flags.disable_group("risky")
```

## Профили настроек

### Быстрый старт (без эмбеддингов)

```yaml
retriever:
  use_embeddings: false

reranker:
  enabled: false

category_router:
  enabled: false

development:
  skip_embeddings: true
```

Плюсы: старт за ~1 секунду
Минусы: только exact и lemma поиск

### Максимальная точность

```yaml
retriever:
  use_embeddings: true
  thresholds:
    lemma: 0.10
    semantic: 0.4
  default_top_k: 3

reranker:
  enabled: true
  candidates_count: 15

category_router:
  enabled: true
  top_k: 5

generator:
  retriever_top_k: 3
```

### Production

```yaml
logging:
  level: "WARNING"
  log_llm_requests: false
  log_retriever_results: false

feature_flags:
  llm_classifier: true
  structured_logging: true
  metrics_tracking: true
  multi_tier_fallback: true
  conversation_guard: true
  response_variations: true
  cascade_classifier: true
  context_full_envelope: true
  context_policy_overlays: true

development:
  debug: false
```

### Режим отладки

```yaml
logging:
  level: "DEBUG"
  log_llm_requests: true
  log_retriever_results: true

conditional_rules:
  enable_tracing: true
  log_context: true
  log_each_condition: true

development:
  debug: true
```

## CLI для проверки

```bash
# Вывести текущие настройки
cd src && python settings.py

# Вывести feature flags
cd src && python feature_flags.py
```

## Тестирование

### Запуск тестов

```bash
# Все тесты конфигурации (1780+ тестов)
pytest tests/test_config*.py -v

# Тесты настроек
pytest tests/test_settings.py -v

# Тесты feature flags
pytest tests/test_feature_flags.py -v

# Edge cases (граничные значения, unicode, конкурентность)
pytest tests/test_config_edge_cases.py -v

# Property-based тесты (Hypothesis)
pytest tests/test_config_property_based.py -v

# Расширенные тесты (190 тестов)
pytest tests/test_config_dynamic_changes.py tests/test_config_conflicts.py \
       tests/test_config_complex_conditions.py tests/test_config_unreachable_states.py \
       tests/test_config_template_interpolation.py tests/test_config_multi_tenant.py \
       tests/test_config_stress_performance.py tests/test_config_migration.py -v
```

### Покрытие тестами

Система конфигурации покрыта **1780+ тестами**:

| Категория | Файл | Тестов | Описание |
|-----------|------|--------|----------|
| **Базовые тесты** | | | |
| Settings YAML | `test_config_settings_yaml.py` | 89 | Параметры settings.yaml |
| Constants YAML | `test_config_constants_yaml.py` | 133 | Параметры constants.yaml |
| Flow YAML | `test_config_flow_yaml.py` | 137 | Структура flow.yaml |
| Integration | `test_config_integration.py` | 16 | ConfigLoader + Parser + Resolver |
| Behavior (settings) | `test_config_behavior_settings.py` | 78 | Поведение компонентов |
| Behavior (constants) | `test_config_behavior_constants.py` | 112 | Поведение с constants |
| Behavior (flags) | `test_config_behavior_feature_flags.py` | 38 | Влияние feature flags |
| E2E сценарии | `test_config_e2e_scenarios.py` | 26 | Полные диалоговые сценарии |
| Edge cases | `test_config_edge_cases.py` | 72 | Граничные значения |
| Property-based | `test_config_property_based.py` | 38 | Автогенерация Hypothesis |
| **Расширенные тесты (190)** | | | |
| Dynamic Changes | `test_config_dynamic_changes.py` | 22 | Runtime-изменение конфигурации |
| Conflicts | `test_config_conflicts.py` | 22 | Конфликты между параметрами |
| Complex Conditions | `test_config_complex_conditions.py` | 25 | Вложенные AND/OR/NOT |
| Unreachable States | `test_config_unreachable_states.py` | 24 | BFS/DFS анализ графа |
| Template Interpolation | `test_config_template_interpolation.py` | 25 | {{variable}}, circular refs |
| Multi-tenant | `test_config_multi_tenant.py` | 24 | Изоляция конфигов |
| Stress/Performance | `test_config_stress_performance.py` | 24 | Нагрузочные тесты |
| Migration | `test_config_migration.py` | 24 | Миграция версий |

### Расширенные тесты конфигурации

Расширенные тесты покрывают критичные сценарии:

**Dynamic Changes** — изменение параметров в runtime:
- Hot reload конфигурации
- Thread-safe обновления
- Синхронизация компонентов

**Conflicts** — обнаружение конфликтов:
- Несовместимые threshold значения
- Недействительные ссылки на состояния
- Циклические зависимости

**Complex Conditions** — вложенные условия:
- Глубокая вложенность AND/OR/NOT
- Short-circuit evaluation
- Законы Де Моргана

**Unreachable States** — анализ графа:
- BFS/DFS обход состояний
- Обнаружение orphan состояний
- Dead-end детекция

**Template Interpolation** — переменные в шаблонах:
- Вложенная интерполяция {{a.{{b}}}}
- Circular reference детекция
- Сохранение типов (int, bool, list)

**Multi-tenant** — изоляция tenant:
- Независимые конфигурации
- Deep copy изоляция
- Config inheritance

**Stress/Performance** — нагрузка:
- Большие конфиги (1000+ states)
- Concurrent доступ
- Memory leak детекция

**Migration** — миграция версий:
- Version detection
- Migration path
- Backwards compatibility

### Edge Case тесты

`test_config_edge_cases.py` покрывает:

- **Граничные значения** — `max_turns=0/1/999999/-1`, `timeout=0/86400`
- **Пустые значения** — пустые templates, categories, phases
- **Типы данных** — string "25", float 25.7, "true" vs true
- **Unicode/кодировки** — русский текст, emoji, BOM
- **Файловые ошибки** — not found, invalid YAML, read-only, empty
- **Конкурентность** — многопоточное чтение конфигов
- **Сложные условия** — глубокая вложенность and/or/not
- **Консистентность** — guard.threshold == frustration.threshold

### Property-based тесты

`test_config_property_based.py` использует [Hypothesis](https://hypothesis.readthedocs.io/) для автоматической генерации тестовых данных:

```python
@given(
    max_turns=st.integers(min_value=1, max_value=1000),
    timeout=st.integers(min_value=1, max_value=86400)
)
def test_guard_config_with_positive_values(max_turns, timeout):
    """Любые положительные значения должны загружаться."""
    config = {"guard": {"max_turns": max_turns, "timeout_seconds": timeout}}
    loaded = yaml.safe_load(yaml.dump(config))
    assert loaded['guard']['max_turns'] == max_turns
```

Преимущества:
- Автоматическое обнаружение edge cases
- Тысячи комбинаций параметров за секунды
- Воспроизводимость через seed

## YAML Configuration (yaml_config/)

Помимо `settings.yaml`, система использует структурированную YAML конфигурацию.

### Структура yaml_config/

```
src/yaml_config/
├── constants.yaml          # Константы (limits, intents, policy)
├── spin/phases.yaml        # Конфигурация SPIN фаз
├── states/sales_flow.yaml  # Состояния диалога
├── conditions/custom.yaml  # Кастомные условия для rules
│
├── flows/                  # Модульные flow
│   ├── _base/              # Базовые компоненты
│   │   ├── states.yaml     # Общие состояния
│   │   ├── mixins.yaml     # Переиспользуемые блоки
│   │   └── priorities.yaml # Приоритеты обработки
│   └── spin_selling/       # SPIN Selling flow
│       ├── flow.yaml       # Конфигурация flow
│       └── states.yaml     # SPIN-состояния
│
└── templates/              # Шаблоны промптов
    ├── _base/prompts.yaml
    └── spin_selling/prompts.yaml
```

### constants.yaml — Константы

```yaml
# Лимиты
limits:
  max_consecutive_objections: 3
  max_total_objections: 5
  max_gobacks: 2

# Категории интентов
intents:
  question: [price_question, question_features, question_integrations]
  objection: [objection_price, objection_time, objection_competitor]
  positive: [agreement, interest, demo_request]

# SPIN конфигурация
spin:
  phases: [situation, problem, implication, need_payoff]
  states:
    situation: spin_situation
    problem: spin_problem
```

### flows/ — Модульные flow

Позволяют создавать кастомные диалоги без кода:

```yaml
# flows/my_flow/flow.yaml
flow:
  name: my_flow
  phases:
    order: [phase1, phase2]
    mapping:
      phase1: state_phase1
      phase2: state_phase2
  entry_points:
    default: greeting
```

```yaml
# flows/my_flow/states.yaml
states:
  state_phase1:
    extends: _base_phase
    mixins: [price_handling]
    goal: "Phase 1 goal"
```

### templates/ — Шаблоны промптов

```yaml
# templates/spin_selling/prompts.yaml
templates:
  spin_situation:
    template: |
      Ты — консультант Wipon.
      Цель: узнать ситуацию клиента.
      {{context}}
    variables:
      - context
```

```python
# Использование
flow = loader.load_flow("spin_selling")
template = flow.get_template("spin_situation")
prompt = template.format(context="...")
```

### priorities.yaml — Приоритеты обработки

```yaml
# _base/priorities.yaml
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

  - name: phase_progress
    priority: 4
    handler: phase_progress_handler
```

При наличии FlowConfig, StateMachine использует эти приоритеты вместо hardcoded логики.

### on_enter Actions

```yaml
# Состояние с действием при входе
states:
  ask_activity:
    on_enter:
      action: show_activity_options
    transitions:
      activity_selected: next_state
```

При переходе в состояние, action автоматически становится `show_activity_options`.

### Загрузка конфигурации

```python
from src.config_loader import ConfigLoader, get_config

# Глобальный конфиг
config = get_config()

# Или с перезагрузкой
config = get_config(reload=True)

# Загрузка flow
loader = ConfigLoader()
flow = loader.load_flow("spin_selling")

# FlowConfig содержит:
# - states: Dict — resolved состояния
# - priorities: List — приоритеты обработки
# - templates: Dict — шаблоны промптов
# - phase_order: List — порядок фаз
# - entry_points: Dict — точки входа
```

### Валидация конфигурации

```python
from src.config_loader import get_config_validated

# Загрузка с валидацией условий
config = get_config_validated()
```

Подробнее: [src/yaml_config/flows/README.md](../src/yaml_config/flows/README.md)
