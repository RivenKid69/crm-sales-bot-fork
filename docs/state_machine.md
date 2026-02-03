# State Machine - Полная Документация

> **Версия документации:** 3.2 (v2.0 Domain-Independent)
> **Последнее обновление:** Январь 2026
> **Основной файл:** `src/state_machine.py`

---

## ВАЖНО: Архитектура v2.0

**С января 2026** StateMachine использует исключительно YAML-конфигурацию и стал **domain-independent**.
- Все константы в `constants.yaml` (single source of truth)
- Выбор flow через `settings.yaml` (`flow.active`)
- Нет hardcoded SPIN логики — платформа универсальная
- Legacy Python constants (`SPIN_PHASES`, `SPIN_STATES`, `SALES_STATES`) **deprecated**.

### Быстрый старт v2.0

```python
from state_machine import StateMachine

# v2.0: Автоматически загружает config и flow из YAML
# Flow определяется в settings.yaml: flow.active = "spin_selling"
sm = StateMachine()

# Конфигурация доступна через свойства
print(sm.phase_order)      # ['situation', 'problem', 'implication', 'need_payoff']
print(sm.states_config)    # Dict из flows/spin_selling/states.yaml
```

### Выбор flow

```yaml
# settings.yaml
flow:
  active: "spin_selling"  # Можно заменить на другой flow
```

Доступные flows находятся в `src/yaml_config/flows/`.

### Миграция импортов

```python
# Старый способ (не работает в v2.0)
from state_machine import SPIN_PHASES, SPIN_STATES

# Новый способ
from src.yaml_config.constants import SPIN_PHASES, SPIN_STATES
```

---

## Содержание

