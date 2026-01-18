# CRM Sales Bot

Чат-бот для продажи CRM-системы Wipon. Ведёт клиента от приветствия до закрытия сделки, используя методологию SPIN Selling.

## Быстрый старт

```bash
# 1. Запустить vLLM сервер (в отдельном терминале)
vllm serve Qwen/Qwen3-4B-AWQ --port 8000 --quantization awq

# 2. Активация виртуального окружения
source venv/bin/activate

# 3. Запуск бота
cd src && python bot.py
```

**Требования:**
- Python 3.10+
- vLLM сервер с моделью Qwen/Qwen3-4B-AWQ (~3-4 GB VRAM)
- sentence-transformers для семантического поиска (ai-forever/FRIDA)

## vLLM Setup

> **Важно:** Этот проект использует **только vLLM**. Ollama не поддерживается.

### Установка vLLM

```bash
pip install vllm
```

### Запуск vLLM сервера

```bash
# С AWQ квантизацией (рекомендуется, ~4GB VRAM)
vllm serve Qwen/Qwen3-4B-AWQ --port 8000 --quantization awq

# Без квантизации (требует ~8GB VRAM)
vllm serve Qwen/Qwen3-4B --port 8000

# С 8B моделью (лучшее качество, ~6GB VRAM с AWQ)
vllm serve Qwen/Qwen3-8B-AWQ --port 8000 --quantization awq
```

### Проверка работы

```bash
curl http://localhost:8000/v1/models
```

### Настройка модели

В `src/settings.yaml`:

```yaml
llm:
  model: "Qwen/Qwen3-4B-AWQ"
  base_url: "http://localhost:8000/v1"
  timeout: 60
```

### Преимущества vLLM

- **Native Structured Output** — гарантированный JSON через `response_format`
- **Высокая скорость** — PagedAttention и continuous batching
- **Эффективное использование VRAM** — оптимизированное выделение памяти
- **AWQ квантизация** — 4-bit квантизация без потери качества

## Возможности

- **SPIN Selling** — структурированный подход к продажам (Situation → Problem → Implication → Need-Payoff)
- **Гибридная классификация** — 426 приоритетных паттернов + поиск по корням + лемматизация
- **Каскадный поиск** — 3-этапный retriever (exact → lemma → semantic)
- **LLM-маршрутизация** — CategoryRouter для интеллектуальной классификации категорий
- **Голосовой интерфейс** — Voice Bot с STT (Whisper) и TTS (F5-TTS)
- **Модульные фазы** — постепенное включение новых возможностей через feature flags
- **Modular Flow System** — YAML-конфигурация диалоговых flow с extends/mixins
- **Priority-driven Rules** — приоритизация обработки правил через YAML
- **Dynamic CTA** — контекстно-зависимые подсказки при fallback на основе собранных данных
- **Категоризация болей** — автоматическое определение типа боли (losing_clients, no_control, manual_work)

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
│  State Machine  │  ← SPIN-логика: S → P → I → N → Presentation
│                 │    Решает какое действие выполнить
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
│   LLM (vLLM)    │  ← Qwen3-4B-AWQ генерирует финальный ответ
└────────┬────────┘
         │
         ▼
    Ответ бота
```

## Структура проекта

```
src/
├── bot.py                  # Главный класс SalesBot, координирует компоненты
├── settings.yaml           # Конфигурация (LLM, retriever, classifier, feature_flags)
├── settings.py             # Загрузчик настроек с DotDict
├── config.py               # Интенты, состояния, SPIN-промпты
├── llm.py                  # VLLMClient — интеграция с vLLM
├── state_machine.py        # Управление состояниями диалога (SPIN flow)
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
│   ├── regex_analyzer.py   # Tier 1: Regex паттерны
│   ├── semantic_analyzer.py # Tier 2: RoSBERTa semantic
│   ├── llm_analyzer.py     # Tier 3: LLM fallback
│   └── frustration_tracker.py # Трекинг фрустрации
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
│
├── # Условные правила
├── conditions/             # Пакет условных правил
│
├── # YAML Configuration (Phase 1 Parameterization)
├── config_loader.py        # Загрузчик YAML конфигурации
├── yaml_config/            # YAML конфигурация
│   ├── constants.yaml      # Константы (limits, intents, policy)
│   ├── spin/phases.yaml    # SPIN фазы
│   ├── states/sales_flow.yaml  # Состояния диалога
│   ├── conditions/custom.yaml  # Кастомные условия
│   ├── flows/              # Модульные flow (extends/mixins)
│   │   ├── _base/          # Базовые компоненты
│   │   │   ├── states.yaml     # Общие состояния
│   │   │   ├── mixins.yaml     # Переиспользуемые блоки правил
│   │   │   └── priorities.yaml # Приоритеты обработки
│   │   └── spin_selling/   # SPIN Selling flow
│   │       ├── flow.yaml       # Конфигурация flow
│   │       └── states.yaml     # SPIN-состояния
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
│   ├── llm/                # LLM классификатор (основной)
│   │   ├── classifier.py   # LLMClassifier (vLLM + Outlines)
│   │   ├── prompts.py      # System prompt + few-shot
│   │   └── schemas.py      # Pydantic схемы для structured output
│   ├── intents/            # Подпакет классификации интентов (для fallback)
│   │   ├── patterns.py     # Приоритетные паттерны (426 шт)
│   │   ├── root_classifier.py   # Быстрая классификация по корням
│   │   └── lemma_classifier.py  # Fallback через pymorphy
│   └── extractors/         # Подпакет извлечения данных
│       └── data_extractor.py    # Извлечение структурированных данных
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

