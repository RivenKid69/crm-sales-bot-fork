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

## Контекст и восстановление сессии

Классификатор использует **ContextWindow** как основной источник истории и паттернов:
- intent_history / action_history
- stuck / oscillation / repeated_question
- счётчики objections / questions / positives

При восстановлении из snapshot:
- `ContextWindow` восстанавливается из `_context_window_full`
- последние 4 сообщения подгружаются из внешней истории, но **не влияют напрямую на классификацию**
- для защиты от утечек между клиентами snapshot проверяется по `client_id`

Таким образом, классификация остаётся стабильной даже после “неделя спустя”.

## Структура пакета

```
classifier/
├── __init__.py              # Публичный API
├── unified.py               # UnifiedClassifier — адаптер для переключения
├── normalizer.py            # TextNormalizer, TYPO_FIXES, SPLIT_PATTERNS
├── hybrid.py                # HybridClassifier — regex-based fallback
├── cascade.py               # CascadeClassifier — semantic fallback
├── disambiguation.py        # IntentDisambiguator
├── refinement_pipeline.py   # RefinementPipeline — универсальный pipeline уточнения
├── refinement_layers.py     # Адаптеры слоёв (short_answer, composite_message, first_contact, greeting_context, objection, option_selection)
├── refinement.py            # ClassificationRefinementLayer (short answer refinement)
├── composite_refinement.py  # CompositeMessageRefinementLayer (legacy)
├── objection_refinement.py  # ObjectionRefinementLayer (legacy)
├── llm/                     # LLM классификатор (основной)
│   ├── __init__.py          # Экспорт LLMClassifier, schemas
│   ├── classifier.py        # LLMClassifier
│   ├── prompts.py           # System prompt + few-shot примеры
│   └── schemas.py           # Pydantic схемы для structured output
├── intents/                 # Regex-based классификация (для fallback)
│   ├── __init__.py
│   ├── patterns.py          # PRIORITY_PATTERNS (491 паттерн)
│   ├── root_classifier.py   # Быстрая классификация по корням
│   └── lemma_classifier.py  # Fallback через pymorphy
└── extractors/              # Извлечение данных
    ├── __init__.py
    └── data_extractor.py    # DataExtractor
```

## Публичный API

```python
from src.classifier import UnifiedClassifier, HybridClassifier, TextNormalizer, DataExtractor
from src.classifier import TYPO_FIXES, SPLIT_PATTERNS, PRIORITY_PATTERNS
from src.classifier.llm import LLMClassifier, ClassificationResult, ExtractedData
```

## UnifiedClassifier (рекомендуется)

Адаптер для переключения между LLM и Hybrid классификаторами:

```python
from src.classifier import UnifiedClassifier

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
from src.classifier.llm import LLMClassifier

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

- **300 записей интентов** в 34 категориях (271 unique) из `constants.yaml`
- **Structured output** — 100% валидный JSON через Ollama native format
- **Извлечение данных** — company_size, pain_point, contact_info и др.
- **Контекстная классификация** — учёт SPIN фазы и last_action
- **Few-shot примеры** — интегрированы в классификационный промпт для улучшения точности (classifier/llm/few_shot.py)
- **Fallback** на HybridClassifier при ошибке Ollama

### 34 категории интентов (300)

Все интенты определены в `yaml_config/constants.yaml` → `intents.categories`:

**Composed Categories** — автоматическая синхронизация категорий без ручного дублирования:

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
    includes: [price_related, company_info]  # edge cases без question_* префикса
```

**Результат:** категории синхронизируются автоматически, а `rejection` учитывается в `exit`, не раздувая лимиты возражений.

| Категория | Кол-во | Описание |
|-----------|--------|----------|
| objection | 18 | Возражения (price, timing, competitor, etc.) |
| positive | 23 | Позитивные сигналы (agreement, demo_request, ready_to_buy) |
| question | 18 | Базовые вопросы |
| equipment_questions | 12 | Вопросы об оборудовании (POS, принтеры, сканеры) |
| tariff_questions | 8 | Вопросы о тарифах (Mini, Lite, Standard, Pro) |
| tis_questions | 10 | Вопросы о ТИС (товарно-информационная система) |
| tax_questions | 8 | Налоговые вопросы (retail tax, SNR, VAT) |
| accounting_questions | 8 | Бухгалтерские вопросы (ESF/SNT, формы 910/200/300) |
| integration_specific | 8 | Вопросы об интеграциях (Kaspi, Halyk, 1C, iiko) |
| operations_questions | 10 | Операционные вопросы (учёт, ревизии, возвраты) |
| delivery_service | 6 | Доставка и сервис |
| business_scenarios | 18 | Бизнес-сценарии (продуктовый, ресторан, аптека) |
| technical_problems | 6 | Технические проблемы |
| conversational | 10 | Разговорные (greeting, farewell, compliment) |
| fiscal_questions | 8 | Фискализация (Z/X отчёты, KKM, OFD Wipon) |
| analytics_questions | 8 | Аналитика (ABC, прибыль, дашборды) |
| wipon_products | 6 | Продукты Wipon (Pro, Desktop, Kassa) |
| employee_questions | 6 | Вопросы о сотрудниках (зарплата, график, KPI) |
| price_related | 7 | Вопросы о цене |
| purchase_stages | 8 | Этапы покупки (proposal, contract, invoice) |
| company_info | 4 | Информация о компании |
| dialogue_control | 8 | Управление диалогом (go_back, skip, repeat) |
| technical_question | 13 | Технические вопросы |
| promo_loyalty | 6 | Промо и лояльность (бонусы, скидки) |
| region_questions | 6 | Регионы и присутствие |
| stability_questions | 6 | Стабильность и надёжность (backup, SLA) |
| informative | 16 | Информативные интенты |
| spin_progress | 4 | Прогресс SPIN |
| exit | 2 | Завершение диалога |
| escalation | 8 | Эскалация к человеку |
| frustration | 6 | Фрустрация/недовольство |
| sensitive | 7 | Чувствительные темы |
| additional_integrations | 6 | Доп. интеграции (Glovo, Telegram, WhatsApp) |
| greeting_additional_redirects | 2 | Доп. интенты для безопасности greeting |

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
    intent: IntentType  # Literal из 300 интентов
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

## CascadeIntentClassifier (Advanced Fallback)

Каскадный классификатор интентов с 5-этапным пайплайном для HybridClassifier.

**Архитектура:** 5-этапный пайплайн классификации, каждый этап возвращает результат только при высокой уверенности, иначе передаёт управление следующему этапу.

**Этапы классификации:**

1. **Priority Patterns (regex)** — confidence >= 0.85
   - Использует COMPILED_PRIORITY_PATTERNS (491 паттерн)
   - Высокоприоритетные интенты (rejection, agreement, price_question)
   - Latency: ~0.5-2ms
   - Если совпадение найдено с high confidence → немедленный возврат

