# Conditional Rules: Гибридная архитектура

## Часть 1: ТЕКУЩЕЕ СОСТОЯНИЕ

### 1.1 Как работает система сейчас

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

**Ключевой момент:** Rules — это просто строки. Одна строка = один action. Всегда.

### 1.2 Проблема: Нужна условная логика

**Бизнес-требование:** "Если клиент спросил о цене И мы уже знаем размер команды — ответить на вопрос. Если не знаем — спросить размер."

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

### 1.3 Текущее решение: Костыли в коде

```python
# state_machine.py — СЕЙЧАС

def apply_rules(self, intent: str):
    rules = config.get("rules", {})

    if intent in rules:
        rule_action = rules[intent]

        # ═══════════════════════════════════════════════════════
        # КОСТЫЛЬ #1: Price Deflect Loop Bug
        # ═══════════════════════════════════════════════════════
        if intent == "price_question" and rule_action == "deflect_and_continue":
            has_pricing_data = self.collected_data.get("company_size") or \
                              self.collected_data.get("users_count")
            if has_pricing_data:
                return "answer_with_facts", self.state

        # КОСТЫЛЬ #2: (будущий) Эскалация при повторах
        # if intent == "price_question" and self.price_question_count > 3:
        #     return "answer_with_range", self.state

        # КОСТЫЛЬ #3: (будущий) Competitor handling
        # if intent == "comparison" and self.collected_data.get("competitor"):
        #     return "compare_with_competitor", self.state

        return rule_action, self.state
```

**Проблемы:**

| Проблема | Описание |
|----------|----------|
| Hardcoded | Каждое условие = новый if в коде |
| Не масштабируется | 10 условий = 10 if'ов |
| Логика размазана | Часть в config.py, часть в state_machine.py |
| Сложно тестировать | Нужно поднимать весь SM для теста условия |
| Сложно понять | Чтобы узнать поведение, нужно читать код |

### 1.4 Выявленные случаи где нужны условия

Из анализа simulation_report.txt и кода:

| № | Интент | Условие | Результат |
|---|--------|---------|-----------|
| 1 | price_question | Есть company_size/users_count | answer_with_facts (action) |
| 2 | price_question | Повторился 3+ раз | answer_with_range (action) |
| 3 | pricing_details | Есть company_size | answer_with_facts (action) |
| 4 | comparison | Известен конкурент | compare_specific (action) |
| 5 | objection_price | Есть pain_point + company_size | handle_with_roi (action) |
| 6 | question_technical | Повторился 2+ раз | offer_documentation (action) |
| 7 | demo_request | В фазе close | success (transition) |

---

## Часть 2: ЦЕЛЬ РЕФАКТОРИНГА

### 2.1 Что хотим получить

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      ГИБРИДНАЯ АРХИТЕКТУРА                                   │
│           Python Conditions + Declarative Rules + Domain Registries          │
└─────────────────────────────────────────────────────────────────────────────┘

                              ДОМЕНЫ (изолированные)
   ┌─────────────────────────────────────────────────────────────────────────┐
   │                                                                         │
   │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐         │
   │  │  StateMachine   │  │ DialoguePolicy  │  │ FallbackHandler │   ...   │
   │  │     Domain      │  │     Domain      │  │     Domain      │         │
   │  ├─────────────────┤  ├─────────────────┤  ├─────────────────┤         │
   │  │ EvaluatorContext│  │  PolicyContext  │  │ FallbackContext │         │
   │  │   sm_registry   │  │ policy_registry │  │fallback_registry│         │
   │  │  conditions.py  │  │  conditions.py  │  │  conditions.py  │         │
   │  └─────────────────┘  └─────────────────┘  └─────────────────┘         │
   │                                                                         │
   └─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │    BaseContext      │
                         │     (Protocol)      │
                         │  shared conditions  │
                         └─────────────────────┘
```

### 2.2 Философия: Разделение ответственности

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  ПРИНЦИП: Условия — это ЛОГИКА, Правила — это МАППИНГ                        │
│           Домены — это ИЗОЛЯЦИЯ                                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  CONDITIONS (Python-функции)    RULES (Declarative)    DOMAINS (Isolation)  │
│  ───────────────────────────    ─────────────────────  ───────────────────  │
│  • Типизация (mypy)             • Читаемость           • SRP соблюдён       │
│  • IDE autocomplete             • Единый источник      • Type safety        │
│  • Breakpoints, debugging       • Легко изменить       • Open-Closed        │
│  • Stack traces при ошибках     • Валидация            • Изоляция условий   │
│  • Unit-тесты изолированно                             • Свой контекст      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.3 Принципы архитектуры

| Принцип | Описание |
|---------|----------|
| **Условия = Python** | Вся логика проверок — типизированные функции |
| **Правила = Декларативно** | Маппинг условие→действие в config.py |
| **Домены = Изоляция** | Каждый компонент имеет свой реестр и контекст |
| **Строгое разделение** | rules → action, transitions → state |
| **Type Safety** | mypy проверяет совместимость контекстов |
| **Open-Closed** | Новый домен = новый реестр, без изменения существующих |
| **Обратная совместимость** | Старые правила-строки продолжают работать |

---

## Часть 3: ДЕТАЛЬНОЕ ОПИСАНИЕ РЕШЕНИЯ

### 3.1 Формат rules и transitions (Schema)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  ПРИНЦИП: Строгое разделение ответственности                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  rules       → определяют ACTION (что делать)                               │
│  transitions → определяют STATE  (куда переходить)                          │
│                                                                             │
│  Условия — Python-функции, ссылаемся по имени (строке)                      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### RULES — определяют action

```python
# ═══════════════════════════════════════════════════════════════════════════
# ФОРМАТ ПРАВИЛ
# ═══════════════════════════════════════════════════════════════════════════

# Простое правило (обратная совместимость) — строка
"greeting": "acknowledge_and_continue"

# Одно условие — tuple (condition_name, action)
"comparison": ("has_competitor_mention", "compare_with_known_competitor")

# Несколько условий — list of tuples + default (последняя строка)
"price_question": [
    ("has_pricing_data", "answer_with_facts"),      # Приоритет 1
    ("price_repeated_3x", "answer_with_range"),     # Приоритет 2
    "deflect_and_continue"                          # Default
]

# Типы:
RuleValue = Union[
    str,                                    # Простое: "action"
    Tuple[str, str],                        # Одно условие: ("condition", "action")
    List[Union[Tuple[str, str], str]]       # Список + default
]
```

#### TRANSITIONS — определяют state

```python
# Простой переход (обратная совместимость)
"demo_request": "success"

# Условный переход — None означает "остаться в текущем состоянии"
"contact_provided": [
    ("in_spin_phase", "close"),     # Если в SPIN → в close
    "success"                        # Иначе → success
]

# Переход только при условии, иначе остаться
"demo_request": [
    ("has_contact", "success"),
    None                             # None = остаться в текущем состоянии
]
```

### 3.2 Базовый контекст (Protocol)

```python
# src/conditions/base.py

from typing import Protocol, Dict, Any, runtime_checkable


@runtime_checkable
class BaseContext(Protocol):
    """
    Базовый протокол для всех контекстов.

    Определяет общие поля, доступные во всех доменах.
    Условия, типизированные под BaseContext, могут использоваться везде.
    """

    @property
    def collected_data(self) -> Dict[str, Any]:
        """Собранные данные о клиенте."""
        ...

    @property
    def state(self) -> str:
        """Текущее состояние диалога."""
        ...

    @property
    def turn_number(self) -> int:
        """Номер хода в диалоге."""
        ...
```

### 3.3 Типизированный реестр (Generic)

```python
# src/conditions/registry.py

from typing import (
    Generic, TypeVar, Callable, Dict, Optional,
    List, Set, Any, Type
)
from dataclasses import dataclass, field
from functools import wraps
import inspect

from src.conditions.base import BaseContext


TContext = TypeVar("TContext", bound=BaseContext)


@dataclass
class ConditionMetadata(Generic[TContext]):
    """Метаданные условия."""
    name: str
    description: str
    func: Callable[[TContext], bool]
    context_type: Type[TContext]
    requires_fields: Set[str] = field(default_factory=set)
    category: str = "general"


