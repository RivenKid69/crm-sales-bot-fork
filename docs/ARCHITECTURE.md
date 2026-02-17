# Архитектура CRM Sales Bot

## 1. Слои

### Application layer
- `src/bot.py` (`SalesBot`) — главный фасад и orchestration хода.

### Dialogue core
- `src/blackboard/` — Orchestrator + Knowledge Sources + Conflict Resolver.
- `src/state_machine.py` — хранение текущего состояния, phase, collected_data.

### NLU
- `src/classifier/` — `UnifiedClassifier`, LLM/Hybrid классификация, refinement и disambiguation.
- `src/classifier/style_modifier_detection.py` — разделение стилевых и семантических интентов (flag: `separate_style_modifiers`).

### NLG
- `src/generator.py` — генерация ответа по action/state/context.

### Knowledge
- `src/knowledge/` — загрузка KB, category routing, retrieval, rerank.
- `src/knowledge/autonomous_kb.py` — прямая загрузка фактов по категориям для автономного flow.
- `src/knowledge/enhanced_retrieval.py` — Enhanced Autonomous Retrieval: LLM-driven RAG pipeline (только для автономного flow).

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

## 6. Autonomous flow

Автономный flow (`--flow autonomous`) — режим, в котором LLM (Qwen) сам управляет переходами между фазами продаж без жёстких правил.

### Два режима поиска фактов

| Режим | Flag | Механизм |
|-------|------|----------|
| Базовый | `autonomous_flow: true` | Прямая загрузка по `kb_categories` из YAML состояния (`autonomous_kb.py`) |
| Enhanced | `enhanced_autonomous_retrieval: true` | LLM-driven RAG pipeline (`enhanced_retrieval.py`) |

Enhanced Autonomous Retrieval используется **только** автономным flow. Стандартные flow (spin_selling, aida и др.) используют `CascadeRetriever` напрямую.

### Enhanced Retrieval Pipeline

8-этапный pipeline, где LLM (Qwen) — мозг поиска:

1. **Fast path** — пропуск для greeting/farewell (нет поиска)
2. **Query Rewrite** — LLM разрешает местоимения и follow-up вопросы
3. **Category Routing** — LLM определяет категории KB (опционально, `CategoryRouter`)
4. **Base Retrieval** — `CascadeRetriever.search()` по переписанному запросу
5. **Complexity Detection** — rule-based определение сложных запросов
6. **Query Decomposition** — LLM разбивает сложный запрос на подзапросы
7. **RRF Fusion** — Reciprocal Rank Fusion результатов всех подзапросов
8. **State Backfill** — дополнение статическими фактами фазы (оставшийся бюджет)

Финальный контекст = query-driven факты + state-context (до `max_kb_chars`).

### Ключевые файлы

- `src/knowledge/enhanced_retrieval.py` — pipeline
- `src/knowledge/autonomous_kb.py` — базовая загрузка фактов
- `src/knowledge/category_router.py` — LLM-роутинг категорий
- `src/blackboard/sources/autonomous_decision.py` — LLM принятие решений о переходах
- `src/yaml_config/flows/autonomous/states.yaml` — конфигурация состояний

## 7. Snapshot pipeline

`SalesBot.to_snapshot()` сериализует:
- `state_machine`
- `guard`
- `fallback`
- `lead_scorer`
- `metrics`
- `context_window`
- metadata (`conversation_id`, `flow_name`, `config_name`)

`SalesBot.from_snapshot()` восстанавливает объект и переинициализирует orchestrator.
