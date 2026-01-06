# CRM Sales Bot

Чат-бот для продажи CRM-системы Wipon. Ведёт клиента от приветствия до закрытия сделки, используя методологию SPIN Selling.

## Быстрый старт

```bash
# Активация виртуального окружения
source venv/bin/activate

# Запуск бота
cd src && python bot.py
```

**Требования:**
- Python 3.11+
- Ollama с моделью `qwen3:8b-fast`
- (опционально) sentence-transformers для семантического поиска

## Возможности

- **SPIN Selling** — структурированный подход к продажам (Situation → Problem → Implication → Need-Payoff)
- **Гибридная классификация** — 214 приоритетных паттернов + поиск по корням + лемматизация
- **Каскадный поиск** — 3-этапный retriever (exact → lemma → semantic)
- **LLM-маршрутизация** — CategoryRouter для интеллектуальной классификации категорий
- **Голосовой интерфейс** — Voice Bot с STT (Whisper) и TTS (F5-TTS)
- **Модульные фазы** — постепенное включение новых возможностей через feature flags
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
│   Generator     │ ───► │ Knowledge Base  │  ← 1722 секции о продуктах Wipon
│                 │ ◄─── │ (CascadeRetriever)│   в YAML-файлах
└────────┬────────┘      └─────────────────┘
         │
         ▼
┌─────────────────┐
│   LLM (Ollama)  │  ← Qwen3:8b-fast генерирует финальный ответ
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
├── llm.py                  # Интеграция с Ollama
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
├── tone_analyzer.py        # Анализ тона клиента
├── response_variations.py  # Вариативность ответов
│
├── # Фаза 3: Оптимизация SPIN Flow
├── lead_scoring.py         # Скоринг лидов
├── objection_handler.py    # Продвинутая обработка возражений
├── cta_generator.py        # Генерация Call-to-Action
│
├── classifier/             # Пакет классификации интентов
│   ├── __init__.py         # Публичный API пакета
│   ├── normalizer.py       # Нормализация текста (опечатки, сленг)
│   ├── hybrid.py           # HybridClassifier — главный класс
│   ├── intents/            # Подпакет классификации интентов
│   │   ├── patterns.py     # Приоритетные паттерны (214 шт)
│   │   ├── root_classifier.py   # Быстрая классификация по корням
│   │   └── lemma_classifier.py  # Fallback через pymorphy
│   └── extractors/         # Подпакет извлечения данных
│       └── data_extractor.py    # Извлечение структурированных данных
│
└── knowledge/              # База знаний о продуктах Wipon
    ├── __init__.py         # Публичный API (WIPON_KNOWLEDGE, get_retriever)
    ├── base.py             # Структуры данных (KnowledgeSection, KnowledgeBase)
    ├── loader.py           # Загрузчик YAML файлов
    ├── lemmatizer.py       # Лемматизация для поиска
    ├── retriever.py        # CascadeRetriever (3-этапный поиск)
    ├── category_router.py  # LLM-классификация категорий
    ├── reranker.py         # Cross-encoder переоценка результатов
    └── data/               # YAML-файлы базы знаний (1722 секции)
        ├── _meta.yaml      # Метаданные (company, stats)
        ├── equipment.yaml  # Оборудование (183 секции)
        ├── tis.yaml        # Товарно-информационная система (166 секций)
        ├── support.yaml    # Техподдержка (156 секций)
        ├── products.yaml   # Продукты (116 секций)
        ├── pricing.yaml    # Тарифы (104 секции)
        ├── inventory.yaml  # Складской учёт (97 секций)
        ├── integrations.yaml   # Интеграции (71 секция)
        ├── regions.yaml    # Регионы (60 секций)
        ├── features.yaml   # Функции (59 секций)
        ├── analytics.yaml  # Аналитика (52 секции)
        ├── employees.yaml  # Управление персоналом (43 секции)
        ├── fiscal.yaml     # Фискализация (41 секция)
        ├── stability.yaml  # Стабильность (31 секция)
        ├── mobile.yaml     # Мобильное приложение (31 секция)
        ├── promotions.yaml # Акции и скидки (19 секций)
        ├── competitors.yaml # Конкуренты (7 секций)
        └── faq.yaml        # Часто задаваемые вопросы (3 секции)

voice_bot/                  # Голосовой интерфейс
├── voice_pipeline.py       # Полный pipeline: STT → LLM → TTS
├── CosyVoice/              # Синтез речи (submodule)
├── fish-speech/            # Speech synthesis (submodule)
├── checkpoints/            # Модели F5-TTS, OpenAudio
├── models/                 # XTTS-RU-IPA модели
└── test_*.py               # Тесты компонентов (STT, TTS, LLM)

tests/                      # 1285+ тестов в 34 файлах
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
# LLM (Language Model)
llm:
  model: "qwen3:8b-fast"
  base_url: "http://localhost:11434"
  timeout: 60

# Retriever (Поиск по базе знаний)
retriever:
  use_embeddings: true
  embedder_model: "ai-forever/ru-en-RoSBERTa"
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
  structured_logging: true    # JSON логи
  metrics_tracking: true      # Трекинг метрик
  multi_tier_fallback: true   # 4-уровневый fallback
  conversation_guard: true    # Защита от зацикливания
  tone_analysis: false        # Анализ тона (выключен)
  response_variations: true   # Вариативность ответов
  lead_scoring: false         # Скоринг лидов (выключен)
  objection_handler: false    # Обработка возражений (выключен)
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