class ConditionRegistry(Generic[TContext]):
    """
    Типизированный реестр условий для конкретного домена.

    Каждый домен (StateMachine, Policy, Fallback, Personalization)
    имеет свой реестр со своим типом контекста.

    Преимущества:
    - Type safety: mypy проверяет совместимость контекстов
    - Изоляция: условия одного домена не видны в другом
    - Open-Closed: новый домен = новый реестр, без изменения существующих
    """

    def __init__(self, name: str, context_type: Type[TContext]):
        self.name = name
        self.context_type = context_type
        self._conditions: Dict[str, ConditionMetadata[TContext]] = {}
        self._categories: Dict[str, List[str]] = {}

    def condition(
        self,
        name: str,
        description: str = "",
        requires_fields: Set[str] = None,
        category: str = "general"
    ) -> Callable[[Callable[[TContext], bool]], Callable[[TContext], bool]]:
        """
        Декоратор для регистрации условия.

        Пример:
            @sm_registry.condition("has_pricing_data", category="data")
            def has_pricing_data(ctx: EvaluatorContext) -> bool:
                return bool(ctx.collected_data.get("company_size"))
        """
        def decorator(func: Callable[[TContext], bool]) -> Callable[[TContext], bool]:
            # Валидация сигнатуры
            sig = inspect.signature(func)
            params = list(sig.parameters.values())

            if len(params) != 1:
                raise ValueError(
                    f"Condition '{name}' must accept exactly one parameter"
                )

            # Проверка аннотации параметра (если указана)
            param_annotation = params[0].annotation
            if param_annotation != inspect.Parameter.empty:
                if not (param_annotation == self.context_type or
                        param_annotation == BaseContext or
                        param_annotation.__name__ == self.context_type.__name__):
                    raise TypeError(
                        f"Condition '{name}' expects {param_annotation.__name__}, "
                        f"but registry is for {self.context_type.__name__}"
                    )

            metadata = ConditionMetadata(
                name=name,
                description=description or func.__doc__ or "",
                func=func,
                context_type=self.context_type,
                requires_fields=requires_fields or set(),
                category=category,
            )

            if name in self._conditions:
                raise ValueError(
                    f"Condition '{name}' already registered in {self.name}"
                )

            self._conditions[name] = metadata

            if category not in self._categories:
                self._categories[category] = []
            self._categories[category].append(name)

            @wraps(func)
            def wrapper(ctx: TContext) -> bool:
                return func(ctx)

            wrapper._condition_name = name
            wrapper._registry = self.name
            return wrapper

        return decorator

    def evaluate(
        self,
        name: str,
        ctx: TContext,
        trace: Optional["EvaluationTrace"] = None
    ) -> bool:
        """
        Вычислить условие.

        Args:
            name: Имя условия
            ctx: Контекст соответствующего типа
            trace: Опциональная трассировка для дебага

        Returns:
            Результат вычисления условия

        Raises:
            ConditionNotFoundError: Условие не найдено
            TypeError: Неверный тип контекста
            ConditionEvaluationError: Ошибка при вычислении
        """
        metadata = self._conditions.get(name)
        if metadata is None:
            raise ConditionNotFoundError(
                f"Condition '{name}' not found in registry '{self.name}'"
            )

        try:
            result = metadata.func(ctx)

            if trace:
                trace.record(name, result, ctx, metadata.requires_fields)

            return result

        except Exception as e:
            raise ConditionEvaluationError(
                f"Error evaluating '{name}' in '{self.name}': {e}"
            ) from e

    def get(self, name: str) -> Optional[ConditionMetadata[TContext]]:
        """Получить метаданные условия."""
        return self._conditions.get(name)

    def has(self, name: str) -> bool:
        """Проверить существование условия."""
        return name in self._conditions

    def list_all(self) -> List[str]:
        """Список всех условий."""
        return list(self._conditions.keys())

    def list_by_category(self, category: str) -> List[str]:
        """Список условий по категории."""
        return self._categories.get(category, [])

    def get_categories(self) -> List[str]:
        """Список всех категорий."""
        return list(self._categories.keys())

    def validate_all(self, ctx_factory: Callable[[], TContext]) -> Dict[str, Any]:
        """
        Валидация всех условий на тестовом контексте.

        Args:
            ctx_factory: Фабрика для создания тестового контекста

        Returns:
            Результаты валидации
        """
        results = {"passed": [], "failed": [], "errors": []}
        test_ctx = ctx_factory()

        for name, metadata in self._conditions.items():
            try:
                result = metadata.func(test_ctx)
                if not isinstance(result, bool):
                    results["failed"].append({
                        "name": name,
                        "reason": f"Returned {type(result).__name__}, expected bool"
                    })
                else:
                    results["passed"].append(name)
            except Exception as e:
                results["errors"].append({"name": name, "error": str(e)})

        return results

    def get_documentation(self) -> str:
        """Генерация документации по условиям реестра."""
        lines = [f"# {self.name.title()} Conditions\n"]
        lines.append(f"Context: `{self.context_type.__name__}`\n")

        for category in sorted(self._categories.keys()):
            lines.append(f"\n## {category.title()}\n")
            for name in sorted(self._categories[category]):
                meta = self._conditions[name]
                lines.append(f"### `{name}`")
                lines.append(f"{meta.description}\n")
                if meta.requires_fields:
                    lines.append(f"**Requires:** {', '.join(meta.requires_fields)}\n")

        return "\n".join(lines)


class ConditionNotFoundError(Exception):
    """Условие не найдено в реестре."""
    pass


class ConditionEvaluationError(Exception):
    """Ошибка при вычислении условия."""
    pass
```

### 3.4 Трассировка выполнения

```python
# src/conditions/trace.py

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Set
from datetime import datetime


@dataclass
class TraceEntry:
    """Одна запись в трассировке."""
    condition_name: str
    result: bool
    timestamp: datetime
    context_snapshot: Dict[str, Any]
    evaluation_time_ms: float = 0.0


@dataclass
class EvaluationTrace:
    """
    Трассировка вычисления условий.

    Позволяет понять:
    - Какие условия проверялись
    - В каком порядке
    - С каким результатом
    - На каком контексте
    """
    rule_name: str
    intent: str
    state: str
    domain: str = ""  # "state_machine", "policy", "fallback", etc.
    entries: List[TraceEntry] = field(default_factory=list)
    final_action: Optional[str] = None
    resolution: str = ""  # "condition_matched", "default", "simple"
    matched_condition: Optional[str] = None

    def record(
        self,
        condition_name: str,
        result: bool,
        ctx: Any,
        relevant_fields: Set[str] = None
    ):
        """Записать результат проверки условия."""
        context_snapshot = {}

        if relevant_fields:
            for field_name in relevant_fields:
                if hasattr(ctx, field_name):
                    context_snapshot[field_name] = getattr(ctx, field_name)
                elif hasattr(ctx, "collected_data") and field_name in ctx.collected_data:
                    context_snapshot[field_name] = ctx.collected_data[field_name]
        else:
            # Базовые поля
            if hasattr(ctx, "state"):
                context_snapshot["state"] = ctx.state
            if hasattr(ctx, "turn_number"):
                context_snapshot["turn_number"] = ctx.turn_number

        self.entries.append(TraceEntry(
            condition_name=condition_name,
            result=result,
            timestamp=datetime.now(),
            context_snapshot=context_snapshot,
        ))

    def set_result(self, action: str, resolution: str, matched: Optional[str] = None):
        """Установить финальный результат."""
        self.final_action = action
        self.resolution = resolution
        self.matched_condition = matched

    def to_dict(self) -> Dict[str, Any]:
        """Сериализация для логов."""
        return {
            "rule_name": self.rule_name,
            "intent": self.intent,
            "state": self.state,
            "domain": self.domain,
            "final_action": self.final_action,
            "resolution": self.resolution,
            "matched_condition": self.matched_condition,
            "conditions_checked": len(self.entries),
            "entries": [
                {
                    "condition": e.condition_name,
                    "result": e.result,
                    "context": e.context_snapshot,
                }
                for e in self.entries
            ]
        }

    def to_compact_string(self) -> str:
        """Компактное представление для логов симуляций."""
        if self.resolution == "simple":
            return f"[RULE] simple → {self.final_action}"

        lines = []

        if self.resolution == "condition_matched":
            lines.append(f"[RULE] conditional → MATCHED")
        else:
            lines.append(f"[RULE] conditional → DEFAULT")

        for entry in self.entries:
            result_str = "PASS" if entry.result else "FAIL"
            ctx_str = ", ".join(f"{k}={v}" for k, v in entry.context_snapshot.items())
            lines.append(f"       {entry.condition_name}={result_str} ({ctx_str})")

        lines.append(f"       → {self.final_action}")

        return "\n".join(lines)


class TraceCollector:
    """Коллектор трассировок для симуляций."""

    def __init__(self, simulation_id: Optional[int] = None):
        self.simulation_id = simulation_id
        self.traces: List[EvaluationTrace] = []

    def create_trace(
        self,
        rule_name: str,
        intent: str,
        state: str,
        domain: str = ""
    ) -> EvaluationTrace:
        """Создать новую трассировку."""
        trace = EvaluationTrace(
            rule_name=rule_name,
            intent=intent,
            state=state,
            domain=domain
        )
        self.traces.append(trace)
        return trace

    def get_summary(self) -> Dict[str, Any]:
        """Статистика по трассировкам."""
        total = len(self.traces)
        matched = sum(1 for t in self.traces if t.resolution == "condition_matched")
        defaults = sum(1 for t in self.traces if t.resolution == "default")

        # По доменам
        by_domain = {}
        for trace in self.traces:
            domain = trace.domain or "unknown"
            if domain not in by_domain:
                by_domain[domain] = {"total": 0, "matched": 0}
            by_domain[domain]["total"] += 1
            if trace.resolution == "condition_matched":
                by_domain[domain]["matched"] += 1

        # Статистика по условиям
        condition_hits = {}
        for trace in self.traces:
            for entry in trace.entries:
                if entry.condition_name not in condition_hits:
                    condition_hits[entry.condition_name] = {"checked": 0, "passed": 0}
                condition_hits[entry.condition_name]["checked"] += 1
                if entry.result:
                    condition_hits[entry.condition_name]["passed"] += 1

        return {
            "simulation_id": self.simulation_id,
            "total_rules_evaluated": total,
            "conditions_matched": matched,
            "defaults_used": defaults,
            "match_rate": matched / total if total > 0 else 0,
            "by_domain": by_domain,
            "condition_stats": condition_hits
        }
```

---

## Часть 4: ДОМЕННЫЕ РЕЕСТРЫ

### 4.1 StateMachine домен

#### Контекст

```python
# src/conditions/state_machine/context.py

from dataclasses import dataclass
from typing import Dict, Any, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from src.intent_tracker import IntentTracker


@dataclass
class EvaluatorContext:
    """
    Контекст для условий StateMachine.

    Реализует BaseContext + специфичные поля для SM.
    """
    # BaseContext fields
    collected_data: Dict[str, Any]
    state: str
    turn_number: int

    # SM-specific fields
    spin_phase: Optional[str]
    is_spin_state: bool
    current_intent: str
    prev_intent: Optional[str]
    intent_tracker: "IntentTracker"
    missing_required_data: List[str]

    @classmethod
    def from_state_machine(cls, sm: "StateMachine", intent: str) -> "EvaluatorContext":
        """
        Создать контекст из StateMachine.

        ВАЖНО: intent_tracker.record() должен быть вызван ДО этого метода.
        """
        from src.config import SALES_CONFIG

        config = SALES_CONFIG.get("states", {}).get(sm.state, {})
        required = config.get("required_data", [])
        missing = [f for f in required if not sm.collected_data.get(f)]

        return cls(
            collected_data=sm.collected_data.copy(),
            state=sm.state,
            turn_number=len(sm.intent_tracker.history),
            spin_phase=config.get("spin_phase"),
            is_spin_state=config.get("spin_phase") is not None,
            current_intent=intent,
            prev_intent=sm.intent_tracker.prev_intent,
            intent_tracker=sm.intent_tracker,
            missing_required_data=missing,
        )


def create_sm_test_context(**overrides) -> EvaluatorContext:
    """Фабрика для тестов."""
    from src.intent_tracker import IntentTracker

    tracker = overrides.pop("intent_tracker", None) or IntentTracker()

    defaults = {
        "collected_data": {},
        "state": "spin_situation",
        "turn_number": 1,
        "spin_phase": "situation",
        "is_spin_state": True,
        "current_intent": "unclear",
        "prev_intent": None,
        "intent_tracker": tracker,
        "missing_required_data": [],
    }
    defaults.update(overrides)

    return EvaluatorContext(**defaults)
```

#### Реестр и декоратор

```python
# src/conditions/state_machine/registry.py

from src.conditions.registry import ConditionRegistry
from src.conditions.state_machine.context import EvaluatorContext

# Реестр для StateMachine
sm_registry = ConditionRegistry(
    name="state_machine",
    context_type=EvaluatorContext
)

# Алиас для декоратора
sm_condition = sm_registry.condition
```

#### Условия

```python
# src/conditions/state_machine/conditions.py
"""Условия для StateMachine."""

