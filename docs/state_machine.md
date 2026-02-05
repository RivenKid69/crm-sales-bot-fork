# State Machine - Полная Документация

> **Версия документации:** 4.0 (Blackboard v3.x + StateMachine storage)
> **Последнее обновление:** Февраль 2026
> **Основные файлы:** `src/blackboard/orchestrator.py` (decision engine) + `src/state_machine.py` (state/transition storage)

---

## ВАЖНО: Миграция на Blackboard Architecture (v3.0)

**С января 2026** decision engine переведён на **Dialogue Blackboard Architecture**. `StateMachine` остаётся источником состояния, collected_data и snapshot API — Blackboard использует его через протоколы.

### Что изменилось

| Аспект | v2.0 (Legacy) | v3.0 (Current) |
|--------|---------------|----------------|
| **Архитектура** | Procedural rule processing | Blackboard Pattern |
| **Основной модуль** | `state_machine.apply_rules()` | `blackboard.orchestrator` |
| **Decision Making** | Hardcoded priorities | 15 Knowledge Sources |
| **State Transitions** | Distributed mutation | Atomic transition_to() |
| **Objection Limits** | Hardcoded (12+ places) | Configurable via constants.yaml |
| **Objection Tracking** | Manual _state_before_objection | Automatic tracking |
| **Go Back Logic** | Scattered | CircularFlowManager SSOT |
| **Phase Resolution** | SPIN only | Universal (all 21 flows) |
| **Extensibility** | Править Python код | Plugin System (@register_source) |
| **Observability** | Базовые логи | EventBus + MetricsCollector |
| **Интенты** | 150+ в 26 категориях | 300 в 34 категориях |

### Ключевые компоненты v3.0

```python
from src.blackboard import DialogueOrchestrator, create_orchestrator

# v3.0: Orchestrator координирует Knowledge Sources
orchestrator = create_orchestrator(
    state_machine=sm,
    flow_config=flow
)

# Обработка хода диалога
decision = orchestrator.process_turn()
```

---

## Snapshot Serialization (v3.0)

StateMachine поддерживает сериализацию для восстановления диалога:

```python
data = state_machine.to_dict()
state_machine = StateMachine.from_dict(data, config=config, flow=flow)
```

**Что входит в snapshot:**
- `state`, `current_phase`, `collected_data`
- `in_disambiguation`, `disambiguation_context`, `pre_disambiguation_state`
- `turns_since_last_disambiguation`
- `intent_tracker` (compact, без полной истории)
- `circular_flow` (goback_count, remaining, history)

Эти поля используются `SalesBot.to_snapshot()` и `SalesBot.from_snapshot()` для восстановления состояния после паузы.

### Критические исправления v3.0

**1. Atomic State Transitions (transition_to())**

До исправления различные компоненты напрямую модифицировали `state`, что приводило к рассинхронизации с `current_phase` и `last_action`:

```python
# ПРОБЛЕМА (distributed mutation):
orchestrator: state_machine.state = "spin_problem"
              state_machine.current_phase = "problem"
bot.py:       state_machine.state = "spin_implication"  # Только state!
# Результат: state="spin_implication", current_phase="problem" ❌

# РЕШЕНИЕ (atomic transition):
orchestrator: state_machine.transition_to("spin_problem", source="orchestrator")
bot.py:       state_machine.transition_to("spin_implication", source="policy_override")
# Результат: state="spin_implication", current_phase="implication" ✓
```

**Файлы:** `src/state_machine.py:615-697`, `src/blackboard/orchestrator.py:529`, `tests/test_transition_atomicity.py`

**2. CircularFlowManager SSOT + Deferred Increment**

CircularFlowManager — единственный источник правды для go_back логики с deferred increment механизмом:

```python
# ПРОБЛЕМА: GoBackGuardSource инкрементировал счетчик ДО conflict resolution
# Если ObjectionGuardSource блокировал go_back, счетчик все равно рос ❌

# РЕШЕНИЕ: Deferred increment через proposal metadata
GoBackGuardSource:
  - Добавляет pending_goback_increment=True в metadata
  - НЕ инкрементирует счетчик

Orchestrator._apply_deferred_goback_increment():
  - Вызывается ПОСЛЕ conflict resolution
  - Инкрементирует ТОЛЬКО если go_back выиграл И state изменился ✓
```

**Файлы:** `src/state_machine.py:59-239`, `src/blackboard/orchestrator.py:581-648`, `src/blackboard/sources/go_back_guard.py`

**3. Universal Phase Resolution**

FlowConfig.get_phase_for_state() обеспечивает работу со всеми 21 flows:

```python
# ПРОБЛЕМА: Хардкоженный _STATE_TO_PHASE только для SPIN
# 20 из 21 flows имели сломанное определение фазы ❌

# РЕШЕНИЕ: Universal phase resolution
def get_phase_for_state(state):
    # Priority 1: Explicit state_config.phase (SPIN)
    # Priority 2: Reverse mapping from phase_mapping (BANT, MEDDIC)
    # Работает для всех flows ✓
```

**Файлы:** `src/config_loader.py:state_to_phase`, `src/state_machine.py:679`

**4. Automatic State Before Objection Tracking**

Orchestrator автоматически отслеживает состояние до серии возражений:

```python
# ПРОБЛЕМА: _state_before_objection никогда не устанавливался ❌

# РЕШЕНИЕ: Orchestrator._update_state_before_objection()
# - При входе в handle_objection: сохраняет prev_state
# - При позитивном интенте: очищает когда streak breaks
# - При выходе из handle_objection: очищает ✓
```

**Файл:** `src/blackboard/orchestrator.py:650-699`

### 15 Knowledge Sources

1. **AutonomousDecisionSource** (priority 100) — автономные решения
2. **ObjectionGuardSource** (priority 90) — защита от зацикливания возражений (persona-based limits)
3. **StallGuardSource** (priority 88) — two-tier stall detection (soft NORMAL + hard HIGH)
4. **ConversationGuardSource** (priority 85) — защита от повторов (tier_2 self-loop breaker)
5. **GoBackGuardSource** (priority 82) — возврат назад по фазам (deferred increment)
6. **IntentPatternGuardSource** (priority 80) — comparison fatigue detection
7. **ObjectionReturnSource** (priority 75) — возврат после возражений (all_questions auto-discovery)
8. **PriceQuestionSource** (priority 70) — вопросы о цене (7 price_related intents, category_streak)
9. **EscalationSource** (priority 70) — эскалация к человеку (category_streak для 8 escalation intents)
10. **FactQuestionSource** (priority 65) — фактические вопросы (17 KB categories, secondary_intents support)
11. **PhaseExhaustedSource** (priority 60) — исчерпанные фазы (migrated from ConversationGuard)
12. **DisambiguationSource** (priority 55) — уточнение неоднозначностей (blocking, combinable=False)
13. **DataCollectorSource** (priority 50) — сбор данных клиента
14. **IntentProcessorSource** (priority 40) — обработка базовых интентов
15. **TransitionResolverSource** (priority 30) — разрешение переходов

### Legacy State Machine (v2.0) — Deprecated

