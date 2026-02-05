# Phases — Фазы разработки CRM Sales Bot

## Обзор

Система разбита на фазы для постепенного внедрения функциональности. Каждая фаза добавляет новые возможности, управляемые через feature flags. Все основные фазы находятся в production, за исключением Phase 3 (SPIN Optimization), которая находится в тестировании.

**Принципы:**
- **Постепенность** — новые фичи включаются по одной
- **Обратимость** — любую фичу можно выключить без кода
- **Изоляция** — фазы независимы друг от друга
- **Тестируемость** — каждая фаза имеет свои тесты

**Статус по фазам:**
- Phase 0 (Infrastructure) — Production
- Phase 1 (Reliability) — Production
- Phase 2 (Naturalness) — Production
- Phase 3 (SPIN Optimization) — Частично включено (CTA включён по умолчанию; остальное — эксперимент)
- Phase 4 (Advanced Classification) — Production
- Phase 5 (Context Policy) — Production
- Phase 6 (Session Persistence) — Production

## Фаза 0: Инфраструктура

**Цель:** Заложить основу для наблюдаемости и управляемости.

**Статус:** Production

### Компоненты

| Модуль | Флаг | Описание | Статус |
|--------|------|----------|--------|
| `logger.py` | `structured_logging` | Структурированное логирование | Production |
| `metrics.py` | `metrics_tracking` | Трекинг метрик диалогов | Production |
| `feature_flags.py` | — | Управление feature flags | Production |

### logger.py — Структурированное логирование

```python
from logger import logger

# Логирование с контекстом
logger.info("Обработка сообщения", user_id="123", message="привет")
logger.set_conversation("conv_123")
logger.info("Переход в фазу problem")
```

**Режимы:**
- **JSON** (production) — структурированные логи для ELK/Loki
- **Readable** (development) — человекочитаемый формат

### metrics.py — Трекинг метрик

```python
from metrics import ConversationMetrics, ConversationOutcome

metrics = ConversationMetrics("conv_123")

# Начало хода
metrics.start_turn_timer()

# Трекинг событий
metrics.record_turn(
    state="spin_situation",
    intent="situation_provided",
    tone="neutral",
    fallback_used=False,
    fallback_tier=None
)

# Запись возражений
metrics.record_objection("price", resolved=True)

# Завершение
metrics.set_outcome(ConversationOutcome.SUCCESS)

# Получение статистики
summary = metrics.get_summary()
```

### feature_flags.py — Управление фичами

```python
from src.feature_flags import flags

# Проверка флага (property)
if flags.llm_classifier:
    # использовать LLM классификатор

# Проверка флага (метод)
if flags.is_enabled("tone_analysis"):
    # использовать ToneAnalyzer

# Все флаги
all_flags = flags.get_all_flags()

# Группы флагов
flags.enable_group("phase_3")
flags.disable_group("risky")
```

**Переопределение через env:**
```bash
FF_TONE_ANALYSIS=true python bot.py
```

---

## Фаза 1: Защита и надёжность

**Цель:** Обеспечить стабильную работу при любых условиях.

**Статус:** Production

### Компоненты

| Модуль | Флаг | Описание | Статус |
|--------|------|----------|--------|
| `fallback_handler.py` | `multi_tier_fallback` | 4-уровневый fallback | Production |
| `conversation_guard.py` | `conversation_guard` | Защита от зацикливания | Production |

### fallback_handler.py — 4-уровневый Fallback

При ошибке LLM система не падает, а использует fallback:

```
Уровень 1: Knowledge Base
    │       Попытка найти ответ в базе знаний
    ▼
Уровень 2: Company Facts + Dynamic CTA
    │       Общие факты о компании + контекстные подсказки
    ▼
Уровень 3: Generic Response
    │       Шаблонный ответ по действию
    ▼
Уровень 4: Apology
            "Извините, произошла ошибка..."
```

```python
from fallback_handler import FallbackHandler

handler = FallbackHandler()
response = handler.get_fallback(
    tier="tier_2",
    state="spin_problem",
    context={
        "collected_data": {"pain_category": "losing_clients"},
        "last_intent": "price_question"
    }
)
```

### conversation_guard.py — Защита от зацикливания