from src.conditions.state_machine.registry import sm_condition
from src.conditions.state_machine.context import EvaluatorContext


# ═══════════════════════════════════════════════════════════════════════════
# DATA CONDITIONS
# ═══════════════════════════════════════════════════════════════════════════

@sm_condition(
    name="has_pricing_data",
    description="Есть данные для расчёта цены (размер компании или количество пользователей)",
    requires_fields={"company_size", "users_count"},
    category="data"
)
def has_pricing_data(ctx: EvaluatorContext) -> bool:
    return bool(
        ctx.collected_data.get("company_size") or
        ctx.collected_data.get("users_count")
    )


@sm_condition(
    name="has_pain_point",
    description="Клиент озвучил проблему/боль",
    requires_fields={"pain_point", "pain_category"},
    category="data"
)
def has_pain_point(ctx: EvaluatorContext) -> bool:
    return bool(
        ctx.collected_data.get("pain_point") or
        ctx.collected_data.get("pain_category")
    )


@sm_condition(
    name="has_contact",
    description="Есть контактные данные клиента",
    requires_fields={"contact_info", "phone", "email"},
    category="data"
)
def has_contact(ctx: EvaluatorContext) -> bool:
    return bool(
        ctx.collected_data.get("contact_info") or
        ctx.collected_data.get("phone") or
        ctx.collected_data.get("email")
    )


@sm_condition(
    name="has_competitor_mention",
    description="Клиент упомянул конкурента",
    requires_fields={"competitor_mentioned", "current_crm"},
    category="data"
)
def has_competitor_mention(ctx: EvaluatorContext) -> bool:
    return bool(
        ctx.collected_data.get("competitor_mentioned") or
        ctx.collected_data.get("current_crm")
    )


@sm_condition(
    name="data_complete",
    description="Все обязательные данные для текущего состояния собраны",
    category="data"
)
def data_complete(ctx: EvaluatorContext) -> bool:
    return len(ctx.missing_required_data) == 0


@sm_condition(
    name="ready_for_pricing",
    description="Готов к обсуждению цены: есть размер компании И боль",
    requires_fields={"company_size", "pain_point"},
    category="data"
)
def ready_for_pricing(ctx: EvaluatorContext) -> bool:
    has_size = bool(ctx.collected_data.get("company_size"))
    has_pain = bool(
        ctx.collected_data.get("pain_point") or
        ctx.collected_data.get("pain_category")
    )
    return has_size and has_pain


# ═══════════════════════════════════════════════════════════════════════════
# INTENT CONDITIONS
# ═══════════════════════════════════════════════════════════════════════════

@sm_condition(
    name="price_repeated_3x",
    description="Вопрос о цене задан 3+ раз подряд",
    requires_fields={"intent_tracker"},
    category="intent"
)
def price_repeated_3x(ctx: EvaluatorContext) -> bool:
    if ctx.current_intent != "price_question":
        return False
    return ctx.intent_tracker.streak_count("price_question") >= 3


@sm_condition(
    name="question_repeated_2x",
    description="Текущий вопрос задан 2+ раз подряд",
    requires_fields={"intent_tracker"},
    category="intent"
)
def question_repeated_2x(ctx: EvaluatorContext) -> bool:
    return ctx.intent_tracker.streak_count(ctx.current_intent) >= 2


@sm_condition(
    name="after_objection",
    description="Предыдущий интент был возражением",
    requires_fields={"prev_intent"},
    category="intent"
)
def after_objection(ctx: EvaluatorContext) -> bool:
    return ctx.prev_intent is not None and ctx.prev_intent.startswith("objection_")


# ═══════════════════════════════════════════════════════════════════════════
# COUNTER CONDITIONS
# ═══════════════════════════════════════════════════════════════════════════

@sm_condition(
    name="objection_limit_reached",
    description="Достигнут лимит возражений подряд (3+)",
    requires_fields={"intent_tracker"},
    category="counter"
)
def objection_limit_reached(ctx: EvaluatorContext) -> bool:
    return ctx.intent_tracker.objection_consecutive() >= 3


@sm_condition(
    name="many_objections_total",
    description="Много возражений за диалог (5+)",
    requires_fields={"intent_tracker"},
    category="counter"
)
def many_objections_total(ctx: EvaluatorContext) -> bool:
    return ctx.intent_tracker.objection_total() >= 5


@sm_condition(
    name="early_conversation",
    description="Начало разговора (первые 3 хода)",
    category="counter"
)
def early_conversation(ctx: EvaluatorContext) -> bool:
    return ctx.turn_number <= 3


@sm_condition(
    name="late_conversation",
    description="Затянувшийся разговор (10+ ходов)",
    category="counter"
)
def late_conversation(ctx: EvaluatorContext) -> bool:
    return ctx.turn_number > 10


# ═══════════════════════════════════════════════════════════════════════════
# STATE CONDITIONS
# ═══════════════════════════════════════════════════════════════════════════

@sm_condition(
    name="in_spin_phase",
    description="Находимся в SPIN-фазе диалога",
    category="state"
)
def in_spin_phase(ctx: EvaluatorContext) -> bool:
    return ctx.is_spin_state


@sm_condition(
    name="in_closing_phase",
    description="Находимся в фазе закрытия (close, soft_close)",
    category="state"
)
def in_closing_phase(ctx: EvaluatorContext) -> bool:
    return ctx.state in ("close", "soft_close")


@sm_condition(
    name="past_spin",
    description="Вышли из SPIN-фазы (presentation, close, etc.)",
    category="state"
)
def past_spin(ctx: EvaluatorContext) -> bool:
    return not ctx.is_spin_state and ctx.state not in ("greeting", "initial")


# ═══════════════════════════════════════════════════════════════════════════
# COMPOSITE CONDITIONS
# ═══════════════════════════════════════════════════════════════════════════

@sm_condition(
    name="should_answer_price",
    description="Следует ответить на вопрос о цене: есть данные ИЛИ спросили 3+ раз",
    category="composite"
)
def should_answer_price(ctx: EvaluatorContext) -> bool:
    has_data = bool(
        ctx.collected_data.get("company_size") or
        ctx.collected_data.get("users_count")
    )
    repeated = (
        ctx.current_intent == "price_question" and
        ctx.intent_tracker.streak_count("price_question") >= 3
    )
    return has_data or repeated


@sm_condition(
    name="can_handle_objection_with_roi",
    description="Можно обработать возражение о цене через ROI",
    category="composite"
)
def can_handle_objection_with_roi(ctx: EvaluatorContext) -> bool:
    has_pricing = bool(ctx.collected_data.get("company_size"))
    has_pain = bool(
        ctx.collected_data.get("pain_point") or
        ctx.collected_data.get("pain_category")
    )
    return has_pricing and has_pain


@sm_condition(
    name="should_soft_close",
    description="Пора предложить мягкое завершение",
    category="composite"
)
def should_soft_close(ctx: EvaluatorContext) -> bool:
    objection_limit = ctx.intent_tracker.objection_consecutive() >= 3
    in_closing = ctx.state in ("close", "soft_close")
    return objection_limit and in_closing
```

### 4.2 DialoguePolicy домен

#### Контекст

```python
# src/conditions/policy/context.py

from dataclasses import dataclass
from typing import Dict, Any, List, Optional


@dataclass
class PolicyContext:
    """
    Контекст для условий DialoguePolicy.

    Содержит сигналы о качестве диалога и необходимости вмешательства.
    """
    # BaseContext fields
    collected_data: Dict[str, Any]
    state: str
    turn_number: int

    # Policy-specific fields
    oscillation_detected: bool           # Осцилляция между состояниями
    confidence_trend: str                # "rising", "falling", "stable"
    momentum_direction: str              # "positive", "negative", "neutral"
    turns_in_state: int                  # Сколько ходов в текущем состоянии
    breakthrough_detected: bool          # Был ли прорыв в диалоге
    turns_since_breakthrough: int        # Ходов с момента прорыва
    total_objections: int                # Всего возражений
    repeated_objection_types: List[str]  # Повторяющиеся типы возражений
    current_action: Optional[str]        # Текущее предлагаемое действие
    frustration_level: float             # 0.0 - 1.0

    @classmethod
    def from_envelope(
        cls,
        envelope: "ContextEnvelope",
        sm_result: Dict[str, Any]
    ) -> "PolicyContext":
        """Создать контекст из ContextEnvelope."""
        return cls(
            collected_data=envelope.collected_data,
            state=sm_result.get("next_state", envelope.state),
            turn_number=envelope.turn_number,
            oscillation_detected=envelope.oscillation_detected,
            confidence_trend=envelope.confidence_trend,
            momentum_direction=envelope.momentum_direction,
            turns_in_state=envelope.turns_in_state,
            breakthrough_detected=envelope.has_breakthrough,
            turns_since_breakthrough=envelope.turns_since_breakthrough,
            total_objections=envelope.total_objections,
            repeated_objection_types=envelope.repeated_objection_types,
            current_action=sm_result.get("action"),
            frustration_level=envelope.frustration_level,
        )


def create_policy_test_context(**overrides) -> PolicyContext:
    """Фабрика для тестов."""
    defaults = {
        "collected_data": {},
        "state": "spin_situation",
        "turn_number": 1,
        "oscillation_detected": False,
        "confidence_trend": "stable",
        "momentum_direction": "neutral",
        "turns_in_state": 1,
        "breakthrough_detected": False,
        "turns_since_breakthrough": 0,
        "total_objections": 0,
        "repeated_objection_types": [],
        "current_action": None,
        "frustration_level": 0.0,
    }
    defaults.update(overrides)
    return PolicyContext(**defaults)
```

#### Реестр и условия

```python
# src/conditions/policy/registry.py

from src.conditions.registry import ConditionRegistry
from src.conditions.policy.context import PolicyContext

policy_registry = ConditionRegistry(
    name="policy",
    context_type=PolicyContext
)

policy_condition = policy_registry.condition
```

```python
# src/conditions/policy/conditions.py
"""Условия для DialoguePolicy."""

from src.conditions.policy.registry import policy_condition
from src.conditions.policy.context import PolicyContext


# ═══════════════════════════════════════════════════════════════════════════
# REPAIR CONDITIONS
# ═══════════════════════════════════════════════════════════════════════════

@policy_condition(
    name="is_stuck",
    description="Диалог застрял: осцилляция + падающая уверенность",
    category="repair"
)
def is_stuck(ctx: PolicyContext) -> bool:
    return ctx.oscillation_detected and ctx.confidence_trend == "falling"


@policy_condition(
    name="needs_repair",
    description="Нужен repair: много ходов в одном состоянии без прогресса",
    category="repair"
)
def needs_repair(ctx: PolicyContext) -> bool:
    return ctx.turns_in_state >= 5 and not ctx.breakthrough_detected


