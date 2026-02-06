# State Machine

## 1. Роль в текущей архитектуре

`StateMachine` (`src/state_machine.py`) сейчас отвечает за:
- хранение текущего `state`
- хранение `collected_data`
- phase metadata
- disambiguation state
- сериализацию/восстановление

Роутинг решений по интентам выполняется в Blackboard (`src/blackboard/orchestrator.py`).

## 2. Deprecated API

Методы:
- `StateMachine.apply_rules()`
- `StateMachine.process()`

Оставлены для обратной совместимости и тестов, но не являются основным runtime-путём.

## 3. Основные runtime-методы

- `transition_to(next_state, action, source=...)`
- `update_data(extracted_data)`
- `increment_turn()`
- `enter_disambiguation()`
- `resolve_disambiguation()`
- `exit_disambiguation()`
- `get_context()`
- `build_evaluator_context()`

## 4. Конфигурация

Источники:
- `FlowConfig` из `src/config_loader.py`
- `constants.yaml` через `src/yaml_config/constants.py`

Параметры берутся из YAML, а не из hardcoded map.

## 5. Circular flow

`CircularFlowManager` в `state_machine.py` хранит:
- `goback_count`
- `goback_history`
- `max_gobacks`

Go-back ограничения и цели перехода берутся из конфигурации.

## 6. Snapshot

Сериализация:
- `StateMachine.to_dict()`

Восстановление:
- `StateMachine.from_dict()`

Используется в `SalesBot.to_snapshot()` / `SalesBot.from_snapshot()`.

## 7. Blackboard bridge

`DialogueOrchestrator.process_turn()` возвращает `ResolvedDecision`,
который затем конвертируется в `sm_result` и применяется к состоянию.

Это текущий production-маршрут обработки интента.
