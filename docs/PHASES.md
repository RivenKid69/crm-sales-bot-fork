# Phases — Фазы разработки CRM Sales Bot

## Обзор

Система разбита на фазы для постепенного внедрения функциональности. Каждая фаза добавляет новые возможности, управляемые через feature flags.

**Принципы:**
- **Постепенность** — новые фичи включаются по одной
- **Обратимость** — любую фичу можно выключить без кода
- **Изоляция** — фазы независимы друг от друга
- **Тестируемость** — каждая фаза имеет свои тесты

## Фаза 0: Инфраструктура

**Цель:** Заложить основу для наблюдаемости и управляемости.

### Компоненты

| Модуль | Флаг | Описание |
|--------|------|----------|
| `logger.py` | `structured_logging` | Структурированное логирование |
| `metrics.py` | `metrics_tracking` | Трекинг метрик диалогов |
| `feature_flags.py` | — | Управление feature flags |

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
from feature_flags import flags

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

### Компоненты

| Модуль | Флаг | Описание |
|--------|------|----------|
| `fallback_handler.py` | `multi_tier_fallback` | 4-уровневый fallback |
| `conversation_guard.py` | `conversation_guard` | Защита от зацикливания |

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

### Компоненты

| Модуль | Флаг | Описание |
|--------|------|----------|
| `tone_analyzer/` | `cascade_tone_analyzer` | Каскадный анализатор тона (3 уровня) |
| `response_variations.py` | `response_variations` | Вариативность ответов |

### tone_analyzer/ — Каскадный анализатор тона

```
tone_analyzer/
├── cascade_analyzer.py     # Основной 3-уровневый каскад
├── regex_analyzer.py       # Tier 1: Regex паттерны (быстро)
├── semantic_analyzer.py    # Tier 2: RoSBERTa semantic (точно)
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
Tier 2: RoSBERTa semantic (точно)
    │
    ▼  всё ещё не уверен
Tier 3: LLM fallback (медленно, но надёжно)
```

**Флаги:**
- `cascade_tone_analyzer` — master switch
- `tone_semantic_tier2` — RoSBERTa (Tier 2)
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

**Цель:** Повысить эффективность продаж.

### Компоненты

| Модуль | Флаг | Описание |
|--------|------|----------|
| `lead_scoring.py` | `lead_scoring` | Скоринг лидов |
| `objection_handler.py` | `objection_handler` | Обработка возражений |
| `cta_generator.py` | `cta_generator` | Call-to-Action |

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
from cta_generator import CTAGenerator

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

## Фаза 4: Intent Disambiguation & Cascade Classifier

**Цель:** Уточнять намерение пользователя при неоднозначных ответах.

### Компоненты

| Модуль | Флаг | Описание |
|--------|------|----------|
| `disambiguation_ui.py` | `intent_disambiguation` | UI для уточнения интента |
| `classifier/cascade/` | `cascade_classifier` | Каскадный классификатор |
| `classifier/cascade/` | `semantic_objection_detection` | Семантическая детекция возражений |

### Disambiguation Flow

```
Классификация → несколько интентов с близкими scores
    │
    ▼
Формирование вопроса с вариантами
    │
    ▼
Пользователь выбирает (цифра/текст)
    │
    ▼
Продолжение с выбранным интентом
```

```python
# В bot.py автоматически
if intent == "disambiguation_needed":
    # Бот задаёт уточняющий вопрос
    # "Уточните, пожалуйста:
    #  1. Хотите узнать цену?
    #  2. Интересует демо?"
```

### Cascade Classifier — 3-уровневый

```
Tier 1: Regex patterns (быстро, ~100 интентов)
    │
    ▼  низкая уверенность
Tier 2: Lemma matching (точнее)
    │
    ▼  всё ещё не уверен
Tier 3: Semantic similarity (RoSBERTa)
```

**Флаги:**
- `cascade_classifier` — master switch для каскада
- `semantic_objection_detection` — semantic fallback для возражений

---

## Фаза 5: Context Policy & Dynamic CTA

**Цель:** Context-aware решения и динамические подсказки.

### Компоненты

| Модуль | Флаг | Описание |
|--------|------|----------|
| `context_envelope.py` | `context_full_envelope` | Полный ContextEnvelope |
| `dialogue_policy.py` | `context_policy_overlays` | DialoguePolicy overrides |
| `context_window.py` | — | Расширенный контекст диалога |
| `fallback_handler.py` | `dynamic_cta_fallback` | Динамические подсказки |

