# Classifier — Пакет классификации интентов

## Обзор

Пакет `classifier/` отвечает за:
1. **Классификацию интентов** — определение намерения пользователя
2. **Извлечение данных** — структурированные данные из сообщения
3. **Контекстную классификацию** — учёт SPIN-фазы и истории диалога

**Основной классификатор**: LLMClassifier (Qwen3 14B через Ollama)
**Fallback**: HybridClassifier (regex + pymorphy)

## Config-Driven Architecture

Классификатор использует конфигурацию из `constants.yaml`:
- Категории интентов (`intents.categories`)
- Конфигурация SPIN фаз (`spin.phase_classification`)
- Классификация коротких ответов (`spin.short_answer_classification`)

## Структура пакета

```
classifier/
├── __init__.py              # Публичный API
├── unified.py               # UnifiedClassifier — адаптер для переключения
├── normalizer.py            # TextNormalizer, TYPO_FIXES, SPLIT_PATTERNS
├── hybrid.py                # HybridClassifier — regex-based fallback
├── cascade.py               # CascadeClassifier — semantic fallback
├── disambiguation.py        # IntentDisambiguator
├── refinement_pipeline.py   # RefinementPipeline — универсальный pipeline уточнения├── refinement_layers.py     # Адаптеры слоёв (Short, Composite, Objection)├── refinement.py            # ClassificationRefinementLayer (legacy)
├── composite_refinement.py  # CompositeMessageRefinementLayer (legacy)
├── objection_refinement.py  # ObjectionRefinementLayer (legacy)
├── llm/                     # LLM классификатор (основной)
│   ├── __init__.py          # Экспорт LLMClassifier, schemas
│   ├── classifier.py        # LLMClassifier
│   ├── prompts.py           # System prompt + few-shot примеры
│   └── schemas.py           # Pydantic схемы для structured output
├── intents/                 # Regex-based классификация (для fallback)
│   ├── __init__.py
│   ├── patterns.py          # PRIORITY_PATTERNS (426 паттернов)
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
│   │ (Ollama)      │         │ (regex+lemma)   │          │
│   └───────┬───────┘         └────────────────┘          │
│           │                                              │
│           │ fallback при ошибке Ollama                   │
│           ▼                                              │
│   ┌────────────────┐                                     │
│   │ HybridClassifier│                                    │
│   └────────────────┘                                     │
└──────────────────────────────────────────────────────────┘
```

## LLMClassifier (основной)

Классификатор на базе LLM с structured output через Ollama native format.

**Модель:** `qwen3:14b` (настраивается в `settings.yaml`)

**Конфигурация из YAML:**
- Категории интентов берутся из `constants.yaml` → `intents.categories`
- Конфигурация классификации по SPIN фазам из `constants.yaml` → `spin.phase_classification`
- Классификация коротких ответов из `constants.yaml` → `spin.short_answer_classification`

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

- **34 основных интента** + 150+ специализированных в 26 категориях (из `constants.yaml`)
- **Structured output** — 100% валидный JSON через Ollama native format
- **Извлечение данных** — company_size, pain_point, contact_info и др.
- **Контекстная классификация** — учёт SPIN фазы и last_action
- **Few-shot примеры** — интегрированы в классификационный промпт для улучшения точности (classifier/llm/few_shot.py)
- **Fallback** на HybridClassifier при ошибке Ollama

### 26 категорий интентов (150+)

Все интенты определены в `yaml_config/constants.yaml` → `intents.categories`:

| Категория | Кол-во | Описание |
|-----------|--------|----------|
| objection | 18 | Возражения (price, timing, competitor, etc.) |
| positive | 24 | Позитивные сигналы (agreement, demo_request, ready_to_buy) |
| question | 18 | Базовые вопросы |
| equipment_questions | 12 | Вопросы об оборудовании |
| tariff_questions | 8 | Вопросы о тарифах |
| tis_questions | 10 | Вопросы о ТИС |
| tax_questions | 8 | Налоговые вопросы |
| accounting_questions | 8 | Бухгалтерские вопросы |
| integration_specific | 8 | Вопросы об интеграциях |
| operations_questions | 10 | Операционные вопросы |
| delivery_service | 6 | Доставка |
| business_scenarios | 18 | Бизнес-сценарии |
| technical_problems | 6 | Технические проблемы |
| conversational | 10 | Разговорные (greeting, farewell, etc.) |
| fiscal_questions | 8 | Фискальные вопросы |
| analytics_questions | 8 | Аналитика |
| wipon_products | 6 | Продукты Wipon |
| employee_questions | 6+ | Вопросы о сотрудниках |
| meta | 5 | Мета-интенты (request_brevity, unclear, etc.) |

