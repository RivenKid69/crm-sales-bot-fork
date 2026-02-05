# CRM Sales Bot

Чат-бот для продажи CRM-системы Wipon. Ведёт клиента от приветствия до закрытия сделки, используя методологию SPIN Selling.

## Быстрый старт

```bash
# 1. Запустить Ollama и скачать модель
ollama serve
ollama pull qwen3:14b

# 2. Активация виртуального окружения
source .venv/bin/activate

# 3. Запуск бота
cd src && python bot.py
```

**Требования:**
- Python 3.10+
- Ollama с моделью qwen3:14b (~9 GB VRAM)
- sentence-transformers для семантического поиска (ai-forever/FRIDA)

## Ollama Setup

> **Стандарт проекта:** Ollama + Qwen3 14B с native structured output.

### Установка Ollama

```bash
curl -fsSL https://ollama.ai/install.sh | sh
```

### Запуск Ollama сервера

```bash
# Через системный сервис (автозапуск)
sudo systemctl start ollama

# Или вручную
ollama serve
```

### Скачать модель

```bash
# Qwen3 14B - стандарт проекта (9.3 GB, ~12-16 GB VRAM)
ollama pull qwen3:14b
```

### Проверка работы

```bash
curl http://localhost:11434/api/tags
```

### Настройка модели

В `src/settings.yaml`:

```yaml
llm:
  model: "qwen3:14b"
  base_url: "http://localhost:11434"
  timeout: 120
```

### Преимущества Ollama + Qwen3 14B

- **Native Structured Output** — гарантированный JSON через `format` параметр (Ollama 0.5+)
- **Высокое качество** — Qwen3 14B значительно лучше 4B/8B моделей
- **Простая установка** — одна команда для установки и запуска
- **Поддержка русского** — Qwen3 отлично работает с русским языком

## Возможности

- **SPIN Selling** — структурированный подход к продажам (Situation → Problem → Implication → Need-Payoff)
- **Интенсивная классификация** — 300 интентов в 34 категориях с LLM-классификатором (Qwen3 14B)
- **Refinement Pipeline** — 7 активных слоёв в pipeline (ConfidenceCalibration, SecondaryIntentDetection, ShortAnswer, Composite, OptionSelection, Objection, DataAware) + дополнительные опциональные слои (FirstContact, GreetingContext, Comparison, DisambiguationResolution)
- **Blackboard Architecture** — современная архитектура с 15 Knowledge Sources для принятия решений
- **KB-Grounded Questions** — 5344 вопроса из базы знаний для реалистичных E2E симуляций
- **Auto-Discovery Categories** — автоматическое обнаружение 19+ question categories через intent_prefix
- **Objection Return System** — автоматический возврат к фазам после разрешения возражений
- **Secondary Intent Detection** — обработка составных сообщений с вторичными интентами
- **Frustration Intensity** — intensity-based детекция фрустрации с pre-intervention механизмом
- **Atomic State Transitions** — transition_to() для консистентности state/phase/last_action
- **Configurable Objection Limits** — persona-based лимиты из YAML (tire_kicker: 6/12, skeptic: 4/7)
- **Universal Phase Resolution** — все 21 flow с автоматическим phase detection
- **CircularFlowManager SSOT** — единый источник истины для go_back logic с deferred increment
- **Composed Categories** — автоматическая синхронизация категорий интентов (rejection → exit)
- **Intent Taxonomy System** — 5-level fallback chain для unmapped intents с интеллектуальным fallback
- **Category Streak Tracking** — price_related, escalation, technical_question category streaks для паттернов
- **Objection Loop Escape** — автоматический выход из циклов возражений (total-based + consecutive)
- **Каскадный поиск** — 3-этапный retriever (exact → lemma → semantic)
- **LLM-маршрутизация** — CategoryRouter для интеллектуальной классификации категорий
- **Голосовой интерфейс** — Voice Bot с STT (Whisper) и TTS (F5-TTS)
- **Модульные фазы** — постепенное включение новых возможностей через feature flags (42+ флагов)
- **Modular Flow System** — 21 готовый сценарий продаж с YAML-конфигурацией (extends/mixins)
- **Flow-Specific Prompts** — goal-aware промпты для каждого из 21 flow
- **Two-Tier StallGuard** — soft (NORMAL) + hard (HIGH) thresholds для детекции застреваний
- **PhaseExhaustedSource** — migrated from ConversationGuard в Blackboard pipeline
- **Disambiguation via Blackboard** — unified pipeline (~540 lines removed from bot.py)
- **All-Flows Data Infrastructure** — extraction, dedup, required_data для всех 20 non-SPIN flows
- **Plugin System** — динамическая регистрация Knowledge Sources через декораторы
- **Phase Coverage** — точное отслеживание visited_states для метрик
- **Dynamic CTA** — контекстно-зависимые подсказки при fallback на основе собранных данных
- **Категоризация болей** — автоматическое определение типа боли (losing_clients, no_control, manual_work)
- **Snapshot Persistence** — восстановление диалогов после паузы (TTL + локальный буфер + вечерний batch flush)
- **History Compaction** — LLM-сжатие истории при сохранении снапшота (без последних 4 сообщений)
- **Multi-Session безопасно** — параллельные диалоги с межпроцессными lock'ами
- **Multi-Config/Flow** — разные клиенты могут работать на разных flow/config без смешивания
- **Client Binding** — `client_id` сохраняется в снапшоте и проверяется при восстановлении

