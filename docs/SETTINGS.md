# Settings — Конфигурация CRM Sales Bot

## Обзор

Все настраиваемые параметры бота вынесены в файлы конфигурации:

- **`src/settings.yaml`** — основные настройки (LLM, retriever, feature flags)
- **`src/yaml_config/`** — структурированная конфигурация (states, flows, constants)

Это позволяет изменять поведение системы без правки кода.

## Файл настроек

**Расположение:** `src/settings.yaml`

```yaml
llm:
  model: "qwen3:14b"
  base_url: "http://localhost:11434"
  timeout: 120
  stream: false

retriever:
  use_embeddings: true
  embedder_model: "ai-forever/FRIDA"
  thresholds:
    exact: 1.0
    lemma: 0.15
    semantic: 0.5
  default_top_k: 2

reranker:
  enabled: true
  model: "BAAI/bge-reranker-v2-m3"
  threshold: 0.5
  candidates_count: 10

category_router:
  enabled: true
  top_k: 3
  fallback_categories:
    - "faq"
    - "features"

generator:
  max_retries: 3
  history_length: 4
  retriever_top_k: 2
  allowed_english_words:
    - "crm"
    - "api"
    - "ok"
    - "id"
    - "ip"
    - "sms"
    - "email"
    - "excel"
    - "whatsapp"
    - "telegram"
    - "hr"
    - "pos"
    - "erp"
    - "rest"
    - "oauth"
    - "ssl"
    - "tls"
    - "jwt"
    - "sla"
    - "http"
    - "https"
    - "url"
    - "usb"
    - "wifi"
    - "qr"
    - "pdf"
    - "sql"
    - "csv"
    - "ofd"
    - "mini"
    - "lite"
    - "standard"
    - "pro"
    - "basic"
    - "team"
    - "business"
    - "demo"
    - "saas"
    - "cloud"
    - "online"
    - "kaspi"
    - "halyk"
    - "iiko"
    - "poster"

tone_analyzer:
  style_instructions:
    informal: "Отвечай менее формально, дружелюбно. Можно использовать разговорные обороты."
    formal: ""
  thresholds:
    tier1_high_confidence: 0.85
    tier2_threshold: 0.70
    tier3_threshold: 0.65
    min_confidence: 0.30
  semantic:
    threshold: 0.70
    ambiguity_delta: 0.15

objection:
  semantic_threshold: 0.75
  ambiguity_delta: 0.10
  max_attempts_per_type: 2
  counters:
    price: "Стоимость окупается за счёт экономии времени и роста продаж. Наши клиенты в среднем увеличивают выручку на 20%."
    competitor: "Многие переходят к нам с других систем. Wipon проще во внедрении и дешевле в обслуживании."
    no_time: "Внедрение занимает всего 1-2 дня. Мы помогаем на каждом этапе."
    think: "Конечно, это важное решение. Могу прислать материалы для изучения или ответить на конкретные вопросы."
    no_need: "Многие так думали, пока не попробовали. Давайте покажу на примере вашей ситуации."
    trust: "Мы работаем с 2015 года, более 5000 клиентов. Могу дать контакты для отзывов."
    timing: "Понимаю, сейчас не лучший момент. Когда будет удобно вернуться к разговору?"
    complexity: "Система интуитивно понятна, обучение занимает пару часов. Есть бесплатная поддержка."

classifier:
  weights:
    root_match: 1.0
    phrase_match: 2.0
    lemma_match: 1.5
  merge_weights:
    root_classifier: 0.6
    lemma_classifier: 0.4
  thresholds:
    high_confidence: 0.7
    min_confidence: 0.3

logging:
  level: "INFO"
  log_llm_requests: false
  log_retriever_results: false

conditional_rules:
  enable_tracing: true

feature_flags:
  structured_logging: true
  metrics_tracking: true
  multi_tier_fallback: true
  conversation_guard: true
  tone_analysis: true
  response_variations: true
  personalization: false
  lead_scoring: false
  circular_flow: false
  objection_handler: false
  cta_generator: true

phone_validation:
  ru_mobile_range: [900, 999]
  kz_mobile_ranges:
    - [700, 709]
  kz_mobile_explicit: [747, 771, 775, 776, 777, 778]
  city_codes: [495, 499, 812, 343, 383, 861, 727, 717]

development:
  debug: false
  skip_embeddings: false
```

## Параметры

### LLM (Ollama Server)

| Параметр | Тип | По умолчанию | Описание |
|----------|-----|--------------|----------|
| `model` | string | `"qwen3:14b"` | Модель Ollama (qwen3:14b - стандарт проекта) |
| `base_url` | string | `"http://localhost:11434"` | URL Ollama сервера (native API) |
| `timeout` | int | `120` | Таймаут запроса в секундах |
| `stream` | bool | `false` | Режим стриминга |

**Запуск Ollama сервера:**
```bash
# Установка
curl -fsSL https://ollama.ai/install.sh | sh

# Скачать модель
ollama pull qwen3:14b

# Запуск
ollama serve
```

**Требования:** ~12-16 GB VRAM, CUDA GPU

### RETRIEVER (Поиск по базе знаний)

| Параметр | Тип | По умолчанию | Описание |
|----------|-----|--------------|----------|
| `use_embeddings` | bool | `true` | Использовать семантический поиск |
| `embedder_model` | string | `"ai-forever/FRIDA"` | Модель для эмбеддингов (ruMTEB avg ~71) |
| `thresholds.exact` | float | `1.0` | Порог для exact match |
| `thresholds.lemma` | float | `0.15` | Порог для lemma match |
| `thresholds.semantic` | float | `0.5` | Порог для semantic match |
| `default_top_k` | int | `2` | Количество результатов по умолчанию |

**Пороги:**
- `exact: 1.0` — требуется минимум 1 полное совпадение keyword
- `lemma: 0.15` — низкий порог для широкого охвата
- `semantic: 0.5` — средний порог для баланса точности/охвата

### RERANKER (Переоценка результатов)

| Параметр | Тип | По умолчанию | Описание |
|----------|-----|--------------|----------|
| `enabled` | bool | `true` | Включить reranker fallback |
| `model` | string | `"BAAI/bge-reranker-v2-m3"` | Модель cross-encoder |
| `threshold` | float | `0.5` | Порог score ниже которого включается |
| `candidates_count` | int | `10` | Сколько кандидатов переоценивать |