@policy_condition(
    name="clarification_needed",
    description="Нужно уточнение: много ходов без данных",
    category="repair"
)
def clarification_needed(ctx: PolicyContext) -> bool:
    no_progress = ctx.turns_in_state >= 3
    no_data = len(ctx.collected_data) < 2
    return no_progress and no_data


# ═══════════════════════════════════════════════════════════════════════════
# MOMENTUM CONDITIONS
# ═══════════════════════════════════════════════════════════════════════════

@policy_condition(
    name="has_breakthrough_window",
    description="Окно после прорыва (1-3 хода) — можно продвигать",
    category="momentum"
)
def has_breakthrough_window(ctx: PolicyContext) -> bool:
    return (
        ctx.breakthrough_detected and
        1 <= ctx.turns_since_breakthrough <= 3
    )


@policy_condition(
    name="positive_momentum",
    description="Положительный momentum — диалог идёт хорошо",
    category="momentum"
)
def positive_momentum(ctx: PolicyContext) -> bool:
    return ctx.momentum_direction == "positive"


@policy_condition(
    name="negative_momentum",
    description="Отрицательный momentum — диалог ухудшается",
    category="momentum"
)
def negative_momentum(ctx: PolicyContext) -> bool:
    return ctx.momentum_direction == "negative"


@policy_condition(
    name="confidence_rising",
    description="Уверенность растёт",
    category="momentum"
)
def confidence_rising(ctx: PolicyContext) -> bool:
    return ctx.confidence_trend == "rising"


# ═══════════════════════════════════════════════════════════════════════════
# ESCALATION CONDITIONS
# ═══════════════════════════════════════════════════════════════════════════

@policy_condition(
    name="high_frustration",
    description="Высокий уровень фрустрации клиента (>=0.7)",
    category="escalation"
)
def high_frustration(ctx: PolicyContext) -> bool:
    return ctx.frustration_level >= 0.7


@policy_condition(
    name="medium_frustration",
    description="Средний уровень фрустрации (0.4-0.7)",
    category="escalation"
)
def medium_frustration(ctx: PolicyContext) -> bool:
    return 0.4 <= ctx.frustration_level < 0.7


@policy_condition(
    name="should_deescalate",
    description="Нужна деэскалация: высокая фрустрация + негативный momentum",
    category="escalation"
)
def should_deescalate(ctx: PolicyContext) -> bool:
    return ctx.frustration_level >= 0.7 and ctx.momentum_direction == "negative"


# ═══════════════════════════════════════════════════════════════════════════
# OBJECTION CONDITIONS
# ═══════════════════════════════════════════════════════════════════════════

@policy_condition(
    name="repeated_objections",
    description="Есть повторяющиеся возражения",
    category="objection"
)
def repeated_objections(ctx: PolicyContext) -> bool:
    return len(ctx.repeated_objection_types) > 0


@policy_condition(
    name="objection_fatigue",
    description="Усталость от возражений: 3+ возражений + негативный momentum",
    category="objection"
)
def objection_fatigue(ctx: PolicyContext) -> bool:
    return ctx.total_objections >= 3 and ctx.momentum_direction == "negative"


@policy_condition(
    name="same_objection_repeated",
    description="Одно и то же возражение повторяется",
    category="objection"
)
def same_objection_repeated(ctx: PolicyContext) -> bool:
    return len(ctx.repeated_objection_types) >= 1


# ═══════════════════════════════════════════════════════════════════════════
# CONSERVATIVE CONDITIONS
# ═══════════════════════════════════════════════════════════════════════════

@policy_condition(
    name="should_be_conservative",
    description="Нужен консервативный подход: негативный momentum в SPIN",
    category="conservative"
)
def should_be_conservative(ctx: PolicyContext) -> bool:
    is_spin = ctx.state.startswith("spin_")
    return is_spin and ctx.momentum_direction == "negative"
```

### 4.3 FallbackHandler домен

#### Контекст

```python
# src/conditions/fallback/context.py

from dataclasses import dataclass
from typing import Dict, Any, Optional


@dataclass
class FallbackContext:
    """
    Контекст для условий FallbackHandler.

    Содержит информацию о fallback'ах и эскалации.
    """
    # BaseContext fields
    collected_data: Dict[str, Any]
    state: str
    turn_number: int

    # Fallback-specific fields
    total_fallbacks: int             # Всего fallback'ов за диалог
    consecutive_fallbacks: int       # Fallback'ов подряд
    current_tier: str                # "tier_1", "tier_2", "tier_3"
    fallbacks_in_state: int          # Fallback'ов в текущем состоянии
    last_successful_intent: Optional[str]  # Последний успешный интент

    # Context signals
    frustration_level: float         # 0.0 - 1.0
    momentum_direction: str          # "positive", "negative", "neutral"
    engagement_level: str            # "high", "medium", "low"

    # Data for dynamic CTA
    pain_category: Optional[str]
    competitor_mentioned: bool
    last_intent: Optional[str]

    @classmethod
    def from_handler(
        cls,
        handler: "FallbackHandler",
        current_tier: str,
        state: str,
        envelope: Optional["ContextEnvelope"] = None,
        context: Optional[Dict] = None
    ) -> "FallbackContext":
        """Создать контекст из FallbackHandler."""
        ctx = context or {}
        collected = ctx.get("collected_data", {})

        return cls(
            collected_data=collected,
            state=state,
            turn_number=ctx.get("turn_number", 0),
            total_fallbacks=handler.stats.total_count,
            consecutive_fallbacks=handler.get_consecutive_count(),
            current_tier=current_tier,
            fallbacks_in_state=handler.stats.state_counts.get(state, 0),
            last_successful_intent=handler.stats.last_successful_intent,
            frustration_level=envelope.frustration_level if envelope else 0.0,
            momentum_direction=envelope.momentum_direction if envelope else "neutral",
            engagement_level=envelope.engagement_level if envelope else "medium",
            pain_category=collected.get("pain_category"),
            competitor_mentioned=bool(collected.get("competitor_mentioned")),
            last_intent=ctx.get("last_intent"),
        )


def create_fallback_test_context(**overrides) -> FallbackContext:
    """Фабрика для тестов."""
    defaults = {
        "collected_data": {},
        "state": "spin_situation",
        "turn_number": 1,
        "total_fallbacks": 0,
        "consecutive_fallbacks": 0,
        "current_tier": "tier_1",
        "fallbacks_in_state": 0,
        "last_successful_intent": None,
        "frustration_level": 0.0,
        "momentum_direction": "neutral",
        "engagement_level": "medium",
        "pain_category": None,
        "competitor_mentioned": False,
        "last_intent": None,
    }
    defaults.update(overrides)
    return FallbackContext(**defaults)
```

#### Реестр и условия

```python
# src/conditions/fallback/registry.py

from src.conditions.registry import ConditionRegistry
from src.conditions.fallback.context import FallbackContext

fallback_registry = ConditionRegistry(
    name="fallback",
    context_type=FallbackContext
)

fallback_condition = fallback_registry.condition
```

```python
# src/conditions/fallback/conditions.py
"""Условия для FallbackHandler."""

from src.conditions.fallback.registry import fallback_condition
from src.conditions.fallback.context import FallbackContext


# ═══════════════════════════════════════════════════════════════════════════
# ESCALATION CONDITIONS — когда пропустить tiers
# ═══════════════════════════════════════════════════════════════════════════

@fallback_condition(
    name="frustrated_with_fallbacks",
    description="Фрустрация + 2+ fallback подряд → сразу на tier 3",
    category="escalation"
)
def frustrated_with_fallbacks(ctx: FallbackContext) -> bool:
    return ctx.consecutive_fallbacks >= 2 and ctx.frustration_level >= 0.7


@fallback_condition(
    name="stuck_in_state",
    description="3+ fallback в одном состоянии → пропустить на tier 3",
    category="escalation"
)
def stuck_in_state(ctx: FallbackContext) -> bool:
    return ctx.fallbacks_in_state >= 3


@fallback_condition(
    name="exhausted_patience",
    description="4+ fallback + low engagement → soft_close",
    category="escalation"
)
def exhausted_patience(ctx: FallbackContext) -> bool:
    return ctx.total_fallbacks >= 4 and ctx.engagement_level == "low"


@fallback_condition(
    name="late_stage_fallback",
    description="Fallback в поздней стадии → пропустить tier 2",
    category="escalation"
)
def late_stage_fallback(ctx: FallbackContext) -> bool:
    return ctx.state in ("close", "presentation")


# ═══════════════════════════════════════════════════════════════════════════
# STAY CONDITIONS — когда остаться на текущем tier
# ═══════════════════════════════════════════════════════════════════════════

@fallback_condition(
    name="positive_momentum_fallback",
    description="Положительный momentum + мало fallback → дать ещё шанс",
    category="stay"
)
def positive_momentum_fallback(ctx: FallbackContext) -> bool:
    return ctx.momentum_direction == "positive" and ctx.consecutive_fallbacks <= 1


@fallback_condition(
    name="first_fallback",
    description="Первый fallback в диалоге",
    category="stay"
)
def first_fallback(ctx: FallbackContext) -> bool:
    return ctx.total_fallbacks <= 1


# ═══════════════════════════════════════════════════════════════════════════
# CTA CONDITIONS — для Dynamic CTA выбора
# ═══════════════════════════════════════════════════════════════════════════

@fallback_condition(
    name="has_competitor_for_cta",
    description="Упомянут конкурент → CTA про сравнение",
    category="cta"
)
def has_competitor_for_cta(ctx: FallbackContext) -> bool:
    return ctx.competitor_mentioned


@fallback_condition(
    name="has_pain_for_cta",
    description="Есть pain category → CTA про решение проблемы",
    category="cta"
)
def has_pain_for_cta(ctx: FallbackContext) -> bool:
    return ctx.pain_category is not None


@fallback_condition(
    name="after_price_question_cta",
    description="После вопроса о цене → CTA про условия оплаты",
    category="cta"
)
def after_price_question_cta(ctx: FallbackContext) -> bool:
    return ctx.last_intent in ("price_question", "pricing_details", "objection_price")


@fallback_condition(
    name="after_features_question_cta",
    description="После вопроса о функциях → CTA про демо",
    category="cta"
)
def after_features_question_cta(ctx: FallbackContext) -> bool:
    return ctx.last_intent in ("question_features", "question_integrations", "question_how")


@fallback_condition(
    name="large_company_cta",
    description="Крупная компания → CTA про enterprise",
    category="cta"
)
def large_company_cta(ctx: FallbackContext) -> bool:
    size = ctx.collected_data.get("company_size")
    if size is None:
        return False
    try:
        return int(size) > 20
    except (ValueError, TypeError):
        return False
