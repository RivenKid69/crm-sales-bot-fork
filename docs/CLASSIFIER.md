# Classifier

## 1. Актуальный вход

Точка входа: `UnifiedClassifier` (`src/classifier/unified.py`).

Базовый pipeline:
1. Priority patterns (`classifier/intents/patterns.py`).
2. Primary classifier:
   - `LLMClassifier`, если `flags.llm_classifier == True`.
   - `HybridClassifier`, если флаг выключен.
3. Refinement:
   - `RefinementPipeline`, если `flags.refinement_pipeline == True`.
   - иначе legacy-слои.
4. Unified disambiguation (`DisambiguationDecisionEngine`), если `flags.unified_disambiguation == True`.

## 2. Что возвращает `classify()`

Базовые поля:
- `intent`
- `confidence`
- `extracted_data`
- `method`

Дополнительные поля (когда применимо):
- `refined`
- `original_intent`
- `refinement_chain`
- `disambiguation_triggered`
- `disambiguation_options`
- `disambiguation_decision`

## 3. Ключевые модули

- `src/classifier/llm/classifier.py`
- `src/classifier/hybrid.py`
- `src/classifier/refinement_pipeline.py`
- `src/classifier/refinement_layers.py`
- `src/classifier/disambiguation_engine.py`
- `src/classifier/disambiguation_resolution_layer.py`
- `src/classifier/extractors/data_extractor.py`

## 4. Feature flags, влияющие на классификатор

Основные:
- `llm_classifier`
- `refinement_pipeline`
- `classification_refinement`
- `composite_refinement`
- `objection_refinement`
- `data_aware_refinement`
- `first_contact_refinement`
- `confidence_calibration`
- `unified_disambiguation`
- `option_selection_refinement`

## 5. Источники истины

- Интент-категории: `src/yaml_config/constants.yaml` -> `intents`.
- Taxonomy fallback: `intent_taxonomy` + `taxonomy_*_defaults` в том же файле.
- Паттерны top-priority: `src/classifier/intents/patterns.py`.