### CATEGORY ROUTER (LLM-классификация)

| Параметр | Тип | По умолчанию | Описание |
|----------|-----|--------------|----------|
| `enabled` | bool | `true` | Включить LLM-классификацию |
| `top_k` | int | `3` | Количество возвращаемых категорий |
| `fallback_categories` | list | `["faq", "features"]` | Категории по умолчанию при ошибке |

### GENERATOR (Генерация ответов)

| Параметр | Тип | По умолчанию | Описание |
|----------|-----|--------------|----------|
| `max_retries` | int | `3` | Количество retry при иностранном тексте |
| `history_length` | int | `4` | Количество сообщений в контексте |
| `retriever_top_k` | int | `2` | Количество фактов из базы знаний |
| `allowed_english_words` | list | см. выше | Разрешённые английские слова |

### TONE ANALYZER (Анализ тона)

| Параметр | Тип | По умолчанию | Описание |
|----------|-----|--------------|----------|
| `style_instructions.informal` | string | см. файл | Инструкция для неформального стиля |
| `style_instructions.formal` | string | `""` | Инструкция для формального стиля |
| `thresholds.tier1_high_confidence` | float | `0.85` | Порог высокой уверенности для Tier 1 (regex) |
| `thresholds.tier2_threshold` | float | `0.70` | Порог для Tier 2 (semantic) |
| `thresholds.tier3_threshold` | float | `0.65` | Порог для Tier 3 (LLM) |
| `thresholds.min_confidence` | float | `0.30` | Минимальная уверенность |
| `semantic.threshold` | float | `0.70` | Порог уверенности semantic |
| `semantic.ambiguity_delta` | float | `0.15` | Разница top‑1/top‑2 для неоднозначности |

### OBJECTION (Обработка возражений)

| Параметр | Тип | По умолчанию | Описание |
|----------|-----|--------------|----------|
| `semantic_threshold` | float | `0.75` | Минимальная уверенность semantic детекции |
| `ambiguity_delta` | float | `0.10` | Разница top‑1/top‑2 для неоднозначности |
| `max_attempts_per_type` | int | `2` | Максимум попыток по одному типу возражений |
| `counters` | map | см. файл | Контраргументы по типам возражений |

### CLASSIFIER (Классификация интентов)

| Параметр | Тип | По умолчанию | Описание |
|----------|-----|--------------|----------|
| `weights.root_match` | float | `1.0` | Вес совпадения по корню (для HybridClassifier) |
| `weights.phrase_match` | float | `2.0` | Вес точного совпадения фразы |
| `weights.lemma_match` | float | `1.5` | Вес совпадения по лемме |
| `merge_weights.root_classifier` | float | `0.6` | Вес RootClassifier при слиянии |
| `merge_weights.lemma_classifier` | float | `0.4` | Вес LemmaClassifier при слиянии |
| `thresholds.high_confidence` | float | `0.7` | Порог высокой уверенности |
| `thresholds.min_confidence` | float | `0.3` | Минимальная уверенность |

### LOGGING (Логирование)

| Параметр | Тип | По умолчанию | Описание |
|----------|-----|--------------|----------|
| `level` | string | `"INFO"` | Уровень логирования |
| `log_llm_requests` | bool | `false` | Логировать запросы к LLM |
| `log_retriever_results` | bool | `false` | Логировать результаты retriever |

### CONDITIONAL RULES (Условные правила)

| Параметр | Тип | По умолчанию | Описание |
|----------|-----|--------------|----------|
| `enable_tracing` | bool | `true` | Включить трассировку правил |
| `log_level` | string | `"INFO"` | Уровень логирования правил |
| `log_context` | bool | `false` | Логировать контекст при проверке |
| `log_each_condition` | bool | `false` | Логировать каждую проверку |
| `validate_on_startup` | bool | `true` | Валидация при старте |
| `coverage_threshold` | float | `0.8` | Минимальное покрытие условий в тестах |

Примечание: в `settings.yaml` сейчас задан только `enable_tracing`. Остальные параметры берутся из defaults в `src/settings.py` и могут быть переопределены при добавлении в YAML.

### FEATURE FLAGS (Управление фичами)

Feature flags позволяют постепенно включать новые возможности без изменения кода. В системе реализовано **62 флага** (см. `src/feature_flags.py`), организованные по фазам разработки и категориям риска. `src/settings.yaml` задаёт базовые значения для ключевых флагов, остальные берутся из defaults.

#### Статус флагов по категориям

- **Production** (безопасные, включены в production)
- **Safe** (испытанные, рекомендуется включать)
- **Risky** (требуют калибровки, включать осторожно)
- **Experimental** (новые, отключены по умолчанию)

#### Фаза 0: Инфраструктура (Phase 0)

Базовые компоненты и логирование. Статус: Production.

| Флаг | Default | Статус | Описание |
|------|---------|--------|----------|
| `structured_logging` | `true` | Production | JSON логи для production окружения |
| `metrics_tracking` | `true` | Production | Трекинг метрик диалогов и KPI |

**Зависимости:** Нет (базовый уровень)

#### Фаза 1: Защита и надёжность (Phase 1)

Критичные механизмы защиты от зацикливания и деградации. Статус: Production.

| Флаг | Default | Статус | Описание |
|------|---------|--------|----------|
| `multi_tier_fallback` | `true` | Production | 4-уровневый fallback: TIER_1 (intent)→ TIER_2 (retrieve)→ TIER_3 (LLM)→ TIER_4 (default) |
| `conversation_guard` | `true` | Production | Защита от зацикливания: отслеживание repeated states, max_turns_in_state |
| `conversation_guard_in_pipeline` | `false` | Experimental | ConversationGuard внутри Blackboard pipeline для более раннего срабатывания |

**Зависимости:** Нет (базовый уровень)

#### Фаза 2: Естественность диалога (Phase 2)

Анализ тона, вариативность ответов, качество диалога. Статус: Production.