```

### 4.4 PersonalizationEngine домен

#### Контекст

```python
# src/conditions/personalization/context.py

from dataclasses import dataclass
from typing import Dict, Any, Optional


@dataclass
class PersonalizationContext:
    """
    Контекст для условий PersonalizationEngine.

    Содержит информацию для выбора стиля messaging.
    """
    # BaseContext fields
    collected_data: Dict[str, Any]
    state: str
    turn_number: int

    # Company data
    company_size: Optional[int]
    role: Optional[str]
    industry: Optional[str]

    # Pain data
    pain_category: Optional[str]
    pain_point: Optional[str]
    current_crm: Optional[str]

    # Context signals
    has_breakthrough: bool
    engagement_level: str
    objection_type: Optional[str]

    @classmethod
    def from_collected_data(
        cls,
        collected_data: Dict[str, Any],
        envelope: Optional["ContextEnvelope"] = None,
        context: Optional[Dict] = None
    ) -> "PersonalizationContext":
        """Создать контекст из собранных данных."""
        ctx = context or {}

        # Parse company_size
        company_size = collected_data.get("company_size")
        if isinstance(company_size, str):
            try:
                company_size = int(company_size)
            except ValueError:
                company_size = None

        return cls(
            collected_data=collected_data,
            state=ctx.get("state", ""),
            turn_number=ctx.get("turn_number", 0),
            company_size=company_size,
            role=collected_data.get("role"),
            industry=collected_data.get("industry"),
            pain_category=collected_data.get("pain_category"),
            pain_point=collected_data.get("pain_point"),
            current_crm=collected_data.get("current_crm"),
            has_breakthrough=envelope.has_breakthrough if envelope else False,
            engagement_level=envelope.engagement_level if envelope else "medium",
            objection_type=ctx.get("objection_type"),
        )


def create_personalization_test_context(**overrides) -> PersonalizationContext:
    """Фабрика для тестов."""
    defaults = {
        "collected_data": {},
        "state": "spin_situation",
        "turn_number": 1,
        "company_size": None,
        "role": None,
        "industry": None,
        "pain_category": None,
        "pain_point": None,
        "current_crm": None,
        "has_breakthrough": False,
        "engagement_level": "medium",
        "objection_type": None,
    }
    defaults.update(overrides)
    return PersonalizationContext(**defaults)
```

#### Реестр и условия

```python
# src/conditions/personalization/registry.py

from src.conditions.registry import ConditionRegistry
from src.conditions.personalization.context import PersonalizationContext

personalization_registry = ConditionRegistry(
    name="personalization",
    context_type=PersonalizationContext
)

personalization_condition = personalization_registry.condition
```

```python
# src/conditions/personalization/conditions.py
"""Условия для PersonalizationEngine."""

from src.conditions.personalization.registry import personalization_condition
from src.conditions.personalization.context import PersonalizationContext


# ═══════════════════════════════════════════════════════════════════════════
# SIZE CONDITIONS
# ═══════════════════════════════════════════════════════════════════════════

@personalization_condition(
    name="is_micro_company",
    description="Микро-компания (1-5 человек)",
    category="size"
)
def is_micro_company(ctx: PersonalizationContext) -> bool:
    return ctx.company_size is not None and 1 <= ctx.company_size <= 5


@personalization_condition(
    name="is_small_company",
    description="Небольшая компания (6-15 человек)",
    category="size"
)
def is_small_company(ctx: PersonalizationContext) -> bool:
    return ctx.company_size is not None and 6 <= ctx.company_size <= 15


@personalization_condition(
    name="is_medium_company",
    description="Средняя компания (16-50 человек)",
    category="size"
)
def is_medium_company(ctx: PersonalizationContext) -> bool:
    return ctx.company_size is not None and 16 <= ctx.company_size <= 50


@personalization_condition(
    name="is_large_company",
    description="Крупная компания (50+ человек)",
    category="size"
)
def is_large_company(ctx: PersonalizationContext) -> bool:
    return ctx.company_size is not None and ctx.company_size > 50


# ═══════════════════════════════════════════════════════════════════════════
# ROLE CONDITIONS
# ═══════════════════════════════════════════════════════════════════════════

@personalization_condition(
    name="is_decision_maker",
    description="Роль = ЛПР (owner, director, ceo, founder)",
    category="role"
)
def is_decision_maker(ctx: PersonalizationContext) -> bool:
    return ctx.role in ("owner", "director", "ceo", "founder")


@personalization_condition(
    name="is_technical_role",
    description="Техническая роль (it, admin, developer, cto)",
    category="role"
)
def is_technical_role(ctx: PersonalizationContext) -> bool:
    return ctx.role in ("it", "admin", "developer", "cto")


@personalization_condition(
    name="is_sales_role",
    description="Роль в продажах (sales, manager, rop)",
    category="role"
)
def is_sales_role(ctx: PersonalizationContext) -> bool:
    return ctx.role in ("sales", "manager", "rop", "sales_manager")


# ═══════════════════════════════════════════════════════════════════════════
# PAIN CONDITIONS
# ═══════════════════════════════════════════════════════════════════════════

@personalization_condition(
    name="pain_is_no_control",
    description="Боль = нет контроля над командой/процессами",
    category="pain"
)
def pain_is_no_control(ctx: PersonalizationContext) -> bool:
    return ctx.pain_category == "no_control"


@personalization_condition(
    name="pain_is_manual_work",
    description="Боль = много ручной работы",
    category="pain"
)
def pain_is_manual_work(ctx: PersonalizationContext) -> bool:
    return ctx.pain_category == "manual_work"


@personalization_condition(
    name="pain_is_losing_clients",
    description="Боль = теряют клиентов",
    category="pain"
)
def pain_is_losing_clients(ctx: PersonalizationContext) -> bool:
    return ctx.pain_category == "losing_clients"


@personalization_condition(
    name="has_any_pain",
    description="Есть какая-либо боль",
    category="pain"
)
def has_any_pain(ctx: PersonalizationContext) -> bool:
    return ctx.pain_point is not None or ctx.pain_category is not None


# ═══════════════════════════════════════════════════════════════════════════
# EXPERIENCE CONDITIONS
# ═══════════════════════════════════════════════════════════════════════════

@personalization_condition(
    name="has_crm_experience",
    description="Есть опыт с CRM-системами",
    category="experience"
)
def has_crm_experience(ctx: PersonalizationContext) -> bool:
    return ctx.current_crm is not None


@personalization_condition(
    name="no_crm_experience",
    description="Нет опыта с CRM",
    category="experience"
)
def no_crm_experience(ctx: PersonalizationContext) -> bool:
    return ctx.current_crm is None


# ═══════════════════════════════════════════════════════════════════════════
# MESSAGING STYLE CONDITIONS (composite)
# ═══════════════════════════════════════════════════════════════════════════

@personalization_condition(
    name="use_roi_style",
    description="ROI-стиль: крупная компания + есть данные для расчёта",
    category="style"
)
def use_roi_style(ctx: PersonalizationContext) -> bool:
    is_large = ctx.company_size is not None and ctx.company_size > 50
    has_data = ctx.pain_point is not None or ctx.current_crm is not None
    return is_large and has_data


@personalization_condition(
    name="use_simplicity_style",
    description="Simplicity-стиль: микро компания или ЛПР маленькой компании",
    category="style"
)
def use_simplicity_style(ctx: PersonalizationContext) -> bool:
    is_micro = ctx.company_size is not None and ctx.company_size <= 5
    is_small_dm = (
        ctx.role in ("owner", "director", "ceo") and
        ctx.company_size is not None and
        ctx.company_size <= 20
    )
    return is_micro or is_small_dm


@personalization_condition(
    name="use_control_style",
    description="Control-стиль: боль = нет контроля или растущая команда",
    category="style"
)
def use_control_style(ctx: PersonalizationContext) -> bool:
    pain_control = ctx.pain_category == "no_control"
    growing_team = ctx.company_size is not None and 6 <= ctx.company_size <= 20
    return pain_control or growing_team


@personalization_condition(
    name="use_automation_style",
    description="Automation-стиль: боль = ручная работа",
    category="style"
)
def use_automation_style(ctx: PersonalizationContext) -> bool:
    return ctx.pain_category == "manual_work"


@personalization_condition(
    name="use_enterprise_style",
    description="Enterprise-стиль: крупная компания + техническая роль",
    category="style"
)
def use_enterprise_style(ctx: PersonalizationContext) -> bool:
    is_large = ctx.company_size is not None and ctx.company_size > 50
    is_tech = ctx.role in ("it", "admin", "developer", "cto")
    return is_large and is_tech


@personalization_condition(
    name="use_relationship_style",
    description="Relationship-стиль: breakthrough + high engagement",
    category="style"
)
def use_relationship_style(ctx: PersonalizationContext) -> bool:
    return ctx.has_breakthrough and ctx.engagement_level == "high"


@personalization_condition(
    name="use_quick_win_style",
    description="Quick-win стиль: начало разговора + мало данных",
    category="style"
)
def use_quick_win_style(ctx: PersonalizationContext) -> bool:
    early = ctx.turn_number <= 3
    no_pain = ctx.pain_point is None and ctx.pain_category is None
    return early and no_pain
```

---

## Часть 5: SHARED CONDITIONS

```python
# src/conditions/shared/__init__.py
"""
Общие условия, работающие с BaseContext.
Могут использоваться в любом домене через прямой импорт.
"""

from src.conditions.base import BaseContext


def has_company_size(ctx: BaseContext) -> bool:
    """Известен размер компании."""
    return bool(ctx.collected_data.get("company_size"))


def has_pain_point(ctx: BaseContext) -> bool:
    """Клиент озвучил проблему."""
    return bool(
        ctx.collected_data.get("pain_point") or
        ctx.collected_data.get("pain_category")
    )


def has_contact_info(ctx: BaseContext) -> bool:
    """Есть контактные данные."""
    return bool(
        ctx.collected_data.get("contact_info") or
        ctx.collected_data.get("phone") or
        ctx.collected_data.get("email")
    )


def early_conversation(ctx: BaseContext) -> bool:
    """Начало разговора (первые 3 хода)."""
    return ctx.turn_number <= 3


def late_conversation(ctx: BaseContext) -> bool:
    """Затянувшийся разговор (10+ ходов)."""
    return ctx.turn_number > 10


