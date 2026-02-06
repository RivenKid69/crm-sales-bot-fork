# Intent Taxonomy

## 1. Источник данных

SSOT: `src/yaml_config/constants.yaml`

Основные секции:
- `intents.categories`
- `intents.composed_categories`
- `intent_taxonomy`
- `taxonomy_category_defaults`
- `taxonomy_super_category_defaults`
- `taxonomy_domain_defaults`

## 2. Фактические размеры (текущая кодовая база)

- Base categories: `34`
- Composed categories: `7`
- Total categories после резолва: `41`
- Intent entries в `intent_taxonomy`: `271`

Часто используемые base-категории:
- `question` — 18
- `objection` — 18
- `positive` — 23
- `technical_question` — 13
- `spin_progress` — 4

## 3. Где используется taxonomy

- `RuleResolver` и state transition fallback.
- Классификатор (через категории и refinement layers).
- Blackboard sources (например, rule/intent guards).

## 4. Важный operational note

При импорте `src.yaml_config.constants` в текущей ревизии выводятся warnings о ghost-intents (`question_technical`, `question_answered`) в некоторых категориях.

Это не ломает runtime, но это признак рассинхронизации между категориями и генератором интентов (`INTENT_ROOTS` в `src/config.py`).
