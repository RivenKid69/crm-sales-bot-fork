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
from logger import get_logger, LogContext

logger = get_logger(__name__)

# Обычное логирование
logger.info("Обработка сообщения", user_id="123", message="привет")

# Контекстное логирование
with LogContext(conversation_id="conv_123", spin_phase="situation"):
    logger.info("Переход в фазу problem")
```

**Режимы:**
- **JSON** (production) — структурированные логи для ELK/Loki
- **Readable** (development) — человекочитаемый формат

### metrics.py — Трекинг метрик

```python
from metrics import MetricsTracker

tracker = MetricsTracker()

# Начало диалога
tracker.start_conversation("conv_123")

# Трекинг событий
tracker.track_intent("price_question")
tracker.track_state_transition("greeting", "spin_situation")
tracker.track_response_time(1.5)

# Завершение
tracker.end_conversation("conv_123", outcome="success")

# Получение статистики
stats = tracker.get_stats()
# {
#     "total_conversations": 100,
#     "success_rate": 0.65,
#     "avg_turns": 8.5,
#     "avg_response_time": 1.2
# }
```

### feature_flags.py — Управление фичами

```python
from feature_flags import is_enabled, get_all_flags, FeatureFlags

# Проверка флага
if is_enabled("tone_analysis"):
    # использовать ToneAnalyzer

# Все флаги
flags = get_all_flags()

# Декоратор
@FeatureFlags.require("lead_scoring")
def calculate_score(data):
    # выполнится только если lead_scoring включён
    pass
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
Уровень 2: Company Facts
    │       Общие факты о компании
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

try:
    response = llm.generate(prompt)
except Exception as e:
    response = handler.get_fallback(
        action="answer_question",
        context={"user_message": "сколько стоит?"},
        error=e
    )
```

### conversation_guard.py — Защита от зацикливания

```python
from conversation_guard import ConversationGuard

guard = ConversationGuard(
    max_turns=50,
    max_same_state=5,
    loop_detection_window=10
)

# Проверка перед обработкой
if guard.should_stop(conversation_history):
    return "Извините, давайте начнём сначала."

# Обновление после хода
guard.update(
    state="spin_situation",
    intent="situation_provided",
    response="Понял, 10 человек."
)

# Детекция зацикливания
if guard.detect_loop():
    guard.break_loop()  # Форсированный переход
```

---

## Фаза 2: Естественность диалога

**Цель:** Сделать общение более человечным.

### Компоненты

| Модуль | Флаг | Описание |
|--------|------|----------|
| `tone_analyzer.py` | `tone_analysis` | Анализ тона клиента |
| `response_variations.py` | `response_variations` | Вариативность ответов |

### tone_analyzer.py — Анализ тона

```python
from tone_analyzer import ToneAnalyzer

analyzer = ToneAnalyzer()

result = analyzer.analyze("Это слишком дорого, не интересует")
# {
#     "sentiment": "negative",
#     "frustration": 0.7,
#     "urgency": 0.3,
#     "interest": 0.2,
#     "recommended_tone": "empathetic"
# }

# Адаптация ответа под тон
if result["frustration"] > 0.5:
    prompt += "\n\nКлиент раздражён. Будь особенно вежлив и лаконичен."
```

**Анализируемые параметры:**
- `sentiment` — позитивный/негативный/нейтральный
- `frustration` — уровень раздражения (0-1)
- `urgency` — срочность (0-1)
- `interest` — заинтересованность (0-1)

### response_variations.py — Вариативность ответов

```python
from response_variations import ResponseVariations

variations = ResponseVariations()

# Получить вариацию приветствия
greeting = variations.get("greeting")
# "Здравствуйте!" / "Добрый день!" / "Привет!"

# С учётом истории (не повторяться)
greeting = variations.get("greeting", history=["Здравствуйте!"])
# Вернёт другой вариант

# Кастомные вариации
variations.add("spin_situation", [
    "Расскажите о вашей компании",
    "Сколько человек работает?",
    "Чем занимается ваш бизнес?"
])
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
from lead_scoring import LeadScorer, LeadCategory

scorer = LeadScorer()

# Расчёт скора
score = scorer.calculate(
    collected_data={
        "company_size": 10,
        "pain_point": "теряем клиентов",
        "current_tools": "Excel"
    },
    conversation_history=history,
    intents=["situation_provided", "problem_revealed"]
)
# {
#     "score": 75,
#     "category": LeadCategory.WARM,
#     "factors": {
#         "company_size": +10,
#         "pain_expressed": +20,
#         "current_tools_weak": +15,
#         "engagement": +30
#     },
#     "recommendation": "Переходить к презентации"
# }