2. **Root Classifier (stems)** — confidence >= high_threshold (0.85)
   - Классификация по корням слов из INTENT_ROOTS
   - Быстрый словарный поиск без морфологии
   - Latency: ~2-5ms
   - Если уверенность >= 0.85 → возврат

3. **Lemma Classifier (pymorphy)** — confidence >= medium_threshold (0.65)
   - Лемматизация через pymorphy2
   - Обработка сложных форм слов
   - Latency: ~10-30ms
   - Сравнение с Root результатом, выбор лучшего
   - Если уверенность >= 0.65 → возврат

4. **Semantic Classifier (embeddings)** — confidence >= semantic_threshold (0.55)
   - Semantic search через embeddings
   - Cosine similarity с reference examples
   - Latency: ~50-150ms (зависит от model)
   - Fallback для сложных/новых формулировок
   - Если уверенность >= 0.55 и лучше keyword результата → возврат

5. **Fallback** — возврат лучшего из доступных или "unclear"
   - Собирает все результаты из этапов 1-4
   - Выбирает best по confidence
   - Если best confidence < min_confidence (0.3) → "unclear"

**Пример выполнения:**

```python
classifier = get_cascade_classifier(enable_semantic=True)
result = classifier.classify("сколько стоит Wipon Pro?")

# Execution flow:
# Stage 1 (Priority Patterns): Match "сколько стоит" → price_question (0.95)
# Return immediately, skip stages 2-5
# Total time: ~1.2ms

result = classifier.classify("хочу узнать про интеграцию с 1С")

# Execution flow:
# Stage 1: No priority pattern match
# Stage 2 (Root): Match "интеграц" → question_integrations (0.75) < 0.85
# Stage 3 (Lemma): Match "интеграция" → question_integrations (0.80) >= 0.65
# Return lemma result, skip stages 4-5
# Total time: ~8ms
```

**CascadeResult структура:**

```python
@dataclass
class CascadeResult:
    intent: str
    confidence: float
    stage: ClassificationStage  # PRIORITY_PATTERN | ROOT | LEMMA | SEMANTIC | FALLBACK
    method: str  # Для обратной совместимости

    pattern_matched: Optional[str]  # Regex pattern (Stage 1)
    root_scores: Dict[str, float]   # Top scores (Stage 2)
    lemma_scores: Dict[str, float]  # Top scores (Stage 3)
    semantic_scores: Dict[str, float]  # Top scores (Stage 4)

    stage_times_ms: Dict[str, float]  # Timing для каждого этапа
    total_time_ms: float
```

**Thresholds (configurable):**

```python
classifier = CascadeIntentClassifier(
    high_threshold=0.85,      # Early return для Stage 1-2
    medium_threshold=0.65,    # Return для Stage 3
    semantic_threshold=0.55,  # Minimum для Stage 4
    min_confidence=0.3,       # Minimum для возврата intent (иначе unclear)
    enable_semantic=True      # Включить Stage 4
)
```

**Performance Metrics:**

| Stage | Latency | Accuracy | Coverage |
|-------|---------|----------|----------|
| Priority Patterns | ~1-2ms | ~98% | ~40% |
| Root Classifier | ~2-5ms | ~92% | ~60% |
| Lemma Classifier | ~10-30ms | ~88% | ~75% |
| Semantic Classifier | ~50-150ms | ~82% | ~90% |

**Feature Flag:** cascade_classifier (для HybridClassifier)

**Factory Function:**
```python
from src.classifier.cascade import get_cascade_classifier, reset_cascade_classifier

# Get singleton instance
classifier = get_cascade_classifier(enable_semantic=True)

# Reset singleton (testing)
reset_cascade_classifier()
```

**Explain Method (для отладки):**
```python
explanation = classifier.explain("сколько стоит?")
# {
#     "message": "сколько стоит?",
#     "final_intent": "price_question",
#     "final_confidence": 0.95,
#     "stage_used": "priority_pattern",
#     "method": "priority_pattern",
#     "pattern_matched": "скольк\\w*\\s*стоит",
#     "stages": {
#         "root": {"top_intents": [...]},
#         "lemma": {"top_intents": [...]},
#         "semantic": {"available": False}
#     },
#     "timing_ms": {...},
#     "total_time_ms": 1.2
# }
```

**SSoT:** src/classifier/cascade.py

## HybridClassifier (fallback)

Быстрый regex-based классификатор для fallback при недоступности LLM.

```python
from src.classifier import HybridClassifier

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

#### 4. PRIORITY_PATTERNS (491 паттерн)

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

## RefinementPipeline Architecture

Универсальная архитектура для уточнения результатов классификации. Решает проблемы контекстной классификации через расширяемый pipeline слоёв.

### Архитектура и дизайн-принципы

RefinementPipeline реализует Registry Pattern с Protocol-based интерфейсом для динамической регистрации и выполнения refinement layers.

**Дизайн-принципы:**
- **OCP (Open-Closed):** Новые слои добавляются без изменения pipeline кода
- **DIP (Dependency Inversion):** Pipeline зависит от абстракции IRefinementLayer, не от конкретных реализаций
- **SRP (Single Responsibility):** Каждый слой имеет одну ответственность
- **Registry Pattern:** Динамическая регистрация и поиск слоёв
- **Configuration-Driven:** Порядок и настройки слоёв из YAML
- **Fail-Safe:** Ошибки отдельного слоя не ломают pipeline

**Основные компоненты:**

1. **IRefinementLayer (Protocol)** — контракт для всех слоёв:
   - name: уникальное имя слоя
   - priority: LayerPriority (CRITICAL > HIGH > NORMAL > LOW > FALLBACK)
   - enabled: активен ли слой
   - should_apply(ctx): проверка применимости слоя
   - refine(message, result, ctx): логика уточнения
   - get_stats(): мониторинг статистики

2. **BaseRefinementLayer (ABC)** — базовый класс с общей функциональностью:
   - Feature flag интеграция
   - Error handling (fail-safe)
   - Statistics tracking
   - Logging
   - Template methods: _should_apply(), _do_refine()

3. **RefinementLayerRegistry** — singleton registry для слоёв:
   - register(name, layer_class): регистрация слоя
   - get_layer_instance(name): получение экземпляра слоя
   - Thread-safe для lookup операций
   - Кеширование экземпляров слоёв

4. **RefinementPipeline** — оркестрация слоёв:
   - Загрузка конфигурации из constants.yaml
   - Инстанциация enabled слоёв из registry
   - Сортировка по priority (highest first)
   - Последовательное выполнение слоёв
   - Передача refined result следующему слою

5. **RefinementContext** — универсальный контекст:
   - Содержит всю информацию для decision-making слоёв
   - Обновляется между слоями (update_from_result)
   - Immutable semantics (новый объект при update)

6. **RefinementResult** — результат работы слоя:
   - decision: PASS_THROUGH | REFINED | SKIPPED | ERROR
   - intent: финальный интент (refined или original)
   - confidence: финальная уверенность
   - refinement_reason: код причины refinement
   - metadata: дополнительные метаданные

**Execution Flow:**
```
message → Classifier → RefinementPipeline → result