__all__ = [
    "has_company_size",
    "has_pain_point",
    "has_contact_info",
    "early_conversation",
    "late_conversation",
]
```

---

## Часть 6: АГРЕГАТОР И ЭКСПОРТ

```python
# src/conditions/__init__.py
"""
Условия разделены по доменам:
- state_machine: условия для StateMachine (rules/transitions)
- policy: условия для DialoguePolicy
- fallback: условия для FallbackHandler
- personalization: условия для PersonalizationEngine

Каждый домен имеет свой реестр и свой тип контекста.
Это обеспечивает:
- Type safety (mypy проверяет совместимость)
- Изоляцию (условия не смешиваются)
- Open-Closed (новый домен = новый реестр)
"""

# Base
from src.conditions.base import BaseContext
from src.conditions.registry import (
    ConditionRegistry,
    ConditionMetadata,
    ConditionNotFoundError,
    ConditionEvaluationError,
)
from src.conditions.trace import EvaluationTrace, TraceCollector

# StateMachine domain
from src.conditions.state_machine.registry import sm_registry, sm_condition
from src.conditions.state_machine.context import EvaluatorContext, create_sm_test_context

# Policy domain
from src.conditions.policy.registry import policy_registry, policy_condition
from src.conditions.policy.context import PolicyContext, create_policy_test_context

# Fallback domain
from src.conditions.fallback.registry import fallback_registry, fallback_condition
from src.conditions.fallback.context import FallbackContext, create_fallback_test_context

# Personalization domain
from src.conditions.personalization.registry import (
    personalization_registry,
    personalization_condition
)
from src.conditions.personalization.context import (
    PersonalizationContext,
    create_personalization_test_context
)

# Shared conditions
from src.conditions import shared

# Import conditions to register them
from src.conditions.state_machine import conditions as _sm_conditions
from src.conditions.policy import conditions as _policy_conditions
from src.conditions.fallback import conditions as _fallback_conditions
from src.conditions.personalization import conditions as _personalization_conditions


class ConditionRegistries:
    """
    Агрегатор всех реестров.

    Используется для:
    - Валидации всех условий
    - Генерации документации
    - Статистики
    """

    state_machine = sm_registry
    policy = policy_registry
    fallback = fallback_registry
    personalization = personalization_registry

    @classmethod
    def all_registries(cls):
        """Список всех реестров."""
        return [
            cls.state_machine,
            cls.policy,
            cls.fallback,
            cls.personalization,
        ]

    @classmethod
    def get_registry(cls, name: str):
        """Получить реестр по имени."""
        mapping = {
            "state_machine": cls.state_machine,
            "policy": cls.policy,
            "fallback": cls.fallback,
            "personalization": cls.personalization,
        }
        return mapping.get(name)

    @classmethod
    def validate_all(cls) -> dict:
        """Валидация всех реестров."""
        from src.conditions.state_machine.context import create_sm_test_context
        from src.conditions.policy.context import create_policy_test_context
        from src.conditions.fallback.context import create_fallback_test_context
        from src.conditions.personalization.context import create_personalization_test_context

        factories = {
            "state_machine": create_sm_test_context,
            "policy": create_policy_test_context,
            "fallback": create_fallback_test_context,
            "personalization": create_personalization_test_context,
        }

        results = {}
        for registry in cls.all_registries():
            factory = factories.get(registry.name)
            if factory:
                results[registry.name] = registry.validate_all(factory)
            else:
                results[registry.name] = {"error": "No test context factory"}

        return results

    @classmethod
    def get_stats(cls) -> dict:
        """Статистика по всем реестрам."""
        stats = {}
        for registry in cls.all_registries():
            stats[registry.name] = {
                "total": len(registry.list_all()),
                "categories": {
                    cat: len(registry.list_by_category(cat))
                    for cat in registry.get_categories()
                }
            }
        return stats

    @classmethod
    def generate_documentation(cls) -> str:
        """Генерация документации по всем условиям."""
        lines = ["# All Conditions\n"]

        for registry in cls.all_registries():
            lines.append(f"\n## {registry.name.replace('_', ' ').title()}\n")
            lines.append(f"Context: `{registry.context_type.__name__}`\n")
            lines.append(f"Total conditions: {len(registry.list_all())}\n")

            for category in sorted(registry.get_categories()):
                lines.append(f"\n### {category.title()}\n")
                for name in sorted(registry.list_by_category(category)):
                    meta = registry.get(name)
                    lines.append(f"- **`{name}`**: {meta.description}")

        return "\n".join(lines)


__all__ = [
    # Base
    "BaseContext",
    "ConditionRegistry",
    "ConditionMetadata",
    "ConditionNotFoundError",
    "ConditionEvaluationError",
    "EvaluationTrace",
    "TraceCollector",

    # StateMachine
    "sm_registry",
    "sm_condition",
    "EvaluatorContext",
    "create_sm_test_context",

    # Policy
    "policy_registry",
    "policy_condition",
    "PolicyContext",
    "create_policy_test_context",

    # Fallback
    "fallback_registry",
    "fallback_condition",
    "FallbackContext",
    "create_fallback_test_context",

    # Personalization
    "personalization_registry",
    "personalization_condition",
    "PersonalizationContext",
    "create_personalization_test_context",

    # Shared
    "shared",

    # Aggregator
    "ConditionRegistries",
]
```

---

## Часть 7: INTENT TRACKER

```python
# src/intent_tracker.py

from dataclasses import dataclass
from typing import List, Dict, Optional, Any
import time

from src.config import INTENT_CATEGORIES


@dataclass
class IntentRecord:
    """Запись об одном интенте."""
    intent: str
    state: str
    timestamp: float
    category: Optional[str] = None


class IntentTracker:
    """
    Единый источник истории интентов.

    Заменяет:
    - StateMachine.last_intent
    - Bot.last_intent
    - ObjectionFlowManager (весь класс)

    ВАЖНО: Контракт timing'а
    ========================
    record() вызывается В НАЧАЛЕ apply_rules(), ДО проверки условий.
    Все методы возвращают значения ВКЛЮЧАЯ текущий записанный интент.
    """

    MAX_HISTORY = 50

    def __init__(self):
        self.history: List[IntentRecord] = []
        self._streak_count: int = 0
        self._last_intent: Optional[str] = None

    def record(self, intent: str, state: str) -> None:
        """
        Записать интент.

        Вызывать В НАЧАЛЕ apply_rules().
        После вызова streak_count() будет включать этот интент.
        """
        category = self._get_category(intent)

        # Update streak
        if intent == self._last_intent:
            self._streak_count += 1
        else:
            self._streak_count = 1

        record = IntentRecord(
            intent=intent,
            state=state,
            timestamp=time.time(),
            category=category
        )

        self.history.append(record)
        if len(self.history) > self.MAX_HISTORY:
            self.history.pop(0)

        self._last_intent = intent

    def _get_category(self, intent: str) -> Optional[str]:
        """Определить категорию интента."""
        for category, intents in INTENT_CATEGORIES.items():
            if intent in intents:
                return category
        return None

    # ═══════════════════════════════════════════════════════════════════
    # ЧТЕНИЕ — базовые свойства
    # ═══════════════════════════════════════════════════════════════════

    @property
    def last_intent(self) -> Optional[str]:
        """Последний интент."""
        return self._last_intent

    @property
    def prev_intent(self) -> Optional[str]:
        """Интент до текущего."""
        if len(self.history) >= 2:
            return self.history[-2].intent
        return None

    @property
    def last_record(self) -> Optional[IntentRecord]:
        """Полная запись о последнем интенте."""
        return self.history[-1] if self.history else None

    # ═══════════════════════════════════════════════════════════════════
    # ЧТЕНИЕ — streak
    # ═══════════════════════════════════════════════════════════════════

    def streak_count(self, intent: str) -> int:
        """Сколько раз этот интент идёт подряд (включая текущий)."""
        if intent == self._last_intent:
            return self._streak_count
        return 0

    def count_in_window(self, intent: str, window: int = 5) -> int:
        """Сколько раз интент встречался в последних N ходах."""
        recent = self.history[-window:] if window else self.history
        return sum(1 for r in recent if r.intent == intent)

    # ═══════════════════════════════════════════════════════════════════
    # ЧТЕНИЕ — objection (заменяет ObjectionFlowManager)
    # ═══════════════════════════════════════════════════════════════════

    def objection_consecutive(self) -> int:
        """Сколько возражений подряд."""
        count = 0
        for record in reversed(self.history):
            if record.category == "objection":
                count += 1
            else:
                break
        return count

    def objection_total(self) -> int:
        """Всего возражений за диалог."""
        return sum(1 for r in self.history if r.category == "objection")

    def objection_in_window(self, window: int = 5) -> int:
        """Возражений в последних N ходах."""
        recent = self.history[-window:] if window else self.history
        return sum(1 for r in recent if r.category == "objection")

    # ═══════════════════════════════════════════════════════════════════
    # ЧТЕНИЕ — категории
    # ═══════════════════════════════════════════════════════════════════

    def category_consecutive(self, category: str) -> int:
        """Сколько интентов данной категории подряд."""
        count = 0
        for record in reversed(self.history):
            if record.category == category:
                count += 1
            else:
                break
        return count

    def positive_consecutive(self) -> int:
        """Сколько положительных интентов подряд."""
        return self.category_consecutive("positive")

    # ═══════════════════════════════════════════════════════════════════
    # СЕРИАЛИЗАЦИЯ
    # ═══════════════════════════════════════════════════════════════════

    def to_dict(self) -> Dict[str, Any]:
        """Сериализация."""
        return {
            "last_intent": self._last_intent,
            "prev_intent": self.prev_intent,
            "current_streak": self._streak_count,
            "objection_consecutive": self.objection_consecutive(),
            "objection_total": self.objection_total(),
            "turn_number": len(self.history),
            "recent_intents": [r.intent for r in self.history[-5:]]
        }

    def reset(self) -> None:
        """Сброс для нового диалога."""
        self.history.clear()
        self._streak_count = 0
        self._last_intent = None
```

---

## Часть 8: RULE RESOLVER

```python
# src/rules/resolver.py

from typing import Optional, Union, Tuple, List
from dataclasses import dataclass

from src.conditions import sm_registry, EvaluatorContext
from src.conditions.trace import EvaluationTrace


RuleValue = Union[
    str,
    Tuple[str, str],
    List[Union[Tuple[str, str], str, None]]
]


@dataclass
class RuleResult:
    """
    Результат разрешения правила.

    Поддерживает tuple unpacking:
        action, state = resolver.resolve(...)
    """
    action: str
    next_state: Optional[str]
    trace: Optional[EvaluationTrace] = None

    def __iter__(self):
        return iter((self.action, self.next_state))


