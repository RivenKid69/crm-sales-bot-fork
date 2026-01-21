# План исправления: Баг 1 — Массовые Guard/Fallback интервенции

> **Баг**: 326 случаев ложных срабатываний Guard tier_3
> **Дата**: Январь 2026
> **Статус**: План

---

## 1. Корневой анализ проблемы

### 1.1 Первичная причина: `fallback_response` не сбрасывается

**Файл**: `src/bot.py:691-734`

```python
if fb_result.get("response"):
    fallback_response = fb_result  # ← Устанавливается

    if fb_result.get("action") == "close":
        return {...}  # early return OK

    elif fb_result.get("action") == "skip":
        self.state_machine.state = skip_next_state
        # ❌ BUG: fallback_response НЕ сбрасывается!
        # Комментарий говорит "normal flow to generate response"
        # но fallback_response остаётся установленным!
```

**Затем на строке 922:**

```python
if fallback_response:
    response = fallback_response["response"]  # ← tier_3 шаблон!
else:
    response = self.generator.generate(action, context)  # ← Не вызывается!
```

**Результат**: Бот выдаёт "Если сложно ответить — можем пропустить" вместо нормального ответа.

### 1.2 Вторичная причина: Guard не учитывает информативность

**Файл**: `src/conversation_guard.py:219-227`

```python
same_state_count = self._count_recent_same_state(state)
if same_state_count >= self.config.max_same_state:  # max=4
    return True, self.TIER_3  # ← Срабатывает даже при прогрессе!
```

**Проблема**: Guard считает только количество раз в одном состоянии, но:
- Клиент может 4 раза отвечать в `spin_situation` (даёт company_size, current_tools, etc.)
- Это НОРМАЛЬНО для сбора данных
- Guard срабатывает, хотя есть прогресс

---

## 2. Архитектурное решение

### 2.1 Принципы

| Принцип | Применение |
|---------|------------|
| **Single Responsibility** | Guard проверяет только застревание; Bot решает когда сбрасывать fallback |
| **Config-driven** | Добавить `informative_intents` в YAML |
| **Feature flags** | Новое поведение под флагами для A/B тестирования |
| **Observable** | Метрики ложных срабатываний |

### 2.2 Схема исправления

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         ТЕКУЩИЙ FLOW (БАГ)                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Guard.check() → TIER_3 → fallback_response = {...}                         │
│                                 │                                           │
│                                 ▼                                           │
│  action == "skip" → state переключается                                     │
│                                 │                                           │
│                                 ▼                                           │
│  classify() → intent = "situation_provided" (клиент дал данные!)            │
│                                 │                                           │
│                                 ▼                                           │
│  generate() → if fallback_response: response = fallback_response  ❌        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                         ИСПРАВЛЕННЫЙ FLOW                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Guard.check() → проверяет ИНФОРМАТИВНОСТЬ → если intent в INFORMATIVE      │
│                  → НЕ срабатывает даже при same_state_count >= 4            │
│                                 │                                           │
│                                 ▼                                           │
│  ИЛИ: action == "skip" → fallback_response = None  ✅                       │
│                                 │                                           │
│                                 ▼                                           │
│  classify() → intent = "situation_provided"                                 │
│                                 │                                           │
│                                 ▼                                           │
│  generate() → if fallback_response: ... else: generator.generate()  ✅      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Детальный план исправлений

### Фаза 1: Исправление bot.py (Критично)

**Файл**: `src/bot.py`

**Изменение 1.1**: Сброс `fallback_response` после "skip"

```python
# БЫЛО (строки 722-734):
elif fb_result.get("action") == "skip" and fb_result.get("next_state"):
    skip_next_state = fb_result["next_state"]
    self.state_machine.state = skip_next_state
    logger.info(
        "Fallback skip applied",
        from_state=current_state,
        to_state=skip_next_state
    )
    current_state = skip_next_state
    # Continue processing with new state - don't return early

# СТАНЕТ:
elif fb_result.get("action") == "skip" and fb_result.get("next_state"):
    skip_next_state = fb_result["next_state"]
    self.state_machine.state = skip_next_state
    logger.info(
        "Fallback skip applied - resetting fallback_response for normal generation",
        from_state=current_state,
        to_state=skip_next_state,
        original_tier=intervention
    )
    current_state = skip_next_state
    # ✅ FIX: Сбрасываем fallback_response чтобы сгенерировать нормальный ответ
    fallback_response = None
```

**Изменение 1.2**: Добавить метрику для отслеживания

```python
# После сброса fallback_response:
if trace_builder:
    trace_builder.record_guard_decision(
        tier=intervention,
        action="skip",
        fallback_reset=True
    )
```