```python
from conversation_guard import ConversationGuard

guard = ConversationGuard()

# Проверка перед обработкой
can_continue, intervention = guard.check(
    state="spin_situation",
    message="10 человек",
    collected_data={"company_size": 10},
    frustration_level=0
)

if not can_continue:
    # Применить intervention (soft_close, skip, etc.)
    pass

# Запись прогресса
guard.record_progress()
```

---

## Фаза 2: Естественность диалога

**Цель:** Сделать общение более человечным.

**Статус:** Production

### Компоненты

| Модуль | Флаг | Описание | Статус |
|--------|------|----------|--------|
| `tone_analyzer/` | `cascade_tone_analyzer` | Каскадный анализатор тона (3 уровня) | Production |
| `response_variations.py` | `response_variations` | Вариативность ответов | Production |

### tone_analyzer/ — Каскадный анализатор тона

```
tone_analyzer/
├── cascade_analyzer.py     # Основной 3-уровневый каскад
├── regex_analyzer.py       # Tier 1: Regex паттерны (быстро)
├── semantic_analyzer.py    # Tier 2: FRIDA semantic (точно)
├── llm_analyzer.py         # Tier 3: LLM fallback (надёжно)
├── frustration_tracker.py  # Трекинг уровня фрустрации
├── markers.py              # Маркеры для анализа
├── models.py               # Модели данных
└── examples.py             # Примеры и паттерны
```

### Использование анализатора тона

```python
from tone_analyzer import ToneAnalyzer

analyzer = ToneAnalyzer()

result = analyzer.analyze("Это слишком дорого, не интересует")
# ToneAnalysis(
#     tone=Tone.NEGATIVE,
#     frustration_level=3,
#     style=Style.CONCISE
# )

guidance = analyzer.get_response_guidance(result)
# {
#     "tone_instruction": "Будь эмпатичным, не дави",
#     "should_apologize": False,
#     "should_offer_exit": True,
#     "max_words": 30
# }
```

### Cascade Tone Analyzer — 3-уровневый каскад

```
Tier 1: Regex patterns (быстро)
    │
    ▼  низкая уверенность
Tier 2: FRIDA semantic (точно)
    │
    ▼  всё ещё не уверен
Tier 3: LLM fallback (медленно, но надёжно)
```

**Флаги:**
- `cascade_tone_analyzer` — master switch
- `tone_semantic_tier2` — FRIDA (Tier 2)
- `tone_llm_tier3` — LLM fallback (Tier 3)

### response_variations.py — Вариативность ответов

```python
from response_variations import variations

# Получить вариацию приветствия
greeting = variations.get("greeting")
# "Здравствуйте!" / "Добрый день!" / "Привет!"

# С учётом истории (не повторяться)
greeting = variations.get_variant("greeting", used=["Здравствуйте!"])
```

---

## Фаза 3: Оптимизация SPIN Flow

**Цель:** Повысить эффективность продаж через лучшее понимание возражений и персонализированные CTA.

**Статус:** Testing/Development

### Компоненты

| Модуль | Флаг | Описание | Статус |
|--------|------|----------|--------|
| `lead_scoring.py` | `lead_scoring` | Скоринг лидов | Calibration |
| `objection_handler.py` | `objection_handler` | Обработка возражений | Testing |
| `cta_generator.py` | `cta_generator` | Call-to-Action | Production (enabled) |

### lead_scoring.py — Скоринг лидов

```python
from lead_scoring import LeadScorer, get_signal_from_intent

scorer = LeadScorer()

# Добавление сигналов
signal = get_signal_from_intent("situation_provided")
result = scorer.add_signal(signal)

# Результат
# LeadScore(
#     score=65,
#     temperature=Temperature.WARM,
#     signals=["company_size", "pain_revealed"]
# )

# Сводка
summary = scorer.get_summary()
```

### objection_handler.py — Обработка возражений

```python
from objection_handler import ObjectionHandler

handler = ObjectionHandler()

result = handler.handle_objection(
    message="Это слишком дорого для нас",
    collected_data={"company_size": 10}
)
# ObjectionResult(
#     objection_type=ObjectionType.PRICE,
#     strategy="value_reframe",
#     should_soft_close=False,
#     attempt_number=1,
#     response_parts={"message": "...", "points": [...]}
# )
```

**Типы возражений:**
- `price` — дорого
- `no_time` — нет времени
- `think` — подумаю
- `competitor` — уже есть решение
- `complexity` — сложно
- `trust` — не доверяю
- `no_need` — не нужно

