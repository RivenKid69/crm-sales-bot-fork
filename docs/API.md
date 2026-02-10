# API Reference

Документ описывает публичные интерфейсы, которые реально используются в текущем коде.

## 1. `SalesBot` (`src/bot.py`)

### Создание

```python
from src.bot import SalesBot
from src.llm import OllamaLLM

llm = OllamaLLM()
bot = SalesBot(llm=llm, flow_name="spin_selling")
```

Параметры конструктора:
- `llm`
- `conversation_id: str | None = None`
- `enable_tracing: bool = False`
- `flow_name: str | None = None`
- `persona: str | None = None`
- `client_id: str | None = None`

### Основные методы

- `process(user_message: str) -> dict`
- `reset() -> None`
- `to_snapshot(compact_history: bool = False, history_tail_size: int = 4) -> dict`
- `from_snapshot(snapshot: dict, llm=None, history_tail: list[dict] | None = None) -> SalesBot`

### Методы наблюдаемости

- `get_metrics_summary() -> dict`
- `get_lead_score() -> dict`
- `get_guard_stats() -> dict`
- `get_disambiguation_metrics() -> dict`
- `get_decision_traces() -> list[DecisionTrace]`
- `get_last_decision_trace() -> DecisionTrace | None`

### Поля результата `process()`

Возвращаемый словарь содержит (ключи могут быть опциональными по сценарию):
- `response`
- `intent`
- `action`
- `state`
- `is_final`
- `spin_phase`
- `visited_states`
- `initial_state`
- `fallback_used`
- `fallback_tier`
- `tone`
- `frustration_level`
- `lead_score`
- `objection_detected`
- `options`
- `cta_added`
- `cta_text`
- `decision_trace`

## 2. `StateMachine` (`src/state_machine.py`)

Важный статус:
- `StateMachine.process()` и `StateMachine.apply_rules()` помечены как `deprecated`.
- Текущая оркестрация переходов идёт через `DialogueOrchestrator.process_turn()`.

Публичные методы, которые используются напрямую:
- `transition_to(next_state, action, source="...")`
- `update_data(extracted_data)`
- `increment_turn()`
- `enter_disambiguation(options, extracted_data=None)`
- `resolve_disambiguation(resolved_intent)`
- `exit_disambiguation()`
- `get_context()`
- `to_dict()` / `from_dict()`

## 3. `ConfigLoader` (`src/config_loader.py`)

- `load() -> LoadedConfig`
- `load_flow(flow_name: str) -> FlowConfig`
- `load_named(config_name: str, flow_name: Optional[str] = None) -> LoadedConfig`
- `load_bundle(config_name: str = "default", flow_name: Optional[str] = None) -> tuple[LoadedConfig, FlowConfig]`
- `reload() -> LoadedConfig`

## 4. Retriever API (`src/knowledge/retriever.py`)

Класс: `CascadeRetriever`

Методы:
- `retrieve(message, intent=None, state=None, categories=None, top_k=None) -> str`
- `retrieve_with_urls(...) -> tuple[str, list[dict]]`
- `search(message, categories=None, top_k=10) -> list[SearchResult]`
- `search_with_stats(...) -> tuple[list[SearchResult], dict]`
- `get_company_info() -> dict`

## 5. CLI точки входа

В текущем состоянии репозитория надёжный запуск:

```bash
python3 -m src.bot --flow spin_selling
```

Примечание: в `pyproject.toml` объявлен `crm-bot = src.bot:main`,
но в `src/bot.py` нет функции `main()`.