RefinementPipeline:
  1. Создать RefinementContext из classification result + context
  2. Для каждого enabled layer (по priority):
     a. layer.should_apply(ctx) → True?
     b. layer.refine(message, result, ctx) → RefinementResult
     c. Если REFINED:
        - Обновить result метаданными
        - Обновить ctx для следующего слоя
        - Добавить layer.name в refinement_chain
  3. Вернуть обновлённый result с refinement_chain и timing
```

**Feature Flag Verification:**
Pipeline автоматически проверяет, что все FEATURE_FLAG слоёв зарегистрированы в FeatureFlags.DEFAULTS. Если flag отсутствует, выдаётся WARNING и flag auto-регистрируется как True. Это предотвращает dead code pattern.

### Визуальная архитектура

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

### Встроенные слои (8+ refinement layers)

RefinementPipeline включает 8+ специализированных слоёв, каждый решает конкретную проблему классификации.

#### 1. ConfidenceCalibrationLayer

Научная калибровка LLM confidence для решения проблемы overconfident LLM.

**Проблема:** LLM генерирует confidence как текст, а не вычисляет алгоритмически. Это приводит к overconfidence — высокой уверенности (0.85-0.95) даже при ошибочной классификации.

**Решение:** Три научно-обоснованные стратегии калибровки:

1. **EntropyCalibrationStrategy** — использует Shannon entropy для оценки неопределённости:
   - Высокая entropy (распределение вероятностей по многим альтернативам) → понижаем confidence
   - Формула: H = -Σ(p_i × log(p_i))
   - Normalized entropy: H_norm = H / log(n)
   - Penalty: если H_norm > threshold, применяется entropy_penalty_factor

2. **GapCalibrationStrategy** — анализирует разрыв между top-1 и top-2 интентами:
   - Маленький gap → неоднозначная классификация → понижаем confidence
   - Особый штраф за high confidence + small gap (подозрительно)
   - Gap = confidence_primary - confidence_top_alternative

3. **HeuristicCalibrationStrategy** — pattern-based правила для известных ошибок LLM:
   - Короткие сообщения с высоким confidence → подозрительно
   - Overconfident intents (greeting, farewell, small_talk) → штраф
   - Context mismatch (data-expecting action + non-data intent) → штраф
   - Objection without alternatives → повышенный штраф (Rule 5)

**Пример калибровки:**
```python
# LLM вернул confidence 0.9 для "да"
# Alternatives: [{"intent": "agreement", "confidence": 0.75}]
# Результат после калибровки:
# - Entropy penalty: 0.05 (alternatives были)
# - Gap penalty: 0.1 (gap = 0.9 - 0.75 = 0.15 < 0.2)
# - Heuristic penalty: 0.15 (short message + high confidence)
# Итого: 0.9 - 0.05 - 0.1 - 0.15 = 0.6
```

**Научная база:**
- LLMs are systematically overconfident (Guo et al., 2017)
- Entropy correlates with prediction uncertainty (Shannon, 1948)
- Calibration improves decision-making reliability (Niculescu-Mizil & Caruana, 2005)
- Verbal confidence needs post-hoc calibration (Tian et al., 2023)

**Приоритет:** CRITICAL (100) — выполняется первым, до всех остальных слоёв.

**SSoT:** src/classifier/confidence_calibration.py

**Конфигурация (constants.yaml):**
```yaml
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
  min_gap_for_high_confidence: 0.15
  high_confidence_small_gap_penalty: 0.1
  no_alternatives_penalty: 0.1

  # Heuristic strategy
  heuristic_enabled: true
  short_message_words: 3
  short_message_penalty: 0.15
  overconfident_intent_penalty: 0.1
  context_mismatch_penalty: 0.1
  objection_overconfidence_penalty: 0.1
  objection_no_alternatives_penalty: 0.15  # Rule 5
```

#### 2. SecondaryIntentDetectionLayer

Детекция вторичных интентов в составных сообщениях для решения "Lost Question Bug".

**Проблема:** Когда пользователь отправляет составное сообщение типа "100 человек. Сколько стоит?", LLM классификатор выбирает ОДИН primary intent (часто info_provided для данных). Question intent (price_question) ТЕРЯЕТСЯ.

**Решение:** Этот слой детектирует secondary intents (особенно вопросы) в ЛЮБОМ сообщении, независимо от primary intent. Secondary intents сохраняются в result metadata и могут быть обработаны Knowledge Sources.

**Архитектура:**
- Запускается EARLY в pipeline (HIGH priority, после confidence calibration)
- НЕ меняет primary intent (сохраняет решение classifier)
- ДОБАВЛЯЕТ secondary_intents список в result metadata
- Использует keyword/pattern matching для надёжности (без LLM зависимости)
- Configuration-driven: patterns из constants.yaml

**Дизайн-принципы:**
- Non-destructive: никогда не перезаписывает primary intent
- Additive: только добавляет metadata
- Fast: O(n) pattern matching, без внешних вызовов
- Fail-safe: возвращает original при ошибке
- Universal: работает с ЛЮБЫМ flow (SPIN, BANT, custom)

**Пример:**
```python
Input:
    message: "100 человек. Сколько стоит?"
    intent: "info_provided"
    confidence: 0.85

Output:
    intent: "info_provided"  # UNCHANGED
    confidence: 0.85         # UNCHANGED
    secondary_intents: ["price_question"]  # ADDED
    secondary_intent_confidence: {"price_question": 0.9}  # ADDED