| Флаг | Default | Статус | Описание |
|------|---------|--------|----------|
| `tone_analysis` | `true` | Production | Базовый анализ тона клиента (regex Tier 1) для определения стиля ответа |
| `cascade_tone_analyzer` | `true` | Production | Каскадный анализатор тона с тремя уровнями fallback |
| `tone_semantic_tier2` | `true` | Safe | Tier 2: FRIDA semantic embeddings для анализа тона |
| `tone_llm_tier3` | `true` | Safe | Tier 3: LLM fallback при низкой уверенности Tier 2 |
| `response_variations` | `true` | Production | Вариативность ответов: избегание повторяющихся фраз и шаблонов |
| `response_diversity` | `true` | Safe | Post-processing замена монотонных вступлений на разнообразные варианты |
| `response_diversity_logging` | `true` | Safe | Логирование замен для мониторинга diversity engine |
| `question_deduplication` | `true` | Safe | Фильтрация повторяющихся вопросов на основе collected_data |
| `question_deduplication_logging` | `true` | Safe | Логирование фильтраций для мониторинга |
| `apology_system` | `true` | Safe | Гарантированное добавление извинений при обнаружении frustration |
| `response_deduplication` | `true` | Safe | Проверка на дублирующиеся ответы в пределах сессии |
| `price_question_override` | `true` | Safe | Intent-aware override для вопросов о цене |
| `personalization` | `false` | Experimental | Персонализация ответов на основе профиля клиента (v1, legacy) |

**Зависимости:**
- `tone_semantic_tier2` требует `cascade_tone_analyzer=true`
- `tone_llm_tier3` требует `cascade_tone_analyzer=true`

#### Фаза 3: Оптимизация SPIN Flow (Phase 3)

Продвинутые механизмы управления диалогом и генерация действий. Статус: Experimental.

| Флаг | Default | Статус | Описание |
|------|---------|--------|----------|
| `lead_scoring` | `false` | Risky | Скоринг лидов для адаптивного SPIN (требует калибровки) |
| `circular_flow` | `false` | Risky | Возврат назад по фазам SPIN (опасно, может привести к зацикливанию) |
| `objection_handler` | `false` | Experimental | Продвинутая обработка возражений с контраргументами |
| `cta_generator` | `true` | Safe | Генерация Call-to-Action в зависимости от фазы диалога |
| `dynamic_cta_fallback` | `false` | Experimental | Динамические подсказки в fallback tier_2 на основе контекста |

**Зависимости:** Нет (опциональные механизмы)

#### Фаза 4: Классификация и дизамбигуация (Phase 4)

Улучшенная классификация интентов и детекция возражений. Статус: Safe/Production.

| Флаг | Default | Статус | Описание |
|------|---------|--------|----------|
| `intent_disambiguation` | `false` | Legacy | Уточнение намерения при близких scores (HybridClassifier, deprecated) |
| `unified_disambiguation` | `true` | Safe | Унифицированный disambiguation для LLM и HybridClassifier |
| `cascade_classifier` | `true` | Production | Каскадный классификатор с эмбеддингами для семантического fallback |
| `semantic_objection_detection` | `true` | Production | Semantic fallback для детекции возражений при низкой уверенности |
| `confidence_router` | `true` | Safe | Gap-based решения и graceful degradation при неоднозначности |
| `confidence_router_logging` | `true` | Safe | Логирование слепых зон для self-learning системы |
| `confidence_calibration` | `true` | Safe | Калибровка confidence для решения проблемы overconfident LLM |
| `classification_refinement` | `true` | Safe | Контекстное уточнение классификации коротких ответов |
| `secondary_intent_detection` | `true` | Safe | Детекция secondary intents в composite сообщениях |
| `objection_refinement` | `true` | Safe | Контекстная валидация objection классификаций |
| `composite_refinement` | `true` | Safe | Приоритет извлечения данных над мета-интентами |
| `option_selection_refinement` | `true` | Safe | Обработка выбора вариантов ("1", "2", "первое") |

**Зависимости:**
- `semantic_objection_detection` требует `cascade_classifier=true`
- `confidence_router` работает как с LLM, так и с HybridClassifier

#### Фаза 5: Контекстная политика диалога (Phase 5)

Продвинутое управление контекстом и память диалога. Статус: Safe/Experimental.

| Флаг | Default | Статус | Описание |
|------|---------|--------|----------|
| `context_full_envelope` | `true` | Production | Полный ContextEnvelope для всех подсистем (source_signal, confidence, directives) |
| `context_shadow_mode` | `false` | Experimental | Shadow mode: логируем решения policy без применения (для A/B тестирования) |
| `context_response_directives` | `true` | Safe | ResponseDirectives для кастомизации ответов генератором |
| `context_policy_overlays` | `true` | Safe | DialoguePolicy action/transition overrides на основе контекста |
| `context_engagement_v2` | `false` | Experimental | Улучшенный расчёт engagement на основе interaction patterns |
| `context_cta_memory` | `false` | Experimental | CTA с учётом episodic memory и истории CTA |

**Зависимости:**
- `context_response_directives` требует `context_full_envelope=true`
- `context_policy_overlays` требует `context_full_envelope=true`
- `context_engagement_v2` требует `context_full_envelope=true`
- `context_cta_memory` требует `context_full_envelope=true`

#### Фаза 5.5: Очистка и рефайнмент (Refinement Pipeline)

Универсальный pipeline для улучшения классификации и обработки данных. Статус: Safe.

| Флаг | Default | Статус | Описание |
|------|---------|--------|----------|
| `refinement_pipeline` | `true` | Safe | Использовать универсальный RefinementPipeline вместо отдельных слоёв |
| `data_aware_refinement` | `true` | Safe | Promote unclear→info_provided когда данные извлечены |
| `first_contact_refinement` | `true` | Safe | First contact objection refinement layer (защита в первом контакте) |
| `greeting_state_safety` | `true` | Safe | Category-based greeting transition overrides для безопасности |
| `greeting_context_refinement` | `true` | Safe | Greeting context refinement layer для улучшения первого сообщения |
| `structural_frustration_detection` | `true` | Safe | Behavioral frustration detection из диалоговых паттернов |

**Зависимости:** Нет (все флаги независимы)

#### Фаза 6: Guard и Fallback улучшения (Guard/Fallback Fixes)

Специализированные фиксы для механизмов защиты. Статус: Production.

