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

---

## 3) Конфиг‑схема rules / transitions (Hybrid schema)

Ссылка на полное описание: `docs/ARCHITECTURE_HYBRID.md`.

### 3.1 Формат rules (action)

`RuleValue`:
- `"action"` — простое правило (legacy)
- `("condition_name", "action")` — одно условие
- `[("cond1","action1"), ("cond2","action2"), "default_action"]` — цепочка условий, порядок = приоритет, последний `str` = default

Пример (переписано из `Новая архитектура.txt` на hybrid‑формат):

```python
SPIN_COMMON_RULES = {
    "price_question": [
        ("has_pricing_data", "answer_with_facts"),     # если знаем размер/объём
        ("price_repeated_3x", "answer_with_price_range"),
        "deflect_and_continue",
    ],
}
```

### 3.2 Формат transitions (state)

`TransitionValue`:
- `"next_state"` — простой переход (legacy)
- `("condition_name", "next_state")` — одно условие
- `[("cond","next_state"), None]` — если не сработало, остаться в текущем состоянии (`None`)

Пример:

```python
"demo_request": [
    ("has_contact_info", "success"),
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
    ("has_pricing_data", "answer_with_facts"),
    "deflect_and_continue",
]
```

### 5.2 Эскалация при повторных вопросах о цене

```python
"price_question": [
    ("has_pricing_data", "answer_with_facts"),        # приоритет 1
    ("price_repeated_3x", "answer_with_price_range"), # приоритет 2
    "deflect_and_continue",
]
```

### 5.3 Умная обработка возражения о цене (action) + управляемый переход (transition)

Action (в состоянии обработки возражений):
```python
"objection_price": [
    ("has_pain_and_company_size", "handle_price_with_roi"),
    ("has_company_size", "handle_price_with_comparison"),
    "handle_price_objection_generic",
]
```

Transition (пример лимита возражений):
```python
"objection_price": [
    ("objection_limit_reached", "soft_close"),
    None,
]
```

### 5.4 Технические вопросы с эскалацией

```python
"question_technical": [
    ("technical_question_repeated_2x", "offer_documentation_link"),
    "answer_technical",
]
```

### 5.5 Условный переход demo_request → success только при наличии контакта

```python
"demo_request": [
    ("has_contact_info", "success"),
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
- unit: `RuleResolver._evaluate_rule()` (simple/tuple/list/default/None)
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
