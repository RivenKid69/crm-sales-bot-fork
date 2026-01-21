# Фундаментальное решение проблем нерелевантных ответов

## Проблемы из e2e симуляции

### Проблема 1: "не грузите меня, скажите суть" → ответ про масштабирование
- **Корень**: Нет интента `request_brevity` в LLM классификаторе
- **Результат**: LLM вынужден выбрать ближайший интент → `objection_think`
- **Воспроизведение**: `intent = objection_think`, но сообщение о желании краткости

### Проблема 2: "у нас Poster" → ответ про масштаб внедрения (вместо сравнения с Poster)
- **Корень**: Интент `objection_competitor` классифицируется КОРРЕКТНО!
- **НО**: Template selection не учитывает тип возражения
- **Результат**: Используется generic `handle_objection` вместо `handle_objection_competitor`
- **Плюс**: Шаблон использует `{facts}` вместо `{retrieved_facts}` с информацией о конкуренте

---

## План решения (по архитектуре проекта)

### Шаг 1: Добавить интент `request_brevity`

**Файлы для изменения:**

1. **`src/classifier/llm/schemas.py`** - добавить в IntentType:
```python
IntentType = Literal[
    # ... existing ...
    # Управление диалогом
    "unclear", "go_back", "correct_info",
    "request_brevity"  # НОВОЕ: запрос краткости
]
```

2. **`src/classifier/llm/prompts.py`** - добавить в SYSTEM_PROMPT:
```python
### Управление диалогом:
- unclear: непонятное сообщение
- go_back: вернуться назад
- correct_info: исправление информации
- request_brevity: запрос краткости ("скажите суть", "короче", "не грузите")
```

3. **`src/classifier/llm/few_shot.py`** - добавить примеры:
```python
{
    "message": "не грузите меня, просто скажите суть",
    "context": {},
    "result": {
        "intent": "request_brevity",
        "confidence": 0.95,
        "reasoning": "Клиент просит более краткий ответ"
    }
}
```

4. **`src/knowledge/retriever.py`** - добавить маппинг:
```python
"request_brevity": [],  # Не требует фактов, это meta-интент
```

5. **`src/yaml_config/constants.yaml`** - добавить в категории:
```yaml
categories:
  dialog_control:
    - unclear
    - go_back
    - correct_info
    - request_brevity
```

---

### Шаг 2: Intent-aware выбор шаблонов для objection

**Паттерн**: Скопировать логику `PRICE_RELATED_INTENTS` / `_get_price_template_key()`

**Файл: `src/generator.py`**

1. Добавить константу:
```python
class ResponseGenerator:
    PRICE_RELATED_INTENTS = {"price_question", "pricing_details"}

    # НОВОЕ: Objection интенты - требуют специфичный шаблон
    OBJECTION_RELATED_INTENTS = {
        "objection_competitor",
        "objection_price",
        "objection_no_time",
        "objection_think",
        "objection_complexity",
        "objection_trust",
        "objection_no_need",
        "objection_timing",
    }
```

2. Добавить метод `_get_objection_template_key()`:
```python
def _get_objection_template_key(self, intent: str, action: str) -> str:
    """
    Выбрать шаблон для objection-related интентов.
    """
    # Маппинг интента на специфичный шаблон
    OBJECTION_TEMPLATE_MAP = {
        "objection_competitor": "handle_objection_competitor",
        "objection_price": "handle_objection_price",
        "objection_no_time": "handle_objection_no_time",
        "objection_think": "handle_objection_think",
        "objection_complexity": "handle_objection_complexity",
        "objection_trust": "handle_objection_trust",
        "objection_no_need": "handle_objection_no_need",
        "objection_timing": "handle_objection_timing",
    }

    template_key = OBJECTION_TEMPLATE_MAP.get(intent)

    # Проверяем существует ли шаблон
    if template_key:
        if (self._flow and self._flow.get_template(template_key)) or template_key in PROMPT_TEMPLATES:
            return template_key

    # Fallback на generic
    return "handle_objection"
```

3. Обновить логику выбора шаблона в `generate_response()`:
```python
# === Intent-aware выбор шаблона ===
if intent in self.PRICE_RELATED_INTENTS:
    template_key = self._get_price_template_key(intent, action)
elif intent in self.OBJECTION_RELATED_INTENTS:
    template_key = self._get_objection_template_key(intent, action)
elif action.startswith("transition_to_"):
    template_key = action.replace("transition_to_", "")
else:
    template_key = action
```

---

### Шаг 3: Исправить шаблоны objection (retrieved_facts)

