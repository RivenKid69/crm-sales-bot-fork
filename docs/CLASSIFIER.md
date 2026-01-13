# Classifier — Пакет классификации интентов

## Обзор

Пакет `classifier/` отвечает за:
1. **Классификацию интентов** — определение намерения пользователя
2. **Извлечение данных** — структурированные данные из сообщения
3. **Контекстную классификацию** — учёт SPIN-фазы и истории диалога

**Основной классификатор**: LLMClassifier (Qwen3-8B через vLLM)
**Fallback**: HybridClassifier (regex + pymorphy)

## Структура пакета

```
classifier/
├── __init__.py              # Публичный API
├── unified.py               # UnifiedClassifier — адаптер для переключения
├── normalizer.py            # TextNormalizer, TYPO_FIXES, SPLIT_PATTERNS
├── hybrid.py                # HybridClassifier — regex-based fallback
├── disambiguation.py        # IntentDisambiguator
├── llm/                     # LLM классификатор (основной)
│   ├── __init__.py          # Экспорт LLMClassifier, schemas
│   ├── classifier.py        # LLMClassifier
│   ├── prompts.py           # System prompt + few-shot примеры
│   └── schemas.py           # Pydantic схемы для structured output
├── intents/                 # Regex-based классификация (для fallback)
│   ├── __init__.py
│   ├── patterns.py          # PRIORITY_PATTERNS (212 паттернов)
│   ├── root_classifier.py   # Быстрая классификация по корням
│   └── lemma_classifier.py  # Fallback через pymorphy
└── extractors/              # Извлечение данных
    ├── __init__.py
    └── data_extractor.py    # DataExtractor
```

## Публичный API

```python
from classifier import UnifiedClassifier, HybridClassifier, TextNormalizer, DataExtractor
from classifier import TYPO_FIXES, SPLIT_PATTERNS, PRIORITY_PATTERNS
from classifier.llm import LLMClassifier, ClassificationResult, ExtractedData
```

## UnifiedClassifier (рекомендуется)

Адаптер для переключения между LLM и Hybrid классификаторами:

```python
from classifier import UnifiedClassifier

classifier = UnifiedClassifier()

result = classifier.classify(
    message="нас 10 человек, теряем клиентов",
    context={"spin_phase": "situation"}
)
```

**Логика переключения:**
- `flags.llm_classifier == True` → LLMClassifier (по умолчанию)
- `flags.llm_classifier == False` → HybridClassifier

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
│           │ fallback при ошибке vLLM                     │
│           ▼                                              │
│   ┌────────────────┐                                     │
│   │ HybridClassifier│                                    │
│   └────────────────┘                                     │
└──────────────────────────────────────────────────────────┘
```

## LLMClassifier (основной)

Классификатор на базе LLM с structured output через vLLM + Outlines.

```python
from classifier.llm import LLMClassifier

classifier = LLMClassifier()

result = classifier.classify(
    message="нас 10 человек, теряем клиентов",
    context={"spin_phase": "situation"}
)