## Архитектура

```
Сообщение клиента
       │
       ▼
┌─────────────────┐
│   Classifier    │  ← Определяет интент + извлекает данные
│                 │    (company_size, pain_point, current_tools, ...)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   Blackboard    │  ← 15 Knowledge Sources принимают решения
│  Orchestrator   │    (Autonomous, Guards, Data Collectors, etc.)
└────────┬────────┘
         │
         ▼
┌─────────────────┐      ┌─────────────────┐
│   Generator     │ ───► │ Knowledge Base  │  ← 1969 секций о продуктах Wipon
│                 │ ◄─── │ (CascadeRetriever)│   в YAML-файлах
└────────┬────────┘      └─────────────────┘
         │
         ▼
┌─────────────────┐
│   LLM (Ollama)  │  ← Qwen3 14B генерирует финальный ответ
└────────┬────────┘
         │
         ▼
    Ответ бота
```

## Сессии и снапшоты

Диалог сохраняется только после периода тишины (TTL), а не на каждое сообщение.
Снапшот попадает в локальный буфер и выгружается в внешнюю БД пачкой после 23:00.
При восстановлении подгружается последние 4 сообщения из внешней истории, а основная история хранится в компактном виде.

```
Входящее сообщение
  └── SessionManager.get_or_create(session_id, client_id, flow, config)
       ├── cache hit → вернуть активный бот
       ├── local snapshot → восстановить + history_tail
       └── external snapshot → восстановить + history_tail

TTL cleanup (каждые 5–10 минут)
  └── bot.to_snapshot(compact_history=True) → LocalSnapshotBuffer

Первый запрос после 23:00
  └── batch flush → внешняя БД → LocalSnapshotBuffer.clear()
```

## Структура проекта