| Флаг | Default | Статус | Описание |
|------|---------|--------|----------|
| `guard_informative_intent_check` | `true` | Production | Проверка информативных интентов перед TIER_3 fallback |
| `guard_skip_resets_fallback` | `true` | Production | Сброс fallback_response после skip action |
| `universal_stall_guard` | `true` | Safe | Universal max-turns-in-state forced ejection |
| `stall_guard_dual_proposal` | `true` | Safe | StallGuard proposes action + transition simultaneously |
| `phase_exhausted_source` | `true` | Safe | PhaseExhaustedSource: options menu когда фаза застопорена |
| `phase_completion_gating` | `true` | Safe | has_completed_minimum_phases condition для контроля прогресса |

**Зависимости:** Нет (все механизмы независимы)

#### Фаза 7: Персонализация v2 (Personalization V2)

Адаптивная персонализация с поведенческой адаптацией. Статус: Experimental.

| Флаг | Default | Статус | Описание |
|------|---------|--------|----------|
| `personalization_v2` | `false` | Experimental | V2 engine с behavioral adaptation и machine learning |
| `personalization_adaptive_style` | `false` | Experimental | AdaptiveStyleSelector для выбора стиля общения |
| `personalization_semantic_industry` | `false` | Experimental | IndustryDetectorV2 semantic matching для определения отрасли |
| `personalization_session_memory` | `false` | Experimental | EffectiveActionTracker для session memory и action history |

**Зависимости:**
- `personalization_adaptive_style` требует `personalization_v2=true`
- `personalization_semantic_industry` требует `personalization_v2=true`
- `personalization_session_memory` требует `personalization_v2=true`

#### Классификатор (Classifier Selection)

Выбор механизма классификации интентов. Статус: Production.

| Флаг | Default | Статус | Описание |
|------|---------|--------|----------|
| `llm_classifier` | `true` | Production | Использовать LLM классификатор вместо HybridClassifier |

**Зависимости:** Нет (выбор один из двух подходов)

#### Экспериментальные режимы (Experimental/Diagnostic)

Режимы для диагностики и расширенного тестирования. Статус: Experimental.

| Флаг | Default | Статус | Описание |
|------|---------|--------|----------|
| `simulation_diagnostic_mode` | `false` | Experimental | Диагностический режим с повышенными лимитами для обнаружения ошибок |
| `intent_pattern_guard` | `false` | Experimental | Configurable intent pattern detection (Change 7) |
| `comparison_refinement` | `false` | Experimental | Comparison refinement layer (Change 8) |
| `autonomous_flow` | `false` | Experimental | LLM-driven sales flow без YAML правил (полная автономия) |

**Зависимости:** Нет (все независимые режимы)

#### Таблица всех флагов (сортировка по названию)

| Флаг | Default | Фаза | Статус | Описание |
|------|---------|------|--------|----------|
| `apology_system` | `true` | 2 | Safe | Гарантированное добавление извинений при frustration |
| `autonomous_flow` | `false` | 6 | Experimental | LLM-driven sales flow без YAML правил |
| `cascade_classifier` | `true` | 4 | Production | Каскадный классификатор с семантическим fallback |
| `cascade_tone_analyzer` | `true` | 2 | Production | Каскадный анализатор тона с тремя уровнями |
| `circular_flow` | `false` | 3 | Risky | Возврат назад по фазам SPIN |
| `classification_refinement` | `true` | 4 | Safe | Контекстное уточнение коротких ответов |
| `comparison_refinement` | `false` | 6 | Experimental | Comparison refinement layer |
| `composite_refinement` | `true` | 4 | Safe | Приоритет данных над мета-интентами |
| `confidence_calibration` | `true` | 4 | Safe | Калибровка confidence для overconfident LLM |
| `confidence_router` | `true` | 4 | Safe | Gap-based решения и graceful degradation |
| `confidence_router_logging` | `true` | 4 | Safe | Логирование слепых зон |
| `context_cta_memory` | `false` | 5 | Experimental | CTA с episodic memory |
| `context_engagement_v2` | `false` | 5 | Experimental | Улучшенный расчёт engagement |
| `context_full_envelope` | `true` | 5 | Production | Полный ContextEnvelope |
| `context_policy_overlays` | `true` | 5 | Safe | DialoguePolicy overrides |
| `context_response_directives` | `true` | 5 | Safe | ResponseDirectives для генератора |
| `context_shadow_mode` | `false` | 5 | Experimental | Shadow mode для policy |
| `conversation_guard` | `true` | 1 | Production | Защита от зацикливания |
| `conversation_guard_in_pipeline` | `false` | 1 | Experimental | ConversationGuard в pipeline |
| `cta_generator` | `true` | 3 | Safe | Генерация Call-to-Action |
| `data_aware_refinement` | `true` | 5.5 | Safe | Promote info_provided при извлечении данных |
| `dynamic_cta_fallback` | `false` | 3 | Experimental | Динамические CTA в fallback |
| `first_contact_refinement` | `true` | 5.5 | Safe | First contact objection refinement |
| `greeting_context_refinement` | `true` | 5.5 | Safe | Greeting context refinement |
| `greeting_state_safety` | `true` | 5.5 | Safe | Category-based greeting overrides |
| `guard_informative_intent_check` | `true` | 6 | Production | Проверка информативных интентов |
| `guard_skip_resets_fallback` | `true` | 6 | Production | Сброс fallback после skip |
| `intent_disambiguation` | `false` | 4 | Legacy | Уточнение намерения (deprecated) |
| `intent_pattern_guard` | `false` | 6 | Experimental | Configurable intent pattern detection |
| `lead_scoring` | `false` | 3 | Risky | Скоринг лидов |
| `llm_classifier` | `true` | Classifier | Production | LLM вместо HybridClassifier |
| `metrics_tracking` | `true` | 0 | Production | Трекинг метрик диалогов |
| `multi_tier_fallback` | `true` | 1 | Production | 4-уровневый fallback |
| `objection_handler` | `false` | 3 | Experimental | Продвинутая обработка возражений |
| `objection_refinement` | `true` | 4 | Safe | Контекстная валидация возражений |
| `option_selection_refinement` | `true` | 4 | Safe | Обработка выбора вариантов |
| `personalization` | `false` | 2 | Experimental | Персонализация v1 (legacy) |
| `personalization_adaptive_style` | `false` | 7 | Experimental | AdaptiveStyleSelector |
| `personalization_semantic_industry` | `false` | 7 | Experimental | IndustryDetectorV2 |
| `personalization_session_memory` | `false` | 7 | Experimental | EffectiveActionTracker |
| `personalization_v2` | `false` | 7 | Experimental | Персонализация v2 |
| `phase_completion_gating` | `true` | 6 | Safe | Phase completion control |
| `phase_exhausted_source` | `true` | 6 | Safe | Options menu при застое фазы |
| `price_question_override` | `true` | 2 | Safe | Intent-aware override для цены |
| `question_deduplication` | `true` | 2 | Safe | Фильтрация повторяющихся вопросов |
| `question_deduplication_logging` | `true` | 2 | Safe | Логирование фильтраций |
| `refinement_pipeline` | `true` | 5.5 | Safe | Универсальный RefinementPipeline |
| `response_deduplication` | `true` | 2 | Safe | Проверка дублирующихся ответов |
| `response_diversity` | `true` | 2 | Safe | Anti-monotony engine |
| `response_diversity_logging` | `true` | 2 | Safe | Логирование replacements |
| `response_variations` | `true` | 2 | Production | Вариативность ответов |
| `secondary_intent_detection` | `true` | 4 | Safe | Secondary intents в composite |
| `semantic_objection_detection` | `true` | 4 | Production | Semantic fallback для возражений |
| `simulation_diagnostic_mode` | `false` | 6 | Experimental | Диагностический режим |
| `stall_guard_dual_proposal` | `true` | 6 | Safe | Dual action + transition |
| `structural_frustration_detection` | `true` | 5.5 | Safe | Behavioral frustration detection |
| `structured_logging` | `true` | 0 | Production | JSON логи для production |
| `tone_analysis` | `true` | 2 | Production | Анализ тона (базовый Tier 1) |
| `tone_llm_tier3` | `true` | 2 | Safe | Tier 3 (LLM) для тона |
| `tone_semantic_tier2` | `true` | 2 | Safe | Tier 2 (FRIDA) для тона |
| `unified_disambiguation` | `true` | 4 | Safe | Unified disambiguation |
| `universal_stall_guard` | `true` | 6 | Safe | Max-turns-in-state ejection |