class RuleResolver:
    """
    Разрешает правила для StateMachine.

    Использует sm_registry для вычисления условий.
    """

    def __init__(self, config: dict = None):
        from src.config import SALES_CONFIG
        self.config = config or SALES_CONFIG
        self.registry = sm_registry

    def resolve_action(
        self,
        intent: str,
        state: str,
        ctx: EvaluatorContext,
        trace: Optional[EvaluationTrace] = None
    ) -> str:
        """
        Разрешить action для интента.

        Порядок:
        1. state.rules[intent]
        2. global_rules[intent]
        3. "continue_current_goal"
        """
        state_config = self.config.get("states", {}).get(state, {})

        # 1. State rules
        rule = state_config.get("rules", {}).get(intent)
        if rule is not None:
            return self._evaluate_rule(rule, ctx, trace)

        # 2. Global rules
        global_rule = self.config.get("global_rules", {}).get(intent)
        if global_rule is not None:
            return self._evaluate_rule(global_rule, ctx, trace)

        # 3. Fallback
        if trace:
            trace.set_result("continue_current_goal", "fallback")
        return "continue_current_goal"

    def resolve_transition(
        self,
        intent: str,
        state: str,
        ctx: EvaluatorContext,
        trace: Optional[EvaluationTrace] = None
    ) -> Optional[str]:
        """Разрешить transition для интента."""
        state_config = self.config.get("states", {}).get(state, {})

        rule = state_config.get("transitions", {}).get(intent)
        if rule is not None:
            result = self._evaluate_rule(rule, ctx, trace, allow_none=True)
            return result if result else None

        return None

    def _evaluate_rule(
        self,
        rule: RuleValue,
        ctx: EvaluatorContext,
        trace: Optional[EvaluationTrace] = None,
        allow_none: bool = False
    ) -> Union[str, None]:
        """Вычислить правило."""
        # Простое правило
        if isinstance(rule, str):
            if trace:
                trace.set_result(rule, "simple")
            return rule

        if rule is None:
            if trace:
                trace.set_result(None, "explicit_none")
            return None

        # Одно условие
        if isinstance(rule, tuple) and len(rule) == 2:
            condition_name, action = rule
            result = self.registry.evaluate(condition_name, ctx, trace)

            if result:
                if trace:
                    trace.set_result(action, "condition_matched", condition_name)
                return action
            else:
                if allow_none:
                    if trace:
                        trace.set_result(None, "condition_not_matched")
                    return None
                raise ValueError(f"Condition '{condition_name}' not matched, no default")

        # Список условий
        if isinstance(rule, list):
            default_action = None

            for item in rule:
                if isinstance(item, str):
                    default_action = item
                    continue
                if item is None:
                    default_action = None
                    continue

                if isinstance(item, tuple) and len(item) == 2:
                    condition_name, action = item
                    result = self.registry.evaluate(condition_name, ctx, trace)

                    if result:
                        if trace:
                            trace.set_result(action, "condition_matched", condition_name)
                        return action

            if trace:
                trace.set_result(default_action, "default")
            return default_action

        raise ValueError(f"Invalid rule format: {rule}")

    def validate_config(self) -> dict:
        """Валидация конфигурации."""
        errors = []
        warnings = []

        all_conditions = set(self.registry.list_all())
        all_states = set(self.config.get("states", {}).keys())

        for state_name, state_config in self.config.get("states", {}).items():
            # Rules
            for intent, rule in state_config.get("rules", {}).items():
                for cond in self._extract_conditions(rule):
                    if cond not in all_conditions:
                        errors.append(
                            f"State '{state_name}', rule '{intent}': "
                            f"unknown condition '{cond}'"
                        )

            # Transitions
            for intent, rule in state_config.get("transitions", {}).items():
                for cond in self._extract_conditions(rule):
                    if cond not in all_conditions:
                        errors.append(
                            f"State '{state_name}', transition '{intent}': "
                            f"unknown condition '{cond}'"
                        )

                for target in self._extract_targets(rule):
                    if target and target not in all_states:
                        errors.append(
                            f"State '{state_name}', transition '{intent}': "
                            f"unknown target '{target}'"
                        )

        # Global rules
        for intent, rule in self.config.get("global_rules", {}).items():
            for cond in self._extract_conditions(rule):
                if cond not in all_conditions:
                    errors.append(f"Global rule '{intent}': unknown condition '{cond}'")

        return {"valid": len(errors) == 0, "errors": errors, "warnings": warnings}

    def _extract_conditions(self, rule: RuleValue) -> List[str]:
        if isinstance(rule, str) or rule is None:
            return []
        if isinstance(rule, tuple):
            return [rule[0]]
        if isinstance(rule, list):
            return [item[0] for item in rule if isinstance(item, tuple)]
        return []

    def _extract_targets(self, rule: RuleValue) -> List[Optional[str]]:
        if isinstance(rule, str):
            return [rule]
        if rule is None:
            return [None]
        if isinstance(rule, tuple):
            return [rule[1]]
        if isinstance(rule, list):
            targets = []
            for item in rule:
                if isinstance(item, str):
                    targets.append(item)
                elif isinstance(item, tuple):
                    targets.append(item[1])
                elif item is None:
                    targets.append(None)
            return targets
        return []
```

---

## Часть 9: STATE MACHINE

```python
# src/state_machine.py

from typing import Optional

from src.conditions import sm_registry, EvaluatorContext
from src.conditions.trace import EvaluationTrace, TraceCollector
from src.rules.resolver import RuleResolver, RuleResult
from src.intent_tracker import IntentTracker
from src.config import SALES_CONFIG


class StateMachine:
    """
    State Machine с гибридной архитектурой:
    - Условия: Python-функции в sm_registry
    - Правила: декларативная конфигурация
    """

    def __init__(
        self,
        config: dict = None,
        trace_collector: Optional[TraceCollector] = None
    ):
        self.config = config or SALES_CONFIG
        self.state = "spin_situation"
        self.collected_data = {}
        self.intent_tracker = IntentTracker()
        self.rule_resolver = RuleResolver(self.config)
        self.trace_collector = trace_collector

    @property
    def spin_phase(self) -> Optional[str]:
        state_config = self.config.get("states", {}).get(self.state, {})
        return state_config.get("spin_phase")

    def apply_rules(self, intent: str) -> RuleResult:
        """
        Применить правила для интента.

        Returns:
            RuleResult с action, next_state и трассировкой.
        """
        # 1. Record intent
        self.intent_tracker.record(intent, self.state)

        # 2. Create context
        ctx = EvaluatorContext.from_state_machine(self, intent)

        # 3. Create trace
        trace = None
        if self.trace_collector:
            trace = self.trace_collector.create_trace(
                rule_name=f"{self.state}.{intent}",
                intent=intent,
                state=self.state,
                domain="state_machine"
            )

        # 4. Early exits
        early_exit = self._check_early_exits(intent)
        if early_exit:
            return early_exit

        # 5. Resolve action
        action = self.rule_resolver.resolve_action(
            intent=intent,
            state=self.state,
            ctx=ctx,
            trace=trace
        )

        # 6. Resolve transition
        next_state = self.rule_resolver.resolve_transition(
            intent=intent,
            state=self.state,
            ctx=ctx,
            trace=trace
        )

        # 7. Fallback transitions
        if next_state is None:
            next_state = self._fallback_transition(intent, ctx)

        # 8. Apply transition
        if next_state and next_state != self.state:
            self.state = next_state

        return RuleResult(
            action=action,
            next_state=self.state,
            trace=trace
        )

    def _check_early_exits(self, intent: str) -> Optional[RuleResult]:
        state_config = self.config.get("states", {}).get(self.state, {})
        if state_config.get("is_final"):
            return RuleResult(action="stay", next_state=self.state)
        return None

    def _fallback_transition(self, intent: str, ctx: EvaluatorContext) -> Optional[str]:
        state_config = self.config.get("states", {}).get(self.state, {})
        transitions = state_config.get("transitions", {})

        if "data_complete" in transitions:
            if sm_registry.evaluate("data_complete", ctx):
                target = transitions["data_complete"]
                if isinstance(target, str):
                    return target

        return None

    def update_data(self, data: dict):
        self.collected_data.update(data)

    def reset(self):
        self.state = "spin_situation"
        self.collected_data = {}
        self.intent_tracker.reset()

    def get_state_info(self) -> dict:
        state_config = self.config.get("states", {}).get(self.state, {})
        return {
            "state": self.state,
            "goal": state_config.get("goal", ""),
            "spin_phase": state_config.get("spin_phase"),
            "is_final": state_config.get("is_final", False),
            "intent_tracker": self.intent_tracker.to_dict(),
        }
```

---

## Часть 10: КОНФИГУРАЦИЯ

```python
# src/config.py

from typing import Dict, List, Tuple, Union

RuleValue = Union[
    str,
    Tuple[str, str],
    List[Union[Tuple[str, str], str, None]]
]

# ═══════════════════════════════════════════════════════════════════════════
# INTENT_CATEGORIES
# ═══════════════════════════════════════════════════════════════════════════

INTENT_CATEGORIES = {
    "objection": [
        "objection_price", "objection_competitor",
        "objection_no_time", "objection_think", "objection_not_interested"
    ],
    "positive": [
        "agreement", "demo_request", "callback_request", "contact_provided",
        "consultation_request", "situation_provided", "problem_revealed",
        "implication_acknowledged", "need_expressed", "info_provided",
        "question_features", "question_integrations", "comparison",
        "greeting", "gratitude"
    ],
    "go_back": ["go_back", "correct_info"],
    "question": ["question_features", "question_integrations", "question_technical"]
}


# ═══════════════════════════════════════════════════════════════════════════
# SHARED RULES
# ═══════════════════════════════════════════════════════════════════════════

SPIN_COMMON_RULES: Dict[str, RuleValue] = {
    "price_question": [
        ("has_pricing_data", "answer_with_facts"),
        ("price_repeated_3x", "answer_with_range"),
        "deflect_and_continue"
    ],
    "pricing_details": [
        ("has_pricing_data", "answer_with_facts"),
        "deflect_and_continue"
    ],
    "comparison": [
        ("has_competitor_mention", "compare_with_known_competitor"),
        "answer_and_continue"
    ],
    "objection_price": [
        ("can_handle_objection_with_roi", "handle_objection_with_roi"),
        "handle_objection"
    ],
    "question_features": "answer_question",
    "question_integrations": "answer_question",
}

POST_SPIN_RULES: Dict[str, RuleValue] = {
    "price_question": "answer_with_facts",
    "pricing_details": "answer_with_facts",
    "objection_price": [
        ("objection_limit_reached", "soft_close_offer"),
        ("can_handle_objection_with_roi", "handle_objection_with_roi"),
        "handle_objection"
    ],
    "objection_competitor": [
        ("has_competitor_mention", "compare_with_known_competitor"),
        "handle_objection"
    ],
}


# ═══════════════════════════════════════════════════════════════════════════
# SALES_CONFIG
# ═══════════════════════════════════════════════════════════════════════════

