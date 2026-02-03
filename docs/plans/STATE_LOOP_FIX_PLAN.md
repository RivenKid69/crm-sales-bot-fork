# План исправления State Loop Bug (52 случая)

> **Версия:** 1.0
> **Дата:** 23 Января 2026
> **Статус:** Proposal

---

## Содержание

1. [Диагностика проблемы](#1-диагностика-проблемы)
2. [Корневая причина](#2-корневая-причина)
3. [Архитектурное решение](#3-архитектурное-решение)
4. [Детальный план реализации](#4-детальный-план-реализации)
5. [Изменения по файлам](#5-изменения-по-файлам)
6. [Тестирование](#6-тестирование)
7. [Миграция и риски](#7-миграция-и-риски)

---

## 1. Диагностика проблемы

### 1.1 Симптомы

Из e2e симуляции (100 диалогов):

| Проблема | Количество случаев |
|----------|-------------------|
| **State Loop — бот застревает в состояниях** | **52** |
| greeting | 6 |
| handle_objection | 7 |
| close | 6 |
| bant_* (budget/authority/need) | 5 |
| meddic_* | 3 |
| Другие | 25 |

### 1.2 Пример из логов

```
[13:26:21] WARNING - State loop detected [state=greeting, count=4]

Диалог:
  Turn 1: Bot: "Сколько человек в вашей команде?"
  Turn 2: Client: "1"           → intent: greeting (НЕВЕРНО!)
  Turn 3: Bot: "Здравствуйте!"  → state: greeting (остаётся)
  Turn 4: Client: "первое"      → intent: greeting (НЕВЕРНО!)
  Turn 5: Bot: "Чем могу помочь?" → state: greeting (застревание)
```

### 1.3 Цепочка ошибок

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  1. Клиент отвечает: "1" или "первое"                                       │
│                       │                                                      │
│                       ▼                                                      │
│  2. LLMClassifier: Короткое сообщение без контекста                         │
│                    → intent: "greeting" (confidence: 0.95)                  │
│                       │                                                      │
│                       ▼                                                      │
│  3. TransitionResolverSource: intent="greeting" NOT IN transitions          │
│                               → Ничего не предлагает                        │
│                       │                                                      │
│                       ▼                                                      │
│  4. ConflictResolver: Нет proposals → next_state = current_state            │
│                       │                                                      │
│                       ▼                                                      │
│  5. StateMachine: Остаётся в greeting → LOOP DETECTED                       │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Корневая причина

### 2.1 Основная проблема

**LLM классификатор не использует контекстную логику для коротких ответов**, которая уже реализована в системе:

1. В `constants.yaml` (строки 62-80) есть `short_answer_classification`:
   ```yaml
   short_answer_classification:
     situation:
       positive_intent: situation_provided
       positive_confidence: 0.7
     problem:
       positive_intent: problem_revealed
       # ...
   ```

2. `HybridClassifier` использует эту логику в `_classify_short_answer()` (строки 340-529)

3. **НО** `LLMClassifier` — основной классификатор — **НЕ использует** эту логику!

### 2.2 Почему это происходит

```python
# LLMClassifier.classify() - текущая реализация
def classify(self, message: str, context: dict = None):
    # Просто отправляет в LLM без контекстной логики
    result = self._llm.generate_structured(prompt, ClassificationResult)
    return result
```

LLM получает сообщение "1" без понимания что:
- Бот только что спросил "сколько сотрудников?"
- Текущая фаза: `situation`
- Ожидается: информация о компании

### 2.3 Вторичная проблема

В состоянии `greeting` для intent `greeting` нет transition:

```yaml
# states.yaml
greeting:
  rules:
    greeting: greet_back  # Только rule, НЕ transition!
  transitions:
    info_provided: "{{entry_state}}"  # Есть для info_provided
    # НО НЕТ для greeting!
```

Это нормальный дизайн (не стоит переходить при приветствии), но в сочетании с неправильной классификацией → застревание.

---

## 3. Архитектурное решение

### 3.1 Принцип решения

**Добавить Context-Aware Classification Refinement Layer** — слой уточнения классификации, который:

1. Работает ПОСЛЕ основной LLM классификации
2. Использует существующую конфигурацию `short_answer_classification` из `constants.yaml`
3. Переклассифицирует ТОЛЬКО когда есть сильные контекстные сигналы
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
│   │            ClassificationRefinementLayer (NEW)                        │ │
│   │                                                                        │ │
│   │  ┌─────────────────────────────────────────────────────────────────┐  │ │
│   │  │  Should Refine?                                                  │  │ │
│   │  │  • is_short_message (< 5 words OR < 20 chars)                   │  │ │
│   │  │  • LLM returned low-signal intent (greeting, unclear, small_talk)│  │ │
│   │  │  • Has SPIN phase context OR awaiting_data action               │  │ │
│   │  └────────────────────────────────┬────────────────────────────────┘  │ │
│   │                                   │                                    │ │
│   │                          YES      │      NO                            │ │
│   │                      ┌────────────┴────────────┐                       │ │
│   │                      │                         │                       │ │
│   │                      ▼                         ▼                       │ │
│   │  ┌─────────────────────────────┐   ┌─────────────────────────────┐    │ │
│   │  │  Contextual Refinement      │   │  Pass Through               │    │ │
│   │  │  (short_answer_classification│   │  (return LLM result)        │    │ │
│   │  │   from constants.yaml)      │   │                             │    │ │
│   │  └─────────────────────────────┘   └─────────────────────────────┘    │ │
│   │                                                                        │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 3.3 Соответствие архитектурным принципам

| Принцип | Как соблюдается |
|---------|-----------------|
| **SRP** | Refinement Layer имеет одну ответственность — контекстное уточнение |
| **OCP** | Расширяемо через `constants.yaml` без изменения кода |
| **DIP** | Зависит от конфигурации, не от конкретных реализаций |
| **Configuration-Driven** | Использует существующую конфигурацию `short_answer_classification` |
| **Fail-Safe** | При ошибке refinement — возвращает оригинальный результат LLM |
| **Observable** | Логирует каждое решение о refinement |

---

## 4. Детальный план реализации

### Фаза 1: ClassificationRefinementLayer

#### 4.1.1 Создать новый модуль refinement

**Файл:** `src/classifier/refinement.py`

```python
"""
Classification Refinement Layer.

Context-aware refinement of LLM classification results.
Uses short_answer_classification from constants.yaml.
"""

from dataclasses import dataclass
from typing import Optional, Set
import logging

from src.yaml_config.constants import get_short_answer_config

logger = logging.getLogger(__name__)


@dataclass
class RefinementContext:
    """Context for classification refinement."""
    message: str
    spin_phase: Optional[str]
    state: Optional[str]
    last_action: Optional[str]
    last_intent: Optional[str]


class ClassificationRefinementLayer:
    """
    Refines LLM classification results using contextual signals.

    Architecture:
    - Runs AFTER LLMClassifier
    - Uses short_answer_classification from constants.yaml
    - Only refines when strong contextual signals present
    - Falls back to original result on any error
    """

    # Intents that may need refinement (low-signal in short message context)
    LOW_SIGNAL_INTENTS: Set[str] = {
        "greeting",
        "unclear",
        "small_talk",
        "gratitude",
    }

    # Actions that indicate we're awaiting data
    AWAITING_DATA_ACTIONS: Set[str] = {
        "ask_about_company",
        "ask_about_problem",
        "ask_about_impact",
        "ask_about_outcome",
        "ask_for_clarification",
        "transition_to_spin_situation",
        "transition_to_spin_problem",
        "transition_to_spin_implication",
        "transition_to_spin_need_payoff",
    }

    # Short message thresholds
    MAX_SHORT_WORDS = 5
    MAX_SHORT_CHARS = 20

    def __init__(self):
        self._short_answer_config = get_short_answer_config()

    def should_refine(
        self,
        message: str,
        llm_intent: str,
        context: RefinementContext
    ) -> bool:
        """
        Determine if classification should be refined.

        Returns True if:
        1. Message is short
        2. LLM returned low-signal intent
        3. We have contextual signals (SPIN phase or awaiting_data action)
        """
        # Check 1: Is message short?
        if not self._is_short_message(message):
            return False

        # Check 2: Did LLM return low-signal intent?
        if llm_intent not in self.LOW_SIGNAL_INTENTS:
            return False

        # Check 3: Do we have context?
        has_phase_context = context.spin_phase is not None
        has_action_context = context.last_action in self.AWAITING_DATA_ACTIONS

        return has_phase_context or has_action_context

    def refine(
        self,
        message: str,
        llm_result: dict,
        context: RefinementContext
    ) -> dict:
        """
        Refine classification result using context.

        Args:
            message: User message
            llm_result: Original LLM classification result
            context: Refinement context

        Returns:
            Refined result (or original if refinement not applicable)
        """
        llm_intent = llm_result.get("intent", "unclear")

        if not self.should_refine(message, llm_intent, context):
            return llm_result

        # Get refined intent from short_answer_classification
        refined = self._get_refined_intent(message, context)

        if refined is None:
            logger.debug(
                "Refinement not applicable",
                message=message[:50],
                llm_intent=llm_intent,
                phase=context.spin_phase
            )
            return llm_result

        refined_intent, refined_confidence = refined

        logger.info(
            "Classification refined",
            original_intent=llm_intent,
            refined_intent=refined_intent,
            phase=context.spin_phase,
            message=message[:50]
        )

        # Create refined result
        result = llm_result.copy()
        result["intent"] = refined_intent
        result["confidence"] = refined_confidence
        result["refined"] = True
        result["original_intent"] = llm_intent
        result["refinement_reason"] = f"short_answer_in_{context.spin_phase}_phase"

        return result

    def _is_short_message(self, message: str) -> bool:
        """Check if message is short enough for refinement."""
        words = message.split()
        return (
            len(words) <= self.MAX_SHORT_WORDS or
            len(message.strip()) <= self.MAX_SHORT_CHARS
        )

    def _get_refined_intent(
        self,
        message: str,
        context: RefinementContext
    ) -> Optional[tuple]:
        """
        Get refined intent based on message sentiment and phase.

        Returns:
            Tuple of (intent, confidence) or None if not applicable
        """
        phase = context.spin_phase

        if not phase or phase not in self._short_answer_config:
            return None

        phase_config = self._short_answer_config[phase]

        # Detect sentiment (positive/negative/neutral)
        sentiment = self._detect_sentiment(message)

        if sentiment == "positive":
            intent = phase_config.get("positive_intent")
            confidence = phase_config.get("positive_confidence", 0.7)
            if intent:
                return (intent, confidence)

        elif sentiment == "negative":
            intent = phase_config.get("negative_intent")
            confidence = phase_config.get("negative_confidence", 0.7)
            if intent:
                return (intent, confidence)

        # Neutral/unclear → default to positive for data collection
        if sentiment == "neutral":
            intent = phase_config.get("positive_intent")
            confidence = phase_config.get("positive_confidence", 0.6)  # Lower confidence
            if intent:
                return (intent, confidence)

        return None

    def _detect_sentiment(self, message: str) -> str:
        """
        Detect sentiment of short message.

        Returns: "positive", "negative", or "neutral"
        """
        text = message.lower().strip()

        # Negative patterns
        negative_patterns = [
            "нет", "не", "никак", "ничего", "отказ",
            "не надо", "не нужно", "не интересно"
        ]

        for pattern in negative_patterns:
            if pattern in text:
                return "negative"

        # Positive patterns (includes numbers, confirmations)
        positive_patterns = [
            "да", "ок", "хорошо", "согласен", "верно", "точно",
            "конечно", "ага", "угу", "первое", "второе", "третье"
        ]

        for pattern in positive_patterns:
            if pattern in text:
                return "positive"

        # Numbers are typically positive (answering data questions)
        if any(c.isdigit() for c in text):
            return "positive"

        # Short single words are typically info_provided
        if len(text.split()) == 1 and len(text) > 0:
            return "neutral"

        return "neutral"
```

#### 4.1.2 Обновить constants.py для доступа к конфигурации

**Файл:** `src/yaml_config/constants.py`

Добавить функцию:

```python
def get_short_answer_config() -> dict:
    """
    Get short_answer_classification config from constants.yaml.

    Returns:
        Dict with phase -> {positive_intent, positive_confidence, ...}
    """
    return _CONSTANTS.get("spin", {}).get("short_answer_classification", {})
```

#### 4.1.3 Интегрировать в UnifiedClassifier

**Файл:** `src/classifier/unified.py`

```python
from .refinement import ClassificationRefinementLayer, RefinementContext

class UnifiedClassifier:
    def __init__(self):
        # ... existing init ...
        self._refinement_layer = ClassificationRefinementLayer()

    def classify(self, message: str, context: dict = None) -> dict:
        context = context or {}

        # Step 1: Primary classification
        if flags.llm_classifier:
            result = self._llm_classifier.classify(message, context)
        else:
            result = self._hybrid_classifier.classify(message, context)

        # Step 2: Contextual refinement (NEW)
        if flags.classification_refinement:  # New feature flag
            refinement_ctx = RefinementContext(
                message=message,
                spin_phase=context.get("spin_phase"),
                state=context.get("state"),
                last_action=context.get("last_action"),
                last_intent=context.get("last_intent"),
            )
            result = self._refinement_layer.refine(message, result, refinement_ctx)

        return result
```

### Фаза 2: Улучшение промпта LLM

#### 4.2.1 Добавить контекстные инструкции в prompts.py

**Файл:** `src/classifier/llm/prompts.py`

Добавить секцию в SYSTEM_PROMPT:

```python
SHORT_ANSWER_CONTEXT_SECTION = """
## ВАЖНО: Контекстная классификация коротких ответов

При классификации КОРОТКИХ сообщений (1-3 слова, числа, "да/нет"):
- ОБЯЗАТЕЛЬНО учитывай last_action и spin_phase из контекста
- Если бот спросил о данных (размер команды, проблемы, etc.) и клиент ответил кратко:
  → Это скорее info_provided или situation_provided, НЕ greeting!

Примеры:
- Бот спросил "Сколько человек?" → Клиент: "5" → intent: info_provided (НЕ greeting!)
- Бот спросил "Есть проблемы?" → Клиент: "да" → intent: problem_revealed или agreement
- Бот приветствовал → Клиент: "привет" → intent: greeting (это корректно)

Ключевое правило: Короткие ответы на конкретные вопросы = info_provided или релевантный SPIN intent.
"""
```

#### 4.2.2 Передавать last_bot_question в контекст

**Файл:** `src/classifier/llm/classifier.py`

```python
def _build_context_section(self, context: dict) -> str:
    """Build context section for prompt."""
    sections = []

    if context.get("state"):
        sections.append(f"- Текущее состояние: {context['state']}")

    if context.get("spin_phase"):
        sections.append(f"- SPIN фаза: {context['spin_phase']}")

    if context.get("last_action"):
        sections.append(f"- Последнее действие бота: {context['last_action']}")

    # NEW: Add last bot question if available
    if context.get("last_bot_message"):
        # Truncate to avoid prompt bloat
        last_msg = context["last_bot_message"][:100]
        sections.append(f"- Последнее сообщение бота: \"{last_msg}\"")

    return "\n".join(sections) if sections else "Нет контекста"
```

### Фаза 3: Fallback Transition для greeting

#### 4.3.1 Добавить safe transition в greeting state

**Файл:** `src/yaml_config/flows/_base/states.yaml`

```yaml
greeting:
  extends: _base_greeting
  goal: "Установить контакт и понять запрос"

  transitions:
    # ... existing transitions ...
    info_provided: "{{entry_state}}"
    situation_provided: "{{entry_state}}"

    # NEW: Safe exit from greeting on repeated greeting intent
    # This is a fallback for cases when refinement doesn't trigger
    greeting:
      - when: turn_number_gte_3
        then: "{{entry_state}}"
      - greet_back  # Default: just greet back
```

#### 4.3.2 Добавить условие turn_number_gte_3

**Файл:** `src/conditions/state_machine/definitions.py`

```python
@condition_registry.register("turn_number_gte_3")
def turn_number_gte_3(ctx: EvaluatorContext) -> bool:
    """True if turn number >= 3 (been greeting too long)."""
    return ctx.turn_number >= 3
```

### Фаза 4: Feature Flag и метрики

#### 4.4.1 Добавить feature flag

**Файл:** `src/feature_flags.py`

```python
DEFAULTS = {
    # ... existing flags ...

    # Classification refinement for short answers
    "classification_refinement": True,
}
```

#### 4.4.2 Добавить метрики для отслеживания

**Файл:** `src/metrics.py` (или где хранятся метрики)

```python
# Metrics to track refinement effectiveness
REFINEMENT_METRICS = {
    "refinement_triggered_total": Counter(),
    "refinement_by_phase": Counter(),  # situation, problem, etc.
    "refinement_from_intent": Counter(),  # greeting, unclear, etc.
    "refinement_to_intent": Counter(),  # info_provided, situation_provided, etc.
}
```

---

## 5. Изменения по файлам

### 5.1 Новые файлы

| Файл | Описание |
|------|----------|
| `src/classifier/refinement.py` | ClassificationRefinementLayer |
| `tests/test_classification_refinement.py` | Unit тесты для refinement |
| `tests/test_state_loop_regression.py` | Регрессионные тесты |

### 5.2 Изменяемые файлы

| Файл | Изменения |
|------|-----------|
| `src/classifier/unified.py` | Интеграция RefinementLayer |
| `src/classifier/llm/prompts.py` | Контекстные инструкции для коротких ответов |
| `src/classifier/llm/classifier.py` | Передача last_bot_message в контекст |
| `src/yaml_config/constants.py` | Функция `get_short_answer_config()` |
| `src/yaml_config/flows/_base/states.yaml` | Conditional transition для greeting |
| `src/conditions/state_machine/definitions.py` | Условие `turn_number_gte_3` |
| `src/feature_flags.py` | Флаг `classification_refinement` |
| `src/bot.py` | Передача last_bot_message в контекст классификации |

### 5.3 Порядок изменений (dependency order)

```
1. src/yaml_config/constants.py          # get_short_answer_config()
2. src/classifier/refinement.py          # ClassificationRefinementLayer (NEW)
3. src/feature_flags.py                  # classification_refinement flag
4. src/classifier/unified.py             # Integration
5. src/classifier/llm/prompts.py         # Context instructions
6. src/classifier/llm/classifier.py      # last_bot_message
7. src/bot.py                            # Pass context
8. src/conditions/.../definitions.py     # turn_number_gte_3
9. src/yaml_config/.../states.yaml       # Conditional transition
```

---

## 6. Тестирование

### 6.1 Unit тесты

**Файл:** `tests/test_classification_refinement.py`

```python
import pytest
from src.classifier.refinement import (
    ClassificationRefinementLayer,
    RefinementContext
)


class TestClassificationRefinement:
    """Tests for ClassificationRefinementLayer."""

    @pytest.fixture
    def layer(self):
        return ClassificationRefinementLayer()

    @pytest.fixture
    def situation_context(self):
        return RefinementContext(
            message="1",
            spin_phase="situation",
            state="greeting",
            last_action="ask_about_company",
            last_intent=None
        )

    # =========================================================================
    # should_refine() tests
    # =========================================================================

    def test_should_refine_short_greeting_in_situation(self, layer, situation_context):
        """Short message + greeting intent + situation phase → should refine."""
        assert layer.should_refine("1", "greeting", situation_context)

    def test_should_not_refine_long_message(self, layer, situation_context):
        """Long message → should not refine."""
        long_msg = "У нас в компании работает около 10 человек в отделе продаж"
        assert not layer.should_refine(long_msg, "greeting", situation_context)

    def test_should_not_refine_specific_intent(self, layer, situation_context):
        """Specific intent (not greeting/unclear) → should not refine."""
        assert not layer.should_refine("1", "objection_price", situation_context)

    def test_should_not_refine_no_context(self, layer):
        """No SPIN phase → should not refine."""
        no_context = RefinementContext(
            message="1",
            spin_phase=None,
            state=None,
            last_action=None,
            last_intent=None
        )
        assert not layer.should_refine("1", "greeting", no_context)

    # =========================================================================
    # refine() tests
    # =========================================================================

    def test_refine_greeting_to_situation_provided(self, layer, situation_context):
        """'1' classified as greeting in situation phase → situation_provided."""
        llm_result = {"intent": "greeting", "confidence": 0.95}

        refined = layer.refine("1", llm_result, situation_context)

        assert refined["intent"] == "situation_provided"
        assert refined["refined"] is True
        assert refined["original_intent"] == "greeting"

    def test_refine_preserves_other_fields(self, layer, situation_context):
        """Refinement preserves extracted_data and other fields."""
        llm_result = {
            "intent": "greeting",
            "confidence": 0.95,
            "extracted_data": {"company_size": 1},
            "method": "llm"
        }

        refined = layer.refine("1", llm_result, situation_context)

        assert refined["extracted_data"] == {"company_size": 1}
        assert refined["method"] == "llm"

    def test_refine_negative_in_problem_phase(self, layer):
        """'нет' in problem phase → no_problem."""
        problem_context = RefinementContext(
            message="нет",
            spin_phase="problem",
            state="spin_problem",
            last_action="ask_about_problem",
            last_intent=None
        )
        llm_result = {"intent": "greeting", "confidence": 0.8}

        refined = layer.refine("нет", llm_result, problem_context)

        assert refined["intent"] == "no_problem"

    # =========================================================================
    # Sentiment detection tests
    # =========================================================================

    def test_detect_positive_number(self, layer):
        assert layer._detect_sentiment("5") == "positive"

    def test_detect_positive_confirmation(self, layer):
        assert layer._detect_sentiment("да") == "positive"
        assert layer._detect_sentiment("хорошо") == "positive"

    def test_detect_negative(self, layer):
        assert layer._detect_sentiment("нет") == "negative"
        assert layer._detect_sentiment("не надо") == "negative"

    def test_detect_neutral(self, layer):
        assert layer._detect_sentiment("может") == "neutral"
```

### 6.2 Интеграционные тесты

**Файл:** `tests/test_state_loop_regression.py`

```python
import pytest
from src.bot import SalesBot


class TestStateLoopRegression:
    """Regression tests for state loop bug fix."""

    @pytest.fixture
    def bot(self):
        return SalesBot()

    @pytest.mark.parametrize("short_answer,expected_no_loop", [
        ("1", True),
        ("5", True),
        ("первое", True),
        ("да", True),
        ("ок", True),
        ("10 человек", True),
    ])
    def test_short_answer_does_not_cause_loop(self, bot, short_answer, expected_no_loop):
        """Short answers should not cause state loops."""
        # Simulate conversation
        bot.process("привет")  # Turn 1: greeting

        # Bot asks about company size
        result = bot.process(short_answer)  # Turn 2: short answer

        # Should NOT stay in greeting
        assert bot.state != "greeting" or bot._turn_number < 3

    def test_four_greeting_intents_transitions_out(self, bot):
        """After 3 turns in greeting, should transition out."""
        bot.process("привет")
        bot.process("да")
        bot.process("1")

        # By turn 4, should not be in greeting
        result = bot.process("ок")

        # Either transitioned OR fallback triggered
        assert bot.state != "greeting" or result.get("fallback_triggered")
```

### 6.3 E2E тесты с симуляцией

```bash
# Запуск симуляции для проверки fix
python -m src.simulator -n 50 --focus-state greeting --report state_loop_fix_test.txt

# Проверка метрик
grep "State loop detected" state_loop_fix_test.txt | wc -l
# Ожидается: значительно меньше 52 (было 52 из 100)
```

---

## 7. Миграция и риски

### 7.1 Риски

| Риск | Вероятность | Влияние | Митигация |
|------|-------------|---------|-----------|
| Refinement переклассифицирует корректные greeting | Средняя | Низкое | Строгие условия should_refine(), feature flag |
| Изменение поведения в production | Средняя | Среднее | Feature flag, постепенный rollout |
| Промпт изменения ломают LLM классификацию | Низкая | Высокое | A/B тестирование, fallback на старый промпт |

### 7.2 План rollout

```
1. Deploy с feature flag OFF
2. Включить для 10% трафика (A/B test)
3. Мониторинг метрик:
   - state_loop_detected_rate (должен уменьшиться)
   - classification_accuracy (не должен ухудшиться)
   - conversation_success_rate (должен улучшиться)
4. При положительных результатах → 100% rollout
5. Удалить feature flag после стабилизации
```

### 7.3 Rollback план

```python
# Если что-то пошло не так:
# 1. Выключить feature flag
export FF_CLASSIFICATION_REFINEMENT=false

# 2. Откатить промпт изменения (если были)
git revert <commit_hash_prompts>

# 3. Проверить метрики вернулись к baseline
```

---

## Appendix A: Альтернативные решения (отвергнутые)

### A.1 Просто добавить transition greeting → entry_state

**Почему отвергнуто:**
- Маскирует проблему классификации
- При любом greeting будет переход, даже когда это некорректно
- Не соответствует принципу "fix root cause"

### A.2 Использовать HybridClassifier для коротких сообщений

**Почему отвергнуто:**
- HybridClassifier менее точен для сложных случаев
- Создаёт ветвление логики (if short → hybrid, else → llm)
- Сложнее поддерживать два классификатора

### A.3 Переобучить LLM на контекстных примерах

**Почему отвергнуто:**
- Требует fine-tuning (время, ресурсы)
- LLM всё равно может ошибаться
- Refinement layer — более надёжный и детерминированный

---

## Appendix B: Мониторинг после деплоя

### B.1 Ключевые метрики

```yaml
metrics:
  # Уменьшение state loops
  - name: state_loop_rate
    query: sum(state_loop_detected) / sum(conversations)
    expected: < 0.05  # Было ~0.52

  # Refinement применяется
  - name: refinement_rate
    query: sum(refinement_triggered) / sum(classifications)
    expected: 0.01-0.10  # 1-10% классификаций

  # Точность не упала
  - name: classification_accuracy
    query: sum(correct_intents) / sum(total_intents)
    expected: >= baseline
```

### B.2 Алерты

```yaml
alerts:
  - name: StateLoopRateHigh
    condition: state_loop_rate > 0.10
    severity: warning

  - name: RefinementRateTooHigh
    condition: refinement_rate > 0.20
    severity: warning
    message: "Refinement срабатывает слишком часто — возможно LLM деградировал"
```

---

*Документ создан: 23 Января 2026*
