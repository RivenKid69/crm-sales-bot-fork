# Conditional Rules — единый master‑план (Hybrid‑first)

Этот документ объединяет:
- `Новая архитектура.txt` (черновик/идеи/примеры/логирование)
- `docs/ARCHITECTURE_HYBRID.md` (источник истины по инженерным решениям)

**Правило конфликтов:** если форматы/решения расходятся — выбираем подход из `docs/ARCHITECTURE_HYBRID.md`.

---

## 1) Цель и границы

**Цель:** добавить условную логику в `rules` и `transitions` без “костылей” в `src/state_machine.py`, сохранив:
- читаемость поведения из `src/config.py`;
- тестируемость условий изолированно;
- дебажность (трассировка “почему выбрали action/transition”);
- обратную совместимость (старые `intent: "action"` продолжают работать).

**Граница ответственности:**
- `rules` выбирают **action** (что делать)
- `transitions` выбирают **state** (куда перейти)
- условия — это **Python‑функции** (типизированные, отлаживаемые), а конфиг лишь **ссылается на них по имени**

### 1.1 Текущее состояние (как работает сейчас)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           ТЕКУЩАЯ АРХИТЕКТУРА                               │
└─────────────────────────────────────────────────────────────────────────────┘

                              config.py
                    ┌─────────────────────────┐
                    │  SALES_STATES = {       │
                    │    "spin_situation": {  │
                    │      "rules": {         │
                    │        "price_question":│──────► "deflect_and_continue"
                    │        "greeting":      │──────► "acknowledge"
                    │        "rejection":     │──────► "handle_rejection"
                    │      }                  │            │
                    │    }                    │            │
                    │  }                      │            │
                    └─────────────────────────┘            │
                                                          │
                                                          ▼
                              state_machine.py            │
                    ┌─────────────────────────┐           │
                    │  def apply_rules():     │           │
                    │                         │           │
                    │    rule = rules[intent] │◄──────────┘
                    │    return rule, state   │  ← Просто возвращает строку
                    │                         │    Никакой логики!
                    └─────────────────────────┘
```

**Ключевой момент:** исторически `rules` — это просто строки: `intent -> action`.

### 1.2 Почему это ломается (пример: price_question)

**Бизнес‑требование:** “Если спросили цену **и** мы уже знаем размер команды — ответить. Если не знаем — уточнить размер.”

```
                    ┌─────────────────────────────────────────┐
                    │  Клиент: "Сколько стоит?"               │
                    └─────────────────────────────────────────┘
                                       │
                                       ▼
                    ┌─────────────────────────────────────────┐
                    │  intent = "price_question"              │
                    │  rule = "deflect_and_continue"          │
                    └─────────────────────────────────────────┘
                                       │
                       ┌───────────────┴───────────────┐
                       ▼                               ▼
              Данных НЕТ                        Данные ЕСТЬ
              collected_data = {}               collected_data = {
                                                  company_size: 10
                                                }
                       │                               │
                       ▼                               ▼
              deflect_and_continue              deflect_and_continue
              "Сколько человек?"                "Сколько человек?"
                     ✓                                 ✗
              ПРАВИЛЬНО                         НЕПРАВИЛЬНО!
                                                Должен ответить на цену
