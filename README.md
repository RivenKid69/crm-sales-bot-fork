# CRM Sales Bot

Актуальная документация по проекту на основе текущего кода в `src/`.

## Что это

`CRM Sales Bot` — диалоговый B2B-бот для продаж на русском языке.

Ключевые свойства:
- YAML-driven конфигурация (`src/settings.yaml`, `src/yaml_config/`).
- Оркестрация диалога через Blackboard (`src/blackboard/`).
- Единый классификатор интентов с refinement-пайплайном (`src/classifier/unified.py`).
- Каскадный retrieval по базе знаний (`src/knowledge/retriever.py`).
- Снэпшоты сессии (`SalesBot.to_snapshot()` / `SalesBot.from_snapshot()`).

## Быстрый старт

### 1. Установить зависимости

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 2. Поднять Ollama и скачать модель

```bash
ollama serve
ollama pull qwen3:14b
```

### 3. Запустить бота

```bash
python3 -m src.bot
```

Или с выбором flow:

```bash
python3 -m src.bot --flow spin_selling
```

## Основной pipeline хода

`SalesBot.process()` (`src/bot.py`):

1. Инкремент хода и сбор контекста.
2. Анализ тона (`ToneAnalyzer`).
3. Классификация интента (`UnifiedClassifier`).
4. Blackboard-оркестрация (`DialogueOrchestrator.process_turn`).
5. Генерация ответа (`ResponseGenerator`).
6. Опциональные CTA/fallback/guard/policy overlays.
7. Запись метрик, истории и decision trace.

## Архитектура (кратко)

- `src/bot.py` — фасад и orchestration уровня приложения.
- `src/state_machine.py` — состояние, collected data, сериализация.
- `src/blackboard/` — knowledge sources, resolver конфликтов, event bus.
- `src/classifier/` — primary classifier + refinement + disambiguation.
- `src/knowledge/` — загрузка KB, category routing, retrieval, reranking.
- `src/generator.py` — генерация ответа по action + контексту.

## Конфигурация

### `src/settings.yaml`

Основные секции:
- `llm`
- `retriever`
- `reranker`
- `category_router`
- `generator`
- `tone_analyzer`
- `objection`
- `classifier`
- `conditional_rules`
- `flow`
- `feature_flags`

### Feature flags

- Источник: `src/feature_flags.py`
- Всего флагов: `62`
- По умолчанию включено: `43`
- По умолчанию выключено: `19`

Приоритет значений:
1. runtime override (`flags.set_override`)
2. переменные окружения `FF_<FLAG_NAME>`
3. `settings.yaml`
4. `FeatureFlags.DEFAULTS`

## Flows

Flow-загрузчик: `ConfigLoader.load_flow()`.

Текущие flow в `src/yaml_config/flows/`:
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

## База знаний

Файлы знаний: `src/knowledge/data/*.yaml`.

Категории (17):
- `analytics`
- `competitors`
- `employees`
- `equipment`
- `faq`
- `features`
- `fiscal`
- `integrations`
- `inventory`
- `mobile`
- `pricing`
- `products`
- `promotions`
- `regions`
- `stability`
- `support`
- `tis`

## Тесты

```bash
pytest
```

## Документация

- `docs/ARCHITECTURE.md` — текущая архитектура.
- `docs/API.md` — публичные интерфейсы.
- `docs/CLASSIFIER.md` — классификация и refinement.
- `docs/SETTINGS.md` — параметры и precedence конфигурации.
- `docs/state_machine.md` — state machine + Blackboard интеграция.
- `docs/KNOWLEDGE.md` — retrieval и структура KB.
- `docs/INTENT_TAXONOMY.md` — таксономия интентов.
- `docs/VOICE.md` — состояние голосового контура.
- `docs/PHASES.md` — эволюция фаз.
- `docs/DAG.md` — DAG-подсистема и текущий статус.
- `docs/DESIGN_PRINCIPLES.md` — архитектурные принципы.
- `docs/INTEGRATION_SPEC.md` — план интеграции (без изменений).
