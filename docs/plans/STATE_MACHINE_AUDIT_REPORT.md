# State Machine Deep Audit Report

**Дата:** 2026-01-21
**Версия State Machine:** 2.0
**Проверенных flows:** 20
**Зарегистрированных условий:** 81

---

## Executive Summary

Обнаружено **146 проблем**:
- **144 HIGH** severity (критические)
- **1 MEDIUM** severity
- **1 LOW** severity

Основные категории проблем:
1. **Незарезолвленные параметры** (141 случай) - `{{default_price_action}}` не определён в большинстве flows
2. **Несуществующие интенты** (107+ интентов) - transitions ссылаются на интенты которых нет в classifier
3. **Отсутствующие handlers** (4 интента) - некоторые classifier intents не имеют transitions/rules

---

## Детальный анализ проблем

### 1. [SEVERITY: HIGH] Незарезолвленные параметры `{{default_price_action}}`

**Где:** 19 из 20 flows (все кроме spin_selling)

**Что:** Параметр `{{default_price_action}}` используется в mixin `price_handling` ([_base/mixins.yaml:30](src/yaml_config/flows/_base/mixins.yaml#L30)), но не определён в `flow.yaml` большинства flows.

**Почему плохо:**
- При вызове правила `price_question` с conditional logic, fallback ветка возвращает строку `"{{default_price_action}}"` вместо action
- Generator не сможет найти template для такого action
- Клиент не получит ответ на вопрос о цене

**Как воспроизвести:**
```
Flow: aida, bant, challenger, etc.
1. Перейти в любое состояние с mixin price_handling
2. Отправить "Сколько стоит?"
3. Система вернёт action "{{default_price_action}}"
```

**Рекомендация:**
Добавить во все flow.yaml:
```yaml
variables:
  default_price_action: deflect_and_continue  # или answer_with_facts
```

**Оценка влияния:** ~30% диалогов (все где спрашивают цену в non-spin flows)

---

### 2. [SEVERITY: HIGH] Transitions на несуществующие интенты

**Где:** Все flows кроме spin_selling и bant

**Что:** 107+ интентов используются в transitions/rules, но не определены в classifier ([prompts.py](src/classifier/llm/prompts.py)):

```
attention_captured, interest_shown, desire_expressed, action_taken,  # AIDA
budget_discussed, pain_confirmed, pain_critical,                      # Sandler
insight_shared, reframe_accepted, commitment,                         # Challenger
value_question, roi_inquiry, cost_concern,                            # Value
... и ещё ~90 интентов
```

**Почему плохо:**
- Classifier никогда не вернёт эти интенты
- Transitions никогда не сработают
- Flows фактически сломаны — всегда будет срабатывать default action

**Как воспроизвести:**
```
Flow: aida
1. Начать диалог в aida_attention
2. Клиент говорит что-то что должно быть "attention captured"
3. Classifier вернёт situation_provided или info_provided
4. Transition attention_captured → aida_interest НЕ сработает
```

**Рекомендация:**
Варианты решения:
1. Добавить эти интенты в classifier (увеличит сложность классификации)
2. Использовать существующие интенты с маппингом:
   ```yaml
   # В flow.yaml
   intent_mapping:
     situation_provided: attention_captured  # для AIDA
   ```
3. Переписать transitions на существующие интенты

**Оценка влияния:** 100% диалогов в affected flows (все кроме spin_selling)

---

### 3. [SEVERITY: MEDIUM] Интенты classifier без handlers

**Где:** [_base/states.yaml](src/yaml_config/flows/_base/states.yaml), все flows

**Что:** 4 интента из classifier не имеют явных transitions/rules:
- `objection_complexity` - "слишком сложно"
- `objection_no_need` - "не нужно" (отличается от `no_need`)
- `objection_timing` - "сейчас не актуально"
- `objection_trust` - "не уверен"

**Почему плохо:**
- При получении этих интентов система вернёт `continue_current_goal`
- Возражение не будет корректно обработано
- Клиент не получит ответ на своё возражение

**Как воспроизвести:**
```
1. Любой flow, любое состояние
2. Клиент: "Это слишком сложно для нас"
3. Classifier → objection_complexity
4. Нет transition → continue_current_goal
5. Бот продолжает как будто возражения не было
```

**Рекомендация:**
Добавить в mixin `objection_handling`:
```yaml
objection_handling:
  transitions:
    objection_complexity:
      - when: objection_limit_reached
        then: soft_close
      - handle_objection
    objection_timing:
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
```

**Оценка влияния:** ~5% диалогов (клиенты с этими возражениями)

---

### 4. [SEVERITY: LOW] Координация лимитов

**Где:** [constants.yaml](src/yaml_config/constants.yaml)

**Что:**
- `max_consecutive_objections: 3`
- `max_same_state: 4` (ConversationGuard)

**Почему потенциально плохо:**
- Если клиент возражает 3 раза подряд → soft_close
- Guard сработает только на 4-м повторе состояния
- Лимиты работают корректно, но важно понимать порядок

**Рекомендация:**
Документировать ожидаемое поведение. Текущая логика корректна:
1. 3 возражения → soft_close (objection limit)
2. Guard на 4 повторе — backup защита

**Оценка влияния:** ~2% диалогов (edge cases)

---

## Дополнительные находки

### 5. [SEVERITY: MEDIUM] Семантика phase_progress mixin

**Где:** [_base/mixins.yaml:244-251](src/yaml_config/flows/_base/mixins.yaml#L244)

**Что:** Mixin `phase_progress` переводит `situation_provided`, `problem_revealed` и др. в `{{next_phase_state}}`.

**Проблема в BANT:**
В `bant_budget` если клиент говорит `situation_provided` (информация о ситуации), система переходит в `bant_authority`. Но клиент дал информацию о ситуации, а не о бюджете!

**Как воспроизвести:**
```
Flow: bant
1. bant_budget: "Какой у вас бюджет?"
2. Клиент: "У нас 10 человек в команде" (situation_provided)
3. → bant_authority (НЕПРАВИЛЬНО, должен остаться в bant_budget)
```

**Рекомендация:**
Для BANT flow отключить mixin phase_progress или переопределить:
```yaml
bant_budget:
  extends: _base_phase
  mixins:
    - price_handling
    - product_questions
    # НЕ включать phase_progress
  transitions:
    situation_provided: bant_budget  # Остаться, попросить бюджет
```

**Оценка влияния:** ~10% диалогов в BANT flow

---

### 6. [SEVERITY: LOW] soft_close не финальный но выходы работают

**Где:** [_base/states.yaml:118-155](src/yaml_config/flows/_base/states.yaml#L118)

**Что:** `soft_close` имеет `is_final: false` и 11 выходных transitions.

**Анализ:** Это **корректное** поведение:
- Клиент может передумать → `agreement: "{{entry_state}}"`
- Клиент может задать вопрос → `price_question: presentation`
- Явные rejection/farewell обрабатываются через rules (без перехода)

**Рекомендация:** Документировать это поведение. Текущая реализация правильная.

---

## Приоритетный план исправлений

### Критические (сделать сегодня):

1. **Добавить `default_price_action` во все flow.yaml**
   ```bash
   for flow in aida bant challenger ... ; do
     # Добавить в variables
   done
   ```

2. **Добавить недостающие objection handlers в mixins.yaml**

### Важные (эта неделя):

3. **Решить проблему несуществующих интентов**
   - Вариант A: Расширить classifier
   - Вариант B: Использовать mapping существующих интентов
   - Вариант C: Переписать transitions на существующие интенты (рекомендуется)

4. **Исправить семантику phase_progress для BANT**

### Низкий приоритет:

5. Документировать координацию лимитов
6. Добавить тесты для edge cases

---

## Статистика

| Метрика | Значение |
|---------|----------|
| Всего flows | 20 |
| Работающих flows | 2 (spin_selling, частично bant) |
| Интентов в classifier | 33 |
| Интентов в transitions | 140+ |
| Зарегистрированных условий | 81 |
| Состояний в базе | 7 (_base) |

---

## Валидационный скрипт

Создан скрипт для автоматической проверки:

```bash
python3 scripts/audit_state_machine.py
```

Скрипт проверяет:
- ✅ Покрытие интентов
- ✅ Unreachable states
- ✅ Незарезолвленные параметры
- ✅ Несуществующие условия
- ✅ Mixin конфликты
- ✅ Terminal states

---

## Выводы

1. **Только spin_selling flow полностью работоспособен**
2. Остальные 19 flows требуют доработки перед использованием
3. Основная проблема — отсутствие синхронизации между classifier intents и flow transitions
4. Рекомендуется использовать единый набор интентов для всех flows вместо flow-specific

---

*Отчёт сгенерирован: 2026-01-21*
*Автор: Claude Code (Deep Audit)*