```
src/
├── bot.py                  # Главный класс SalesBot, координирует компоненты
├── settings.yaml           # Конфигурация (LLM, retriever, classifier, feature_flags)
├── settings.py             # Загрузчик настроек с DotDict
├── config.py               # Legacy-словарь интентов/паттернов для fallback классификатора
├── llm.py                  # OllamaClient — интеграция с Ollama
├── state_machine.py        # Управление состояниями диалога (flow из YAML)
├── generator.py            # Генерация ответов через LLM
│
├── # Фаза 0: Инфраструктура
├── logger.py               # Структурированное логирование (JSON/readable)
├── metrics.py              # Трекинг метрик диалогов
├── feature_flags.py        # Управление фичами без переразвертывания
│
├── # Фаза 1: Защита и надёжность
├── fallback_handler.py     # 4-уровневый fallback при ошибках
├── conversation_guard.py   # Защита от зацикливания
│
├── # Фаза 2: Естественность диалога
├── tone_analyzer/          # Каскадный анализатор тона
│   ├── cascade_analyzer.py # 3-уровневый каскад (regex → semantic → LLM)
│   ├── regex_analyzer.py   # Tier 1: Regex паттерны с intensity-based frustration
│   ├── semantic_analyzer.py # Tier 2: RoSBERTa semantic
│   ├── llm_analyzer.py     # Tier 3: LLM fallback
│   ├── frustration_tracker.py # Трекинг фрустрации с FrustrationIntensityCalculator
│   ├── frustration_intensity.py # FrustrationIntensityCalculator (intensity-based scoring)
│   └── structural_frustration.py # Структурная детекция фрустрации (unanswered repeats, deflection loops)
├── response_variations.py  # Вариативность ответов
│
├── # Фаза 3: Оптимизация SPIN Flow
├── lead_scoring.py         # Скоринг лидов
├── objection_handler.py    # Продвинутая обработка возражений
├── cta_generator.py        # Генерация Call-to-Action
├── objection/              # Продвинутая обработка возражений
│
├── # Фаза 5: Context Policy
├── context_envelope.py     # Построение единого контекста для подсистем
├── context_window.py       # Расширенный контекст диалога (история)
├── dialogue_policy.py      # Context-aware policy overlays
├── intent_tracker.py       # Трекинг интентов и паттернов
├── response_directives.py  # Директивы для генератора
├── history_compactor.py    # LLM-компакция истории при снапшоте
├── snapshot_buffer.py      # Локальный буфер снапшотов (SQLite, multi-process)
├── session_manager.py      # Кеш сессий + восстановление + TTL cleanup + batch flush
├── session_lock.py         # Межпроцессные lock'и по session_id
│
├── # Условные правила
├── conditions/             # Пакет условных правил
├── rules/                  # Intent resolution system
│   ├── resolver.py         # RuleResolver с taxonomy fallback
│   └── intent_taxonomy.py  # IntentTaxonomyRegistry (5-level fallback)
│
├── # Validation system
├── validation/             # Статическая валидация конфигурации
│   ├── __init__.py         # Публичный API
│   └── intent_coverage.py  # IntentCoverageValidator (zero unmapped intents)
│
├── # YAML Configuration (Phase 1 Parameterization)
├── config_loader.py        # Загрузчик YAML конфигурации
├── yaml_config/            # YAML конфигурация
│   ├── constants.yaml      # ЕДИНЫЙ ИСТОЧНИК ИСТИНЫ (limits, intents, policy)
│   ├── constants.py        # Python-обёртка для constants.yaml
│   ├── spin/phases.yaml    # SPIN фазы
│   ├── states/sales_flow.yaml  # Состояния диалога
│   ├── conditions/custom.yaml  # Кастомные условия
│   ├── flows/              # 21 модульный flow (extends/mixins)
│   │   ├── _base/          # Базовые компоненты
│   │   ├── spin_selling/   # SPIN Selling (по умолчанию)
│   │   ├── autonomous/     # Autonomous Decision flow (новое)
│   │   ├── aida/           # AIDA flow
│   │   ├── bant/           # BANT framework
│   │   ├── challenger/     # Challenger Sale
│   │   ├── command/        # Command flow
│   │   ├── consultative/   # Consultative Selling
│   │   ├── customer_centric/ # Customer Centric
│   │   ├── demo_first/     # Demo First approach
│   │   ├── fab/            # FAB (Features-Advantages-Benefits)
│   │   ├── gap/            # GAP Selling
│   │   ├── inbound/        # Inbound flow
│   │   ├── meddic/         # MEDDIC
│   │   ├── neat/           # NEAT Selling
│   │   ├── relationship/   # Relationship Selling
│   │   ├── sandler/        # Sandler
│   │   ├── snap/           # SNAP Selling
│   │   ├── social/         # Social Selling
│   │   ├── solution/       # Solution Selling
│   │   ├── transactional/  # Transactional flow
│   │   └── value/          # Value Selling
│   └── templates/          # Шаблоны промптов
│       ├── _base/prompts.yaml  # Базовые шаблоны
│       └── spin_selling/prompts.yaml  # SPIN шаблоны
│
├── classifier/             # Пакет классификации интентов
│   ├── __init__.py         # Публичный API пакета
│   ├── unified.py          # UnifiedClassifier — адаптер LLM/Hybrid
│   ├── normalizer.py       # Нормализация текста (опечатки, сленг)
│   ├── hybrid.py           # HybridClassifier — regex fallback
│   ├── cascade.py          # CascadeClassifier — semantic fallback
│   ├── disambiguation.py   # IntentDisambiguator
│   ├── refinement_pipeline.py   # RefinementPipeline (Protocol, Registry, Pipeline)
│   ├── refinement_layers.py     # Refinement layers (adapters)
│   ├── confidence_calibration.py # ConfidenceCalibrationLayer (entropy, gap, heuristics)
│   ├── secondary_intent_detection.py # SecondaryIntentDetectionLayer (composite messages)
│   ├── llm/                # LLM классификатор (основной)
│   │   ├── classifier.py   # LLMClassifier (Ollama + Structured Output)
│   │   ├── prompts.py      # System prompt + few-shot
│   │   └── schemas.py      # Pydantic схемы для structured output
│   ├── intents/            # Подпакет классификации интентов (для fallback)
│   │   ├── patterns.py     # Приоритетные паттерны (523 шт, +97 новых)
│   │   ├── root_classifier.py   # Быстрая классификация по корням
│   │   └── lemma_classifier.py  # Fallback через pymorphy
│   └── extractors/         # Подпакет извлечения данных
│       └── data_extractor.py    # Извлечение структурированных данных
│
├── blackboard/             # Dialogue Blackboard System (decision engine; StateMachine хранит state)
│   ├── __init__.py         # Публичный API
│   ├── blackboard.py       # DialogueBlackboard — центральное хранилище
│   ├── orchestrator.py     # DialogueOrchestrator — координатор
│   ├── knowledge_source.py # KnowledgeSource — базовый класс
│   ├── source_registry.py  # SourceRegistry + @register_source
│   ├── protocols.py        # Hexagonal Architecture (IStateMachine, IIntentTracker)
│   ├── models.py           # Proposal, ResolvedDecision, ContextSnapshot
│   ├── enums.py            # Priority, ProposalType
│   ├── proposal_validator.py # ProposalValidator
│   ├── conflict_resolver.py  # ConflictResolver
│   ├── priority_assigner.py  # PriorityAssigner
│   ├── event_bus.py        # DialogueEventBus (observability)
│   └── sources/            # 15 Knowledge Sources
│       ├── autonomous_decision.py  # Автономные решения
│       ├── price_question.py       # Вопросы о цене (7 price_related intents, category_streak)
│       ├── fact_question.py        # Фактические вопросы (17 KB categories + secondary_intents)
│       ├── data_collector.py       # Сбор данных
│       ├── objection_guard.py      # Защита от возражений (persona-based limits)
│       ├── conversation_guard_ks.py # Защита от повторов
│       ├── intent_pattern_guard.py  # Паттерн-анализ
│       ├── stall_guard.py          # Детекция застреваний
│       ├── go_back_guard.py        # Возврат назад
│       ├── objection_return.py     # Возврат после возражений (HIGH priority, phase restoration)
│       ├── phase_exhausted.py      # Исчерпанные фазы
│       ├── escalation.py           # Эскалация (category_streak для escalation intents)
│       ├── disambiguation.py       # Уточнение
│       ├── intent_processor.py     # Базовые интенты
│       └── transition_resolver.py  # Переходы
│
├── simulator/              # Симулятор диалогов для тестирования
│   ├── __init__.py         # Публичный API
│   ├── runner.py           # SimulationRunner — оркестратор симуляций
│   ├── client_agent.py     # ClientAgent — эмуляция клиента через LLM
│   ├── personas.py         # Персоны клиентов (happy_path, objector, etc.)
│   ├── noise.py            # Добавление шума в сообщения
│   ├── metrics.py          # Сбор метрик симуляций
│   └── report.py           # Генерация отчётов
│
└── knowledge/              # База знаний о продуктах Wipon
    ├── __init__.py         # Публичный API (WIPON_KNOWLEDGE, get_retriever)
    ├── base.py             # Структуры данных (KnowledgeSection, KnowledgeBase)
    ├── loader.py           # Загрузчик YAML файлов
    ├── lemmatizer.py       # Лемматизация для поиска
    ├── retriever.py        # CascadeRetriever (3-этапный поиск)
    ├── category_router.py  # LLM-классификация категорий
    ├── reranker.py         # Cross-encoder переоценка результатов
    └── data/               # YAML-файлы базы знаний (1969 секций)
        ├── _meta.yaml      # Метаданные (company, stats)
        ├── equipment.yaml  # Оборудование (316 секций)
        ├── pricing.yaml    # Тарифы (286 секций)
        ├── products.yaml   # Продукты (273 секции)
        ├── support.yaml    # Техподдержка (201 секция)
        ├── tis.yaml        # Товарно-информационная система (191 секция)
        ├── regions.yaml    # Регионы (130 секций)
        ├── inventory.yaml  # Складской учёт (93 секции)
        ├── features.yaml   # Функции (90 секций)
        ├── integrations.yaml   # Интеграции (86 секций)
        ├── fiscal.yaml     # Фискализация (68 секций)
        ├── analytics.yaml  # Аналитика (63 секции)
        ├── employees.yaml  # Управление персоналом (55 секций)
        ├── stability.yaml  # Стабильность (45 секций)
        ├── mobile.yaml     # Мобильное приложение (35 секций)
        ├── promotions.yaml # Акции и скидки (26 секций)
        ├── competitors.yaml # Конкуренты (7 секций)
        └── faq.yaml        # Часто задаваемые вопросы (4 секции)

voice_bot/                  # Голосовой интерфейс
├── voice_pipeline.py       # Полный pipeline: STT → LLM → TTS
├── CosyVoice/              # Синтез речи (submodule)
├── fish-speech/            # Speech synthesis (submodule)
├── checkpoints/            # Модели F5-TTS, OpenAudio
├── models/                 # XTTS-RU-IPA модели
└── test_*.py               # Тесты компонентов (STT, TTS, LLM)

tests/                      # Тесты в 228 файлах
├── test_classifier.py      # Тесты классификатора
├── test_spin.py            # Тесты SPIN-методологии
├── test_knowledge.py       # Тесты базы знаний
├── test_cascade_retriever.py   # Тесты CascadeRetriever
├── test_cascade_advanced.py    # Продвинутые тесты каскадного поиска
├── test_category_router*.py    # Тесты LLM-маршрутизации
├── test_reranker.py        # Тесты переоценки результатов
├── test_intent_coverage.py # Тесты Intent Taxonomy coverage (zero unmapped intents)
├── test_phase*_integration.py  # Интеграционные тесты фаз 0-4
├── test_conditions_phase3.py   # Тесты RuleResolver с taxonomy fallback
├── test_feature_flags.py   # Тесты feature flags
├── test_logger.py          # Тесты логирования
├── test_metrics.py         # Тесты метрик
└── ...

scripts/                    # Вспомогательные скрипты
├── full_bot_stress_test.py     # Стресс-тест бота
├── stress_test_knowledge.py    # Стресс-тест базы знаний
└── validate_knowledge_yaml.py  # Валидация YAML
```