**Основные интенты для SPIN:**

**SPIN данные:**
- `situation_provided` — информация о ситуации
- `problem_revealed` — описание проблемы
- `implication_acknowledged` — осознание последствий
- `need_expressed` — выражение потребности
- `no_problem` — отрицание проблемы
- `no_need` — отрицание потребности
- `info_provided` — предоставление информации

**Мета-интенты (управление диалогом):**
- `request_brevity` — просьба говорить кратко ("не грузите, скажите суть")
- `unclear` — неясное сообщение
- `off_topic` — не по теме
- `meta_request` — мета-запрос о диалоге

**Возражения (18 типов):**
- `objection_price` — дорого
- `objection_no_time` — нет времени
- `objection_timing` — неподходящее время
- `objection_think` — нужно подумать
- `objection_complexity` — сложность
- `objection_competitor` — есть конкурент
- `objection_trust` — недоверие
- `objection_no_need` — не нужно
- `rejection` — жёсткий отказ
- И другие...

**Позитивные сигналы (24 типа):**
- `agreement` — согласие
- `demo_request` — запрос демо
- `callback_request` — запрос перезвона
- `contact_provided` — предоставление контакта
- `ready_to_buy` — готов к покупке
- `consultation_request` — запрос консультации
- И другие...

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
    intent: IntentType  # Literal из 150+ интентов
    confidence: float  # 0.0 - 1.0
    reasoning: str  # Объяснение выбора
    extracted_data: ExtractedData