#### Переопределение через environment variables

Все флаги можно переопределить через переменные окружения:

```bash
# Формат: FF_<FLAG_NAME>=true|false
FF_LLM_CLASSIFIER=false python bot.py
FF_TONE_ANALYSIS=true python bot.py
FF_LEAD_SCORING=true python bot.py

# Несколько флагов
FF_LLM_CLASSIFIER=false FF_TONE_ANALYSIS=true FF_CIRCULAR_FLOW=true python bot.py
```

Приоритет загрузки (от высшего к низшему):
1. Environment variables (`FF_*`)
2. settings.yaml (`feature_flags` раздел)
3. Defaults (в коде FeatureFlags.DEFAULTS)

#### Группы флагов для управления

Флаги организованы в группы для удобного управления:

```python
# Production-safe группа
flags.enable_group("safe")  # все проверенные флаги

# По фазам
flags.enable_group("phase_0")    # инфраструктура
flags.enable_group("phase_1")    # защита
flags.enable_group("phase_2")    # естественность
flags.enable_group("phase_3")    # SPIN optimization
flags.enable_group("phase_4")    # классификация
flags.enable_group("phase_5")    # контекст

# Рискованные флаги
flags.disable_group("risky")  # отключить circular_flow, lead_scoring

# Контекстная политика
flags.enable_group("context_all")   # все context флаги
flags.enable_group("context_safe")  # только safe (context_full_envelope, directives)

# Тон анализа
flags.enable_group("tone_full")     # все уровни cascade analyzer
flags.enable_group("tone_safe")     # только базовый Tier 1

# Персонализация v2
flags.enable_group("personalization_v2_full")  # все компоненты

# Специализированные группы
flags.enable_group("guard_fixes")           # guard/fallback улучшения
flags.enable_group("robust_classification") # confidence router
flags.enable_group("refinement_pipeline_all")  # все refinement слои
flags.enable_group("stall_guard")           # anti-stall механизмы
```

#### Зависимости между флагами

Некоторые флаги требуют, чтобы другие флаги были включены:

**Cascade Analyzer (Phase 2):**
- `tone_semantic_tier2` → требует `cascade_tone_analyzer=true`
- `tone_llm_tier3` → требует `cascade_tone_analyzer=true`

**Context Policy (Phase 5):**
- `context_response_directives` → требует `context_full_envelope=true`
- `context_policy_overlays` → требует `context_full_envelope=true`
- `context_engagement_v2` → требует `context_full_envelope=true`
- `context_cta_memory` → требует `context_full_envelope=true`
- `context_shadow_mode` → требует `context_full_envelope=true`

**Personalization V2 (Phase 7):**
- `personalization_adaptive_style` → требует `personalization_v2=true`
- `personalization_semantic_industry` → требует `personalization_v2=true`
- `personalization_session_memory` → требует `personalization_v2=true`

**Cascade Classifier (Phase 4):**
- `semantic_objection_detection` → требует `cascade_classifier=true`

**Classifier Selection:**
- Система выбирает между LLM и HybridClassifier на основе `llm_classifier`
- Все флаги Phase 4 работают с обоими классификаторами

#### Профили флагов для разных окружений

**Production Profile (максимальная надёжность)**

```yaml
feature_flags:
  # Phase 0: Infrastructure (production-ready)
  structured_logging: true
  metrics_tracking: true

  # Phase 1: Safety (critical, always on)
  multi_tier_fallback: true
  conversation_guard: true
  conversation_guard_in_pipeline: false

  # Phase 2: Dialog Quality (production-stable)
  tone_analysis: true
  cascade_tone_analyzer: true
  tone_semantic_tier2: true
  tone_llm_tier3: true
  response_variations: true
  response_diversity: true
  question_deduplication: true
  apology_system: true

  # Phase 3: SPIN (safe only, risky disabled)
  lead_scoring: false
  circular_flow: false
  objection_handler: false
  cta_generator: true
  dynamic_cta_fallback: false

  # Phase 4: Classification (production)
  cascade_classifier: true
  semantic_objection_detection: true
  confidence_router: true
  unified_disambiguation: true
  classification_refinement: true

  # Phase 5: Context (safe components)
  context_full_envelope: true
  context_response_directives: true
  context_policy_overlays: true
  context_shadow_mode: false
  context_engagement_v2: false
  context_cta_memory: false

  # Guard Fixes (all enabled)
  guard_informative_intent_check: true
  guard_skip_resets_fallback: true
  universal_stall_guard: true

  # Experimental (disabled)
  personalization: false
  personalization_v2: false
  autonomous_flow: false
```