```

### 1.3 Почему “костыли в коде” — тупиковый путь

| Проблема | Описание |
|---|---|
| Hardcoded | Каждое условие = новый `if` в коде |
| Не масштабируется | 10 условий = 10 `if`’ов |
| Логика размазана | Часть в `config.py`, часть в `state_machine.py` |
| Сложно тестировать | Нужно поднимать весь SM, чтобы проверить условие |
| Сложно понимать | Чтобы узнать поведение, приходится читать код |

### 1.4 Выявленные кейсы, где нужны условия (минимальный список)

| № | Интент | Условие | Результат |
|---:|---|---|---|
| 1 | `price_question` | есть `company_size/users_count` | `answer_with_facts` (action) |
| 2 | `price_question` | повторился 3+ раз | `answer_with_range` (action) |
| 3 | `pricing_details` | есть `company_size` | `answer_with_facts` (action) |
| 4 | `comparison` | известен конкурент | `compare_specific` (action) |
| 5 | `objection_price` | есть `pain_point + company_size` | `handle_with_roi` (action) |
| 6 | `question_technical` | повторился 2+ раз | `offer_documentation` (action) |
| 7 | `demo_request` | в фазе `close` | `success` (transition) |

---

## 2) Ключевые архитектурные решения (приоритет: Hybrid)

1) **Условия = Python**  
   Типизированные функции + реестры условий вместо JSON/DSL‑интерпретатора.

2) **Правила = декларативный маппинг** в `src/config.py`  
   Конфиг задаёт только “условие → результат”, не реализует логику.

3) **Домены = изоляция**  
   Для разных подсистем разные контексты и реестры условий:
   - `state_machine` (rules/transitions)
   - `policy` (DialoguePolicy)
   - `fallback` (FallbackHandler)
   - `personalization` (PersonalizationEngine/CTA)

4) **Type safety**  
   `ConditionRegistry[TContext]` + контексты‑dataclass’ы; mypy (если включён) ловит несовместимости.

5) **Обратная совместимость**  
   Старый формат `intent: "action"` остаётся валидным.

### 2.1 Принципы (короткая версия таблицы из Hybrid)

| Принцип | Что это значит на практике |
|---|---|
| Условия = Python | логика проверок — в функциях, с типами/дебагом/тестами |
| Правила = декларативно | `config.py` описывает “когда → что” без `if` в SM |
| Домены = изоляция | отдельные реестры/контексты для SM/policy/fallback/personalization |
| rules ≠ transitions | правила выбирают action; переходы выбирают state |
| Type safety | реестры типизированы: `ConditionRegistry[TContext]` |
| Open‑Closed | новый домен = новый реестр, без правок старых |
| Backward compatible | строки‑rules и строки‑transitions продолжают работать |

---

## 3) Конфиг‑схема rules / transitions (Hybrid schema)

Ссылка на полное описание: `docs/ARCHITECTURE_HYBRID.md`.

### 3.1 Формат rules (action)

`RuleValue`:
- `"action"` — простое правило (legacy)
- `{"when": "condition_name", "then": "action"}` — одно условие
- `[{...}, {...}, "default_action"]` — цепочка условий, порядок = приоритет, последний `str` = default

**Почему dict, а не tuple:**
- Именованные поля — не надо помнить порядок
- Легко расширять (добавить `priority`, `description`, `disabled`)
- Лучше читается в конфиге

Пример (переписано из `Новая архитектура.txt` на hybrid‑формат):

```python
SPIN_COMMON_RULES = {
    "price_question": [
        {"when": "has_pricing_data", "then": "answer_with_facts"},     # если знаем размер/объём
        {"when": "price_repeated_3x", "then": "answer_with_price_range"},
        "deflect_and_continue",  # default
    ],
}
```

### 3.2 Формат transitions (state)

`TransitionValue`:
- `"next_state"` — простой переход (legacy)
- `{"when": "condition_name", "then": "next_state"}` — одно условие
- `[{...}, None]` — если не сработало, остаться в текущем состоянии (`None`)

Пример:

```python
"demo_request": [
    {"when": "has_contact_info", "then": "success"},
    None,  # иначе остаёмся в текущем состоянии
]
```

---

## 4) Основные компоненты (что добавляем/рефакторим)

Состав и контракты приведены в `docs/ARCHITECTURE_HYBRID.md`; здесь — “скелет” системы и точки интеграции с текущим кодом.

### 4.0 Целевая структура файлов (ориентир)

```text
src/
  conditions/
    base.py
    registry.py
    trace.py
    shared/
      __init__.py
    state_machine/
      __init__.py
      context.py
      registry.py
      conditions.py
    policy/
      __init__.py
      context.py
      registry.py
      conditions.py
    fallback/
      __init__.py
      context.py
      registry.py
      conditions.py
    personalization/
      __init__.py
      context.py
      registry.py
      conditions.py
    __init__.py
  rules/
    __init__.py
    resolver.py
  intent_tracker.py
  state_machine.py
  config.py