## Конфигурация (settings.yaml)

Все параметры вынесены в `src/settings.yaml`:

```yaml
# LLM (Language Model) - Ollama Server
llm:
  model: "qwen3:14b"
  base_url: "http://localhost:11434"
  timeout: 120

# Retriever (Поиск по базе знаний)
retriever:
  use_embeddings: true
  embedder_model: "ai-forever/FRIDA"
  thresholds:
    exact: 1.0      # Точное совпадение keyword
    lemma: 0.15     # Совпадение по леммам
    semantic: 0.5   # Косинусное сходство эмбеддингов

# Reranker (Переоценка при низком score)
reranker:
  enabled: true
  model: "BAAI/bge-reranker-v2-m3"
  threshold: 0.5

# Category Router (LLM-классификация категорий)
category_router:
  enabled: true
  top_k: 3

# Feature Flags (Управление фичами)
feature_flags:
  llm_classifier: true        # LLM классификатор (основной)
  structured_logging: true    # JSON логи
  metrics_tracking: true      # Трекинг метрик
  multi_tier_fallback: true   # 4-уровневый fallback
  conversation_guard: true    # Защита от зацикливания
  cascade_tone_analyzer: true # Каскадный анализатор тона
  response_variations: true   # Вариативность ответов
  context_full_envelope: true # Полный ContextEnvelope
  context_policy_overlays: true # DialoguePolicy overrides
```

Подробнее: [docs/SETTINGS.md](docs/SETTINGS.md)

## SPIN Selling Methodology

Бот использует методологию SPIN Selling для квалификации клиентов:

```
greeting → spin_situation → spin_problem → spin_implication → spin_need_payoff → presentation → close → success
                                    │                                                    │
                                    └────────────── rejection ───────────────────────────┴──→ soft_close
```

### Фазы SPIN

| Фаза | Состояние | Цель | Собираемые данные |
|------|-----------|------|-------------------|
| **S**ituation | `spin_situation` | Понять текущую ситуацию | `company_size`, `current_tools`, `business_type` |
| **P**roblem | `spin_problem` | Выявить боли и проблемы | `pain_point` |
| **I**mplication | `spin_implication` | Осознать последствия | `pain_impact`, `financial_impact` |
| **N**eed-Payoff | `spin_need_payoff` | Сформулировать ценность | `desired_outcome`, `value_acknowledged` |