### Фаза 2: Улучшение conversation_guard.py (Важно)

**Файл**: `src/conversation_guard.py`

**Изменение 2.1**: Добавить проверку информативности перед state loop detection

```python
# БЫЛО (строки 219-227):
# 5. Проверка застревания в состоянии
same_state_count = self._count_recent_same_state(state)
if same_state_count >= self.config.max_same_state:
    logger.warning(
        "State loop detected",
        state=state,
        count=same_state_count
    )
    return True, self.TIER_3

# СТАНЕТ:
# 5. Проверка застревания в состоянии (с учётом информативности)
same_state_count = self._count_recent_same_state(state)
if same_state_count >= self.config.max_same_state:
    # ✅ FIX: Проверяем был ли последний intent информативным
    if self._has_recent_informative_intent():
        logger.debug(
            "State loop threshold reached but client is providing info - not triggering",
            state=state,
            count=same_state_count,
            last_intent=self._state.last_intent
        )
        # Не срабатываем если клиент даёт полезную информацию
    else:
        logger.warning(
            "State loop detected - no informative intents",
            state=state,
            count=same_state_count
        )
        return True, self.TIER_3
```

**Изменение 2.2**: Добавить метод `_has_recent_informative_intent()`

```python
def _has_recent_informative_intent(self, lookback: int = 2) -> bool:
    """
    Проверить были ли недавние интенты информативными.

    Информативные интенты показывают что клиент отвечает на вопросы,
    а не застрял. В таком случае не нужно срабатывать Guard.

    Args:
        lookback: Сколько последних интентов проверять

    Returns:
        True если хотя бы один из последних интентов информативный
    """
    informative_intents = self._get_informative_intents()
    recent_intents = self._state.intent_history[-lookback:]

    for intent in recent_intents:
        if intent in informative_intents:
            return True
    return False

def _get_informative_intents(self) -> set:
    """
    Получить множество информативных интентов из конфига.

    Информативные интенты = клиент предоставляет данные, а не застрял.
    """
    # Приоритет: конфиг → default fallback
    if hasattr(self, '_informative_intents_cache'):
        return self._informative_intents_cache

    # Пробуем из YAML конфига
    try:
        from src.config_loader import get_config
        config = get_config()
        intents = config.intents.get("informative", [])
        if intents:
            self._informative_intents_cache = set(intents)
            return self._informative_intents_cache
    except Exception:
        pass

    # Fallback: positive + spin_progress интенты
    self._informative_intents_cache = {
        # SPIN progress
        "situation_provided",
        "problem_revealed",
        "implication_acknowledged",
        "need_expressed",
        # Positive engagement
        "info_provided",
        "agreement",
        "demo_request",
        "callback_request",
        "contact_provided",
        "consultation_request",
        # Questions (клиент интересуется)
        "question_features",
        "question_integrations",
        "price_question",
        "pricing_details",
    }
    return self._informative_intents_cache
```

**Изменение 2.3**: Отслеживать intent history в GuardState

```python
@dataclass
class GuardState:
    """Состояние Guard между вызовами"""
    turn_count: int = 0
    last_progress_turn: int = 0
    message_history: List[str] = field(default_factory=list)
    state_history: List[str] = field(default_factory=list)
    phase_attempts: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    collected_data_count: int = 0
    frustration_level: int = 0
    intent_history: List[str] = field(default_factory=list)  # ✅ НОВОЕ
    last_intent: str = ""  # ✅ НОВОЕ
```

**Изменение 2.4**: Обновить `check()` для записи intent

```python
def check(
    self,
    message: str,
    state: str,
    collected_data: Dict[str, Any],
    last_intent: str = ""  # ✅ НОВОЕ: принимаем intent
) -> Tuple[bool, Optional[str]]:
    """..."""
    # Записываем intent в историю
    if last_intent:
        self._state.last_intent = last_intent
        self._state.intent_history.append(last_intent)
        # Ограничиваем размер истории
        if len(self._state.intent_history) > 10:
            self._state.intent_history = self._state.intent_history[-10:]
    # ...
```

### Фаза 3: YAML конфигурация (Config-driven)

**Файл**: `src/yaml_config/constants.yaml`

**Изменение 3.1**: Добавить категорию информативных интентов

```yaml
intents:
  categories:
    # ... existing categories ...

    # НОВОЕ: Информативные интенты (клиент даёт данные / задаёт вопросы)
    # Guard НЕ должен срабатывать если последний intent из этой категории
    informative:
      # SPIN progress
      - situation_provided
      - problem_revealed
      - implication_acknowledged
      - need_expressed
      # Positive engagement
      - info_provided
      - agreement
      - demo_request
      - callback_request
      - contact_provided
      - consultation_request
      # Active interest
      - question_features
      - question_integrations
      - comparison
      - price_question
      - pricing_details
```