### cta_generator.py — Call-to-Action

```python
from src.cta_generator import CTAGenerator

generator = CTAGenerator()

# Инкремент хода
generator.increment_turn()

# Добавление CTA к ответу
response = generator.append_cta(
    response="Wipon поможет решить эту проблему.",
    state="presentation",
    context={"frustration_level": 0}
)
```

---

## Фаза 4: Продвинутая классификация

**Цель:** Повысить точность классификации интентов с помощью каскадного подхода и семантического анализа.

**Статус:** Production

### Компоненты

| Модуль | Флаг | Описание | Статус |
|--------|------|----------|--------|
| `classifier/cascade/` | `cascade_classifier` | Каскадный классификатор (regex, lemma, semantic) | Production |
| `classifier/cascade/` | `semantic_objection_detection` | Семантическая детекция возражений | Production |
| `disambiguation_ui.py` | `intent_disambiguation` | UI для уточнения интента | Development |

### Cascade Classifier — 3-уровневый

```
Tier 1: Regex patterns (быстро, ~100 интентов)
    │
    ▼  низкая уверенность
Tier 2: Lemma matching (точнее)
    │
    ▼  всё ещё не уверен
Tier 3: Semantic similarity (FRIDA)
```

**Особенности каскада:**
- Быстрое выполнение с regex на первом уровне
- Fallback на лемматизацию при низкой уверенности
- Семантический анализ для обработки сложных возражений
- Структурированная экстракция данных из пользовательских сообщений

**Флаги:**
- `cascade_classifier` — master switch для каскада
- `semantic_objection_detection` — semantic fallback для возражений

### Intent Disambiguation (Development)

```
Классификация → несколько интентов с близкими scores
    │
    ▼
Формирование вопроса с вариантами
    │
    ▼
Пользователь выбирает (цифра/текст/свой вариант)
    │
    ▼
Продолжение с выбранным интентом
```

**Поддерживаемые форматы ответа:**
- Числа: `1`, `2`, `3`, `4`
- Слова: `первый`, `второй`, `третий`, `четвёртый`
- Ключевые слова: `цена`, `функции`, `интеграции`
- Свой вариант: `другое`, `4` → переход к вводу своего вопроса

**Статус:** В разработке, не включено в production

---

## Фаза 5: Context Policy & Policy Overlays

**Цель:** Context-aware решения с динамическими policy overlays для автоматического управления диалогом.

**Статус:** Production

### Компоненты

| Модуль | Флаг | Описание | Статус |
|--------|------|----------|--------|
| `context_envelope.py` | `context_full_envelope` | Полный ContextEnvelope | Production |
| `dialogue_policy.py` | `context_policy_overlays` | DialoguePolicy overrides | Production |
| `context_window.py` | — | Расширенный контекст диалога | Production |
| `fallback_handler.py` | `dynamic_cta_fallback` | Динамические подсказки | Testing |

### ContextEnvelope — Единый контекст

Полный контекст диалога, объединяющий информацию из state machine, истории, тона и guard'а:

```python
from context_envelope import build_context_envelope

envelope = build_context_envelope(
    state_machine=sm,
    context_window=ctx_window,
    tone_info=tone_info,
    guard_info={"intervention": None},
    last_action="spin_situation",
    last_intent="situation_provided"
)

# envelope содержит:
# - state, spin_phase, collected_data, missing_data
# - intent_history, action_history
# - objection_count, positive_count
# - has_oscillation, is_stuck
# - confidence_trend
# - tone, frustration_level
```

**Ключевые метрики:**
- Oscillation detection: чередование интереса и возражений
- Stuck pattern detection: застревание в одном состоянии
- Confidence trend: тренд уверенности классификатора
- Frustration tracking: отслеживание уровня фрустрации пользователя

### DialoguePolicy — Policy Overlays

Система перехвата и переопределения действий state machine на основе контекстных правил:

```python
from dialogue_policy import DialoguePolicy

policy = DialoguePolicy(shadow_mode=False, trace_enabled=True)

# Проверка и возможный override
override = policy.maybe_override(sm_result, context_envelope)

if override and override.has_override:
    # Применить override
    sm_result["action"] = override.action
    sm_result["next_state"] = override.next_state
```

**Примеры policy rules:**
- При 3+ unclear подряд → предложить конкретные варианты
- При oscillation (интерес ↔ возражение) → мягко уточнить
- При высоком frustration → предложить выход
- При достаточной информации → предложить демо или встречу

