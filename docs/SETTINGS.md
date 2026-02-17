# Settings

## 1. Основной файл

- `src/settings.yaml`
- загрузчик: `src/settings.py`

`settings.py` делает deep-merge: `DEFAULTS` + значения из YAML.

## 2. Приоритет конфигурации

### Для обычных параметров
1. `src/settings.yaml`
2. `DEFAULTS` в `src/settings.py`

### Для feature flags
1. runtime override (`flags.set_override`)
2. env (`FF_<FLAG_NAME>`)
3. `settings.yaml: feature_flags`
4. `FeatureFlags.DEFAULTS`

## 3. Структура `settings.yaml`

Текущие верхнеуровневые секции:
- `llm`
- `retriever`
- `reranker`
- `category_router`
- `generator`
- `tone_analyzer`
- `objection`
- `classifier`
- `logging`
- `conditional_rules`
- `flow`
- `feature_flags`
- `phone_validation`
- `development`

## 4. Важные параметры

### LLM
- `llm.model`
- `llm.base_url`
- `llm.timeout`

### Retriever/rerank
- `retriever.use_embeddings`
- `retriever.embedder_model`
- `retriever.thresholds.exact`
- `retriever.thresholds.lemma`
- `retriever.thresholds.semantic`
- `reranker.enabled`
- `reranker.threshold`

### Enhanced Retrieval (только автономный flow)
- `enhanced_retrieval.max_kb_chars` — бюджет символов (default: 40000)
- `enhanced_retrieval.top_k_per_sub_query` — top-k на подзапрос (default: 3)
- `enhanced_retrieval.max_sub_queries` — макс. подзапросов при декомпозиции (default: 4)
- `enhanced_retrieval.rrf_k` — параметр RRF fusion (default: 60)
- `enhanced_retrieval.rewrite_min_words` — порог для query rewrite (default: 4)
- `enhanced_retrieval.min_complexity_length` — мин. длина для complexity detection (default: 30)

### Active flow
- `flow.active`

### Feature flags
Источник: `src/feature_flags.py`.

Текущее состояние defaults:
- Всего флагов: 63
- Включено по умолчанию: 43
- Выключено по умолчанию: 20

Новые флаги:
- `separate_style_modifiers` (OFF) — разделение стилевых и семантических интентов в classifier
- `enhanced_autonomous_retrieval` (OFF) — LLM-driven RAG pipeline для автономного flow

## 5. Проверка настроек

```bash
python3 -m src.settings
```

Команда печатает merged settings и результаты базовой валидации.