tests/                      # Тесты в 102 файлах
├── test_classifier.py      # Тесты классификатора
├── test_spin.py            # Тесты SPIN-методологии
├── test_knowledge.py       # Тесты базы знаний
├── test_cascade_retriever.py   # Тесты CascadeRetriever
├── test_cascade_advanced.py    # Продвинутые тесты каскадного поиска
├── test_category_router*.py    # Тесты LLM-маршрутизации
├── test_reranker.py        # Тесты переоценки результатов
├── test_phase*_integration.py  # Интеграционные тесты фаз 0-4
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
# LLM (Language Model) - vLLM Server
llm:
  model: "Qwen/Qwen3-4B-AWQ"
  base_url: "http://localhost:8000/v1"
  timeout: 60

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

База знаний содержит **1969 секций** в **17 YAML файлах**:

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
│   ├── classifier.py    # LLMClassifier (vLLM + Outlines)
│   ├── prompts.py       # System prompt + few-shot примеры
│   └── schemas.py       # Pydantic схемы (ClassificationResult, ExtractedData)
├── intents/
│   ├── patterns.py      # PRIORITY_PATTERNS (426 шт) для fallback
│   ├── root_classifier.py   # Быстрая классификация по корням
│   └── lemma_classifier.py  # Fallback через pymorphy2/3
└── extractors/
    └── data_extractor.py    # Извлечение structured data