### Фаза 4: Feature flags

**Файл**: `src/feature_flags.py`

```python
# === Guard Improvements ===
"guard_check_informative_intents": True,   # Проверять информативность перед TIER_3
"fallback_skip_reset": True,               # Сбрасывать fallback_response при skip
```

### Фаза 5: Интеграция с bot.py

**Изменение 5.1**: Передавать intent в Guard

```python
# БЫЛО:
should_continue, intervention = self.guard.check(
    message=user_message,
    state=current_state,
    collected_data=collected_data
)

# СТАНЕТ:
should_continue, intervention = self.guard.check(
    message=user_message,
    state=current_state,
    collected_data=collected_data,
    last_intent=self.last_intent  # ✅ Передаём предыдущий intent
)
```

---

## 4. Тестовый план

### 4.1 Unit тесты

```python
class TestGuardInformativeIntents:
    """Тесты для проверки информативности."""

    def test_state_loop_not_triggered_with_informative_intent(self):
        """Guard не срабатывает при state loop если intent информативный."""
        guard = ConversationGuard()

        # Симулируем 4 раза в одном состоянии с информативными интентами
        for i in range(4):
            guard.check(
                message=f"У нас {i+5} человек в команде",
                state="spin_situation",
                collected_data={},
                last_intent="situation_provided"
            )

        # 5-й раз - НЕ должен сработать потому что intent информативный
        should_continue, tier = guard.check(
            message="Используем Excel сейчас",
            state="spin_situation",
            collected_data={},
            last_intent="situation_provided"
        )

        assert tier is None, "Guard не должен срабатывать при информативных интентах"

    def test_state_loop_triggered_without_informative_intent(self):
        """Guard срабатывает при state loop если intent НЕ информативный."""
        guard = ConversationGuard()

        # Симулируем 4 раза с unclear
        for i in range(4):
            guard.check(
                message="Не знаю",
                state="spin_situation",
                collected_data={},
                last_intent="unclear"
            )

        # 5-й раз - ДОЛЖЕН сработать
        should_continue, tier = guard.check(
            message="Что?",
            state="spin_situation",
            collected_data={},
            last_intent="unclear"
        )

        assert tier == ConversationGuard.TIER_3


class TestFallbackSkipReset:
    """Тесты для сброса fallback_response при skip."""

    def test_skip_action_resets_fallback_response(self):
        """При action=skip fallback_response должен сбрасываться."""
        # Мок бота с fallback
        bot = SalesBot()

        # Симулируем ситуацию где Guard вернул skip
        # После этого fallback_response должен быть None
        # и generator.generate() должен вызваться
        ...
```

### 4.2 Integration тесты

```python
class TestGuardIntegration:
    """E2E тесты Guard поведения."""

    def test_client_providing_data_not_interrupted(self):
        """Клиент дающий данные не прерывается Guard."""
        bot = SalesBot()

        # Диалог где клиент отвечает на вопросы в одном состоянии
        responses = []
        messages = [
            "Привет, расскажу о компании",
            "У нас 5 человек в команде",
            "Работаем в IT",
            "Используем Excel для учёта",
            "Хотим автоматизировать продажи",
        ]

        for msg in messages:
            result = bot.process(msg)
            responses.append(result)
            # Ни один ответ не должен содержать fallback шаблон
            assert "Если сложно ответить" not in result["response"]
```

---

## 5. Метрики успеха

| Метрика | Текущее | Цель |
|---------|---------|------|
| Guard TIER_3 срабатываний | 326 | < 50 |
| Ложные срабатывания (informative intents) | ~80% | < 10% |
| Fallback response при skip | 100% (баг) | 0% |

---

## 6. Риски и митигация

| Риск | Вероятность | Митигация |
|------|-------------|-----------|
| Guard перестанет срабатывать вообще | Низкая | Unit тесты + метрики |
| Регрессия в других компонентах | Средняя | Feature flags для отката |
| Performance (intent history) | Низкая | Ограничение размера истории (10 записей) |

---

## 7. Чеклист реализации

- [ ] **Фаза 1**: Исправить `bot.py` - сброс `fallback_response` при skip
- [ ] **Фаза 2**: Улучшить `conversation_guard.py` - проверка информативности
- [ ] **Фаза 3**: Добавить `informative` категорию в `constants.yaml`
- [ ] **Фаза 4**: Добавить feature flags
- [ ] **Фаза 5**: Интеграция - передавать intent в Guard
- [ ] **Тесты**: Написать unit и integration тесты
- [ ] **Метрики**: Настроить мониторинг Guard срабатываний
