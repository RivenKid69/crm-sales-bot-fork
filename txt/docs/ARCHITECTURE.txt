# Архитектура CRM Sales Bot

## 1. Слои

### Application layer
- `src/bot.py` (`SalesBot`) — главный фасад и orchestration хода.

### Dialogue core
- `src/blackboard/` — Orchestrator + Knowledge Sources + Conflict Resolver.
- `src/state_machine.py` — хранение текущего состояния, phase, collected_data.

### NLU
- `src/classifier/` — `UnifiedClassifier`, LLM/Hybrid классификация, refinement и disambiguation.

### NLG
- `src/generator.py` — генерация ответа по action/state/context.

### Knowledge
- `src/knowledge/` — загрузка KB, category routing, retrieval, rerank.

### Infrastructure
- `src/feature_flags.py`
- `src/metrics.py`
- `src/logger.py`
- `src/settings.py` + `src/settings.yaml`

## 2. Ход обработки сообщения

1. `SalesBot.process()` собирает контекст и tone signals.
2. `UnifiedClassifier.classify()` возвращает intent + extracted_data.
3. `DialogueOrchestrator.process_turn()` собирает предложения от sources.
4. `ConflictResolver` выбирает финальное решение.
5. `StateMachine.transition_to()` фиксирует переход.
6. `ResponseGenerator.generate()` формирует текст.
7. Метрики/trace/history сохраняются.

## 3. Blackboard subsystem

Реестр источников (`src/blackboard/source_registry.py`) регистрирует 15 built-in sources:
- `GoBackGuardSource`
- `ConversationGuardSource`
- `DisambiguationSource`
- `PriceQuestionSource`
- `FactQuestionSource`
- `DataCollectorSource`
- `IntentPatternGuardSource`
- `ObjectionGuardSource`
- `ObjectionReturnSource`
- `IntentProcessorSource`
- `AutonomousDecisionSource`
- `PhaseExhaustedSource`
- `StallGuardSource`
- `TransitionResolverSource`
- `EscalationSource`

## 4. Конфигурация

SSOT:
- `src/settings.yaml` — runtime параметры подсистем.
- `src/yaml_config/constants.yaml` — taxonomy/guard/refinement/fallback constants.
- `src/yaml_config/flows/*` — flow/state definition.

## 5. Flow system

`ConfigLoader.load_flow()` подгружает `flow.yaml` и `states.yaml`.

В репозитории доступно 21 flow (включая `spin_selling`, `autonomous`, `aida`, `bant`, `meddic` и др.).

## 6. Snapshot pipeline

`SalesBot.to_snapshot()` сериализует:
- `state_machine`
- `guard`
- `fallback`
- `lead_scorer`
- `metrics`
- `context_window`
- metadata (`conversation_id`, `flow_name`, `config_name`)

`SalesBot.from_snapshot()` восстанавливает объект и переинициализирует orchestrator.