```

### Публичный API:
```python
from classifier import UnifiedClassifier, HybridClassifier, TextNormalizer, DataExtractor
from classifier.llm import LLMClassifier, ClassificationResult, ExtractedData
```

### Dual-mode классификация:
- **LLM режим** (по умолчанию) — 33 интента через vLLM + Outlines, structured output
- **Hybrid режим** (fallback) — regex + pymorphy при ошибке LLM или `llm_classifier=false`

### Контекстная классификация:
Классификатор учитывает текущую SPIN-фазу:
- В фазе `situation` → информация классифицируется как `situation_provided`
- В фазе `problem` → боль классифицируется как `problem_revealed`
- В фазе `implication` → последствия как `implication_acknowledged`
- В фазе `need_payoff` → желания как `need_expressed`

Подробнее: [docs/CLASSIFIER.md](docs/CLASSIFIER.md)

## State Machine (state_machine.py)

### Приоритеты обработки:
1. **Вопросы** (`price_question`, etc.) — всегда отвечаем
2. **Rejection** — сразу переход в `soft_close`
3. **Go Back** — возврат назад по фазам (CircularFlowManager)
4. **Возражения** — обработка с защитой от зацикливания (ObjectionFlowManager)
5. **SPIN-логика** — проверка прогресса и data_complete
6. **Правила состояния** — специфичные для состояния действия
7. **Переходы по интенту** — стандартные переходы

### Умное пропускание фаз:
При `high_interest = True` можно пропустить Implication и Need-Payoff фазы.

### CircularFlowManager — возврат назад:
- Позволяет клиенту вернуться к предыдущей SPIN-фазе
- Максимум 2 возврата за диалог (защита от зацикливания)

### ObjectionFlowManager — обработка возражений:
- Управление последовательными возражениями
- Максимум 3 подряд / 5 за диалог → soft_close

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

## Feature Flags (Фазы разработки)

Система использует feature flags для постепенного включения функциональности:

| Фаза | Компонент | Флаг | Статус |
|------|-----------|------|--------|
| LLM | LLM Classifier | `llm_classifier` | ✅ Production |
| 0 | Логирование | `structured_logging` | ✅ Production |
| 0 | Метрики | `metrics_tracking` | ✅ Production |
| 1 | Fallback | `multi_tier_fallback` | ✅ Production |
| 1 | Guard | `conversation_guard` | ✅ Production |
| 2 | Cascade Tone | `cascade_tone_analyzer` | ✅ Production |
| 2 | Tone Tier 2 | `tone_semantic_tier2` | ✅ Production |
| 2 | Tone Tier 3 | `tone_llm_tier3` | ✅ Production |
| 2 | Вариации | `response_variations` | ✅ Production |
| 4 | Cascade Classifier | `cascade_classifier` | ✅ Production |
| 4 | Semantic Objection | `semantic_objection_detection` | ✅ Production |
| 5 | Context Envelope | `context_full_envelope` | ✅ Production |
| 5 | Policy Overlays | `context_policy_overlays` | ✅ Production |
| 3 | Скоринг | `lead_scoring` | ⏸️ Testing |
| 3 | Возражения | `objection_handler` | ⏸️ Testing |
| 3 | CTA | `cta_generator` | ⏸️ Development |
| 3 | Dynamic CTA | `dynamic_cta_fallback` | ⏸️ Testing |
| 4 | Disambig | `intent_disambiguation` | ⏸️ Development |

Подробнее: [docs/PHASES.md](docs/PHASES.md)

## Voice Bot (voice_bot/)

Голосовой интерфейс для разговорного взаимодействия:

```
┌───────────────────┐     ┌───────────────────┐     ┌───────────────────┐
│   faster-whisper  │ ──► │   LLM (vLLM)      │ ──► │   F5-TTS Russian  │
│   (STT)           │     │   Qwen3-4B-AWQ    │     │   + RUAccent      │
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
# Все тесты (3000+ тестов)
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

# Тесты конфигурации (1590 тестов)
pytest tests/test_config*.py -v

# Стресс-тест бота
python scripts/full_bot_stress_test.py

# Тест базы знаний
python scripts/stress_test_knowledge.py
```

### Тесты конфигурации

Система конфигурации покрыта **1590 тестами**:

| Категория | Файлы | Тестов |
|-----------|-------|--------|
| Unit тесты | `test_config_*_yaml.py` | ~450 |
| Integration | `test_config_integration.py` | ~100 |
| Behavior | `test_config_behavior_*.py` | ~280 |
| E2E сценарии | `test_config_e2e_scenarios.py` | ~70 |
| Edge cases | `test_config_edge_cases.py` | 72 |
| Property-based | `test_config_property_based.py` | 38 |

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

| Пакет | Назначение |
|-------|------------|
| `vllm` | vLLM сервер для LLM (Qwen3-8B-AWQ) |
| `outlines` | Structured output (guided decoding) |
| `pydantic` | Схемы для structured output |
| `pymorphy3` | Морфология русского языка (fallback на pymorphy2) |
| `sentence-transformers` | Эмбеддинги (ai-forever/FRIDA) |
| `openai` | HTTP-клиент для vLLM API (OpenAI-compatible) |
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
- [SETTINGS.md](docs/SETTINGS.md) — описание настроек
- [PHASES.md](docs/PHASES.md) — фазы разработки (0-5)
- [state_machine.md](docs/state_machine.md) — State Machine v2.0
- [DAG.md](docs/DAG.md) — DAG State Machine (параллельные потоки)
- [VOICE.md](docs/VOICE.md) — голосовой интерфейс

## Метрики проекта

```
Модулей Python:           102 в src/
Тестовых файлов:          102 в tests/
Секций в базе знаний:     1969 в 17 YAML файлах
Интентов LLM:             33 в classifier/llm/
Интентов Hybrid:          58 в INTENT_ROOTS
Паттернов опечаток:       663 в TYPO_FIXES
Паттернов разделения:     170 в SPLIT_PATTERNS
Приоритетных паттернов:   426 в PRIORITY_PATTERNS
Паттернов болей:          240+ в pain_patterns
Состояний диалога:        10 основных
Категорий знаний:         17
Feature Flags:            28 флагов
YAML Config Files:        11 в yaml_config/
Modular Flows:            1 (spin_selling) + _base
```