# Категории
if score["category"] == LeadCategory.HOT:
    # Агрессивный close
elif score["category"] == LeadCategory.WARM:
    # Стандартный flow
else:
    # Nurturing
```

**Факторы скоринга:**
- Размер компании (+5..+20)
- Выраженность боли (+10..+30)
- Слабость текущих инструментов (+10..+20)
- Вовлечённость в диалог (+5..+30)
- Интент high_interest (+25)

### objection_handler.py — Обработка возражений

```python
from objection_handler import ObjectionHandler

handler = ObjectionHandler()

# Классификация возражения
objection = handler.classify("Это слишком дорого для нас")
# {
#     "type": "price",
#     "intensity": 0.8,
#     "subtype": "budget_constraint"
# }

# Получение стратегии
strategy = handler.get_strategy(objection, context)
# {
#     "approach": "value_reframe",
#     "points": [
#         "Подсчитайте потери от текущих проблем",
#         "Wipon окупается за 2-3 месяца",
#         "Есть рассрочка до 12 месяцев"
#     ],
#     "prompt_modifier": "Фокус на ROI и рассрочку"
# }

# Генерация ответа
response = handler.generate_response(objection, strategy, llm)
```

**Типы возражений:**
- `price` — дорого
- `time` — нет времени
- `competitor` — уже есть решение
- `authority` — не принимаю решения
- `need` — не нужно
- `trust` — не доверяю

### cta_generator.py — Call-to-Action

```python
from cta_generator import CTAGenerator

generator = CTAGenerator()

# Генерация CTA
cta = generator.generate(
    state="presentation",
    collected_data=data,
    lead_score=75
)
# {
#     "primary": "Давайте запишу вас на демо?",
#     "secondary": "Или могу отправить презентацию на почту",
#     "urgency": "Сейчас действует скидка 20%"
# }

# Адаптивный CTA
cta = generator.adaptive(
    previous_ctas=["демо", "презентация"],
    response_to_previous="нет"
)
# Предложит что-то другое
```

---

## Фаза 4: Intent Disambiguation

**Цель:** Уточнять намерение пользователя при неоднозначных ответах.

### Компоненты

| Модуль | Флаг | Описание |
|--------|------|----------|
| `classifier/` | `intent_disambiguation` | Уточнение при близких scores |

### Функциональность

При нескольких интентах с близкими scores система может:
1. Запросить уточнение у пользователя
2. Использовать контекст для disambiguition
3. Применить более сложную классификацию

---

## Фаза 5: Dynamic CTA Fallback

**Цель:** Контекстно-зависимые подсказки в fallback_tier_2 на основе собранных данных.

### Компоненты

| Модуль | Флаг | Описание |
|--------|------|----------|
| `fallback_handler.py` | `dynamic_cta_fallback` | Динамические подсказки |
| `data_extractor.py` | — | Категоризация боли (pain_category) |

### DYNAMIC_CTA_OPTIONS

8 типов контекстных подсказок с приоритетами:

```python
DYNAMIC_CTA_OPTIONS = {
    "competitor_mentioned": {      # Приоритет 10
        "options": ["Сравнить с {competitor}", "Узнать отличия", ...],
        "priority": 10
    },
    "pain_losing_clients": {       # Приоритет 8
        "options": ["Как Wipon помогает удерживать клиентов", ...],
        "priority": 8
    },
    "pain_no_control": {           # Приоритет 8
        "options": ["Какие отчёты есть в Wipon", ...],
        "priority": 8
    },
    "pain_manual_work": {          # Приоритет 8
        "options": ["Что можно автоматизировать", ...],
        "priority": 8
    },
    "after_price_question": {      # Приоритет 7
        "options": ["Узнать про рассрочку", "Что входит в тариф", ...],
        "priority": 7
    },
    "after_features_question": {   # Приоритет 7
        "options": ["Записаться на демо", "Какие интеграции есть", ...],
        "priority": 7
    },
    "large_company": {             # Приоритет 5 (>20 сотрудников)
        "options": ["Enterprise возможности", "Мультифилиальность", ...],
        "priority": 5
    },
    "small_company": {             # Приоритет 5 (≤5 сотрудников)
        "options": ["Базовый тариф", "Быстрый старт", ...],
        "priority": 5
    }
}
```

### Категоризация боли (pain_category)

DataExtractor автоматически определяет категорию боли по ключевым словам:

```python
PAIN_CATEGORY_KEYWORDS = {
    "losing_clients": ["теря", "клиент", "отток", "упуска", "продаж", ...],
    "no_control": ["контрол", "вид", "прозрачн", "хаос", "статистик", ...],
    "manual_work": ["excel", "рутин", "вручную", "времен", "дубл", ...]
}
```

Пример:
```python
extractor = DataExtractor()
result = extractor.extract("Мы теряем клиентов")
# result: {"pain_point": "потеря клиентов", "pain_category": "losing_clients"}
```

### Использование

```python
from fallback_handler import FallbackHandler