**Development Profile (максимум функционала)**

```yaml
feature_flags:
  # Все Phase 0-4 включены
  structured_logging: true
  metrics_tracking: true
  multi_tier_fallback: true
  conversation_guard: true

  # Phase 2: все варианты
  tone_analysis: true
  cascade_tone_analyzer: true
  tone_semantic_tier2: true
  tone_llm_tier3: true
  response_variations: true
  response_diversity: true

  # Phase 3: включены experimental
  lead_scoring: true
  circular_flow: true  # ОСТОРОЖНО!
  objection_handler: true
  cta_generator: true
  dynamic_cta_fallback: true

  # Phase 5: все варианты
  context_full_envelope: true
  context_response_directives: true
  context_policy_overlays: true
  context_shadow_mode: true  # для A/B тестирования
  context_engagement_v2: true
  context_cta_memory: true

  # Phase 7: Personalization v2
  personalization_v2: true
  personalization_adaptive_style: true
  personalization_semantic_industry: true
  personalization_session_memory: true

  # Experimental
  autonomous_flow: true
  simulation_diagnostic_mode: true
```

**Testing Profile (минимум для быстрого тестирования)**

```yaml
feature_flags:
  # Критичные только
  multi_tier_fallback: true
  conversation_guard: true

  # Phase 2: базовое качество
  tone_analysis: true
  response_variations: true

  # Остальное отключено для скорости
  cascade_tone_analyzer: false
  cascade_classifier: false
  context_full_envelope: false
  personalization_v2: false
```

### FLOW (Конфигурация диалогового flow)

| Параметр | Тип | По умолчанию | Описание |
|----------|-----|--------------|----------|
| `active` | string | `"spin_selling"` | Активный flow из `yaml_config/flows/` |

Примечание: раздел `flow` может отсутствовать в `settings.yaml` — тогда используется default из `src/settings.py`.

**Доступные flows:**
- `spin_selling`, `aida`, `autonomous`, `bant`, `challenger`, `command`, `consultative`,
  `customer_centric`, `demo_first`, `fab`, `gap`, `inbound`, `meddic`, `neat`,
  `relationship`, `sandler`, `snap`, `social`, `solution`, `transactional`, `value`
- Создайте собственный flow в `yaml_config/flows/<name>/`

**Структура flow:**
```
yaml_config/flows/<name>/
├── flow.yaml       # Конфигурация flow (phases, skip_conditions)
└── states.yaml     # Специфичные состояния для этого flow
```

### PHONE VALIDATION (Валидация телефонных номеров)

| Параметр | Тип | По умолчанию | Описание |
|----------|-----|--------------|----------|
| `ru_mobile_range` | list[int] | `[900, 999]` | Диапазон кодов мобильных РФ |
| `kz_mobile_ranges` | list[list[int]] | `[[700, 709]]` | Диапазоны кодов мобильных КЗ |
| `kz_mobile_explicit` | list[int] | см. файл | Явные коды мобильных КЗ |
| `city_codes` | list[int] | см. файл | Коды городов РФ/КЗ |

### DEVELOPMENT (Режим разработки)

| Параметр | Тип | По умолчанию | Описание |
|----------|-----|--------------|----------|
| `debug` | bool | `false` | Режим отладки (больше логов) |
| `skip_embeddings` | bool | `false` | Пропустить инициализацию эмбеддингов |

## Использование в коде

### Импорт настроек

```python
from src.settings import settings

# Доступ через точку
model = settings.llm.model
threshold = settings.retriever.thresholds.lemma
allowed = settings.generator.allowed_english_words
```

### Получение по пути

```python
from src.settings import settings

value = settings.get_nested("retriever.thresholds.semantic")
# -> 0.5

value = settings.get_nested("nonexistent.path", default="fallback")
# -> "fallback"
```

### Перезагрузка настроек

```python
from src.settings import reload_settings

# После изменения settings.yaml
reload_settings()
```

### Использование Feature Flags в коде

#### Базовые проверки

```python
from src.feature_flags import flags

# Способ 1: Через property (типизировано, IDE-friendly)
if flags.tone_analysis:
    analyzer = ToneAnalyzer()

if flags.llm_classifier:
    classifier = LLMClassifier()
else:
    classifier = HybridClassifier()

# Способ 2: Через метод is_enabled()
if flags.is_enabled("custom_flag"):
    # Для динамических флагов
    pass
```

#### Работа с группами флагов

```python
from src.feature_flags import flags

# Проверка включена ли группа (хотя бы один флаг)
if flags.is_group_enabled("phase_3"):
    # Какой-то из Phase 3 флагов включен
    pass

# Требовать ВСЕ флаги в группе
if flags.is_group_enabled("safe", require_all=True):
    # Все safe флаги включены
    pass

# Получить все флаги
all_flags = flags.get_all_flags()
for flag_name, is_enabled in all_flags.items():
    print(f"{flag_name}: {is_enabled}")

# Получить только включённые
enabled = flags.get_enabled_flags()
print(f"Enabled: {enabled}")

# Получить только отключённые
disabled = flags.get_disabled_flags()
print(f"Disabled: {disabled}")
```

#### Runtime управление флагами

```python
from src.feature_flags import flags

# Override флага (для тестов и отладки)
flags.set_override("tone_analysis", False)
# Теперь flags.tone_analysis вернёт False

# Убрать override
flags.clear_override("tone_analysis")

# Очистить все overrides
flags.clear_all_overrides()

# Управление группами
flags.enable_group("phase_5")   # Включить все Phase 5 флаги
flags.disable_group("risky")    # Отключить рискованные флаги
```

#### Пример: Выбор классификатора

```python
from src.feature_flags import flags

def get_classifier():
    """Получить классификатор на основе флага"""
    if flags.llm_classifier:
        return LLMClassifier()
    else:
        return HybridClassifier()

classifier = get_classifier()
intent, confidence = classifier.classify(message)
```

#### Пример: Каскадный анализ тона