### Context Window — История диалога (Atomic Transitions)

История диалога с поддержкой atomic transitions и детекцией паттернов:

```python
from context_window import ContextWindow

window = ContextWindow(max_size=5)

# Добавить ход
window.add_turn_from_dict(
    user_message="нас 10 человек",
    bot_response="Понял, команда из 10 человек.",
    intent="situation_provided",
    confidence=0.95,
    action="spin_situation",
    state="greeting",
    next_state="spin_situation"
)

# Получить историю
intent_history = window.get_intent_history()  # ["situation_provided"]
action_history = window.get_action_history()  # ["spin_situation"]

# Детекция паттернов
has_oscillation = window.detect_oscillation()  # True/False
is_stuck = window.detect_stuck_pattern()       # True/False
confidence_trend = window.get_confidence_trend()  # "rising"/"falling"/"stable"
```

**Atomic Transitions:** Все переходы состояний гарантированно выполняются полностью или откатываются при ошибке.

### Dynamic CTA Fallback (Testing)

Динамическая генерация Call-to-Action на основе контекста диалога:

```python
DYNAMIC_CTA_OPTIONS = {
    "competitor_mentioned": {
        "options": ["Сравнить с {competitor}", "Узнать отличия"],
        "priority": 10
    },
    "pain_losing_clients": {
        "options": ["Как Wipon помогает удерживать клиентов"],
        "priority": 8
    },
    "pain_no_control": {
        "options": ["Какие отчёты есть в Wipon"],
        "priority": 8
    },
    "pain_manual_work": {
        "options": ["Что можно автоматизировать"],
        "priority": 8
    }
}
```

**Статус:** В тестировании, включено параллельно с основной логикой

---

## Инфраструктура: YAML конфигурация и Refinement Pipeline

**Цель:** Вынести конфигурацию в YAML для изменений без кода и реализовать уточнение классификации через Refinement Pipeline.

**Статус:** Production

### Компоненты

| Модуль | Описание | Статус |
|--------|----------|--------|
| `config_loader.py` | ConfigLoader, FlowConfig, LoadedConfig | Production |
| `yaml_config/constants.yaml` | Константы (limits, intents, policy) | Production |
| `yaml_config/states/` | Состояния диалога | Production |
| `yaml_config/flows/` | Модульные flow с extends/mixins | Production |
| `yaml_config/templates/` | Шаблоны промптов | Production |
| `refinement_pipeline.py` | Уточнение классификации (Semantic, LLM) | Production |

### ConfigLoader — Загрузка конфигурации

```python
from src.config_loader import ConfigLoader, get_config

# Глобальный конфиг
config = get_config()

# Или создать loader
loader = ConfigLoader()
config = loader.load()

# Доступ к настройкам
max_objections = config.limits.get("max_total_objections", 5)
spin_phases = config.spin_phases
```

### FlowConfig — Модульные flow

```python
from src.config_loader import ConfigLoader
from src.state_machine import StateMachine

loader = ConfigLoader()
flow = loader.load_flow("spin_selling")

# FlowConfig содержит resolved данные
print(flow.phase_order)       # ['situation', 'problem', ...]
print(flow.priorities)        # [{name, priority, ...}, ...]
print(flow.states)            # Resolved состояния

sm = StateMachine(flow=flow)
```

### Priority-driven apply_rules

При наличии FlowConfig, StateMachine использует YAML-приоритеты:

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

  - name: phase_progress
    priority: 4
    handler: phase_progress_handler
```

### on_enter Actions

Состояния могут определять action при входе:

```yaml
states:
  ask_activity:
    on_enter:
      action: show_activity_options
```

При переходе в `ask_activity`, action автоматически становится `show_activity_options`.

### Extends и Mixins

```yaml
# Наследование
states:
  spin_situation:
    extends: _base_phase
    mixins:
      - price_handling
      - exit_intents
    goal: "Понять ситуацию"
```

### Templates — Шаблоны промптов

```yaml
# templates/spin_selling/prompts.yaml
templates:
  spin_situation:
    template: |
      Ты — консультант Wipon.
      Цель: узнать ситуацию клиента.
      ...
```

```python
flow = loader.load_flow("spin_selling")
template = flow.get_template("spin_situation")
```

### Refinement Pipeline

Pipeline для уточнения результатов классификации через Semantic и LLM анализ:

```python
from refinement_pipeline import RefinementPipeline