```

### 4.1 Conditions layer

- `src/conditions/base.py` — `BaseContext` (общий контракт)
- `src/conditions/registry.py` — `ConditionRegistry[TContext]`, декораторы регистрации, валидация
- `src/conditions/trace.py` — `EvaluationTrace` и `TraceCollector` (трассировка для симуляций/дебага)
- `src/conditions/<domain>/context.py` — типизированный контекст домена
- `src/conditions/<domain>/registry.py` — доменный реестр + декоратор
- `src/conditions/<domain>/conditions.py` — функции условий
- `src/conditions/shared/` — общие условия над `BaseContext`
- `src/conditions/__init__.py` — агрегатор `ConditionRegistries` (валидация/доки/статистика)

### 4.2 IntentTracker

- `src/intent_tracker.py` — единый источник истории интентов:
  - streak (подряд)
  - totals (например, возражения)
  - сериализация для контекста/логов
  - контракт: `record()` вызывается в начале `apply_rules()` **до** вычисления условий

### 4.3 RuleResolver

- `src/rules/resolver.py` — разрешение `rules` и `transitions` через доменный реестр, с опциональной трассировкой:
  - `resolve_action(state.rules → global_rules → continue_current_goal)`
  - `resolve_transition(state.transitions → None)`
  - `validate_config()` (неизвестные условия/состояния)

### 4.4 StateMachine integration

- `src/state_machine.py` — упрощение `apply_rules()` до пайплайна:
  1) hooks: `intent_tracker.record()`
  2) build context
  3) early exits (final/rejection/go_back)
  4) resolver: action + transition
  5) вернуть `RuleResult(action, next_state, trace)`

### 4.5 Остальные домены

- `src/dialogue_policy.py` → домен `policy`
- `src/fallback_handler.py` → домен `fallback`
- `src/cta_generator.py` / персонализация → домен `personalization`

---

## 5) Примеры применения (из .txt, адаптировано под Hybrid)

### 5.1 Price Question (фикс текущего бага без костылей в SM)

```python
"price_question": [
    {"when": "has_pricing_data", "then": "answer_with_facts"},
    "deflect_and_continue",
]
```

### 5.2 Эскалация при повторных вопросах о цене

```python
"price_question": [
    {"when": "has_pricing_data", "then": "answer_with_facts"},        # приоритет 1
    {"when": "price_repeated_3x", "then": "answer_with_price_range"}, # приоритет 2
    "deflect_and_continue",
]
```

### 5.3 Умная обработка возражения о цене (action) + управляемый переход (transition)

Action (в состоянии обработки возражений):
```python
"objection_price": [
    {"when": "has_pain_and_company_size", "then": "handle_price_with_roi"},
    {"when": "has_company_size", "then": "handle_price_with_comparison"},
    "handle_price_objection_generic",
]
```

Transition (пример лимита возражений):
```python
"objection_price": [
    {"when": "objection_limit_reached", "then": "soft_close"},
    None,
]
```

### 5.4 Технические вопросы с эскалацией

```python
"question_technical": [
    {"when": "technical_question_repeated_2x", "then": "offer_documentation_link"},
    "answer_technical",
]
```

### 5.5 Условный переход demo_request → success только при наличии контакта

```python
"demo_request": [
    {"when": "has_contact_info", "then": "success"},
    None,
]
```

---

## 6) Наблюдаемость и симуляции (объединение Hybrid trace + идеи из .txt)

`docs/ARCHITECTURE_HYBRID.md` уже задаёт `EvaluationTrace`/`TraceCollector` и `RuleResult(trace=...)`.  
Из `Новая архитектура.txt` добавляем требования к уровням и формату вывода в отчёте симуляций.

### 6.1 Уровни логирования

Используем существующий `src/logger.py`:
- `DEBUG` — детали проверок условий (какие условия/какой результат/какой контекст)
- `INFO` — финальные решения (action/transition/matched condition)
- `WARNING` — fallback на default/нет правила/условия не сработали
- `EVENT` — бизнес‑события (например, “conditional_rule_triggered”, “state_transition”)
- `METRIC` — числовые метрики (например, `conditions_checked`, `evaluation_time_ms`)

### 6.2 Что и где логируем (минимальный обязательный набор)

- В `RuleResolver`:
  - начало разрешения правила (intent/state/type)
  - результат (simple/condition_matched/default/fallback)
  - метрики: количество проверок, время (если измеряем)
- В `StateMachine`:
  - state_transition (EVENT): `from_state`, `to_state`, `intent`, `reason`
- В `SimulationRunner`:
  - сохранять `trace.to_compact_string()` в `turn_data` для каждого хода

### 6.3 Формат в отчёте симуляций (как в .txt)

Расширяем `src/simulator/report.py` так, чтобы для каждого хода печаталась строка:
- `"[RULE] simple → action"`
- `"[RULE] conditional → MATCHED"` / `DEFAULT`
- детали проверенных условий (только для conditional)

Цель: при 50+ симуляциях “почему выбрали action/state” видно прямо в секции диалога, без дебага кода.

### 6.4 Настройки детализации (как в .txt, через settings)

Рекомендованные ключи (ориентир), чтобы управлять объёмом логов без правок кода:

```yaml
# settings.yaml
logging:
  level: INFO
  conditional_rules:
    enabled: true
    level: DEBUG
    log_context: true
    log_each_condition: true
