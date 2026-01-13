# Settings — Конфигурация CRM Sales Bot

## Обзор

Все настраиваемые параметры бота вынесены в файл `src/settings.yaml`. Это позволяет изменять поведение системы без правки кода.

## Файл настроек

**Расположение:** `src/settings.yaml`

```yaml
# =============================================================================
# НАСТРОЙКИ CRM SALES BOT
# =============================================================================

# -----------------------------------------------------------------------------
# LLM (Language Model) - vLLM Server
# -----------------------------------------------------------------------------
llm:
  model: "Qwen/Qwen3-8B-AWQ"
  base_url: "http://localhost:8000/v1"
  timeout: 60
  stream: false
  think: false

# -----------------------------------------------------------------------------
# RETRIEVER (Поиск по базе знаний)
# -----------------------------------------------------------------------------
retriever:
  use_embeddings: true
  embedder_model: "ai-forever/ru-en-RoSBERTa"
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
# DEVELOPMENT (Режим разработки)
# -----------------------------------------------------------------------------
development:
  debug: false
  skip_embeddings: false
```

## Параметры

### LLM (vLLM Server)

| Параметр | Тип | По умолчанию | Описание |
|----------|-----|--------------|----------|
| `model` | string | `"Qwen/Qwen3-8B-AWQ"` | Модель vLLM (с AWQ квантизацией) |
| `base_url` | string | `"http://localhost:8000/v1"` | URL vLLM сервера (OpenAI-compatible) |
| `timeout` | int | `60` | Таймаут запроса в секундах |
| `stream` | bool | `false` | Режим стриминга |
| `think` | bool | `false` | Thinking mode (/no_think для скорости) |

**Запуск vLLM сервера:**
```bash
vllm serve Qwen/Qwen3-8B-AWQ \
    --host 0.0.0.0 \
    --port 8000 \
    --guided-decoding-backend outlines \
    --max-model-len 4096 \
    --gpu-memory-utilization 0.9
```

**Требования:** ~5-6 GB VRAM, CUDA GPU

### RETRIEVER (Поиск по базе знаний)

| Параметр | Тип | По умолчанию | Описание |
|----------|-----|--------------|----------|
| `use_embeddings` | bool | `true` | Использовать семантический поиск |
| `embedder_model` | string | `"ai-forever/ru-en-RoSBERTa"` | Модель для эмбеддингов |
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
| `llm_classifier` | `true` | **LLM классификатор вместо Hybrid** |
| `structured_logging` | `true` | JSON логи для production |
| `metrics_tracking` | `true` | Трекинг метрик диалогов |
| `multi_tier_fallback` | `true` | 4-уровневый fallback |
| `conversation_guard` | `true` | Защита от зацикливания |
| `tone_analysis` | `false` | Анализ тона клиента |
| `response_variations` | `true` | Вариативность ответов |
| `personalization` | `false` | Персонализация |
| `lead_scoring` | `false` | Скоринг лидов |
| `circular_flow` | `false` | Возврат назад по фазам |
| `objection_handler` | `false` | Обработка возражений |
| `cta_generator` | `false` | Call-to-Action |
| `cascade_classifier` | `true` | Каскадный классификатор |
| `semantic_objection_detection` | `true` | Семантическая детекция возражений |
| `cascade_tone_analyzer` | `true` | Каскадный анализатор тона |
| `context_full_envelope` | `true` | Полный ContextEnvelope |
| `context_policy_overlays` | `true` | DialoguePolicy overrides |

**Переопределение через env:**
```bash
# Переключиться на HybridClassifier
FF_LLM_CLASSIFIER=false python bot.py

# Включить tone_analysis
FF_TONE_ANALYSIS=true python bot.py
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

```bash
# Тесты настроек
pytest tests/test_settings.py -v

# Тесты feature flags
pytest tests/test_feature_flags.py -v
```