### Примеры SPIN-вопросов

**Situation (понять ситуацию):**
- "Сколько человек работает с клиентами?"
- "Чем сейчас пользуетесь для учёта — Excel, 1С?"

**Problem (выявить проблемы):**
- "Какая главная головная боль с учётом прямо сейчас?"
- "Случается терять данные или путать заказы?"

**Implication (осознать последствия):**
- "Сколько примерно клиентов теряете из-за этого в месяц?"
- "Во сколько это обходится бизнесу?"

**Need-Payoff (создать ценность):**
- "Если бы остатки обновлялись автоматически — насколько это упростило бы работу?"
- "Как изменилась бы ситуация, если бы вся информация была в одном месте?"

## Все состояния диалога

| Состояние | Цель | SPIN-фаза |
|-----------|------|-----------|
| `greeting` | Поздороваться | - |
| `spin_situation` | Понять ситуацию клиента | Situation |
| `spin_problem` | Выявить проблемы | Problem |
| `spin_implication` | Осознать последствия | Implication |
| `spin_need_payoff` | Сформулировать ценность | Need-Payoff |
| `presentation` | Показать решение | - |
| `handle_objection` | Отработать "дорого" | - |
| `close` | Получить контакт | - |
| `success` | Успешное завершение | - |
| `soft_close` | Вежливый отказ | - |

## Ключевые интенты

### Вопросы (приоритет 0 — всегда отвечаем):
- `price_question` — сколько стоит?
- `question_features` — какие функции?
- `question_integrations` — с чем интегрируется?

### SPIN-интенты:
- `situation_provided` — клиент рассказал о ситуации
- `problem_revealed` — клиент озвучил проблему
- `implication_acknowledged` — клиент осознал последствия
- `need_expressed` — клиент выразил потребность

### Данные:
- `info_provided` — клиент дал информацию о себе

### Решения:
- `agreement` — клиент согласен
- `rejection` — клиент отказывается (приоритет 1 — сразу soft_close)
- `objection_price` — дорого

## Извлекаемые данные

### Базовые:
| Поле | Описание | Пример |
|------|----------|--------|
| `company_size` | Размер команды | "10 человек" → 10 |
| `pain_point` | Боль клиента | "теряем клиентов" |
| `pain_category` | Категория боли | `losing_clients`, `no_control`, `manual_work` |
| `contact_info` | Контакт клиента | телефон, email |

### SPIN-специфичные:
| Поле | Описание | Фаза | Пример |
|------|----------|------|--------|
| `current_tools` | Текущие инструменты | Situation | "Excel", "1С", "вручную" |
| `business_type` | Тип бизнеса | Situation | "розничная торговля", "общепит" |
| `pain_impact` | Последствия проблемы | Implication | "теряем ~10 клиентов" |
| `financial_impact` | Финансовые потери | Implication | "~50 000 в месяц" |
| `desired_outcome` | Желаемый результат | Need-Payoff | "автоматизация процессов" |
| `value_acknowledged` | Признание ценности | Need-Payoff | true/false |
| `high_interest` | Высокий интерес | Любая | true (позволяет пропустить I/N) |

## База знаний (knowledge/)

База знаний содержит **1969 секций** в **17 категориях** (+ `_meta.yaml`):

| Категория | Секций | Описание |
|-----------|--------|----------|
| equipment | 316 | Оборудование (кассы, принтеры, сканеры) |
| pricing | 286 | Тарифы и стоимость |
| products | 273 | Продукты Wipon |
| support | 201 | Техподдержка и обслуживание |
| tis | 191 | Товарно-информационная система |
| regions | 130 | Регионы Казахстана |
| inventory | 93 | Складской учёт |
| features | 90 | Функции системы |
| integrations | 86 | Интеграции (1С, Kaspi, Telegram) |
| fiscal | 68 | Фискализация |
| analytics | 63 | Аналитика и отчёты |
| employees | 55 | Управление персоналом |
| stability | 45 | Стабильность и надёжность |
| mobile | 35 | Мобильное приложение |
| promotions | 26 | Акции и скидки |
| competitors | 7 | Конкуренты |
| faq | 4 | Часто задаваемые вопросы |

### CascadeRetriever — 3-этапный поиск

```
1. Exact Match    ─── keyword как подстрока в запросе
       │
       ▼ (если не найдено)
2. Lemma Match    ─── сравнение лемматизированных множеств
       │
       ▼ (если не найдено)
3. Semantic Match ─── cosine similarity эмбеддингов (ai-forever/FRIDA)
```

### CategoryRouter — LLM-маршрутизация

При низком score или сложных запросах включается LLM-классификатор категорий:

```python
# Запрос: "как подключить 1С?"
# CategoryRouter определяет: ["integrations", "features"]
# Поиск сужается до релевантных категорий
```

Подробнее: [docs/KNOWLEDGE.md](docs/KNOWLEDGE.md)

## Classifier (classifier/)

Пакет классификации с LLM-классификатором и regex fallback:

