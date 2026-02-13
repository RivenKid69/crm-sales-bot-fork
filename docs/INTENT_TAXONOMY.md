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
- Intent entries в `intent_taxonomy`: `247`

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

## 4. Operational note

Категории интентов собираются через `INTENT_CATEGORIES` в `src/yaml_config/constants.py` (base + composed).
При изменениях в taxonomy важно обновлять `constants.yaml` и тесты классификатора синхронно.