# result:
{
    "intent": "situation_provided",
    "confidence": 0.95,
    "extracted_data": {
        "company_size": 10,
        "pain_point": "теряем клиентов",
        "pain_category": "losing_clients"
    },
    "method": "llm",
    "reasoning": "Клиент указал размер команды и проблему с клиентами"
}
```

### Возможности

- **33 интента** с описаниями и примерами
- **Structured output** — 100% валидный JSON через Pydantic
- **Извлечение данных** — company_size, pain_point, contact_info и др.
- **Контекстная классификация** — учёт SPIN фазы и last_action
- **Fallback** на HybridClassifier при ошибке vLLM

### 33 интента

**Приветствия и общение:**
- `greeting` — приветствие
- `agreement` — согласие
- `gratitude` — благодарность
- `farewell` — прощание
- `small_talk` — разговор не по теме

**Ценовые вопросы:**
- `price_question` — вопрос о цене
- `pricing_details` — детали тарифов
- `objection_price` — возражение по цене

**Вопросы о продукте:**
- `question_features` — вопрос о функциях
- `question_integrations` — вопрос об интеграциях
- `comparison` — сравнение с конкурентами

**Запросы на контакт:**
- `callback_request` — запрос перезвона
- `contact_provided` — предоставление контакта
- `demo_request` — запрос демо
- `consultation_request` — запрос консультации

**SPIN данные:**
- `situation_provided` — информация о ситуации
- `problem_revealed` — описание проблемы
- `implication_acknowledged` — осознание последствий
- `need_expressed` — выражение потребности
- `no_problem` — отрицание проблемы
- `no_need` — отрицание потребности
- `info_provided` — предоставление информации

**Возражения:**
- `objection_no_time` — нет времени
- `objection_timing` — неподходящее время
- `objection_think` — нужно подумать
- `objection_complexity` — сложность
- `objection_competitor` — есть конкурент
- `objection_trust` — недоверие
- `objection_no_need` — не нужно
- `rejection` — жёсткий отказ

**Управление диалогом:**
- `unclear` — непонятное сообщение
- `go_back` — вернуться назад
- `correct_info` — исправление информации

### Pydantic схемы (schemas.py)

```python
class ExtractedData(BaseModel):
    """Извлечённые данные из сообщения."""
    company_size: Optional[int]
    business_type: Optional[str]
    current_tools: Optional[str]
    pain_point: Optional[str]
    pain_category: Optional[Literal["losing_clients", "no_control", "manual_work"]]
    pain_impact: Optional[str]
    financial_impact: Optional[str]
    contact_info: Optional[str]
    desired_outcome: Optional[str]
    value_acknowledged: Optional[bool]


class ClassificationResult(BaseModel):
    """Результат классификации интента."""
    intent: IntentType  # Literal из 33 интентов
    confidence: float  # 0.0 - 1.0
    reasoning: str  # Объяснение выбора
    extracted_data: ExtractedData
```

### System Prompt (prompts.py)

LLMClassifier использует детальный system prompt с:
- Описанием всех 33 интентов
- Критическими правилами (price_question vs objection_price)
- Примерами неоднозначных случаев
- Инструкциями по использованию контекста

## HybridClassifier (fallback)

Быстрый regex-based классификатор для fallback.

```python
from classifier import HybridClassifier

classifier = HybridClassifier()

result = classifier.classify(
    message="нас 10 человек, теряем клиентов",
    context={"spin_phase": "situation"}
)

# result:
{
    "intent": "situation_provided",
    "confidence": 0.85,
    "extracted_data": {
        "company_size": 10,
        "pain_point": "теряем клиентов"
    },
    "debug": {
        "normalized": "нас 10 человек теряем клиентов",
        "root_intent": "situation_provided",
        "lemma_intent": None
    }
}
```

### Компоненты HybridClassifier

#### 1. TextNormalizer

Нормализация текста перед классификацией:

```python
normalizer = TextNormalizer()

# Исправление опечаток (692 записи)
text = normalizer.normalize("скок стоит прайс?")
# → "сколько стоит цена?"

# Разбиение слитного текста (176 паттернов)
text = normalizer.normalize("сколькостоит")
# → "сколько стоит"
```

#### 2. RootClassifier

Быстрая классификация по корням слов:

```python
# config.py
INTENT_ROOTS = {
    "agreement": ["согласен", "да", "хорошо", "ок", "давай", "интерес"],
    "rejection": ["нет", "не надо", "отказ", "не хочу"],
    "price_question": ["цен", "стоим", "стоит", "тариф", "прайс"],
    # ...
}
```

#### 3. LemmaClassifier

Fallback через pymorphy для сложных форм слов.

#### 4. PRIORITY_PATTERNS (212 паттернов)

Regex-паттерны для приоритетных интентов:

```python
PRIORITY_PATTERNS = [
    # Rejection (приоритет над agreement)
    (r"не\s*интересно", "rejection", 0.95),
    (r"не\s*надо", "rejection", 0.95),

    # Price questions
    (r"скольк\w*\s*стоит", "price_question", 0.95),
    # ... 208+ паттернов
]
```

## DataExtractor

Извлечение структурированных данных:

```python
from classifier import DataExtractor

extractor = DataExtractor()

