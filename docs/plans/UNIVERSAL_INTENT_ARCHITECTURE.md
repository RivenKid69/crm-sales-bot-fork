# Universal Intent Architecture

## Проблема

Текущая архитектура имеет рассинхронизацию:
- **Classifier** определяет 33 интента
- **Flows** используют 140+ интентов в transitions

Это приводит к тому, что 18 из 20 flows не работают.

## Решение: Universal Intent Mapping

### Принцип

Вместо добавления 107+ flow-specific интентов в classifier, используем **универсальные интенты** с маппингом на flow-specific концепции.

### Universal Progress Intents

| Intent | Значение | Использование в flows |
|--------|----------|----------------------|
| `agreement` | Клиент согласен, готов двигаться дальше | Основной прогресс-интент |
| `info_provided` | Клиент предоставил информацию | Прогресс при сборе данных |
| `situation_provided` | Информация о ситуации | SPIN situation, BANT budget |
| `problem_revealed` | Проблема выявлена | SPIN problem, Sandler pain |
| `need_expressed` | Потребность выражена | SPIN need_payoff |
| `demo_request` | Запрос демо | Сигнал готовности к close |
| `consultation_request` | Запрос консультации | Сигнал интереса |

### Маппинг Flow-Specific → Universal

```yaml
# AIDA
attention_captured  → agreement, info_provided
interest_shown      → agreement, question_features
desire_expressed    → need_expressed, agreement
action_taken        → agreement, demo_request

# Challenger
insight_accepted    → agreement, info_provided
reframe_accepted    → agreement
commitment          → agreement, demo_request

# Value
value_drivers_found → info_provided
impact_quantified   → info_provided, agreement
roi_accepted        → agreement
```

### Архитектурное решение

**1. Все flows используют универсальные интенты в transitions:**
```yaml
transitions:
  agreement: next_state
  info_provided: next_state
  demo_request: close
  callback_request: close
```

**2. Flow-specific logic реализуется через rules:**
```yaml
rules:
  # Flow-specific actions, не transitions
  question_features: explain_feature
  price_question: answer_with_facts
```

**3. Phase progression через agreement + data_complete:**
```yaml
transitions:
  agreement: next_phase_state
  data_complete: next_phase_state
```

## Новые интенты для добавления в Classifier

Для полного покрытия нужно добавить **4 новых интента**:

1. `budget_mentioned` — клиент упоминает бюджет
2. `timeline_mentioned` — клиент упоминает сроки
3. `authority_mentioned` — клиент упоминает полномочия/ЛПР
4. `value_acknowledged` — клиент признаёт ценность

## Реализация

### Шаг 1: Обновить _base/mixins.yaml

Добавить unified_progress mixin:
```yaml
unified_progress:
  description: "Universal progress transitions for all flows"
  transitions:
    agreement: "{{next_phase_state}}"
    info_provided: "{{next_phase_state}}"
    situation_provided: "{{next_phase_state}}"
    problem_revealed: "{{next_phase_state}}"
    need_expressed: "{{next_phase_state}}"
```

### Шаг 2: Обновить все flows

Заменить flow-specific transitions на universal.

### Шаг 3: Добавить default_price_action

Добавить в _base/mixins.yaml defaults:
```yaml
defaults:
  default_price_action: deflect_and_continue
  default_unclear_action: continue_current_goal
```

## Backward Compatibility

- spin_selling продолжает работать без изменений
- Новые flows используют unified подход
- Старые flows мигрируют на universal intents