```
classifier/
├── __init__.py          # API: UnifiedClassifier, HybridClassifier, TextNormalizer
├── unified.py           # UnifiedClassifier — адаптер LLM/Hybrid
├── normalizer.py        # TYPO_FIXES (663 шт), SPLIT_PATTERNS (170 шт)
├── hybrid.py            # HybridClassifier — regex fallback
├── cascade.py           # CascadeClassifier — semantic fallback
├── disambiguation.py    # IntentDisambiguator
├── llm/                 # LLM классификатор (основной)
│   ├── classifier.py    # LLMClassifier (Ollama + Structured Output)
│   ├── prompts.py       # System prompt + few-shot примеры
│   └── schemas.py       # Pydantic схемы (ClassificationResult, ExtractedData)
├── intents/
│   ├── patterns.py      # PRIORITY_PATTERNS (491 шт) для fallback
│   ├── root_classifier.py   # Быстрая классификация по корням
│   └── lemma_classifier.py  # Fallback через pymorphy2/3
└── extractors/
    └── data_extractor.py    # Извлечение structured data
```

### Публичный API:
```python
from src.classifier import UnifiedClassifier, HybridClassifier, TextNormalizer, DataExtractor
from src.classifier.llm import LLMClassifier, ClassificationResult, ExtractedData
```

### Dual-mode классификация:
- **LLM режим** (по умолчанию) — 300 интентов в 34 категориях через Ollama, structured output
- **Hybrid режим** (fallback) — regex + pymorphy при ошибке LLM или `llm_classifier=false`

### Контекстная классификация:
Классификатор учитывает текущую SPIN-фазу:
- В фазе `situation` → информация классифицируется как `situation_provided`
- В фазе `problem` → боль классифицируется как `problem_revealed`
- В фазе `implication` → последствия как `implication_acknowledged`
- В фазе `need_payoff` → желания как `need_expressed`

Подробнее: [docs/CLASSIFIER.md](docs/CLASSIFIER.md)

## Dialogue Blackboard System (blackboard/)

**Архитектурный паттерн**: Blackboard Pattern — shared workspace для принятия решений

### Компоненты:
- **DialogueBlackboard** — центральное хранилище состояния диалога
- **DialogueOrchestrator** — координатор Knowledge Sources
- **15 Knowledge Sources** — независимые модули принятия решений:
  - **AutonomousDecisionSource** — автономные решения на основе паттернов
  - **PriceQuestionSource** — обработка вопросов о цене (7 price_related intents, category_streak tracking)
  - **FactQuestionSource** — обработка фактических вопросов (17 KB categories, secondary_intents support)
  - **DataCollectorSource** — сбор данных клиента
  - **ObjectionGuardSource** — защита от зацикливания возражений (persona-based limits: tire_kicker 6/12, skeptic 4/7)
  - **ConversationGuardSource** — защита от повторов
  - **IntentPatternGuardSource** — паттерн-анализ интентов
  - **StallGuardSource** — детекция застреваний
  - **GoBackGuardSource** — возврат назад по фазам
  - **ObjectionReturnSource** — возврат после возражений (HIGH priority, phase restoration, total-based escape)
  - **PhaseExhaustedSource** — обработка исчерпанных фаз
  - **EscalationSource** — эскалация к человеку (category_streak для 8 escalation intents)
  - **DisambiguationSource** — уточнение неоднозначностей
  - **IntentProcessorSource** — обработка базовых интентов
  - **TransitionResolverSource** — разрешение переходов

### Plugin System:
```python
from src.blackboard import register_source, KnowledgeSource

@register_source(name="my_source", priority=50, enabled=True)
class MySource(KnowledgeSource):
    def contribute(self, snapshot: ContextSnapshot) -> List[Proposal]:
        # Custom decision logic
        pass
```

### Приоритеты Knowledge Sources:
1. **Autonomous Decision** (priority 100) — высший приоритет
2. **Guards** (priority 80-90) — защитные механизмы
3. **Question Handlers** (priority 60-70) — обработка вопросов
4. **Data Collectors** (priority 50) — сбор данных
5. **Transition Resolvers** (priority 30-40) — переходы состояний

## Modular Flow System (yaml_config/flows/)

Система модульных flow для создания кастомизированных диалогов без изменения кода.

### Ключевые возможности:

- **Extends** — наследование от базовых состояний
- **Mixins** — переиспользуемые блоки правил
- **Parameters** — подстановка `{{param}}` в конфигурации
- **Priority-driven Rules** — приоритизация через YAML

### Пример создания custom flow:

```yaml
# flows/my_flow/flow.yaml
flow:
  name: my_flow
  version: "1.0"

  phases:
    order: [discovery, qualification, proposal]
    mapping:
      discovery: state_discovery
      qualification: state_qualification
      proposal: state_proposal
    post_phases_state: closing

  entry_points:
    default: greeting
    hot_lead: state_qualification
```

```yaml
# flows/my_flow/states.yaml
states:
  state_discovery:
    extends: _base_phase
    mixins:
      - price_handling
      - exit_intents
    goal: "Understand customer situation"
    phase: discovery
    required_data: [company_size]
```

### Загрузка flow:

```python
from src.config_loader import ConfigLoader
from src.state_machine import StateMachine

loader = ConfigLoader()
flow = loader.load_flow("my_flow")
sm = StateMachine(flow=flow)
```

Подробнее: [src/yaml_config/flows/README.md](src/yaml_config/flows/README.md)

## Intent Taxonomy System (Zero Unmapped Intents by Design)

Система иерархической taxonomy для intelligent fallback resolution. Устраняет **81% failure rate** для unmapped intents через 5-level fallback chain.

### Проблема до внедрения