```

### System Prompt (prompts.py)

LLMClassifier использует детальный system prompt с:
- Описанием категорий интентов (из constants.yaml)
- Критическими правилами (price_question vs objection_price)
- **Few-shot примерами** для сложных случаев (few_shot.py):
  - `request_brevity` — распознавание просьб говорить кратко
  - `objection_competitor` — правильное извлечение {retrieved_facts} о конкурентах
  - `price_question` vs `objection_price` — различение вопроса и возражения
- Инструкциями по использованию контекста

**Few-shot интеграция** (коммит 6bc6285):
```python
# classifier/llm/few_shot.py
FEW_SHOT_EXAMPLES = {
    "request_brevity": [
        ("не грузите меня, скажите суть", "request_brevity"),
        ("коротко, пожалуйста", "request_brevity"),
    ],
    "objection_competitor": [
        ("у нас Poster", "objection_competitor", {"competitor": "Poster"}),
        ("мы уже с Штрих-М работаем", "objection_competitor", {"competitor": "Штрих-М"}),
    ]
}
```

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

# Исправление опечаток (663 записи)
text = normalizer.normalize("скок стоит прайс?")
# → "сколько стоит цена?"

# Разбиение слитного текста (170 паттернов)
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

#### 4. PRIORITY_PATTERNS (426 паттернов)

Regex-паттерны для приоритетных интентов:

```python
PRIORITY_PATTERNS = [
    # Rejection (приоритет над agreement)
    (r"не\s*интересно", "rejection", 0.95),
    (r"не\s*надо", "rejection", 0.95),

    # Price questions
    (r"скольк\w*\s*стоит", "price_question", 0.95),
    # ... 420+ паттернов
]
```

## RefinementPipeline NEW

Универсальная архитектура для уточнения результатов классификации. Решает проблемы контекстной классификации через расширяемый pipeline слоёв.

### Архитектура

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                        Classification Flow                                     │
│                                                                                │
│   User Message                                                                 │
│        │                                                                       │
│        ▼                                                                       │
│   ┌────────────────────┐                                                       │
│   │  LLM/Hybrid        │  ← Primary Classification                             │
│   │  Classifier        │                                                       │
│   └─────────┬──────────┘                                                       │
│             │                                                                  │
│             ▼                                                                  │
│   ┌────────────────────────────────────────────────────────────────────┐      │
│   │                    RefinementPipeline                               │      │
│   │                                                                     │      │
│   │   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐          │      │
│   │   │ Confidence   │ → │ ShortAnswer  │ → │ Composite    │ →        │      │
│   │   │ Calibration  │   │ Layer        │   │ Message      │          │      │
│   │   │ (CRITICAL)   │   │ (HIGH)       │   │ (HIGH)       │          │      │
│   │   └──────────────┘   └──────────────┘   └──────────────┘          │      │
│   │                                                    │               │      │
│   │                                              ┌─────▼──────┐        │      │
│   │                                              │ Objection  │        │      │
│   │                                              │ Layer      │        │      │
│   │                                              │ (NORMAL)   │        │      │
│   │                                              └────────────┘        │      │
│   │   Features:                                                         │      │
│   │   • Protocol Pattern (IRefinementLayer)                            │      │
│   │   • Registry Pattern (dynamic registration)                        │      │
│   │   • Priority-based execution order                                 │      │
│   │   • Fail-safe (layer errors don't break pipeline)                  │      │
│   │   • YAML configuration                                             │      │
│   │   • Scientific confidence calibration (entropy, gap, heuristics)   │      │
│   └─────────┬──────────────────────────────────────────────────────────┘      │
│             │                                                                  │
│             ▼                                                                  │
│   ┌────────────────────┐                                                       │
│   │  Disambiguation    │  ← Optional: needs_disambiguation check               │
│   │  Engine            │                                                       │
│   └─────────┬──────────┘                                                       │
│             │                                                                  │
│             ▼                                                                  │
│      Final Result                                                              │
│                                                                                │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Ключевые компоненты

#### 1. IRefinementLayer Protocol

```python
@runtime_checkable
class IRefinementLayer(Protocol):
    """Контракт для всех слоёв уточнения."""

    @property
    def name(self) -> str:
        """Уникальное имя слоя."""
        ...

    @property
    def priority(self) -> LayerPriority:
        """Приоритет выполнения (CRITICAL > HIGH > NORMAL > LOW)."""
        ...

    def should_apply(self, ctx: RefinementContext) -> bool:
        """Проверить, нужно ли применять слой."""
        ...

    def refine(
        self,
        message: str,
        result: Dict[str, Any],
        ctx: RefinementContext
    ) -> RefinementResult:
        """Уточнить результат классификации."""
        ...
```

#### 2. RefinementLayerRegistry

```python
# Регистрация слоя
registry = RefinementLayerRegistry.get_registry()
registry.register("my_layer", MyLayerClass)

# Или через декоратор
@register_refinement_layer("my_layer")
class MyLayerClass(BaseRefinementLayer):
    LAYER_NAME = "my_layer"

    def _should_apply(self, ctx: RefinementContext) -> bool:
        return ctx.intent == "some_intent"

    def _do_refine(
        self,
        message: str,
        result: Dict[str, Any],
        ctx: RefinementContext
    ) -> RefinementResult:
        # Уточнение логика
        return self._refine_to(result, ctx, "new_intent", confidence=0.9)
```

#### 3. RefinementPipeline

```python
pipeline = get_refinement_pipeline()

# Запуск уточнения
refined_result = pipeline.refine(message, classification_result, context)

