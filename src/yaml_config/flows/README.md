# Modular Flow System

Актуальное описание структуры flow-конфигурации.

## 1. Где лежат flow

`src/yaml_config/flows/<flow_name>/`

Типовой набор файлов:
- `flow.yaml`
- `states.yaml`

## 2. Формат `flow.yaml`

В текущей кодовой базе используется корневой ключ `flow`:

```yaml
flow:
  name: spin_selling
  version: "2.0"
  description: "SPIN Selling methodology flow"
  variables: {}
  phases:
    order: [situation, problem, implication, need_payoff]
    mapping: {}
    progress_intents: {}
    skip_conditions: {}
    post_phases_state: presentation
  entry_points:
    default: greeting
```

## 3. Формат `states.yaml`

Также использует корневой ключ `states`:

```yaml
states:
  greeting:
    goal: "..."
    phase: situation
    required_data: []
    optional_data: []
    transitions: {}
    rules: {}
```

Поддерживается `extends`, `parameters`, `on_enter`, `abstract: true`.

## 4. Загрузка

- `ConfigLoader.load_flow(flow_name)`
- Автовыбор flow через `settings.flow.active` в `src/settings.yaml`

## 5. Текущий набор flow

В репозитории доступны:
- `spin_selling`
- `autonomous`
- `aida`
- `bant`
- `challenger`
- `command`
- `consultative`
- `customer_centric`
- `demo_first`
- `fab`
- `gap`
- `inbound`
- `meddic`
- `neat`
- `relationship`
- `sandler`
- `snap`
- `social`
- `solution`
- `transactional`
- `value`

## 6. Примечание по DAG

Flow loader поддерживает DAG-типы узлов (`choice/fork/join/parallel`),
но в текущих `states.yaml` они не используются.