```

**Detection Patterns:**
- price_question: "сколько стоит", "какая цена", "прайс", "тариф"
- question_features: "какие функции", "что умеет", "функционал"
- question_integrations: "интеграция", "api", "webhook", "касп[иы]", "1с"
- question_technical: "технический", "настройка", "ssl", "протокол"
- question_security: "безопасность", "шифрование", "gdpr", "2fa"
- question_equipment: "оборудование", "терминал", "касса", "сканер"
- demo_request: "демо", "показать", "попробовать"
- callback_request: "перезвоните", "свяжитесь"

**Algorithm:**
1. Normalize message (lowercase)
2. Fast keyword check (O(1) set intersection)
3. Pattern matching для keyword-matched intents
4. Rank by confidence and priority
5. Add to secondary_intents (excluding primary intent)

**Usage by Downstream:**
- FactQuestionSource проверяет secondary_intents для question_* intents
- DialoguePolicy использует secondary_intents для overlay decisions
- Response generator может acknowledge оба: данные И вопрос

**Приоритет:** HIGH (75)
**SSoT:** src/classifier/secondary_intent_detection.py

#### 3. DisambiguationResolutionLayer

Resolves user responses after disambiguation через 3 пути (critical intent, option selection, custom input).

**Проблема:** bot.py содержал ~540 lines параллельного disambiguation code с дублированием логики resolution.

**Решение:** CRITICAL priority layer в RefinementPipeline с тремя путями:

**Path A: Critical Intent Override**
- Если LLM классифицировал critical intent (rejection, escalation, contact_provided, demo_request)
- Немедленный выход из disambiguation
- Возвращает classification as-is

**Path B: Option Selection**
- Пользователь выбрал одну из предложенных опций ("1", "2", "первое", "второе")
- DisambiguationUI.parse_answer() парсит ответ
- Маппинг option number → intent из disambiguation_options
- Refinement к выбранному intent с confidence 0.9

**Path C: Custom Input Pass-Through**
- Пользователь ввёл free text (не распознано как option)
- LLM classification IS the answer
- Pass-through с exit_disambiguation flag

**Все пути:** Возвращают valid RefinementResult. Нет early returns, нет None.

**Activation:** Только когда ctx.in_disambiguation == True

**Приоритет:** CRITICAL (100) - запускается первым, до всех остальных слоёв
**SSoT:** src/classifier/disambiguation_resolution_layer.py

#### 4. OptionSelectionRefinementLayer

Обработка выбора из предложенных опций ("1", "2", "первое") в non-disambiguation контексте.

**Проблема:** LLM классифицирует numeric answers как request_brevity вместо info_provided.

**Root Cause (3-part):**
1. ClientAgent detected simple "или" questions as disambiguation
2. ShortAnswerRefinementLayer didn't handle request_brevity
3. No layer to detect option selection context

**Примеры ошибок:**
```python
# Пример 1: Inline question
# Bot: "Скорость или функционал?"
# Client: "1"
# LLM: request_brevity (0.9) ❌
# Expected: info_provided ✓

# Пример 2: Numbered options
# Bot: "1) Desktop 2) Pro 3) Kassa — что интересует?"
# Client: "второе"
# LLM: unclear (0.7) ❌
# Expected: info_provided ✓
```

**Решение:**
- Детекция option patterns в last_bot_message:
  - "или" pattern: "X или Y?"
  - Numbered lists: "1) ... 2) ..."
  - Choice indicators: "выбрать", "что интересует"
- Numeric answer detection: "1", "2", "первый", "второе"
- Refinement request_brevity/unclear → info_provided
- Added request_brevity to LOW_SIGNAL_INTENTS в ShortAnswerRefinementLayer
- Fixed ClientAgent disambiguation — removed broad r"или\s+.+\?$" pattern

**Примеры успешного refinement:**
```python
# Пример 1: "или" question
# Last bot message: "Скорость или функционал важнее?"
# Client: "1"
# LLM: request_brevity (0.9)
# After refinement: info_provided (0.9)

# Пример 2: Numbered options
# Last bot message: "1) Wipon Desktop 2) Wipon Pro"
# Client: "второй вариант"
# LLM: unclear (0.7)
# After refinement: info_provided (0.85)
```

**Scientific Basis:**
- Grice's Cooperative Principle: короткие ответы на вопросы несут implicature ответа на этот вопрос
- Conversational repair research: numeric responses на binary questions понимаются как selections, не meta-comments

**Приоритет:** HIGH — выполняется раньше ShortAnswerRefinementLayer
**SSoT:** src/classifier/refinement_layers.py

#### 5. FirstContactRefinementLayer

Уточнение классификации на первом контакте (turn <= 2 в greeting/initial states).

**Проблема:** LLM классифицирует cautious interest как objection на turn=1.

```python
# Example: "слушайте мне тут посоветовали... но я не уверен"
# LLM: objection_trust (0.9) → handle_objection
# Expected: consultation_request → greeting + dialog start
```

**Semantic Difference по turn_number:**
- turn=1: "не уверен" = modesty, cautious interest (первое знакомство)
- turn>3: "не уверен" = doubt after presentation (реальное возражение)

**Решение:**
- Применяется только на turn <= 2 в greeting/initial states
- Детекция referral patterns ("посоветовали", "рекомендовали", "порекомендовал")
- Детекция cautious interest patterns ("не уверен", "хочу понять", "интересно узнать")
- Refinement suspicious objection intents → consultation_request

**Примеры:**
```python
# Пример 1: Referral + cautious interest
# Message: "мне тут коллега посоветовал, но я не уверен стоит ли"
# Turn: 1
# LLM: objection_trust (0.85)
# After refinement: consultation_request (0.9)

# Пример 2: Pure cautious interest
# Message: "интересно, но хочу сначала понять как это работает"
# Turn: 2
# LLM: objection_think (0.8)
# After refinement: consultation_request (0.85)

# Пример 3: Turn > 2 (no refinement)
# Message: "не уверен что это нам подходит"
# Turn: 5
# LLM: objection_think (0.85)
# No refinement — это реальное возражение после презентации
```

**Приоритет:** HIGH — выполняется перед ObjectionRefinementLayer
**SSoT:** src/classifier/refinement_layers.py

#### 6. GreetingContextRefinementLayer

Refines technical/misclassified intents in greeting context для предотвращения Dialog Failure.

**Проблема:** В greeting state, intents типа problem_sync, request_references классифицируются LLM, но ведут к escalated/close через _universal_base transitions. Слой перенаправляет их в problem_revealed/need_expressed для входа в flow.

**SSOT Categories:** Использует категории из constants.yaml — добавление intent в technical_problems category автоматически включает его в suspicious_intents.

**Конфигурация:**
```yaml
greeting_context_refinement:
  enabled: true
  max_turn_number: 3
  active_states: ["greeting"]
  suspicious_intent_categories:
    - technical_problems  # SSOT from INTENT_CATEGORIES
  additional_suspicious_intents: []  # Edge cases
  default_target: "problem_revealed"
  target_overrides:
    problem_sync: "problem_revealed"
    request_references: "need_expressed"