```python
from src.feature_flags import flags

def analyze_customer_tone(message: str) -> str:
    """Анализ тона с каскадными fallback"""

    if not flags.tone_analysis:
        return "neutral"

    # Tier 1: regex (всегда)
    tone = regex_analyzer.detect(message)
    if tone and confidence >= 0.85:
        return tone

    # Tier 2: Semantic (если включён)
    if flags.tone_semantic_tier2:
        tone = semantic_analyzer.detect(message)
        if tone and confidence >= 0.70:
            return tone

    # Tier 3: LLM (если включён)
    if flags.tone_llm_tier3:
        tone = llm_analyzer.detect(message)
        if tone:
            return tone

    return "neutral"
```

## Профили настроек

### Быстрый старт (без эмбеддингов)

```yaml
retriever:
  use_embeddings: false

reranker:
  enabled: false

category_router:
  enabled: false

development:
  skip_embeddings: true
```

Плюсы: старт за ~1 секунду
Минусы: только exact и lemma поиск

### Максимальная точность

```yaml
retriever:
  use_embeddings: true
  thresholds:
    lemma: 0.10
    semantic: 0.4
  default_top_k: 3

reranker:
  enabled: true
  candidates_count: 15

category_router:
  enabled: true
  top_k: 5

generator:
  retriever_top_k: 3
```

### Production

```yaml
logging:
  level: "WARNING"
  log_llm_requests: false
  log_retriever_results: false

feature_flags:
  llm_classifier: true
  structured_logging: true
  metrics_tracking: true
  multi_tier_fallback: true
  conversation_guard: true
  response_variations: true
  cascade_classifier: true
  context_full_envelope: true
  context_policy_overlays: true

development:
  debug: false
```

### Режим отладки

```yaml
logging:
  level: "DEBUG"
  log_llm_requests: true
  log_retriever_results: true

conditional_rules:
  enable_tracing: true
  log_context: true
  log_each_condition: true

development:
  debug: true
```

## CLI для проверки

```bash
# Вывести текущие настройки
cd src && python settings.py

# Вывести feature flags
cd src && python feature_flags.py
```

## Тестирование

### Запуск тестов

```bash
# Все тесты конфигурации (1780+ тестов)
pytest tests/test_config*.py -v

# Тесты настроек
pytest tests/test_settings.py -v

# Тесты feature flags
pytest tests/test_feature_flags.py -v

# Edge cases (граничные значения, unicode, конкурентность)
pytest tests/test_config_edge_cases.py -v

# Property-based тесты (Hypothesis)
pytest tests/test_config_property_based.py -v

# Расширенные тесты (190 тестов)
pytest tests/test_config_dynamic_changes.py tests/test_config_conflicts.py \
       tests/test_config_complex_conditions.py tests/test_config_unreachable_states.py \
       tests/test_config_template_interpolation.py tests/test_config_multi_tenant.py \
       tests/test_config_stress_performance.py tests/test_config_migration.py -v
```

### Покрытие тестами

Система конфигурации покрыта **1780+ тестами**:

| Категория | Файл | Тестов | Описание |
|-----------|------|--------|----------|
| **Базовые тесты** | | | |
| Settings YAML | `test_config_settings_yaml.py` | 89 | Параметры settings.yaml |
| Constants YAML | `test_config_constants_yaml.py` | 133 | Параметры constants.yaml |
| Flow YAML | `test_config_flow_yaml.py` | 137 | Структура flow.yaml |
| Integration | `test_config_integration.py` | 16 | ConfigLoader + Parser + Resolver |
| Behavior (settings) | `test_config_behavior_settings.py` | 78 | Поведение компонентов |
| Behavior (constants) | `test_config_behavior_constants.py` | 112 | Поведение с constants |
| Behavior (flags) | `test_config_behavior_feature_flags.py` | 38 | Влияние feature flags |
| E2E сценарии | `test_config_e2e_scenarios.py` | 26 | Полные диалоговые сценарии |
| Edge cases | `test_config_edge_cases.py` | 72 | Граничные значения |
| Property-based | `test_config_property_based.py` | 38 | Автогенерация Hypothesis |
| **Расширенные тесты (190)** | | | |
| Dynamic Changes | `test_config_dynamic_changes.py` | 22 | Runtime-изменение конфигурации |
| Conflicts | `test_config_conflicts.py` | 22 | Конфликты между параметрами |
| Complex Conditions | `test_config_complex_conditions.py` | 25 | Вложенные AND/OR/NOT |
| Unreachable States | `test_config_unreachable_states.py` | 24 | BFS/DFS анализ графа |
| Template Interpolation | `test_config_template_interpolation.py` | 25 | {{variable}}, circular refs |
| Multi-tenant | `test_config_multi_tenant.py` | 24 | Изоляция конфигов |
| Stress/Performance | `test_config_stress_performance.py` | 24 | Нагрузочные тесты |
| Migration | `test_config_migration.py` | 24 | Миграция версий |

### Расширенные тесты конфигурации

Расширенные тесты покрывают критичные сценарии:

**Dynamic Changes** — изменение параметров в runtime:
- Hot reload конфигурации
- Thread-safe обновления
- Синхронизация компонентов

**Conflicts** — обнаружение конфликтов:
- Несовместимые threshold значения
- Недействительные ссылки на состояния
- Циклические зависимости

**Complex Conditions** — вложенные условия:
- Глубокая вложенность AND/OR/NOT
- Short-circuit evaluation
- Законы Де Моргана

**Unreachable States** — анализ графа:
- BFS/DFS обход состояний
- Обнаружение orphan состояний
- Dead-end детекция

**Template Interpolation** — переменные в шаблонах:
- Вложенная интерполяция {{a.{{b}}}}
- Circular reference детекция
- Сохранение типов (int, bool, list)

**Multi-tenant** — изоляция tenant:
- Независимые конфигурации
- Deep copy изоляция
- Config inheritance

**Stress/Performance** — нагрузка:
- Большие конфиги (1000+ states)
- Concurrent доступ
- Memory leak детекция

**Migration** — миграция версий:
- Version detection
- Migration path
- Backwards compatibility

### Edge Case тесты

`test_config_edge_cases.py` покрывает:

- **Граничные значения** — `max_turns=0/1/999999/-1`, `timeout=0/86400`
- **Пустые значения** — пустые templates, categories, phases
- **Типы данных** — string "25", float 25.7, "true" vs true
- **Unicode/кодировки** — русский текст, emoji, BOM
- **Файловые ошибки** — not found, invalid YAML, read-only, empty
- **Конкурентность** — многопоточное чтение конфигов
- **Сложные условия** — глубокая вложенность and/or/not
- **Консистентность** — guard.threshold == frustration.threshold