SALES_CONFIG = {
    "global_rules": {
        "greeting": "acknowledge_and_continue",
        "gratitude": "acknowledge_and_continue",
        "small_talk": "small_talk_and_continue",
        "question_features": "answer_question",
        "question_integrations": "answer_question",
        "question_technical": [
            ("question_repeated_2x", "offer_documentation"),
            "answer_question"
        ],
        "farewell": "farewell_response",
    },

    "states": {
        "spin_situation": {
            "goal": "Понять ситуацию клиента",
            "spin_phase": "situation",
            "required_data": ["company_size", "industry"],
            "rules": {
                **SPIN_COMMON_RULES,
                "unclear": "probe_situation",
                "info_provided": "acknowledge_and_probe",
            },
            "transitions": {
                "situation_provided": "spin_problem",
                "data_complete": "spin_problem",
            }
        },

        "spin_problem": {
            "goal": "Выявить проблемы клиента",
            "spin_phase": "problem",
            "required_data": ["pain_point"],
            "rules": {
                **SPIN_COMMON_RULES,
                "unclear": "probe_problem",
            },
            "transitions": {
                "problem_revealed": "spin_implication",
                "data_complete": "spin_implication",
            }
        },

        "spin_implication": {
            "goal": "Показать последствия проблем",
            "spin_phase": "implication",
            "rules": {
                **SPIN_COMMON_RULES,
                "unclear": "probe_implication",
            },
            "transitions": {
                "implication_acknowledged": "spin_need_payoff",
            }
        },

        "spin_need_payoff": {
            "goal": "Сформировать потребность в решении",
            "spin_phase": "need_payoff",
            "rules": {
                **SPIN_COMMON_RULES,
                "unclear": "probe_need_payoff",
            },
            "transitions": {
                "need_expressed": "presentation",
                "demo_request": "presentation",
                "agreement": "presentation",
            }
        },

        "presentation": {
            "goal": "Презентовать решение",
            "rules": {
                **POST_SPIN_RULES,
                "demo_request": "schedule_demo",
                "agreement": "propose_next_step",
            },
            "transitions": {
                "agreement": "close",
                "demo_request": [
                    ("has_contact", "success"),
                    "close"
                ],
            }
        },

        "close": {
            "goal": "Взять контакт или назначить демо",
            "rules": {
                **POST_SPIN_RULES,
                "demo_request": [
                    ("has_contact", "confirm_demo"),
                    "ask_for_contact"
                ],
                "rejection": [
                    ("objection_limit_reached", "soft_close_offer"),
                    "handle_soft_rejection"
                ],
            },
            "transitions": {
                "contact_provided": "success",
                "demo_request": [
                    ("has_contact", "success"),
                    None
                ],
                "rejection": [
                    ("objection_limit_reached", "soft_close"),
                    None
                ],
            }
        },

        "soft_close": {
            "goal": "Мягкое завершение",
            "rules": {
                "agreement": "reopen_conversation",
                "demo_request": "reopen_conversation",
                "rejection": "farewell",
                "contact_provided": "thank_and_confirm",
            },
            "transitions": {
                "agreement": "close",
                "demo_request": "close",
                "contact_provided": "success",
                "rejection": "failed",
            }
        },

        "success": {
            "goal": "Успешное завершение",
            "is_final": True,
            "rules": {},
            "transitions": {}
        },

        "failed": {
            "goal": "Неуспешное завершение",
            "is_final": True,
            "rules": {},
            "transitions": {}
        },
    }
}
```

---

## Часть 11: СТРУКТУРА ФАЙЛОВ

```
src/
├── conditions/
│   ├── __init__.py                 # Агрегатор и экспорт
│   ├── base.py                     # BaseContext Protocol
│   ├── registry.py                 # Generic ConditionRegistry
│   ├── trace.py                    # EvaluationTrace, TraceCollector
│   │
│   ├── shared/                     # Переиспользуемые условия
│   │   └── __init__.py
│   │
│   ├── state_machine/              # StateMachine домен
│   │   ├── __init__.py
│   │   ├── context.py              # EvaluatorContext
│   │   ├── registry.py             # sm_registry, sm_condition
│   │   └── conditions.py           # ~20 условий
│   │
│   ├── policy/                     # DialoguePolicy домен
│   │   ├── __init__.py
│   │   ├── context.py              # PolicyContext
│   │   ├── registry.py             # policy_registry
│   │   └── conditions.py           # ~15 условий
│   │
│   ├── fallback/                   # FallbackHandler домен
│   │   ├── __init__.py
│   │   ├── context.py              # FallbackContext
│   │   ├── registry.py             # fallback_registry
│   │   └── conditions.py           # ~12 условий
│   │
│   └── personalization/            # PersonalizationEngine домен
│       ├── __init__.py
│       ├── context.py              # PersonalizationContext
│       ├── registry.py             # personalization_registry
│       └── conditions.py           # ~20 условий
│
├── rules/
│   ├── __init__.py
│   └── resolver.py                 # RuleResolver, RuleResult
│
├── intent_tracker.py               # IntentTracker
├── state_machine.py                # StateMachine
└── config.py                       # SALES_CONFIG
```

---

## Часть 12: ПЛАН РЕАЛИЗАЦИИ

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  ЭТАП 1: Foundation — Base и Registry                                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  1.1 Создать src/conditions/:                                               │
│      - base.py (BaseContext Protocol)                                       │
│      - registry.py (Generic ConditionRegistry)                              │
│      - trace.py (EvaluationTrace, TraceCollector)                           │
│                                                                             │
│  1.2 Написать unit-тесты для ConditionRegistry                              │
│                                                                             │
│  Результат: Базовая инфраструктура готова                                   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  ЭТАП 2: StateMachine домен                                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  2.1 Создать src/conditions/state_machine/:                                 │
│      - context.py (EvaluatorContext)                                        │
│      - registry.py (sm_registry, sm_condition)                              │
│      - conditions.py (~20 условий)                                          │
│                                                                             │
│  2.2 Написать тесты для всех условий                                        │
│                                                                             │
│  Результат: SM условия готовы                                               │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  ЭТАП 3: IntentTracker и RuleResolver                                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  3.1 Создать src/intent_tracker.py                                          │
│  3.2 Создать src/rules/resolver.py                                          │
│  3.3 Обновить src/config.py (SALES_CONFIG)                                  │
│  3.4 Написать тесты                                                         │
│                                                                             │
│  Результат: Resolver работает с условиями                                   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  ЭТАП 4: Интеграция StateMachine                                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  4.1 Рефакторинг src/state_machine.py                                       │
│  4.2 Удалить дублирование (last_intent, ObjectionFlowManager)               │
│  4.3 Обновить Bot.py                                                        │
│  4.4 Интеграционные тесты                                                   │
│                                                                             │
│  Результат: SM работает на новой архитектуре                                │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  ЭТАП 5: Policy домен                                                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  5.1 Создать src/conditions/policy/                                         │
│  5.2 Рефакторинг DialoguePolicy                                             │
│  5.3 Тесты                                                                  │
│                                                                             │
│  Результат: DialoguePolicy на условиях                                      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  ЭТАП 6: Fallback домен                                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  6.1 Создать src/conditions/fallback/                                       │
│  6.2 Рефакторинг FallbackHandler                                            │
│  6.3 Тесты                                                                  │
│                                                                             │
│  Результат: FallbackHandler на условиях                                     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  ЭТАП 7: Personalization домен                                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  7.1 Создать src/conditions/personalization/                                │
│  7.2 Рефакторинг PersonalizationEngine                                      │
│  7.3 Тесты                                                                  │
│                                                                             │
│  Результат: PersonalizationEngine на условиях                               │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  ЭТАП 8: Tooling и CI                                                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  8.1 scripts/validate_conditions.py                                         │
│  8.2 scripts/generate_docs.py                                               │
│  8.3 CI pipeline                                                            │
│  8.4 Симуляции с трассировкой                                               │
│                                                                             │
│  Результат: Полный tooling                                                  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Часть 13: РЕЗЮМЕ

### Решённые проблемы

| # | Проблема | Решение |
|---|----------|---------|
| 1 | JSON DSL без типов | Python-функции с @condition |
| 2 | Единый evaluator для всех контекстов (SRP) | Доменные реестры |
| 3 | Open-Closed нарушен | Новый домен = новый реестр |
| 4 | Type safety отсутствует | Generic[TContext], mypy |
| 5 | Условия смешиваются | Изоляция по доменам |
| 6 | Hardcoded OBJECTION_INTENTS | INTENT_CATEGORIES |
| 7 | last_intent в 4+ местах | IntentTracker |
| 8 | ObjectionFlowManager | IntentTracker.objection_*() |
| 9 | Runtime ошибки | Валидация на старте |
| 10 | Сложно дебажить | Breakpoints, stack traces |

### Сравнение подходов

| Аспект | Один ConditionEvaluator | Доменные реестры |
|--------|-------------------------|------------------|
| **SRP** | Нарушен | Соблюдён |
| **Type Safety** | Runtime ошибки | Compile-time (mypy) |
| **Open-Closed** | Изменять evaluator | Добавить новый домен |
| **Изоляция** | Всё смешано | По доменам |
| **IDE Support** | Слабый | Полный |
| **Тестирование** | Сложно | Просто |

### Итоговая архитектура

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         ИТОГОВАЯ АРХИТЕКТУРА                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐│
│  │ StateMachine  │  │DialoguePolicy │  │FallbackHandler│  │Personalization││
│  │    Domain     │  │    Domain     │  │    Domain     │  │    Domain     ││
│  ├───────────────┤  ├───────────────┤  ├───────────────┤  ├───────────────┤│
│  │EvaluatorCtx   │  │ PolicyCtx     │  │ FallbackCtx   │  │PersonalizCtx  ││
│  │ sm_registry   │  │policy_registry│  │fallback_reg   │  │personal_reg   ││
│  │ ~20 conditions│  │~15 conditions │  │~12 conditions │  │~20 conditions ││
│  └───────────────┘  └───────────────┘  └───────────────┘  └───────────────┘│
│         │                  │                  │                  │         │
│         └──────────────────┴──────────────────┴──────────────────┘         │
│                                    │                                        │
│                                    ▼                                        │
│                         ┌─────────────────────┐                             │
│                         │    BaseContext      │                             │
│                         │     (Protocol)      │                             │
│                         │  shared conditions  │                             │
│                         └─────────────────────┘                             │
│                                    │                                        │
│                                    ▼                                        │
│                    ┌───────────────────────────────┐                        │
│                    │    ConditionRegistry<T>       │                        │
│                    │    (Generic, Type-safe)       │                        │
│                    └───────────────────────────────┘                        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```