При отсутствии explicit mapping для intent:
- `price_question` → `continue_current_goal` (generic) → **81% failure**
- `contact_provided` → no transition → **81% failure**
- `request_brevity` → spurious transitions → **55% failure**
- `request_references` → no mapping → **54% failure**

### Решение: Hierarchical Taxonomy

Каждый intent имеет **taxonomy metadata**:
```yaml
intent_taxonomy:
  price_question:
    category: question                    # Группа интентов
    super_category: user_input            # Высокоуровневая группа
    semantic_domain: pricing              # Семантический домен
    fallback_action: answer_with_pricing  # Intelligent fallback
    priority: high
```

### 5-Level Fallback Chain

1. **Exact match** — поиск в state/global rules
2. **Category fallback** — fallback по категории (`question` → `answer_and_continue`)
3. **Super-category fallback** — fallback по super-category (`user_input` → `acknowledge_and_continue`)
4. **Domain fallback** — fallback по semantic domain (`pricing` → `answer_with_pricing`)
5. **DEFAULT_ACTION** — `continue_current_goal` (только если все выше не сработало)

### Guaranteed Coverage через _universal_base

Все критические intents имеют **explicit mappings** в `_universal_base` mixin:

```yaml
_universal_base:
  rules:
    # Price intents
    price_question: answer_with_pricing
    pricing_details: answer_with_pricing
    # ... all 7 price intents

    # Meta intents
    request_brevity: respond_briefly
    unclear: clarify_one_question

  transitions:
    contact_provided: success
    demo_request: close
    request_references: close
    # ... all purchase intents
```

### Результат

- `price_question`: **81% → 95%+** (domain fallback → `answer_with_pricing`)
- `contact_provided`: **81% → 95%+** (`_universal_base` → transition to `success`)
- `request_brevity`: **55% → <5%** (no spurious transitions)
- `request_references`: **54% → 95%+** (`_universal_base` → `provide_references`)

### Validation System

**Static validation** (CI):
```python
from src.validation import IntentCoverageValidator

validator = IntentCoverageValidator(config, flow)
issues = validator.validate_all()
# Проверяет: unmapped critical intents, taxonomy completeness, wrong actions
```

**Runtime monitoring**:
```python
from src.metrics import FallbackMetrics

metrics = FallbackMetrics()
# Отслеживает: fallback rate by level, DEFAULT_ACTION usage (<1% target)
```

Подробнее: [docs/INTENT_TAXONOMY.md](docs/INTENT_TAXONOMY.md)

## Feature Flags

Источник истины — `src/feature_flags.py` (62 флага). `src/settings.yaml` задаёт базовые значения для ключевых фич, остальные берутся из defaults и могут быть переопределены через `FF_*`.

**Базовые флаги (settings.yaml):**

| Фаза | Флаг | Значение | Комментарий |
|------|------|----------|-------------|
| 0 | `structured_logging` | `true` | JSON логи |
| 0 | `metrics_tracking` | `true` | Метрики диалога |
| 1 | `multi_tier_fallback` | `true` | 4-уровневый fallback |
| 1 | `conversation_guard` | `true` | Защита от зацикливания |
| 2 | `tone_analysis` | `true` | Анализ тона |
| 2 | `response_variations` | `true` | Вариативность ответов |
| 2 | `personalization` | `false` | Персонализация (v1) |
| 3 | `lead_scoring` | `false` | Скоринг лидов |
| 3 | `circular_flow` | `false` | Возврат назад по фазам |
| 3 | `objection_handler` | `false` | Продвинутая обработка возражений |
| 3 | `cta_generator` | `true` | Генерация CTA |

**Дополнительно:** `llm_classifier`, `cascade_tone_analyzer`, `context_*`, `refinement_*`, `confidence_*`, `response_*` и др. — см. `src/feature_flags.py` и [docs/PHASES.md](docs/PHASES.md).

## Voice Bot (voice_bot/)

Голосовой интерфейс для разговорного взаимодействия:

```
┌───────────────────┐     ┌───────────────────┐     ┌───────────────────┐
│   faster-whisper  │ ──► │   LLM (Ollama)    │ ──► │   F5-TTS Russian  │
│   (STT)           │     │   Qwen3 14B       │     │   + RUAccent      │
└───────────────────┘     └───────────────────┘     └───────────────────┘
      Голос клиента              Текст                   Голос бота
```

Подробнее: [docs/VOICE.md](docs/VOICE.md)

## Симулятор диалогов (simulator/)

Модуль для массового тестирования бота с эмуляцией различных типов клиентов:

```bash
# Запуск 50 симуляций
python -m src.simulator -n 50 -o report.txt

# Запуск с конкретной персоной
python -m src.simulator -n 10 --persona happy_path

# Параллельный запуск
python -m src.simulator -n 100 --parallel 4
```

### Компоненты симулятора

| Компонент | Описание |
|-----------|----------|
| `SimulationRunner` | Оркестратор batch-симуляций |
| `ClientAgent` | LLM-агент, эмулирующий клиента |
| `Persona` | Профили поведения (happy_path, objector, price_focused) |
| `MetricsCollector` | Сбор метрик (SPIN coverage, outcome, duration) |
| `ReportGenerator` | Генерация отчётов в текстовом формате |

### Персоны клиентов

- **happy_path** — идеальный клиент, следует SPIN flow
- **objector** — часто возражает (цена, конкуренты)
- **price_focused** — фокусируется на стоимости
- **quick_decision** — быстро принимает решение
- **skeptic** — скептически настроен

