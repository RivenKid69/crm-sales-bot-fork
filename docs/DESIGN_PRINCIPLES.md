# Design Principles

## 1. Конфигурация как SSOT

Принцип: бизнес-логика приоритетно задаётся через YAML, а не через hardcoded Python.

Основные SSOT-файлы:
- `src/settings.yaml`
- `src/yaml_config/constants.yaml`
- `src/yaml_config/flows/*/flow.yaml`
- `src/yaml_config/flows/*/states.yaml`

## 2. Fail-safe поведение

Ключевые подсистемы проектированы с graceful degradation:
- LLM вызовы (`src/llm.py`) с retry/circuit breaker/fallback.
- Классификация с fallback-path в `UnifiedClassifier`.
- Guard/fallback слой в `SalesBot`.

## 3. Расширяемость через registry/plugin pattern

- Blackboard sources подключаются через `SourceRegistry`.
- Дополнительные refinements подключаются через `RefinementPipeline`.
- Feature flags обеспечивают rollout без переписывания core.

## 4. Separation of concerns

- `SalesBot` оркестрирует.
- `StateMachine` хранит state.
- `DialogueOrchestrator` принимает решение по действию/переходу.
- `ResponseGenerator` отвечает за текст.
- `CascadeRetriever` отвечает за факты.

## 5. Observability by default

- Metrics (`src/metrics.py`)
- Decision trace (`src/decision_trace.py`)
- Event bus (`src/blackboard/event_bus.py`)

## 6. Совместимость и миграции

`StateMachine.process()` и `apply_rules()` оставлены как deprecated-compatible API для legacy-тестов.
Текущая production-логика маршрутизации хода находится в Blackboard orchestrator.
