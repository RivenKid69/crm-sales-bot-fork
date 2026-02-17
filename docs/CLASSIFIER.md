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

## 5. Style/Semantic Separation

Feature flag: `separate_style_modifiers` (OFF по умолчанию).

### Проблема

Стилевые интенты (`request_brevity`, `request_examples`, `request_summary`) могут стать primary intent и сломать маршрутизацию в `ResponseGenerator._select_template_key()`. Клиент говорит "5 человек, быстрее" — классификатор выдаёт `request_brevity` вместо `info_provided`.

### Решение

`StyleModifierDetectionLayer` (`src/classifier/style_modifier_detection.py`) — refinement layer с приоритетом `LayerPriority.HIGHEST (110)`, запускается первым в pipeline.

Разделение на два канала:
- **Канал 1 (semantic intent)** → маршрутизация: `info_provided`, `question_pricing`, ...
- **Канал 2 (style modifiers)** → рендеринг: `request_brevity`, `request_examples`, ...

### Inference semantic intent (6 стратегий)

1. **Action-based**: `last_action=ask_about_company` → `info_provided`
2. **Alternatives-based**: берёт лучший не-стилевой альтернативный интент
3. **Data-based**: есть `extracted_data` → `info_provided`
4. **Phase-based**: `discovery` → `info_provided`, `negotiation` → `objection_price`
5. **Expects-based**: `expects_response` из контекста
6. **Fallback**: `unclear`

### Выходные поля classify()

Когда flag ON:
- `style_modifiers: List[str]` — список стилевых модификаторов
- `style_separation_applied: bool` — было ли разделение
- `secondary_signals` — не содержит уже разделённые стилевые интенты

### Применение модификаторов в генераторе

`ResponseGenerator._apply_style_modifiers()` применяет модификаторы к `PersonalizationResult.style`:
- `request_brevity` → `verbosity="concise"`, `tactical_instruction="Будь краток..."`
- `request_examples` → `verbosity="detailed"`
- `request_summary` → `tactical_instruction="Суммируй..."`

При конфликте brevity + examples — побеждает brevity.

### Ключевые файлы

- `src/classifier/style_modifier_detection.py` — layer
- `src/yaml_config/constants.yaml` → `style_modifier_detection` — конфигурация
- `src/generator.py` → `_apply_style_modifiers()` — применение к рендерингу

## 6. Источники истины

- Интент-категории: `src/yaml_config/constants.yaml` -> `intents`.
- Taxonomy fallback: `intent_taxonomy` + `taxonomy_*_defaults` в том же файле.
- Паттерны top-priority: `src/classifier/intents/patterns.py`.
