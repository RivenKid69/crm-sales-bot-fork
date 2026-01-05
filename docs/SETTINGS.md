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
    # ...
}
```

## Профили настроек

### Быстрый старт (без эмбеддингов)

```yaml
retriever:
  use_embeddings: false

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

generator:
  retriever_top_k: 3
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

# Проверка валидации
python scripts/validate_settings.py
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