handler = FallbackHandler()
context = {
    "collected_data": {
        "competitor_mentioned": True,
        "competitor_name": "Битрикс",
        "pain_category": "losing_clients"
    },
    "last_intent": "price_question"
}

response = handler.get_fallback("fallback_tier_2", "spin_problem", context)
# Вернёт подсказки про сравнение с Битрикс (приоритет 10)
```

---

## Статус фаз

| Фаза | Компонент | Флаг | Статус |
|------|-----------|------|--------|
| 0 | Логирование | `structured_logging` | ✅ Production |
| 0 | Метрики | `metrics_tracking` | ✅ Production |
| 1 | Fallback | `multi_tier_fallback` | ✅ Production |
| 1 | Guard | `conversation_guard` | ✅ Production |
| 2 | Тон | `tone_analysis` | ⏸️ Testing |
| 2 | Вариации | `response_variations` | ✅ Production |
| 2 | Персонализация | `personalization` | ⏸️ Development |
| 3 | Скоринг | `lead_scoring` | ⏸️ Calibration |
| 3 | Circular flow | `circular_flow` | ⏸️ Risky |
| 3 | Возражения | `objection_handler` | ⏸️ Testing |
| 3 | CTA | `cta_generator` | ⏸️ Development |
| 4 | Disambig | `intent_disambiguation` | ⏸️ Development |
| 5 | Dynamic CTA | `dynamic_cta_fallback` | ⏸️ Testing |

**Легенда:**
- ✅ Production — включено в production
- ⏸️ Testing — в тестировании
- ⏸️ Development — в разработке
- ⏸️ Calibration — требует калибровки
- ⏸️ Risky — потенциально опасно

## Включение фаз

### Через settings.yaml

```yaml
feature_flags:
  # Включить фазу 2 полностью
  tone_analysis: true
  response_variations: true
  personalization: true

  # Включить фазу 3 полностью
  lead_scoring: true
  objection_handler: true
  cta_generator: true
```

### Через переменные окружения

```bash
# Включить отдельные фичи
FF_TONE_ANALYSIS=true \
FF_LEAD_SCORING=true \
python bot.py
```

### В коде

```python
from feature_flags import is_enabled

# Условное использование
if is_enabled("tone_analysis"):
    from tone_analyzer import ToneAnalyzer
    analyzer = ToneAnalyzer()
    tone = analyzer.analyze(message)
```

## Тестирование фаз

```bash
# Тесты фазы 0
pytest tests/test_logger.py tests/test_metrics.py tests/test_feature_flags.py -v

# Тесты фазы 1
pytest tests/test_fallback_handler.py tests/test_conversation_guard.py -v

# Тесты фазы 2
pytest tests/test_tone_analyzer.py tests/test_response_variations.py -v
pytest tests/test_phase2_integration.py -v

# Тесты фазы 3
pytest tests/test_lead_scoring.py tests/test_objection_handler.py tests/test_cta_generator.py -v
pytest tests/test_phase3_integration.py -v

# Интеграционные тесты всех фаз
pytest tests/test_phase4_integration.py -v
```

## Рекомендации по внедрению

### Порядок включения

1. **Фаза 0** — включить сразу (безопасно)
2. **Фаза 1** — включить сразу (критично для надёжности)
3. **Фаза 2** — включить `response_variations`, затем `tone_analysis`
4. **Фаза 3** — включать по одной фиче после калибровки

### Мониторинг при включении

При включении новой фичи отслеживайте:

```python
# Метрики для мониторинга
metrics.track("feature_enabled", feature="tone_analysis")
metrics.track("feature_error_rate", feature="tone_analysis", rate=0.01)
metrics.track("feature_latency", feature="tone_analysis", ms=50)
```

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