pipeline = RefinementPipeline()

# Уточнить классификацию
refined_result = pipeline.refine(
    message="Это слишком дорого для нас",
    initial_result=classification_result,
    confidence_threshold=0.7
)

# Результат содержит улучшенные данные
# - уточненный intent
# - повышенный confidence
# - дополнительные extracted_data
```

**Процесс уточнения:**
1. Проверка confidence начального результата
2. Семантический анализ (FRIDA) для низких confidence
3. LLM анализ при неуверенности семантики
4. Мергинг результатов с исходной классификацией

**Преимущества:**
- Две попытки улучшить классификацию
- Атомарность операций (откат при ошибке)
- Логирование всех шагов уточнения

### Создание нового Flow

1. Создать `yaml_config/flows/my_flow/flow.yaml`
2. Создать `yaml_config/flows/my_flow/states.yaml`
3. (Опционально) `yaml_config/templates/my_flow/prompts.yaml`
4. Загрузить: `loader.load_flow("my_flow")`

Подробнее: [src/yaml_config/flows/README.md](../src/yaml_config/flows/README.md)

---

## LLM Classifier

**Цель:** Использовать LLM для классификации интентов вместо regex при необходимости.

**Статус:** Production (fallback mode)

### Компоненты

| Модуль | Флаг | Описание | Статус |
|--------|------|----------|--------|
| `classifier/unified.py` | `llm_classifier` | Переключатель LLM/Hybrid | Production |
| `classifier/llm/` | — | LLM классификатор | Production |

### UnifiedClassifier — Адаптер

```python
from src.classifier import UnifiedClassifier

classifier = UnifiedClassifier()

# Автоматически использует LLM или Hybrid
# в зависимости от flags.llm_classifier
result = classifier.classify(message, context)
```

### LLMClassifier — Ollama + Structured Output

```python
from src.classifier.llm import LLMClassifier

classifier = LLMClassifier()