## Тестирование

```bash
# Все тесты (~8600 test functions, 228 файлов)
pytest tests/ -v

# Только тесты классификатора
pytest tests/test_classifier.py -v

# Только SPIN-тесты
pytest tests/test_spin.py -v

# Только тесты базы знаний
pytest tests/test_knowledge.py -v

# Тесты каскадного retriever
pytest tests/test_cascade_retriever.py -v

# Тесты CategoryRouter
pytest tests/test_category_router*.py -v

# Тесты фаз 0-4
pytest tests/test_phase*_integration.py -v

# Тесты конфигурации (~1860 test functions)
pytest tests/test_config*.py -v

# Стресс-тест бота
python scripts/full_bot_stress_test.py

# Тест базы знаний
python scripts/stress_test_knowledge.py
```

### Тесты конфигурации

Система конфигурации покрыта **~1860 test functions**:

| Категория | Файлы | Тестов |
|-----------|-------|--------|
| Unit тесты | `test_config_*_yaml.py` | см. файлы |
| Integration | `test_config_integration.py` | см. файлы |
| Behavior | `test_config_behavior_*.py` | см. файлы |
| E2E сценарии | `test_config_e2e_scenarios.py` | см. файлы |
| Edge cases | `test_config_edge_cases.py` | см. файлы |
| Property-based | `test_config_property_based.py` | см. файлы |

```bash
# Edge cases (граничные значения, unicode, конкурентность)
pytest tests/test_config_edge_cases.py -v

# Property-based (Hypothesis - автоматическая генерация тестов)
pytest tests/test_config_property_based.py -v
```

## Отладка

В интерактивном режиме:
- `/status` — текущее состояние, SPIN-фаза и собранные данные
- `/reset` — сброс диалога
- `/quit` — выход

Пример вывода:
```
Бот: Понял, команда из 10 человек. Скажите, какая главная сложность с учётом?
  [spin_problem] transition_to_spin_problem (SPIN: problem)
```

## Зависимости

> Источник истины для зависимостей — `pyproject.toml`. `requirements.txt` содержит минимальный набор для быстрого запуска.

| Пакет | Назначение |
|-------|------------|
| `ollama` | Ollama для LLM (qwen3:14b) — устанавливается системно |
| `requests` | HTTP-клиент для Ollama API |
| `pydantic` | Схемы для structured output |
| `pymorphy3` | Морфология русского языка (fallback на pymorphy2) |
| `sentence-transformers` | Эмбеддинги (ai-forever/FRIDA) |
| `numpy` | Численные операции (embeddings/reranker/semantic) |
| `pyyaml` | Парсинг YAML конфигурации и базы знаний |
| `pytest` | Тестирование |

Для голосового интерфейса:
| Пакет | Назначение |
|-------|------------|
| `faster-whisper` | Speech-to-Text с GPU |
| `f5-tts` | Text-to-Speech на русском |
| `RUAccent` | Расстановка ударений |
| `sounddevice` | Работа с аудио |
| `torch` | GPU поддержка |

Установка:
```bash
pip install -r requirements.txt
```

## Документация

- [ARCHITECTURE.md](docs/ARCHITECTURE.md) — архитектура системы
- [API.md](docs/API.md) — справочник по API
- [CLASSIFIER.md](docs/CLASSIFIER.md) — документация классификатора
- [KNOWLEDGE.md](docs/KNOWLEDGE.md) — документация базы знаний
- [INTENT_TAXONOMY.md](docs/INTENT_TAXONOMY.md) — Intent Taxonomy System (zero unmapped intents)
- [SETTINGS.md](docs/SETTINGS.md) — описание настроек
- [PHASES.md](docs/PHASES.md) — фазы разработки (0-5)
- [state_machine.md](docs/state_machine.md) — State Machine v2.0
- [DAG.md](docs/DAG.md) — DAG State Machine (параллельные потоки)
- [VOICE.md](docs/VOICE.md) — голосовой интерфейс

## Метрики проекта

```
Дата среза:               2026-02-05
Модулей Python (src):     171 файлов
Тестовых файлов:          228 (≈8595 test functions)
Секций в базе знаний:     1969 в 17 категориях (meta: 2026-01-07)
KB Questions Pool:        5904 сгенерировано, 5344 после dedup (2026-02-01)
Интентов:                 300 записей в 34 категориях (271 unique)
Intent Taxonomy Entries:  271
Secondary Intent Patterns: 365 regex-паттернов
Composed Categories:      7 (negative, blocking, all_questions, question_requires_facts, greeting_redirect_intents, comparison_like, objection_return_triggers)
Auto-Discovery Categories: 19 question_* категорий через intent_prefix
Паттернов опечаток:       663 в TYPO_FIXES
Паттернов разделения:     170 в SPLIT_PATTERNS
Приоритетных паттернов:   491 в PRIORITY_PATTERNS
Паттернов болей:          565 в pain_patterns
Refinement Pipeline:      7 слоёв (confidence_calibration, secondary_intent_detection, short_answer, composite_message, option_selection, objection, data_aware)
Knowledge Sources:        15
Категорий знаний:         17
Feature Flags:            62 флага (44 включены по умолчанию)
YAML Config Files:        76 в yaml_config/
Modular Flows:            21 готовый flow
Flow-Specific Prompts:    21 template (+_base)
Data Infrastructure:      поддержка всех 20 non-SPIN flows
Строк Python кода (src):  ~81,000
```