**Проблема**: `handle_objection_competitor` использует `{objection_counter}` но не `{retrieved_facts}` с информацией о конкуренте

**Файл: `src/config.py`** (линия 2093)

Обновить шаблон:
```python
"handle_objection_competitor": """{system}

{style_full_instruction}

Ситуация: Клиент говорит что уже использует другую CRM/систему.

=== ИНФОРМАЦИЯ О КОНКУРЕНТАХ ===
{retrieved_facts}
================================

Информация о клиенте:
- Размер: {bc_size_label} ({company_size} человек)
- Отрасль: {industry}

Диалог:
{history}

Клиент: "{user_message}"

Структура ответа:
1. Признай что другие системы тоже хороши (покажи уважение к выбору)
2. Используй ФАКТЫ выше для сравнения (НЕ придумывай!)
3. Предложи посмотреть демо — вдруг понравится больше

Ответ на русском (2-3 предложения):"""
```

---

### Шаг 4: Подключить few-shot примеры к LLM классификатору

**Проблема**: `get_few_shot_prompt()` в `few_shot.py` - мёртвый код, никогда не вызывается

**Файл: `src/classifier/llm/prompts.py`**

```python
from .few_shot import get_few_shot_prompt

def build_classification_prompt(
    message: str,
    context: dict = None,
    n_few_shot: int = 5  # НОВОЕ: количество примеров
) -> str:
    """Построить промпт для классификации."""
    context = context or {}

    # ... existing context building ...

    few_shot_section = get_few_shot_prompt(n_few_shot)

    return f"""{SYSTEM_PROMPT}

{few_shot_section}

## Контекст диалога:
{context_str}

## Сообщение пользователя:
{message}

## Твой JSON ответ:"""
```

---

### Шаг 5: Добавить шаблон для request_brevity

**Файл: `src/yaml_config/templates/_base/prompts.yaml`**

```yaml
  respond_briefly:
    description: "Ответить кратко по запросу клиента"
    parameters:
      required: [system, history, user_message, collected_data, spin_phase]
    template: |
      {system}

      СИТУАЦИЯ: Клиент попросил говорить короче/по сути.
      Это НЕ возражение! Просто стиль коммуникации.

      Что уже знаем о клиенте: {collected_data}
      Текущая фаза: {spin_phase}

      Диалог:
      {history}

      Клиент: "{user_message}"

      Твоя задача:
      1. Подтвердить что понял (1 слово: "Понял" или "Хорошо")
      2. Дать КОРОТКИЙ ответ по сути (1 предложение максимум)
      3. Если нужен вопрос — один простой вопрос

      ВАЖНО: Не извиняйся, не объясняй почему был многословен.

      Ответ на русском (максимум 2 коротких предложения):
```

**Файл: `src/config.py`** - добавить в PROMPT_TEMPLATES

---

### Шаг 6: Обновить state machine transitions для request_brevity

**Файл: `src/yaml_config/flows/_base/states.yaml`** и mixins

```yaml
# В каждом состоянии добавить:
transitions:
  request_brevity:
    - respond_briefly  # action
    - [current_state]  # остаёмся в текущем состоянии
```

---

## Порядок реализации

1. **schemas.py** → IntentType (добавить request_brevity)
2. **prompts.py** → SYSTEM_PROMPT (добавить описание request_brevity) + подключить few_shot
3. **few_shot.py** → добавить примеры для request_brevity
4. **retriever.py** → INTENT_TO_CATEGORY (добавить request_brevity: [])
5. **generator.py** → OBJECTION_RELATED_INTENTS + _get_objection_template_key()
6. **config.py** → обновить handle_objection_competitor с retrieved_facts
7. **prompts.yaml** → добавить respond_briefly шаблон
8. **states.yaml** → transitions для request_brevity
9. **constants.yaml** → categories (добавить в dialog_control)

---

## Тесты

1. **test_request_brevity_intent.py** - классификация "не грузите меня"
2. **test_objection_template_selection.py** - правильный выбор шаблона для objection_competitor
3. **test_retrieved_facts_in_objection.py** - проверка что {retrieved_facts} используется
4. **test_few_shot_integration.py** - проверка что few-shot примеры включены в промпт

---

## Ожидаемый результат

### До:
- "не грузите меня, скажите суть" → intent: `objection_think` → ответ про "подумать"
- "у нас Poster" → intent: `objection_competitor` → template: `handle_objection` (generic) → ответ про масштаб

### После:
- "не грузите меня, скажите суть" → intent: `request_brevity` → краткий релевантный ответ
- "у нас Poster" → intent: `objection_competitor` → template: `handle_objection_competitor` → ответ с фактами о Poster vs Wipon