```

**Приоритет:** HIGH (75)
**SSoT:** src/classifier/refinement_layers.py

#### 7. ComparisonRefinementLayer

Refinement comparison интентов в objection_competitor.

**Проблема:** "чем Wipon лучше Poster" классифицировался как question_features вместо objection_competitor.

**Решение:**
- Comparison patterns: "чем лучше", "отличие от", "vs", "сравните"
- Competitive objection patterns: "дешевле", "дороже", "конкурент лучше"
- Competitor name patterns: "bitrix", "amo", "salesforce", "hubspot"
- Refinement к objection_competitor при наличии competitive signals

**COMPARISON_INTENTS:**
- comparison
- question_product_comparison
- question_tariff_comparison
- question_snr_comparison

**Примеры:**
```python
# "У Битрикс дешевле" → comparison → objection_competitor
# "Конкурент лучше по функционалу" → comparison → objection_competitor
# "Зачем вы если есть AmoCRM?" → comparison → objection_competitor
```

**Приоритет:** NORMAL
**Feature flag:** comparison_refinement (off by default)
**SSoT:** src/classifier/comparison_refinement.py

#### 8. DataAwareRefinementLayer

Promotion unclear → info_provided когда DataExtractor находит business data.

**Проблема:** "не знаю точно но около 15 человек" → unclear вместо info_provided. False stall detection (54% rate).

**Решение:**
- Проверка extracted_data для meaningful fields (company_size, pain_point, business_type)
- Refinement unclear → info_provided при наличии данных
- Defense-in-depth Layer 1 для stall prevention

**Meaningful Fields:**
```python
_MEANINGFUL_FIELDS = frozenset({
    "company_size", "pain_point", "pain_category", "role",
    "timeline", "contact_info", "budget_range",
    "current_tools", "business_type", "users_count",
    "pain_impact", "financial_impact", "desired_outcome",
    "urgency", "client_name",
})
```

**Trivial fields excluded:** option_index, high_interest, value_acknowledged, preferred_channel, contact_type

**Результаты:** Stall rate **54% → <10%**
**Приоритет:** NORMAL
**Feature flag:** data_aware_refinement
**SSoT:** src/classifier/data_aware_refinement.py

#### 9. ShortAnswerRefinementLayer

Уточняет классификацию коротких ответов ("да", "1", "ок") на основе контекста SPIN-фазы.

**Проблема:** LLM классификатор неверно классифицирует короткие сообщения ("1", "да", "первое") как greeting вместо контекстно-правильных интентов (situation_provided, problem_revealed). Это вызывало State Loop bug - зацикливание в greeting state (52 случая в e2e симуляции).

**Root Cause:** LLM без контекста видит только текст "1" и выбирает наиболее вероятный intent (greeting). Контекст SPIN фазы не учитывается достаточно сильно.

**Решение:**
- ClassificationRefinementLayer анализирует короткие сообщения и уточняет классификацию на основе SPIN фазы
- Конфигурация через constants.yaml → spin.short_answer_classification
- Feature flag classification_refinement для безопасного роллаута
- Fallback transition в greeting state (turn_number_gte_3 → entry_state)
- Улучшенный LLM prompt с явными инструкциями для коротких ответов

**LOW_SIGNAL_INTENTS:**
- greeting
- unclear
- small_talk
- gratitude
- request_brevity (FIX: добавлен для обработки "1" misclassifications)

**AWAITING_DATA_ACTIONS:**
- ask_about_company, ask_about_problem, ask_about_impact, ask_about_outcome
- ask_situation, ask_problem, ask_implication, ask_need_payoff
- transition_to_spin_*, continue_current_goal, clarify_one_question

**Sentiment Detection:**
- Negative patterns: "нет", "не надо", "не нужно", "не интересно"
- Positive patterns: "да", "ок", "хорошо", "согласен", "первое", "второе"
- Numbers: typically positive (answering data questions)

**Конфигурация (constants.yaml):**
```yaml
spin:
  short_answer_classification:
    enabled: true
    max_words: 5  # Считается "коротким"
    situation:
      positive_intent: situation_provided
      positive_confidence: 0.7
      negative_intent: no_problem
      negative_confidence: 0.7
    problem:
      positive_intent: problem_revealed
      positive_confidence: 0.7
      negative_intent: no_problem
      negative_confidence: 0.7
    implication:
      positive_intent: implication_acknowledged
      positive_confidence: 0.7
    need_payoff:
      positive_intent: need_expressed
      positive_confidence: 0.7
```

**Примеры:**
```python
# Пример 1: фаза "situation", сообщение "1"
# LLM: greeting (0.8)
# Sentiment: positive (number)
# After refinement: situation_provided (0.7) с company_size=1

# Пример 2: фаза "problem", сообщение "да, теряем клиентов"
# LLM: greeting (0.7)
# Sentiment: positive ("да")
# After refinement: problem_revealed (0.7) с pain_point="теряем клиентов"

# Пример 3: фаза "implication", сообщение "первое"
# LLM: greeting (0.8)
# Sentiment: positive ("первое")
# After refinement: implication_acknowledged (0.7)
```

**Результаты:**
- 32/32 unit тестов проходят
- e2e симуляция: **100% успешность** (было примерно 48% с 52 State Loop случаями)
- State Loop ошибки: **0** (было 52)
- Средний success rate по всем flows: **+52%**

**Приоритет:** HIGH
**SSoT:** src/classifier/refinement_layers.py

#### 10. CompositeMessageLayer

Обрабатывает составные сообщения с приоритетом извлечения данных.

**Проблема:** "5 человек, больше не нужно, быстрее" классифицируется как objection_think вместо info_provided с company_size=5.

**Key Principle:** Когда бот спросил о данных и пользователь отвечает с extractable data, приоритет data intent над meta-intents.

**REFINABLE_INTENTS:**
- objection_think, objection_no_need, objection_no_time
- rejection, unclear, small_talk, gratitude

**Data Extraction Logic:**
1. Проверка action_expects_data mapping (last_action → expected_type)
2. Extraction patterns для company_size, pain_point, budget_range
3. Валидация извлечённых данных (min/max bounds)
4. Refinement к target intent (default: info_provided)

**Secondary Signals Detection:**
- urgency: "быстрее", "срочно", "не тяни"
- impatience: "давай уже", "хватит", "конкретно"
- brevity_request: "короче", "по делу"

**Ambiguous Pattern Resolution:**
- "больше не нужно" — контекст-зависимо:
  - В data context (ask_about_company) → info_provided
  - В rejection context → rejection

**Примеры:**
```python
# Пример 1: Data + meta-signals
# Bot: "Сколько у вас человек в команде?"
# Client: "5 человек, быстрее давайте"
# LLM: objection_timing (0.7)
# After refinement: info_provided (0.75)
#   extracted_data: {company_size: 5}
#   secondary_signals: ["urgency"]

# Пример 2: Ambiguous pattern
# Bot: "Какие у вас боли?"
# Client: "больше не нужно"
# LLM: rejection (0.8)
# After refinement: Pass through (rejection context)
```

**Приоритет:** HIGH
**Feature flag:** composite_refinement
**SSoT:** src/classifier/refinement_layers.py

#### 11. ObjectionRefinementLayerAdapter

Валидирует objection-классификации с учётом контекста диалога.

**Проблема:** "бюджет пока не определён" классифицируется как objection_price, хотя бот только что спросил о бюджете (это ответ, не возражение).

**Refinement Rules:**

**Rule 1: Topic Alignment**
- Если objection topic совпадает с last_action topic → это info_provided, не objection
- Topic mapping: objection_price → "budget", objection_competitor → "competitor"
- Action mapping: ask_about_budget → "budget" topics

**Rule 2: Question Markers**
- Если сообщение содержит "?" или question markers → это вопрос, не objection
- Question markers: "как", "что", "где", "когда", "почему", "сколько"

**Rule 3: Callback Patterns**
- objection_no_time + callback patterns → callback_request
- Callback patterns: "перезвоните", "позже созвонимся"

**Rule 4: Interest Patterns**
- objection_think + interest patterns → question_features
- Interest patterns: "интересно", "хочу понять", "расскажите"

**Rule 5: Uncertainty Patterns (FIX for Skeptic Personas)**
- objection_think + uncertainty patterns → question_features
- Uncertainty patterns: "не уверен нужно ли", "сомневаюсь", "зачем это нужно"
- **FIX:** Это правило было MISSING в adapter, но present в ObjectionRefinementLayer
- Без него skeptic personas застревали в objection_stuck → phases_reached: []

**Примеры:**
```python
# Rule 1: Topic alignment
# Bot: ask_about_budget
# Client: "бюджет пока не определён"
# LLM: objection_price (0.8)
# After refinement: info_provided (0.75)