### Property-based тесты

`test_config_property_based.py` использует [Hypothesis](https://hypothesis.readthedocs.io/) для автоматической генерации тестовых данных:

```python
@given(
    max_turns=st.integers(min_value=1, max_value=1000),
    timeout=st.integers(min_value=1, max_value=86400)
)
def test_guard_config_with_positive_values(max_turns, timeout):
    """Любые положительные значения должны загружаться."""
    config = {"guard": {"max_turns": max_turns, "timeout_seconds": timeout}}
    loaded = yaml.safe_load(yaml.dump(config))
    assert loaded['guard']['max_turns'] == max_turns
```

Преимущества:
- Автоматическое обнаружение edge cases
- Тысячи комбинаций параметров за секунды
- Воспроизводимость через seed

## YAML Configuration (yaml_config/)

Помимо `settings.yaml`, система использует структурированную YAML конфигурацию.

### Структура yaml_config/

```
src/yaml_config/
├── constants.yaml          # Константы (limits, intents, policy)
├── spin/phases.yaml        # Конфигурация SPIN фаз
├── states/sales_flow.yaml  # Состояния диалога
├── conditions/custom.yaml  # Кастомные условия для rules
│
├── flows/                  # Модульные flow
│   ├── _base/              # Базовые компоненты
│   │   ├── states.yaml     # Общие состояния
│   │   ├── mixins.yaml     # Переиспользуемые блоки
│   │   └── priorities.yaml # Приоритеты обработки
│   └── spin_selling/       # SPIN Selling flow
│       ├── flow.yaml       # Конфигурация flow
│       └── states.yaml     # SPIN-состояния
│
└── templates/              # Шаблоны промптов
    ├── _base/prompts.yaml
    └── spin_selling/prompts.yaml
```

### constants.yaml — Константы

```yaml
# Лимиты
limits:
  max_consecutive_objections: 3
  max_total_objections: 5
  max_gobacks: 2

# Категории интентов
intents:
  question: [price_question, question_features, question_integrations]
  objection: [objection_price, objection_time, objection_competitor]
  positive: [agreement, interest, demo_request]

# SPIN конфигурация
spin:
  phases: [situation, problem, implication, need_payoff]
  states:
    situation: spin_situation
    problem: spin_problem
```

### flows/ — Модульные flow

Позволяют создавать кастомные диалоги без кода:

```yaml
# flows/my_flow/flow.yaml
flow:
  name: my_flow
  phases:
    order: [phase1, phase2]
    mapping:
      phase1: state_phase1
      phase2: state_phase2
  entry_points:
    default: greeting
```

```yaml
# flows/my_flow/states.yaml
states:
  state_phase1:
    extends: _base_phase
    mixins: [price_handling]
    goal: "Phase 1 goal"
```

### templates/ — Шаблоны промптов

```yaml
# templates/spin_selling/prompts.yaml
templates:
  spin_situation:
    template: |
      Ты — консультант Wipon.
      Цель: узнать ситуацию клиента.
      {{context}}
    variables:
      - context
```

```python
# Использование
flow = loader.load_flow("spin_selling")
template = flow.get_template("spin_situation")
prompt = template.format(context="...")
```

### priorities.yaml — Приоритеты обработки

```yaml
# _base/priorities.yaml
default_priorities:
  - name: final_state
    priority: 0
    condition: is_final
    action: final

  - name: rejection
    priority: 1
    intents: [rejection]
    use_transitions: true

  - name: questions
    priority: 2
    intent_category: question
    default_action: answer_question

  - name: phase_progress
    priority: 4
    handler: phase_progress_handler
```

При наличии FlowConfig, StateMachine использует эти приоритеты вместо hardcoded логики.

### on_enter Actions

```yaml
# Состояние с действием при входе
states:
  ask_activity:
    on_enter:
      action: show_activity_options
    transitions:
      activity_selected: next_state
```

При переходе в состояние, action автоматически становится `show_activity_options`.

### Загрузка конфигурации

```python
from src.config_loader import ConfigLoader, get_config

# Глобальный конфиг
config = get_config()

# Или с перезагрузкой
config = get_config(reload=True)

# Загрузка flow
loader = ConfigLoader()
flow = loader.load_flow("spin_selling")

# FlowConfig содержит:
# - states: Dict — resolved состояния
# - priorities: List — приоритеты обработки
# - templates: Dict — шаблоны промптов
# - phase_order: List — порядок фаз
# - entry_points: Dict — точки входа
```

### Валидация конфигурации

```python
from src.config_loader import get_config_validated

# Загрузка с валидацией условий
config = get_config_validated()
```

Подробнее: [src/yaml_config/flows/README.md](../src/yaml_config/flows/README.md)

---

## Session Persistence — Runtime Settings

Часть параметров управления сессиями задаётся в коде интеграции (а не в `settings.yaml`).
Они критичны для поведения снапшотов и восстановления.

### Параметры SessionManager

| Параметр | Где задаётся | Рекомендация |
|---------|--------------|--------------|
| `ttl_seconds` | `SessionManager(...)` | 3600 (1 час тишины) |
| `flush_hour` | `SessionManager(...)` | 23 (локальное время сервера) |
| `load_snapshot` | интеграция | функция загрузки снапшота из внешней БД |
| `save_snapshot` | интеграция | функция сохранения снапшота в внешнюю БД |
| `load_history_tail` | интеграция | получение последних 4 сообщений |

### Environment Variables

| Переменная | Назначение | По умолчанию |
|-----------|------------|--------------|
| `SNAPSHOT_BUFFER_PATH` | путь к SQLite буферу снапшотов | `snapshot_buffer.sqlite` |
| `SESSION_LOCK_DIR` | директория для файловых lock'ов | `/tmp/crm_sales_bot_session_locks` |
| `LOG_FORMAT` | формат логов (`json` или `readable`) | `readable` |

### Multi‑Config

Для загрузки tenant‑конфигов используется структура:

```
src/yaml_config/tenants/<config_name>/
  constants.yaml
  states/
  flows/
  templates/
```

Если tenant‑каталог не найден, будет использована конфигурация по умолчанию.