**С января 2026** StateMachine сохранён для совместимости, но основная логика перенесена в Blackboard.
- `apply_rules()` → DEPRECATED (заменён на `orchestrator.process_turn()`)
- Все константы в `constants.yaml` (single source of truth)
- Выбор flow через `settings.yaml` (`flow.active`)
- Нет hardcoded SPIN логики — платформа универсальная

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
3. [Atomic State Transitions](#3-atomic-state-transitions) NEW
4. [SPIN Selling Flow](#4-spin-selling-flow)
5. [Система Приоритетов](#5-система-приоритетов)
6. [Условные Правила (Conditional Rules)](#6-условные-правила-conditional-rules)
7. [IntentTracker](#7-intenttracker)
8. [YAML Конфигурация](#8-yaml-конфигурация)
9. [Условия (Conditions)](#9-условия-conditions)
10. [Примеры Использования](#10-примеры-использования)
11. [Диаграммы и Схемы](#11-диаграммы-и-схемы)
12. [Тестирование](#12-тестирование)
13. [FAQ и Troubleshooting](#13-faq-и-troubleshooting)
14. [DAG State Machine](#14-dag-state-machine)

---

## 1. Обзор и Архитектура

### 1.1 Что такое Dialogue Blackboard System?

**Dialogue Blackboard** — это современная архитектура для управления диалогом, основанная на паттерне Blackboard.

**Ключевая идея:** Независимые Knowledge Sources анализируют контекст и делают предложения (Proposals), которые затем разрешаются через ConflictResolver.

**Компоненты:**
- **DialogueBlackboard** — центральное хранилище состояния диалога
- **DialogueOrchestrator** — координатор Knowledge Sources
- **15 Knowledge Sources** — независимые модули принятия решений
- **ConflictResolver** — разрешение конфликтов между предложениями
- **EventBus** — наблюдаемость и аналитика

**Что он управляет:**
- **Состояниями диалога** (greeting, spin_situation, close и др.)
- **Переходами** между состояниями через Knowledge Sources
- **Правилами** обработки интентов через distributed decision-making
- **Сбором данных** о клиенте через DataCollectorSource

### 1.2 Архитектурные принципы v3.0 (Blackboard)

```
┌─────────────────────────────────────────────────────────────────┐
│                  DialogueOrchestrator                            │
├─────────────────────────────────────────────────────────────────┤
│  ┌──────────────────┐                                           │
│  │ ContextSnapshot  │  ← Immutable snapshot для KS              │
│  └────────┬─────────┘                                           │
│           │                                                      │
│           ▼                                                      │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │         15 Knowledge Sources (параллельно)                  ││
│  │  AutonomousDecision │ ObjectionGuard │ ConversationGuard   ││
│  │  PriceQuestion │ FactQuestion │ DataCollector │ ...        ││
│  └────────┬────────────────────────────────────────────────────┘│
│           │ Proposals (List[Proposal])                          │
│           ▼                                                      │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │              ConflictResolver                                ││
│  │  1. Filter invalid proposals (ProposalValidator)             ││
│  │  2. Group by type (ACTION, TRANSITION, DATA)                ││
│  │  3. Sort by priority (highest first)                        ││
│  │  4. Resolve conflicts (combinable vs blocking)              ││
│  └────────┬────────────────────────────────────────────────────┘│
│           │                                                      │
│           ▼                                                      │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │          ResolvedDecision                                    ││
│  │  • action: str                                              ││
│  │  • next_state: Optional[str]                                ││
│  │  • collected_data: Dict                                     ││
│  └─────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
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
| `current_phase` | `Optional[str]` | Текущая фаза (universal for all flows) |
| `last_action` | `Optional[str]` | Последнее действие |
| `intent_tracker` | `IntentTracker` | Трекер истории интентов |
| `circular_flow` | `CircularFlowManager` | Менеджер возвратов назад (SSOT) |
| `_state_before_objection` | `Optional[str]` | Состояние до возражения (auto-tracked) |

#### Ключевые методы

##### `transition_to(next_state: str, action: Optional[str] = None, phase: Optional[str] = None, source: str = "unknown", validate: bool = True) -> bool` NEW

**Atomic state transition** — единственная точка контроля для изменения состояния, обеспечивающая согласованность state, current_phase и last_action.

```python
# БЫЛО (distributed mutation bug):
# orchestrator._apply_side_effects()
sm.state = "spin_problem"
sm.current_phase = "problem"
sm.last_action = "ask_problem_questions"

# bot.py (policy_override)
sm.state = "spin_implication"  # ТОЛЬКО state!
# Результат: state="spin_implication", current_phase="problem" — НЕСОГЛАСОВАННОСТЬ!

# СТАЛО (atomic):
# orchestrator._apply_side_effects()
sm.transition_to(
    next_state="spin_problem",
    action="ask_problem_questions",
    source="orchestrator"
)

# bot.py (policy_override)
sm.transition_to(
    next_state="spin_implication",
    action="ask_implication_questions",
    source="policy_override"
)
# Результат: state="spin_implication", current_phase="implication" — СОГЛАСОВАННО!
```

**Проблема (Distributed State Mutation bug):**

До внедрения transition_to() различные компоненты напрямую изменяли `state_machine.state`, что приводило к рассинхронизации:
- `orchestrator._apply_side_effects()` устанавливал `state`, `current_phase` и `last_action` отдельно
- `bot.py` (policy_override) изменял только `state`, забывая обновить `current_phase`
- Результат: `state` указывал на одну фазу, а `current_phase` — на другую

Это вызывало критические баги:
- Неверное определение required_data (для другой фазы)
- Некорректная работа условий (`in_problem_phase` возвращал False, когда state="spin_problem")
- Промпты генерировались для неправильной фазы

**Решение:**

`transition_to()` обеспечивает атомарное обновление всех трёх атрибутов:

1. **Валидация** (если `validate=True`): проверяет существование целевого состояния в flow config
2. **Вычисление phase**: автоматически определяет `current_phase` через `FlowConfig.get_phase_for_state()`
   - Для SPIN: использует явное поле `state_config.phase`
   - Для BANT, MEDDIC и других: использует reverse mapping из `phases.mapping`
3. **Атомарное обновление**: изменяет `state`, `current_phase` и `last_action` одновременно
4. **Логирование**: записывает переход для отладки с указанием источника

**Параметры:**

| Параметр | Тип | Описание |
|----------|-----|----------|
| `next_state` | `str` | Целевое состояние для перехода |
| `action` | `Optional[str]` | Действие, вызвавшее переход (если не указано, last_action не изменяется) |
| `phase` | `Optional[str]` | Явное указание фазы (если не указано, вычисляется из flow config) |
| `source` | `str` | Идентификатор источника для отладки (например, "orchestrator", "policy_override") |
| `validate` | `bool` | Включить валидацию существования целевого состояния (по умолчанию True) |

**Возвращает:** `True` если переход успешен, `False` если валидация не прошла

**Использование в кодовой базе:**

1. **Orchestrator (src/blackboard/orchestrator.py:529)**
   ```python
   phase = self._flow_config.get_phase_for_state(decision.next_state)
   self._state_machine.transition_to(
       next_state=decision.next_state,
       action=final_action,
       phase=phase,
       source="orchestrator",
       validate=False,  # Уже провалидировано ProposalValidator
   )
   ```

2. **Bot.py (src/bot.py - policy_override)**
   ```python
   self.state_machine.transition_to(
       next_state=policy_next_state,
       action=decision.action,
       source="policy_override"
   )
   ```

3. **Bot.py (src/bot.py - fallback_skip)**
   ```python
   self.state_machine.transition_to(
       skip_next_state,
       source="fallback_skip"
   )
   ```

**Миграция от старого подхода:**

```python
# СТАРЫЙ КОД (не использовать):
sm.state = "spin_problem"
sm.current_phase = "problem"
sm.last_action = "ask_problem_questions"

# НОВЫЙ КОД (обязательно):
sm.transition_to(
    next_state="spin_problem",
    action="ask_problem_questions",
    source="my_component"
)
```

**Тесты:**
- `tests/test_transition_atomicity.py` (348 тестов)
- `tests/test_blackboard_orchestrator.py` (использование в orchestrator)
- `tests/test_bugfixes_verified.py` (регрессионные тесты)

##### `sync_phase_from_state() -> None` NEW

**Safety net для синхронизации current_phase из state**

Этот метод синхронизирует `current_phase` с текущим значением `state`, используя `FlowConfig.get_phase_for_state()`.

```python
# Legacy код напрямую изменил state
sm.state = "spin_problem"
sm.current_phase = "wrong_phase"  # Устарело

# Синхронизация
sm.sync_phase_from_state()

# Теперь current_phase корректен
assert sm.current_phase == "problem"
```

**Когда использовать:**

Этот метод является **страховочной сеткой** для обратной совместимости с legacy кодом, который ещё напрямую модифицирует `state_machine.state`.

**НЕ РЕКОМЕНДУЕТСЯ** для нового кода — используйте `transition_to()` вместо этого.

**Применение:**

Universal phase resolution (коммит 3e6a8eb) обеспечивает работу метода со всеми 21 flows:
- Использует `FlowConfig.get_phase_for_state()` для определения фазы
- Для SPIN: читает явное поле `state_config.phase`
- Для BANT, MEDDIC и других: использует reverse mapping из `phase_mapping`

**Фундаментальное исправление:**

До коммита 3e6a8eb метод использовал хардкоженный `_STATE_TO_PHASE` только для SPIN, что ломало 20 из 21 flows. Теперь работает универсально.

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
| `max_consecutive_objections` | `int` | Config → constants.yaml (3) CONFIGURABLE |
| `max_total_objections` | `int` | Config → constants.yaml (5) CONFIGURABLE |
| `max_turns_in_state` | `int` | _base_phase → 5 (was 6) |
| `phase_exhaust_threshold` | `int` | _base_phase → 4 (NEW) |
| `max_simulation_consecutive` | `int` | Auto-derived: max_turns_in_state + 1 |
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

### 2.3 Класс `CircularFlowManager` - REFACTORED as SSOT

**Single Source of Truth** для всей go_back логики (коммит dc336c9).

CircularFlowManager управляет возвратами назад по фазам диалога с защитой от злоупотреблений. Это централизованный компонент, который:
- Отслеживает количество совершенных возвратов
- Проверяет лимиты (max_gobacks)
- Хранит историю переходов
- Интегрируется с Blackboard через GoBackGuardSource

```python
from src.state_machine import CircularFlowManager

manager = CircularFlowManager(
    allowed_gobacks={
        "spin_problem": "spin_situation",
        "spin_implication": "spin_problem",
        "spin_need_payoff": "spin_implication",
        "presentation": "spin_need_payoff",
        "close": "presentation",
        "handle_objection": "presentation",
        "soft_close": "greeting",  # Новая попытка
    },
    max_gobacks=2  # Максимум возвратов за диалог
)

# Проверка возможности возврата
if manager.can_go_back("spin_problem"):
    prev_state = manager.get_go_back_target("spin_problem")
    print(f"Can go back to: {prev_state}")  # "spin_situation"

# После успешного перехода (вызывается orchestrator)
manager.record_go_back("spin_problem", "spin_situation")

# Статистика
stats = manager.get_stats()
# {
#     "goback_count": 1,
#     "remaining": 1,
#     "history": [("spin_problem", "spin_situation")]
# }
```

**FUNDAMENTAL CHANGE:** CircularFlowManager теперь единственный источник правды для go_back решений, исключая дублирование логики.

#### Константы по умолчанию

```python
MAX_GOBACKS = 2  # Максимум возвратов за диалог

# Если allowed_gobacks не передан в конструктор,
# используется ALLOWED_GOBACKS из constants.yaml
```

Пример `constants.yaml`:

```yaml
circular_flow:
  allowed_gobacks:
    spin_problem: spin_situation
    spin_implication: spin_problem
    spin_need_payoff: spin_implication
    presentation: spin_need_payoff
    close: presentation
    handle_objection: presentation
    soft_close: greeting
```

#### Архитектура и интеграция

**UNIFIED GO_BACK LOGIC:**

CircularFlowManager — это ЕДИНСТВЕННЫЙ ИСТОЧНИК ПРАВДЫ для go_back логики. Он обрабатывает оба способа определения целевого состояния:

1. **allowed_gobacks map** (legacy, для SPIN states из constants.yaml)
2. **YAML transitions** (`go_back: "{{prev_phase_state}}"` в любом flow)

GoBackGuardSource должен использовать методы из этого класса вместо дублирования логики.

**Интеграция с Blackboard (v3.0):**

```
┌─────────────────────────────────────────────────────────┐
│             Blackboard Pipeline (v3.0)                   │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  1. User sends "go_back" intent                          │
│                                                          │
│  2. GoBackGuardSource.contribute()                       │
│     ├─ Get CircularFlowManager from state_machine        │
│     ├─ Check limit: is_limit_reached()                   │
│     ├─ Get target: get_go_back_target(state, yaml_trans) │
│     └─ If allowed:                                       │
│        └─ Propose "acknowledge_go_back" action           │
│           with pending_goback_increment=True metadata    │
│                                                          │
│  3. ConflictResolver resolves proposals                  │
│     ├─ ObjectionGuardSource might BLOCK with CRITICAL    │
│     └─ Or GoBackGuard wins with "acknowledge_go_back"    │
│                                                          │
│  4. Orchestrator._apply_deferred_goback_increment()      │
│     ├─ Check: decision.action == "acknowledge_go_back"?  │
│     ├─ Check: state actually changed?                    │
│     └─ If YES:                                           │
│        └─ circular_flow.record_go_back(from, to)         │
│           └─ Increments goback_count                     │
│           └─ Adds to goback_history                      │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

#### Методы

| Метод | Сигнатура | Описание |
|-------|-----------|----------|
| `can_go_back(current_state, yaml_transitions=None)` | `-> bool` | **CANONICAL CHECK**: Проверяет возможность возврата (лимит НЕ достигнут И целевое состояние существует). Приоритет: 1) лимит, 2) YAML transitions, 3) allowed_gobacks |
| `is_limit_reached()` | `-> bool` | Проверка лимита: `goback_count >= max_gobacks` |
| `get_go_back_target(current_state, yaml_transitions=None)` | `-> Optional[str]` | **CANONICAL LOOKUP**: Получить целевое состояние для go_back. Приоритет: 1) YAML transitions, 2) allowed_gobacks map |
| `record_go_back(from_state, to_state)` | `-> None` | **DEFERRED INCREMENT**: Записывает успешный go_back переход. Вызывается Orchestrator ПОСЛЕ подтверждения перехода. Инкрементирует счетчик и добавляет в историю |
| `go_back(current_state)` | `-> Optional[str]` | **LEGACY METHOD**: Выполнить возврат (deprecated, использовать can_go_back + record_go_back) |
| `get_remaining_gobacks()` | `-> int` | Оставшееся количество возвратов: `max(0, max_gobacks - goback_count)` |
| `get_history()` | `-> List[tuple]` | История возвратов: список кортежей `(from_state, to_state)` |
| `get_stats()` | `-> Dict` | Статистика для аналитики: `{"goback_count", "remaining", "history"}` |
| `reset()` | `-> None` | Сброс для нового разговора: `goback_count = 0`, `goback_history = []` |

#### Deferred Increment Pattern (коммит ff3e620)

**ПРОБЛЕМА (BUG FIXED):**

До внедрения deferred increment, GoBackGuardSource инкрементировал счетчик `goback_count` напрямую в методе `contribute()` — ДО conflict resolution.

Это вызывало баг:
```python
# Сценарий бага:
1. User: "go_back" (3-е возражение подряд)
2. GoBackGuardSource.contribute():
   - goback_count++ (0 -> 1)  # ИНКРЕМЕНТ ДО РЕЗОЛЮЦИИ!
   - Propose: action="acknowledge_go_back"
3. ObjectionGuardSource.contribute():
   - objection_consecutive == 3 -> LIMIT!
   - Propose: action="objection_limit_reached", priority=CRITICAL
4. ConflictResolver:
   - CRITICAL wins -> action="objection_limit_reached"
   - Go back BLOCKED!
5. Результат:
   - State: "soft_close" (go_back не произошел)
   - goback_count: 1 (но возврат НЕ произошел!) ❌
```

**РЕШЕНИЕ (Deferred Increment):**

1. **GoBackGuardSource.contribute():**
   - НЕ инкрементирует счетчик
   - Добавляет `pending_goback_increment=True` в proposal metadata
   - Добавляет `from_state`, `to_state` в metadata

2. **Orchestrator._apply_deferred_goback_increment():**
   - Вызывается ПОСЛЕ conflict resolution
   - Проверяет условия:
     - `decision.action == "acknowledge_go_back"`?
     - `state_changed == True`? (переход действительно произошел)
     - `metadata.pending_goback_increment == True`?
     - `actual_next_state == expected_to_state`?
   - ТОЛЬКО ЕСЛИ все условия выполнены:
     - `circular_flow.record_go_back(from_state, to_state)`

3. **CircularFlowManager.record_go_back():**
   - Инкрементирует `goback_count`
   - Добавляет `(from_state, to_state)` в `goback_history`
   - Логирует переход

**Корректный сценарий:**

```python
# С deferred increment:
1. User: "go_back" (3-е возражение подряд)
2. GoBackGuardSource.contribute():
   - Propose: action="acknowledge_go_back",
     metadata={"pending_goback_increment": True, "to_state": "spin_situation"}
   # НЕ ИНКРЕМЕНТИРУЕТ!
3. ObjectionGuardSource.contribute():
   - Propose: action="objection_limit_reached", priority=CRITICAL
4. ConflictResolver:
   - CRITICAL wins -> decision.action="objection_limit_reached"
5. Orchestrator._apply_deferred_goback_increment():
   - decision.action != "acknowledge_go_back"
   - SKIP INCREMENT
6. Результат:
   - State: "soft_close"
   - goback_count: 0 (корректно — возврат НЕ произошел!) ✅
```

**Код Orchestrator._apply_deferred_goback_increment():**

```python
def _apply_deferred_goback_increment(
    self,
    decision: ResolvedDecision,
    prev_state: str,
    state_changed: bool,
) -> None:
    # Только если winning action — acknowledge_go_back
    if decision.action != "acknowledge_go_back":
        return

    # Только если state действительно изменился
    if not state_changed:
        logger.debug("Deferred goback increment SKIPPED: state did not change")
        return

    # Получить metadata из resolution trace
    winning_metadata = decision.resolution_trace.get("winning_action_metadata", {})

    # Проверить pending flag
    if not winning_metadata.get("pending_goback_increment"):
        return

    # Проверить что переход пошел в ожидаемое состояние
    expected_to_state = winning_metadata.get("to_state")
    if expected_to_state and decision.next_state != expected_to_state:
        logger.warning(f"Deferred goback increment SKIPPED: unexpected transition")
        return

    # ИНКРЕМЕНТ через CircularFlowManager (SSOT)
    circular_flow = self._state_machine.circular_flow
    circular_flow.record_go_back(
        from_state=winning_metadata.get("from_state", prev_state),
        to_state=decision.next_state
    )
```

**Ключевые файлы:**
- `src/state_machine.py:59-239` — CircularFlowManager implementation
- `src/blackboard/orchestrator.py:581-648` — _apply_deferred_goback_increment()
- `src/blackboard/sources/go_back_guard.py` — GoBackGuardSource integration
- `tests/test_go_back_guard.py` — тесты deferred increment

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

## 2.5 Configurable Objection Limits NEW

Лимиты возражений теперь читаются из `constants.yaml` вместо хардкода (коммит 204ec70).

**BREAKING:** Objection limits are now read from YAML config instead of hardcoded values.

**Проблема:**
- Limits (max_consecutive_objections=3, max_total_objections=5) были хардкодены в 12+ местах
- Изменение limits в constants.yaml не влияло на conditions.py
- Несогласованность между StateMachine и RuleResolver

**Решение:**
```yaml
# constants.yaml
limits:
  max_consecutive_objections: 3
  max_total_objections: 5
```

**Изменения:**
- Добавлены max_consecutive_objections/max_total_objections поля в EvaluatorContext
- Добавлены те же поля в PolicyContext
- Все condition функции используют ctx.max_* вместо хардкода
- Обновлены все другие места (hybrid.py, client_agent.py, etc.)
- 10 comprehensive тестов для configurable limits

---

## 2.6 Universal Phase Resolution NEW

Все 21 flows теперь работают с phase detection (коммит 3e6a8eb).

**Проблема:**
- _STATE_TO_PHASE в context.py был хардкоден из SPIN_STATES
- Custom flows (BANT, MEDDIC, etc.) определяли фазы в flow.yaml, но auto-compute current_phase никогда не работал
- 20 из 21 flows имели сломанное определение фазы

**Решение:**
```python
# FlowConfig.state_to_phase property (reverse mapping)
# FlowConfig.get_phase_for_state() - canonical method

# Было:
_STATE_TO_PHASE = {v: k for k, v in SPIN_STATES.items()}  # только SPIN

# Стало:
@property
def state_to_phase(self) -> Dict[str, str]:
    """Reverse mapping: state -> phase (includes explicit phases)."""
    mapping = {state: phase for phase, state in self.phase_mapping.items()}
    # Add explicit phases (override mapping)
    for state, config in self.states.items():
        if "phase" in config:
            mapping[state] = config["phase"]
    return mapping
```

**Изменения:**
- FlowConfig.state_to_phase property (reverse mapping)
- FlowConfig.get_phase_for_state() как canonical метод
- EvaluatorContext.__post_init__ использует flow_config
- StateMachine.transition_to() и sync_phase_from_state() обновлены
- Orchestrator phase resolution обновлен
- ContextSnapshot с state_to_phase полем
- IFlowConfig protocol с новыми методами
- Все test mocks обновлены

**Результат:** Все 21 flows теперь корректно работают с phase detection.

---

## 2.7 State Before Objection Tracking NEW

Автоматическое отслеживание состояния до возражения (коммит dc90e23).

**Проблема:**
- _state_before_objection никогда не устанавливался или не сбрасывался
- get_return_state() всегда возвращал None
- Bot не мог вернуться к корректному состоянию после обработки возражений

**Решение:**
```python
# orchestrator._apply_side_effects()
def _update_state_before_objection(prev_state, next_state, intent):
    if next_state == "handle_objection" and prev_state != "handle_objection":
        self._state_before_objection = prev_state  # Save
    elif intent in POSITIVE_INTENTS and intent_tracker.objection_consecutive_streak_broken():
        self._state_before_objection = None  # Clear on positive intent
    elif next_state != "handle_objection" and prev_state == "handle_objection":
        self._state_before_objection = None  # Clear when leaving normally
```

**Изменения:**
- _update_state_before_objection() в orchestrator._apply_side_effects()
  - Сохраняет prev_state при входе в handle_objection
  - Очищает при позитивном intent когда streak breaks
  - Очищает при выходе из handle_objection normally
- _update_state_before_objection_legacy() в StateMachine для обратной совместимости
- transition_to() метод добавлен в test mock StateMachine классы

**Результат:** Исправлен broken objection series tracking flow.

---

## 3. Atomic State Transitions

### 3.1 Проблема: Distributed State Mutation Bug

До внедрения atomic transitions (январь 2026), система имела критическую архитектурную проблему: различные компоненты напрямую модифицировали `state_machine.state`, что приводило к рассинхронизации между `state`, `current_phase` и `last_action`.

#### Сценарий бага

```python
# === Шаг 1: Orchestrator устанавливает состояние ===
# src/blackboard/orchestrator.py:_apply_side_effects()

state_machine.state = "spin_problem"
state_machine.current_phase = "problem"
state_machine.last_action = "ask_problem_questions"

# Состояние СОГЛАСОВАННО:
# state="spin_problem", current_phase="problem", last_action="ask_problem_questions"

# === Шаг 2: Bot.py (policy_override) изменяет состояние ===
# src/bot.py (policy_override logic)

state_machine.state = "spin_implication"  # ТОЛЬКО state!
# Забыли обновить current_phase и last_action!

# Состояние РАССИНХРОНИЗИРОВАНО:
# state="spin_implication", current_phase="problem", last_action="ask_problem_questions"
#                            ^^^^^^^^^^^^^^^^^^^^^^
#                            НЕСОГЛАСОВАННОСТЬ!
```

#### Последствия бага

1. **Неверное определение required_data**
   ```python
   config = states_config.get(state)  # spin_implication config
   required = config.get("required_data", [])  # ["implication_probed"]

   # Но current_phase="problem", поэтому условия думают что мы в Problem фазе
   # Ожидают pain_point, а не implication_probed
   ```

2. **Некорректная работа условий**
   ```python
   def in_implication_phase(ctx):
       return ctx.current_phase == "implication"

   # ctx.state = "spin_implication"
   # ctx.current_phase = "problem"  # НЕСОГЛАСОВАННОСТЬ!
   # in_implication_phase() -> False (неверно!)
   ```

3. **Промпты для неправильной фазы**
   ```python
   # Генератор промптов использует current_phase
   phase = state_machine.current_phase  # "problem"
   prompt = prompt_templates[phase]  # Промпт для Problem фазы
   # Но state="spin_implication" -> отправляем неверный промпт
   ```

4. **Ошибки в логах и аналитике**
   ```python
   logger.info(f"State: {state}, Phase: {current_phase}")
   # "State: spin_implication, Phase: problem" <- сбивает с толку при отладке
   ```

### 3.2 Решение: transition_to() Method

Метод `transition_to()` обеспечивает атомарное обновление всех трёх атрибутов состояния, предотвращая рассинхронизацию.

#### API

```python
def transition_to(
    self,
    next_state: str,
    action: Optional[str] = None,
    phase: Optional[str] = None,
    source: str = "unknown",
    validate: bool = True,
) -> bool:
    """
    Atomically transition to a new state with consistent updates.

    Args:
        next_state: Target state to transition to
        action: Action that triggered this transition (optional)
        phase: Phase for the new state (computed from config if not provided)
        source: Identifier for debugging (e.g., "orchestrator", "policy_override")
        validate: If True, validate that next_state exists in flow config

    Returns:
        True if transition was successful, False if validation failed
    """
```

#### Внутренняя реализация

```python
def transition_to(self, next_state, action=None, phase=None, source="unknown", validate=True):
    prev_state = self.state

    # 1. ВАЛИДАЦИЯ: проверить существование целевого состояния
    if validate and self._flow:
        if next_state not in self._flow.states:
            logger.warning(
                f"transition_to: Invalid state '{next_state}' - not in flow config",
                source=source,
                current_state=prev_state,
            )
            return False

    # 2. ВЫЧИСЛЕНИЕ PHASE: автоматически определить через FlowConfig
    if phase is None and self._flow:
        phase = self._flow.get_phase_for_state(next_state)
        # Для SPIN: использует явное поле state_config.phase
        # Для BANT, MEDDIC: использует reverse mapping из phase_mapping

    # 3. АТОМАРНОЕ ОБНОВЛЕНИЕ: все три атрибута вместе
    self.state = next_state
    self.current_phase = phase
    if action is not None:
        self.last_action = action

    # 4. ЛОГИРОВАНИЕ: записать переход для отладки
    if prev_state != next_state:
        logger.debug(
            f"State transition: {prev_state} -> {next_state}",
            phase=phase,
            action=action,
            source=source,
        )

    return True
```

#### Использование в кодовой базе

**1. Orchestrator (основной путь):**

```python
# src/blackboard/orchestrator.py:529
def _apply_side_effects(self, decision, prev_state, state_changed):
    # Compute phase from flow config
    phase = self._flow_config.get_phase_for_state(decision.next_state)

    # ATOMIC TRANSITION
    self._state_machine.transition_to(
        next_state=decision.next_state,
        action=final_action,
        phase=phase,
        source="orchestrator",
        validate=False,  # Already validated by ProposalValidator
    )

    # РЕЗУЛЬТАТ (гарантированно согласованный):
    # state=decision.next_state
    # current_phase=phase (из flow config)
    # last_action=final_action
```

**2. Bot.py (policy_override):**

```python
# src/bot.py (policy override logic)
if policy_override and policy_next_state:
    self.state_machine.transition_to(
        next_state=policy_next_state,
        action=decision.action,
        source="policy_override"
    )
    # Phase вычисляется автоматически через flow config
    # Никакой рассинхронизации!
```

**3. Bot.py (fallback_skip):**

```python
# src/bot.py (fallback skip logic)
if skip_next_state:
    self.state_machine.transition_to(
        skip_next_state,
        source="fallback_skip"
    )
```

### 3.3 Migration Guide

#### От старого подхода к transition_to()

**ПЛОХО (не использовать):**

```python
# Распределенная мутация — источник багов
sm.state = "spin_problem"
sm.current_phase = "problem"
sm.last_action = "ask_problem_questions"

# Или ещё хуже — забыть обновить current_phase:
sm.state = "spin_implication"  # НЕСОГЛАСОВАННОСТЬ!
```

**ХОРОШО (обязательно использовать):**

```python
# Атомарная транзакция — все поля обновляются вместе
sm.transition_to(
    next_state="spin_problem",
    action="ask_problem_questions",
    source="my_component"
)

# РЕЗУЛЬТАТ (гарантированно):
# state="spin_problem"
# current_phase="problem" (из flow config)
# last_action="ask_problem_questions"
```

#### Миграция существующего кода

**Шаг 1: Поиск прямых присваиваний**

```bash
# Найти все места, где state изменяется напрямую
grep -rn "state_machine.state = " src/
grep -rn "self.state = " src/state_machine.py
```

**Шаг 2: Замена на transition_to()**

```python
# БЫЛО:
state_machine.state = "spin_situation"
state_machine.current_phase = "situation"
state_machine.last_action = "probe_situation"

# СТАЛО:
state_machine.transition_to(
    next_state="spin_situation",
    action="probe_situation",
    source="my_component_name"
)
```

**Шаг 3: Если нужна только смена state (без action)**

```python
# БЫЛО:
state_machine.state = "presentation"

# СТАЛО:
state_machine.transition_to(
    next_state="presentation",
    source="my_component_name"
)
# last_action сохраняется, current_phase вычисляется
```

**Шаг 4: Для legacy кода с прямым изменением state**

```python
# Если изменение кода невозможно (legacy библиотека и т.д.):
state_machine.state = "spin_problem"  # Legacy код

# Добавить sync_phase_from_state() сразу после
state_machine.sync_phase_from_state()
# Синхронизирует current_phase с state
```

### 3.4 Universal Phase Resolution

`transition_to()` использует `FlowConfig.get_phase_for_state()` для универсального определения фазы, что обеспечивает работу со всеми 21 flows.

#### До исправления (только SPIN)

```python
# OLD CODE (hardcoded для SPIN):
_STATE_TO_PHASE = {
    "spin_situation": "situation",
    "spin_problem": "problem",
    "spin_implication": "implication",
    "spin_need_payoff": "need_payoff",
}

def sync_phase_from_state(self):
    self.current_phase = _STATE_TO_PHASE.get(self.state)
    # Работает только для SPIN!
    # BANT, MEDDIC, MEDDPICC, CHAMP, etc. — СЛОМАНО
```

#### После исправления (все 21 flows)

```python
# NEW CODE (universal):
def transition_to(self, next_state, ...):
    # ...
    if phase is None and self._flow:
        # FlowConfig.get_phase_for_state() - универсальный метод
        phase = self._flow.get_phase_for_state(next_state)
    # ...

# FlowConfig.get_phase_for_state() implementation:
def get_phase_for_state(self, state: str) -> Optional[str]:
    """
    Universal phase resolution for ALL flows.

    Priority:
    1. Explicit state_config.phase (SPIN uses this)
    2. Reverse mapping from phases.mapping (BANT, MEDDIC use this)
    """
    # Priority 1: Explicit phase in state config
    state_config = self.states.get(state, {})
    if "phase" in state_config:
        return state_config["phase"]

    # Priority 2: Reverse mapping from phase_mapping
    for phase_name, phase_state in self.phase_mapping.items():
        if phase_state == state:
            return phase_name

    return None
```

#### Примеры для разных flows

**SPIN Selling (explicit phase field):**

```yaml
# flows/spin_selling/states.yaml
states:
  spin_problem:
    phase: problem  # Explicit field
    goal: "Identify customer problems"
```

```python
# Code:
sm.transition_to("spin_problem")
# state="spin_problem", current_phase="problem" (from explicit field)
```

**BANT (reverse mapping):**

```yaml
# flows/bant/flow.yaml
phases:
  mapping:
    budget: assess_budget
    authority: identify_decision_maker
    need: qualify_need
    timing: determine_timeline
```

```python
# Code:
sm.transition_to("assess_budget")
# state="assess_budget", current_phase="budget" (from reverse mapping)
```

### 3.5 Safety Net: sync_phase_from_state()

Для обратной совместимости с legacy кодом, который напрямую изменяет `state`, существует метод `sync_phase_from_state()`.

```python
def sync_phase_from_state(self) -> None:
    """
    Synchronize current_phase with the current state.

    Call this after external code directly modifies state_machine.state
    to ensure current_phase is consistent.

    This is a SAFETY NET for backward compatibility.
    """
    if self._flow:
        self.current_phase = self._flow.get_phase_for_state(self.state)
```

#### Когда использовать

**Сценарий 1: Legacy код напрямую изменил state**

```python
# Legacy library (cannot modify):
state_machine.state = "spin_implication"

# Add sync immediately after:
state_machine.sync_phase_from_state()
# current_phase="implication" (corrected)
```

**Сценарий 2: Десериализация состояния**

```python
# Restore state from database
state_machine.state = saved_state
state_machine.collected_data = saved_data

# Sync phase (may not be saved):
state_machine.sync_phase_from_state()
```

**НЕ РЕКОМЕНДУЕТСЯ для нового кода** — используйте `transition_to()` вместо этого.

### 3.6 Integration with Blackboard v3.0

Atomic transitions критичны для Blackboard Architecture, где orchestrator координирует множество Knowledge Sources.

#### Orchestrator._apply_side_effects()

```python
def _apply_side_effects(self, decision, prev_state, state_changed):
    """
    Apply side effects after conflict resolution.

    CRITICALLY IMPORTANT: Uses transition_to() for atomic updates.
    This prevents distributed state mutation when bot.py also modifies state.
    """
    # Get state configuration for on_enter logic
    next_config = self._flow_config.states.get(decision.next_state, {})

    # Compute final action (considering on_enter override)
    final_action = decision.action
    if state_changed:
        on_enter = next_config.get("on_enter")
        if on_enter:
            on_enter_action = on_enter.get("action") if isinstance(on_enter, dict) else on_enter
            if on_enter_action:
                final_action = on_enter_action

    # ATOMIC STATE TRANSITION via transition_to()
    phase = self._flow_config.get_phase_for_state(decision.next_state)
    self._state_machine.transition_to(
        next_state=decision.next_state,
        action=final_action,
        phase=phase,
        source="orchestrator",
        validate=False,  # Already validated by ProposalValidator
    )

    # Apply data_updates, flags, deferred goback increment, etc.
    # ...
```

#### Knowledge Sources не модифицируют state напрямую

Knowledge Sources работают через proposals, которые разрешаются в ConflictResolver. State изменяется ТОЛЬКО через orchestrator:

```python
# src/blackboard/sources/go_back_guard.py
class GoBackGuardSource(KnowledgeSource):
    def contribute(self, blackboard):
        # PROPOSE transition (не изменяет state напрямую)
        blackboard.propose_transition(
            next_state=prev_state,
            priority=Priority.NORMAL,
            reason_code="go_back_allowed"
        )
        # State изменится ТОЛЬКО если proposal выиграет в ConflictResolver
        # И ТОЛЬКО через orchestrator.transition_to()
```

### 3.7 Testing

Тесты для atomic transitions находятся в `tests/test_transition_atomicity.py` (348 тестов).

#### Ключевые тест-кейсы

**1. Атомарность обновления всех полей:**

```python
def test_transition_to_updates_all_fields_atomically(state_machine):
    """Verify that transition_to() updates state, current_phase, and last_action together."""
    state_machine.transition_to(
        next_state="spin_situation",
        action="ask_situation_questions",
        source="test",
    )

    assert state_machine.state == "spin_situation"
    assert state_machine.current_phase == "situation"  # from flow config
    assert state_machine.last_action == "ask_situation_questions"
```

**2. Воспроизведение бага (теперь исправлено):**

```python
def test_old_bug_scenario_now_fixed(state_machine):
    """
    Reproduce the exact bug scenario and verify it's fixed.

    Old code:
        orchestrator: state_machine.state = "spin_problem"
                     state_machine.current_phase = "problem"
        bot.py:      state_machine.state = "spin_implication"  # ONLY state!
        Result: state="spin_implication", phase="problem"  # BUG!

    New code (with transition_to()):
        orchestrator: state_machine.transition_to("spin_problem", ...)
        bot.py:      state_machine.transition_to("spin_implication", ...)
        Result: state="spin_implication", phase="implication"  # CORRECT!
    """
    # Step 1: Orchestrator transition
    state_machine.transition_to(
        next_state="spin_problem",
        action="ask_problem_questions",
        source="orchestrator",
    )

    assert state_machine.state == "spin_problem"
    assert state_machine.current_phase == "problem"

    # Step 2: Bot.py policy override (NOW USING transition_to!)
    state_machine.transition_to(
        next_state="spin_implication",
        action="ask_implication_questions",
        source="policy_override",
    )

    # Verify consistency
    assert state_machine.state == "spin_implication"
    assert state_machine.current_phase == "implication"  # CORRECT!
```

**3. Валидация целевого состояния:**

```python
def test_transition_to_validates_state_exists(state_machine):
    """Verify that invalid states are rejected when validate=True."""
    result = state_machine.transition_to(
        next_state="nonexistent_state",
        source="test",
        validate=True,
    )

    assert result is False
    # State should not change
    assert state_machine.state == "greeting"
```

**4. sync_phase_from_state() как safety net:**

```python
def test_sync_phase_from_state_corrects_mismatch(state_machine):
    """Verify that sync_phase_from_state() corrects phase after direct state mutation."""
    # Simulate direct state mutation (legacy code pattern)
    state_machine.state = "spin_problem"
    state_machine.current_phase = "wrong_phase"  # Intentional mismatch

    # Sync should correct the mismatch
    state_machine.sync_phase_from_state()

    assert state_machine.state == "spin_problem"
    assert state_machine.current_phase == "problem"  # Corrected
```

---

## 4. SPIN Selling Flow

### 13.1 Что такое SPIN Selling?

SPIN Selling — методология продаж, разработанная Нилом Рэкхэмом. Аббревиатура расшифровывается как:

- **S**ituation — понять текущую ситуацию
- **P**roblem — выявить проблемы
- **I**mplication — показать последствия
- **N**eed-Payoff — сформировать ценность

### 13.2 Состояния и фазы

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

### 12.3 Переходы между состояниями

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

### 4.4 Прогресс-интенты

Интенты, указывающие на готовность к следующей фазе:

| Интент | Указывает на фазу |
|--------|-------------------|
| `situation_provided` | Situation завершена |
| `problem_revealed` | Problem завершена |
| `implication_acknowledged` | Implication завершена |
| `need_expressed` | Need-Payoff завершена |

### 4.5 Пропуск фаз

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

## 5. Система Приоритетов

### 13.1 Hardcoded приоритеты (Legacy)

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

### 13.2 Конфигурируемые приоритеты (YAML)

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

### 12.3 Поля конфигурации приоритета

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

## 6. Условные Правила (Conditional Rules)

### 13.1 Форматы правил

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

### 13.2 RuleResolver

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

### 12.3 Валидация конфигурации

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

## 7. IntentTracker

### 13.1 Назначение

`IntentTracker` — единый источник истории интентов. Отслеживает:

- Текущий и предыдущий интент
- Streak (подряд идущие одинаковые интенты)
- Totals (общее количество по интентам и категориям)
- Категории интентов

### 13.2 Использование

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

### 12.3 Категории интентов

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

### 10.4 Методы для возражений

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

## 8. YAML Конфигурация

### 13.1 Структура директории

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

### 13.2 constants.yaml

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

### 12.3 sales_flow.yaml

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

### 10.4 Mixins

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

#### Ключевые Mixins (коммиты 2838e8f, 5c2aad7)

**unified_progress** — универсальная архитектура для intent-to-transition mapping:
```yaml
# mixins.yaml
unified_progress:
  description: "Универсальное отображение progress интентов на переходы"
  transitions:
    situation_provided: "{{next_phase_state}}"
    problem_revealed: "{{next_phase_state}}"
    implication_acknowledged: "{{next_phase_state}}"
    need_expressed: "{{next_phase_state}}"
  parameters:
    next_phase_state: null  # Переопределяется в каждом состоянии
```

**phase_progress** — предотвращение зацикливания на progress интентах:
```yaml
# mixins.yaml
phase_progress:
  description: "Обработка progress интентов для всех flow"
  transitions:
    situation_provided: "{{next_phase_state}}"
    problem_revealed: "{{next_phase_state}}"
    implication_acknowledged: "{{next_phase_state}}"
    need_expressed: "{{next_phase_state}}"
  parameters:
    next_phase_state: null  # REQUIRED: следующее состояние фазы
```

**Проблема без phase_progress:**
Когда классификатор возвращает progress интенты в non-SPIN flow, отсутствие transitions приводило к зацикливанию до срабатывания ConversationGuard (76% диалогов).

**Результаты:**
- soft_close rate: 76% → 63%
- success rate: 24% → 37%
- Все 60 e2e тестов проходят (20 techniques × 3 personas)

**Новые objection handlers** (коммит 2838e8f):
```yaml
# mixins.yaml
objection_handling:
  rules:
    objection_complexity: handle_objection_complexity
    objection_timing: handle_objection_timing
    objection_trust: handle_objection_trust
    objection_no_need: handle_objection_no_need
    # ... существующие objection handlers
```

**Улучшенная обработка возражений** (коммит 735751b):

Все возражения теперь маршрутизируются в `handle_objection` через условные переходы:
```yaml
# mixins.yaml (до)
objection_handling:
  transitions:
    objection_no_time: soft_close  # Немедленный soft_close (плохо!)
    objection_think: soft_close    # Немедленный soft_close (плохо!)

# mixins.yaml (после)
objection_handling:
  transitions:
    objection_no_time:
      - when: objection_limit_reached
        then: soft_close
      - handle_objection  # Default: обработать возражение
    objection_think:
      - when: objection_limit_reached
        then: soft_close
      - handle_objection  # Default: обработать возражение
```

**Результаты:**
- soft_close при первом возражении: 92% → **0%**
- soft_close только при достижении лимита (3 подряд ИЛИ 5 всего)

### 8.5 Модульные Flow

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

## 9. Условия (Conditions)

### 13.1 EvaluatorContext

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

### 13.2 Категории условий

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

#### Phase Completion Conditions NEW

Условия для корректного phase gating.

| Условие | Описание |
|---------|----------|
| `has_completed_minimum_phases` | turn≥6 OR (size+pain) OR terminal state |
| `phase_exhausted` | consecutive_same_state ≥ phase_exhaust_threshold |
| `has_extracted_data` | DataExtractor нашел business data (company_size, pain_point, etc.) |

**has_completed_minimum_phases:**
- Предотвращает преждевременный переход к close
- Требует минимум: turn≥6 OR (company_size AND pain_point) OR terminal_state
- Используется в close_shortcuts transitions с conditional logic

**phase_exhausted:**
- Exclusive window: [phase_exhaust_threshold, stall_soft)
- phase_exhaust_threshold=4 (configurable в _base_phase)
- Triggers PhaseExhaustedSource для offer_options

**has_extracted_data:**
- Предотвращает false stall detection
- Компенсирует timing lag в context_window
- Проверяет наличие company_size, pain_point, business_type в extracted_data

**Feature flag:** phase_completion_gating
**SSoT:** [src/conditions/state_machine/conditions.py](../src/conditions/state_machine/conditions.py)

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

### 12.3 Регистрация условий

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

### 10.4 Использование в YAML

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

## 10. Примеры Использования

### 13.1 Базовое использование

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

### 13.2 С YAML конфигурацией

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

### 12.3 С модульным Flow

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

### 10.4 Использование Atomic Transitions (v3.0) NEW

```python
from src.state_machine import StateMachine

sm = StateMachine()

# === ПРАВИЛЬНЫЙ СПОСОБ: Использовать transition_to() ===

# 1. Базовый переход
sm.transition_to(
    next_state="spin_situation",
    action="ask_situation_questions",
    source="my_component"
)
# Результат: state="spin_situation", current_phase="situation", last_action="ask_situation_questions"

# 2. Переход без изменения action (last_action сохраняется)
sm.transition_to(
    next_state="spin_problem",
    source="orchestrator"
)
# Результат: state="spin_problem", current_phase="problem", last_action="ask_situation_questions"

# 3. Переход с явной phase (override автоматического определения)
sm.transition_to(
    next_state="custom_state",
    action="custom_action",
    phase="custom_phase",
    source="custom_component",
    validate=False  # Skip validation for custom states
)

# 4. Валидация целевого состояния
success = sm.transition_to(
    next_state="nonexistent_state",
    source="test",
    validate=True  # Default
)
if not success:
    print("Transition failed: invalid state")

# === НЕПРАВИЛЬНЫЙ СПОСОБ: НЕ изменять state напрямую ===
# sm.state = "spin_problem"  # ❌ НЕСОГЛАСОВАННОСТЬ!
# sm.current_phase = "problem"  # ❌ РАСПРЕДЕЛЕННАЯ МУТАЦИЯ!

# === LEGACY КОД: Использовать sync_phase_from_state() ===
# Если legacy код напрямую изменил state
sm.state = "spin_implication"  # Legacy library
sm.sync_phase_from_state()  # Sync phase
# Результат: state="spin_implication", current_phase="implication" (synced)
```

### 10.5 Интеграция с Blackboard Orchestrator (v3.0) NEW

```python
from src.blackboard import create_orchestrator
from src.state_machine import StateMachine
from src.config_loader import ConfigLoader

# Создание state machine
sm = StateMachine()

# Загрузка flow config
loader = ConfigLoader()
flow = loader.load_flow("spin_selling")

# Создание orchestrator
orchestrator = create_orchestrator(
    state_machine=sm,
    flow_config=flow
)

# === ОБРАБОТКА ХОДА ДИАЛОГА ===
decision = orchestrator.process_turn(
    intent="price_question",
    extracted_data={"company_size": 50},
    context_envelope=None,
    user_message="Сколько стоит?",
    frustration_level=0
)

# Orchestrator автоматически вызывает transition_to() в _apply_side_effects()
# state, current_phase, last_action обновлены атомарно

# === РЕЗУЛЬТАТ РЕШЕНИЯ ===
print(f"Action: {decision.action}")
print(f"Next State: {decision.next_state}")
print(f"Reason Codes: {decision.reason_codes}")

# === СТАТИСТИКА ===
print(f"Turn number: {sm.turn_number}")
print(f"Current phase: {sm.current_phase}")
print(f"Collected data: {sm.collected_data}")

# === ПРЕОБРАЗОВАНИЕ В ФОРМАТ STATE_MACHINE ===
sm_result = decision.to_sm_result()
# {
#     "action": "deflect_and_continue",
#     "prev_state": "greeting",
#     "next_state": "spin_situation",
#     "goal": "Understand customer situation",
#     "collected_data": {"company_size": 50},
#     "missing_data": [],
#     "is_final": False,
#     "spin_phase": "situation",
#     ...
# }
```

### 10.6 CircularFlowManager и Go Back (v3.0) NEW

```python
from src.state_machine import StateMachine, CircularFlowManager

sm = StateMachine()

# CircularFlowManager создается автоматически при создании StateMachine
# Читает конфигурацию из constants.yaml

# === ПРОВЕРКА ВОЗМОЖНОСТИ ВОЗВРАТА ===

# Текущее состояние
sm.state = "spin_problem"

# Проверить можно ли вернуться
if sm.circular_flow.can_go_back(sm.state):
    target = sm.circular_flow.get_go_back_target(sm.state)
    print(f"Can go back to: {target}")  # "spin_situation"

    # Оставшиеся возвраты
    remaining = sm.circular_flow.get_remaining_gobacks()
    print(f"Remaining go backs: {remaining}")  # 2

# === ИСПОЛЬЗОВАНИЕ С YAML TRANSITIONS ===

# Для универсальных flows с go_back в transitions:
transitions = {
    "go_back": "{{prev_phase_state}}",  # From YAML
    "rejection": "soft_close",
}

# Получить target с учетом YAML
target = sm.circular_flow.get_go_back_target(
    sm.state,
    yaml_transitions=transitions
)
# Приоритет: 1) YAML transitions, 2) allowed_gobacks

# === ИНТЕГРАЦИЯ С BLACKBOARD (v3.0) ===

# GoBackGuardSource автоматически использует CircularFlowManager:
# 1. Проверяет лимит через is_limit_reached()
# 2. Получает target через get_go_back_target()
# 3. Если allowed: propose action с pending_goback_increment=True
# 4. Orchestrator инкрементирует счетчик ТОЛЬКО если go_back выиграл

# Обработка go_back интента
decision = orchestrator.process_turn(
    intent="go_back",
    extracted_data={},
    context_envelope=None
)

# Если go_back разрешен и выиграл conflict resolution:
# - decision.action == "acknowledge_go_back"
# - decision.next_state == prev_state (из CircularFlowManager)
# - sm.circular_flow.goback_count инкрементирован (через record_go_back)

# Если go_back заблокирован (лимит или higher priority source):
# - decision.action может быть другой (e.g., "objection_limit_reached")
# - goback_count НЕ инкрементирован (deferred increment не произошел)

# === СТАТИСТИКА GO BACK ===
stats = sm.circular_flow.get_stats()
print(f"Go back count: {stats['goback_count']}")
print(f"Remaining: {stats['remaining']}")
print(f"History: {stats['history']}")
# {
#     'goback_count': 1,
#     'remaining': 1,
#     'history': [('spin_problem', 'spin_situation')]
# }

# === РУЧНОЙ КОНТРОЛЬ (для тестов) ===

# Проверить лимит явно
if sm.circular_flow.is_limit_reached():
    print("Go back limit reached!")

# Сбросить для нового диалога
sm.circular_flow.reset()
```

### 10.7 С ContextEnvelope

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

### 10.8 Полный жизненный цикл диалога

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

### 10.9 Обработка возражений

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

### 10.10 Возврат назад (Go Back) - Legacy Example

```python
from src.feature_flags import flags
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

## 11. Диаграммы и Схемы

### 13.1 Диаграмма состояний

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

### 13.2 Диаграмма обработки apply_rules()

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

### 12.3 Диаграмма компонентов

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

## 12. Тестирование

### 13.1 Основные тестовые файлы

| Файл | Описание |
|------|----------|
| `tests/test_transition_atomicity.py` | **Atomic state transitions** (348 тестов) NEW |
| `tests/test_blackboard_orchestrator.py` | **Blackboard orchestrator integration** (v3.0) NEW |
| `tests/test_go_back_guard.py` | **CircularFlowManager + GoBackGuardSource** NEW |
| `tests/test_state_machine_phase4.py` | Phase 4 интеграция |
| `tests/test_conditions_state_machine.py` | Все условия |
| `tests/test_state_machine_config.py` | ConfigLoader интеграция |
| `tests/test_intent_tracker.py` | IntentTracker |
| `tests/test_rules_resolver.py` | RuleResolver |
| `tests/test_bugfixes_verified.py` | Регрессионные тесты для критических багов |

### 13.2 Тесты Atomic Transitions (NEW)

#### Базовый тест атомарности

```python
def test_transition_to_updates_all_fields_atomically(state_machine):
    """Verify that transition_to() updates state, current_phase, and last_action together."""
    # Initial state
    assert state_machine.state == "greeting"
    assert state_machine.current_phase is None
    assert state_machine.last_action is None

    # Transition to spin_situation
    result = state_machine.transition_to(
        next_state="spin_situation",
        action="ask_situation_questions",
        source="test",
    )

    # All fields updated atomically
    assert result is True
    assert state_machine.state == "spin_situation"
    assert state_machine.current_phase == "situation"  # from flow config
    assert state_machine.last_action == "ask_situation_questions"
```

#### Тест distributed state mutation fix

```python
def test_old_bug_scenario_now_fixed(state_machine):
    """
    Reproduce the exact bug scenario and verify it's fixed.

    Old code:
        orchestrator: state_machine.state = "spin_problem"
                     state_machine.current_phase = "problem"
        bot.py:      state_machine.state = "spin_implication"  # ONLY state!
        Result: state="spin_implication", phase="problem"  # BUG!

    New code (with transition_to()):
        orchestrator: state_machine.transition_to("spin_problem", ...)
        bot.py:      state_machine.transition_to("spin_implication", ...)
        Result: state="spin_implication", phase="implication"  # CORRECT!
    """
    # Step 1: Orchestrator transition
    state_machine.transition_to(
        next_state="spin_problem",
        action="ask_problem_questions",
        source="orchestrator",
    )

    assert state_machine.state == "spin_problem"
    assert state_machine.current_phase == "problem"

    # Step 2: Bot.py policy override (NOW USING transition_to!)
    state_machine.transition_to(
        next_state="spin_implication",
        action="ask_implication_questions",
        source="policy_override",
    )

    # Verify consistency
    assert state_machine.state == "spin_implication"
    assert state_machine.current_phase == "implication"  # CORRECT!
```

#### Тест sync_phase_from_state (safety net)

```python
def test_sync_phase_from_state_corrects_mismatch(state_machine):
    """Verify that sync_phase_from_state() corrects phase after direct state mutation."""
    # Simulate direct state mutation (legacy code pattern)
    state_machine.state = "spin_problem"
    state_machine.current_phase = "wrong_phase"  # Intentional mismatch

    # Sync should correct the mismatch
    state_machine.sync_phase_from_state()

    assert state_machine.state == "spin_problem"
    assert state_machine.current_phase == "problem"  # Corrected
```

### 12.3 Тесты CircularFlowManager (NEW)

#### Тест deferred goback increment

```python
def test_deferred_goback_increment_when_go_back_wins():
    """
    Verify goback_count is incremented ONLY if go_back transition actually happens.
    """
    sm = StateMachine()
    orchestrator = create_orchestrator(sm, flow_config)

    # Initial state
    sm.state = "spin_problem"
    assert sm.circular_flow.goback_count == 0

    # Process go_back intent
    decision = orchestrator.process_turn(
        intent="go_back",
        extracted_data={},
        context_envelope=None
    )

    # If go_back wins:
    if decision.action == "acknowledge_go_back":
        # Counter SHOULD be incremented
        assert sm.circular_flow.goback_count == 1
        assert sm.state == "spin_situation"  # Went back
    else:
        # Counter SHOULD NOT be incremented
        assert sm.circular_flow.goback_count == 0


def test_deferred_goback_increment_not_incremented_when_blocked():
    """
    Verify goback_count is NOT incremented when higher-priority source blocks go_back.
    """
    sm = StateMachine()
    orchestrator = create_orchestrator(sm, flow_config)

    # Setup: 3 consecutive objections (triggers objection limit)
    sm.intent_tracker.record("objection_price", "presentation")
    sm.intent_tracker.record("objection_competitor", "handle_objection")
    sm.intent_tracker.record("objection_think", "handle_objection")

    # Current state
    sm.state = "spin_problem"
    initial_count = sm.circular_flow.goback_count

    # Process go_back intent (will be BLOCKED by ObjectionGuardSource)
    decision = orchestrator.process_turn(
        intent="go_back",
        extracted_data={},
        context_envelope=None
    )

    # ObjectionGuardSource should block with CRITICAL priority
    assert decision.action == "objection_limit_reached"
    assert decision.next_state == "soft_close"

    # Counter SHOULD NOT be incremented (go_back was blocked)
    assert sm.circular_flow.goback_count == initial_count
```

### 12.4 Примеры тестов

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

### 12.3 Запуск тестов

```bash
# Все тесты state machine
pytest tests/test_state_machine*.py -v

# Тесты условий
pytest tests/test_conditions_state_machine.py -v

# С покрытием
pytest tests/test_state_machine*.py --cov=src/state_machine --cov-report=html
```

---

## 13. FAQ и Troubleshooting

### 13.1 Часто задаваемые вопросы

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
from src.feature_flags import flags
flags.circular_flow = True
```

### 13.2 Troubleshooting

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

## 14. DAG State Machine

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
