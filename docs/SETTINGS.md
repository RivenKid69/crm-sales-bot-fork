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
# LLM (Language Model)
# -----------------------------------------------------------------------------
llm:
  model: "qwen3:8b-fast"
  base_url: "http://localhost:11434"
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
# FEATURE FLAGS (Управление фичами)
# -----------------------------------------------------------------------------
feature_flags:
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

### LLM (Language Model)

| Параметр | Тип | По умолчанию | Описание |
|----------|-----|--------------|----------|
| `model` | string | `"qwen3:8b-fast"` | Название модели Ollama |
| `base_url` | string | `"http://localhost:11434"` | URL сервера Ollama |
| `timeout` | int | `60` | Таймаут запроса в секундах |
| `stream` | bool | `false` | Режим стриминга |
| `think` | bool | `false` | Thinking mode (для скорости выключен) |

**Примеры моделей:**
- `qwen3:8b-fast` — быстрая версия Qwen3 8B (рекомендуется)
- `qwen3:8b` — стандартная версия
- `llama3.1:8b` — альтернатива

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

**Модели эмбеддингов:**
- `ai-forever/ru-en-RoSBERTa` — русско-английская модель (рекомендуется)
- `cointegrated/rubert-tiny2` — компактная русская модель (быстрее)

### RERANKER (Переоценка результатов)

| Параметр | Тип | По умолчанию | Описание |
|----------|-----|--------------|----------|
| `enabled` | bool | `true` | Включить reranker fallback |
| `model` | string | `"BAAI/bge-reranker-v2-m3"` | Модель cross-encoder |
| `threshold` | float | `0.5` | Порог score ниже которого включается |
| `candidates_count` | int | `10` | Сколько кандидатов переоценивать |

**Модели reranker:**
- `BAAI/bge-reranker-v2-m3` — мультиязычный, высокое качество (рекомендуется)
- `cross-encoder/ms-marco-MiniLM-L-6-v2` — быстрый, английский

### CATEGORY ROUTER (LLM-классификация)

| Параметр | Тип | По умолчанию | Описание |
|----------|-----|--------------|----------|
| `enabled` | bool | `true` | Включить LLM-классификацию |
| `top_k` | int | `3` | Количество возвращаемых категорий |
| `fallback_categories` | list | `["faq"]` | Категории по умолчанию при ошибке |

### GENERATOR (Генерация ответов)

| Параметр | Тип | По умолчанию | Описание |
|----------|-----|--------------|----------|
| `max_retries` | int | `3` | Количество retry при иностранном тексте |
| `history_length` | int | `4` | Количество сообщений в контексте |
| `retriever_top_k` | int | `2` | Количество фактов из базы знаний |
| `allowed_english_words` | list | см. выше | Разрешённые английские слова |

**allowed_english_words:**

Список английских слов, которые НЕ считаются "иностранным текстом" и не вызывают retry. Добавьте сюда технические термины, используемые в вашем продукте.

### CLASSIFIER (Классификация интентов)

| Параметр | Тип | По умолчанию | Описание |
|----------|-----|--------------|----------|
| `weights.root_match` | float | `1.0` | Вес совпадения по корню |
| `weights.phrase_match` | float | `2.0` | Вес точного совпадения фразы |
| `weights.lemma_match` | float | `1.5` | Вес совпадения по лемме |
| `thresholds.high_confidence` | float | `0.7` | Порог высокой уверенности |
| `thresholds.min_confidence` | float | `0.3` | Минимальная уверенность |

**Влияние порогов:**
- `high_confidence: 0.7` — при этом score возврат без fallback на pymorphy
- `min_confidence: 0.3` — ниже этого возвращается `unclear`

### LOGGING (Логирование)

| Параметр | Тип | По умолчанию | Описание |
|----------|-----|--------------|----------|
| `level` | string | `"INFO"` | Уровень логирования |
| `log_llm_requests` | bool | `false` | Логировать запросы к LLM |
| `log_retriever_results` | bool | `false` | Логировать результаты retriever |

**Уровни:** `DEBUG`, `INFO`, `WARNING`, `ERROR`

### FEATURE FLAGS (Управление фичами)

Feature flags позволяют постепенно включать новые возможности без изменения кода.