1. [Обзор и Архитектура](#1-обзор-и-архитектура)
2. [Основные Классы](#2-основные-классы)
3. [SPIN Selling Flow](#3-spin-selling-flow)
4. [Система Приоритетов](#4-система-приоритетов)
5. [Условные Правила (Conditional Rules)](#5-условные-правила-conditional-rules)
6. [IntentTracker](#6-intenttracker)
7. [YAML Конфигурация](#7-yaml-конфигурация)
8. [Условия (Conditions)](#8-условия-conditions)
9. [Примеры Использования](#9-примеры-использования)
10. [Диаграммы и Схемы](#10-диаграммы-и-схемы)
11. [Тестирование](#11-тестирование)
12. [FAQ и Troubleshooting](#12-faq-и-troubleshooting)
13. [DAG State Machine](#13-dag-state-machine) NEW

---

## 1. Обзор и Архитектура

### 1.1 Что такое State Machine?

State Machine (конечный автомат) — это ядро диалоговой системы CRM Sales Bot. Он управляет:

- **Состояниями диалога** (greeting, spin_situation, close и др.)
- **Переходами** между состояниями на основе интентов
- **Правилами** обработки интентов внутри состояний
- **Сбором данных** о клиенте в процессе диалога

### 1.2 Архитектурные принципы

```
┌─────────────────────────────────────────────────────────────────┐
│                        State Machine                             │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────────┐ │
│  │IntentTracker│───▶│EvaluatorCtx │───▶│   RuleResolver      │ │
│  │ (история)   │    │ (контекст)  │    │ (правила+условия)   │ │
│  └─────────────┘    └─────────────┘    └─────────────────────┘ │
│         │                  │                      │             │
│         ▼                  ▼                      ▼             │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │                    apply_rules()                            ││
│  │  Priority 0: Final State                                    ││
│  │  Priority 1: Rejection                                      ││
│  │  Priority 1.5: Go Back                                      ││
│  │  Priority 1.7: Objection Limits                             ││
│  │  Priority 2: State Rules                                    ││
│  │  Priority 3: Question Handler                               ││
│  │  Priority 4: SPIN Phase Progress                            ││
│  │  Priority 5: Transitions                                    ││
│  │  Priority 6-8: Auto-transitions, Default                    ││
│  └─────────────────────────────────────────────────────────────┘│
│                           │                                      │
│                           ▼                                      │
│                  (action, next_state)                            │
└─────────────────────────────────────────────────────────────────┘
```

### 1.3 Ключевые компоненты

| Компонент | Файл | Назначение |
|-----------|------|------------|
| `StateMachine` | `src/state_machine.py` | Главный класс управления состояниями |
| `IntentTracker` | `src/intent_tracker.py` | Отслеживание истории интентов |
| `RuleResolver` | `src/rules/resolver.py` | Разрешение условных правил |
| `EvaluatorContext` | `src/conditions/state_machine/context.py` | Контекст для условий |
| `ConditionRegistry` | `src/conditions/state_machine/registry.py` | Реестр условий |
| `CircularFlowManager` | `src/state_machine.py` | Управление возвратами назад |
| `ConfigLoader` | `src/config_loader.py` | Загрузка YAML конфигурации |

### 1.4 Фазы разработки

Система разрабатывалась в несколько фаз:

- **Phase 1**: Базовая параметризация через YAML
- **Phase 2**: Условия для StateMachine domain
- **Phase 3**: IntentTracker + RuleResolver
- **Phase 4**: Полная интеграция, приоритеты
- **Phase 5**: Context-aware условия через ContextEnvelope

---

## 2. Основные Классы

### 2.1 Класс `StateMachine`

Главный класс системы, управляющий диалогом.

```python
from src.state_machine import StateMachine

# Базовое создание
sm = StateMachine()

# С конфигурацией
from src.config_loader import ConfigLoader
loader = ConfigLoader("src/yaml_config")
config = loader.load()
sm = StateMachine(config=config, enable_tracing=True)

# С модульным flow
flow = config.load_flow("spin_selling")
sm = StateMachine(config=config, flow=flow)
```

#### Конструктор

```python
def __init__(
    self,
    enable_tracing: bool = False,    # Включить трассировку для отладки
    config: LoadedConfig = None,      # Конфигурация из YAML
    flow: FlowConfig = None           # Модульный flow
)
```

#### Основные атрибуты

| Атрибут | Тип | Описание |
|---------|-----|----------|
| `state` | `str` | Текущее состояние (по умолчанию `"greeting"`) |
| `collected_data` | `Dict` | Собранные данные о клиенте |
| `spin_phase` | `Optional[str]` | Текущая SPIN фаза |
| `intent_tracker` | `IntentTracker` | Трекер истории интентов |
| `circular_flow` | `CircularFlowManager` | Менеджер возвратов назад |

#### Ключевые методы

##### `apply_rules(intent, context_envelope=None) -> Tuple[str, str]`

**Главный метод** — определяет действие и следующее состояние.

```python
action, next_state = sm.apply_rules("price_question")
# action = "deflect_and_continue"
# next_state = "spin_situation"
```

**Порядок приоритетов обработки:**

| Приоритет | Название | Описание |
|-----------|----------|----------|
| 0 | Final State | Проверка финального состояния |
| 1 | Rejection | Критический интент отказа |
| 1.5 | Go Back | Возврат назад по фазам |
| 1.7 | Objection Limits | Лимиты возражений |
| 2 | State Rules | Правила текущего состояния |
| 3 | Question Handler | Обработка вопросов |
| 4 | SPIN Progress | Прогресс по SPIN фазам |
| 5 | Transitions | Переходы по интенту |
| 6 | Data Complete | Автопереход при сборе данных |
| 7 | Any Transition | Автопереход (для greeting) |
| 8 | Default | Оставаться в текущем состоянии |

##### `process(intent, extracted_data=None, context_envelope=None) -> Dict`

Обрабатывает интент и возвращает полный результат.

```python
result = sm.process("info_provided", {"company_size": 50})
print(result)
# {
#     "action": "transition_to_spin_problem",
#     "prev_state": "spin_situation",
#     "next_state": "spin_problem",
#     "goal": "Выявить проблемы и боли клиента",
#     "collected_data": {"company_size": 50},
#     "missing_data": ["pain_point"],
#     "optional_data": [],
#     "is_final": False,
#     "spin_phase": "problem",
#     "circular_flow": {...},
#     "objection_flow": {...}
# }
```

##### `reset()`

Сбрасывает состояние для нового разговора.

```python
sm.reset()
assert sm.state == "greeting"
assert sm.collected_data == {}
```

##### `update_data(data: Dict)`

Сохраняет извлечённые данные.

```python
sm.update_data({"company_size": 100, "pain_point": "теряем клиентов"})
```

##### `build_evaluator_context(intent: str) -> EvaluatorContext`

Строит контекст для внешних систем.

```python
ctx = sm.build_evaluator_context("price_question")
# Можно использовать для условий
```

#### Properties

| Property | Тип | Источник |
|----------|-----|----------|
| `max_consecutive_objections` | `int` | Config → константа (3) |
| `max_total_objections` | `int` | Config → константа (5) |
| `phase_order` | `List[str]` | Flow → Config → SPIN_PHASES |
| `phase_states` | `Dict[str, str]` | Flow → Config → SPIN_STATES |
| `progress_intents` | `Dict[str, str]` | Flow → Config |
| `states_config` | `Dict` | Flow → Config → SALES_STATES |
| `priorities` | `List[Dict]` | Flow (или пустой список) |
| `last_intent` | `Optional[str]` | IntentTracker |
| `turn_number` | `int` | IntentTracker |

---

### 2.2 Класс `RuleResult`

Результат разрешения правил с поддержкой tuple unpacking.

```python
from src.state_machine import RuleResult

# Создание
result = RuleResult(action="answer_with_facts", next_state="spin_situation")

# Tuple unpacking (обратная совместимость)
action, state = result

# Доступ к полям
print(result.action)      # "answer_with_facts"
print(result.next_state)  # "spin_situation"
print(result.trace)       # EvaluationTrace или None

# Конвертация в dict
print(result.to_dict())
```

---

### 2.3 Класс `CircularFlowManager`

Управляет возвратами назад с защитой от злоупотреблений.

```python
from src.state_machine import CircularFlowManager

manager = CircularFlowManager(
    allowed_gobacks={
        "spin_problem": "spin_situation",
        "spin_implication": "spin_problem",
        # ...
    },
    max_gobacks=2  # Максимум возвратов за диалог
)
```

#### Константы по умолчанию

```python
MAX_GOBACKS = 2  # Максимум возвратов за диалог

DEFAULT_ALLOWED_GOBACKS = {
    "spin_problem": "spin_situation",
    "spin_implication": "spin_problem",
    "spin_need_payoff": "spin_implication",
    "presentation": "spin_need_payoff",
    "close": "presentation",
    "handle_objection": "presentation",
    "soft_close": "greeting",  # Новая попытка
}
```

#### Методы

| Метод | Описание |
|-------|----------|
| `can_go_back(current_state)` | Проверить возможность возврата |
| `go_back(current_state)` | Выполнить возврат, вернуть предыдущее состояние |
| `get_remaining_gobacks()` | Оставшееся количество возвратов |
| `get_history()` | История возвратов |
| `get_stats()` | Статистика для аналитики |
| `reset()` | Сброс для нового разговора |

---

### 2.4 Класс `ObjectionFlowAdapter`

Адаптер для обратной совместимости со старым API ObjectionFlowManager.

```python
# Доступ через StateMachine
sm = StateMachine()
sm.apply_rules("objection_price")

# Старый API через адаптер
print(sm.objection_flow.objection_count)      # Подряд
print(sm.objection_flow.total_objections)     # Всего
print(sm.objection_flow.should_soft_close())  # Лимит достигнут?
```

---

## 3. SPIN Selling Flow

### 3.1 Что такое SPIN Selling?

SPIN Selling — методология продаж, разработанная Нилом Рэкхэмом. Аббревиатура расшифровывается как:

- **S**ituation — понять текущую ситуацию
- **P**roblem — выявить проблемы
- **I**mplication — показать последствия
- **N**eed-Payoff — сформировать ценность

### 3.2 Состояния и фазы

```
greeting → spin_situation → spin_problem → spin_implication → spin_need_payoff → presentation → close → success
                                                                                      ↓
                                                                              handle_objection
                                                                                      ↓
                                                                                 soft_close
```

| Состояние | SPIN Фаза | Цель | Обязательные данные |
|-----------|-----------|------|---------------------|
| `greeting` | — | Поздороваться | — |
| `spin_situation` | Situation | Понять ситуацию | `company_size` |
| `spin_problem` | Problem | Выявить проблемы | `pain_point` |
| `spin_implication` | Implication | Показать последствия | `implication_probed` |
| `spin_need_payoff` | Need-Payoff | Сформировать ценность | `need_payoff_probed` |
| `presentation` | — | Показать продукт | — |
| `handle_objection` | — | Отработать возражение | — |
| `close` | — | Взять контакт | `contact_info` |
| `success` | — | Успех | — |
| `soft_close` | — | Мягкое завершение | — |

### 3.3 Переходы между состояниями

Переходы определяются:

1. **Явным интентом** — клиент говорит что-то конкретное
2. **Автопереходом** — собраны все обязательные данные (`data_complete`)
3. **Прогресс-интентом** — информация соответствует следующей фазе

```yaml
# Пример из sales_flow.yaml
spin_situation:
  transitions:
    data_complete: spin_problem        # Автопереход
    situation_provided: spin_problem   # Прогресс-интент
    demo_request: close                # Клиент хочет демо
    rejection: soft_close              # Отказ
```

### 3.4 Прогресс-интенты

Интенты, указывающие на готовность к следующей фазе:

| Интент | Указывает на фазу |
|--------|-------------------|
| `situation_provided` | Situation завершена |
| `problem_revealed` | Problem завершена |
| `implication_acknowledged` | Implication завершена |
| `need_expressed` | Need-Payoff завершена |

### 3.5 Пропуск фаз

Фазы можно пропустить при определённых условиях:

```python
def _should_skip_phase(self, phase: str) -> bool:
    # При высоком интересе — пропустить I и N
    if phase in ["implication", "need_payoff"]:
        if self.collected_data.get("high_interest"):
            return True
        if phase == "need_payoff" and self.collected_data.get("desired_outcome"):
            return True
    return False
```

---

## 4. Система Приоритетов

### 4.1 Hardcoded приоритеты (Legacy)

По умолчанию используются приоритеты, зашитые в `apply_rules()`:

```
Приоритет 0: Финальное состояние
    ↓
Приоритет 1: Rejection
    ↓
Приоритет 1.5: Go Back (если circular_flow включён)
    ↓
Приоритет 1.7: Objection Limits
    ↓
Приоритет 2: State-specific Rules
    ↓
Приоритет 3: Question Handler
    ↓
Приоритет 4: SPIN Phase Progress
    ↓
Приоритет 5: Transitions
    ↓
Приоритет 6: Data Complete
    ↓
Приоритет 7: Any Transition
    ↓
Приоритет 8: Default (continue_current_goal)
```

### 4.2 Конфигурируемые приоритеты (YAML)

При использовании FlowConfig можно настроить приоритеты через YAML:

```yaml
# src/yaml_config/flows/_base/priorities.yaml
default_priorities:
  - name: final_state
    priority: 0
    condition: is_final
    action: final

  - name: rejection
    priority: 100
    intents: [rejection]
    use_transitions: true

  - name: go_back
    priority: 150
    intents: [go_back, correct_info]
    feature_flag: circular_flow
    handler: circular_flow_handler

  - name: objection_limit
    priority: 170
    intent_category: objection
    condition: objection_limit_reached
    action: transition_to_soft_close
    else: use_transitions

  - name: state_rules
    priority: 200
    source: rules
    use_resolver: true

  - name: question_handling
    priority: 300
    intent_category: question
    default_action: answer_question
    use_transitions: true

  - name: phase_progress
    priority: 400
    handler: phase_progress_handler

  - name: transitions
    priority: 500
    use_transitions: true

  - name: default
    priority: 999
    action: continue_current_goal
```

### 4.3 Поля конфигурации приоритета

| Поле | Тип | Описание |
|------|-----|----------|
| `name` | `str` | Уникальное имя приоритета |
| `priority` | `int` | Числовой приоритет (меньше = раньше) |
| `intents` | `List[str]` | Список конкретных интентов |
| `intent_category` | `str` | Категория интентов |
| `condition` | `str` | Условие из registry |
| `feature_flag` | `str` | Feature flag |
| `trigger` | `str` | Специальный триггер (`data_complete`, `any`) |
| `action` | `str` | Действие при срабатывании |
| `handler` | `str` | Имя handler-метода |
| `use_transitions` | `bool` | Использовать transitions |
| `use_resolver` | `bool` | Использовать RuleResolver |
| `source` | `str` | Источник правил (`rules`) |
| `else` | `str` | Действие если условие не выполнено |

---

## 5. Условные Правила (Conditional Rules)

### 5.1 Форматы правил

#### Простой формат (строка)

```yaml
rules:
  greeting: greet_back
  unclear: ask_how_to_help
```

#### Условный формат (dict)

```yaml
rules:
  price_question:
    when: can_answer_price
    then: answer_with_facts
```

#### Цепочка правил (list)

```yaml
rules:
  price_question:
    - when: can_answer_price
      then: answer_with_facts
    - when: should_answer_directly
      then: answer_with_facts
    - deflect_and_continue  # Default (последний элемент)
```

#### Составные условия (AND/OR/NOT)

```yaml
rules:
  price_question:
    - when:
        and:
          - has_pricing_data
          - in_spin_phase
      then: answer_with_facts
    - when:
        or:
          - price_repeated_3x
          - client_frustrated
      then: answer_with_facts
    - when:
        not: in_early_conversation
      then: deflect_and_continue
    - deflect_and_continue
```

### 5.2 RuleResolver

`RuleResolver` разрешает условные правила:

```python
from src.rules.resolver import RuleResolver, create_resolver

# Создание
resolver = create_resolver()  # Использует sm_registry по умолчанию

# Разрешение действия
action = resolver.resolve_action(
    intent="price_question",
    state_rules={
        "price_question": [
            {"when": "has_pricing_data", "then": "answer_with_facts"},
            "deflect_and_continue"
        ]
    },
    global_rules={},
    ctx=evaluator_context,
    state="spin_situation"
)

# Разрешение перехода
next_state = resolver.resolve_transition(
    intent="rejection",
    transitions={"rejection": "soft_close"},
    ctx=evaluator_context,
    state="spin_situation"
)
```

### 5.3 Валидация конфигурации

```python
from src.rules.resolver import RuleResolver

resolver = RuleResolver(registry)

# Валидация всей конфигурации
result = resolver.validate_config(
    states_config=SALES_STATES,
    global_rules={},
    known_states={"greeting", "spin_situation", ...}
)

if not result.is_valid:
    for error in result.errors:
        print(f"Error in {error.state}/{error.rule_name}: {error.message}")
```

---

## 6. IntentTracker

### 6.1 Назначение

`IntentTracker` — единый источник истории интентов. Отслеживает:

- Текущий и предыдущий интент
- Streak (подряд идущие одинаковые интенты)
- Totals (общее количество по интентам и категориям)
- Категории интентов

### 6.2 Использование

```python
from src.intent_tracker import IntentTracker

tracker = IntentTracker()

# Запись интента (делается автоматически в apply_rules)
tracker.record("price_question", "spin_situation")
tracker.record("price_question", "spin_situation")

# Проверка streak
assert tracker.streak_count("price_question") == 2

# Проверка totals
assert tracker.total_count("price_question") == 2

# Категории
assert tracker.category_total("question") == 2
assert tracker.category_streak("question") == 2

# Свойства
print(tracker.last_intent)  # "price_question"
print(tracker.prev_intent)  # "price_question"
print(tracker.turn_number)  # 2

# Сериализация
print(tracker.to_dict())
print(tracker.to_compact_dict())
```

### 6.3 Категории интентов

```python
INTENT_CATEGORIES = {
    "objection": [
        "objection_price",
        "objection_competitor",
        "objection_no_time",
        "objection_think",
    ],
    "positive": [
        "agreement",
        "demo_request",
        "callback_request",
        "contact_provided",
        # ...
    ],
    "question": [
        "price_question",
        "pricing_details",
        "question_features",
        "question_integrations",
        "question_technical",
        "comparison",
    ],
    "spin_progress": [
        "situation_provided",
        "problem_revealed",
        "implication_acknowledged",
        "need_expressed",
    ],
    "negative": [
        "rejection",
        "farewell",
        # ... все objection интенты
    ],
}
```

### 6.4 Методы для возражений

Для обратной совместимости:

```python
# Вместо ObjectionFlowManager
tracker.objection_consecutive()  # Подряд идущие возражения
tracker.objection_total()        # Всего возражений

# Проверки категории
tracker.is_objection("objection_price")  # True
tracker.is_positive("agreement")          # True
tracker.is_question("price_question")     # True
```

---

## 7. YAML Конфигурация

### 7.1 Структура директории

```
src/
├── settings.yaml               # Настройки (flow.active выбирает flow)
└── yaml_config/
    ├── constants.yaml          # Единая точка истины для констант
    ├── constants.py            # Python-обёртка для constants.yaml
    ├── states/
    │   └── sales_flow.yaml     # Конфигурация состояний
    └── flows/
        ├── _base/
        │   ├── states.yaml     # Базовые состояния
        │   ├── priorities.yaml # Приоритеты обработки
        │   └── mixins.yaml     # Переиспользуемые блоки
        └── spin_selling/
            ├── flow.yaml       # Конфигурация flow
            └── states.yaml     # Состояния для SPIN
```

**Выбор flow в settings.yaml:**
```yaml
flow:
  active: "spin_selling"
```

### 7.2 constants.yaml

Единая точка истины для всех констант:

```yaml
# SPIN конфигурация
spin:
  phases:
    - situation
    - problem
    - implication
    - need_payoff
  states:
    situation: spin_situation
    problem: spin_problem
    implication: spin_implication
    need_payoff: spin_need_payoff
  progress_intents:
    situation_provided: situation
    problem_revealed: problem
    implication_acknowledged: implication
    need_expressed: need_payoff

# Лимиты
limits:
  max_consecutive_objections: 3
  max_total_objections: 5
  max_gobacks: 2

# Категории интентов
intents:
  go_back:
    - go_back
    - correct_info
  categories:
    objection: [objection_price, objection_competitor, ...]
    positive: [agreement, demo_request, ...]
    question: [price_question, question_features, ...]

# Circular Flow
circular_flow:
  allowed_gobacks:
    spin_problem: spin_situation
    spin_implication: spin_problem
    # ...
```

### 7.3 sales_flow.yaml

Конфигурация состояний:

```yaml
meta:
  version: "1.0"
  description: "SPIN Selling state machine"

defaults:
  default_action: continue_current_goal

states:
  greeting:
    goal: "Поздороваться и узнать чем помочь"
    required_data: []
    transitions:
      price_question: spin_situation
      demo_request: close
      rejection: soft_close
    rules:
      greeting: greet_back
      unclear: ask_how_to_help

  spin_situation:
    goal: "Понять текущую ситуацию клиента"
    spin_phase: situation
    required_data:
      - company_size
    optional_data:
      - current_tools
      - business_type
    transitions:
      data_complete: spin_problem
      situation_provided: spin_problem
      rejection: soft_close
    rules:
      price_question:
        - when: can_answer_price
          then: answer_with_facts
        - deflect_and_continue
      unclear:
        - when: client_stuck
          then: clarify_one_question
        - probe_situation
```

### 7.4 Mixins

Переиспользуемые блоки правил:

```yaml
# mixins.yaml
mixins:
  price_handling:
    description: "Правила для обработки вопросов о цене"
    rules:
      price_question:
        - when: can_answer_price
          then: answer_with_facts
        - "{{default_price_action}}"  # Параметр

  spin_common:
    description: "Общие правила для всех SPIN состояний"
    includes:  # Композиция mixins
      - price_handling
      - product_questions
      - objection_handling
      - dialogue_repair

defaults:
  default_price_action: deflect_and_continue
```

Использование в состоянии:

```yaml
states:
  spin_situation:
    mixins:
      - spin_common
    parameters:
      default_price_action: deflect_and_continue
```

### 7.5 Модульные Flow

```yaml
# flows/spin_selling/flow.yaml
meta:
  name: spin_selling
  version: "1.0"
  extends: _base

phases:
  order: [situation, problem, implication, need_payoff]
  mapping:
    situation: spin_situation
    problem: spin_problem
    implication: spin_implication
    need_payoff: spin_need_payoff
  post_phases_state: presentation

skip_conditions:
  implication:
    - has_high_interest
  need_payoff:
    - has_desired_outcome

priorities_profile: default_priorities
```

---

## 8. Условия (Conditions)

### 8.1 EvaluatorContext

Контекст для вычисления условий:

```python
from src.conditions.state_machine.context import EvaluatorContext

# Создание из StateMachine
ctx = EvaluatorContext.from_state_machine(
    state_machine=sm,
    current_intent="price_question",
    config=state_config,
    context_envelope=envelope  # Опционально
)

# Создание для тестов
ctx = EvaluatorContext.create_test_context(
    collected_data={"company_size": 50},
    state="spin_situation",
    turn_number=3,
    current_intent="price_question"
)
```

#### Поля EvaluatorContext

| Поле | Тип | Описание |
|------|-----|----------|
| `collected_data` | `Dict` | Собранные данные |
| `state` | `str` | Текущее состояние |
| `turn_number` | `int` | Номер хода |
| `spin_phase` | `Optional[str]` | SPIN фаза |
| `is_spin_state` | `bool` | В SPIN состоянии? |
| `current_intent` | `str` | Текущий интент |
| `intent_tracker` | `IntentTracker` | Трекер интентов |
| `missing_required_data` | `List[str]` | Недостающие данные |
| `frustration_level` | `int` | Уровень фрустрации (0-5) |
| `is_stuck` | `bool` | Диалог застрял? |
| `has_oscillation` | `bool` | Диалог осциллирует? |
| `momentum_direction` | `str` | Направление момента |
| `engagement_level` | `str` | Уровень вовлечённости |

### 8.2 Категории условий

#### Data Conditions

Проверка собранных данных:

| Условие | Описание |
|---------|----------|
| `has_pricing_data` | Есть company_size или users_count |
| `has_contact_info` | Есть email, phone или contact |
| `has_company_size` | Есть company_size |
| `has_pain_point` | Есть pain_point или pain_category |
| `has_pain_and_company_size` | Есть и боль, и размер |
| `has_competitor_mention` | Упомянут конкурент |
| `missing_required_data` | Есть недостающие данные |
| `has_all_required_data` | Все данные собраны |
| `has_high_interest` | Высокий интерес |
| `has_desired_outcome` | Известен желаемый результат |

#### Intent Conditions

Проверка истории интентов:

| Условие | Описание |
|---------|----------|
| `price_repeated_3x` | Вопрос о цене 3+ раза подряд |
| `price_repeated_2x` | Вопрос о цене 2+ раза подряд |
| `objection_limit_reached` | 3 подряд или 5 всего возражений |
| `objection_consecutive_3x` | 3+ возражения подряд |
| `objection_total_5x` | 5+ возражений всего |
| `is_current_intent_objection` | Текущий интент — возражение |
| `is_current_intent_positive` | Текущий интент — позитивный |
| `is_current_intent_question` | Текущий интент — вопрос |

#### State Conditions

Проверка состояния:

| Условие | Описание |
|---------|----------|
| `is_spin_state` | В SPIN состоянии |
| `in_situation_phase` | В фазе Situation |
| `in_problem_phase` | В фазе Problem |
| `in_implication_phase` | В фазе Implication |
| `in_need_payoff_phase` | В фазе Need-Payoff |
| `is_presentation_state` | В состоянии presentation |
| `is_close_state` | В состоянии close |
| `is_terminal_state` | В терминальном состоянии |

#### Context-Aware Conditions

Условия на основе ContextEnvelope:

| Условие | Описание |
|---------|----------|
| `client_frustrated` | Фрустрация >= 3 |
| `client_very_frustrated` | Фрустрация >= 4 |
| `client_stuck` | Диалог застрял |
| `client_oscillating` | Диалог осциллирует |
| `momentum_positive` | Позитивный момент |
| `momentum_negative` | Негативный момент |
| `engagement_high` | Высокая вовлечённость |
| `engagement_low` | Низкая вовлечённость |
| `needs_repair` | Нужен repair диалога |
| `should_answer_directly` | Нужно ответить напрямую |

#### Combined Conditions

Составные условия:

| Условие | Описание |
|---------|----------|
| `can_answer_price` | Можно ответить на вопрос о цене |
| `should_deflect_price` | Нужно отклонить вопрос о цене |
| `ready_for_presentation` | Готовы к презентации |
| `ready_for_close` | Готовы к закрытию |
| `can_handle_with_roi` | Можно ответить с ROI |

### 8.3 Регистрация условий

```python
from src.conditions.state_machine.registry import sm_condition

@sm_condition(
    "my_condition",
    description="Описание условия",
    requires_fields={"field1", "field2"},  # Документация
    category="data"
)
def my_condition(ctx: EvaluatorContext) -> bool:
    return ctx.collected_data.get("field1") is not None
```

### 8.4 Использование в YAML

```yaml
rules:
  price_question:
    # Простое условие
    - when: has_pricing_data
      then: answer_with_facts

    # Составное условие (AND)
    - when:
        and:
          - has_company_size
          - not: in_early_conversation
      then: answer_with_facts

    # Составное условие (OR)
    - when:
        or:
          - price_repeated_3x
          - client_frustrated
      then: answer_with_facts

    # Default
    - deflect_and_continue
```

---

## 9. Примеры Использования

### 9.1 Базовое использование

```python
from src.state_machine import StateMachine

# Создание
sm = StateMachine()

# Обработка диалога
tests = [
    ("greeting", {}),
    ("price_question", {}),
    ("info_provided", {"company_size": 15}),
    ("info_provided", {"pain_point": "теряем клиентов"}),
    ("agreement", {}),
]

for intent, data in tests:
    result = sm.process(intent, data)
    print(f"Intent: {intent}")
    print(f"  {result['prev_state']} → {result['next_state']}")
    print(f"  Action: {result['action']}")
    print()
```

### 9.2 С YAML конфигурацией

```python
from src.config_loader import ConfigLoader
from src.state_machine import StateMachine

# Загрузка конфигурации
loader = ConfigLoader("src/yaml_config")
config = loader.load()

# Создание с конфигурацией
sm = StateMachine(config=config, enable_tracing=True)

# Обработка
result = sm.apply_rules("price_question")
action, next_state = result

# Доступ к трассировке
trace = sm.get_last_trace()
if trace:
    print(trace.to_dict())
```

### 9.3 С модульным Flow

```python
from src.config_loader import ConfigLoader
from src.state_machine import StateMachine

loader = ConfigLoader("src/yaml_config")
config = loader.load()

# Загрузка flow
flow = config.load_flow("spin_selling")

# Создание с flow
sm = StateMachine(config=config, flow=flow)

# Теперь используются приоритеты из flow
print(sm.priorities)
```

### 9.4 С ContextEnvelope

```python
from src.state_machine import StateMachine
from src.context_envelope import ContextEnvelope

sm = StateMachine()

# Создание envelope с контекстными сигналами
envelope = ContextEnvelope(
    frustration_level=3,
    is_stuck=True,
    momentum_direction="negative"
)

# Передача в apply_rules
action, next_state = sm.apply_rules("price_question", context_envelope=envelope)
# При frustration_level >= 3 условие should_answer_directly = True
# Поэтому будет answer_with_facts вместо deflect_and_continue
```

### 9.5 Полный жизненный цикл диалога

```python
from src.state_machine import StateMachine

sm = StateMachine()

# 1. Greeting
result = sm.process("greeting", {})
# state: greeting → greeting, action: greet_back

# 2. Клиент спрашивает о цене
result = sm.process("price_question", {})
# state: greeting → spin_situation, action: deflect_and_continue

# 3. Клиент называет размер компании
result = sm.process("info_provided", {"company_size": 50})
# state: spin_situation → spin_problem, action: transition_to_spin_problem

# 4. Клиент называет проблему
result = sm.process("problem_revealed", {"pain_point": "теряем клиентов"})
# state: spin_problem → spin_implication, action: transition_to_spin_implication

# 5. Клиент понимает последствия
result = sm.process("implication_acknowledged", {})
# state: spin_implication → spin_need_payoff

# 6. Клиент понимает ценность
result = sm.process("need_expressed", {})
# state: spin_need_payoff → presentation

# 7. Клиент просит демо
result = sm.process("demo_request", {"contact_info": "+79001234567"})
# state: presentation → close

# 8. Контакт получен
result = sm.process("contact_provided", {})
# state: close → success
assert result["is_final"] == True
```

### 9.6 Обработка возражений

```python
sm = StateMachine()
sm.state = "presentation"

# Первое возражение
result = sm.process("objection_price", {})
# state: presentation → handle_objection

# Второе возражение
result = sm.process("objection_competitor", {})
# state: handle_objection → handle_objection

# Третье возражение подряд
result = sm.process("objection_think", {})
# state: handle_objection → soft_close
# Достигнут лимит 3 возражения подряд

assert result["action"] == "objection_limit_reached"
assert result["next_state"] == "soft_close"
```

### 9.7 Возврат назад (Go Back)

```python
from feature_flags import flags
flags.circular_flow = True  # Включить функцию

sm = StateMachine()
sm.state = "spin_problem"

# Клиент хочет вернуться
result = sm.process("go_back", {})
# state: spin_problem → spin_situation

# Можно вернуться ещё раз
sm.state = "spin_implication"
result = sm.process("go_back", {})
# state: spin_implication → spin_problem

# Третья попытка — лимит достигнут
sm.state = "spin_need_payoff"
result = sm.process("go_back", {})
# state остаётся spin_need_payoff, возврат невозможен
```

---

## 10. Диаграммы и Схемы

### 10.1 Диаграмма состояний

```
                            ┌──────────────┐
                            │   greeting   │
                            └──────┬───────┘
                                   │ any intent
                                   ▼
                         ┌──────────────────┐
                         │  spin_situation  │◄────┐
                         └────────┬─────────┘     │
                                  │ data_complete │
                                  ▼               │
                         ┌──────────────────┐     │
                         │   spin_problem   │─────┤ go_back
                         └────────┬─────────┘     │
                                  │ data_complete │
                                  ▼               │
                       ┌────────────────────┐     │
                       │ spin_implication   │─────┤
                       └────────┬───────────┘     │
                                │ data_complete   │
                                ▼                 │
                       ┌────────────────────┐     │
                       │  spin_need_payoff  │─────┘
                       └────────┬───────────┘
                                │ data_complete
                                ▼
                       ┌────────────────────┐
    objection ────────▶│    presentation    │◄───────┐
         │             └────────┬───────────┘        │
         │                      │ agreement          │
         ▼                      ▼                    │
┌─────────────────┐    ┌───────────────┐            │
│handle_objection │───▶│     close     │            │
└────────┬────────┘    └───────┬───────┘            │
         │                     │ contact_provided   │
         │ limit               ▼                    │
         │             ┌───────────────┐            │
         │             │    success    │ (is_final) │
         │             └───────────────┘            │
         │                                          │
         ▼                                          │
┌────────────────┐                                  │
│   soft_close   │──────────────────────────────────┘
└────────────────┘   agreement (новая попытка)
```

### 10.2 Диаграмма обработки apply_rules()

```
                     apply_rules(intent)
                            │
                            ▼
              ┌─────────────────────────────┐
              │ 1. Record intent in tracker │
              └──────────────┬──────────────┘
                             │
                             ▼
              ┌─────────────────────────────┐
              │ 2. Build EvaluatorContext   │
              └──────────────┬──────────────┘
                             │
                             ▼
              ┌─────────────────────────────┐
              │ 3. Create trace (if enabled)│
              └──────────────┬──────────────┘
                             │
            ┌────────────────┴────────────────┐
            │     Has FlowConfig + priorities? │
            └────────┬───────────────┬────────┘
                     │ YES           │ NO
                     ▼               ▼
      ┌──────────────────────┐ ┌──────────────────────┐
      │ Priority-driven loop │ │ Hardcoded priorities │
      │ (YAML configuration) │ │ (legacy approach)    │
      └──────────┬───────────┘ └──────────┬───────────┘
                 │                         │
                 └────────────┬────────────┘
                              │
                              ▼
                    ┌───────────────────┐
                    │ Return (action,   │
                    │         next_state)│
                    └───────────────────┘
```

### 10.3 Диаграмма компонентов

```
┌─────────────────────────────────────────────────────────────────┐
│                         StateMachine                             │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │                       Core State                             ││
│  │  • state: str                                               ││
│  │  • collected_data: Dict                                     ││
│  │  • spin_phase: str                                          ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                  │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
│  │  IntentTracker  │  │CircularFlowMgr  │  │  RuleResolver   │  │
│  │  • streaks      │  │  • goback_count │  │  • registry     │  │
│  │  • totals       │  │  • allowed      │  │  • evaluate     │  │
│  │  • history      │  │  • max_gobacks  │  │  • validate     │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘  │
│           │                    │                    │            │
│           └────────────────────┼────────────────────┘            │
│                                │                                 │
│                                ▼                                 │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │                      apply_rules()                          ││
│  │  Priority 0-8: Check conditions, resolve rules, transition  ││
│  └─────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                      External Components                         │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
│  │  ConfigLoader   │  │ConditionRegistry│  │EvaluatorContext │  │
│  │  • YAML files   │  │  • conditions   │  │  • data fields  │  │
│  │  • FlowConfig   │  │  • evaluate     │  │  • tracker refs │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 11. Тестирование

### 11.1 Основные тестовые файлы

| Файл | Описание |
|------|----------|
| `tests/test_state_machine_phase4.py` | Phase 4 интеграция |
| `tests/test_conditions_state_machine.py` | Все условия |
| `tests/test_state_machine_config.py` | ConfigLoader интеграция |
| `tests/test_intent_tracker.py` | IntentTracker |
| `tests/test_rules_resolver.py` | RuleResolver |

### 11.2 Примеры тестов

#### Тест IntentTracker интеграции

```python
def test_objection_counted_via_tracker(sm):
    """Objections should be counted via IntentTracker."""
    sm.apply_rules("objection_price")
    assert sm.intent_tracker.objection_total() == 1

def test_objection_limit_triggers_soft_close(sm):
    """Reaching objection limit should trigger soft_close."""
    objections = ["objection_price", "objection_competitor", "objection_think"]

    for intent in objections:
        action, next_state = sm.apply_rules(intent)

    assert action == "objection_limit_reached"
    assert next_state == "soft_close"
```

#### Тест условий

```python
def test_has_pricing_data(pricing_context):
    """Test has_pricing_data condition."""
    ctx = EvaluatorContext.create_test_context(
        collected_data={"company_size": 50}
    )
    assert has_pricing_data(ctx) == True

def test_can_answer_price():
    """Test can_answer_price composite condition."""
    ctx = EvaluatorContext.create_test_context(
        collected_data={"company_size": 50}
    )
    assert can_answer_price(ctx) == True
```

#### Тест конфигурации

```python
def test_state_machine_with_config(config_dir):
    """Test StateMachine uses config values."""
    loader = ConfigLoader(config_dir)
    config = loader.load()
    sm = StateMachine(config=config)

    # Проверить что лимиты из конфига
    assert sm.max_consecutive_objections == 3
    assert sm.max_total_objections == 5
```

### 11.3 Запуск тестов

```bash
# Все тесты state machine
pytest tests/test_state_machine*.py -v

# Тесты условий
pytest tests/test_conditions_state_machine.py -v

# С покрытием
pytest tests/test_state_machine*.py --cov=src/state_machine --cov-report=html
```

---

## 12. FAQ и Troubleshooting

### 12.1 Часто задаваемые вопросы

**Q: Как добавить новое состояние?**

A: Добавьте состояние в `src/yaml_config/states/sales_flow.yaml`:

```yaml
states:
  my_new_state:
    goal: "Описание цели"
    required_data:
      - some_field
    transitions:
      some_intent: next_state
      data_complete: another_state
    rules:
      some_intent: some_action
```

**Q: Как добавить новое условие?**

A: Создайте функцию в `src/conditions/state_machine/conditions.py`:

```python
@sm_condition(
    "my_condition",
    description="Описание",
    category="data"
)
def my_condition(ctx: EvaluatorContext) -> bool:
    return ctx.collected_data.get("my_field") is not None
```

**Q: Как изменить лимиты возражений?**

A: Измените в `src/yaml_config/constants.yaml`:

```yaml
limits:
  max_consecutive_objections: 4  # Было 3
  max_total_objections: 7        # Было 5
```

**Q: Как включить circular flow?**

A: Установите feature flag:

```python
from feature_flags import flags
flags.circular_flow = True
```

### 12.2 Troubleshooting

#### Проблема: Условие не срабатывает

1. Включите трассировку:
   ```python
   sm = StateMachine(enable_tracing=True)
   sm.apply_rules("price_question")
   print(sm.get_last_trace().to_dict())
   ```

2. Проверьте контекст:
   ```python
   ctx = sm.build_evaluator_context("price_question")
   print(ctx.to_dict())
   ```

3. Проверьте условие напрямую:
   ```python
   from src.conditions.state_machine.conditions import has_pricing_data
   print(has_pricing_data(ctx))
   ```

#### Проблема: Неожиданный переход

1. Проверьте порядок приоритетов — более высокий приоритет может перехватывать интент

2. Проверьте IntentTracker:
   ```python
   print(sm.intent_tracker.to_dict())
   ```

3. Проверьте transitions в конфигурации состояния

#### Проблема: Ошибка валидации YAML

1. Проверьте синтаксис YAML
2. Проверьте что все условия зарегистрированы:
   ```python
   from src.conditions.state_machine.registry import sm_registry
   print(sm_registry.list_all())
   ```

3. Запустите валидацию:
   ```python
   result = resolver.validate_config(states_config)
   for error in result.errors:
       print(error.to_dict())
   ```

---

## Приложение A: Полный список действий (Actions)

| Action | Описание |
|--------|----------|
| `greet_back` | Поздороваться в ответ |
| `continue_current_goal` | Продолжить текущую цель |
| `answer_question` | Ответить на вопрос |
| `answer_with_facts` | Ответить с фактами (для цены) |
| `answer_with_roi` | Ответить с ROI расчётом |
| `answer_and_continue` | Ответить и продолжить |
| `deflect_and_continue` | Отклонить и продолжить |
| `probe_situation` | Зондировать ситуацию |
| `probe_problem` | Зондировать проблему |
| `probe_implication` | Зондировать последствия |
| `probe_need_payoff` | Зондировать ценность |
| `clarify_one_question` | Уточнить один вопрос |
| `clarify_and_continue` | Уточнить и продолжить |
| `summarize_and_clarify` | Резюмировать и уточнить |
| `handle_objection` | Отработать возражение |
| `objection_limit_reached` | Достигнут лимит |
| `ask_how_to_help` | Спросить чем помочь |
| `acknowledge_and_continue` | Подтвердить и продолжить |
| `small_talk_and_continue` | Small talk и продолжить |
| `go_back` | Вернуться назад |
| `final` | Финальное состояние |
| `transition_to_{state}` | Переход в состояние |

---

## Приложение B: Полный список интентов

### Категория: Objection
- `objection_price` — возражение по цене
- `objection_competitor` — возражение про конкурента
- `objection_no_time` — нет времени
- `objection_think` — нужно подумать

### Категория: Positive
- `agreement` — согласие
- `demo_request` — запрос демо
- `callback_request` — запрос звонка
- `contact_provided` — контакт предоставлен
- `consultation_request` — запрос консультации
- `situation_provided` — ситуация описана
- `problem_revealed` — проблема выявлена
- `implication_acknowledged` — последствия поняты
- `need_expressed` — потребность выражена
- `info_provided` — информация предоставлена
- `gratitude` — благодарность
- `greeting` — приветствие

### Категория: Question
- `price_question` — вопрос о цене
- `pricing_details` — детали ценообразования
- `question_features` — вопрос о функциях
- `question_integrations` — вопрос об интеграциях
- `question_technical` — технический вопрос
- `comparison` — сравнение

### Категория: Negative
- `rejection` — отказ
- `farewell` — прощание

### Служебные
- `go_back` — вернуться назад
- `correct_info` — исправить информацию
- `unclear` — неясно

---

## 13. DAG State Machine

### 13.1 Что такое DAG State Machine?

DAG (Directed Acyclic Graph) — расширение линейной state machine, позволяющее создавать:

- **Условные ветвления (CHOICE)** — XOR выбор между путями
- **Параллельные потоки (FORK/JOIN)** — одновременное выполнение веток
- **Compound states (PARALLEL)** — вложенные параллельные регионы
- **History states** — сохранение состояния при прерываниях

```
                    ┌─────────────────────────────────────────────┐
                    │           DAG State Machine                  │
                    │                                              │
     LINEAR:        │    A ───► B ───► C ───► D                   │
                    │                                              │
     CHOICE (XOR):  │              ┌──► B ──┐                     │
                    │    A ────────┤        ├────► D              │
                    │              └──► C ──┘                     │
                    │                                              │
     FORK/JOIN:     │              ┌──► B ──┐                     │
                    │    A ────────┤        ├────► E              │
                    │      (fork)  └──► C ──┘  (join)             │
                    │              └──► D ──┘                     │
                    └─────────────────────────────────────────────┘
```

### 13.2 Компоненты DAG

| Компонент | Файл | Назначение |
|-----------|------|------------|
| `DAGExecutionContext` | `src/dag/models.py` | Контекст выполнения DAG (ветки, история) |
| `DAGExecutor` | `src/dag/executor.py` | Выполнение CHOICE, FORK, JOIN, PARALLEL |
| `BranchRouter` | `src/dag/branch_router.py` | Маршрутизация интентов между ветками |
| `SyncPointManager` | `src/dag/sync_points.py` | Синхронизация параллельных веток |
| `HistoryManager` | `src/dag/history.py` | История для прерванных диалогов |

### 13.3 Типы DAG узлов

```python
from src.dag import NodeType

class NodeType(Enum):
    SIMPLE = "simple"      # Обычное состояние
    CHOICE = "choice"      # Условное ветвление (XOR)
    FORK = "fork"          # Начало параллельного выполнения
    JOIN = "join"          # Синхронизация веток
    PARALLEL = "parallel"  # Compound state с регионами
```

### 13.4 YAML конфигурация DAG

#### CHOICE (условное ветвление)

```yaml
states:
  issue_classifier:
    type: choice
    goal: "Классификация типа обращения"
    choices:
      - condition: is_technical_issue
        next: technical_flow
      - condition: is_billing_issue
        next: billing_flow
      - condition: is_account_issue
        next: account_flow
    default: general_inquiry
```

#### FORK/JOIN (параллельные потоки)

```yaml
states:
  # FORK — запуск параллельных веток
  qualification_fork:
    type: fork
    goal: "Параллельная квалификация"
    branches:
      - id: budget_branch
        start_at: collect_budget
      - id: authority_branch
        start_at: identify_decision_maker
      - id: need_branch
        start_at: assess_needs
        condition: has_initial_interest  # Опциональная ветка
    join_at: qualification_complete
    join_condition: all_complete  # или any_complete, majority

  # JOIN — синхронизация веток
  qualification_complete:
    type: join
    goal: "Объединение результатов"
    expects_branches:
      - budget_branch
      - authority_branch
      - need_branch
    join_condition: all_complete
    on_join:
      action: analyze_qualification
    transitions:
      qualified: presentation
      not_qualified: nurture_flow
```

#### History States

```yaml
states:
  billing_flow:
    type: simple
    goal: "Обработка billing вопросов"
    history: shallow  # или deep
    transitions:
      refund_request: process_refund
      payment_failed: troubleshoot_payment
```

### 13.5 Использование DAG в коде

#### Инициализация DAG контекста

```python
from src.dag import DAGExecutionContext, DAGBranch, NodeType

# DAG контекст создаётся автоматически в StateMachine
sm = StateMachine()

# Проверка режима DAG
if sm.is_dag_mode:
    print(f"Active branches: {sm.active_branches}")
    print(f"DAG events: {len(sm.dag_events)}")
```

#### Работа с параллельными ветками

```python
from src.dag import BranchRouter

# Маршрутизация интентов
router = BranchRouter(sm.dag_context, strategy="round_robin")
result = router.route_intent("price_question")

if result.branch_id:
    print(f"Route to branch: {result.branch_id}")
    print(f"Current state: {result.state}")
```

#### Синхронизация веток

```python
from src.dag import SyncPointManager, SyncStrategy

sync_manager = SyncPointManager()

# Регистрация точки синхронизации
sync_manager.register_sync_point(
    "qualification_complete",
    required_branches=["budget", "authority", "need"],
    strategy=SyncStrategy.ALL_COMPLETE
)

# Проверка готовности
result = sync_manager.arrive("qualification_complete", "budget")
if result.is_complete:
    print("All branches complete!")
```

#### History States для прерываний

```python
from src.dag import HistoryManager, HistoryType

history = HistoryManager()

# Сохранить состояние при прерывании
history.save("booking_flow", "collect_date", data={"step": 1})

# ... пользователь спрашивает о ценах ...

# Восстановить состояние
state, data = history.restore_with_data("booking_flow")
# state = "collect_date", data = {"step": 1}
```

### 13.6 Стратегии синхронизации

| Стратегия | Описание |
|-----------|----------|
| `ALL_COMPLETE` | Ждать завершения всех веток |
| `ANY_COMPLETE` | Продолжить при завершении любой ветки |
| `MAJORITY` | Продолжить при завершении >50% веток |
| `N_OF_M` | Продолжить при завершении N из M веток |
| `TIMEOUT` | Продолжить по таймауту |

```yaml
# Пример с MAJORITY
states:
  parallel_diagnostics:
    type: join
    join_condition: majority
    expects_branches:
      - system_check
      - user_diagnostics
      - known_issues
```

### 13.7 Event Sourcing

DAG поддерживает event sourcing для отладки и replay:

```python
from src.dag import DAGEvent

# События записываются автоматически
for event in sm.dag_events:
    print(f"{event.timestamp}: {event.event_type}")
    print(f"  Branch: {event.branch_id}")
    print(f"  State: {event.from_state} → {event.to_state}")
    print(f"  Data: {event.data}")

# Сериализация для персистенции
events_json = [e.to_dict() for e in sm.dag_events]
```

### 13.8 Примеры Flow

#### BANT Qualification Flow

```yaml
# src/yaml_config/flows/examples/bant_flow.yaml
flow:
  name: bant_qualification
  description: "BANT квалификация с параллельным сбором данных"

states:
  bant_fork:
    type: fork
    branches:
      - id: budget
        start_at: collect_budget
      - id: authority
        start_at: identify_dm
      - id: need
        start_at: assess_need
      - id: timeline
        start_at: determine_timeline
    join_at: bant_complete

  bant_complete:
    type: join
    expects_branches: [budget, authority, need, timeline]
    join_condition: all_complete
    transitions:
      all_positive: presentation
      mixed: nurture
      all_negative: disqualify
```

#### Customer Support Flow

```yaml
# src/yaml_config/flows/examples/support_flow.yaml
flow:
  name: customer_support
  description: "Поддержка с DAG маршрутизацией"

states:
  issue_classifier:
    type: choice
    choices:
      - condition: is_technical_issue
        next: technical_flow
      - condition: is_billing_issue
        next: billing_flow
    default: general_inquiry

  technical_flow:
    type: fork
    branches:
      - id: system_check
        start_at: check_system_status
      - id: user_diagnostics
        start_at: collect_error_details
    join_at: technical_resolution
```

### 13.9 Тестирование DAG

```bash
# Запуск DAG тестов
pytest tests/test_dag.py -v

# Все 37 тестов
pytest tests/test_dag.py::TestDAGBranch -v
pytest tests/test_dag.py::TestDAGExecutionContext -v
pytest tests/test_dag.py::TestDAGExecutor -v
pytest tests/test_dag.py::TestBranchRouter -v
pytest tests/test_dag.py::TestSyncPointManager -v
pytest tests/test_dag.py::TestHistoryManager -v
pytest tests/test_dag.py::TestDAGIntegration -v
```

### 13.10 Обратная совместимость

DAG реализован с полной обратной совместимостью:

- Существующие SPIN flows работают без изменений
- DAG активируется только при наличии DAG-узлов в конфигурации
- Линейные переходы остаются основным режимом
- Все существующие тесты проходят

```python
# Обычный режим (без DAG)
sm = StateMachine()
assert not sm.is_dag_mode

# DAG режим (при наличии fork/choice в flow)
sm = StateMachine(flow=dag_flow)
assert sm.is_dag_mode
```

---

*Документация создана на основе анализа кодовой базы CRM Sales Bot.*
