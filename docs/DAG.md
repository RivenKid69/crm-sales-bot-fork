# DAG State Machine - Полная Документация

> **Версия:** 1.0
> **Дата создания:** Январь 2026
> **Модуль:** `src/dag/`

## Содержание

1. [Обзор](#1-обзор)
2. [Архитектура](#2-архитектура)
3. [Типы узлов](#3-типы-узлов)
4. [Модели данных](#4-модели-данных)
5. [DAGExecutor](#5-dagexecutor)
6. [BranchRouter](#6-branchrouter)
7. [SyncPointManager](#7-syncpointmanager)
8. [HistoryManager](#8-historymanager)
9. [YAML конфигурация](#9-yaml-конфигурация)
10. [Примеры Flow](#10-примеры-flow)
11. [Интеграция со StateMachine](#11-интеграция-со-statemachine)
12. [Event Sourcing](#12-event-sourcing)
13. [Тестирование](#13-тестирование)
14. [Best Practices](#14-best-practices)
15. [API Reference](#15-api-reference)

---

## 1. Обзор

### 1.1 Что такое DAG State Machine?

DAG (Directed Acyclic Graph) State Machine — расширение линейной конечной машины состояний, позволяющее создавать сложные диалоговые сценарии с:

- **Условными ветвлениями** — выбор пути на основе условий
- **Параллельными потоками** — одновременное выполнение нескольких веток
- **Синхронизацией** — объединение результатов параллельных веток
- **Историей состояний** — сохранение контекста при прерываниях

### 1.2 Зачем нужен DAG?

| Проблема линейного FSM | Решение DAG |
|------------------------|-------------|
| Один путь выполнения | CHOICE узлы для условного ветвления |
| Последовательный сбор данных | FORK/JOIN для параллельного сбора |
| Потеря контекста при прерывании | History states для сохранения |
| Сложная логика маршрутизации | BranchRouter для интеллектуальной маршрутизации |

### 1.3 Когда использовать DAG?

**Используйте DAG для:**
- Квалификации лидов (BANT, MEDDIC)
- Службы поддержки с маршрутизацией
- Сложных onboarding flows
- Параллельного сбора информации

**Не используйте DAG для:**
- Простых линейных сценариев
- Flows с 3-5 состояниями
- Случаев, когда достаточно условных transitions

---

## 2. Архитектура

### 2.1 Компоненты системы

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              src/dag/                                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                           models.py                                      ││
│  │  • NodeType (SIMPLE, CHOICE, FORK, JOIN, PARALLEL)                      ││
│  │  • BranchStatus (PENDING, ACTIVE, COMPLETED, SKIPPED, FAILED)           ││
│  │  • JoinCondition (ALL_COMPLETE, ANY_COMPLETE, MAJORITY, etc.)           ││
│  │  • DAGBranch, DAGEvent, DAGExecutionContext, DAGNodeConfig              ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                                                              │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────────┐  │
│  │   executor.py   │  │ branch_router.py│  │      sync_points.py         │  │
│  │                 │  │                 │  │                             │  │
│  │ DAGExecutor     │  │ BranchRouter    │  │ SyncPointManager            │  │
│  │ • execute()     │  │ • route_intent()│  │ • register_sync_point()     │  │
│  │ • _execute_     │  │ • broadcast()   │  │ • arrive()                  │  │
│  │   choice/fork/  │  │                 │  │ • check_completion()        │  │
│  │   join/parallel │  │ IntentBranch    │  │                             │  │
│  │                 │  │ Mapping         │  │ SyncStrategy, SyncPoint     │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────────────────┘  │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                           history.py                                     ││
│  │  • HistoryManager — сохранение/восстановление состояний                 ││
│  │  • HistoryEntry — запись истории (state, region_id, timestamp, data)    ││
│  │  • ConversationFlowTracker — высокоуровневый трекер прерываний          ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Поток данных

```
                    User Intent
                         │
                         ▼
              ┌──────────────────────┐
              │    StateMachine      │
              │    apply_rules()     │
              └──────────┬───────────┘
                         │
            ┌────────────┴────────────┐
            │   Is DAG state?         │
            └────────┬───────┬────────┘
                     │ YES   │ NO
                     ▼       ▼
         ┌───────────────┐  ┌───────────────┐
         │  DAGExecutor  │  │ Standard flow │
         │   execute()   │  │               │
         └───────┬───────┘  └───────────────┘
                 │
    ┌────────────┼────────────┬────────────┐
    │            │            │            │
    ▼            ▼            ▼            ▼
┌───────┐  ┌─────────┐  ┌─────────┐  ┌──────────┐
│CHOICE │  │  FORK   │  │  JOIN   │  │ PARALLEL │
└───┬───┘  └────┬────┘  └────┬────┘  └────┬─────┘
    │           │            │            │
    │    ┌──────┴──────┐     │            │
    │    │ BranchRouter│     │            │
    │    └──────┬──────┘     │            │
    │           │            │            │
    │           │      ┌─────┴─────┐      │
    │           │      │SyncPoint  │      │
    │           │      │Manager    │      │
    │           │      └───────────┘      │
    │           │            │            │
    └───────────┴────────────┴────────────┘
                         │
                         ▼
              ┌──────────────────────┐
              │   DAGExecutionResult │
              │   (action, state,    │
              │    branch_id, events)│
              └──────────────────────┘
```

---

## 3. Типы узлов

### 3.1 NodeType Enum

```python
from src.dag import NodeType

class NodeType(Enum):
    SIMPLE = "simple"      # Обычное состояние (по умолчанию)
    CHOICE = "choice"      # Условное ветвление (XOR)
    FORK = "fork"          # Начало параллельного выполнения
    JOIN = "join"          # Синхронизация/объединение веток
    PARALLEL = "parallel"  # Compound state с регионами
```

### 3.2 CHOICE (Условное ветвление)

Выбирает один путь из нескольких на основе условий (XOR — взаимоисключающий выбор).

```yaml
issue_classifier:
  type: choice
  goal: "Классификация обращения"
  choices:
    - condition: is_technical_issue
      next: technical_flow
    - condition: is_billing_issue
      next: billing_flow
    - condition: is_account_issue
      next: account_flow
  default: general_inquiry  # Если ни одно условие не выполнено
```

**Логика выполнения:**
1. Проверяются условия по порядку
2. Первое истинное условие определяет путь
3. Если ни одно не истинно — используется default

### 3.3 FORK (Параллельный запуск)

Запускает несколько веток одновременно.

```yaml
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
  join_condition: all_complete
```

**Поля:**
- `branches` — список веток для запуска
- `join_at` — состояние для синхронизации
- `join_condition` — условие завершения (all_complete, any_complete, etc.)

### 3.4 JOIN (Синхронизация)

Ожидает завершения веток и объединяет результаты.

```yaml
qualification_complete:
  type: join
  goal: "Объединение результатов квалификации"
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

**Стратегии синхронизации:**

| Стратегия | Описание |
|-----------|----------|
| `all_complete` | Ждать все ветки |
| `any_complete` | Продолжить при первой завершённой |
| `majority` | Продолжить при >50% завершённых |
| `n_of_m` | Продолжить при N из M |
| `timeout` | Продолжить по таймауту |

### 3.5 PARALLEL (Compound State)

Compound state с несколькими параллельными регионами.

```yaml
complex_flow:
  type: parallel
  goal: "Compound state с регионами"
  regions:
    - id: main_flow
      start_at: main_entry
    - id: monitoring
      start_at: track_engagement
  sync_on_exit: true  # Синхронизировать при выходе
```

---

## 4. Модели данных

### 4.1 DAGBranch

Представляет ветку выполнения в DAG.

```python
from src.dag import DAGBranch, BranchStatus

branch = DAGBranch(
    branch_id="budget_branch",
    start_state="collect_budget",
    current_state="collect_budget",
    status=BranchStatus.PENDING
)

# Активация
branch.activate()
assert branch.status == BranchStatus.ACTIVE

# Обновление состояния
branch.update_state("verify_budget")

# Завершение
branch.complete(result={"budget": 50000})
assert branch.status == BranchStatus.COMPLETED

# Сериализация
data = branch.to_dict()
restored = DAGBranch.from_dict(data)
```

### 4.2 DAGEvent

Событие в DAG (для event sourcing).

```python
from src.dag.models import DAGEvent

event = DAGEvent(
    event_type="branch_started",
    branch_id="budget_branch",
    from_state=None,
    to_state="collect_budget",
    data={"initial": True}
)

print(event.timestamp)  # Автоматически
print(event.to_dict())
```

**Типы событий:**
- `fork_started`, `fork_completed`
- `branch_started`, `branch_completed`, `branch_skipped`
- `join_started`, `join_completed`
- `choice_evaluated`
- `state_transition`

### 4.3 DAGExecutionContext

Контекст выполнения DAG.

```python
from src.dag import DAGExecutionContext

ctx = DAGExecutionContext(primary_state="greeting")

# Проверка режима DAG
if ctx.is_dag_mode:
    print(f"Active branches: {ctx.active_branch_ids}")

# Запуск fork
branches = {
    "budget": DAGBranch("budget", "collect_budget"),
    "need": DAGBranch("need", "assess_needs"),
}
ctx.start_fork("qualification_fork", branches)

# Обновление ветки
ctx.update_branch_state("budget", "verify_budget")

# Завершение ветки
ctx.complete_branch("budget", result={"amount": 50000})

# Проверка синхронизации
if ctx.all_branches_complete:
    ctx.complete_current_fork()
```

### 4.4 DAGNodeConfig

Конфигурация DAG-узла из YAML.

```python
from src.dag import DAGNodeConfig, NodeType

config = DAGNodeConfig(
    node_type=NodeType.FORK,
    branches=[
        {"id": "budget", "start_at": "collect_budget"},
        {"id": "need", "start_at": "assess_needs"},
    ],
    join_at="qualification_complete",
    join_condition="all_complete"
)

# Из YAML dict
yaml_config = {
    "type": "fork",
    "branches": [
        {"id": "budget", "start_at": "collect_budget"},
    ],
    "join_at": "complete",
    "join_condition": "all_complete"
}
config = DAGNodeConfig.from_dict(yaml_config)
```

---

## 5. DAGExecutor

### 5.1 Обзор

`DAGExecutor` выполняет DAG-узлы и управляет переходами.

```python
from src.dag import DAGExecutor, DAGExecutionContext

ctx = DAGExecutionContext(primary_state="greeting")
executor = DAGExecutor(ctx)
```

### 5.2 Методы выполнения

#### execute()

Главный метод — определяет тип узла и делегирует выполнение.

```python
result = executor.execute(
    state="issue_classifier",
    node_config=config,
    intent="technical_question",
    evaluator_ctx=eval_ctx
)

print(result.action)       # "classify_issue"
print(result.next_state)   # "technical_flow"
print(result.branch_id)    # None (для CHOICE)
```

#### _execute_choice()

Выполняет условное ветвление.

```python
result = executor._execute_choice(
    state="classifier",
    config=choice_config,
    ctx=eval_ctx
)
# Возвращает (action, next_state)
```

#### _execute_fork()

Запускает параллельные ветки.

```python
result = executor._execute_fork(
    state="fork_state",
    config=fork_config,
    ctx=eval_ctx
)
# Создаёт ветки в DAGExecutionContext
```

#### _execute_join()

Синхронизирует завершённые ветки.

```python
result = executor._execute_join(
    state="join_state",
    config=join_config,
    ctx=eval_ctx
)
# Проверяет готовность и объединяет результаты
```

### 5.3 DAGExecutionResult

Результат выполнения DAG-узла.

```python
from src.dag import DAGExecutionResult

result = DAGExecutionResult(
    action="start_fork",
    next_state="collect_budget",
    branch_id="budget_branch",
    is_dag_action=True,
    fork_branches=["budget", "need", "authority"],
    join_ready=False
)

print(result.is_dag_action)  # True
print(result.fork_branches)  # ["budget", "need", "authority"]
```

---

## 6. BranchRouter

### 6.1 Обзор

`BranchRouter` маршрутизирует интенты между активными ветками.

```python
from src.dag import BranchRouter

router = BranchRouter(dag_ctx, strategy="round_robin")
```

### 6.2 Стратегии маршрутизации

| Стратегия | Описание |
|-----------|----------|
| `round_robin` | Циклический перебор веток |
| `priority` | По приоритету веток |
| `first_match` | Первая активная ветка |

```python
# Round-robin (по умолчанию)
router = BranchRouter(ctx, strategy="round_robin")

# По приоритету
router = BranchRouter(ctx, strategy="priority")
router.set_branch_priority("urgent_branch", 100)
router.set_branch_priority("normal_branch", 50)
```

### 6.3 Маршрутизация интентов

```python
# Базовая маршрутизация
result = router.route_intent("price_question")
if result.branch_id:
    print(f"Route to: {result.branch_id}")
    print(f"State: {result.state}")

# С явным маппингом intent → branch
branch_handlers = {
    "budget_branch": ["budget_question", "pricing_inquiry"],
    "need_branch": ["pain_point", "requirement"],
}
result = router.route_intent("budget_question", branch_handlers)
```

### 6.4 Broadcast интентов

Отправка интента во все активные ветки.

```python
def handle_cancel(branch_id, state, intent):
    return {"cancelled": True, "branch": branch_id}

results = router.broadcast_intent("cancel", handle_cancel)
# {"budget_branch": {...}, "need_branch": {...}}
```

### 6.5 IntentBranchMapping

Явный маппинг интентов к веткам.

```python
from src.dag import IntentBranchMapping

mapping = IntentBranchMapping()
mapping.register("budget_branch", ["budget_question", "pricing"])
mapping.register("need_branch", ["pain_point", "requirement"])

# Получить ветки для интента
branches = mapping.get_branches_for_intent("budget_question")
# ["budget_branch"]

# Получить интенты для ветки
intents = mapping.get_intents_for_branch("budget_branch")
# ["budget_question", "pricing"]
```

---

## 7. SyncPointManager

### 7.1 Обзор

`SyncPointManager` управляет точками синхронизации для параллельных веток.

```python
from src.dag import SyncPointManager, SyncStrategy

sync_manager = SyncPointManager()
```

### 7.2 Стратегии синхронизации

```python
from src.dag import SyncStrategy

class SyncStrategy(Enum):
    ALL_COMPLETE = "all_complete"    # Все ветки
    ANY_COMPLETE = "any_complete"    # Любая ветка
    MAJORITY = "majority"            # >50% веток
    N_OF_M = "n_of_m"               # N из M
    TIMEOUT = "timeout"              # По таймауту
```

### 7.3 Регистрация точек синхронизации

```python
# ALL_COMPLETE
sync_manager.register_sync_point(
    "qualification_complete",
    required_branches=["budget", "authority", "need"],
    strategy=SyncStrategy.ALL_COMPLETE
)

# N_OF_M (2 из 3)
sync_manager.register_sync_point(
    "partial_complete",
    required_branches=["a", "b", "c"],
    strategy=SyncStrategy.N_OF_M,
    n_required=2
)

# С callback
def on_sync(sync_point, results):
    print(f"Synced at {sync_point}: {results}")

sync_manager.register_sync_point(
    "final_sync",
    required_branches=["x", "y"],
    strategy=SyncStrategy.ALL_COMPLETE,
    callback=on_sync
)
```

### 7.4 Прибытие в точку синхронизации

```python
# Ветка прибывает
result = sync_manager.arrive(
    "qualification_complete",
    "budget",
    result={"amount": 50000}
)

print(result.is_complete)   # False (ждём остальные)
print(result.arrived)       # ["budget"]
print(result.waiting)       # ["authority", "need"]

# Ещё одна ветка
result = sync_manager.arrive("qualification_complete", "authority")
result = sync_manager.arrive("qualification_complete", "need")

print(result.is_complete)   # True
print(result.results)       # {"budget": {...}, "authority": {...}, "need": {...}}
```

---

## 8. HistoryManager

### 8.1 Обзор

`HistoryManager` сохраняет и восстанавливает состояния для прерванных диалогов.

```python
from src.dag import HistoryManager, HistoryType

history = HistoryManager(max_deep_history=10)
```

### 8.2 Типы истории

| Тип | Описание |
|-----|----------|
| `SHALLOW` | Только последнее состояние |
| `DEEP` | Полная история (стек) |

### 8.3 Сохранение состояния

```python
# Shallow (по умолчанию)
history.save(
    region_id="booking_flow",
    state="collect_date",
    data={"step": 1, "selected_service": "consultation"}
)

# Deep
history.save(
    region_id="booking_flow",
    state="collect_time",
    history_type=HistoryType.DEEP,
    data={"step": 2}
)
```

### 8.4 Восстановление состояния

```python
# Shallow
state = history.restore("booking_flow")
# "collect_date"

# С данными
result = history.restore_with_data("booking_flow")
if result:
    state, data = result
    print(f"Restored to {state} with {data}")

# Deep (с pop)
state = history.restore("booking_flow", HistoryType.DEEP, pop=True)
# Удаляет из стека
```

### 8.5 ConversationFlowTracker

Высокоуровневая абстракция для управления прерываниями.

```python
from src.dag import ConversationFlowTracker

tracker = ConversationFlowTracker()

# Начать flow
tracker.start_flow("booking", "collect_date")

# Прервать (пользователь спрашивает о ценах)
tracker.interrupt_flow("collect_time", data={"step": 2})

# ... обработка вопроса о ценах ...

# Возобновить
result = tracker.resume_flow()
if result:
    flow_id, state, data = result
    print(f"Resume {flow_id} at {state}")

# Завершить
tracker.complete_flow()
```

---

## 9. YAML конфигурация

### 9.1 Структура файлов

```
yaml_config/
├── flows/
│   ├── examples/
│   │   ├── bant_flow.yaml       # BANT квалификация
│   │   └── support_flow.yaml    # Служба поддержки
│   └── _base/
│       └── states.yaml
└── schemas/
    └── dag_state.schema.json    # JSON Schema для валидации
```

### 9.2 CHOICE конфигурация

```yaml
states:
  issue_classifier:
    type: choice
    goal: "Классификация обращения"
    choices:
      # Проверяются по порядку
      - condition: is_technical_issue
        next: technical_flow
      - condition: is_billing_issue
        next: billing_flow
      - condition: is_urgent_issue
        next: human_handoff
    default: general_inquiry  # Fallback
```

### 9.3 FORK конфигурация

```yaml
states:
  bant_fork:
    type: fork
    goal: "Параллельный сбор BANT"
    branches:
      - id: budget_branch
        start_at: collect_budget

      - id: authority_branch
        start_at: identify_decision_maker

      - id: need_branch
        start_at: assess_needs
        condition: has_initial_interest  # Опциональная

      - id: timeline_branch
        start_at: determine_timeline

    join_at: bant_complete
    join_condition: all_complete
```

### 9.4 JOIN конфигурация

```yaml
states:
  bant_complete:
    type: join
    goal: "Анализ квалификации"
    expects_branches:
      - budget_branch
      - authority_branch
      - need_branch
      - timeline_branch
    join_condition: all_complete  # или majority, any_complete
    on_join:
      action: analyze_bant_results
    transitions:
      all_positive: presentation
      mixed_results: nurture
      all_negative: disqualify
```

### 9.5 History конфигурация

```yaml
states:
  billing_flow:
    type: simple
    goal: "Обработка billing"
    history: shallow  # Сохранять при прерывании
    transitions:
      refund: process_refund
      payment: troubleshoot_payment
```

### 9.6 Состояния веток

```yaml
states:
  # Состояние внутри ветки
  collect_budget:
    type: simple
    branch: budget_branch  # Привязка к ветке
    goal: "Узнать бюджет"
    required_data:
      - budget_range
    transitions:
      budget_provided: verify_budget
      no_budget: _branch_complete  # Специальный переход

  verify_budget:
    type: simple
    branch: budget_branch
    goal: "Подтвердить бюджет"
    transitions:
      confirmed: _branch_complete
      needs_adjustment: collect_budget
```

---

## 10. Примеры Flow

### 10.1 BANT Qualification Flow

```yaml
# src/yaml_config/flows/examples/bant_flow.yaml

flow:
  name: bant_qualification
  version: "1.0"
  description: "BANT квалификация с параллельным сбором"

entry_points:
  default: greeting
  returning: quick_qualify

states:
  greeting:
    type: simple
    goal: "Приветствие"
    transitions:
      greeting_complete: interest_check

  interest_check:
    type: choice
    goal: "Проверка интереса"
    choices:
      - condition: has_high_interest
        next: bant_fork
      - condition: has_some_interest
        next: nurture_entry
    default: qualification_questions

  bant_fork:
    type: fork
    goal: "BANT квалификация"
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
    join_condition: all_complete

  # ... состояния веток ...

  bant_complete:
    type: join
    expects_branches: [budget, authority, need, timeline]
    join_condition: all_complete
    on_join:
      action: calculate_bant_score
    transitions:
      score_high: presentation
      score_medium: nurture
      score_low: disqualify
```

### 10.2 Customer Support Flow

```yaml
# src/yaml_config/flows/examples/support_flow.yaml

flow:
  name: customer_support
  version: "1.0"
  description: "Поддержка с DAG маршрутизацией"

states:
  greeting:
    type: simple
    goal: "Приветствие"
    transitions:
      greeting_complete: issue_classifier

  issue_classifier:
    type: choice
    goal: "Классификация обращения"
    choices:
      - condition: is_technical_issue
        next: technical_flow
      - condition: is_billing_issue
        next: billing_flow
      - condition: is_account_issue
        next: account_flow
      - condition: is_urgent_issue
        next: human_handoff
    default: general_inquiry

  technical_flow:
    type: fork
    goal: "Параллельная диагностика"
    branches:
      - id: system_check
        start_at: check_system_status
      - id: user_diagnostics
        start_at: collect_error_details
      - id: known_issues
        start_at: check_known_issues
        condition: has_error_code
    join_at: technical_resolution
    join_condition: all_complete

  billing_flow:
    type: simple
    history: shallow  # Сохранять при прерывании
    goal: "Billing вопросы"
    transitions:
      refund_request: process_refund
      payment_failed: troubleshoot_payment
```

---

## 11. Интеграция со StateMachine

### 11.1 Автоматическая инициализация

```python
from src.state_machine import StateMachine
from src.config_loader import ConfigLoader

# DAG контекст создаётся автоматически при наличии DAG-узлов
loader = ConfigLoader()
flow = loader.load_flow("bant_qualification")
sm = StateMachine(flow=flow)

# Проверка режима
print(sm.is_dag_mode)      # True если есть DAG узлы
print(sm.dag_context)      # DAGExecutionContext
print(sm.active_branches)  # Список активных веток
```

### 11.2 apply_rules() с DAG

```python
# apply_rules автоматически обрабатывает DAG узлы
action, next_state = sm.apply_rules("price_question")

# Если в DAG режиме
if sm.is_dag_mode:
    # Маршрутизация к ветке
    print(f"Active branches: {sm.active_branches}")
```

### 11.3 DAG Properties в StateMachine

```python
sm = StateMachine(flow=dag_flow)

# Проверки
sm.is_dag_mode          # bool: активен ли DAG
sm.dag_context          # DAGExecutionContext или None
sm.active_branches      # List[str]: ID активных веток
sm.dag_events           # List[DAGEvent]: события

# Методы
sm.is_dag_state("fork_state")  # bool: это DAG узел?
```

### 11.4 Reset с DAG

```python
sm.reset()

# DAG контекст тоже сбрасывается
assert not sm.is_dag_mode or len(sm.active_branches) == 0
```

---

## 12. Event Sourcing

### 12.1 Обзор

DAG поддерживает event sourcing для отладки, аудита и replay.

### 12.2 Типы событий

| Событие | Описание |
|---------|----------|
| `fork_started` | Запущен fork |
| `fork_completed` | Fork завершён |
| `branch_started` | Ветка активирована |
| `branch_completed` | Ветка завершена |
| `branch_skipped` | Ветка пропущена (условие не выполнено) |
| `join_started` | Начата синхронизация |
| `join_completed` | Синхронизация завершена |
| `choice_evaluated` | Выполнено условное ветвление |
| `state_transition` | Переход состояния |

### 12.3 Работа с событиями

```python
# Получение событий
events = sm.dag_events

for event in events:
    print(f"[{event.timestamp}] {event.event_type}")
    print(f"  Branch: {event.branch_id}")
    print(f"  {event.from_state} → {event.to_state}")
    print(f"  Data: {event.data}")

# Фильтрация
fork_events = [e for e in events if e.event_type == "fork_started"]
branch_events = [e for e in events if e.branch_id == "budget_branch"]
```

### 12.4 Сериализация

```python
# Сериализация для персистенции
ctx = sm.dag_context
data = ctx.to_dict()

# Включает:
# - primary_state
# - active_branches
# - completed_branches
# - history
# - events

# Восстановление
from src.dag import DAGExecutionContext
restored_ctx = DAGExecutionContext.from_dict(data)
```

---

## 13. Тестирование

### 13.1 Тестовые файлы

```
tests/
└── test_dag.py           # 37 тестов
    ├── TestDAGBranch
    ├── TestDAGExecutionContext
    ├── TestDAGNodeConfig
    ├── TestDAGExecutor
    ├── TestBranchRouter
    ├── TestIntentBranchMapping
    ├── TestSyncPointManager
    ├── TestHistoryManager
    ├── TestConversationFlowTracker
    └── TestDAGIntegration
```

### 13.2 Запуск тестов

```bash
# Все DAG тесты
pytest tests/test_dag.py -v

# Конкретный класс
pytest tests/test_dag.py::TestDAGExecutor -v

# С покрытием
pytest tests/test_dag.py --cov=src/dag --cov-report=html
```

### 13.3 Примеры тестов

```python
# test_dag.py

def test_fork_creates_branches():
    """Fork should create branches in context."""
    ctx = DAGExecutionContext(primary_state="greeting")
    executor = DAGExecutor(ctx)

    config = DAGNodeConfig(
        node_type=NodeType.FORK,
        branches=[
            {"id": "a", "start_at": "state_a"},
            {"id": "b", "start_at": "state_b"},
        ],
        join_at="join_state"
    )

    result = executor.execute("fork_state", config, "start", eval_ctx)

    assert ctx.is_dag_mode
    assert len(ctx.active_branches) == 2
    assert "a" in ctx.active_branch_ids
    assert "b" in ctx.active_branch_ids


def test_join_waits_for_all_branches():
    """Join should wait until all branches complete."""
    ctx = DAGExecutionContext(primary_state="greeting")

    # Start fork
    branches = {
        "a": DAGBranch("a", "state_a"),
        "b": DAGBranch("b", "state_b"),
    }
    ctx.start_fork("fork", branches)

    # Complete one branch
    ctx.complete_branch("a")
    assert not ctx.all_branches_complete

    # Complete second branch
    ctx.complete_branch("b")
    assert ctx.all_branches_complete
```

---

## 14. Best Practices

### 14.1 Когда использовать DAG

✅ **Используйте DAG:**
- BANT/MEDDIC квалификация
- Параллельный сбор информации
- Служба поддержки с маршрутизацией
- Сложные onboarding flows
- Диалоги с частыми прерываниями

❌ **Не используйте DAG:**
- Простые линейные сценарии
- Flows с < 5 состояниями
- Когда достаточно условных transitions

### 14.2 Именование

```yaml
# Хорошо
branches:
  - id: budget_branch      # Понятное имя
    start_at: collect_budget

# Плохо
branches:
  - id: b1                 # Непонятное имя
    start_at: s1
```

### 14.3 Структура веток

```yaml
# Хорошо: каждая ветка имеет чёткую цель
branches:
  - id: budget_collection
    start_at: ask_budget
  - id: need_assessment
    start_at: identify_pain

# Плохо: слишком много мелких веток
branches:
  - id: step1
  - id: step2
  - id: step3
```

### 14.4 Обработка ошибок

```python
# Всегда проверяйте результаты
result = router.route_intent("question")
if result.branch_id is None:
    # Fallback логика
    if result.all_waiting:
        # Все ветки ждут синхронизации
        pass
```

### 14.5 History States

```yaml
# Используйте history для flows с прерываниями
booking_flow:
  type: simple
  history: shallow  # Для простых случаев

complex_flow:
  type: simple
  history: deep     # Для глубокой навигации
```

---

## 15. API Reference

### 15.1 Импорты

```python
from src.dag import (
    # Enums
    NodeType,
    BranchStatus,
    JoinCondition,
    HistoryType,

    # Models
    DAGBranch,
    DAGEvent,
    DAGExecutionContext,
    DAGNodeConfig,

    # Executor
    DAGExecutor,
    DAGExecutionResult,

    # Branch Router
    BranchRouter,
    BranchRouteResult,
    IntentBranchMapping,

    # Sync Points
    SyncPointManager,
    SyncStrategy,
    SyncPoint,
    SyncResult,

    # History
    HistoryManager,
    HistoryEntry,
    ConversationFlowTracker,
)
```

### 15.2 Основные классы

| Класс | Описание |
|-------|----------|
| `DAGExecutionContext` | Контекст выполнения DAG |
| `DAGExecutor` | Выполнение DAG узлов |
| `BranchRouter` | Маршрутизация интентов |
| `SyncPointManager` | Синхронизация веток |
| `HistoryManager` | История состояний |

### 15.3 Enums

| Enum | Значения |
|------|----------|
| `NodeType` | SIMPLE, CHOICE, FORK, JOIN, PARALLEL |
| `BranchStatus` | PENDING, ACTIVE, COMPLETED, SKIPPED, FAILED |
| `JoinCondition` | ALL_COMPLETE, ANY_COMPLETE, MAJORITY, N_OF_M |
| `SyncStrategy` | ALL_COMPLETE, ANY_COMPLETE, MAJORITY, N_OF_M, TIMEOUT |
| `HistoryType` | NONE, SHALLOW, DEEP |

---

*Документация создана на основе реализации DAG State Machine в CRM Sales Bot.*