# Rule 2: Question markers
# Client: "а сколько это стоит?"
# LLM: objection_price (0.85)
# After refinement: price_question (0.7)

# Rule 5: Uncertainty pattern
# Client: "не уверен нужно ли это вообще"
# LLM: objection_think (0.8)
# After refinement: question_features (0.7)
```

**OBJECTION_INTENTS:**
- objection_price, objection_no_time, objection_think
- objection_no_need, objection_competitor, objection_complexity
- objection_trust, objection_risk, objection_timing

**High Confidence Threshold:** 0.85 — objections с confidence >= 0.85 без context issues принимаются as-is

**Приоритет:** NORMAL
**Feature flag:** objection_refinement
**SSoT:** src/classifier/refinement_layers.py

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
    - name: disambiguation_resolution
      enabled: true
      priority: CRITICAL
      feature_flag: unified_disambiguation
    - name: secondary_intent_detection
      enabled: true
      priority: HIGH
      feature_flag: secondary_intent_detection
    - name: option_selection
      enabled: true
      priority: HIGH
      feature_flag: option_selection_refinement
    - name: first_contact
      enabled: true
      priority: HIGH
      feature_flag: first_contact_refinement
    - name: greeting_context
      enabled: true
      priority: HIGH
      feature_flag: greeting_context_refinement
    - name: short_answer
      enabled: true
      priority: HIGH
      feature_flag: classification_refinement
    - name: composite_message
      enabled: true
      priority: HIGH
      feature_flag: composite_refinement
    - name: comparison
      enabled: true
      priority: NORMAL
      feature_flag: comparison_refinement
    - name: data_aware
      enabled: true
      priority: NORMAL
      feature_flag: data_aware_refinement
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
  no_alternatives_penalty: 0.1
  min_gap_for_high_confidence: 0.15
  high_confidence_small_gap_penalty: 0.1

  # Heuristic strategy
  heuristic_enabled: true
  short_message_words: 3
  short_message_penalty: 0.15
  overconfident_intent_penalty: 0.1
  context_mismatch_penalty: 0.1
  objection_overconfidence_penalty: 0.1
  objection_no_alternatives_penalty: 0.15  # Rule 5: Objection without alternatives
  objection_no_alternatives_threshold: 0.75

  # Overconfident intents
  overconfident_intents:
    - greeting
    - farewell
    - small_talk
    - agreement
    - gratitude

  # Data expecting actions
  data_expecting_actions:
    - ask_about_company
    - ask_about_problem
    - ask_situation
    - ask_problem
    - ask_implication
    - ask_need_payoff

  # Data intents
  data_intents:
    - info_provided
    - situation_provided
    - problem_revealed
    - implication_acknowledged
    - need_expressed

  # Objection intents
  objection_intents:
    - objection_price
    - objection_no_time
    - objection_think
    - objection_no_need
    - objection_competitor
```

**Feature Flags:**
```python
# Включить весь pipeline
flags.is_enabled("refinement_pipeline")  # True по умолчанию

# Отдельные слои
flags.confidence_calibration     # confidence_calibration layer (CRITICAL)
flags.first_contact_refinement   # first_contact layer (HIGH) NEW
flags.option_selection_refinement # option_selection layer (HIGH) NEW
flags.classification_refinement  # short_answer layer (HIGH)
flags.composite_refinement       # composite_message layer (HIGH)
flags.objection_refinement       # objection layer (NORMAL)
flags.secondary_intent_detection # secondary_intent detection NEW
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

### SSoT (Single Source of Truth) — File Mapping

| Компонент | Файл | Описание |
|-----------|------|----------|
| **Pipeline Core** | src/classifier/refinement_pipeline.py | IRefinementLayer Protocol, BaseRefinementLayer, RefinementLayerRegistry, RefinementPipeline |
| **Confidence Calibration** | src/classifier/confidence_calibration.py | ConfidenceCalibrationLayer, EntropyStrategy, GapStrategy, HeuristicStrategy |
| **Secondary Intent Detection** | src/classifier/secondary_intent_detection.py | SecondaryIntentDetectionLayer, pattern matching, Lost Question Bug fix |
| **Disambiguation Resolution** | src/classifier/disambiguation_resolution_layer.py | DisambiguationResolutionLayer, 3 resolution paths |
| **Layer Adapters (6 layers)** | src/classifier/refinement_layers.py | ShortAnswer, CompositeMessage, FirstContact, GreetingContext, OptionSelection, Objection |
| **Data Aware Refinement** | src/classifier/data_aware_refinement.py | DataAwareRefinementLayer, unclear → info_provided при данных |
| **Comparison Refinement** | src/classifier/comparison_refinement.py | ComparisonRefinementLayer, comparison → objection_competitor |
| **Legacy Layers** | src/classifier/refinement.py, composite_refinement.py, objection_refinement.py | Deprecated, используйте RefinementPipeline |
| **LLM Classifier** | src/classifier/llm/classifier.py | LLMClassifier, Qwen3 14B через Ollama |
| **LLM Schemas** | src/classifier/llm/schemas.py | ClassificationResult, ExtractedData Pydantic models |
| **LLM Prompts** | src/classifier/llm/prompts.py | System prompt, few-shot examples |
| **Hybrid Classifier** | src/classifier/hybrid.py | HybridClassifier, regex-based fallback |
| **Cascade Classifier** | src/classifier/cascade.py | CascadeIntentClassifier, 5-этапный пайплайн |
| **Configuration** | src/yaml_config/constants.yaml | refinement_pipeline, confidence_calibration, интенты, паттерны |
| **Feature Flags** | src/feature_flags.py | Все feature flags для классификатора и layers |
| **Tests** | tests/test_refinement_pipeline.py | 33 теста для pipeline |
| **Tests** | tests/test_confidence_calibration.py | Тесты для калибровки |
| **Tests** | tests/test_classification_refinement.py | 32 теста для short answer refinement |

### Сводная таблица всех refinement layers

| Layer | Priority | Feature Flag | Проблема | Решение |
|-------|----------|--------------|----------|---------|
| ConfidenceCalibrationLayer | CRITICAL (100) | confidence_calibration | LLM overconfidence (0.85-0.95 даже при ошибках) | Entropy, Gap, Heuristic стратегии калибровки |
| DisambiguationResolutionLayer | CRITICAL (100) | unified_disambiguation | 540 lines параллельного кода в bot.py | 3 пути: critical intent, option selection, custom input |
| SecondaryIntentDetectionLayer | HIGH (75) | secondary_intent_detection | Lost Question Bug ("100 человек. Сколько?") | Pattern matching для secondary intents в metadata |
| OptionSelectionRefinementLayer | HIGH (75) | option_selection_refinement | "1" → request_brevity вместо info_provided | Детекция option questions в last_bot_message |
| FirstContactRefinementLayer | HIGH (75) | first_contact_refinement | Cautious interest → objection на turn=1 | Referral + cautious patterns → consultation_request |
| GreetingContextRefinementLayer | HIGH (75) | greeting_context_refinement | Technical intents → escalate в greeting | Technical categories → problem_revealed/need_expressed |
| ShortAnswerRefinementLayer | HIGH (75) | classification_refinement | State Loop bug (52 случая), "да" → greeting | SPIN phase context + sentiment detection |
| CompositeMessageLayer | HIGH (75) | composite_refinement | "5 человек, быстрее" → objection_timing | Data extraction priority + secondary signals |
| ComparisonRefinementLayer | NORMAL (50) | comparison_refinement | "чем Wipon лучше Poster" → question_features | Competitive objection signals → objection_competitor |
| DataAwareRefinementLayer | NORMAL (50) | data_aware_refinement | Stall rate 54%, "около 15" → unclear | Extracted meaningful data → info_provided |
| ObjectionRefinementLayerAdapter | NORMAL (50) | objection_refinement | False objections в answer context | 5 rules: topic, question, callback, interest, uncertainty |

**Execution Order (по priority):**
1. CRITICAL layers (100): ConfidenceCalibration, DisambiguationResolution
2. HIGH layers (75): SecondaryIntent, OptionSelection, FirstContact, GreetingContext, ShortAnswer, CompositeMessage
3. NORMAL layers (50): Comparison, DataAware, Objection

**Refinement Statistics (production):**
- Total refinement rate: ~18% (18 из 100 classifications refined)
- Most active layers: ShortAnswer (6%), CompositeMessage (4%), Objection (3%)
- Average latency per layer: 0.5-2ms
- Pipeline total latency: ~5-10ms

### Legacy Mode

При flags.refinement_pipeline == False используется legacy mode с отдельными слоями:

```python
# Legacy pipeline (deprecated):
# 1. ClassificationRefinementLayer (refinement.py)
# 2. CompositeMessageRefinementLayer (composite_refinement.py)
# 3. ObjectionRefinementLayer (objection_refinement.py)