# Статистика
stats = pipeline.get_stats()
# {
#     "total_calls": 100,
#     "refinements_applied": 15,
#     "layers_stats": {"short_answer": {...}, "composite_message": {...}},
#     ...
# }
```

### Встроенные слои

#### ConfidenceCalibrationLayer NEW

Научная калибровка LLM confidence для решения проблемы overconfident LLM. LLM часто возвращает высокий confidence (0.85-0.95) даже при неверной классификации.

**Проблема:** LLM генерирует confidence как текст, а не вычисляет алгоритмически. Это приводит к overconfidence — высокой уверенности даже при ошибочной классификации.

**Решение:** Три научно-обоснованные стратегии калибровки:

1. **Entropy Strategy** — использует Shannon entropy для оценки неопределённости:
   - Высокая entropy (распределение вероятностей по многим альтернативам) → понижаем confidence
   - Формула: `H = -Σ(p_i × log(p_i))`

2. **Gap Strategy** — анализирует разрыв между top-1 и top-2 интентами:
   - Маленький gap → неоднозначная классификация → понижаем confidence
   - Особый штраф за high confidence + small gap (подозрительно)

3. **Heuristic Strategy** — pattern-based правила для известных ошибок LLM:
   - Короткие сообщения с высоким confidence → подозрительно
   - Overconfident intents (greeting, farewell, small_talk) → штраф

```python
# Пример: LLM вернул confidence 0.9 для "да"
# Результат после калибровки:
# - Entropy penalty: 0.05 (alternatives были)
# - Gap penalty: 0.1 (gap между top-1 и top-2 < 0.2)
# - Heuristic penalty: 0.15 (short message + high confidence)
# Итого: 0.9 - 0.05 - 0.1 - 0.15 = 0.6
```

**Приоритет:** CRITICAL (100) — выполняется первым, до всех остальных слоёв.

**SSoT:** `src/classifier/confidence_calibration.py`

#### ShortAnswerRefinementLayer

Уточняет классификацию коротких ответов ("да", "1", "ок") на основе контекста SPIN-фазы.

**Проблема:** Короткие ответы "да", "1" классифицируются как `greeting` вместо `agreement` или `info_provided`.

**Решение:** Анализ текущей фазы SPIN и предыдущего действия бота.

```python
# Пример: фаза "situation", last_action="ask_about_company"
# Сообщение: "5"
# Результат: greeting → info_provided (с company_size=5)
```

#### CompositeMessageLayer

Обрабатывает составные сообщения с приоритетом извлечения данных.

**Проблема:** "5 человек, больше не нужно, быстрее" классифицируется как `objection_think` вместо `info_provided` с company_size=5.

**Решение:** Если сообщение содержит и данные, и мета-сигналы — приоритет данным.

```python
# Пример: "5 человек, быстрее давайте"
# LLM: objection_timing (0.7)
# После refinement: info_provided (0.85) с company_size=5, secondary_signals=["urgency"]
```

#### ObjectionRefinementLayerAdapter

Валидирует objection-классификации с учётом контекста диалога.

**Проблема:** "бюджет пока не определён" классифицируется как `objection_price`, хотя бот только что спросил о бюджете (это ответ, не возражение).

**Решение:** Анализ last_bot_message и last_action для проверки релевантности возражения.

```python
# Пример: last_action="ask_about_budget"
# Сообщение: "бюджет пока не определён"
# LLM: objection_price
# После refinement: info_provided (ответ на вопрос о бюджете)
```

### Конфигурация

**constants.yaml:**
```yaml
refinement_pipeline:
  enabled: true
  layers:
    - name: confidence_calibration
      enabled: true
      priority: CRITICAL  # 100 - runs first
      feature_flag: confidence_calibration
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

# Конфигурация калибровки confidence
confidence_calibration:
  enabled: true
  min_confidence_floor: 0.1
  max_confidence_ceiling: 0.95

  # Entropy strategy
  entropy_enabled: true
  entropy_threshold: 0.5
  entropy_penalty_factor: 0.15

  # Gap strategy
  gap_enabled: true
  gap_threshold: 0.2
  gap_penalty_factor: 0.2

  # Heuristic strategy
  heuristic_enabled: true
  short_message_words: 3
  short_message_penalty: 0.15
```

**Feature Flags:**
```python
# Включить весь pipeline
flags.is_enabled("refinement_pipeline")  # True по умолчанию

# Отдельные слои
flags.confidence_calibration     # confidence_calibration layer (CRITICAL)flags.classification_refinement  # short_answer layer
flags.composite_refinement       # composite_message layer
flags.objection_refinement       # objection layer
```

### Создание нового слоя

1. Создать класс, наследующий `BaseRefinementLayer`:

```python
# В refinement_layers.py или отдельном файле
from src.classifier.refinement_pipeline import (
    BaseRefinementLayer,
    RefinementContext,
    RefinementResult,
    LayerPriority,
    register_refinement_layer,
)