### ContextEnvelope — Единый контекст

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

### DialoguePolicy — Action Overrides

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

### Dynamic CTA Fallback

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

### Context Window — История диалога

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

---

## Phase LLM: LLM Classifier

**Цель:** Использовать LLM для классификации интентов вместо regex.

### Компоненты

| Модуль | Флаг | Описание |
|--------|------|----------|
| `classifier/unified.py` | `llm_classifier` | Переключатель LLM/Hybrid |
| `classifier/llm/` | — | LLM классификатор |

### UnifiedClassifier — Адаптер

```python
from classifier import UnifiedClassifier

classifier = UnifiedClassifier()

# Автоматически использует LLM или Hybrid
# в зависимости от flags.llm_classifier
result = classifier.classify(message, context)
```

### LLMClassifier — vLLM + Outlines

```python
from classifier.llm import LLMClassifier

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

## Статус фаз

| Фаза | Компонент | Флаг | Статус |
|------|-----------|------|--------|
| LLM | LLM Classifier | `llm_classifier` | ✅ Production |
| 0 | Логирование | `structured_logging` | ✅ Production |
| 0 | Метрики | `metrics_tracking` | ✅ Production |
| 1 | Fallback | `multi_tier_fallback` | ✅ Production |
| 1 | Guard | `conversation_guard` | ✅ Production |
| 2 | Вариации | `response_variations` | ✅ Production |
| 2 | Тон | `tone_analysis` | ⏸️ Testing |
| 2 | Cascade Tone | `cascade_tone_analyzer` | ✅ Production |
| 2 | Tone Tier 2 | `tone_semantic_tier2` | ✅ Production |
| 2 | Tone Tier 3 | `tone_llm_tier3` | ✅ Production |
| 3 | Скоринг | `lead_scoring` | ⏸️ Calibration |
| 3 | Возражения | `objection_handler` | ⏸️ Testing |
| 3 | CTA | `cta_generator` | ⏸️ Development |
| 3 | Circular flow | `circular_flow` | ⏸️ Risky |
| 4 | Disambig | `intent_disambiguation` | ⏸️ Development |
| 4 | Cascade Classifier | `cascade_classifier` | ✅ Production |
| 4 | Semantic Objection | `semantic_objection_detection` | ✅ Production |
| 5 | Context Envelope | `context_full_envelope` | ✅ Production |
| 5 | Policy Overlays | `context_policy_overlays` | ✅ Production |
| 5 | Dynamic CTA | `dynamic_cta_fallback` | ⏸️ Testing |

**Легенда:**
- ✅ Production — включено в production
- ⏸️ Testing — в тестировании
- ⏸️ Development — в разработке
- ⏸️ Calibration — требует калибровки
- ⏸️ Risky — потенциально опасно

## Группы флагов

```python
GROUPS = {
    "phase_0": ["structured_logging", "metrics_tracking"],
    "phase_1": ["multi_tier_fallback", "conversation_guard"],
    "phase_2": ["tone_analysis", "response_variations", "personalization"],
    "phase_3": ["lead_scoring", "circular_flow", "objection_handler", "cta_generator", "dynamic_cta_fallback"],
    "phase_4": ["intent_disambiguation", "cascade_classifier", "semantic_objection_detection"],
    "safe": ["response_variations", "multi_tier_fallback", "structured_logging", "metrics_tracking", "conversation_guard", "cascade_classifier", "semantic_objection_detection"],
    "risky": ["circular_flow", "lead_scoring"],
    "context_phase_0": ["context_full_envelope", "context_shadow_mode"],
    "context_phase_3": ["context_policy_overlays", "context_engagement_v2"],
    "phase_5_tone": ["cascade_tone_analyzer", "tone_semantic_tier2", "tone_llm_tier3"],
    "tone_full": ["cascade_tone_analyzer", "tone_semantic_tier2", "tone_llm_tier3"],
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
from feature_flags import flags

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

### Порядок включения

1. **Фаза 0** — включить сразу (безопасно)
2. **Фаза 1** — включить сразу (критично для надёжности)
3. **Фаза 2** — включить `response_variations`, затем `cascade_tone_analyzer`
4. **Фаза 4** — включить `cascade_classifier` (улучшает классификацию)
5. **Фаза 5** — включить `context_full_envelope` и `context_policy_overlays`
6. **Фаза 3** — включать по одной фиче после калибровки

### Откат

При проблемах:

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
