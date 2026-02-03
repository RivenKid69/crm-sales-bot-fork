# Design Document: Архитектура и Принципы Проектирования

> **Версия:** 2.0
> **Дата:** Январь 2026
> **Статус:** Active

---

## Содержание

1. [Vision и Цели](#1-vision-и-цели)
2. [Классические Архитектурные Принципы](#2-классические-архитектурные-принципы)
3. [Операционные Архитектурные Принципы](#3-операционные-архитектурные-принципы)
4. [Blackboard Architecture](#4-blackboard-architecture)
5. [Plugin Architecture](#5-plugin-architecture)
6. [Configuration-Driven Development](#6-configuration-driven-development)
7. [Абстракции и Контракты](#7-абстракции-и-контракты)
8. [Multi-Tenancy и Изоляция](#8-multi-tenancy-и-изоляция)
9. [Расширяемость Flow](#9-расширяемость-flow)
10. [Best Practices](#10-best-practices)
11. [Roadmap](#11-roadmap)

---

## 1. Vision и Цели

### 1.1 Vision

Создать **универсальную платформу диалоговых ботов**, которая может быть адаптирована под любой бизнес-домен без изменения кодовой базы — только через конфигурацию и плагины.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Universal Conversational Platform                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐       │
│   │  CRM Sales  │  │  Support    │  │  HR/Recruit │  │  Custom     │       │
│   │  (SPIN)     │  │  (Routing)  │  │  (Screen)   │  │  Domain     │       │
│   └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘       │
│          │                │                │                │               │
│          └────────────────┴────────────────┴────────────────┘               │
│                                   │                                         │
│                    ┌──────────────▼──────────────┐                          │
│                    │      Core Platform          │                          │
│                    │  • State Machine Engine     │                          │
│                    │  • Plugin System            │                          │
│                    │  • Configuration Loader     │                          │
│                    │  • LLM Integration          │                          │
│                    └─────────────────────────────┘                          │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 Ключевые Цели

| Цель | Метрика | Текущий статус |
|------|---------|----------------|
| **Zero-code flow creation** | Новый flow без Python | [Done] YAML flows |
| **Domain independence** | Нет hardcode бизнес-логики | [Partial] (composed_categories) |
| **Blackboard decision-making** | Все решения через proposals | [Done] 10 Knowledge Sources |
| **Plugin extensibility** | Добавление функций через плагины | [Planned] |
| **Multi-tenant ready** | Изоляция данных между клиентами | [Planned] |
| **LLM agnostic** | Поддержка любой LLM | [Partial] |

### 1.3 Принцип "Convention over Configuration"

Система должна работать "из коробки" с разумными defaults, но позволять переопределить любой аспект:

```yaml
# Минимальный flow (defaults apply)
flow:
  name: simple_flow
  states:
    greeting:
      transitions:
        next: qualification
    qualification:
      transitions:
        done: success
    success:
      is_final: true

# Полный контроль (все явно)
flow:
  name: advanced_flow
  engine: dag  # or 'fsm'
  classifier: llm  # or 'hybrid', 'custom'
  generator: llm
  knowledge_base: cascade
  # ... все параметры
```

---

## 2. Классические Архитектурные Принципы

### 2.1 SOLID в контексте платформы

#### Single Responsibility (SRP)

Каждый компонент имеет одну причину для изменения:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Компонент         │ Ответственность              │ Не отвечает за          │
├───────────────────┼──────────────────────────────┼─────────────────────────│
│ Classifier        │ Определение intent           │ Генерация ответа        │
│ StateMachine      │ Управление flow              │ Бизнес-логика домена    │
│ Generator         │ Создание ответа              │ Выбор следующего состояния│
│ KnowledgeBase     │ Поиск информации             │ Интерпретация результата│
│ ConfigLoader      │ Загрузка конфигурации        │ Валидация бизнес-правил │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### Open/Closed Principle (OCP)

Система открыта для расширения через плагины, закрыта для модификации core:

```python
# ПЛОХО: Модификация core для нового classifier
class UnifiedClassifier:
    def classify(self, text):
        if self.type == "llm":
            return self._llm_classify(text)
        elif self.type == "hybrid":
            return self._hybrid_classify(text)
        elif self.type == "new_type":  # Изменение core!
            return self._new_classify(text)

# ХОРОШО: Расширение через registry
class ClassifierRegistry:
    _classifiers: Dict[str, Type[BaseClassifier]] = {}

    @classmethod
    def register(cls, name: str, classifier_class: Type[BaseClassifier]):
        cls._classifiers[name] = classifier_class

    @classmethod
    def get(cls, name: str) -> BaseClassifier:
        return cls._classifiers[name]()

# Регистрация без изменения core
ClassifierRegistry.register("my_classifier", MyCustomClassifier)
```

#### Liskov Substitution (LSP)

Любая реализация интерфейса должна быть взаимозаменяема:

```python
from abc import ABC, abstractmethod
from typing import Protocol

class ClassifierProtocol(Protocol):
    """Контракт для всех классификаторов"""

    def classify(self, text: str, context: Context) -> ClassificationResult:
        """
        Returns:
            ClassificationResult with:
            - intent: str
            - confidence: float (0.0-1.0)
            - extracted_data: Dict[str, Any]
        """
        ...

# Любая реализация должна соответствовать контракту
class LLMClassifier(ClassifierProtocol): ...
class HybridClassifier(ClassifierProtocol): ...
class RuleBasedClassifier(ClassifierProtocol): ...
```

#### Interface Segregation (ISP)

Маленькие, специализированные интерфейсы:

```python
# ПЛОХО: Монолитный интерфейс
class IBotEngine:
    def classify(self, text): ...
    def generate(self, action): ...
    def search_knowledge(self, query): ...
    def log_metrics(self, data): ...
    def send_notification(self, msg): ...

# ХОРОШО: Сегрегированные интерфейсы
class IClassifier(Protocol):
    def classify(self, text: str) -> ClassificationResult: ...

class IGenerator(Protocol):
    def generate(self, action: str, context: Context) -> str: ...

class IKnowledgeBase(Protocol):
    def search(self, query: str) -> List[Document]: ...

class IMetricsCollector(Protocol):
    def record(self, metric: str, value: float): ...
```

#### Dependency Inversion (DIP)

Зависимость от абстракций, не от конкретных реализаций:

```python
# ПЛОХО: Прямая зависимость
class SalesBot:
    def __init__(self):
        self.classifier = LLMClassifier()  # Жесткая связь
        self.generator = VLLMGenerator()   # Жесткая связь

# ХОРОШО: Dependency Injection
class SalesBot:
    def __init__(
        self,
        classifier: IClassifier,
        generator: IGenerator,
        knowledge: IKnowledgeBase,
    ):
        self.classifier = classifier
        self.generator = generator
        self.knowledge = knowledge

# Composition Root
def create_bot(config: Config) -> SalesBot:
    classifier = ClassifierRegistry.get(config.classifier_type)
    generator = GeneratorRegistry.get(config.generator_type)
    knowledge = KnowledgeRegistry.get(config.knowledge_type)

    return SalesBot(classifier, generator, knowledge)
```

### 2.2 Hexagonal Architecture (Ports & Adapters)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Adapters (Infrastructure)                       │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │
│  │ Telegram     │  │ WhatsApp     │  │ REST API    │  │ Voice        │    │
│  │ Adapter      │  │ Adapter      │  │ Adapter     │  │ Adapter      │    │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘    │
│         └──────────────────┴─────────────────┴──────────────────┘           │
│                                    │                                         │
│                         ┌──────────▼──────────┐                             │
│                         │   Input Port        │                             │
│                         │   (IMessageHandler) │                             │
│                         └──────────┬──────────┘                             │
│                                    │                                         │
├────────────────────────────────────┼────────────────────────────────────────┤
│                                    │                                         │
│                         ┌──────────▼──────────┐                             │
│                         │                     │                             │
│                         │    DOMAIN CORE      │                             │
│                         │                     │                             │
│                         │  • StateMachine     │                             │
│                         │  • FlowEngine       │                             │
│                         │  • BusinessRules    │                             │
│                         │                     │                             │
│                         └──────────┬──────────┘                             │
│                                    │                                         │
│                         ┌──────────▼──────────┐                             │
│                         │   Output Ports      │                             │
│                         │   (Interfaces)      │                             │
│                         └──────────┬──────────┘                             │
│                                    │                                         │
├────────────────────────────────────┼────────────────────────────────────────┤
│         ┌──────────────────────────┼───────────────────────────┐            │
│         │                          │                           │            │
│  ┌──────▼───────┐  ┌───────────────▼────────────┐  ┌──────────▼─────────┐  │
│  │ LLM Adapter  │  │ Knowledge Base Adapter     │  │ Storage Adapter    │  │
│  │ (Ollama)     │  │ (Vector/SQL/Elastic)       │  │ (Redis/Postgres)   │  │
│  └──────────────┘  └────────────────────────────┘  └────────────────────┘  │
│                              Adapters (Infrastructure)                       │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.3 Event-Driven Architecture

Все действия в системе генерируют события для аудита, аналитики и расширения:

```python
@dataclass
class DomainEvent:
    event_id: str
    timestamp: datetime
    event_type: str
    payload: Dict[str, Any]
    metadata: Dict[str, Any]

# Примеры событий
class Events:
    MESSAGE_RECEIVED = "message.received"
    INTENT_CLASSIFIED = "intent.classified"
    STATE_CHANGED = "state.changed"
    RESPONSE_GENERATED = "response.generated"
    LEAD_QUALIFIED = "lead.qualified"
    ERROR_OCCURRED = "error.occurred"

class EventBus:
    """Central event dispatcher"""

    def __init__(self):
        self._handlers: Dict[str, List[Callable]] = defaultdict(list)

    def subscribe(self, event_type: str, handler: Callable):
        self._handlers[event_type].append(handler)

    def publish(self, event: DomainEvent):
        for handler in self._handlers[event.event_type]:
            handler(event)
        # Also publish to wildcard subscribers
        for handler in self._handlers["*"]:
            handler(event)
```

---

## 3. Операционные Архитектурные Принципы

> Принципы из Раздела 2 описывают _классические_ паттерны проектирования.
> Этот раздел кодифицирует **операционные принципы**, выведенные из реального
> опыта разработки — каждый подкреплён конкретным коммитом и примером кода.

### 3.1 SSOT через YAML (Single Source of Truth)

**Принцип:** Любое знание о предметной области (список интентов, группировка категорий,
пороговые значения) должно быть определено **ровно в одном месте** — в YAML-конфигурации.
Python-код читает эти определения, но никогда не дублирует их.

**Коммит-референс:** `01252ba`, `7c74854`

**Анти-паттерн — дублирование в Python:**

```python
# ПЛОХО: Хардкод в Python (реальный баг из кодовой базы)
QUESTION_RETURN_INTENTS = {
    "question_pricing",       # ← опечатка! Правильно: price_question
    "question_competitors",   # ← отсутствовали 6 из 7 price-интентов
    "question_implementation",
}

def handle_objection(self, intent):
    if intent in QUESTION_RETURN_INTENTS:
        return "return_to_previous"  # Пропускает price_comparison и др.
```

**Правильный подход — SSOT через YAML:**

```yaml
# ХОРОШО: Единственный источник истины
composed_categories:
  objection_return_triggers:
    union:
      - positive             # greeting, agreement, thanks, ...
      - price_related        # ВСЕ price-интенты автоматически
      - all_questions        # ALL question categories (auto-discovered + explicit)
```

```python
# Python только ЧИТАЕТ конфигурацию
def handle_objection(self, intent):
    triggers = self.config["composed_categories"]["objection_return_triggers"]
    if intent in triggers:
        return "return_to_previous"
```

**Правило:** Если один и тот же список интентов нужен в двух местах — он должен быть
определён в YAML как `composed_category` и ссылаться по имени. Хардкод в Python запрещён.

---

### 3.2 Blackboard Pipeline Authority

**Принцип:** Все решения о действиях и переходах принимаются **только через Blackboard pipeline**.
Knowledge Source предлагает (propose), ConflictResolver разрешает конфликты, Orchestrator
применяет результат. Прямое изменение состояния вне pipeline запрещено.

**Коммит-референс:** `c3736dd`, `0634e7b`, `b717adb`

**Анти-паттерн — прямое управление состоянием:**

```python
# ПЛОХО: Прямое изменение состояния, минуя Blackboard
def _handle_special_case(self):
    sm_result = {}
    sm_result["next_state"] = "some_state"     # Прямая запись
    sm_result["action"] = "special_action"     # Без proposal/resolution
    self.state_machine.transition_to("some_state")  # Ручной переход
    return sm_result
    # Пропущено: context_window, action_tracker, lead_score,
    #            decision_trace, guard_state, visited_states
```

**Правильный подход — Knowledge Source:**

```python
# ХОРОШО: StallGuardSource (реальный код из c3736dd)
class StallGuardSource(KnowledgeSource):
    """Registered at priority_order=45 via SourceRegistry."""

    def should_contribute(self, blackboard):
        """O(1) gate — быстрая проверка без side effects."""
        ctx = blackboard.get_context()
        return (self._enabled
                and ctx.feature_flags.get("stall_guard_enabled", False)
                and ctx.turn_number > self._min_turns)

    def contribute(self, blackboard):
        """Propose через blackboard — ConflictResolver решает."""
        blackboard.propose_transition(
            next_state=self._escape_state,
            priority=Priority.HIGH,
            reason_code="stall_guard_escape",
            source_name=self.name,
        )
```

**Правило:** Новая поведенческая логика = новый Knowledge Source, зарегистрированный
через `SourceRegistry.register()`. Прямая запись в `sm_result` вне Orchestrator запрещена.

---

### 3.3 Open/Closed через Registry + Feature Flags

**Принцип:** Новая функциональность добавляется через **регистрацию в реестре** и
активируется **feature flag'ом**. Существующий код не модифицируется.

**Коммит-референс:** `84bbde0`, `ba260d1`, `c3736dd`

**Анти-паттерн — inline модификация:**

```python
# ПЛОХО: Добавление логики внутрь существующего метода
def process_classification(self, result):
    # ... существующая логика ...

    # ДОБАВЛЕНО: новая обработка (модификация существующего кода)
    if result.intent == "option_selection":
        result = self._handle_option_selection(result)

    return result
```

**Правильный подход — Registry + Decorator:**

```python
# ХОРОШО: OptionSelectionRefinementLayer (реальный код из 84bbde0)
@register_refinement_layer("option_selection")
class OptionSelectionRefinementLayer(BaseRefinementLayer):
    """Добавлена через декоратор — ноль изменений в существующих layers."""

    def refine(self, result, context):
        if self._is_option_selection(result, context):
            return self._resolve_option(result, context)
        return result
```

```yaml
# Активация через YAML — не требует изменений в коде
refinement_pipeline:
  layers:
    - name: option_selection
      enabled: true        # Feature flag
      priority: 25
```

**Для Knowledge Sources — тот же паттерн:**

```python
# Регистрация без модификации существующих Sources
SourceRegistry.register(
    source_class=StallGuardSource,
    name="StallGuardSource",
    priority_order=45,
    config_key="stall_guard",
)
```

**Правило:** Добавление функциональности без `git diff` в существующих файлах (кроме YAML-конфига).
Три точки расширения: `@register_refinement_layer`, `SourceRegistry.register`, условия через `ConditionRegistry`.

---

### 3.4 Defense-in-Depth (Эшелонированная защита)

**Принцип:** Критическое поведение защищается **несколькими независимыми слоями** в разных
подсистемах. Отказ одного слоя не приводит к полному отказу — следующий слой перехватывает.

**Коммит-референс:** `e47da0a`, `c3736dd`

**Анти-паттерн — единственная точка защиты:**

```python
# ПЛОХО: Одна проверка на всё
def process(self, intent):
    if intent == "greeting" and self.state != "greeting":
        return "ignore"  # Единственная защита. Если сломается — катастрофа.
```

**Правильный подход — 5 фаз в 5 подсистемах:**

```
Commit e47da0a: 5-phase defense-in-depth для greeting safety

Phase 1: State Machine (greeting_safety mixin)
  └─ transitions: { greeting: null }          # Блокировка на уровне SM

Phase 2: Classifier (semantic examples)
  └─ 7 intent descriptions + примеры          # Лучшая классификация

Phase 3: Refinement Layer
  └─ GreetingContextRefinementLayer           # Постклассификационная коррекция

Phase 4: Blackboard Source
  └─ Phase-origin objection escape            # Обработка в Blackboard

Phase 5: Policy Condition
  └─ is_stalled detection                     # Финальная сеть безопасности
```

**Правило:** Для критических поведенческих гарантий — минимум 3 независимых уровня защиты.
Каждый уровень работает в своей подсистеме и может быть протестирован изолированно.

---

### 3.5 Single Pipeline Invariant (Единый конвейер)

**Принцип:** Каждое сообщение пользователя проходит через **один и тот же конвейер**
от начала до конца. Параллельные пути обработки (forked pipelines) запрещены.

**Коммит-референс:** `37e2e3f`, `0f68b09`

**Анти-паттерн — параллельные конвейеры:**

```python
# ПЛОХО: Два конвейера с разной полнотой обработки
class Bot:
    def process(self, message):
        # КОНВЕЙЕР 1: Полный — 14 полей, transition_to(), все context updates
        result = self.orchestrator.process_turn(...)
        self._update_context_window(result)
        self._update_action_tracker(result)
        self._update_lead_score(result)
        return result

    def _continue_with_classification(self, intent):
        # КОНВЕЙЕР 2: Неполный — 8 полей, НЕТ transition_to()
        sm_result = self.state_machine.process(intent)
        sm_result["next_state"] = sm_result.get("next_state", "")
        # ПРОПУЩЕНО: context_window, action_tracker, lead_score,
        #            decision_trace, visited_states, guard_state
        return sm_result
```

**Правильный подход — единый pipeline:**

```python
# ХОРОШО: Все пути сходятся к одному Orchestrator pipeline
class Bot:
    def process(self, message):
        # Единственный путь обработки — всегда полный
        decision = self.orchestrator.process_turn(
            blackboard=self.blackboard,
            intent=classified_intent,
            extracted_data=data,
        )
        # Orchestrator гарантирует: transition_to(), context updates,
        # decision_trace, visited_states — ВСЕГДА
        return decision.to_sm_result()
```

**Правило:** `Orchestrator.process_turn()` — единственная точка принятия решений.
Любой обходной путь (disambiguation, fallback, retry) должен в итоге вызвать `process_turn()`.
Если метод возвращает `sm_result` минуя Orchestrator — это баг.

---

### 3.6 Composed Categories (Композитные категории)

**Принцип:** Интенты организованы в **иерархическую таксономию** с 5 уровнями
fallback-разрешения. Группировка интентов определяется через `composed_categories` в YAML,
а не через плоские списки в Python.

**Коммит-референс:** `01252ba`, `7c74854`

**Анти-паттерн — плоские списки:**

```python
# ПЛОХО: Плоские списки с дублированием
POSITIVE_INTENTS = {"greeting", "agreement", "thanks"}
PRICE_INTENTS = {"price_question", "price_comparison", "budget_question"}
RETURN_INTENTS = {"greeting", "agreement", "thanks",   # ← дублирование
                  "price_question", "price_comparison"} # ← неполный список
```

**Правильный подход — таксономия + composed categories:**

```yaml
# ХОРОШО: Иерархическая таксономия
intent_taxonomy:
  price_question:
    category: price_related         # Уровень 1
    super_category: information     # Уровень 2
    semantic_domain: commercial     # Уровень 3

  agreement:
    category: positive
    super_category: engagement
    semantic_domain: rapport

# Composed categories — union/intersection без дублирования
composed_categories:
  objection_return_triggers:
    union:
      - positive              # Все интенты категории positive
      - price_related         # Все интенты категории price_related
      - all_questions         # ALL question categories (auto-discovered)
```

**Fallback chain (5 уровней):**

```
Intent → Exact Match
  └─ не найден → Category (taxonomy_category_defaults)
       └─ не найден → Super-Category (taxonomy_super_category_defaults)
            └─ не найден → Domain (taxonomy_domain_defaults)
                 └─ не найден → Default (глобальный fallback)
```

**Правило:** Для группировки интентов — только `composed_categories` (union/intersection).
Для обработки неизвестных интентов — таксономия с fallback chain.
Плоские `set()` и `list` интентов в Python запрещены.

---

## 4. Blackboard Architecture

> Blackboard — центральная архитектура принятия решений. Все Knowledge Sources
> вносят предложения (proposals), ConflictResolver разрешает конфликты по приоритетам,
> Orchestrator применяет финальное решение.

### 4.1 Обзор архитектуры

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Blackboard Architecture                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                    Knowledge Sources (10 registered)                   │  │
│  │                                                                       │  │
│  │  [5]  GoBackGuard    [10] PriceHandler    [15] IntentRules            │  │
│  │  [20] DataCollector  [25] ObjectionGuard  [30] TransitionResolver     │  │
│  │  [35] FallbackAction [40] FactQuestion    [45] StallGuard             │  │
│  │  [50] DefaultAction  [60] ReturnIntent                                │  │
│  │                                                                       │  │
│  │  Каждый source: should_contribute() → contribute() → propose()        │  │
│  └───────────────────────────────┬───────────────────────────────────────┘  │
│                                  │ proposals                                │
│                                  ▼                                          │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                       Conflict Resolver                                │  │
│  │                                                                       │  │
│  │  1. Separate: ACTION proposals | TRANSITION proposals                 │  │
│  │  2. Sort: CRITICAL > HIGH > NORMAL > LOW                              │  │
│  │  3. Select: winning_action (highest priority)                         │  │
│  │  4. Check: combinable flag                                            │  │
│  │     • combinable=false → BLOCK all transitions                        │  │
│  │     • combinable=true  → MERGE action + transition                    │  │
│  │  5. Build: ResolvedDecision(action, next_state, reason_codes)         │  │
│  └───────────────────────────────┬───────────────────────────────────────┘  │
│                                  │ decision                                 │
│                                  ▼                                          │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                         Orchestrator                                   │  │
│  │                                                                       │  │
│  │  Step 1: begin_turn()          — snapshot context                     │  │
│  │  Step 2: KS.contribute()       — collect proposals                    │  │
│  │  Step 3: assign priorities     — from YAML config                     │  │
│  │  Step 4: conflict_resolve()    — produce ResolvedDecision             │  │
│  │  Step 5: commit()              — apply data_updates, flags            │  │
│  │  Step 6: side_effects()        — transition_to(), context sync        │  │
│  │  Step 7: fill_compat_fields()  — prev_state, goal, collected_data     │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 4.2 Контракт Knowledge Source

Каждый Knowledge Source реализует два метода:

```python
class KnowledgeSource(ABC):
    """Базовый класс для всех Knowledge Sources."""

    @abstractmethod
    def should_contribute(self, blackboard: 'DialogueBlackboard') -> bool:
        """
        O(1) gate — быстрая проверка без side effects.

        Возвращает True если source хочет внести предложение.
        НЕ ДОЛЖЕН: модифицировать blackboard, вызывать LLM, делать I/O.
        """
        pass

    @abstractmethod
    def contribute(self, blackboard: 'DialogueBlackboard') -> None:
        """
        Основная логика — анализ контекста и внесение предложений.

        Вызывает blackboard.propose_action() и/или
        blackboard.propose_transition() для внесения предложений.
        НЕ ДОЛЖЕН: напрямую менять состояние, вызывать transition_to().
        """
        pass
```

### 4.3 Типы предложений (Proposals)

```python
class ProposalType(Enum):
    ACTION = "action"           # Предложение действия (action для генератора)
    TRANSITION = "transition"   # Предложение перехода в другое состояние

class Priority(IntEnum):
    CRITICAL = 0   # Блокирующие действия (rejection, escalation)
    HIGH = 1       # Важные действия (price, objection handling)
    NORMAL = 2     # Стандартная обработка (intent rules, data collection)
    LOW = 3        # Fallback (continue, default)

@dataclass
class Proposal:
    type: ProposalType
    value: str              # Имя действия или целевое состояние
    priority: Priority
    combinable: bool        # True = можно совмещать с transition
    reason_code: str        # Для трассировки: "price_question_detected"
    source_name: str        # Имя Knowledge Source
    priority_rank: int      # Для тонкой сортировки внутри Priority
    metadata: Dict          # Дополнительные данные
```

**Ключевая инновация — флаг `combinable`:**

- `combinable=True`: действие сосуществует с переходом.
  Пример: `answer_with_pricing` (action) + `data_complete → next_phase` (transition)
- `combinable=False`: действие **блокирует** все переходы.
  Пример: `handle_rejection` блокирует любой переход — диалог остаётся в текущем состоянии

### 4.4 Алгоритм ConflictResolver

```
Input:  proposals[] — от всех Knowledge Sources
Output: ResolvedDecision(action, next_state, reason_codes)

1. SEPARATE proposals → action_proposals[], transition_proposals[]
2. SORT each by (priority.value ASC, priority_rank ASC)  // stable sort
3. winning_action = action_proposals[0]                    // highest priority
4. IF winning_action.combinable == false:
     → BLOCK all transitions
     → next_state = current_state
   ELSE:
     → winning_transition = transition_proposals[0]
     → MERGE action + transition
5. FALLBACK: если нет transition и есть "any" trigger → apply fallback
6. RETURN ResolvedDecision(action, next_state, reason_codes, trace)
```

### 4.5 Регистрация Sources

```python
# src/blackboard/source_registry.py
# Порядок определяет очерёдность вызова contribute()
# (НЕ приоритет — приоритет задаётся в самих proposals)

SourceRegistry.register(GoBackGuardSource,       name="GoBackGuard",       priority_order=5)
SourceRegistry.register(PriceHandlerSource,      name="PriceHandler",      priority_order=10)
SourceRegistry.register(IntentRulesSource,       name="IntentRules",       priority_order=15)
SourceRegistry.register(DataCollectorSource,     name="DataCollector",     priority_order=20)
SourceRegistry.register(ObjectionGuardSource,    name="ObjectionGuard",    priority_order=25)
SourceRegistry.register(TransitionResolverSource,name="TransitionResolver",priority_order=30)
SourceRegistry.register(FallbackActionSource,    name="FallbackAction",    priority_order=35)
SourceRegistry.register(FactQuestionSource,      name="FactQuestion",      priority_order=40)
SourceRegistry.register(StallGuardSource,        name="StallGuard",        priority_order=45)
SourceRegistry.register(DefaultActionSource,     name="DefaultAction",     priority_order=50)
```

> **Важно:** `priority_order` определяет порядок *вызова* sources, а не приоритет их
> предложений. Приоритет определяется `Priority` enum в каждом `Proposal`.

---

## 5. Plugin Architecture

### 5.1 Концепция Plugin System

Плагины позволяют расширять функциональность без модификации core:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Plugin System                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                         Plugin Manager                               │   │
│  │                                                                      │   │
│  │  • discover_plugins()    - Auto-discovery from plugins/             │   │
│  │  • load_plugin()         - Load and validate plugin                 │   │
│  │  • register_hooks()      - Register plugin hooks                    │   │
│  │  • get_extensions()      - Get extensions by type                   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│         ┌──────────────────────────┼──────────────────────────┐            │
│         │                          │                          │            │
│         ▼                          ▼                          ▼            │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐        │
│  │ Classifier      │    │ Generator       │    │ Action          │        │
│  │ Plugins         │    │ Plugins         │    │ Plugins         │        │
│  │                 │    │                 │    │                 │        │
│  │ • Custom NLU    │    │ • Custom LLM    │    │ • CRM hooks     │        │
│  │ • Rule-based    │    │ • Templates     │    │ • Notifications │        │
│  │ • ML models     │    │ • Formatters    │    │ • Integrations  │        │
│  └─────────────────┘    └─────────────────┘    └─────────────────┘        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 5.2 Plugin Interface

```python
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum

class PluginType(Enum):
    CLASSIFIER = "classifier"
    GENERATOR = "generator"
    ACTION = "action"
    CONDITION = "condition"
    MIDDLEWARE = "middleware"
    KNOWLEDGE = "knowledge"
    CHANNEL = "channel"

@dataclass
class PluginMetadata:
    name: str
    version: str
    description: str
    author: str
    plugin_type: PluginType
    dependencies: List[str] = None
    config_schema: Dict[str, Any] = None

class BasePlugin(ABC):
    """Base class for all plugins"""

    @property
    @abstractmethod
    def metadata(self) -> PluginMetadata:
        """Return plugin metadata"""
        pass

    @abstractmethod
    def initialize(self, config: Dict[str, Any]) -> None:
        """Initialize plugin with configuration"""
        pass

    @abstractmethod
    def shutdown(self) -> None:
        """Cleanup on shutdown"""
        pass

    def health_check(self) -> bool:
        """Optional health check"""
        return True


class ClassifierPlugin(BasePlugin):
    """Base for classifier plugins"""

    @abstractmethod
    def classify(
        self,
        text: str,
        context: Dict[str, Any]
    ) -> ClassificationResult:
        pass


class GeneratorPlugin(BasePlugin):
    """Base for generator plugins"""

    @abstractmethod
    def generate(
        self,
        action: str,
        context: Dict[str, Any],
        knowledge: Optional[List[Document]] = None
    ) -> str:
        pass


class ActionPlugin(BasePlugin):
    """Base for action plugins (side effects)"""

    @abstractmethod
    def execute(
        self,
        action_name: str,
        params: Dict[str, Any],
        context: Dict[str, Any]
    ) -> ActionResult:
        pass


class ConditionPlugin(BasePlugin):
    """Base for custom condition plugins"""

    @abstractmethod
    def evaluate(
        self,
        condition_name: str,
        context: Dict[str, Any]
    ) -> bool:
        pass


class MiddlewarePlugin(BasePlugin):
    """Base for middleware plugins (request/response pipeline)"""

    @abstractmethod
    def process_input(
        self,
        message: str,
        context: Dict[str, Any]
    ) -> Tuple[str, Dict[str, Any]]:
        """Transform input before processing"""
        pass

    @abstractmethod
    def process_output(
        self,
        response: str,
        context: Dict[str, Any]
    ) -> str:
        """Transform output before sending"""
        pass
```

### 5.3 Plugin Discovery и Loading

```python
class PluginManager:
    """Manages plugin lifecycle"""

    def __init__(self, plugins_dir: str = "plugins"):
        self.plugins_dir = Path(plugins_dir)
        self._plugins: Dict[str, BasePlugin] = {}
        self._hooks: Dict[str, List[Callable]] = defaultdict(list)
        self._extensions: Dict[PluginType, List[BasePlugin]] = defaultdict(list)

    def discover_plugins(self) -> List[PluginMetadata]:
        """Auto-discover plugins from plugins directory"""
        discovered = []

        for plugin_path in self.plugins_dir.glob("*/plugin.yaml"):
            metadata = self._load_plugin_metadata(plugin_path)
            discovered.append(metadata)

        return discovered

    def load_plugin(self, name: str, config: Dict[str, Any] = None) -> BasePlugin:
        """Load and initialize a plugin"""
        plugin_class = self._import_plugin_class(name)
        plugin = plugin_class()

        # Validate config against schema
        if plugin.metadata.config_schema:
            self._validate_config(config, plugin.metadata.config_schema)

        plugin.initialize(config or {})

        self._plugins[name] = plugin
        self._extensions[plugin.metadata.plugin_type].append(plugin)

        return plugin

    def get_extensions(self, plugin_type: PluginType) -> List[BasePlugin]:
        """Get all plugins of a specific type"""
        return self._extensions[plugin_type]

    def register_hook(self, hook_name: str, callback: Callable):
        """Register a hook callback"""
        self._hooks[hook_name].append(callback)

    def execute_hook(self, hook_name: str, *args, **kwargs) -> List[Any]:
        """Execute all callbacks for a hook"""
        results = []
        for callback in self._hooks[hook_name]:
            result = callback(*args, **kwargs)
            results.append(result)
        return results
```

### 5.4 Пример Plugin: CRM Integration

```yaml
# plugins/salesforce_crm/plugin.yaml
name: salesforce_crm
version: "1.0.0"
description: "Salesforce CRM integration for lead management"
author: "Platform Team"
type: action
dependencies:
  - simple_salesforce>=1.12.0
config_schema:
  type: object
  properties:
    instance_url:
      type: string
      description: "Salesforce instance URL"
    username:
      type: string
    password:
      type: string
    security_token:
      type: string
  required: [instance_url, username, password, security_token]
```

```python
# plugins/salesforce_crm/plugin.py
from simple_salesforce import Salesforce
from core.plugins import ActionPlugin, PluginMetadata, PluginType

class SalesforceCRMPlugin(ActionPlugin):

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="salesforce_crm",
            version="1.0.0",
            description="Salesforce CRM integration",
            author="Platform Team",
            plugin_type=PluginType.ACTION,
        )

    def initialize(self, config: Dict[str, Any]) -> None:
        self.sf = Salesforce(
            instance_url=config["instance_url"],
            username=config["username"],
            password=config["password"],
            security_token=config["security_token"]
        )
        self._actions = {
            "create_lead": self._create_lead,
            "update_lead": self._update_lead,
            "log_activity": self._log_activity,
        }

    def execute(
        self,
        action_name: str,
        params: Dict[str, Any],
        context: Dict[str, Any]
    ) -> ActionResult:
        if action_name not in self._actions:
            return ActionResult(success=False, error=f"Unknown action: {action_name}")

        return self._actions[action_name](params, context)

    def _create_lead(self, params: Dict, context: Dict) -> ActionResult:
        lead_data = {
            "FirstName": params.get("first_name"),
            "LastName": params.get("last_name"),
            "Company": params.get("company"),
            "Phone": params.get("phone"),
            "Email": params.get("email"),
            "LeadSource": "Chatbot",
            "Description": context.get("conversation_summary", ""),
        }

        result = self.sf.Lead.create(lead_data)
        return ActionResult(success=True, data={"lead_id": result["id"]})

    def shutdown(self) -> None:
        pass  # Cleanup if needed
```

### 5.5 Hook Points

```python
class HookPoints:
    """Available hook points in the system"""

    # Lifecycle hooks
    BEFORE_MESSAGE_PROCESS = "before_message_process"
    AFTER_MESSAGE_PROCESS = "after_message_process"

    # Classification hooks
    BEFORE_CLASSIFY = "before_classify"
    AFTER_CLASSIFY = "after_classify"

    # State machine hooks
    BEFORE_STATE_TRANSITION = "before_state_transition"
    AFTER_STATE_TRANSITION = "after_state_transition"
    ON_STATE_ENTER = "on_state_enter"
    ON_STATE_EXIT = "on_state_exit"

    # Generation hooks
    BEFORE_GENERATE = "before_generate"
    AFTER_GENERATE = "after_generate"

    # Error hooks
    ON_ERROR = "on_error"
    ON_FALLBACK = "on_fallback"

    # Business hooks
    ON_LEAD_QUALIFIED = "on_lead_qualified"
    ON_DEAL_CLOSED = "on_deal_closed"
    ON_ESCALATION = "on_escalation"
```

---

## 6. Configuration-Driven Development

### 6.1 Иерархия конфигурации

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Configuration Hierarchy                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Priority (highest to lowest):                                              │
│                                                                             │
│  1. Runtime Overrides (API/Admin Panel)                                     │
│     └── Динамические изменения без перезапуска                              │
│                                                                             │
│  2. Environment Variables                                                   │
│     └── LLM_BASE_URL, FEATURE_FLAGS, etc.                                   │
│                                                                             │
│  3. Tenant Configuration (tenant_configs/{tenant_id}/)                      │
│     └── Переопределения для конкретного клиента                             │
│                                                                             │
│  4. Flow Configuration (flows/{flow_name}/)                                 │
│     └── Специфичные для flow настройки                                      │
│                                                                             │
│  5. Base Configuration (yaml_config/)                                       │
│     └── Общие настройки платформы                                           │
│                                                                             │
│  6. Hardcoded Defaults (code)                                               │
│     └── Fallback значения в коде                                            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 6.2 Структура конфигурации

```
config/
├── platform/                    # Platform-level config
│   ├── defaults.yaml           # Global defaults
│   ├── llm.yaml               # LLM provider settings
│   ├── features.yaml          # Feature flags
│   └── security.yaml          # Security settings
│
├── domains/                    # Domain-specific configs
│   ├── sales/
│   │   ├── domain.yaml        # Domain metadata
│   │   ├── intents.yaml       # Domain intents
│   │   ├── entities.yaml      # Domain entities
│   │   └── knowledge/         # Domain knowledge base
│   │
│   ├── support/
│   └── hr/
│
├── flows/                      # Flow definitions
│   ├── _base/                 # Base templates
│   ├── spin_selling/          # SPIN flow
│   ├── bant_qualification/    # BANT flow
│   └── custom/                # Custom flows
│
├── tenants/                    # Per-tenant overrides
│   ├── tenant_001/
│   │   ├── tenant.yaml        # Tenant settings
│   │   ├── branding.yaml      # Branding/tone
│   │   └── flows/             # Flow overrides
│   └── tenant_002/
│
└── plugins/                    # Plugin configurations
    ├── salesforce/
    └── hubspot/
```

### 6.3 Унифицированный ConfigLoader

```python
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
from pathlib import Path
import yaml
from functools import lru_cache

@dataclass
class ResolvedConfig:
    """Fully resolved configuration"""
    platform: Dict[str, Any]
    domain: Dict[str, Any]
    flow: Dict[str, Any]
    tenant: Dict[str, Any]
    plugins: Dict[str, Any]

    def get(self, path: str, default: Any = None) -> Any:
        """Get value by dot-notation path: 'flow.states.greeting.goal'"""
        parts = path.split(".")
        value = self.__dict__
        for part in parts:
            if isinstance(value, dict):
                value = value.get(part)
            else:
                return default
            if value is None:
                return default
        return value


class UnifiedConfigLoader:
    """Loads and merges configuration from all sources"""

    def __init__(
        self,
        config_dir: str = "config",
        tenant_id: Optional[str] = None,
        flow_name: Optional[str] = None,
        domain: Optional[str] = None,
    ):
        self.config_dir = Path(config_dir)
        self.tenant_id = tenant_id
        self.flow_name = flow_name
        self.domain = domain
        self._cache: Dict[str, Any] = {}

    @lru_cache(maxsize=32)
    def load(self) -> ResolvedConfig:
        """Load and merge all configurations"""

        # 1. Platform defaults
        platform = self._load_yaml("platform/defaults.yaml")
        platform = self._deep_merge(platform, self._load_yaml("platform/llm.yaml"))
        platform = self._deep_merge(platform, self._load_yaml("platform/features.yaml"))

        # 2. Domain config
        domain_config = {}
        if self.domain:
            domain_config = self._load_yaml(f"domains/{self.domain}/domain.yaml")

        # 3. Flow config (with inheritance resolution)
        flow_config = {}
        if self.flow_name:
            flow_config = self._load_flow_with_inheritance(self.flow_name)

        # 4. Tenant overrides
        tenant_config = {}
        if self.tenant_id:
            tenant_config = self._load_tenant_config(self.tenant_id)

        # 5. Apply environment overrides
        platform = self._apply_env_overrides(platform)

        return ResolvedConfig(
            platform=platform,
            domain=domain_config,
            flow=flow_config,
            tenant=tenant_config,
            plugins=self._load_plugin_configs(),
        )

    def _load_flow_with_inheritance(self, flow_name: str) -> Dict[str, Any]:
        """Load flow with extends/mixins resolution"""
        base_path = self.config_dir / "flows" / "_base"
        flow_path = self.config_dir / "flows" / flow_name

        # Load base
        base_states = self._load_yaml(base_path / "states.yaml")
        base_mixins = self._load_yaml(base_path / "mixins.yaml")

        # Load flow
        flow = self._load_yaml(flow_path / "flow.yaml")
        flow_states = self._load_yaml(flow_path / "states.yaml")

        # Resolve extends
        for state_name, state_config in flow_states.get("states", {}).items():
            if "extends" in state_config:
                base_state = base_states.get("states", {}).get(state_config["extends"], {})
                flow_states["states"][state_name] = self._deep_merge(
                    base_state.copy(), state_config
                )

            # Apply mixins
            if "mixins" in state_config:
                for mixin_name in state_config["mixins"]:
                    mixin = base_mixins.get("mixins", {}).get(mixin_name, {})
                    flow_states["states"][state_name] = self._deep_merge(
                        flow_states["states"][state_name],
                        mixin
                    )

        return self._deep_merge(flow, flow_states)

    def _deep_merge(self, base: Dict, override: Dict) -> Dict:
        """Deep merge two dictionaries"""
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    def _apply_env_overrides(self, config: Dict) -> Dict:
        """Apply environment variable overrides"""
        import os

        env_mappings = {
            "LLM_BASE_URL": "llm.base_url",
            "LLM_MODEL": "llm.model",
            "LLM_TIMEOUT": "llm.timeout",
            "FEATURE_LLM_CLASSIFIER": "features.llm_classifier",
        }

        for env_var, config_path in env_mappings.items():
            if env_var in os.environ:
                self._set_nested(config, config_path, os.environ[env_var])

        return config
```

### 6.4 Validation Schema

```python
from pydantic import BaseModel, Field, validator
from typing import List, Dict, Any, Optional
from enum import Enum

class NodeType(str, Enum):
    SIMPLE = "simple"
    CHOICE = "choice"
    FORK = "fork"
    JOIN = "join"
    PARALLEL = "parallel"

class StateConfig(BaseModel):
    """Configuration schema for a state"""
    type: NodeType = NodeType.SIMPLE
    goal: str = Field(..., min_length=1, description="State goal description")
    extends: Optional[str] = None
    mixins: List[str] = []
    transitions: Dict[str, str] = {}
    rules: Dict[str, Any] = {}
    is_final: bool = False
    on_enter: Optional[Dict[str, Any]] = None
    on_exit: Optional[Dict[str, Any]] = None

    # DAG-specific
    branches: Optional[List[Dict]] = None  # For FORK
    choices: Optional[List[Dict]] = None   # For CHOICE
    expects_branches: Optional[List[str]] = None  # For JOIN

class FlowConfig(BaseModel):
    """Configuration schema for a flow"""
    name: str = Field(..., min_length=1)
    version: str = "1.0"
    description: Optional[str] = None
    engine: str = "fsm"  # 'fsm' or 'dag'

    phases: Optional[Dict[str, Any]] = None
    entry_points: Dict[str, str] = {"default": "greeting"}
    states: Dict[str, StateConfig]
    variables: Dict[str, Any] = {}

    @validator("states")
    def validate_transitions(cls, states, values):
        """Ensure all transition targets exist"""
        state_names = set(states.keys())

        for state_name, state_config in states.items():
            for intent, target in state_config.transitions.items():
                if target not in state_names and not target.startswith("_"):
                    raise ValueError(
                        f"State '{state_name}' has transition to unknown state '{target}'"
                    )

        return states
```

---

## 7. Абстракции и Контракты

### 7.1 Core Contracts

```python
from abc import ABC, abstractmethod
from typing import Protocol, runtime_checkable
from dataclasses import dataclass

# ============================================================================
# Data Transfer Objects
# ============================================================================

@dataclass
class Message:
    """Input message"""
    text: str
    sender_id: str
    channel: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)

@dataclass
class ClassificationResult:
    """Result of intent classification"""
    intent: str
    confidence: float
    extracted_data: Dict[str, Any] = field(default_factory=dict)
    alternatives: List[Tuple[str, float]] = field(default_factory=list)

@dataclass
class StateTransition:
    """Result of state machine processing"""
    action: str
    next_state: str
    should_respond: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class GeneratedResponse:
    """Generated response"""
    text: str
    confidence: float
    sources: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class BotResponse:
    """Complete bot response"""
    message: str
    intent: str
    action: str
    state: str
    is_final: bool
    metadata: Dict[str, Any] = field(default_factory=dict)


# ============================================================================
# Protocols (Interfaces)
# ============================================================================

@runtime_checkable
class IClassifier(Protocol):
    """Contract for intent classifiers"""

    def classify(self, message: Message, context: 'IContext') -> ClassificationResult:
        """Classify user message intent"""
        ...

    def get_supported_intents(self) -> List[str]:
        """Return list of supported intents"""
        ...


@runtime_checkable
class IStateMachine(Protocol):
    """Contract for state machine implementations"""

    @property
    def current_state(self) -> str:
        """Get current state"""
        ...

    def process(
        self,
        intent: str,
        extracted_data: Dict[str, Any],
        context: 'IContext'
    ) -> StateTransition:
        """Process intent and return transition"""
        ...

    def can_transition(self, intent: str) -> bool:
        """Check if transition is possible"""
        ...


@runtime_checkable
class IGenerator(Protocol):
    """Contract for response generators"""

    def generate(
        self,
        action: str,
        context: 'IContext',
        knowledge: Optional[List['Document']] = None
    ) -> GeneratedResponse:
        """Generate response for action"""
        ...


@runtime_checkable
class IKnowledgeBase(Protocol):
    """Contract for knowledge base"""

    def search(
        self,
        query: str,
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None
    ) -> List['Document']:
        """Search knowledge base"""
        ...

    def get_by_id(self, doc_id: str) -> Optional['Document']:
        """Get document by ID"""
        ...


@runtime_checkable
class IContext(Protocol):
    """Contract for conversation context"""

    @property
    def conversation_id(self) -> str:
        ...

    @property
    def history(self) -> List[Message]:
        ...

    def get(self, key: str, default: Any = None) -> Any:
        ...

    def set(self, key: str, value: Any) -> None:
        ...

    def get_extracted_data(self) -> Dict[str, Any]:
        ...


@runtime_checkable
class IContextStorage(Protocol):
    """Contract for context persistence"""

    def save(self, context: IContext) -> None:
        ...

    def load(self, conversation_id: str) -> Optional[IContext]:
        ...

    def delete(self, conversation_id: str) -> None:
        ...


@runtime_checkable
class IChannel(Protocol):
    """Contract for messaging channels"""

    @property
    def channel_type(self) -> str:
        ...

    def receive(self) -> AsyncIterator[Message]:
        """Receive messages from channel"""
        ...

    def send(self, recipient_id: str, message: str) -> None:
        """Send message to channel"""
        ...


# ============================================================================
# Abstract Base Classes
# ============================================================================

class BaseBot(ABC):
    """Abstract base class for all bot implementations"""

    def __init__(
        self,
        classifier: IClassifier,
        state_machine: IStateMachine,
        generator: IGenerator,
        knowledge: Optional[IKnowledgeBase] = None,
        context_storage: Optional[IContextStorage] = None,
    ):
        self.classifier = classifier
        self.state_machine = state_machine
        self.generator = generator
        self.knowledge = knowledge
        self.context_storage = context_storage

    @abstractmethod
    def process(self, message: Message) -> BotResponse:
        """Process incoming message"""
        pass

    def _get_or_create_context(self, conversation_id: str) -> IContext:
        if self.context_storage:
            context = self.context_storage.load(conversation_id)
            if context:
                return context
        return self._create_context(conversation_id)

    @abstractmethod
    def _create_context(self, conversation_id: str) -> IContext:
        pass
```

### 7.2 Registry Pattern для расширяемости

```python
from typing import TypeVar, Generic, Dict, Type, Callable

T = TypeVar('T')

class Registry(Generic[T]):
    """Generic registry for extensibility"""

    def __init__(self, name: str):
        self.name = name
        self._items: Dict[str, Type[T]] = {}
        self._factories: Dict[str, Callable[..., T]] = {}

    def register(self, name: str, item: Type[T]) -> None:
        """Register a class"""
        if name in self._items:
            raise ValueError(f"{name} already registered in {self.name}")
        self._items[name] = item

    def register_factory(self, name: str, factory: Callable[..., T]) -> None:
        """Register a factory function"""
        self._factories[name] = factory

    def get(self, name: str, **kwargs) -> T:
        """Get instance by name"""
        if name in self._factories:
            return self._factories[name](**kwargs)
        if name in self._items:
            return self._items[name](**kwargs)
        raise KeyError(f"'{name}' not found in {self.name} registry")

    def list_registered(self) -> List[str]:
        """List all registered names"""
        return list(self._items.keys()) + list(self._factories.keys())

    def __contains__(self, name: str) -> bool:
        return name in self._items or name in self._factories


# Global registries
ClassifierRegistry = Registry[IClassifier]("Classifier")
GeneratorRegistry = Registry[IGenerator]("Generator")
StateMachineRegistry = Registry[IStateMachine]("StateMachine")
KnowledgeRegistry = Registry[IKnowledgeBase]("KnowledgeBase")
ChannelRegistry = Registry[IChannel]("Channel")
ConditionRegistry = Registry[Callable]("Condition")
ActionRegistry = Registry[Callable]("Action")


# Decorator for easy registration
def register_classifier(name: str):
    def decorator(cls):
        ClassifierRegistry.register(name, cls)
        return cls
    return decorator

def register_generator(name: str):
    def decorator(cls):
        GeneratorRegistry.register(name, cls)
        return cls
    return decorator

# Usage
@register_classifier("llm")
class LLMClassifier:
    ...

@register_classifier("hybrid")
class HybridClassifier:
    ...

# Real Implementation: RefinementLayerRegistry (src/classifier/refinement_pipeline.py)
# See: RefinementLayerRegistry.register("short_answer", ShortAnswerRefinementLayer)
# See: @register_refinement_layer("composite_message") decorator
```

---

## 8. Multi-Tenancy и Изоляция

### 8.1 Tenant Model

```python
@dataclass
class Tenant:
    """Tenant configuration"""
    tenant_id: str
    name: str
    domain: str  # sales, support, hr, etc.
    flow: str    # Which flow to use

    # Branding
    bot_name: str = "Assistant"
    tone: str = "professional"  # professional, friendly, formal
    language: str = "ru"

    # Feature overrides
    features: Dict[str, bool] = field(default_factory=dict)

    # Limits
    max_conversation_turns: int = 50
    max_message_length: int = 4000

    # Integration settings
    integrations: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    # Custom prompts/templates
    prompt_overrides: Dict[str, str] = field(default_factory=dict)


class TenantManager:
    """Manages tenant configurations and isolation"""

    def __init__(self, storage: ITenantStorage):
        self.storage = storage
        self._cache: Dict[str, Tenant] = {}

    def get_tenant(self, tenant_id: str) -> Tenant:
        if tenant_id not in self._cache:
            self._cache[tenant_id] = self.storage.load(tenant_id)
        return self._cache[tenant_id]

    def create_bot_for_tenant(self, tenant: Tenant) -> BaseBot:
        """Create a bot instance configured for tenant"""

        config = UnifiedConfigLoader(
            tenant_id=tenant.tenant_id,
            flow_name=tenant.flow,
            domain=tenant.domain,
        ).load()

        # Create components with tenant config
        classifier = ClassifierRegistry.get(
            config.get("classifier.type", "llm"),
            config=config,
            tenant=tenant,
        )

        generator = GeneratorRegistry.get(
            config.get("generator.type", "llm"),
            config=config,
            tenant=tenant,
        )

        state_machine = StateMachineRegistry.get(
            config.get("state_machine.type", "dag"),
            flow_config=config.flow,
            tenant=tenant,
        )

        return SalesBot(
            classifier=classifier,
            state_machine=state_machine,
            generator=generator,
            tenant=tenant,
        )
```

### 8.2 Context Isolation

```python
class TenantContext(IContext):
    """Tenant-isolated conversation context"""

    def __init__(
        self,
        conversation_id: str,
        tenant: Tenant,
        storage: IContextStorage,
    ):
        self._conversation_id = conversation_id
        self._tenant = tenant
        self._storage = storage
        self._data: Dict[str, Any] = {}
        self._history: List[Message] = []
        self._extracted: Dict[str, Any] = {}

    @property
    def conversation_id(self) -> str:
        # Namespace with tenant
        return f"{self._tenant.tenant_id}:{self._conversation_id}"

    @property
    def tenant(self) -> Tenant:
        return self._tenant

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value
        self._persist()

    def _persist(self) -> None:
        """Persist to tenant-scoped storage"""
        self._storage.save(self)
```

### 8.3 Resource Isolation

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          Multi-Tenant Isolation                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌───────────────────┐  ┌───────────────────┐  ┌───────────────────┐       │
│  │     Tenant A      │  │     Tenant B      │  │     Tenant C      │       │
│  │  (SPIN Selling)   │  │  (Support Flow)   │  │  (Custom Flow)    │       │
│  └─────────┬─────────┘  └─────────┬─────────┘  └─────────┬─────────┘       │
│            │                      │                      │                  │
│  ┌─────────▼─────────┐  ┌─────────▼─────────┐  ┌─────────▼─────────┐       │
│  │ Knowledge Base A  │  │ Knowledge Base B  │  │ Knowledge Base C  │       │
│  │ (Isolated)        │  │ (Isolated)        │  │ (Isolated)        │       │
│  └───────────────────┘  └───────────────────┘  └───────────────────┘       │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    Shared Resources (Read-Only)                      │   │
│  │  • Base prompts  • Common intents  • Platform features               │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    Shared Infrastructure                             │   │
│  │  • LLM Service  • Vector DB  • Logging  • Metrics                   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 9. Расширяемость Flow

### 9.1 Flow Composition

```yaml
# flows/composite_flow/flow.yaml
flow:
  name: composite_enterprise_flow
  version: "1.0"
  description: "Композитный flow для Enterprise клиентов"

  # Import и compose других flows
  imports:
    - name: spin_selling
      as: spin
      # Можно переопределить entry/exit points
      entry_override: spin_situation
      exit_override: spin_success

    - name: bant_qualification
      as: bant
      entry_override: standard_bant
      exit_override: bant_aggregation

  # Composite flow definition
  composition:
    entry: enterprise_greeting

    stages:
      - name: greeting
        flow: inline
        states:
          enterprise_greeting:
            goal: "Enterprise приветствие"
            transitions:
              qualified: qualification_router

      - name: qualification_router
        type: choice
        choices:
          - condition: needs_spin
            goto: spin.entry  # Переход в imported flow
          - condition: needs_bant
            goto: bant.entry
          - condition: fast_track
            goto: fast_demo
        default: spin.entry

      - name: spin_phase
        flow: spin  # Use imported flow
        on_exit:
          - flow: inline
            state: post_spin_check

      - name: bant_phase
        flow: bant

      - name: closing
        flow: inline
        states:
          fast_demo:
            goal: "Быстрая демо"
            transitions:
              done: success

          post_spin_check:
            type: choice
            choices:
              - condition: needs_bant
                goto: bant.entry
              - condition: qualified
                goto: closing_state

          closing_state:
            goal: "Закрытие"
            transitions:
              agreement: success

          success:
            is_final: true
```

### 9.2 Custom State Types

```yaml
# config/platform/state_types.yaml
state_types:
  # Custom state type: Survey
  survey:
    description: "Multi-question survey state"
    properties:
      questions:
        type: array
        items:
          type: object
          properties:
            id: { type: string }
            text: { type: string }
            type: { enum: [text, choice, rating] }
            options: { type: array }
            required: { type: boolean }
      on_complete:
        type: string
        description: "Next state after survey"
    behavior: |
      1. Present questions one by one
      2. Collect and validate answers
      3. Store in extracted_data
      4. Transition to on_complete when done

  # Custom state type: API Call
  api_call:
    description: "State that calls external API"
    properties:
      endpoint:
        type: string
      method:
        enum: [GET, POST, PUT, DELETE]
      payload_template:
        type: string
      success_transition:
        type: string
      error_transition:
        type: string
    behavior: |
      1. Build payload from context
      2. Call API
      3. Store response in context
      4. Transition based on result

  # Custom state type: Approval
  approval:
    description: "Human-in-the-loop approval"
    properties:
      approval_channel:
        type: string
      timeout_seconds:
        type: integer
      on_approved:
        type: string
      on_rejected:
        type: string
      on_timeout:
        type: string
```

### 9.3 Dynamic Flow Modification

```python
class FlowModifier:
    """Runtime flow modifications"""

    def __init__(self, base_flow: FlowConfig):
        self.flow = base_flow.copy()

    def add_state(self, name: str, config: StateConfig) -> 'FlowModifier':
        """Add new state to flow"""
        self.flow.states[name] = config
        return self

    def modify_transition(
        self,
        state: str,
        intent: str,
        new_target: str
    ) -> 'FlowModifier':
        """Modify existing transition"""
        if state in self.flow.states:
            self.flow.states[state].transitions[intent] = new_target
        return self

    def insert_before(
        self,
        target_state: str,
        new_state: str,
        new_config: StateConfig
    ) -> 'FlowModifier':
        """Insert state before target (redirect transitions)"""
        # Find all transitions to target_state
        for state_name, state_config in self.flow.states.items():
            for intent, transition_target in state_config.transitions.items():
                if transition_target == target_state:
                    state_config.transitions[intent] = new_state

        # Add new state with transition to target
        new_config.transitions["_continue"] = target_state
        self.flow.states[new_state] = new_config

        return self

    def apply_ab_test(
        self,
        state: str,
        variants: Dict[str, StateConfig],
        distribution: Dict[str, float]
    ) -> 'FlowModifier':
        """Apply A/B test variant selection"""
        # Create choice state
        choice_config = StateConfig(
            type=NodeType.CHOICE,
            goal="A/B test routing",
            choices=[
                {"condition": f"ab_variant_{variant}", "next": f"{state}_{variant}"}
                for variant in variants.keys()
            ]
        )

        # Replace original with choice
        original = self.flow.states[state]
        self.flow.states[f"{state}_router"] = choice_config

        # Add variants
        for variant_name, variant_config in variants.items():
            self.flow.states[f"{state}_{variant_name}"] = variant_config

        return self

    def build(self) -> FlowConfig:
        """Return modified flow"""
        return self.flow
```

---

## 10. Best Practices

### 10.1 Основано на исследованиях

| Практика | Источник | Применение |
|----------|----------|------------|
| **Configuration as Code** | 12-Factor App | YAML configs в Git |
| **Plugin Architecture** | Eclipse, VSCode | Extensible components |
| **Event Sourcing** | Martin Fowler | DomainEvent system |
| **Circuit Breaker** | Netflix Hystrix | LLM resilience |
| **Feature Flags** | LaunchDarkly patterns | Gradual rollout |
| **Hexagonal Architecture** | Alistair Cockburn | Ports & Adapters |
| **Domain-Driven Design** | Eric Evans | Bounded contexts |

### 10.2 Coding Guidelines

```python
# =============================================================================
# 1. ВСЕГДА используй типизацию
# =============================================================================

# ПЛОХО
def process(message, context):
    return {"response": "ok"}

# ХОРОШО
def process(message: Message, context: IContext) -> BotResponse:
    return BotResponse(message="ok", ...)


# =============================================================================
# 2. Dependency Injection через конструктор
# =============================================================================

# ПЛОХО
class Bot:
    def __init__(self):
        self.classifier = LLMClassifier()  # Hardcoded

# ХОРОШО
class Bot:
    def __init__(self, classifier: IClassifier):
        self.classifier = classifier


# =============================================================================
# 3. Конфигурация через YAML, не хардкод
# =============================================================================

# ПЛОХО
MAX_RETRIES = 3
TIMEOUT = 60
INTENTS = ["greeting", "farewell", ...]

# ХОРОШО
config = ConfigLoader().load()
max_retries = config.get("llm.max_retries", 3)
timeout = config.get("llm.timeout", 60)


# =============================================================================
# 4. Логирование с контекстом
# =============================================================================

# ПЛОХО
print(f"Error: {e}")
logger.error("Something failed")

# ХОРОШО
logger.error(
    "Classification failed",
    extra={
        "conversation_id": context.conversation_id,
        "tenant_id": context.tenant.tenant_id,
        "message_preview": message.text[:100],
        "error": str(e),
    }
)


# =============================================================================
# 5. Graceful degradation
# =============================================================================

# ПЛОХО
def classify(self, text):
    return self.llm.classify(text)  # Fails if LLM down

# ХОРОШО
def classify(self, text):
    try:
        return self.llm.classify(text)
    except LLMError:
        logger.warning("LLM failed, falling back to hybrid")
        return self.hybrid.classify(text)
    except Exception:
        logger.error("All classifiers failed, using default")
        return ClassificationResult(intent="unclear", confidence=0.0)


# =============================================================================
# 6. Immutable data objects
# =============================================================================

# ПЛОХО
class Config:
    def __init__(self):
        self.data = {}

    def set(self, key, value):
        self.data[key] = value  # Mutable!

# ХОРОШО
@dataclass(frozen=True)
class Config:
    llm_model: str
    timeout: int
    features: FrozenSet[str]

    def with_override(self, **kwargs) -> 'Config':
        return replace(self, **kwargs)  # Returns new instance
```

### 10.3 Testing Guidelines

```python
# =============================================================================
# 1. Test через публичные интерфейсы
# =============================================================================

# ПЛОХО - тестируем internal
def test_internal_method():
    bot = SalesBot(...)
    result = bot._parse_intent_internal(text)  # Private method

# ХОРОШО - тестируем публичный API
def test_classification():
    bot = SalesBot(...)
    result = bot.process(Message(text="Привет"))
    assert result.intent == "greeting"


# =============================================================================
# 2. Используй фикстуры для DI
# =============================================================================

@pytest.fixture
def mock_classifier():
    classifier = Mock(spec=IClassifier)
    classifier.classify.return_value = ClassificationResult(
        intent="greeting",
        confidence=0.95
    )
    return classifier

@pytest.fixture
def bot(mock_classifier, mock_generator):
    return SalesBot(
        classifier=mock_classifier,
        generator=mock_generator,
    )

def test_greeting_flow(bot):
    response = bot.process(Message(text="Привет"))
    assert response.action == "greet"


# =============================================================================
# 3. Параметризованные тесты для flows
# =============================================================================

@pytest.mark.parametrize("flow_name,entry_state", [
    ("spin_selling", "greeting"),
    ("bant_qualification", "greeting"),
    ("support_flow", "support_greeting"),
])
def test_flow_entry_points(flow_name, entry_state):
    config = ConfigLoader().load_flow(flow_name)
    assert config.entry_points["default"] == entry_state


# =============================================================================
# 4. Contract tests для плагинов
# =============================================================================

class ClassifierContractTest:
    """Base test class for classifier contract compliance"""

    @pytest.fixture
    def classifier(self) -> IClassifier:
        raise NotImplementedError

    def test_returns_classification_result(self, classifier):
        result = classifier.classify(Message(text="test"), context)
        assert isinstance(result, ClassificationResult)

    def test_confidence_in_range(self, classifier):
        result = classifier.classify(Message(text="test"), context)
        assert 0.0 <= result.confidence <= 1.0

    def test_handles_empty_message(self, classifier):
        result = classifier.classify(Message(text=""), context)
        assert result.intent == "unclear" or result.confidence < 0.5

# Each classifier implementation uses this base
class TestLLMClassifier(ClassifierContractTest):
    @pytest.fixture
    def classifier(self):
        return LLMClassifier(config)

class TestHybridClassifier(ClassifierContractTest):
    @pytest.fixture
    def classifier(self):
        return HybridClassifier(config)
```

---

## 11. Roadmap

### Phase 1: Foundation (Complete)

- [x] YAML-based configuration v2.0
- [x] DAG State Machine
- [x] Feature Flags
- [x] Multi-tier fallbacks
- [x] **Comprehensive config testing (1780+ tests)**
  - [x] Dynamic config changes
  - [x] Conflict detection
  - [x] Complex conditions (AND/OR/NOT)
  - [x] Unreachable states (BFS/DFS)
  - [x] Template interpolation
  - [x] Multi-tenant isolation
  - [x] Stress/performance testing
  - [x] Config migration
- [x] **RefinementPipeline** — Protocol + Registry pattern for classification refinement
  - [x] IRefinementLayer Protocol
  - [x] RefinementLayerRegistry (dynamic registration)
  - [x] BaseRefinementLayer (template method pattern)
  - [x] Layer adapters (ShortAnswer, Composite, Objection, GreetingContext, OptionSelection)
  - [x] YAML configuration
  - [x] Feature flag integration
  - [x] 33 unit tests

### Phase 1b: Blackboard Architecture (Current)

- [x] **Blackboard Architecture** — центральная система принятия решений
  - [x] DialogueBlackboard (proposal collection)
  - [x] ConflictResolver (priority-based resolution with combinable flag)
  - [x] Orchestrator (7-step pipeline)
  - [x] 10 Knowledge Sources (SourceRegistry + priority_order)
  - [x] ResolvedDecision → sm_result compatibility layer
- [x] **Операционные принципы** — кодифицированы из реального опыта
  - [x] SSOT через YAML (composed_categories, intent_taxonomy)
  - [x] Blackboard Pipeline Authority (все решения через proposals)
  - [x] OCP через Registry + Feature Flags
  - [x] Defense-in-Depth (эшелонированная защита)
  - [x] Single Pipeline Invariant
  - [x] Composed Categories (5-level fallback chain)
- [ ] **Disambiguation через Blackboard** — устранение параллельного конвейера
  - [ ] DisambiguationSource (Knowledge Source)
  - [ ] DisambiguationResolutionLayer (Refinement Layer)
  - [ ] Удаление ~470 строк дублированного кода в bot.py
- [ ] **Refactor to Protocols/Interfaces** (остальные компоненты)
- [ ] **Registry pattern for all components** (classifier, generator, knowledge)

### Phase 2: Plugin System (Q1 2026)

- [ ] Plugin Manager implementation
- [ ] Plugin discovery & loading
- [ ] Hook points system
- [ ] Plugin SDK & documentation
- [ ] Example plugins (CRM, Notifications)

### Phase 3: Multi-Tenancy (Q2 2026)

- [ ] Tenant model & storage
- [ ] Context isolation
- [ ] Per-tenant configuration
- [ ] Resource quotas
- [ ] Admin API

### Phase 4: Advanced Flows (Q3 2026)

- [ ] Flow composition
- [ ] Custom state types
- [ ] Dynamic flow modification
- [ ] A/B testing for flows
- [ ] Visual flow editor (optional)

### Phase 5: Enterprise Features (Q4 2026)

- [ ] Multi-LLM support (OpenAI, Anthropic, etc.)
- [ ] Advanced analytics
- [ ] Audit logging
- [ ] Role-based access control
- [ ] Self-service onboarding

---

## Appendix A: Migration Checklist

При переходе к новой архитектуре:

```markdown
- [x] Выделить интерфейсы из существующих классов (IRefinementLayer Protocol)
- [x] Создать Registry для каждого типа компонента (RefinementLayerRegistry, SourceRegistry)
- [x] Перенести конфигурацию из Python в YAML (refinement_pipeline, composed_categories, intent_taxonomy)
- [x] Реализовать Blackboard Architecture (10 Knowledge Sources, ConflictResolver, Orchestrator)
- [x] Кодифицировать операционные принципы (SSOT, Pipeline Authority, OCP, Defense-in-Depth, Single Pipeline, Composed Categories)
- [ ] Добавить DI через конструкторы
- [ ] Создать Composition Root (factory)
- [ ] Добавить Event Bus
- [ ] Реализовать Plugin Manager
- [ ] Добавить Tenant model
- [x] Написать contract tests (33 unit tests for RefinementPipeline)
- [x] Обновить документацию (ARCHITECTURE.md, CLASSIFIER.md, DESIGN_PRINCIPLES.md v2.0)
- [ ] Устранить параллельный конвейер disambiguation (DisambiguationSource + ResolutionLayer)
```

---

## Appendix B: Glossary

| Термин | Определение |
|--------|-------------|
| **Blackboard** | Центральная архитектура принятия решений через proposals |
| **Knowledge Source** | Компонент Blackboard, вносящий предложения (proposals) |
| **Proposal** | Предложение действия (ACTION) или перехода (TRANSITION) |
| **ConflictResolver** | Компонент, разрешающий конфликты между proposals по приоритетам |
| **Orchestrator** | 7-шаговый конвейер обработки turn в Blackboard |
| **Combinable** | Флаг proposal: true = совместим с transition, false = блокирует |
| **Composed Category** | YAML-определённое объединение категорий интентов |
| **Intent Taxonomy** | Иерархическая классификация: intent → category → super_category → domain |
| **Tenant** | Клиент платформы с изолированной конфигурацией |
| **Flow** | Определение диалогового сценария в YAML |
| **State** | Узел в графе диалога |
| **Intent** | Намерение пользователя |
| **Action** | Действие бота в ответ на intent |
| **Plugin** | Расширение функциональности платформы |
| **Hook** | Точка расширения для внедрения логики |
| **Mixin** | Переиспользуемый блок правил |
| **DAG** | Directed Acyclic Graph — граф без циклов |
| **Registry** | Реестр для dynamic lookup компонентов |
| **SSOT** | Single Source of Truth — единый источник истины |
| **Defense-in-Depth** | Эшелонированная защита: несколько слоёв в разных подсистемах |

---

*Документ создан: Январь 2026*
*Последнее обновление: 30 Января 2026*
*Версия 2.0: Добавлены Операционные Принципы (Раздел 3) и Blackboard Architecture (Раздел 4)*