data = extractor.extract("у нас 10 человек, работаем в розничной торговле")
# → {"company_size": 10, "business_type": "розничная торговля"}
```

**Поддерживаемые поля:**

| Поле | Описание | Примеры |
|------|----------|---------|
| `company_size` | Размер команды | "нас 10", "команда из 5" |
| `current_tools` | Текущие инструменты | "Excel", "1С", "вручную" |
| `business_type` | Тип бизнеса | "розница", "общепит" |
| `pain_point` | Боль клиента | "теряем клиентов" |
| `pain_category` | Категория боли | `losing_clients`, `no_control`, `manual_work` |
| `pain_impact` | Количественные потери | "10 клиентов в месяц" |
| `financial_impact` | Финансовые потери | "~50 000 в месяц" |
| `desired_outcome` | Желаемый результат | "автоматизировать" |
| `contact_info` | Контакт клиента | телефон, email |

### pain_category

Автоматическая категоризация боли:

```python
PAIN_CATEGORY_KEYWORDS = {
    "losing_clients": ["теря", "клиент", "отток", "сделк", "продаж"],
    "no_control": ["контрол", "прозрачн", "хаос", "аналитик"],
    "manual_work": ["excel", "рутин", "вручную", "долго"]
}
```

## Контекстная классификация

Классификатор учитывает контекст диалога:

```python
# С контекстом SPIN фазы
classifier.classify("10 человек", context={"spin_phase": "situation"})
# → intent: "situation_provided"

# С контекстом предыдущего действия
classifier.classify("да", context={"last_action": "ask_for_demo"})
# → intent: "demo_request"
```

**Контекст для LLMClassifier:**
- `state` — текущее состояние FSM
- `spin_phase` — SPIN фаза (situation/problem/implication/need_payoff)
- `last_action` — последнее действие бота
- `last_intent` — предыдущий интент пользователя

## Статистика

```python
classifier = UnifiedClassifier()

# Получить статистику
stats = classifier.get_stats()
# {
#     "active_classifier": "llm",
#     "llm_stats": {
#         "llm_calls": 100,
#         "llm_successes": 98,
#         "fallback_calls": 2,
#         "llm_success_rate": 98.0,
#         "vllm_stats": {...}
#     }
# }
```

## Конфигурация

### Feature Flags

```python
# feature_flags.py
"llm_classifier": True               # Использовать LLM классификатор
"cascade_classifier": True           # Каскадный классификатор для HybridClassifier
"semantic_objection_detection": True # Семантическая детекция возражений
```

```bash
# Переключиться на HybridClassifier
export FF_LLM_CLASSIFIER=false

# Включить семантическую детекцию возражений
export FF_SEMANTIC_OBJECTION_DETECTION=true
```

### Настройки (settings.yaml)

```yaml
classifier:
  weights:
    root_match: 1.0       # Для HybridClassifier
    phrase_match: 2.0
    lemma_match: 1.5

  thresholds:
    high_confidence: 0.7  # Порог быстрого возврата
    min_confidence: 0.3   # Минимальная уверенность
```

## Расширение

### Добавление нового интента

**Для LLMClassifier:**

1. Добавить в `classifier/llm/schemas.py`:
```python
IntentType = Literal[
    # ...
    "new_intent",
]
```

2. Добавить в `classifier/llm/prompts.py`:
```python
SYSTEM_PROMPT = """
...
- new_intent: описание ("пример 1", "пример 2")
...
"""
```

**Для HybridClassifier (опционально):**

3. Добавить в `config.INTENT_ROOTS`:
```python
"new_intent": ["корень1", "корень2"],
```

4. Добавить паттерн в `classifier/intents/patterns.py`:
```python
(r"regex_pattern", "new_intent", 0.95),
```

### Добавление нового экстрактора

В `classifier/llm/schemas.py`:
```python
class ExtractedData(BaseModel):
    # ...
    new_field: Optional[str] = Field(None, description="Описание")
```

В system prompt добавить инструкции по извлечению.

## Тестирование

```bash
# Все тесты классификатора
pytest tests/test_classifier.py -v

# Тесты LLM классификатора (требует vLLM)
pytest tests/test_llm_classifier.py -v

# С покрытием
pytest tests/test_classifier.py --cov=classifier --cov-report=html
```

## Производительность

| Классификатор | Латентность | Точность |
|--------------|-------------|----------|
| LLMClassifier | ~100-200ms | ~95%+ |
| HybridClassifier | ~5-50ms | ~85% |

**Рекомендации:**
- LLMClassifier по умолчанию для максимальной точности
- HybridClassifier для высоконагруженных сценариев или при недоступности vLLM