@register_refinement_layer("my_custom_layer")
class MyCustomLayer(BaseRefinementLayer):
    LAYER_NAME = "my_custom_layer"
    DEFAULT_PRIORITY = LayerPriority.NORMAL

    def _should_apply(self, ctx: RefinementContext) -> bool:
        """Условие применения слоя."""
        return ctx.intent in ["some_intent", "another_intent"]

    def _do_refine(
        self,
        message: str,
        result: Dict[str, Any],
        ctx: RefinementContext
    ) -> RefinementResult:
        """Логика уточнения."""
        # Анализ и уточнение
        if self._needs_refinement(message, ctx):
            return self._refine_to(
                result, ctx,
                new_intent="refined_intent",
                confidence=0.9,
                metadata={"refined_by": "my_custom_layer"}
            )
        return self._pass_through(result, ctx)
```

2. Добавить конфигурацию в `constants.yaml`:

```yaml
refinement_pipeline:
  layers:
    # ... existing layers ...
    - name: my_custom_layer
      enabled: true
      priority: NORMAL
      feature_flag: my_custom_refinement  # optional
```

3. Добавить feature flag (опционально):

```python
# В feature_flags.py
"my_custom_refinement": True,
```

### SSoT (Single Source of Truth)

| Компонент | Файл |
|-----------|------|
| Pipeline Core | `src/classifier/refinement_pipeline.py` |
| Layer Adapters | `src/classifier/refinement_layers.py` |
| Confidence Calibration | `src/classifier/confidence_calibration.py` |
| Configuration | `src/yaml_config/constants.yaml` (секции `refinement_pipeline`, `confidence_calibration`) |
| Feature Flags | `src/feature_flags.py` |
| Tests | `tests/test_refinement_pipeline.py`, `tests/test_confidence_calibration.py` |

### Legacy Mode

При `flags.refinement_pipeline == False` используется legacy mode с отдельными слоями:

```python
# Legacy pipeline (deprecated):
# 1. ClassificationRefinementLayer (refinement.py)
# 2. CompositeMessageRefinementLayer (composite_refinement.py)
# 3. ObjectionRefinementLayer (objection_refinement.py)

# New pipeline (recommended):
# RefinementPipeline с Registry pattern
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
#         "ollama_stats": {...}
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

# RefinementPipeline flags
"refinement_pipeline": True          # Универсальный RefinementPipeline (рекомендуется)
"confidence_calibration": True       # Научная калибровка LLM confidence NEW
"classification_refinement": True    # Уточнение коротких ответов (ShortAnswerRefinementLayer)
"composite_refinement": True         # Приоритет данных в составных сообщениях (CompositeMessageLayer)
"objection_refinement": True         # Контекстная валидация objection (ObjectionRefinementLayerAdapter)
```

```bash
# Переключиться на HybridClassifier
export FF_LLM_CLASSIFIER=false

# Включить семантическую детекцию возражений
export FF_SEMANTIC_OBJECTION_DETECTION=true

# Отключить RefinementPipeline (использовать legacy mode)
export FF_REFINEMENT_PIPELINE=false
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

**1. Добавить в `yaml_config/constants.yaml`** (единый источник истины):
```yaml
intents:
  categories:
    your_category:
      - new_intent
      - another_intent
```

**2. (Опционально) Добавить в `classifier/llm/prompts.py`:**
```python
SYSTEM_PROMPT = """
...
- new_intent: описание ("пример 1", "пример 2")
...
"""
```

**Для HybridClassifier (fallback):**

**3. Добавить в `config.INTENT_ROOTS`:**
```python
"new_intent": ["корень1", "корень2"],
```

**4. Добавить паттерн в `classifier/intents/patterns.py`:**
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

# Тесты LLM классификатора (требует Ollama)
pytest tests/test_llm_classifier.py -v

# Тесты RefinementPipeline (33 теста)
pytest tests/test_refinement_pipeline.py -v

# Тесты composite refinement
pytest tests/test_composite_refinement.py -v

# С покрытием
pytest tests/test_classifier.py tests/test_refinement_pipeline.py --cov=classifier --cov-report=html
```

## Производительность

| Классификатор | Латентность | Точность |
|--------------|-------------|----------|
| LLMClassifier | ~100-200ms | ~95%+ |
| HybridClassifier | ~5-50ms | ~85% |

**Рекомендации:**
- LLMClassifier по умолчанию для максимальной точности
- HybridClassifier для высоконагруженных сценариев или при недоступности Ollama