```

Опционально — переменная окружения: `CONDITIONAL_RULES_LOG_LEVEL=DEBUG`.

---

## 7) Миграция и обратная совместимость

1) **Форматы legacy остаются валидны**  
   - `rules[intent] = "action"`  
   - `transitions[intent] = "next_state"`

2) **Миграция по одному правилу**  
   Можно переводить только проблемные интенты (например `price_question`), не трогая остальные.

3) **Постепенное включение доменов**  
   Сначала StateMachine (rules/transitions), затем policy/fallback/personalization.

4) **Валидация на старте/в CI**  
   `validate_config()` (неизвестные условия/состояния) + `ConditionRegistries.validate_all()`.

---

## 8) Ожидаемые результаты (из .txt, совместимо с Hybrid)

| Аспект | До | После |
|---|---|---|
| Где живёт условная логика | `config.py` + костыли в коде | только `config.py` + условия (Python) |
| Добавить условие | писать `if` в `StateMachine` | добавить/переиспользовать условие и сослаться в config |
| Понять поведение | читать `StateMachine` | читать `SALES_CONFIG` |
| Тестировать условие | поднимать SM/интеграцию | unit‑тестировать функцию условия и resolver |
| “Почему выбрали action/state?” | вручную дебажить | `EvaluationTrace` + отчёт симуляций с `[RULE] ...` |

---

## 9) Поэтапный план внедрения (конкретные этапы)

Ниже — “PR‑friendly” этапы. Каждый этап завершается тестами и измеримым результатом.

### Этап 1 — Foundation: базовые контракты + реестр + трассировка

**Цель:** создать инфраструктуру условий без изменения бизнес‑логики.

**Сделать:**
- `src/conditions/base.py`: `BaseContext`
- `src/conditions/registry.py`: `ConditionRegistry`, регистрация, ошибки, `validate_all()`
- `src/conditions/trace.py`: `EvaluationTrace`, `TraceCollector`, `to_dict()`, `to_compact_string()`
- `src/conditions/shared/`: базовые shared‑условия над `BaseContext`

**Тесты:**
- unit: реестр (регистрация/перезапись/валидация/ошибки)
- unit: трассировка (record/set_result/format)

**Готово когда:**
- можно зарегистрировать 2–3 условия и прогнать `validate_all()` на тестовом контексте
- `TraceCollector.get_summary()` отдаёт агрегаты

---

### Этап 2 — StateMachine домен: контекст + набор условий

**Цель:** подготовить условия именно для `StateMachine` (rules/transitions).

**Сделать:**
- `src/conditions/state_machine/context.py`: `EvaluatorContext.from_state_machine(...)`
- `src/conditions/state_machine/registry.py`: `sm_registry`, декоратор `@sm_condition`
- `src/conditions/state_machine/conditions.py`: минимальный набор условий, покрывающий:
  - data: `has_pricing_data`, `has_contact_info`, `missing_required_data`
  - intent/counter: `price_repeated_3x`, `technical_question_repeated_2x`, `objection_limit_reached`
  - state: `in_spin_phase`, `is_spin_state`, etc.

**Тесты:**
- unit: каждое условие в изоляции (через `create_sm_test_context` / фабрику)

**Готово когда:**
- есть условия для ключевых сценариев из раздела 5

---

### Этап 3 — IntentTracker + RuleResolver (ядро условных правил)

**Цель:** научиться разрешать action/transition через условия и конфиг.

**Сделать:**
- `src/intent_tracker.py`: `IntentTracker` + сериализация
- `src/rules/resolver.py`: `RuleResolver`, `RuleResult(trace=...)`, `validate_config()`
- обновить/зафиксировать `src/config.py`:
  - `INTENT_CATEGORIES`
  - `SPIN_COMMON_RULES`, `POST_SPIN_RULES`
  - `SALES_CONFIG` со слоями `state.rules → global_rules`

**Тесты:**
- unit: `IntentTracker` (streak/objections/reset/serialизация)
- unit: `RuleResolver._evaluate_rule()` (simple/dict/list/default/None)
- unit: `validate_config()` (unknown conditions / unknown targets)

**Готово когда:**
- `RuleResolver` возвращает ожидаемые action/transition для 5.1–5.5 сценариев на синтетическом контексте

---

### Этап 4 — Интеграция в `StateMachine` + удаление дублирования

**Цель:** убрать костыли и дубли, включить новый pipeline в прод‑коде.

**Сделать:**
- рефактор `src/state_machine.py`:
  - hooks: `intent_tracker.record()`
  - context build: `EvaluatorContext.from_state_machine(...)`
  - `RuleResolver.resolve_action/resolve_transition`
  - возврат `RuleResult` (tuple‑unpacking совместимость)
- удалить дублирующие источники:
  - `last_intent` в нескольких местах → только `IntentTracker`
  - заменить/удалить `ObjectionFlowManager` (если есть) → методы `IntentTracker`
- обновить `src/bot.py` и `src/context_envelope.py` под новый источник данных (tracker/trace)

**Тесты:**
- интеграционные: `apply_rules()` на реальном конфиге
- регрессионные: основные диалоги/переходы SPIN не сломаны

**Готово когда:**
- `price_question` работает без спец‑if в `state_machine.py`
- старый код, который делает `action, state = apply_rules(...)`, продолжает работать

---

### Этап 5 — DialoguePolicy домен

**Цель:** вынести policy‑условия из hardcoded if’ов в доменные условия.

**Сделать:**
- `src/conditions/policy/*` (контекст/реестр/условия)
- рефактор `src/dialogue_policy.py` на декларативное применение policy‑условий

**Тесты:**
- unit: policy‑условия
- интеграционные: политика не деградирует на типовых сценариях (stuck/oscillation/breakthrough)

---

### Этап 6 — Fallback домен

**Цель:** сделать fallback управляемым условиями и наблюдаемым.

**Сделать:**
- `src/conditions/fallback/*`
- рефактор `src/fallback_handler.py`
- добавить метрики/события (`logger.metric`, `logger.event`) для fallback‑решений

**Тесты:**
- unit: fallback‑условия
- интеграционные: fallback tiers срабатывают ожидаемо

---

### Этап 7 — Personalization домен

**Цель:** перенести персонализацию/CTA на условия (там где применимо).

**Сделать:**
- `src/conditions/personalization/*`
- интеграция с `src/cta_generator.py` (или текущим компонентом персонализации)

**Тесты:**
- unit: personalization‑условия
- интеграционные: CTA/тональность не деградируют в ключевых сценариях

---

### Этап 8 — Tooling + CI + симуляции с трассировкой

**Цель:** сделать систему поддерживаемой: валидация, доки, отчёты, наблюдаемость.

**Сделать:**
- скрипт валидации (например `scripts/validate_conditions.py`):
  - `ConditionRegistries.validate_all()`
  - `RuleResolver.validate_config()`
- генератор документации условий (опционально): `ConditionRegistries.generate_documentation()`
- интеграция трассировки в симуляции:
  - `src/simulator/runner.py`: сохранять trace/compact rule info в `turn_data`
  - `src/simulator/report.py`: печатать `[RULE] ...` блоки как в разделе 6.3
- настройки логирования для conditional rules через `src/settings.py` (флаг/уровень/детализация)

**Готово когда:**
- CI падает на неизвестных условиях/битом конфиге
- отчёт симуляций показывает “почему выбрали action/state” на каждом ходе

---

## 10) Что из `Новая архитектура.txt` считается “черновиком” (и как маппится на Hybrid)

В `.txt` предлагался MongoDB‑style DSL (`$has_any`, `$and`, `$ref`, sugar/operators).  
В Hybrid это заменено на **именованные Python‑условия** в реестрах.

Практическое соответствие:
- `$has_any: ["company_size", "users_count"]` → `has_pricing_data(ctx)` / `has_company_size(ctx)` и т.п.
- `$intent_streak: 3` → `price_repeated_3x(ctx)` (через `IntentTracker`)
- `$objections: 3` → `objection_limit_reached(ctx)` (через `IntentTracker` + `INTENT_CATEGORIES`)

Если когда‑то понадобится DSL, его можно добавить как отдельный слой поверх реестров, но **не блокировать текущую реализацию**.

Также из `.txt` были предложены отдельные модули под DSL:
- `src/condition_evaluator.py` → в Hybrid заменён на `src/conditions/*` (Python‑условия + реестры), без общего DSL‑evaluator.
- `src/rule_validator.py` → в Hybrid заменён на `RuleResolver.validate_config()` + `ConditionRegistries.validate_all()`.
- `RuleLogger`/`rule_info` → в Hybrid основной механизм — `EvaluationTrace`/`TraceCollector`; при необходимости `rule_info` генерируется из `trace`.

---

## Appendix A) Контракты и интерфейсы (чтобы не потерять детали при реализации)

### A.1 BaseContext (общий контракт)

Минимальный набор полей, доступных во всех доменах условий:
- `collected_data: Dict[str, Any]`
- `state: str`
- `turn_number: int`

### A.2 ConditionRegistry (реестр условий)

**Назначение:** типобезопасная регистрация/валидация/выполнение условий домена.

Обязательные элементы (из `docs/ARCHITECTURE_HYBRID.md`):
- `ConditionMetadata`: `name`, `description`, `func(ctx)->bool`, `context_type`, `requires_fields`, `category`
- `ConditionRegistry[TContext]`:
  - `condition(name, description="", requires_fields=set(), category="general")` — декоратор регистрации
  - `evaluate(name, ctx, trace=None) -> bool` — выполняет условие и (опционально) пишет в `EvaluationTrace`
  - `validate_all(ctx_factory) -> {passed, failed, errors}` — рантайм‑валидация условий (полезно для CI)
  - `list_all()`, `list_by_category()`, `get_categories()`, `get_documentation()`
- Ошибки:
  - `ConditionNotFoundError` — неизвестное имя условия
  - `ConditionEvaluationError` — исключение внутри условия

### A.3 EvaluationTrace / TraceCollector (трассировка)

**Задача:** объяснить “почему выбран action/state” в симуляциях и дебаге, не залезая в код.

Минимальные требования к API:
- `EvaluationTrace.record(condition_name, result, ctx, relevant_fields=set())`
- `EvaluationTrace.set_result(final_action, resolution, matched_condition=None)`
- `EvaluationTrace.to_dict()` (для JSON/хранения)
- `EvaluationTrace.to_compact_string()` (для отчётов симуляций: блок `[RULE] ...`)
- `TraceCollector.create_trace(rule_name, intent, state, domain="")`
- `TraceCollector.get_summary()` (агрегаты по батчу симуляций)

### A.4 IntentTracker (единый источник истории интентов)

**Контракт timing:** `record(intent, state)` вызывается в самом начале `StateMachine.apply_rules()` — до вычисления условий.

Минимальные методы (из Hybrid):
- `record(intent, state)`
- `last_intent`, `prev_intent`
- `streak_count()` / хранение текущего streak
- `objection_consecutive()` и `objection_total()` (замена ObjectionFlowManager)
- `to_dict()` (для envelope/логов), `reset()`

### A.5 RuleResolver / RuleResult

**RuleResolver:**
- `resolve_action(intent, state, ctx, trace=None) -> action`
  1) `state.rules[intent]`
  2) `global_rules[intent]`
  3) fallback: `"continue_current_goal"`
- `resolve_transition(intent, state, ctx, trace=None) -> Optional[next_state]`
  - если правило отсутствует → `None` (остаться в текущем состоянии)
- `validate_config()`:
  - неизвестные условия
  - неизвестные target‑состояния в transitions

**RuleResult (возвращаемое значение `StateMachine.apply_rules()`):**
- поля: `action: str`, `next_state: Optional[str]`, `trace: Optional[EvaluationTrace]`
- поддержка tuple‑unpacking через `__iter__` (backward compatibility)

### A.6 Доменные контексты (минимальный состав полей)

Нужны, чтобы “не размывать” ответственность и не пытаться сделать один evaluator на всё.

- `EvaluatorContext` (StateMachine):
  - Base: `collected_data`, `state`, `turn_number`
  - SM‑specific: `spin_phase`, `is_spin_state`, `current_intent`, `prev_intent`, `intent_tracker`, `missing_required_data`
- `PolicyContext` (DialoguePolicy):
  - Base: `collected_data`, `state`, `turn_number`
  - Policy‑specific: `oscillation_detected`, `confidence_trend`, `momentum_direction`, `turns_in_state`, `breakthrough_detected`, `turns_since_breakthrough`, `total_objections`, `repeated_objection_types`, `current_action`, `frustration_level`
- `FallbackContext` (FallbackHandler):
  - Base: `collected_data`, `state`, `turn_number`
  - Fallback‑specific: `total_fallbacks`, `consecutive_fallbacks`, `current_tier`, `fallbacks_in_state`, `last_successful_intent`
  - Signals: `frustration_level`, `momentum_direction`, `engagement_level`
  - Data: `pain_category`, `competitor_mentioned`, `last_intent`
- `PersonalizationContext` (PersonalizationEngine):
  - Base: `collected_data`, `state`, `turn_number`
  - Company: `company_size`, `role`, `industry`
  - Pain: `pain_category`, `pain_point`, `current_crm`
  - Signals: `has_breakthrough`, `engagement_level`, `objection_type`

### A.7 Агрегатор реестров (валидация/доки/статистика)

`ConditionRegistries` (из Hybrid) — единая точка для:
- `validate_all()` (прогнать все условия на тест‑контекстах)
- `get_stats()` (сколько условий/категорий по доменам)
- `generate_documentation()` (автоген доки по условиям)

---

## Appendix B) Симуляции и логи: как переносится секция 7 из `Новая архитектура.txt`

### B.1 Уровни (соответствуют текущему `src/logger.py`)

- `DEBUG` — детали вычисления условий
- `INFO` — финальные решения
- `WARNING` — default/fallback (условия не сработали или rule отсутствует)
- `EVENT` — бизнес‑события аналитики
- `METRIC` — числовые метрики

### B.2 Формат `[RULE] ...` в отчёте (совместимо с Hybrid)

Hybrid уже даёт `EvaluationTrace.to_compact_string()`. В симуляциях достаточно:
- записывать `trace.to_compact_string()` в `turn_data` (runner)
- печатать в `_section_full_dialogues()` (report)

### B.3 Что именно переносим из идеи `rule_info` (и как маппится на trace)

В `.txt` предлагалась структура `rule_info` с:
- `rule_type` / `resolution` / `matched_index`
- `conditions_evaluated[]` (type/params/result/details)

В Hybrid это выражается через:
- `trace.resolution` (`simple` / `condition_matched` / `default` / `fallback` / …)
- `trace.matched_condition`
- `trace.entries[]` (условие + результат + context snapshot)

Если нужно 1‑в‑1 совместимое поле `rule_info` для отчётов — его можно **производить из trace** без второго источника истины.

### B.4 События и метрики (EVENT/METRIC)

Примерный минимум (из `.txt`, адаптировано под `src/logger.py`):
- `logger.event("conditional_rule_triggered", intent=..., action=..., matched_condition=...)`
- `logger.event("conditional_rule_default_used", intent=..., action=..., reason=...)`
- `logger.metric("condition_evaluation", conditions_checked=..., evaluation_time_ms=..., intent=...)`
- `logger.metric("conditional_rules_stats", total_evaluations=..., conditions_matched=..., defaults_used=..., batch_id=...)`

### B.5 RuleLogger (идея из .txt) — опционально

В `.txt` предлагалась обёртка `RuleLogger` для удобного логирования conditional rules.

В текущем проекте уже есть `src/logger.py` (структурированный логгер с `event()` и `metric()`), поэтому:
- либо логируем напрямую через `logger.*`;
- либо делаем тонкую обёртку `RuleLogger`, но без “второго источника истины”: вся диагностика строится вокруг `EvaluationTrace`.

---

## Appendix C) Решённые проблемы и сравнение подходов (из Hybrid, без потери)

### C.1 Решённые проблемы

| # | Проблема | Решение (Hybrid) |
|---:|---|---|
| 1 | JSON DSL без типов | Python‑функции с `@condition` |
| 2 | Единый evaluator для всех контекстов (SRP) | доменные реестры |
| 3 | Open‑Closed нарушен | новый домен = новый реестр |
| 4 | Type safety отсутствует | `Generic[TContext]`, mypy |
| 5 | Условия смешиваются | изоляция по доменам |
| 6 | Hardcoded `OBJECTION_INTENTS` | `INTENT_CATEGORIES` |
| 7 | `last_intent` в 4+ местах | `IntentTracker` |
| 8 | `ObjectionFlowManager` | `IntentTracker.objection_*()` |
| 9 | Runtime ошибки | валидация на старте/в CI |
| 10 | Сложно дебажить | breakpoints + stack traces + `EvaluationTrace` |

### C.2 Сравнение подходов

| Аспект | Один evaluator/DSL | Hybrid: доменные реестры |
|---|---|---|
| SRP | нарушен | соблюдён |
| Type safety | в основном runtime | compile‑time (mypy) + контексты |
| Open‑Closed | нужно менять evaluator | добавляем новый домен |
| Изоляция | всё в одном месте | по доменам |
| IDE support | слабый | полный |
| Тестирование | сложнее | проще и изолированно |

---

## Appendix D) Проверка покрытия “по очереди” (что куда перенесено)

### D.1 `docs/ARCHITECTURE_HYBRID.md` → `docs/ARCHITECTURE_UNIFIED_PLAN.md`

| Hybrid секция | Где в unified |
|---|---|
| Часть 1: текущее состояние | `docs/ARCHITECTURE_UNIFIED_PLAN.md` → раздел 1.1–1.4 |
| Часть 2: цель/принципы | раздел 1–2 |
| Часть 3: schema/контракты | раздел 3 + Appendix A |
| Часть 4: домены | раздел 4–5 + этапы 2/5/6/7 |
| Часть 5–6: shared + агрегатор | раздел 4.1 + этапы 1/8 + Appendix A |
| Часть 7: IntentTracker | раздел 4.2 + этап 3 + Appendix A |
| Часть 8: RuleResolver | раздел 4.3 + этап 3 + Appendix A |
| Часть 9: StateMachine | раздел 4.4 + этап 4 |
| Часть 10: конфигурация | раздел 3/5/7 + этап 3 |
| Часть 11: структура файлов | раздел 4.0 |
| Часть 12: план реализации | раздел 9 |
| Часть 13: резюме | Appendix C |

### D.2 `Новая архитектура.txt` → `docs/ARCHITECTURE_UNIFIED_PLAN.md`

| .txt секция | Где в unified |
|---|---|
| Часть 1–2 (контекст/цель) | раздел 1–2 |
| Часть 3.1 (schema) | раздел 3 |
| Часть 3.2 (MongoDB DSL) | **Удалён** — заменён на Python‑условия (раздел 10) |
| Часть 3.3–3.7 (порядок/шаринг/hooks/tracker) | раздел 4 + Appendix A |
| Часть 4 (примеры) | раздел 5 |
| Часть 5 (план) | раздел 9 (PR‑friendly этапы) |
| Часть 6 (ожидаемые результаты) | раздел 8 |
| Часть 7 (логирование симуляций) | раздел 6 + Appendix B |
| Часть 8 (резюме) | раздел 8 + Appendix C |