# New pipeline (recommended):
# RefinementPipeline с Registry pattern
```

**Migration Notes:**
- Legacy mode maintained для backward compatibility
- All new layers должны использовать RefinementPipeline
- Legacy layers будут deprecated в будущих версиях

## DataExtractor

Извлечение структурированных данных:

```python
from src.classifier import DataExtractor

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
"llm_classifier": True               # Использовать LLM классификатор (primary)
"cascade_classifier": True           # Каскадный классификатор для HybridClassifier
"semantic_objection_detection": True # Семантическая детекция возражений (legacy)

# RefinementPipeline core
"refinement_pipeline": True          # Универсальный RefinementPipeline (рекомендуется)

# CRITICAL priority layers
"confidence_calibration": True       # Научная калибровка LLM confidence (Entropy, Gap, Heuristic)
"unified_disambiguation": True       # Disambiguation resolution в pipeline

# HIGH priority layers
"secondary_intent_detection": True   # Secondary intent detection (Lost Question Bug fix)
"option_selection_refinement": True  # Option selection в inline questions
"first_contact_refinement": True     # First turn objection → consultation_request
"greeting_context_refinement": True  # Technical intents в greeting → problem/need
"classification_refinement": True    # Short answer refinement (State Loop Bug fix)
"composite_refinement": True         # Composite messages с data priority

# NORMAL priority layers
"comparison_refinement": False       # Comparison → objection_competitor (off by default)
"data_aware_refinement": True        # unclear → info_provided при наличии данных
"objection_refinement": True         # Контекстная валидация objection (5 rules)
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

## Key Innovations and Scientific Approach

### 1. Scientific Confidence Calibration

**Innovation:** Первая в проекте имплементация post-hoc calibration для LLM-generated confidence с использованием научно-обоснованных стратегий.

**Scientific Basis:**
- Shannon Entropy для uncertainty estimation (Shannon, 1948)
- Gap-based ambiguity detection (Niculescu-Mizil & Caruana, 2005)
- Pattern-based heuristics для known failure modes
- Calibration floor/ceiling для bounded predictions

**Impact:** Уменьшение false confidence на 15-20%, улучшение disambiguation triggering.

### 2. Secondary Intent Detection Architecture

**Innovation:** Non-destructive additive approach к multi-intent detection без изменения primary classification.

**Design Principles:**
- Separation of Concerns: primary vs secondary intents
- Fast pattern matching (O(n)) без LLM calls
- Extensible через YAML configuration
- Universal: работает с любым flow

**Impact:** Решение Lost Question Bug, улучшение fact question handling.

### 3. Registry Pattern for Refinement Layers

**Innovation:** Dynamic registration и configuration-driven ordering слоёв через Protocol-based interface.

**Design Principles:**
- OCP: новые слои без изменения pipeline
- DIP: зависимость от абстракции (IRefinementLayer)
- SRP: каждый слой — одна ответственность
- Fail-Safe: errors не ломают pipeline

**Impact:** Расширяемая архитектура, простое добавление новых слоёв.

### 4. Context-Aware Classification Refinement

**Innovation:** Multi-layer approach к context-sensitive refinement с учётом turn_number, phase, action context.

**Layers by Context Type:**
- Turn-aware: FirstContactRefinementLayer (turn <= 2)
- State-aware: GreetingContextRefinementLayer (greeting state)
- Phase-aware: ShortAnswerRefinementLayer (SPIN phase)
- Action-aware: CompositeMessageLayer (data-expecting actions)
- Topic-aware: ObjectionRefinementLayer (topic alignment)

**Impact:** State Loop Bug fix (100% success rate), objection stuck prevention.

### 5. Cascade Classification with Adaptive Thresholds

**Innovation:** 5-этапный пайплайн с adaptive thresholds для оптимального trade-off latency vs accuracy.

**Optimization Strategy:**
- Fast path (regex): 40% cases, 1-2ms
- Medium path (keywords): 35% cases, 5-10ms
- Slow path (lemmatization): 20% cases, 10-30ms
- Fallback (semantic): 5% cases, 50-150ms

**Impact:** 90% cases resolved в < 10ms, fallback для edge cases.

## Тестирование

### Unit Tests

```bash
# Все тесты классификатора
pytest tests/test_classifier.py -v

# Тесты LLM классификатора (требует Ollama)
pytest tests/test_llm_classifier.py -v

# Тесты RefinementPipeline (33 теста)
pytest tests/test_refinement_pipeline.py -v

# Тесты ConfidenceCalibration
pytest tests/test_confidence_calibration.py -v

# Тесты ShortAnswerRefinement (32 теста)
pytest tests/test_classification_refinement.py -v

# Тесты CompositeRefinement
pytest tests/test_composite_refinement.py -v

# С покрытием
pytest tests/test_classifier.py tests/test_refinement_pipeline.py --cov=classifier --cov-report=html
```

