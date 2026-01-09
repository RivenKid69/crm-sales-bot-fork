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
│           Python Conditions + Declarative Rules                              │
└─────────────────────────────────────────────────────────────────────────────┘

   conditions/*.py (Python)              config.py (Declarative)
   ┌──────────────────────────┐         ┌─────────────────────────────────┐
   │                          │         │                                 │
   │  @condition              │         │  "price_question": [            │
   │  def has_pricing_data    │◄────────│    ("has_pricing_data",         │
   │      return bool(...)    │   ref   │     "answer_with_facts"),       │
   │                          │         │    ("price_repeated_3x",        │
   │  @condition              │◄────────│     "answer_with_range"),       │
   │  def price_repeated_3x   │         │    "deflect_and_continue"       │
   │      return streak >= 3  │         │  ]                              │
   │                          │         │                                 │
   └──────────────────────────┘         └─────────────────────────────────┘
            │                                          │
            │                                          │
            ▼                                          ▼
   ┌──────────────────────────┐         ┌─────────────────────────────────┐
   │   ConditionRegistry      │         │      RuleResolver               │
   │   - evaluate(name, ctx)  │◄────────│      - resolve_action()         │
   │   - validate_all()       │         │      - resolve_transition()     │
   │   - get_documentation()  │         │      - validate_config()        │
   └──────────────────────────┘         └─────────────────────────────────┘
            │                                          │
            └──────────────┬───────────────────────────┘
                           │
                           ▼
                  ┌─────────────────────┐
                  │   StateMachine      │
                  │   apply_rules()     │
                  └─────────────────────┘
```

### 2.2 Философия: Разделение ответственности

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  ПРИНЦИП: Условия — это ЛОГИКА, Правила — это МАППИНГ                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  CONDITIONS (Python-функции)           RULES (Declarative config)           │
│  ─────────────────────────────         ──────────────────────────────────   │
│  • Типизация (mypy)                    • Читаемость                         │
│  • IDE autocomplete                    • Единый источник правды             │
│  • Breakpoints, debugging              • Легко изменить маппинг             │
│  • Stack traces при ошибках            • Не требует знания Python           │
│  • Unit-тесты изолированно             • Валидация на старте                │
│                                                                             │
│  ─────────────────────────────         ──────────────────────────────────   │
│  КАК проверять                         ЧТО делать если условие true         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.3 Принципы архитектуры

| Принцип | Описание |
|---------|----------|
| **Условия = Python** | Вся логика проверок — типизированные функции |
| **Правила = Декларативно** | Маппинг условие→действие в config.py |
| **Строгое разделение** | rules → action, transitions → state |
| **Единый источник правды** | Хочешь узнать поведение — смотри config |
| **Обратная совместимость** | Старые правила-строки продолжают работать |
| **Тестируемость** | Условия тестируются изолированно (pytest) |
| **Отказоустойчивость** | Валидация в CI, fallback + метрики в runtime |
| **IDE Support** | Autocomplete, go-to-definition, типы |

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

### 3.2 Условия как Python-функции

#### 3.2.1 Декоратор @condition

```python
# src/conditions/registry.py

from typing import Callable, Dict, Any, Optional, List, Set
from dataclasses import dataclass, field
from functools import wraps
import inspect


@dataclass
class ConditionMetadata:
    """Метаданные условия для документации и валидации."""
    name: str
    description: str
    func: Callable[["EvaluatorContext"], bool]
    requires_fields: Set[str] = field(default_factory=set)
    category: str = "general"
    examples: List[str] = field(default_factory=list)


class ConditionRegistry:
    """
    Реестр всех условий.

    Преимущества:
    - Единая точка регистрации
    - Валидация на старте приложения
    - Автодокументация
    - Интроспекция для тестов
    """

    _instance: Optional["ConditionRegistry"] = None

    def __init__(self):
        self._conditions: Dict[str, ConditionMetadata] = {}
        self._categories: Dict[str, List[str]] = {}

    @classmethod
    def get_instance(cls) -> "ConditionRegistry":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register(
        self,
        name: str,
        description: str = "",
        requires_fields: Set[str] = None,
        category: str = "general",
        examples: List[str] = None
    ) -> Callable:
        """
        Декоратор для регистрации условия.

        Использование:
            @condition("has_pricing_data",
                      description="Есть данные для расчёта цены",
                      requires_fields={"company_size", "users_count"},
                      category="data")
            def has_pricing_data(ctx: EvaluatorContext) -> bool:
                return bool(ctx.collected_data.get("company_size"))
        """
        def decorator(func: Callable[["EvaluatorContext"], bool]) -> Callable:
            # Валидация сигнатуры
            sig = inspect.signature(func)
            params = list(sig.parameters.keys())
            if len(params) != 1:
                raise ValueError(
                    f"Condition '{name}' must accept exactly one parameter (ctx)"
                )

            metadata = ConditionMetadata(
                name=name,
                description=description or func.__doc__ or "",
                func=func,
                requires_fields=requires_fields or set(),
                category=category,
                examples=examples or []
            )

            if name in self._conditions:
                raise ValueError(f"Condition '{name}' already registered")

            self._conditions[name] = metadata

            if category not in self._categories:
                self._categories[category] = []
            self._categories[category].append(name)

            @wraps(func)
            def wrapper(ctx: "EvaluatorContext") -> bool:
                return func(ctx)

            wrapper._condition_name = name
            wrapper._condition_metadata = metadata
            return wrapper

        return decorator

    def evaluate(
        self,
        name: str,
        ctx: "EvaluatorContext",
        trace: Optional["EvaluationTrace"] = None
    ) -> bool:
        """Вычислить условие с опциональной трассировкой."""
        metadata = self._conditions.get(name)
        if metadata is None:
            raise ConditionNotFoundError(f"Condition '{name}' not found")

        try:
            result = metadata.func(ctx)

            if trace:
                trace.record(name, result, ctx, metadata.requires_fields)

            return result

        except Exception as e:
            raise ConditionEvaluationError(
                f"Error evaluating condition '{name}': {e}"
            ) from e

    def get(self, name: str) -> Optional[ConditionMetadata]:
        return self._conditions.get(name)

    def list_all(self) -> List[str]:
        return list(self._conditions.keys())

    def list_by_category(self, category: str) -> List[str]:
        return self._categories.get(category, [])

    def get_documentation(self) -> str:
        """Автогенерация документации из docstrings."""
        lines = ["# Available Conditions\n"]

        for category in sorted(self._categories.keys()):
            lines.append(f"\n## {category.title()}\n")
            for name in sorted(self._categories[category]):
                meta = self._conditions[name]
                lines.append(f"### `{name}`")
                lines.append(f"{meta.description}\n")
                if meta.requires_fields:
                    lines.append(f"**Requires:** {', '.join(meta.requires_fields)}\n")

        return "\n".join(lines)

    def validate_all(self, ctx_factory: Callable) -> Dict[str, Any]:
        """Валидация всех условий (для CI)."""
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


# Глобальный реестр
registry = ConditionRegistry.get_instance()


# Удобный алиас
def condition(
    name: str,
    description: str = "",
    requires_fields: Set[str] = None,
    category: str = "general",
    examples: List[str] = None
) -> Callable:
    """Декоратор для регистрации условия."""
    return registry.register(name, description, requires_fields, category, examples)


class ConditionNotFoundError(Exception):
    """Условие не найдено в реестре."""
    pass


class ConditionEvaluationError(Exception):
    """Ошибка при вычислении условия."""
    pass
```

#### 3.2.2 EvaluatorContext (типизированный контракт)

```python
# src/conditions/context.py

from dataclasses import dataclass
from typing import Dict, Any, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from src.intent_tracker import IntentTracker


@dataclass
class EvaluatorContext:
    """
    Контекст для проверки условий.

    Все поля гарантированно существуют.
    IntentTracker — единственный источник истории интентов.

    ВАЖНО: Контракт timing'а
    ========================
    record() вызывается В НАЧАЛЕ apply_rules(), ДО создания контекста.
    streak_count() включает текущий интент.
    prev_intent берётся из history[-2] (до текущего).
    """
    # Данные клиента
    collected_data: Dict[str, Any]

    # Состояние диалога
    state: str
    spin_phase: Optional[str]
    is_spin_state: bool

    # Интенты — текущий и предыдущий
    current_intent: str
    prev_intent: Optional[str]

    # IntentTracker — единый источник истории интентов
    intent_tracker: "IntentTracker"

    # Метаданные
    turn_number: int
    missing_required_data: List[str]

    @classmethod
    def from_state_machine(cls, sm: "StateMachine", intent: str) -> "EvaluatorContext":
        """
        Создать контекст из StateMachine.

        Порядок в apply_rules():
            1. intent_tracker.record(intent, state)  # записываем текущий
            2. ctx = EvaluatorContext.from_state_machine(sm, intent)
            3. # Теперь streak_count(intent) включает текущий
        """
        from src.config import SALES_CONFIG

        config = SALES_CONFIG.get("states", {}).get(sm.state, {})
        required = config.get("required_data", [])
        missing = [f for f in required if not sm.collected_data.get(f)]

        return cls(
            collected_data=sm.collected_data.copy(),
            state=sm.state,
            spin_phase=config.get("spin_phase"),
            is_spin_state=config.get("spin_phase") is not None,
            current_intent=intent,
            prev_intent=sm.intent_tracker.prev_intent,
            intent_tracker=sm.intent_tracker,
            turn_number=len(sm.intent_tracker.history),
            missing_required_data=missing,
        )


def create_test_context(**overrides) -> EvaluatorContext:
    """
    Фабрика для создания тестового контекста.

    Использование в тестах:
        ctx = create_test_context(
            collected_data={"company_size": 10},
            current_intent="price_question"
        )
        assert has_pricing_data(ctx) == True
    """
    from src.intent_tracker import IntentTracker

    tracker = IntentTracker()

    defaults = {
        "collected_data": {},
        "state": "spin_situation",
        "spin_phase": "situation",
        "is_spin_state": True,
        "current_intent": "unclear",
        "prev_intent": None,
        "intent_tracker": tracker,
        "turn_number": 1,
        "missing_required_data": [],
    }
    defaults.update(overrides)

    # Записываем текущий интент в трекер для корректного streak
    if "current_intent" in overrides:
        tracker.record(overrides["current_intent"], defaults["state"])

    return EvaluatorContext(**defaults)
```

#### 3.2.3 Определение условий по категориям

```python
# src/conditions/data_conditions.py
"""Условия на основе собранных данных клиента."""

from src.conditions.registry import condition
from src.conditions.context import EvaluatorContext


@condition(
    name="has_pricing_data",
    description="Есть данные для расчёта цены (размер компании или количество пользователей)",
    requires_fields={"company_size", "users_count"},
    category="data",
    examples=[
        "collected_data = {'company_size': 10} → True",
        "collected_data = {} → False"
    ]
)
def has_pricing_data(ctx: EvaluatorContext) -> bool:
    return bool(
        ctx.collected_data.get("company_size") or
        ctx.collected_data.get("users_count")
    )


@condition(
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


@condition(
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


@condition(
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


@condition(
    name="is_large_company",
    description="Крупная компания (50+ сотрудников)",
    requires_fields={"company_size"},
    category="data"
)
def is_large_company(ctx: EvaluatorContext) -> bool:
    size = ctx.collected_data.get("company_size")
    if size is None:
        return False
    try:
        return int(size) > 50
    except (ValueError, TypeError):
        return False


@condition(
    name="is_small_company",
    description="Небольшая компания (до 10 сотрудников)",
    requires_fields={"company_size"},
    category="data"
)
def is_small_company(ctx: EvaluatorContext) -> bool:
    size = ctx.collected_data.get("company_size")
    if size is None:
        return False
    try:
        return int(size) <= 10
    except (ValueError, TypeError):
        return False


@condition(
    name="is_medium_company",
    description="Средняя компания (11-50 сотрудников)",
    requires_fields={"company_size"},
    category="data"
)
def is_medium_company(ctx: EvaluatorContext) -> bool:
    size = ctx.collected_data.get("company_size")
    if size is None:
        return False
    try:
        s = int(size)
        return 10 < s <= 50
    except (ValueError, TypeError):
        return False


@condition(
    name="ready_for_pricing",
    description="Готов к обсуждению цены: есть размер компании И боль",
    requires_fields={"company_size", "pain_point"},
    category="data"
)
def ready_for_pricing(ctx: EvaluatorContext) -> bool:
    return (
        bool(ctx.collected_data.get("company_size")) and
        bool(ctx.collected_data.get("pain_point") or
             ctx.collected_data.get("pain_category"))
    )


@condition(
    name="data_complete",
    description="Все обязательные данные для текущего состояния собраны",
    requires_fields={"missing_required_data"},
    category="data"
)
def data_complete(ctx: EvaluatorContext) -> bool:
    return len(ctx.missing_required_data) == 0


@condition(
    name="has_urgency",
    description="Клиент выразил срочность",
    requires_fields={"urgency"},
    category="data"
)
def has_urgency(ctx: EvaluatorContext) -> bool:
    urgency = ctx.collected_data.get("urgency")
    return urgency in ("high", "urgent", "asap")
```

```python
# src/conditions/intent_conditions.py
"""Условия на основе истории интентов."""

from src.conditions.registry import condition
from src.conditions.context import EvaluatorContext


@condition(
    name="price_repeated_3x",
    description="Вопрос о цене задан 3+ раз подряд",
    requires_fields={"intent_tracker", "current_intent"},
    category="intent",
    examples=[
        "3x price_question подряд → True",
        "price_question, greeting, price_question → False (не подряд)"
    ]
)
def price_repeated_3x(ctx: EvaluatorContext) -> bool:
    if ctx.current_intent != "price_question":
        return False
    return ctx.intent_tracker.streak_count("price_question") >= 3


@condition(
    name="question_repeated_2x",
    description="Текущий вопрос задан 2+ раз подряд",
    requires_fields={"intent_tracker", "current_intent"},
    category="intent"
)
def question_repeated_2x(ctx: EvaluatorContext) -> bool:
    return ctx.intent_tracker.streak_count(ctx.current_intent) >= 2


@condition(
    name="after_greeting",
    description="Предыдущий интент был приветствием",
    requires_fields={"prev_intent"},
    category="intent"
)
def after_greeting(ctx: EvaluatorContext) -> bool:
    return ctx.prev_intent in ("greeting", "small_talk")


@condition(
    name="after_objection",
    description="Предыдущий интент был возражением",
    requires_fields={"prev_intent"},
    category="intent"
)
def after_objection(ctx: EvaluatorContext) -> bool:
    return ctx.prev_intent is not None and ctx.prev_intent.startswith("objection_")


@condition(
    name="is_technical_question",
    description="Текущий интент — технический вопрос",
    requires_fields={"current_intent"},
    category="intent"
)
def is_technical_question(ctx: EvaluatorContext) -> bool:
    return ctx.current_intent in (
        "question_technical",
        "question_integrations",
        "question_api"
    )


@condition(
    name="is_price_question",
    description="Текущий интент — вопрос о цене",
    requires_fields={"current_intent"},
    category="intent"
)
def is_price_question(ctx: EvaluatorContext) -> bool:
    return ctx.current_intent in ("price_question", "pricing_details")
```

```python
# src/conditions/counter_conditions.py
"""Условия на основе счётчиков (возражения, ходы)."""

from src.conditions.registry import condition
from src.conditions.context import EvaluatorContext


@condition(
    name="objection_limit_reached",
    description="Достигнут лимит возражений подряд (3+)",
    requires_fields={"intent_tracker"},
    category="counter"
)
def objection_limit_reached(ctx: EvaluatorContext) -> bool:
    return ctx.intent_tracker.objection_consecutive() >= 3


@condition(
    name="many_objections_total",
    description="Много возражений за диалог (5+)",
    requires_fields={"intent_tracker"},
    category="counter"
)
def many_objections_total(ctx: EvaluatorContext) -> bool:
    return ctx.intent_tracker.objection_total() >= 5


@condition(
    name="early_conversation",
    description="Начало разговора (первые 3 хода)",
    requires_fields={"turn_number"},
    category="counter"
)
def early_conversation(ctx: EvaluatorContext) -> bool:
    return ctx.turn_number <= 3


@condition(
    name="mid_conversation",
    description="Середина разговора (4-10 ходов)",
    requires_fields={"turn_number"},
    category="counter"
)
def mid_conversation(ctx: EvaluatorContext) -> bool:
    return 3 < ctx.turn_number <= 10


@condition(
    name="late_conversation",
    description="Затянувшийся разговор (10+ ходов)",
    requires_fields={"turn_number"},
    category="counter"
)
def late_conversation(ctx: EvaluatorContext) -> bool:
    return ctx.turn_number > 10
```

```python
# src/conditions/state_conditions.py
"""Условия на основе состояния диалога."""

from src.conditions.registry import condition
from src.conditions.context import EvaluatorContext


@condition(
    name="in_spin_phase",
    description="Находимся в SPIN-фазе диалога",
    requires_fields={"is_spin_state"},
    category="state"
)
def in_spin_phase(ctx: EvaluatorContext) -> bool:
    return ctx.is_spin_state


@condition(
    name="in_closing_phase",
    description="Находимся в фазе закрытия (close, soft_close)",
    requires_fields={"state"},
    category="state"
)
def in_closing_phase(ctx: EvaluatorContext) -> bool:
    return ctx.state in ("close", "soft_close")


@condition(
    name="in_presentation",
    description="Находимся в фазе презентации",
    requires_fields={"state"},
    category="state"
)
def in_presentation(ctx: EvaluatorContext) -> bool:
    return ctx.state == "presentation"


@condition(
    name="past_spin",
    description="Вышли из SPIN-фазы (presentation, close, etc.)",
    requires_fields={"state", "is_spin_state"},
    category="state"
)
def past_spin(ctx: EvaluatorContext) -> bool:
    return not ctx.is_spin_state and ctx.state not in ("greeting", "initial")


@condition(
    name="in_situation_phase",
    description="В фазе Situation (SPIN)",
    requires_fields={"spin_phase"},
    category="state"
)
def in_situation_phase(ctx: EvaluatorContext) -> bool:
    return ctx.spin_phase == "situation"


@condition(
    name="in_problem_phase",
    description="В фазе Problem (SPIN)",
    requires_fields={"spin_phase"},
    category="state"
)
def in_problem_phase(ctx: EvaluatorContext) -> bool:
    return ctx.spin_phase == "problem"
```

```python
# src/conditions/composite_conditions.py
"""Составные условия (комбинации базовых)."""

from src.conditions.registry import condition, registry
from src.conditions.context import EvaluatorContext


@condition(
    name="should_answer_price",
    description="Следует ответить на вопрос о цене: есть данные ИЛИ спросили 3+ раз",
    requires_fields={"collected_data", "intent_tracker"},
    category="composite"
)
def should_answer_price(ctx: EvaluatorContext) -> bool:
    has_data = registry.evaluate("has_pricing_data", ctx)
    repeated = registry.evaluate("price_repeated_3x", ctx)
    return has_data or repeated


@condition(
    name="ready_for_demo_offer",
    description="Готов к предложению демо: прошли SPIN + есть боль + не было отказа",
    requires_fields={"state", "collected_data", "prev_intent"},
    category="composite"
)
def ready_for_demo_offer(ctx: EvaluatorContext) -> bool:
    past_spin = registry.evaluate("past_spin", ctx)
    has_pain = registry.evaluate("has_pain_point", ctx)
    recent_rejection = ctx.prev_intent == "rejection"
    return past_spin and has_pain and not recent_rejection


@condition(
    name="should_escalate_to_human",
    description="Нужна эскалация на человека: много возражений + поздний этап",
    requires_fields={"intent_tracker", "turn_number"},
    category="composite"
)
def should_escalate_to_human(ctx: EvaluatorContext) -> bool:
    objection_limit = registry.evaluate("objection_limit_reached", ctx)
    late_convo = registry.evaluate("late_conversation", ctx)
    return objection_limit and late_convo


@condition(
    name="should_offer_soft_close",
    description="Пора предложить мягкое завершение",
    requires_fields={"intent_tracker", "state"},
    category="composite"
)
def should_offer_soft_close(ctx: EvaluatorContext) -> bool:
    objection_limit = registry.evaluate("objection_limit_reached", ctx)
    in_closing = registry.evaluate("in_closing_phase", ctx)
    return objection_limit and in_closing


@condition(
    name="can_handle_objection_with_roi",
    description="Можно обработать возражение о цене через ROI",
    requires_fields={"collected_data"},
    category="composite"
)
def can_handle_objection_with_roi(ctx: EvaluatorContext) -> bool:
    has_pricing = registry.evaluate("has_pricing_data", ctx)
    has_pain = registry.evaluate("has_pain_point", ctx)
    return has_pricing and has_pain
```

### 3.3 IntentTracker — единый источник истории интентов

```python
# src/intent_tracker.py

from dataclasses import dataclass, field
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
    - ContextWindow.get_objection_count()

    ВАЖНО: Контракт timing'а
    ========================
    record() вызывается В НАЧАЛЕ apply_rules(), ДО проверки условий.
    Все методы возвращают значения ВКЛЮЧАЯ текущий записанный интент.

    Пример:
        Ход 1: price_question → record() → streak=1, >=3 → False
        Ход 2: price_question → record() → streak=2, >=3 → False
        Ход 3: price_question → record() → streak=3, >=3 → True ✓
    """

    MAX_HISTORY = 50

    def __init__(self):
        self.history: List[IntentRecord] = []
        self._streak_count: int = 0
        self._last_intent: Optional[str] = None

    def record(self, intent: str, state: str) -> None:
        """
        Записать интент. Вызывать В НАЧАЛЕ apply_rules().

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
        """Определить категорию интента из INTENT_CATEGORIES."""
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
    # ЧТЕНИЕ — для условий streak
    # ═══════════════════════════════════════════════════════════════════

    def streak_count(self, intent: str) -> int:
        """
        Сколько раз этот интент идёт подряд (включая текущий).

        Для условия ">=3" проверяем streak_count(intent) >= 3.
        """
        if intent == self._last_intent:
            return self._streak_count
        return 0

    def count_in_window(self, intent: str, window: int = 5) -> int:
        """Сколько раз интент встречался в последних N ходах."""
        recent = self.history[-window:] if window else self.history
        return sum(1 for r in recent if r.intent == intent)

    # ═══════════════════════════════════════════════════════════════════
    # ЧТЕНИЕ — для условий objection (заменяет ObjectionFlowManager)
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
    # ЧТЕНИЕ — для других категорий
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
        """Сериализация для ContextEnvelope."""
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

### 3.4 Трассировка выполнения (для дебага и симуляций)

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
    entries: List[TraceEntry] = field(default_factory=list)
    final_action: Optional[str] = None
    resolution: str = ""  # "condition_matched", "default", "simple"
    matched_condition: Optional[str] = None

    def record(
        self,
        condition_name: str,
        result: bool,
        ctx: "EvaluatorContext",
        relevant_fields: Set[str] = None
    ):
        """Записать результат проверки условия."""
        context_snapshot = {}

        if relevant_fields:
            for field_name in relevant_fields:
                if hasattr(ctx, field_name):
                    context_snapshot[field_name] = getattr(ctx, field_name)
                elif field_name in ctx.collected_data:
                    context_snapshot[field_name] = ctx.collected_data[field_name]
        else:
            context_snapshot = {
                "state": ctx.state,
                "current_intent": ctx.current_intent,
            }

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

    def create_trace(self, rule_name: str, intent: str, state: str) -> EvaluationTrace:
        trace = EvaluationTrace(rule_name=rule_name, intent=intent, state=state)
        self.traces.append(trace)
        return trace

    def get_summary(self) -> Dict[str, Any]:
        """Статистика по трассировкам."""
        total = len(self.traces)
        matched = sum(1 for t in self.traces if t.resolution == "condition_matched")
        defaults = sum(1 for t in self.traces if t.resolution == "default")

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
            "condition_stats": condition_hits
        }
```

### 3.5 RuleResolver

```python
# src/rules/resolver.py

from typing import Optional, Union, Tuple, List
from dataclasses import dataclass

from src.conditions import registry, EvaluatorContext
from src.conditions.trace import EvaluationTrace


# Тип правила
RuleValue = Union[
    str,                                    # Простое: "action"
    Tuple[str, str],                        # Одно условие: ("condition", "action")
    List[Union[Tuple[str, str], str, None]] # Список + default
]


@dataclass
class RuleResult:
    """
    Результат разрешения правила.

    Поддерживает tuple unpacking для обратной совместимости:
        action, state = resolver.resolve(...)
    """
    action: str
    next_state: Optional[str]
    trace: Optional[EvaluationTrace] = None

    def __iter__(self):
        """Для обратной совместимости."""
        return iter((self.action, self.next_state))


class RuleResolver:
    """
    Разрешает правила: условие → действие.

    Работает с декларативными правилами из config.py,
    вычисляя условия через ConditionRegistry.
    """

    def __init__(self, config: dict = None):
        from src.config import SALES_CONFIG
        self.config = config or SALES_CONFIG

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
        3. "continue_current_goal" (fallback)
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
        """
        Разрешить transition для интента.

        Returns:
            Новое состояние или None (остаться)
        """
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
        """
        Вычислить правило.

        Форматы:
            "action"                          → вернуть action
            ("condition", "action")           → если condition=True
            [("c1", "a1"), ("c2", "a2"), "d"] → первое сработавшее или default
        """
        # Простое правило: строка
        if isinstance(rule, str):
            if trace:
                trace.set_result(rule, "simple")
            return rule

        # None (для transitions)
        if rule is None:
            if trace:
                trace.set_result(None, "explicit_none")
            return None

        # Одно условие: tuple
        if isinstance(rule, tuple) and len(rule) == 2:
            condition_name, action = rule
            result = registry.evaluate(condition_name, ctx, trace)

            if result:
                if trace:
                    trace.set_result(action, "condition_matched", condition_name)
                return action
            else:
                if allow_none:
                    if trace:
                        trace.set_result(None, "condition_not_matched")
                    return None
                raise ValueError(
                    f"Single condition '{condition_name}' did not match, no default"
                )

        # Список условий
        if isinstance(rule, list):
            default_action = None

            for item in rule:
                # Default
                if isinstance(item, str):
                    default_action = item
                    continue
                if item is None:
                    default_action = None
                    continue

                # Условие
                if isinstance(item, tuple) and len(item) == 2:
                    condition_name, action = item
                    result = registry.evaluate(condition_name, ctx, trace)

                    if result:
                        if trace:
                            trace.set_result(action, "condition_matched", condition_name)
                        return action

            # Default
            if trace:
                trace.set_result(default_action, "default")
            return default_action

        raise ValueError(f"Invalid rule format: {rule}")

    def validate_config(self) -> dict:
        """Валидация конфигурации."""
        errors = []
        warnings = []

        all_conditions = set(registry.list_all())
        all_states = set(self.config.get("states", {}).keys())

        for state_name, state_config in self.config.get("states", {}).items():
            # Проверка rules
            for intent, rule in state_config.get("rules", {}).items():
                conditions = self._extract_conditions(rule)
                for cond in conditions:
                    if cond not in all_conditions:
                        errors.append(
                            f"State '{state_name}', rule '{intent}': "
                            f"unknown condition '{cond}'"
                        )

            # Проверка transitions
            for intent, rule in state_config.get("transitions", {}).items():
                conditions = self._extract_conditions(rule)
                for cond in conditions:
                    if cond not in all_conditions:
                        errors.append(
                            f"State '{state_name}', transition '{intent}': "
                            f"unknown condition '{cond}'"
                        )

                targets = self._extract_targets(rule)
                for target in targets:
                    if target and target not in all_states:
                        errors.append(
                            f"State '{state_name}', transition '{intent}': "
                            f"unknown target '{target}'"
                        )

        # Global rules
        for intent, rule in self.config.get("global_rules", {}).items():
            conditions = self._extract_conditions(rule)
            for cond in conditions:
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

### 3.6 Конфигурация (config.py)

```python
# src/config.py

"""
Конфигурация правил.

Условия определены в src/conditions/*.py как Python-функции.
Здесь только МАППИНГ: какое условие → какое действие.

Формат правила:
    "intent": "action"                           # Простое
    "intent": ("condition_name", "action")       # Одно условие
    "intent": [                                  # Несколько условий
        ("condition_1", "action_1"),
        ("condition_2", "action_2"),
        "default_action"                         # Default
    ]
"""

from typing import Dict, List, Tuple, Union

RuleValue = Union[
    str,
    Tuple[str, str],
    List[Union[Tuple[str, str], str, None]]
]


# ═══════════════════════════════════════════════════════════════════════════════
# INTENT_CATEGORIES — категории интентов для hooks и tracking
# ═══════════════════════════════════════════════════════════════════════════════

INTENT_CATEGORIES = {
    "objection": [
        "objection_price",
        "objection_competitor",
        "objection_no_time",
        "objection_think",
        "objection_not_interested"
    ],
    "positive": [
        "agreement", "demo_request", "callback_request", "contact_provided",
        "consultation_request",
        "situation_provided", "problem_revealed", "implication_acknowledged",
        "need_expressed", "info_provided",
        "question_features", "question_integrations", "comparison",
        "greeting", "gratitude"
    ],
    "go_back": ["go_back", "correct_info"],
    "question": [
        "question_features", "question_integrations", "question_technical"
    ]
}


# ═══════════════════════════════════════════════════════════════════════════════
# SHARED RULES — переиспользуемые правила (Python dict unpacking)
# ═══════════════════════════════════════════════════════════════════════════════

SPIN_COMMON_RULES: Dict[str, RuleValue] = {
    # Вопрос о цене с условиями
    "price_question": [
        ("has_pricing_data", "answer_with_facts"),
        ("price_repeated_3x", "answer_with_range"),
        "deflect_and_continue"
    ],

    # Детали цены
    "pricing_details": [
        ("has_pricing_data", "answer_with_facts"),
        "deflect_and_continue"
    ],

    # Сравнение
    "comparison": [
        ("has_competitor_mention", "compare_with_known_competitor"),
        "answer_and_continue"
    ],

    # Возражения (базовая обработка в SPIN)
    "objection_price": [
        ("can_handle_objection_with_roi", "handle_objection_with_roi"),
        "handle_objection"
    ],

    # Простые правила
    "question_features": "answer_question",
    "question_integrations": "answer_question",
}


POST_SPIN_RULES: Dict[str, RuleValue] = {
    # После SPIN — данные уже есть
    "price_question": "answer_with_facts",
    "pricing_details": "answer_with_facts",

    # Возражения с эскалацией
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


# ═══════════════════════════════════════════════════════════════════════════════
# SALES_CONFIG — основная конфигурация (2 уровня: state → global)
# ═══════════════════════════════════════════════════════════════════════════════

SALES_CONFIG = {
    # Глобальные правила — fallback для всех состояний
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
        # ─────────────────────────────────────────────────────────────────────
        # SPIN States
        # ─────────────────────────────────────────────────────────────────────
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

        # ─────────────────────────────────────────────────────────────────────
        # Post-SPIN States
        # ─────────────────────────────────────────────────────────────────────
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

### 3.7 Обновлённый StateMachine

```python
# src/state_machine.py

from typing import Optional
from dataclasses import dataclass

from src.conditions import EvaluatorContext, registry
from src.conditions.trace import EvaluationTrace, TraceCollector
from src.rules.resolver import RuleResolver, RuleResult
from src.intent_tracker import IntentTracker
from src.config import SALES_CONFIG, INTENT_CATEGORIES


class StateMachine:
    """
    State Machine с гибридной архитектурой:
    - Условия: Python-функции (типизация, IDE, дебаг)
    - Правила: декларативная конфигурация (читаемость)
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
        """Текущая SPIN-фаза."""
        state_config = self.config.get("states", {}).get(self.state, {})
        return state_config.get("spin_phase")

    def apply_rules(self, intent: str) -> RuleResult:
        """
        Применить правила для интента.

        Returns:
            RuleResult с action, next_state и трассировкой.
            Поддерживает: action, state = sm.apply_rules(intent)
        """
        # ═══════════════════════════════════════════════════════════════════
        # 0. HOOKS: Записываем интент в tracker
        # ═══════════════════════════════════════════════════════════════════
        self.intent_tracker.record(intent, self.state)

        # ═══════════════════════════════════════════════════════════════════
        # 1. Создаём контекст
        # ═══════════════════════════════════════════════════════════════════
        ctx = self._create_context(intent)

        # ═══════════════════════════════════════════════════════════════════
        # 2. Создаём трассировку (опционально)
        # ═══════════════════════════════════════════════════════════════════
        trace = None
        if self.trace_collector:
            trace = self.trace_collector.create_trace(
                rule_name=f"{self.state}.{intent}",
                intent=intent,
                state=self.state
            )

        # ═══════════════════════════════════════════════════════════════════
        # 3. Early exits (final states)
        # ═══════════════════════════════════════════════════════════════════
        early_exit = self._check_early_exits(intent)
        if early_exit:
            return early_exit

        # ═══════════════════════════════════════════════════════════════════
        # 4. Resolve action
        # ═══════════════════════════════════════════════════════════════════
        action = self.rule_resolver.resolve_action(
            intent=intent,
            state=self.state,
            ctx=ctx,
            trace=trace
        )

        # ═══════════════════════════════════════════════════════════════════
        # 5. Resolve transition
        # ═══════════════════════════════════════════════════════════════════
        next_state = self.rule_resolver.resolve_transition(
            intent=intent,
            state=self.state,
            ctx=ctx,
            trace=trace
        )

        # ═══════════════════════════════════════════════════════════════════
        # 6. Fallback transitions
        # ═══════════════════════════════════════════════════════════════════
        if next_state is None:
            next_state = self._fallback_transition(intent, ctx)

        # ═══════════════════════════════════════════════════════════════════
        # 7. Apply transition
        # ═══════════════════════════════════════════════════════════════════
        if next_state and next_state != self.state:
            self.state = next_state

        return RuleResult(
            action=action,
            next_state=self.state,
            trace=trace
        )

    def _create_context(self, intent: str) -> EvaluatorContext:
        """Создать контекст для вычисления условий."""
        return EvaluatorContext.from_state_machine(self, intent)

    def _check_early_exits(self, intent: str) -> Optional[RuleResult]:
        """Проверка на ранние выходы."""
        state_config = self.config.get("states", {}).get(self.state, {})

        if state_config.get("is_final"):
            return RuleResult(action="stay", next_state=self.state)

        return None

    def _fallback_transition(
        self,
        intent: str,
        ctx: EvaluatorContext
    ) -> Optional[str]:
        """Fallback: SPIN progress, data_complete."""
        state_config = self.config.get("states", {}).get(self.state, {})
        transitions = state_config.get("transitions", {})

        # data_complete transition
        if "data_complete" in transitions:
            if registry.evaluate("data_complete", ctx):
                target = transitions["data_complete"]
                if isinstance(target, str):
                    return target

        return None

    def update_data(self, data: dict):
        """Обновить собранные данные."""
        self.collected_data.update(data)

    def reset(self):
        """Сбросить состояние."""
        self.state = "spin_situation"
        self.collected_data = {}
        self.intent_tracker.reset()

    def get_state_info(self) -> dict:
        """Информация о текущем состоянии."""
        state_config = self.config.get("states", {}).get(self.state, {})
        return {
            "state": self.state,
            "goal": state_config.get("goal", ""),
            "spin_phase": state_config.get("spin_phase"),
            "is_final": state_config.get("is_final", False),
            "required_data": state_config.get("required_data", []),
            "intent_tracker": self.intent_tracker.to_dict(),
        }
```

---

## Часть 4: УДАЛЕНИЕ ДУБЛИРОВАНИЯ

### 4.1 Что удаляется

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  КОМПОНЕНТЫ К УДАЛЕНИЮ                                                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  1. StateMachine.last_intent                                                │
│     - УДАЛИТЬ: self.last_intent = intent                                    │
│     - ДОСТУП ЧЕРЕЗ: self.intent_tracker.last_intent                         │
│                                                                             │
│  2. Bot.last_intent                                                         │
│     - УДАЛИТЬ: self.last_intent = classified_intent                         │
│     - ДОСТУП ЧЕРЕЗ: self.state_machine.intent_tracker.last_intent           │
│                                                                             │
│  3. ObjectionFlowManager (ВЕСЬ КЛАСС)                                       │
│     - УДАЛИТЬ: class ObjectionFlowManager                                   │
│     - УДАЛИТЬ: self.objection_flow = ObjectionFlowManager()                 │
│     - ЗАМЕНА:                                                               │
│       objection_flow.objection_count → intent_tracker.objection_consecutive()│
│       objection_flow.total_objections → intent_tracker.objection_total()    │
│       objection_flow.record_objection() → автоматически через category      │
│       objection_flow.reset_consecutive() → не нужен                         │
│                                                                             │
│  4. ContextEnvelope.last_intent                                             │
│     - ЗАМЕНИТЬ: "last_intent" → "intent_tracker": tracker.to_dict()         │
│                                                                             │
│  5. Hardcoded списки интентов                                               │
│     - УДАЛИТЬ: OBJECTION_INTENTS = [...]                                    │
│     - УДАЛИТЬ: POSITIVE_INTENTS = {...}                                     │
│     - УДАЛИТЬ: QUESTION_INTENTS = [...]                                     │
│     - ЗАМЕНА: INTENT_CATEGORIES в config.py                                 │
│                                                                             │
│  6. Костыли в apply_rules()                                                 │
│     - УДАЛИТЬ: if intent == "price_question" and ...                        │
│     - ЗАМЕНА: условие has_pricing_data в config                             │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 4.2 Результат

| Было | Стало |
|------|-------|
| 4+ источника last_intent | 1 источник: intent_tracker.last_intent |
| ObjectionFlowManager класс | УДАЛЁН |
| Ручной record_objection() | Автоматически через category |
| Ручной reset_consecutive() | Не нужен (динамическое вычисление) |
| Hardcoded OBJECTION_INTENTS | INTENT_CATEGORIES["objection"] |
| Hardcoded POSITIVE_INTENTS | INTENT_CATEGORIES["positive"] |
| if should_soft_close(): ... | условие objection_limit_reached |
| 8+ if'ов в apply_rules() | 4 этапа: hooks → exit → action → state |

---

## Часть 5: TOOLING И ВАЛИДАЦИЯ

### 5.1 CI Валидация

```python
# scripts/validate_config.py

#!/usr/bin/env python3
"""
Валидация конфигурации правил и условий.

Запуск:
    python scripts/validate_config.py
    python scripts/validate_config.py --strict  # Fail on warnings
"""

import sys
import argparse

from src.conditions import registry
from src.conditions.context import create_test_context
from src.rules.resolver import RuleResolver
from src.config import SALES_CONFIG


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    print("=" * 60)
    print("VALIDATING CONDITIONS AND RULES")
    print("=" * 60)

    errors = []
    warnings = []

    # 1. Validate conditions
    print("\n1. Validating conditions...")
    results = registry.validate_all(create_test_context)

    print(f"   Passed: {len(results['passed'])}")
    print(f"   Failed: {len(results['failed'])}")
    print(f"   Errors: {len(results['errors'])}")

    for fail in results["failed"]:
        errors.append(f"Condition '{fail['name']}': {fail['reason']}")
    for err in results["errors"]:
        errors.append(f"Condition '{err['name']}': {err['error']}")

    # 2. Validate config
    print("\n2. Validating config...")
    resolver = RuleResolver(SALES_CONFIG)
    config_results = resolver.validate_config()

    print(f"   Valid: {config_results['valid']}")
    print(f"   Errors: {len(config_results['errors'])}")

    errors.extend(config_results["errors"])
    warnings.extend(config_results.get("warnings", []))

    # 3. Summary
    print("\n3. Registered conditions:")
    print(f"   Total: {len(registry.list_all())}")
    for cat in ["data", "intent", "counter", "state", "composite"]:
        print(f"   {cat}: {len(registry.list_by_category(cat))}")

    # 4. Result
    print("\n" + "=" * 60)

    if errors:
        print("ERRORS:")
        for err in errors:
            print(f"  ✗ {err}")

    if warnings:
        print("WARNINGS:")
        for warn in warnings:
            print(f"  ⚠ {warn}")

    if errors:
        print("\n❌ VALIDATION FAILED")
        sys.exit(1)

    if warnings and args.strict:
        print("\n❌ VALIDATION FAILED (strict)")
        sys.exit(1)

    print("\n✅ VALIDATION PASSED")


if __name__ == "__main__":
    main()
```

### 5.2 Генератор документации

```python
# scripts/generate_docs.py

#!/usr/bin/env python3
"""
Генерация документации по условиям и правилам.

Запуск:
    python scripts/generate_docs.py > docs/CONDITIONS.md
"""

from src.conditions import registry
from src.config import SALES_CONFIG


def main():
    # Conditions
    print(registry.get_documentation())
    print("\n---\n")

    # Rules
    print("# Rules Configuration\n")

    print("## Global Rules\n")
    for intent, rule in SALES_CONFIG.get("global_rules", {}).items():
        print(f"- `{intent}`: {_format_rule(rule)}")

    print("\n## States\n")
    for state_name, config in SALES_CONFIG.get("states", {}).items():
        print(f"### {state_name}")
        print(f"**Goal:** {config.get('goal', 'N/A')}\n")

        if config.get("rules"):
            print("**Rules:**")
            for intent, rule in config["rules"].items():
                print(f"- `{intent}`: {_format_rule(rule)}")
            print()


def _format_rule(rule) -> str:
    if isinstance(rule, str):
        return f"`{rule}`"
    if rule is None:
        return "_stay_"
    if isinstance(rule, tuple):
        return f"if `{rule[0]}` → `{rule[1]}`"
    if isinstance(rule, list):
        parts = []
        for item in rule:
            if isinstance(item, str):
                parts.append(f"default: `{item}`")
            elif isinstance(item, tuple):
                parts.append(f"if `{item[0]}` → `{item[1]}`")
        return " | ".join(parts)
    return str(rule)


if __name__ == "__main__":
    main()
```

### 5.3 Тесты условий

```python
# tests/test_conditions.py

import pytest
from src.conditions import registry
from src.conditions.context import create_test_context


class TestDataConditions:
    """Тесты условий категории 'data'."""

    def test_has_pricing_data_with_company_size(self):
        ctx = create_test_context(
            collected_data={"company_size": 10}
        )
        assert registry.evaluate("has_pricing_data", ctx) == True

    def test_has_pricing_data_with_users_count(self):
        ctx = create_test_context(
            collected_data={"users_count": 5}
        )
        assert registry.evaluate("has_pricing_data", ctx) == True

    def test_has_pricing_data_empty(self):
        ctx = create_test_context(collected_data={})
        assert registry.evaluate("has_pricing_data", ctx) == False

    def test_is_large_company(self):
        ctx = create_test_context(collected_data={"company_size": 100})
        assert registry.evaluate("is_large_company", ctx) == True

        ctx = create_test_context(collected_data={"company_size": 10})
        assert registry.evaluate("is_large_company", ctx) == False

    def test_data_complete(self):
        ctx = create_test_context(missing_required_data=[])
        assert registry.evaluate("data_complete", ctx) == True

        ctx = create_test_context(missing_required_data=["company_size"])
        assert registry.evaluate("data_complete", ctx) == False


class TestIntentConditions:
    """Тесты условий категории 'intent'."""

    def test_price_repeated_3x(self):
        from src.intent_tracker import IntentTracker

        tracker = IntentTracker()
        tracker.record("price_question", "spin_situation")
        tracker.record("price_question", "spin_situation")
        tracker.record("price_question", "spin_situation")

        ctx = create_test_context(
            current_intent="price_question",
            intent_tracker=tracker
        )

        assert registry.evaluate("price_repeated_3x", ctx) == True

    def test_price_repeated_not_enough(self):
        from src.intent_tracker import IntentTracker

        tracker = IntentTracker()
        tracker.record("price_question", "spin_situation")
        tracker.record("price_question", "spin_situation")

        ctx = create_test_context(
            current_intent="price_question",
            intent_tracker=tracker
        )

        assert registry.evaluate("price_repeated_3x", ctx) == False


class TestCounterConditions:
    """Тесты условий категории 'counter'."""

    def test_objection_limit_reached(self):
        from src.intent_tracker import IntentTracker

        tracker = IntentTracker()
        tracker.record("objection_price", "close")
        tracker.record("objection_price", "close")
        tracker.record("objection_price", "close")

        ctx = create_test_context(intent_tracker=tracker)

        assert registry.evaluate("objection_limit_reached", ctx) == True

    def test_early_conversation(self):
        ctx = create_test_context(turn_number=2)
        assert registry.evaluate("early_conversation", ctx) == True

        ctx = create_test_context(turn_number=5)
        assert registry.evaluate("early_conversation", ctx) == False


class TestCompositeConditions:
    """Тесты составных условий."""

    def test_should_answer_price_has_data(self):
        ctx = create_test_context(
            collected_data={"company_size": 10},
            current_intent="price_question"
        )
        assert registry.evaluate("should_answer_price", ctx) == True

    def test_can_handle_with_roi(self):
        ctx = create_test_context(
            collected_data={
                "company_size": 10,
                "pain_point": "теряем клиентов"
            }
        )
        assert registry.evaluate("can_handle_objection_with_roi", ctx) == True
```

---

## Часть 6: ПЛАН РЕАЛИЗАЦИИ

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  ЭТАП 1: Foundation — Условия и Реестр                                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  1.1 Создать структуру src/conditions/:                                     │
│      ├── __init__.py                                                        │
│      ├── registry.py         (ConditionRegistry, @condition)                │
│      ├── context.py          (EvaluatorContext, create_test_context)        │
│      ├── trace.py            (EvaluationTrace, TraceCollector)              │
│      ├── exceptions.py       (ConditionNotFoundError, etc.)                 │
│      ├── data_conditions.py                                                 │
│      ├── intent_conditions.py                                               │
│      ├── counter_conditions.py                                              │
│      ├── state_conditions.py                                                │
│      └── composite_conditions.py                                            │
│                                                                             │
│  1.2 Определить ~25 базовых условий по категориям                           │
│                                                                             │
│  1.3 Написать unit-тесты (tests/test_conditions.py)                         │
│                                                                             │
│  Результат: Работающий реестр, 100% покрытие тестами                        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  ЭТАП 2: IntentTracker — единый источник                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  2.1 Создать src/intent_tracker.py:                                         │
│      - IntentRecord dataclass                                               │
│      - IntentTracker class                                                  │
│      - Методы: record(), streak_count(), objection_*(), to_dict()           │
│                                                                             │
│  2.2 Написать тесты (tests/test_intent_tracker.py)                          │
│                                                                             │
│  Результат: Готовый IntentTracker для интеграции                            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  ЭТАП 3: RuleResolver и конфигурация                                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  3.1 Создать src/rules/:                                                    │
│      ├── __init__.py                                                        │
│      ├── resolver.py         (RuleResolver, RuleResult)                     │
│      └── validator.py        (validate_config)                              │
│                                                                             │
│  3.2 Обновить src/config.py:                                                │
│      - INTENT_CATEGORIES                                                    │
│      - SPIN_COMMON_RULES, POST_SPIN_RULES                                   │
│      - SALES_CONFIG с новым форматом                                        │
│                                                                             │
│  3.3 Написать тесты resolver'а                                              │
│                                                                             │
│  Результат: RuleResolver работает с Python conditions                       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  ЭТАП 4: Интеграция в StateMachine                                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  4.1 Рефакторинг apply_rules():                                             │
│      - Использовать RuleResolver                                            │
│      - Создавать EvaluatorContext                                           │
│      - Поддержка трассировки                                                │
│                                                                             │
│  4.2 Удалить дублирование:                                                  │
│      - SM.last_intent → intent_tracker                                      │
│      - ObjectionFlowManager → удалить                                       │
│      - Hardcoded списки → INTENT_CATEGORIES                                 │
│      - Костыль price_question → условие                                     │
│                                                                             │
│  4.3 Обновить Bot.py:                                                       │
│      - Удалить Bot.last_intent                                              │
│      - Доступ через state_machine.intent_tracker                            │
│                                                                             │
│  4.4 Обновить ContextEnvelope                                               │
│                                                                             │
│  4.5 Обеспечить обратную совместимость (RuleResult с __iter__)              │
│                                                                             │
│  Результат: SM использует новую архитектуру, старый код работает            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  ЭТАП 5: Tooling и CI                                                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  5.1 Валидация:                                                             │
│      - scripts/validate_config.py                                           │
│      - Интеграция в CI pipeline (GitHub Actions / pre-commit)               │
│                                                                             │
│  5.2 Документация:                                                          │
│      - scripts/generate_docs.py                                             │
│      - Автогенерация docs/CONDITIONS.md                                     │
│                                                                             │
│  5.3 IDE Support:                                                           │
│      - Type hints везде                                                     │
│      - Примеры использования                                                │
│                                                                             │
│  Результат: Полный tooling, ошибки ловятся на CI                            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  ЭТАП 6: Тестирование и миграция                                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  6.1 Интеграционные тесты:                                                  │
│      - tests/test_state_machine_integration.py                              │
│      - Полные сценарии диалогов                                             │
│                                                                             │
│  6.2 Симуляции:                                                             │
│      - Запуск симуляций с трассировкой                                      │
│      - Сравнение результатов до/после                                       │
│      - Анализ трассировок                                                   │
│                                                                             │
│  6.3 Миграция существующих правил:                                          │
│      - Конвертация всех правил в новый формат                               │
│      - Удаление legacy кода                                                 │
│                                                                             │
│  Результат: Система полностью мигрирована, костыли удалены                  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  ЭТАП 7-9: Расширение (опционально, после стабилизации)                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Решение о необходимости принимается после успешного завершения 1-6.        │
│  Если текущая архитектура решает проблемы — расширение не требуется.        │
│                                                                             │
│  7. DialoguePolicy:                                                         │
│     - Добавить policy_conditions.py                                         │
│     - PolicyContext dataclass                                               │
│     - POLICY_RULES в config                                                 │
│                                                                             │
│  8. FallbackHandler:                                                        │
│     - Добавить fallback_conditions.py                                       │
│     - FallbackContext dataclass                                             │
│     - FALLBACK_ESCALATION_RULES, DYNAMIC_CTA_RULES                          │
│                                                                             │
│  9. PersonalizationEngine:                                                  │
│     - Добавить personalization_conditions.py                                │
│     - PersonalizationContext dataclass                                      │
│     - MESSAGING_STYLE_RULES, VALUE_PROP_COMPONENTS                          │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Часть 7: ЛОГГИРОВАНИЕ ДЛЯ СИМУЛЯЦИЙ

### 7.1 Формат вывода

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  ФОРМАТ ДИАЛОГА С ТРАССИРОВКОЙ                                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  [Ход 3]                                                                    │
│  Клиент: А сколько это стоит?                                               │
│  Бот: Чтобы назвать точную цену, уточните сколько человек в команде?        │
│    (state=spin_situation, intent=price_question, action=deflect_and_continue)
│    [RULE] conditional → DEFAULT                                             │
│           has_pricing_data=FAIL (company_size=None)                         │
│           price_repeated_3x=FAIL (streak=1)                                 │
│           → deflect_and_continue                                            │
│                                                                             │
│  [Ход 5]                                                                    │
│  Клиент: Ну так сколько стоит-то?                                           │
│  Бот: При команде из 10 человек стоимость составит 15000₸ в месяц.          │
│    (state=spin_situation, intent=price_question, action=answer_with_facts)  │
│    [RULE] conditional → MATCHED                                             │
│           has_pricing_data=PASS (company_size=10)                           │
│           → answer_with_facts                                               │
│                                                                             │
│  [Ход 7]                                                                    │
│  Клиент: Расскажите про интеграции                                          │
│  Бот: Мы интегрируемся с 1С, Kaspi, WhatsApp...                             │
│    (state=spin_situation, intent=question_integrations)                     │
│    [RULE] simple → answer_question                                          │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 7.2 Интеграция с симуляциями

```python
# В runner.py

def _run_single(self, sim_id: int, persona_name: str) -> SimulationResult:
    # Создаём коллектор трассировок
    trace_collector = TraceCollector(simulation_id=sim_id)

    # Передаём в StateMachine
    sm = StateMachine(trace_collector=trace_collector)
    bot = SalesBot(self.bot_llm, state_machine=sm)

    # ... диалог ...

    # Получаем статистику
    trace_summary = trace_collector.get_summary()

    return SimulationResult(
        ...,
        trace_summary=trace_summary
    )
```

---

## Часть 8: РЕЗЮМЕ

### 8.1 Что имеем сейчас

- Rules — простые строки
- Категории интентов — hardcoded списки в коде
- Условная логика — костыли в state_machine.py
- last_intent дублируется в 4+ местах
- ObjectionFlowManager — отдельный класс
- Каждый новый случай = новый if

### 8.2 Что получим

- **Условия** — Python-функции с типами, IDE support, дебаг
- **Правила** — декларативный маппинг в config.py
- **IntentTracker** — единственный источник истории
- **Трассировка** — понятно что проверялось и почему
- **Валидация** — ошибки ловятся на CI, не в runtime
- **Каждый новый случай** = функция + строка в config

### 8.3 Сравнение подходов

| Аспект | JSON DSL | Python Conditions |
|--------|----------|-------------------|
| **Типизация** | Нет | Полная (mypy) |
| **IDE Support** | Нет | Autocomplete, go-to-def |
| **Debugging** | Логи | Breakpoints, stack traces |
| **Runtime errors** | Много | Минимум |
| **Читаемость условий** | `{"$and": [...]}` | `def has_data(ctx)` |
| **Документация** | Ручная | Автогенерация |
| **Тестирование** | Нужен контекст | Обычный pytest |

### 8.4 Решённые проблемы

| # | Проблема | Решение |
|---|----------|---------|
| 1 | JSON DSL без типов | Python-функции с @condition |
| 2 | Hardcoded OBJECTION_INTENTS | INTENT_CATEGORIES в config |
| 3 | Нет отслеживания серий | IntentTracker.streak_count() |
| 4 | Дублирование rules в SPIN | **SPIN_COMMON_RULES unpacking |
| 5 | 8+ if'ов в apply_rules() | RuleResolver |
| 6 | last_intent в 4+ местах | IntentTracker (единый) |
| 7 | ObjectionFlowManager | IntentTracker.objection_*() |
| 8 | Runtime ошибки условий | Валидация на старте, CI |
| 9 | Сложно дебажить | Breakpoints, stack traces |
| 10 | Нет документации | Автогенерация из docstrings |