result = classifier.classify("нас 10 человек")
# {
#     "intent": "situation_provided",
#     "confidence": 0.95,
#     "extracted_data": {"company_size": 10},
#     "method": "llm",
#     "reasoning": "Клиент указал размер команды"
# }
```

**При ошибке LLM → fallback на HybridClassifier**

---

## Статус компонентов

| Фаза | Компонент | Флаг | Статус | Примечание |
|------|-----------|------|--------|-----------|
| **Phase 0** | Логирование | `structured_logging` | Production | JSON/readable режимы |
| | Метрики | `metrics_tracking` | Production | Трекинг диалогов |
| | Feature Flags | — | Production | Управление фичами |
| **Phase 1** | Fallback (4-уровневый) | `multi_tier_fallback` | Production | KB → Facts → Generic → Apology |
| | Guard | `conversation_guard` | Production | Защита от зацикливания |
| | Guard Informative | `guard_informative_intent_check` | Production | Проверка информативности |
| | Guard Skip Reset | `guard_skip_resets_fallback` | Production | Fallback при skip |
| **Phase 2** | Response Variations | `response_variations` | Production | Вариативность ответов |
| | Tone Analysis | `tone_analysis` | Production | Анализ тона |
| | Cascade Tone | `cascade_tone_analyzer` | Production | 3-уровневый каскад |
| | Tone Tier 2 (FRIDA) | `tone_semantic_tier2` | Production | Семантический анализ |
| | Tone Tier 3 (LLM) | `tone_llm_tier3` | Production | LLM fallback |
| **Phase 3** | Lead Scoring | `lead_scoring` | Calibration | Требует настройки |
| | Objection Handler | `objection_handler` | Testing | 7 типов возражений |
| | CTA Generator | `cta_generator` | Production (enabled) | Включён по умолчанию |
| | Dynamic CTA Fallback | `dynamic_cta_fallback` | Testing | Контекстные CTA |
| **Phase 4** | Cascade Classifier | `cascade_classifier` | Production | Regex → Lemma → Semantic |
| | Semantic Objection | `semantic_objection_detection` | Production | FRIDA-based detection |
| | Intent Disambiguation | `intent_disambiguation` | Development | UI уточнения интента |
| **Phase 5** | Context Envelope | `context_full_envelope` | Production | Полный контекст |
| | Context Policy Overlays | `context_policy_overlays` | Production | Policy rules |
| | Response Directives | `context_response_directives` | Production | Директивы ответов |
| | Context Window | — | Production | История + Atomic transitions |
| **LLM** | LLM Classifier | `llm_classifier` | Production | Ollama fallback |
| **Support** | Response Dedup | `response_deduplication` | Production | Избегание повторов |
| | Price Override | `price_question_override` | Production | Специальная обработка |
| | Confidence Router | `confidence_router` | Production | Маршрутизация по уверенности |
| | Router Logging | `confidence_router_logging` | Production | Логирование маршрутизации |
| **Config** | ConfigLoader | — | Production | YAML-based configuration |
| | FlowConfig | — | Production | Модульные flows |
| | Priority-driven Rules | — | Production | YAML priorities |
| | on_enter Actions | — | Production | Автоматические действия |

**Легенда статусов:**
- Production — включено в production, стабильно
- Testing — в активном тестировании, может быть нестабильно
- Development — в разработке, не готово
- Calibration — требует калибровки параметров
- Risky — потенциально опасно (deprecated)

## Группы флагов

```python
GROUPS = {
    # Основные фазы
    "phase_0": ["structured_logging", "metrics_tracking"],
    "phase_1": ["multi_tier_fallback", "conversation_guard"],
    "phase_2": ["tone_analysis", "response_variations", "personalization"],
    "phase_3": ["lead_scoring", "circular_flow", "objection_handler", "cta_generator", "dynamic_cta_fallback"],
    "phase_4": ["intent_disambiguation", "cascade_classifier", "semantic_objection_detection"],

    # Context Policy
    "context_phase_0": ["context_full_envelope", "context_shadow_mode"],
    "context_phase_2": ["context_response_directives"],
    "context_phase_3": ["context_policy_overlays", "context_engagement_v2"],
    "context_phase_5": ["context_cta_memory"],
    "context_all": ["context_full_envelope", "context_shadow_mode", "context_response_directives",
                    "context_policy_overlays", "context_engagement_v2", "context_cta_memory"],
    "context_safe": ["context_full_envelope", "context_response_directives"],

    # Cascade Tone Analyzer
    "phase_5_tone": ["cascade_tone_analyzer", "tone_semantic_tier2", "tone_llm_tier3"],
    "tone_safe": ["cascade_tone_analyzer"],
    "tone_full": ["cascade_tone_analyzer", "tone_semantic_tier2", "tone_llm_tier3"],

    # Personalization v2
    "personalization_v2_safe": ["personalization", "personalization_v2", "personalization_adaptive_style"],
    "personalization_v2_full": ["personalization", "personalization_v2", "personalization_adaptive_style",
                                 "personalization_semantic_industry", "personalization_session_memory"],

    # BUG-001 FIX: Guard/Fallback
    "guard_fixes": ["guard_informative_intent_check", "guard_skip_resets_fallback"],

    # Robust Classification
    "robust_classification": ["confidence_router", "confidence_router_logging"],

    # Safety groups
    "safe": ["response_variations", "multi_tier_fallback", "structured_logging", "metrics_tracking",
             "conversation_guard", "cascade_classifier", "semantic_objection_detection"],
    "risky": ["circular_flow", "lead_scoring"],
}
```

## Включение фаз

### Через settings.yaml

```yaml
feature_flags:
  # Фаза 2
  tone_analysis: true
  response_variations: true

  # Фаза 3
  lead_scoring: true
  objection_handler: true
  cta_generator: true

  # Фаза 5
  context_full_envelope: true
  context_policy_overlays: true
```

### Через переменные окружения

```bash
FF_TONE_ANALYSIS=true \
FF_LEAD_SCORING=true \
python bot.py
```

### В коде (runtime)

```python
from src.feature_flags import flags

# Включить группу
flags.enable_group("phase_3")

# Включить отдельный флаг
flags.set_override("tone_analysis", True)

# Выключить флаг
flags.set_override("circular_flow", False)

# Очистить overrides
flags.clear_all_overrides()
```

## Тестирование фаз

```bash
# Все тесты
pytest tests/ -v