### Integration Tests

```bash
# E2E simulation с классификатором
pytest tests/test_e2e_simulation.py -v --sim-count=100

# Проверка State Loop Bug fix
pytest tests/test_state_machine.py::test_short_answer_no_state_loop -v
```

### Performance Tests

```bash
# Benchmark классификаторов
python -m tests.benchmark_classifier

# Cascade vs Hybrid performance
python -m tests.benchmark_cascade_vs_hybrid

# RefinementPipeline latency
python -m tests.benchmark_refinement_pipeline
```

## Производительность

### Classifier Performance

| Классификатор | Латентность | Точность | Use Case |
|--------------|-------------|----------|----------|
| LLMClassifier | ~100-200ms | ~95%+ | Primary classifier, максимальная точность |
| HybridClassifier | ~5-50ms | ~85% | Fallback при Ollama unavailable |
| CascadeClassifier | ~5-10ms (90%), ~50ms (fallback) | ~88% | HybridClassifier с semantic fallback |

### RefinementPipeline Performance

| Metric | Value | Notes |
|--------|-------|-------|
| Average latency | ~5-10ms | Для всего pipeline |
| Refinement rate | ~18% | 18 из 100 classifications refined |
| Layer latency | ~0.5-2ms | Per layer average |
| Most active layers | ShortAnswer (6%), Composite (4%), Objection (3%) | Production stats |

### Cascade Classifier Performance

| Stage | Latency | Coverage | Accuracy |
|-------|---------|----------|----------|
| Priority Patterns | ~1-2ms | ~40% | ~98% |
| Root Classifier | ~2-5ms | ~60% | ~92% |
| Lemma Classifier | ~10-30ms | ~75% | ~88% |
| Semantic Classifier | ~50-150ms | ~90% | ~82% |

**Рекомендации:**
- **LLMClassifier** по умолчанию для максимальной точности
- **RefinementPipeline** enabled для контекстного уточнения
- **ConfidenceCalibration** enabled для борьбы с LLM overconfidence
- **HybridClassifier** для высоконагруженных сценариев или при недоступности Ollama
- **CascadeClassifier** для HybridClassifier с semantic fallback

## Summary and Architecture Overview

### Classification Flow

```
User Message
    |
    v
┌─────────────────────────────────────────────────────────────┐
│ UnifiedClassifier (адаптер)                                  │
│                                                              │
│  flags.llm_classifier == True?                               │
│         │                                                    │
│         v                                                    │
│  ┌──────────────────┐    fallback on error                  │
│  │  LLMClassifier   │ ──────────────────┐                   │
│  │  (Qwen3 14B)     │                   │                   │
│  └────────┬─────────┘                   │                   │
│           │                             v                   │
│           │                   ┌────────────────────┐        │
│           │                   │ HybridClassifier   │        │
│           │                   │ + CascadeClassifier│        │
│           │                   └─────────┬──────────┘        │
│           │                             │                   │
│           └─────────────────────────────┘                   │
│                      │                                       │
│                      v                                       │
│           Classification Result                              │
│           (intent, confidence, extracted_data)               │
└──────────────────────┬───────────────────────────────────────┘
                       │
                       v
┌─────────────────────────────────────────────────────────────┐
│ RefinementPipeline (11+ layers)                              │
│                                                              │
│  CRITICAL (100):                                             │
│  1. ConfidenceCalibration    → научная калибровка           │
│  2. DisambiguationResolution → 3-path resolution             │
│                                                              │
│  HIGH (75):                                                  │
│  3. SecondaryIntentDetection → multi-intent support          │
│  4. OptionSelection          → inline question handling      │
│  5. FirstContact             → turn=1 objection fix          │
│  6. GreetingContext          → technical→problem redirect    │
│  7. ShortAnswer              → State Loop Bug fix            │
│  8. CompositeMessage         → data priority                 │
│                                                              │
│  NORMAL (50):                                                │
│  9. Comparison               → competitive signals           │
│ 10. DataAware                → unclear→info_provided         │
│ 11. Objection                → 5 validation rules            │
│                                                              │
│  Output: Refined Result + Refinement Chain                   │
└──────────────────────┬───────────────────────────────────────┘
                       │
                       v
            Final Classification Result
         (готов для FSM transitions & response)
```

### Key Components Summary

1. **LLMClassifier** — Primary classifier (Qwen3 14B)
   - 34 категории, 300+ интентов из constants.yaml
   - Structured output через Ollama native format
   - Контекстная классификация (SPIN phase, last_action)
   - Few-shot examples для сложных случаев

2. **HybridClassifier** — Regex-based fallback
   - 491 priority patterns
   - RootClassifier + LemmaClassifier
   - Быстрая классификация (~5-50ms)

3. **CascadeIntentClassifier** — 5-этапный пайплайн
   - Priority Patterns → Root → Lemma → Semantic → Fallback
   - Adaptive thresholds для latency optimization
   - 90% cases в < 10ms

4. **RefinementPipeline** — Универсальная архитектура уточнения
   - Registry Pattern с Protocol-based interface
   - 11+ refinement layers с приоритетами
   - Configuration-driven, fail-safe
   - ~18% refinement rate

5. **ConfidenceCalibrationLayer** — Научная калибровка
   - Entropy, Gap, Heuristic стратегии
   - Post-hoc calibration для LLM overconfidence
   - Уменьшение false confidence на 15-20%

6. **SecondaryIntentDetectionLayer** — Multi-intent support
   - Non-destructive, additive approach
   - Pattern matching для secondary intents
   - Lost Question Bug solution

### Configuration Files

| File | Purpose |
|------|---------|
| src/yaml_config/constants.yaml | Интенты, категории, паттерны, refinement config |
| src/yaml_config/settings.yaml | LLM model, thresholds, weights |
| src/feature_flags.py | Feature flags для всех компонентов |

### Production Metrics

- **Classification Accuracy:** ~95% (LLM), ~88% (Cascade)
- **Refinement Rate:** ~18% (18 из 100 refined)
- **Average Latency:** ~100-200ms (LLM + pipeline)
- **State Loop Bugs:** 0 (было 52 в e2e)
- **Stall Rate:** <10% (было 54%)
- **E2E Success Rate:** ~95% (было ~48%)

### Future Improvements

1. **Confidence Calibration:**
   - Temperature scaling для LLM
   - Platt scaling для probability calibration
   - Historical calibration data

2. **Secondary Intent Detection:**
   - Расширение patterns для новых intents
   - Confidence weighting для overlapping patterns
   - Multi-language support

3. **RefinementPipeline:**
   - Dynamic priority adjustment based on performance
   - A/B testing framework для новых layers
   - Auto-tuning thresholds via reinforcement learning

4. **Cascade Classifier:**
   - Adaptive threshold learning
   - Semantic cache для frequent queries
   - Model distillation для faster Stage 4
