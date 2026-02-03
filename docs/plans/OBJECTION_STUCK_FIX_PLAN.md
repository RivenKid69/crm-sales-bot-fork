# План исправления Objection Stuck Bug (372 перехода в handle_objection)

> **Версия:** 1.0
> **Дата:** 25 Января 2026
> **Статус:** Implementation
> **Связанные баги:** State Loop Fix (#STATE_LOOP_FIX_PLAN.md)

---

## Содержание

1. [Диагностика проблемы](#1-диагностика-проблемы)
2. [Корневые причины](#2-корневые-причины)
3. [Архитектурное решение](#3-архитектурное-решение)
4. [Детальный план реализации](#4-детальный-план-реализации)
5. [Изменения по файлам](#5-изменения-по-файлам)
6. [Тестирование](#6-тестирование)
7. [Миграция и риски](#7-миграция-и-риски)

---

## 1. Диагностика проблемы

### 1.1 Симптомы

Из e2e симуляции (100+ диалогов):

| Метрика | Значение |
|---------|----------|
| **next_state="handle_objection"** | **372 раза** (самый частый переход) |
| Средних возражений на диалог | ~4-5 |
| Диалогов с 5+ возражениями | ~60% |
| Ложноположительных objection | ~30-40% |

### 1.2 Пример из логов

```
[14:32:15] WARNING - Objection detected in presentation

Диалог:
  Turn 5: Bot: "Какой у вас бюджет на автоматизацию?"
  Turn 6: Client: "бюджет пока не определён"  → intent: objection_price (НЕВЕРНО!)
  Turn 7: Bot: [переход в handle_objection]   → state: handle_objection
  Turn 8: Bot: "Понимаю, что цена важна..."   → НЕКОРРЕКТНЫЙ ОТВЕТ
  Turn 9: Client: "я про цену не говорил"     → intent: objection_think
  Turn 10: [застревание продолжается]
```

### 1.3 Цепочка ошибок

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  1. Клиент отвечает: "бюджет пока не определён"                             │
│                       │                                                      │
│                       ▼                                                      │
│  2. RootClassifier: Находит root "бюджет" → objection_price (90+ вариаций) │
│                       │                                                      │
│                       ▼                                                      │
│  3. TransitionResolverSource: presentation.transitions.objection_price      │
│                               → "handle_objection" (ПРЯМОЙ, без условия!)   │
│                       │                                                      │
│                       ▼                                                      │
│  4. StateMachine: Переход в handle_objection                                │
│                       │                                                      │
│                       ▼                                                      │
│  5. Бот отвечает на несуществующее возражение → ФРУСТРАЦИЯ клиента         │
│                       │                                                      │
│                       ▼                                                      │
│  6. Клиент выражает недовольство → новый objection_* → ЗАСТРЕВАНИЕ          │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Корневые причины

### 2.1 ROOT CAUSE #1: Over-classification objections (КРИТИЧЕСКИЙ)

**Локация:** `src/config.py:65-94`, `src/classifier/intents/patterns.py`

**Проблема:** Классификатор имеет 90+ keyword вариаций для каждого типа objection, многие из которых коллидируют с обычной речью:

| Keyword | Objection Type | Ложное срабатывание |
|---------|----------------|---------------------|
| "бюджет" | objection_price | "бюджет какой нужен?" (вопрос!) |
| "подумать" | objection_think | "дайте подумать над вариантами" (интерес!) |
| "занят" | objection_no_time | "сейчас занят, позвоните завтра" (callback_request!) |
| "нет времени" | objection_no_time | "нет времени на долгое внедрение" (вопрос о сроках!) |

**Почему это происходит:**

```python
# config.py INTENT_ROOTS - слишком широкие паттерны
"objection_price": [
    "дорог", "дешевл", "скидк", "бесплатн", "бюджет",  # ← "бюджет" слишком общий!
    "не потянем", "бюджет не позвол", "дороговато", "накладн"
]
```

### 2.2 ROOT CAUSE #2: Несогласованность YAML условий (СРЕДНИЙ)

**Локация:** `src/yaml_config/flows/_base/states.yaml:308-326`

**Проблема:** В `presentation` и `close` возражения переходят в handle_objection БЕЗ проверки `objection_limit_reached`:

```yaml
# presentation (строки 308-326) - БЕЗ УСЛОВИЯ!
objection_price: handle_objection
objection_competitor: handle_objection
# ...

# greeting и handle_objection (строки 152-224, 374-446) - С УСЛОВИЕМ!
objection_price:
  - when: objection_limit_reached
    then: soft_close
  - handle_objection
```

**Риск:** ObjectionGuardSource с Priority.CRITICAL должен override, но это создаёт неявную зависимость и edge cases.

### 2.3 ROOT CAUSE #3: Отсутствие контекстной валидации objection (СРЕДНИЙ)

**Проблема:** Классификатор не проверяет:
- Предыдущий вопрос бота (бот спросил про бюджет → ответ про бюджет НЕ возражение)
- Тон сообщения (вопросительный vs утвердительный)
- Наличие положительных сигналов в том же сообщении

### 2.4 ROOT CAUSE #4: Нет escape hatch для unclear в handle_objection (НИЗКИЙ)

**Локация:** `states.yaml:339-469`

**Проблема:** Если классификатор возвращает `unclear` или neutral в handle_objection → бот остаётся там через mixin rules.

---

## 3. Архитектурное решение

### 3.1 Принцип решения

**Добавить Objection Classification Refinement Layer** — слой контекстной валидации возражений, который:

1. Работает ПОСЛЕ основной классификации (как ClassificationRefinementLayer)
2. Проверяет контекст для objection_* интентов
3. Переклассифицирует ложноположительные objections
4. Соответствует архитектуре: YAML-driven, Blackboard-aware, SOLID

### 3.2 Архитектурная диаграмма

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        UnifiedClassifier                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌───────────────────┐                                                     │
│   │   User Message    │                                                     │
│   │   + Context       │                                                     │
│   └─────────┬─────────┘                                                     │
│             │                                                               │
│             ▼                                                               │
│   ┌───────────────────┐                                                     │
│   │  LLMClassifier    │  Primary classification                             │
│   │  (Qwen3 14B)      │  → intent, confidence, extracted_data               │
│   └─────────┬─────────┘                                                     │
│             │                                                               │
│             ▼                                                               │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │  ClassificationRefinementLayer (EXISTING - short answers)             │ │
│   └─────────┬─────────────────────────────────────────────────────────────┘ │
│             │                                                               │
│             ▼                                                               │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │        ObjectionRefinementLayer (NEW)                                 │ │
│   │                                                                        │ │
│   │  ┌─────────────────────────────────────────────────────────────────┐  │ │
│   │  │  Is intent objection_*?                                          │  │ │
│   │  └────────────────────────────────┬────────────────────────────────┘  │ │
│   │                                   │                                    │ │
│   │                          YES      │      NO                            │ │
│   │                      ┌────────────┴────────────┐                       │ │
│   │                      │                         │                       │ │
│   │                      ▼                         ▼                       │ │
│   │  ┌─────────────────────────────┐   ┌─────────────────────────────┐    │ │
│   │  │  Contextual Validation      │   │  Pass Through               │    │ │
│   │  │  • Bot asked about topic?   │   │  (return as-is)             │    │ │
│   │  │  • Has question markers?    │   │                             │    │ │
│   │  │  • Has positive signals?    │   └─────────────────────────────┘    │ │
│   │  │  • Confidence < threshold?  │                                      │ │
│   │  └────────────────┬────────────┘                                      │ │
│   │                   │                                                    │ │
│   │         Should refine?                                                 │ │
│   │              │                                                         │ │
│   │     YES      │      NO                                                 │ │
│   │  ┌───────────┴───────────┐                                             │ │
│   │  │                       │                                             │ │
│   │  ▼                       ▼                                             │ │
│   │  Reclassify to:          Keep objection_*                              │ │
│   │  • price_question                                                      │ │
│   │  • callback_request                                                    │ │
│   │  • question_*                                                          │ │
│   │  • info_provided                                                       │ │
│   │                                                                        │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 3.3 Компоненты решения

#### Компонент 1: ObjectionRefinementLayer

Контекстная валидация objection классификаций:

```python
@dataclass
class ObjectionRefinementContext:
    message: str
    intent: str
    confidence: float
    last_bot_message: Optional[str]
    last_action: Optional[str]
    state: str
    collected_data: dict
```

**Правила рефайнмента:**

| Условие | Действие |
|---------|----------|
| Бот спросил о теме возражения | objection → question/info_provided |
| Сообщение содержит "?" | objection → question_* |
| Confidence < 0.7 И есть положительные сигналы | objection → проверить альтернативы |
| "подумать над..." или "подумаю о..." | objection_think → interest/question |
| "позвоните/напишите позже" | objection_no_time → callback_request |

#### Компонент 2: Унификация YAML условий

Добавить `when: objection_limit_reached` во ВСЕ состояния:

```yaml
# Единый паттерн для ВСЕХ состояний
objection_price:
  - when: objection_limit_reached
    then: soft_close
  - handle_objection
```

#### Компонент 3: Escape Hatch для handle_objection

Добавить выход при повторных unclear:

```yaml
handle_objection:
  transitions:
    unclear:
      - when: unclear_consecutive_3x
        then: presentation  # Вернуться к презентации
      - handle_objection    # Продолжить работу с возражением
```

#### Компонент 4: Objection Cooldown

Предотвратить немедленные повторные переходы:

```yaml
# constants.yaml
objection_handling:
  cooldown_turns: 2  # Минимум 2 хода между возражениями
  same_type_cooldown: 3  # Минимум 3 хода между одинаковыми возражениями
```

### 3.4 Соответствие архитектурным принципам

| Принцип | Как соблюдается |
|---------|-----------------|
| **SRP** | ObjectionRefinementLayer — только валидация objections |
| **OCP** | Расширяемо через constants.yaml без изменения кода |
| **DIP** | Зависит от конфигурации, не от конкретных реализаций |
| **Configuration-Driven** | Правила рефайнмента в YAML |
| **Fail-Safe** | При ошибке — возвращает оригинальный результат |
| **Observable** | Логирует каждое решение, метрики |
| **Blackboard-Compatible** | Работает как Knowledge Source |

---

## 4. Детальный план реализации

### Фаза 1: ObjectionRefinementLayer

#### 4.1.1 Добавить конфигурацию в constants.yaml

**Файл:** `src/yaml_config/constants.yaml`

```yaml
# =============================================================================
# OBJECTION REFINEMENT CONFIGURATION (Single Source of Truth)
# =============================================================================
objection_refinement:
  # Включить рефайнмент objection классификаций
  enabled: true

  # Минимальная confidence для принятия objection без проверки
  min_confidence_to_accept: 0.85

  # Паттерны, указывающие что это НЕ возражение
  question_markers:
    - "?"
    - "какой"
    - "сколько"
    - "как"
    - "когда"
    - "где"
    - "почему"

  # Паттерны callback_request, маскирующиеся под objection_no_time
  callback_patterns:
    - "позвони"
    - "перезвони"
    - "напиши"
    - "свяж"
    - "завтра"
    - "потом"
    - "на неделе"
    - "через"

  # Паттерны интереса, маскирующиеся под objection_think
  interest_patterns:
    - "подумать над"
    - "подумаю о"
    - "обдумать"
    - "рассмотр"
    - "изучить"
    - "посмотреть"

  # Маппинг objection → альтернативный intent при рефайнменте
  refinement_mapping:
    objection_price:
      question_context: price_question
      info_context: info_provided
    objection_no_time:
      callback_context: callback_request
      schedule_context: consultation_request
    objection_think:
      interest_context: agreement
      question_context: question_features
    objection_competitor:
      question_context: comparison
      info_context: info_provided

  # Действия бота, после которых ответ на ту же тему НЕ возражение
  topic_alignment_actions:
    budget:
      - ask_about_budget
      - ask_pricing_context
      - discuss_pricing
    time:
      - ask_about_timeline
      - schedule_demo
      - ask_availability
    competitor:
      - ask_about_current_tools
      - compare_features

  # Cooldown настройки
  cooldown:
    min_turns_between_objections: 2
    min_turns_same_type: 3
```

#### 4.1.2 Создать ObjectionRefinementLayer

**Файл:** `src/classifier/objection_refinement.py`

```python
"""
Objection Classification Refinement Layer.

Context-aware validation and refinement of objection classifications.
Prevents false-positive objection detection by checking:
- Topic alignment with bot's last question
- Question markers in message
- Interest patterns vs real objections
- Confidence thresholds

Part of Phase 5: Objection Stuck Fix (OBJECTION_STUCK_FIX_PLAN.md)
"""

from dataclasses import dataclass
from typing import Optional, Set, Dict, List
import re
import logging

from src.yaml_config.constants import get_objection_refinement_config, OBJECTION_INTENTS

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ObjectionRefinementContext:
    """Immutable context for objection refinement."""
    message: str
    intent: str
    confidence: float
    last_bot_message: Optional[str]
    last_action: Optional[str]
    state: str
    turn_number: int
    last_objection_turn: Optional[int]
    last_objection_type: Optional[str]


@dataclass
class RefinementResult:
    """Result of objection refinement."""
    intent: str
    confidence: float
    refined: bool
    original_intent: Optional[str] = None
    refinement_reason: Optional[str] = None


class ObjectionRefinementLayer:
    """
    Refines objection classifications using contextual signals.

    Architecture:
    - Runs AFTER ClassificationRefinementLayer
    - Uses objection_refinement config from constants.yaml
    - Only refines objection_* intents
    - Falls back to original result on any error

    Design Principles:
    - Configuration-Driven: All rules from YAML
    - Fail-Safe: Never crashes, returns original on error
    - Observable: Logs all refinement decisions
    - SOLID: Single responsibility - objection validation only
    """

    def __init__(self):
        self._config = get_objection_refinement_config()
        self._enabled = self._config.get("enabled", True)
        self._min_confidence = self._config.get("min_confidence_to_accept", 0.85)
        self._question_markers = set(self._config.get("question_markers", []))
        self._callback_patterns = self._config.get("callback_patterns", [])
        self._interest_patterns = self._config.get("interest_patterns", [])
        self._refinement_mapping = self._config.get("refinement_mapping", {})
        self._topic_actions = self._config.get("topic_alignment_actions", {})
        self._cooldown = self._config.get("cooldown", {})

        # Compile patterns for efficiency
        self._callback_regex = self._compile_patterns(self._callback_patterns)
        self._interest_regex = self._compile_patterns(self._interest_patterns)

        # Stats
        self._refinements_total = 0
        self._refinements_by_type: Dict[str, int] = {}

    @staticmethod
    def _compile_patterns(patterns: List[str]) -> re.Pattern:
        """Compile list of patterns into single regex."""
        if not patterns:
            return re.compile(r"^$")  # Never matches
        escaped = [re.escape(p) for p in patterns]
        return re.compile("|".join(escaped), re.IGNORECASE)

    def should_refine(self, ctx: ObjectionRefinementContext) -> bool:
        """
        Determine if classification should be refined.

        Returns True if:
        1. Layer is enabled
        2. Intent is objection_*
        3. At least one refinement signal is present
        """
        if not self._enabled:
            return False

        if ctx.intent not in OBJECTION_INTENTS:
            return False

        # High confidence objections with no context issues → accept as-is
        if ctx.confidence >= self._min_confidence:
            if not self._has_question_markers(ctx.message):
                if not self._is_topic_aligned(ctx):
                    return False

        return True

    def refine(
        self,
        message: str,
        llm_result: dict,
        ctx: ObjectionRefinementContext
    ) -> dict:
        """
        Refine objection classification using context.

        Args:
            message: User message
            llm_result: Original classification result
            ctx: Refinement context

        Returns:
            Refined result (or original if refinement not applicable)
        """
        try:
            if not self.should_refine(ctx):
                return llm_result

            # Check refinement signals
            result = self._apply_refinement_rules(ctx)

            if result.refined:
                self._refinements_total += 1
                self._refinements_by_type[ctx.intent] = (
                    self._refinements_by_type.get(ctx.intent, 0) + 1
                )

                logger.info(
                    "Objection refined",
                    extra={
                        "original_intent": ctx.intent,
                        "refined_intent": result.intent,
                        "reason": result.refinement_reason,
                        "message": message[:50],
                        "state": ctx.state
                    }
                )

                # Create refined result
                refined_result = llm_result.copy()
                refined_result["intent"] = result.intent
                refined_result["confidence"] = result.confidence
                refined_result["refined"] = True
                refined_result["original_intent"] = ctx.intent
                refined_result["refinement_reason"] = result.refinement_reason
                refined_result["refinement_layer"] = "objection"

                return refined_result

            return llm_result

        except Exception as e:
            logger.error(f"Objection refinement error: {e}", exc_info=True)
            return llm_result

    def _apply_refinement_rules(self, ctx: ObjectionRefinementContext) -> RefinementResult:
        """Apply refinement rules in priority order."""

        # Rule 1: Topic alignment (bot asked about this topic)
        if self._is_topic_aligned(ctx):
            alternative = self._get_topic_alternative(ctx)
            if alternative:
                return RefinementResult(
                    intent=alternative,
                    confidence=0.75,
                    refined=True,
                    original_intent=ctx.intent,
                    refinement_reason="topic_alignment"
                )

        # Rule 2: Question markers
        if self._has_question_markers(ctx.message):
            alternative = self._get_question_alternative(ctx)
            if alternative:
                return RefinementResult(
                    intent=alternative,
                    confidence=0.7,
                    refined=True,
                    original_intent=ctx.intent,
                    refinement_reason="question_markers"
                )

        # Rule 3: Callback patterns (objection_no_time → callback_request)
        if ctx.intent == "objection_no_time":
            if self._callback_regex.search(ctx.message):
                return RefinementResult(
                    intent="callback_request",
                    confidence=0.8,
                    refined=True,
                    original_intent=ctx.intent,
                    refinement_reason="callback_pattern"
                )

        # Rule 4: Interest patterns (objection_think → agreement/question)
        if ctx.intent == "objection_think":
            if self._interest_regex.search(ctx.message):
                return RefinementResult(
                    intent="question_features",
                    confidence=0.7,
                    refined=True,
                    original_intent=ctx.intent,
                    refinement_reason="interest_pattern"
                )

        # Rule 5: Cooldown violation
        if self._violates_cooldown(ctx):
            # Don't refine, but log
            logger.debug(
                "Objection within cooldown, accepting anyway",
                extra={"intent": ctx.intent, "turn": ctx.turn_number}
            )

        # No refinement needed
        return RefinementResult(
            intent=ctx.intent,
            confidence=ctx.confidence,
            refined=False
        )

    def _has_question_markers(self, message: str) -> bool:
        """Check if message contains question markers."""
        text = message.lower()

        # Direct question mark
        if "?" in message:
            return True

        # Question words
        for marker in self._question_markers:
            if marker in text:
                return True

        return False

    def _is_topic_aligned(self, ctx: ObjectionRefinementContext) -> bool:
        """
        Check if objection topic aligns with bot's last question.

        If bot asked about budget and user mentions budget,
        it's likely an answer, not an objection.
        """
        if not ctx.last_action:
            return False

        # Get objection topic
        topic = self._get_objection_topic(ctx.intent)
        if not topic:
            return False

        # Check if last action was about this topic
        topic_actions = self._topic_actions.get(topic, [])
        return ctx.last_action in topic_actions

    def _get_objection_topic(self, intent: str) -> Optional[str]:
        """Map objection intent to topic."""
        topic_map = {
            "objection_price": "budget",
            "objection_no_time": "time",
            "objection_competitor": "competitor",
        }
        return topic_map.get(intent)

    def _get_topic_alternative(self, ctx: ObjectionRefinementContext) -> Optional[str]:
        """Get alternative intent based on topic alignment."""
        mapping = self._refinement_mapping.get(ctx.intent, {})
        return mapping.get("info_context", "info_provided")

    def _get_question_alternative(self, ctx: ObjectionRefinementContext) -> Optional[str]:
        """Get alternative intent for question context."""
        mapping = self._refinement_mapping.get(ctx.intent, {})
        return mapping.get("question_context")

    def _violates_cooldown(self, ctx: ObjectionRefinementContext) -> bool:
        """Check if objection violates cooldown rules."""
        if ctx.last_objection_turn is None:
            return False

        turns_since = ctx.turn_number - ctx.last_objection_turn
        min_turns = self._cooldown.get("min_turns_between_objections", 2)

        if turns_since < min_turns:
            return True

        # Same type cooldown
        if ctx.last_objection_type == ctx.intent:
            min_same = self._cooldown.get("min_turns_same_type", 3)
            if turns_since < min_same:
                return True

        return False

    def get_stats(self) -> dict:
        """Get refinement statistics."""
        return {
            "refinements_total": self._refinements_total,
            "refinements_by_type": dict(self._refinements_by_type),
        }
```

#### 4.1.3 Добавить функцию доступа к конфигурации

**Файл:** `src/yaml_config/constants.py`

Добавить:

```python
def get_objection_refinement_config() -> dict:
    """
    Get objection_refinement config from constants.yaml.

    Returns:
        Dict with objection refinement configuration
    """
    return _CONSTANTS.get("objection_refinement", {})
```

### Фаза 2: Интеграция в UnifiedClassifier

#### 4.2.1 Обновить UnifiedClassifier

**Файл:** `src/classifier/unified.py`

```python
from .refinement import ClassificationRefinementLayer, RefinementContext
from .objection_refinement import ObjectionRefinementLayer, ObjectionRefinementContext

class UnifiedClassifier:
    def __init__(self):
        # ... existing init ...
        self._refinement_layer = ClassificationRefinementLayer()
        self._objection_refinement_layer = ObjectionRefinementLayer()

    def classify(self, message: str, context: dict = None) -> dict:
        context = context or {}

        # Step 1: Primary classification
        if flags.llm_classifier:
            result = self._llm_classifier.classify(message, context)
        else:
            result = self._hybrid_classifier.classify(message, context)

        # Step 2: Short answer refinement (EXISTING)
        if flags.classification_refinement:
            refinement_ctx = RefinementContext(
                message=message,
                spin_phase=context.get("spin_phase"),
                state=context.get("state"),
                last_action=context.get("last_action"),
                last_intent=context.get("last_intent"),
            )
            result = self._refinement_layer.refine(message, result, refinement_ctx)

        # Step 3: Objection refinement (NEW)
        if flags.objection_refinement:  # New feature flag
            objection_ctx = ObjectionRefinementContext(
                message=message,
                intent=result.get("intent", "unclear"),
                confidence=result.get("confidence", 0.0),
                last_bot_message=context.get("last_bot_message"),
                last_action=context.get("last_action"),
                state=context.get("state", "greeting"),
                turn_number=context.get("turn_number", 0),
                last_objection_turn=context.get("last_objection_turn"),
                last_objection_type=context.get("last_objection_type"),
            )
            result = self._objection_refinement_layer.refine(
                message, result, objection_ctx
            )

        return result
```

### Фаза 3: Унификация YAML условий

#### 4.3.1 Обновить states.yaml для presentation

**Файл:** `src/yaml_config/flows/_base/states.yaml`

Заменить строки 308-326:

```yaml
# Презентация
presentation:
  extends: _base_phase
  goal: "Показать ценность продукта"
  # ... existing config ...
  transitions:
    # ... existing transitions ...

    # Все 18 возражений → handle_objection (С ПРОВЕРКОЙ ЛИМИТА!)
    objection_price:
      - when: objection_limit_reached
        then: soft_close
      - handle_objection
    objection_competitor:
      - when: objection_limit_reached
        then: soft_close
      - handle_objection
    objection_no_time:
      - when: objection_limit_reached
        then: soft_close
      - handle_objection
    objection_think:
      - when: objection_limit_reached
        then: soft_close
      - handle_objection
    objection_timing:
      - when: objection_limit_reached
        then: soft_close
      - handle_objection
    objection_complexity:
      - when: objection_limit_reached
        then: soft_close
      - handle_objection
    objection_trust:
      - when: objection_limit_reached
        then: soft_close
      - handle_objection
    objection_no_need:
      - when: objection_limit_reached
        then: soft_close
      - handle_objection
    objection_risk:
      - when: objection_limit_reached
        then: soft_close
      - handle_objection
    objection_team_resistance:
      - when: objection_limit_reached
        then: soft_close
      - handle_objection
    objection_security:
      - when: objection_limit_reached
        then: soft_close
      - handle_objection
    objection_bad_experience:
      - when: objection_limit_reached
        then: soft_close
      - handle_objection
    objection_priority:
      - when: objection_limit_reached
        then: soft_close
      - handle_objection
    objection_scale:
      - when: objection_limit_reached
        then: soft_close
      - handle_objection
    objection_change_management:
      - when: objection_limit_reached
        then: soft_close
      - handle_objection
    objection_contract_bound:
      - when: objection_limit_reached
        then: soft_close
      - handle_objection
    objection_company_policy:
      - when: objection_limit_reached
        then: soft_close
      - handle_objection
    objection_roi_doubt:
      - when: objection_limit_reached
        then: soft_close
      - handle_objection
```

#### 4.3.2 Обновить states.yaml для close

Аналогичное изменение для close state (строки 536-554).

### Фаза 4: Escape Hatch для handle_objection

#### 4.4.1 Добавить условие unclear_consecutive_3x

**Файл:** `src/conditions/state_machine/conditions.py`

```python
@sm_condition(
    "unclear_consecutive_3x",
    description="Check if unclear intent repeated 3+ times consecutively",
    category="intent"
)
def unclear_consecutive_3x(ctx: EvaluatorContext) -> bool:
    """
    Returns True if unclear has been returned 3+ times in a row.

    This triggers escape from handle_objection to presentation.
    """
    return ctx.get_intent_streak("unclear") >= 3
```

#### 4.4.2 Обновить handle_objection transitions

**Файл:** `src/yaml_config/flows/_base/states.yaml`

Добавить в handle_objection transitions:

```yaml
handle_objection:
  # ... existing config ...
  transitions:
    # ... existing transitions ...

    # NEW: Escape hatch for repeated unclear
    unclear:
      - when: unclear_consecutive_3x
        then: presentation
      - handle_objection  # Default: stay and clarify

    # NEW: Escape on repeated same objection (user is frustrated)
    objection_price:
      - when: objection_limit_reached
        then: soft_close
      - when: objection_repeated
        then: soft_close  # Same objection 2+ times = give up
      - handle_objection
    # ... repeat for other objections
```

#### 4.4.3 Добавить условие objection_repeated

**Файл:** `src/conditions/state_machine/conditions.py`

```python
@sm_condition(
    "objection_repeated",
    description="Check if same objection type repeated 2+ times",
    category="intent"
)
def objection_repeated_2x(ctx: EvaluatorContext) -> bool:
    """
    Returns True if same objection has been repeated 2+ times.

    If user repeats same objection, they're not convinced.
    Better to soft_close than continue pushing.
    """
    if not ctx.current_intent:
        return False
    return ctx.get_intent_streak(ctx.current_intent) >= 2
```

### Фаза 5: Feature Flags и метрики

#### 4.5.1 Добавить feature flag

**Файл:** `src/feature_flags.py`

```python
DEFAULTS = {
    # ... existing flags ...

    # Objection classification refinement
    "objection_refinement": True,
}
```

---

## 5. Изменения по файлам

### 5.1 Новые файлы

| Файл | Описание |
|------|----------|
| `src/classifier/objection_refinement.py` | ObjectionRefinementLayer |
| `tests/test_objection_refinement.py` | Unit тесты для objection refinement |
| `tests/test_objection_stuck_regression.py` | Регрессионные тесты |
| `docs/plans/OBJECTION_STUCK_FIX_PLAN.md` | Этот документ |

### 5.2 Изменяемые файлы

| Файл | Изменения |
|------|-----------|
| `src/yaml_config/constants.yaml` | Секция `objection_refinement` |
| `src/yaml_config/constants.py` | Функция `get_objection_refinement_config()` |
| `src/classifier/unified.py` | Интеграция ObjectionRefinementLayer |
| `src/yaml_config/flows/_base/states.yaml` | Унификация условий, escape hatch |
| `src/conditions/state_machine/conditions.py` | `unclear_consecutive_3x`, `objection_repeated` |
| `src/feature_flags.py` | Флаг `objection_refinement` |

### 5.3 Порядок изменений (dependency order)

```
1. docs/plans/OBJECTION_STUCK_FIX_PLAN.md     # Документация (этот файл)
2. src/yaml_config/constants.yaml              # objection_refinement config
3. src/yaml_config/constants.py                # get_objection_refinement_config()
4. src/classifier/objection_refinement.py      # ObjectionRefinementLayer (NEW)
5. src/feature_flags.py                        # objection_refinement flag
6. src/classifier/unified.py                   # Integration
7. src/conditions/state_machine/conditions.py  # New conditions
8. src/yaml_config/flows/_base/states.yaml     # YAML updates (last!)
9. tests/test_objection_refinement.py          # Unit tests
10. tests/test_objection_stuck_regression.py   # Regression tests
```

---

## 6. Тестирование

### 6.1 Unit тесты

**Файл:** `tests/test_objection_refinement.py`

```python
import pytest
from src.classifier.objection_refinement import (
    ObjectionRefinementLayer,
    ObjectionRefinementContext,
)


class TestObjectionRefinement:
    """Tests for ObjectionRefinementLayer."""

    @pytest.fixture
    def layer(self):
        return ObjectionRefinementLayer()

    @pytest.fixture
    def price_objection_context(self):
        return ObjectionRefinementContext(
            message="бюджет пока не определён",
            intent="objection_price",
            confidence=0.75,
            last_bot_message="Какой у вас бюджет на автоматизацию?",
            last_action="ask_about_budget",
            state="presentation",
            turn_number=5,
            last_objection_turn=None,
            last_objection_type=None,
        )

    # =========================================================================
    # should_refine() tests
    # =========================================================================

    def test_should_refine_low_confidence_objection(self, layer, price_objection_context):
        """Low confidence objection with context → should refine."""
        assert layer.should_refine(price_objection_context)

    def test_should_not_refine_high_confidence(self, layer):
        """High confidence objection without question markers → should not refine."""
        ctx = ObjectionRefinementContext(
            message="это слишком дорого для нас",
            intent="objection_price",
            confidence=0.95,
            last_bot_message="Вот наши тарифы",
            last_action="show_pricing",
            state="presentation",
            turn_number=5,
            last_objection_turn=None,
            last_objection_type=None,
        )
        assert not layer.should_refine(ctx)

    def test_should_not_refine_non_objection(self, layer):
        """Non-objection intent → should not refine."""
        ctx = ObjectionRefinementContext(
            message="расскажите подробнее",
            intent="question_features",
            confidence=0.8,
            last_bot_message=None,
            last_action=None,
            state="presentation",
            turn_number=5,
            last_objection_turn=None,
            last_objection_type=None,
        )
        assert not layer.should_refine(ctx)

    # =========================================================================
    # refine() tests - Topic alignment
    # =========================================================================

    def test_refine_topic_aligned_price(self, layer, price_objection_context):
        """Bot asked about budget + user mentions budget → info_provided."""
        llm_result = {"intent": "objection_price", "confidence": 0.75}

        refined = layer.refine(
            price_objection_context.message,
            llm_result,
            price_objection_context
        )

        assert refined["refined"] is True
        assert refined["intent"] == "info_provided"
        assert refined["refinement_reason"] == "topic_alignment"

    # =========================================================================
    # refine() tests - Question markers
    # =========================================================================

    def test_refine_question_marker(self, layer):
        """Message with ? → question intent."""
        ctx = ObjectionRefinementContext(
            message="бюджет какой нужен?",
            intent="objection_price",
            confidence=0.7,
            last_bot_message="Расскажу о тарифах",
            last_action="present_features",
            state="presentation",
            turn_number=5,
            last_objection_turn=None,
            last_objection_type=None,
        )
        llm_result = {"intent": "objection_price", "confidence": 0.7}

        refined = layer.refine(ctx.message, llm_result, ctx)

        assert refined["refined"] is True
        assert refined["intent"] == "price_question"

    # =========================================================================
    # refine() tests - Callback patterns
    # =========================================================================

    def test_refine_callback_pattern(self, layer):
        """'позвоните завтра' → callback_request, not objection_no_time."""
        ctx = ObjectionRefinementContext(
            message="сейчас занят, позвоните завтра",
            intent="objection_no_time",
            confidence=0.8,
            last_bot_message="Можем обсудить?",
            last_action="ask_availability",
            state="close",
            turn_number=8,
            last_objection_turn=None,
            last_objection_type=None,
        )
        llm_result = {"intent": "objection_no_time", "confidence": 0.8}

        refined = layer.refine(ctx.message, llm_result, ctx)

        assert refined["refined"] is True
        assert refined["intent"] == "callback_request"
        assert refined["refinement_reason"] == "callback_pattern"

    # =========================================================================
    # refine() tests - Interest patterns
    # =========================================================================

    def test_refine_interest_pattern(self, layer):
        """'подумать над предложением' → interest, not objection_think."""
        ctx = ObjectionRefinementContext(
            message="хочу подумать над вашим предложением, пришлите детали",
            intent="objection_think",
            confidence=0.75,
            last_bot_message="Что скажете?",
            last_action="ask_feedback",
            state="presentation",
            turn_number=7,
            last_objection_turn=None,
            last_objection_type=None,
        )
        llm_result = {"intent": "objection_think", "confidence": 0.75}

        refined = layer.refine(ctx.message, llm_result, ctx)

        assert refined["refined"] is True
        assert refined["intent"] == "question_features"

    # =========================================================================
    # refine() tests - No refinement needed
    # =========================================================================

    def test_no_refine_genuine_objection(self, layer):
        """Genuine objection without refinement signals → keep as-is."""
        ctx = ObjectionRefinementContext(
            message="это слишком дорого, у нас нет такого бюджета",
            intent="objection_price",
            confidence=0.9,
            last_bot_message="Вот стоимость",
            last_action="show_pricing",
            state="presentation",
            turn_number=6,
            last_objection_turn=None,
            last_objection_type=None,
        )
        llm_result = {"intent": "objection_price", "confidence": 0.9}

        refined = layer.refine(ctx.message, llm_result, ctx)

        assert refined.get("refined", False) is False
        assert refined["intent"] == "objection_price"
```

### 6.2 Интеграционные тесты

**Файл:** `tests/test_objection_stuck_regression.py`

```python
import pytest
from src.bot import SalesBot


class TestObjectionStuckRegression:
    """Regression tests for objection stuck bug fix."""

    @pytest.fixture
    def bot(self):
        return SalesBot()

    @pytest.mark.parametrize("message,should_not_be_objection", [
        ("бюджет какой нужен?", True),
        ("сколько стоит?", True),
        ("позвоните завтра", True),
        ("хочу подумать над предложением", True),
        ("бюджет пока не определён", True),  # After budget question
    ])
    def test_false_positive_objections_refined(self, bot, message, should_not_be_objection):
        """Messages that look like objections but aren't should be refined."""
        # Setup: get to presentation state
        bot.process("привет")
        bot.process("10 человек")
        bot.process("теряем клиентов")

        # Ask about budget (sets context)
        bot.process("да, интересно")

        # Now test
        result = bot.process(message)

        # Should NOT transition to handle_objection
        if should_not_be_objection:
            assert bot.state != "handle_objection", f"False positive: {message}"

    def test_genuine_objection_still_works(self, bot):
        """Genuine objections should still trigger handle_objection."""
        bot.process("привет")
        bot.process("это слишком дорого для нас, не потянем")

        assert bot.state == "handle_objection"

    def test_objection_limit_works(self, bot):
        """After 5 total objections, should go to soft_close."""
        bot.process("привет")

        # 5 objections
        for i in range(5):
            bot.process("это дорого")

        assert bot.state == "soft_close"

    def test_escape_hatch_on_unclear(self, bot):
        """3 unclear in handle_objection → escape to presentation."""
        bot.process("привет")
        bot.process("это дорого")  # → handle_objection

        # 3 unclear responses
        bot.process("ммм")
        bot.process("эээ")
        bot.process("...")

        # Should escape to presentation
        assert bot.state in ("presentation", "soft_close")
```

### 6.3 E2E тесты с симуляцией

```bash
# Запуск полной симуляции для проверки fix
python -m src.simulator -n 100 --report objection_fix_test.json

# Проверка ключевых метрик
python -c "
import json
with open('objection_fix_test.json') as f:
    data = json.load(f)
print(f'handle_objection transitions: {data[\"transitions\"][\"handle_objection\"]}')
print(f'False positive rate: {data[\"refinement_stats\"][\"objection_refinement_rate\"]}')
"

# Ожидается:
# - handle_objection transitions: < 200 (было 372)
# - refinement_rate: 20-40% от всех objection классификаций
```

---

## 7. Миграция и риски

### 7.1 Риски

| Риск | Вероятность | Влияние | Митигация |
|------|-------------|---------|-----------|
| Refinement пропускает реальные objections | Средняя | Высокое | Консервативные thresholds (0.85), только при явных сигналах |
| Изменение поведения в production | Средняя | Среднее | Feature flag, постепенный rollout |
| YAML изменения ломают существующие flows | Низкая | Высокое | Тесты конфигурации, backup |
| Cooldown блокирует реальные повторные objections | Низкая | Среднее | Короткий cooldown (2 turns), мониторинг |

### 7.2 План rollout

```
1. Deploy с feature flag OFF
2. A/B test на 10% трафика:
   - Control: objection_refinement=false
   - Treatment: objection_refinement=true
3. Мониторинг метрик (7 дней):
   - objection_rate (должен уменьшиться)
   - false_positive_objection_rate (должен уменьшиться)
   - conversation_success_rate (должен увеличиться)
   - missed_objection_rate (не должен увеличиться!)
4. При положительных результатах → 50% → 100%
5. Удалить feature flag после стабилизации (2 недели)
```

### 7.3 Мониторинг

```yaml
metrics:
  # Уменьшение objection переходов
  - name: handle_objection_transition_rate
    query: sum(transitions_to_handle_objection) / sum(total_transitions)
    expected: < 0.15  # Было ~0.30

  # Refinement применяется
  - name: objection_refinement_rate
    query: sum(objection_refined) / sum(objection_classified)
    expected: 0.20-0.40  # 20-40% objections refined

  # Не пропускаем реальные objections
  - name: missed_objection_rate
    query: sum(real_objection_not_detected) / sum(real_objections)
    expected: < 0.05  # < 5%

alerts:
  - name: ObjectionRefinementTooAggressive
    condition: missed_objection_rate > 0.10
    severity: critical
    action: "Disable objection_refinement flag immediately"
```

### 7.4 Rollback план

```bash
# Если что-то пошло не так:
# 1. Выключить feature flag
export FF_OBJECTION_REFINEMENT=false

# 2. Откатить YAML изменения (если были)
git checkout HEAD~1 -- src/yaml_config/flows/_base/states.yaml

# 3. Перезапустить сервис
systemctl restart sales-bot

# 4. Проверить метрики вернулись к baseline
```

---

## Appendix A: Альтернативные решения (отвергнутые)

### A.1 Ужесточить keyword matching

**Предложение:** Удалить широкие keywords типа "бюджет" из objection_price.

**Почему отвергнуто:**
- Может пропустить реальные objections
- Требует ручного аудита 90+ keywords
- Не решает контекстную проблему

### A.2 Переобучить LLM на контекстных примерах

**Предложение:** Fine-tune модель на примерах с контекстом.

**Почему отвергнуто:**
- Долго и дорого
- Требует качественных данных
- Refinement layer — более детерминированный

### A.3 Полностью убрать objection detection

**Предложение:** Убрать автоматическое определение возражений.

**Почему отвергнуто:**
- Потеря ключевой функциональности
- Не соответствует бизнес-требованиям

---

*Документ создан: 25 Января 2026*