База знаний содержит **1722 секции** в **18 YAML файлах**:

| Категория | Секций | Описание |
|-----------|--------|----------|
| equipment | 275 | Оборудование (кассы, принтеры, сканеры) |
| products | 253 | Продукты Wipon |
| tis | 192 | Товарно-информационная система |
| support | 189 | Техподдержка и обслуживание |
| pricing | 184 | Тарифы и стоимость |
| inventory | 103 | Складской учёт |
| features | 93 | Функции системы |
| integrations | 83 | Интеграции (1С, Kaspi, Telegram) |
| regions | 75 | Регионы Казахстана |
| analytics | 62 | Аналитика и отчёты |
| employees | 56 | Управление персоналом |
| fiscal | 46 | Фискализация |
| stability | 42 | Стабильность и надёжность |
| mobile | 35 | Мобильное приложение |
| promotions | 24 | Акции и скидки |
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
3. Semantic Match ─── cosine similarity эмбеддингов (ai-forever/ru-en-RoSBERTa)
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

Пакет классификации разбит на модули для удобства поддержки:

```
classifier/
├── __init__.py          # API: HybridClassifier, TextNormalizer, DataExtractor
├── normalizer.py        # TYPO_FIXES (663 шт), SPLIT_PATTERNS (170 шт)
├── hybrid.py            # HybridClassifier — оркестратор
├── intents/
│   ├── patterns.py      # PRIORITY_PATTERNS (214 шт) для "не интересно" и т.д.
│   ├── root_classifier.py   # Быстрая классификация по корням
│   └── lemma_classifier.py  # Fallback через pymorphy2/3
└── extractors/
    └── data_extractor.py    # Извлечение structured data
```

### Публичный API:
```python
from classifier import HybridClassifier, TextNormalizer, DataExtractor
from classifier import TYPO_FIXES, SPLIT_PATTERNS, PRIORITY_PATTERNS
```

### Гибридная классификация:
1. **Приоритетные паттерны** — "не интересно" → rejection (не agreement)
2. **Быстрый поиск по корням слов** — основной метод
3. **Fallback на pymorphy3** (или pymorphy2) — если корни не сработали

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
3. **SPIN-логика** — проверка прогресса и data_complete
4. **Правила состояния** — специфичные для состояния действия
5. **Переходы по интенту** — стандартные переходы

### Умное пропускание фаз:
При `high_interest = True` можно пропустить Implication и Need-Payoff фазы.

## Feature Flags (Фазы разработки)

Система использует feature flags для постепенного включения функциональности:

| Фаза | Компонент | Флаг | Статус |
|------|-----------|------|--------|
| 0 | Логирование | `structured_logging` | ✅ Включено |
| 0 | Метрики | `metrics_tracking` | ✅ Включено |
| 1 | Fallback | `multi_tier_fallback` | ✅ Включено |
| 1 | Guard | `conversation_guard` | ✅ Включено |
| 2 | Тон | `tone_analysis` | ⏸️ Выключено |
| 2 | Вариации | `response_variations` | ✅ Включено |
| 3 | Скоринг | `lead_scoring` | ⏸️ Выключено |
| 3 | Возражения | `objection_handler` | ⏸️ Выключено |
| 3 | CTA | `cta_generator` | ⏸️ Выключено |
| 4 | Disambig | `intent_disambiguation` | ⏸️ Выключено |
| 5 | Dynamic CTA | `dynamic_cta_fallback` | ⏸️ Выключено |

Подробнее: [docs/PHASES.md](docs/PHASES.md)

## Voice Bot (voice_bot/)

Голосовой интерфейс для разговорного взаимодействия:

```
┌───────────────────┐     ┌───────────────────┐     ┌───────────────────┐
│   faster-whisper  │ ──► │   LLM (Ollama)    │ ──► │   F5-TTS Russian  │
│   (STT)           │     │   Qwen3:8b-fast   │     │   + RUAccent      │
└───────────────────┘     └───────────────────┘     └───────────────────┘
      Голос клиента              Текст                   Голос бота
```

Подробнее: [docs/VOICE.md](docs/VOICE.md)

## Тестирование

```bash
# Все тесты (1056+ тестов)
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

# Стресс-тест бота
python scripts/full_bot_stress_test.py

# Тест базы знаний
python scripts/stress_test_knowledge.py
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
| `ollama` + `qwen3:8b-fast` | Локальная LLM |
| `pymorphy3` | Морфология русского языка (fallback на pymorphy2) |
| `sentence-transformers` | Эмбеддинги (ai-forever/ru-en-RoSBERTa) |
| `requests` | HTTP-клиент для Ollama API |
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
- [PHASES.md](docs/PHASES.md) — фазы разработки (0-3)
- [VOICE.md](docs/VOICE.md) — голосовой интерфейс

## Метрики проекта

```
Модулей Python:           18+ в src/
Тестов:                   1285+ в 34 файлах
Секций в базе знаний:     1722 в 18 YAML файлах
Интентов:                 50+ в INTENT_ROOTS
Паттернов опечаток:       699+ в TYPO_FIXES
Паттернов разделения:     170 в SPLIT_PATTERNS
Приоритетных паттернов:   214 в PRIORITY_PATTERNS
Паттернов болей:          240+ в pain_patterns
Состояний диалога:        10 основных
Категорий знаний:         17
Feature Flags:            12 флагов
```
