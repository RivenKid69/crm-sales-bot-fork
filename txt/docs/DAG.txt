# DAG Subsystem

## 1. Назначение

DAG-подсистема добавляет расширенные типы узлов для state-машины:
- `choice`
- `fork`
- `join`
- `parallel`

Файлы:
- `src/dag/models.py`
- `src/dag/executor.py`
- `src/dag/branch_router.py`
- `src/dag/sync_points.py`
- `src/dag/history.py`

## 2. Интеграция

DAG-узлы парсятся через `FlowConfig._parse_dag_nodes()` (`src/config_loader.py`).

`StateMachine` может хранить `DAGExecutionContext` и проксировать `dag_*` свойства.

## 3. Текущий статус в репозитории

В текущих flow-конфигах (`src/yaml_config/flows/*/states.yaml`) DAG-узлы типа `choice/fork/join/parallel` не используются.

Практически это значит:
- Подсистема готова в коде.
- Runtime сейчас работает как linear state flow + Blackboard orchestration.

## 4. Когда использовать

DAG нужен, если в конкретном flow требуется:
- детерминированное ветвление по условиям,
- параллельная обработка веток,
- явные точки синхронизации.