| Флаг | Фаза | По умолчанию | Описание |
|------|------|--------------|----------|
| `structured_logging` | 0 | `true` | JSON логи для production |
| `metrics_tracking` | 0 | `true` | Трекинг метрик диалогов |
| `multi_tier_fallback` | 1 | `true` | 4-уровневый fallback |
| `conversation_guard` | 1 | `true` | Защита от зацикливания |
| `tone_analysis` | 2 | `false` | Анализ тона клиента |
| `response_variations` | 2 | `true` | Вариативность ответов |
| `personalization` | 2 | `false` | Персонализация |
| `lead_scoring` | 3 | `false` | Скоринг лидов |
| `circular_flow` | 3 | `false` | Возврат назад по фазам |
| `objection_handler` | 3 | `false` | Обработка возражений |
| `cta_generator` | 3 | `false` | Call-to-Action |

**Переопределение через env:**
```bash
# Включить tone_analysis
FF_TONE_ANALYSIS=true python bot.py

# Выключить metrics_tracking
FF_METRICS_TRACKING=false python bot.py
```

Подробнее: [PHASES.md](./PHASES.md)

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
# → 0.5

value = settings.get_nested("nonexistent.path", default="fallback")
# → "fallback"
```

### Перезагрузка настроек

```python
from settings import reload_settings

# После изменения settings.yaml
reload_settings()
```

### Валидация настроек

```python
from settings import validate_settings, get_settings

errors = validate_settings(get_settings())
if errors:
    for err in errors:
        print(f"Ошибка: {err}")
```

### Использование Feature Flags

```python
from feature_flags import is_enabled, get_all_flags

# Проверка флага
if is_enabled("tone_analysis"):
    analyzer = ToneAnalyzer()
    tone = analyzer.analyze(message)

# Получить все флаги
flags = get_all_flags()
print(flags)  # {"structured_logging": True, "tone_analysis": False, ...}
```

## Значения по умолчанию

Если параметр не указан в `settings.yaml`, используются значения по умолчанию из `settings.py`:

```python
DEFAULTS = {
    "llm": {
        "model": "qwen3:8b-fast",
        "base_url": "http://localhost:11434",
        "timeout": 60,
        "stream": False,
        "think": False,
    },
    "retriever": {
        "use_embeddings": True,
        "embedder_model": "ai-forever/ru-en-RoSBERTa",
        "thresholds": {
            "exact": 1.0,
            "lemma": 0.15,
            "semantic": 0.5,
        },
        "default_top_k": 2,
    },
    "reranker": {
        "enabled": True,
        "model": "BAAI/bge-reranker-v2-m3",
        "threshold": 0.5,
        "candidates_count": 10,
    },
    "category_router": {
        "enabled": True,
        "top_k": 3,
        "fallback_categories": ["faq"],
    },
    # ...
}
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
    exact: 1.0
    lemma: 0.10      # Понизить порог
    semantic: 0.4    # Понизить порог
  default_top_k: 3   # Больше результатов

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
  structured_logging: true
  metrics_tracking: true
  multi_tier_fallback: true
  conversation_guard: true
  response_variations: true
  # Остальные выключены

development:
  debug: false
```

### Режим отладки

```yaml
logging:
  level: "DEBUG"
  log_llm_requests: true
  log_retriever_results: true

development:
  debug: true
```

## CLI для проверки

```bash
# Вывести текущие настройки
cd src && python settings.py

# Вывод:
# ============================================================
# ТЕКУЩИЕ НАСТРОЙКИ
# ============================================================
#
# [+] Все настройки валидны
#
# ------------------------------------------------------------
# {
#   "llm": {
#     "model": "qwen3:8b-fast",
#     ...
#   },
#   ...
# }
```

## Тестирование

```bash
# Тесты настроек
pytest tests/test_settings.py -v

# Тесты feature flags
pytest tests/test_feature_flags.py -v
```

## Миграция настроек

При обновлении версии бота новые параметры автоматически получают значения по умолчанию. Существующие настройки сохраняются.

**Пример:** добавлен новый параметр `retriever.cache_ttl`

1. Обновите код
2. Старый `settings.yaml` продолжит работать
3. Новый параметр будет использовать default

Для явного указания:
```yaml
retriever:
  cache_ttl: 3600  # новый параметр
```
