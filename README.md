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
│   Generator     │ ───► │ Knowledge Base  │  ← 446 секций о продуктах Wipon
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
├── settings.yaml           # Конфигурация (LLM, retriever, classifier)
├── settings.py             # Загрузчик настроек с DotDict
├── config.py               # Интенты, состояния, SPIN-промпты
├── llm.py                  # Интеграция с Ollama
├── state_machine.py        # Управление состояниями диалога (SPIN flow)
├── generator.py            # Генерация ответов через LLM
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
    └── data/               # YAML-файлы базы знаний (446 секций)
        ├── _meta.yaml      # Метаданные (company, stats)
        ├── pricing.yaml    # Тарифы (24 секции)
        ├── products.yaml   # Продукты (10 секций)
        ├── features.yaml   # Функции (3 секции)
        ├── integrations.yaml   # Интеграции (24 секции)
        ├── support.yaml    # Техподдержка (70 секций)
        ├── equipment.yaml  # Оборудование (60 секций)
        ├── tis.yaml        # Товарно-информационная система (132 секции)
        ├── analytics.yaml  # Аналитика (27 секций)
        ├── inventory.yaml  # Складской учёт (21 секция)
        ├── employees.yaml  # Управление персоналом (21 секция)
        ├── fiscal.yaml     # Фискализация (7 секций)
        ├── mobile.yaml     # Мобильное приложение (5 секций)
        ├── promotions.yaml # Акции и скидки (10 секций)
        ├── stability.yaml  # Стабильность (14 секций)
        ├── regions.yaml    # Регионы (4 секции)
        ├── faq.yaml        # Часто задаваемые вопросы (3 секции)
        └── other.yaml      # Прочее (11 секций)

tests/                      # 294 теста
├── test_classifier.py      # Тесты классификатора
├── test_spin.py            # Тесты SPIN-методологии
├── test_knowledge.py       # Тесты базы знаний
├── test_cascade_retriever.py   # Тесты CascadeRetriever
├── test_cascade_advanced.py    # Продвинутые тесты каскадного поиска
├── test_knowledge_yaml.py  # Валидация YAML файлов
├── test_settings.py        # Тесты настроек
└── test_bug_fixes.py       # Регрессионные тесты

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

# Generator (Генерация ответов)
generator:
  max_retries: 3
  history_length: 4
  retriever_top_k: 2

# Classifier (Классификация интентов)
classifier:
  weights:
    root_match: 1.0
    phrase_match: 2.0
    lemma_match: 1.5
  thresholds:
    high_confidence: 0.7
    min_confidence: 0.3
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

База знаний содержит **446 секций** в **18 YAML файлах**:

| Категория | Секций | Описание |
|-----------|--------|----------|
| tis | 132 | Товарно-информационная система |
| support | 70 | Техподдержка |
| equipment | 60 | Оборудование |
| analytics | 27 | Аналитика |
| pricing | 24 | Тарифы |
| integrations | 24 | Интеграции |
| inventory | 21 | Складской учёт |
| employees | 21 | Управление персоналом |
| stability | 14 | Стабильность |
| products | 10 | Продукты |
| promotions | 10 | Акции |
| fiscal | 7 | Фискализация |
| mobile | 5 | Мобильное приложение |
| regions | 4 | Регионы |
| features | 3 | Функции |
| faq | 3 | FAQ |
| other | 11 | Прочее |

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

## Тестирование

```bash
# Все тесты (294 теста)
pytest tests/ -v

# Только тесты классификатора
pytest tests/test_classifier.py -v

# Только SPIN-тесты
pytest tests/test_spin.py -v

# Только тесты базы знаний
pytest tests/test_knowledge.py -v

# Тесты каскадного retriever
pytest tests/test_cascade_retriever.py -v

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