# Тесты по фазам
pytest tests/test_logger.py tests/test_metrics.py tests/test_feature_flags.py -v  # Phase 0
pytest tests/test_fallback_handler.py tests/test_conversation_guard.py -v         # Phase 1
pytest tests/test_tone_analyzer.py tests/test_response_variations.py -v           # Phase 2
pytest tests/test_lead_scoring.py tests/test_objection_handler.py -v              # Phase 3
pytest tests/test_phase4_integration.py -v                                         # Phase 4

# Интеграционные тесты
pytest tests/test_spin.py -v
pytest tests/test_simulator_integration.py -v
```

## Рекомендации по внедрению

### Текущее состояние production (все фазы активны)

Все основные фазы (0, 1, 2, 4, 5) полностью включены и стабильны в production.

### Фаза 3 (Testing/Development)

Компоненты phase 3 находятся в тестировании и разработке:

1. **Lead Scoring** (Calibration) — в production, требует мониторинга метрик
2. **Objection Handler** (Testing) — активно тестируется на real conversations
3. **CTA Generator** (Development) — еще в разработке, отключено по умолчанию
4. **Dynamic CTA Fallback** (Testing) — тестируется параллельно с основной логикой

### Порядок включения new features

1. **Фаза 0** — все включены (базовая инфраструктура)
2. **Фаза 1** — все включены (критично для надёжности)
3. **Фаза 2** — все включены (естественность диалога)
4. **Фаза 4** — все включены (улучшенная классификация)
5. **Фаза 5** — все включены (контекстные решения)
6. **Фаза 3** — для новых фич: включать по одной после калибровки

### Добавление новой фичи

При разработке новой фичи следовать порядку:
1. Development → Development flag отключен по умолчанию
2. Testing → Testing flag включен на staging, выключен на production
3. Calibration → Calibration flag включен везде, мониторятся метрики
4. Production → Production flag включен везде, стабилен

### Откат

При проблемах с любой фичей (даже production):

```yaml
# Быстрый откат через settings.yaml
feature_flags:
  problematic_feature: false
```

Или через env:
```bash
FF_PROBLEMATIC_FEATURE=false python bot.py
```

Или в runtime:
```python
flags.set_override("problematic_feature", False)
```

### Мониторинг и метрики

Для каждой фазы следить за метриками:

**Phase 0:**
- Логирование ошибок
- Время обработки диалогов

**Phase 1:**
- Количество fallback срабатываний
- Эффективность guard'а (false positives)

**Phase 2:**
- Точность анализа тона
- Вариативность ответов (не повторяются ли)

**Phase 3:**
- Lead score distribution
- Conversion rate
- Objection resolution rate

**Phase 4:**
- Accuracy классификации
- Confidence scores
- Semantic vs regex comparison

**Phase 5:**
- Policy override frequency
- Oscillation detection effectiveness
- Stuck pattern detection

**Phase 6:**
- Snapshot creation rate
- Restore success rate
- Batch flush success rate
- Client_id mismatch events

## Фаза 6: Session Persistence

**Цель:** Персистентность диалога между сессиями и безопасная работа в мультипроцессе.

**Статус:** Production

### Компоненты

| Модуль | Назначение | Статус |
|--------|------------|--------|
| `history_compactor.py` | LLM-компакция истории при snapshot | Production |
| `snapshot_buffer.py` | Локальный буфер снапшотов (SQLite) | Production |
| `session_manager.py` | Кеш сессий + TTL cleanup + restore | Production |
| `session_lock.py` | Межпроцессный lock по session_id | Production |

### Основной поток

1. Active session → история в памяти.
2. TTL cleanup (тишина ≥ 1 час) → snapshot с компакцией.
3. Local buffer → накопление до вечерней выгрузки.
4. Batch flush после 23:00 → внешняя БД.
5. Restore → local buffer → external snapshot.

### Гарантии

- Snapshot загружается только при cache-miss.
- Последние 4 сообщения берутся из внешней истории.
- `client_id` сохраняется и проверяется при восстановлении.
- Возможен “горячий” switch flow/config во время активной сессии.

---

## Завершение

Система разработана и развернута в production с полной поддержкой:
- Инфраструктура (логирование, метрики, feature flags)
- Надежность (fallback, guards, atomic transitions)
- Естественность (тон, вариации, персонализация)
- Продвинутая классификация (каскадный подход, семантика)
- Контекстные решения (policy overlays, context window)
- Персистентность диалогов (snapshots, session manager, history compaction)

Phase 3 (SPIN Optimization) остается в тестировании для дальнейшей калибровки и оптимизации.
