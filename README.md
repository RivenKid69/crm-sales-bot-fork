# CRM Sales Bot

Чат-бот для продажи CRM-системы Wipon. Ведёт клиента от приветствия до закрытия сделки, используя методологию SPIN Selling.

## Быстрый старт

```bash
source venv/bin/activate
cd src && python bot.py
```

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
│   Generator     │ ───► │ Knowledge Base  │  ← Факты о продуктах Wipon
│                 │ ◄─── │   (Retriever)   │    (тарифы, функции, интеграции)
└────────┬────────┘      └─────────────────┘
         │
         ▼
┌─────────────────┐
│   LLM (Ollama)  │  ← Qwen3 генерирует финальный ответ
└────────┬────────┘
         │
         ▼
    Ответ бота
```

## Структура файлов

```
src/
├── bot.py              # Главный класс, координирует компоненты
├── classifier/         # Пакет классификации интентов
│   ├── __init__.py     # Публичный API пакета
│   ├── normalizer.py   # Нормализация текста (опечатки, сленг)
│   ├── hybrid.py       # HybridClassifier — главный класс
│   ├── intents/        # Подпакет классификации интентов
│   │   ├── __init__.py
│   │   ├── patterns.py        # Приоритетные паттерны (214 шт)
│   │   ├── root_classifier.py # Быстрая классификация по корням
│   │   └── lemma_classifier.py # Fallback через pymorphy
│   └── extractors/     # Подпакет извлечения данных
│       ├── __init__.py
│       └── data_extractor.py  # Извлечение структурированных данных
├── state_machine.py    # Управление состояниями диалога (SPIN flow)
├── generator.py        # Генерация ответов через LLM
├── config.py           # Интенты, состояния, SPIN-промпты
├── llm.py              # Интеграция с Ollama
└── knowledge/
    ├── data.py         # База знаний о продуктах Wipon
    ├── retriever.py    # Гибридный поиск (keywords + embeddings)
    └── base.py         # Структуры данных

tests/
├── test_knowledge.py   # Тесты базы знаний
├── test_spin.py        # Тесты SPIN-методологии
└── test_classifier.py  # Тесты классификатора (100+ тестов)
```

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

## Промпт-шаблоны (config.py)

### Базовые:
| Шаблон | Когда используется |
|--------|-------------------|
| `greet_back` | Ответ на приветствие |
| `answer_question` | Ответ на вопрос клиента |
| `deflect_and_continue` | Уход от цены к ситуации |
| `presentation` | Презентация решения |
| `handle_objection` | Возражение "дорого" |
| `soft_close` | Вежливое завершение |
| `close` | Запрос контакта |

### SPIN-специфичные:
| Шаблон | Фаза | Задача |
|--------|------|--------|
| `spin_situation` | S | Спросить о ситуации |
| `spin_problem` | P | Выявить проблемы |
| `spin_implication` | I | Осознать последствия |
| `spin_need_payoff` | N | Сформулировать ценность |
| `transition_to_spin_problem` | S→P | Переход к проблемам |
| `transition_to_spin_implication` | P→I | Переход к последствиям |
| `transition_to_spin_need_payoff` | I→N | Переход к ценности |
| `transition_to_presentation` | N→Pres | Персонализированная презентация |

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

### Извлечение данных:
- `company_size` — regex паттерны ("нас 10", "команда из 5", "8 официантов")
- `pain_point` — 50+ паттернов ("теряем клиентов", "низкие продажи")
- `current_tools` — Excel, 1С, вручную, блокнот
- `business_type` — розница, общепит, опт, услуги
- `pain_impact` — количественные потери ("10 клиентов", "3 часа в день")
- `desired_outcome` — желаемые результаты ("автоматизировать", "упростить")

### Нормализация текста:
- **TYPO_FIXES** — 663 автозамены опечаток ("прайс" → "цена", "скок" → "сколько")
- **SPLIT_PATTERNS** — 170 паттернов слитного текста ("сколькостоит" → "сколько стоит")

### Контекстная классификация:
Классификатор учитывает текущую SPIN-фазу:
- В фазе `situation` → информация классифицируется как `situation_provided`
- В фазе `problem` → боль классифицируется как `problem_revealed`
- В фазе `implication` → последствия как `implication_acknowledged`
- В фазе `need_payoff` → желания как `need_expressed`

## State Machine (state_machine.py)

### Приоритеты обработки:
1. **Вопросы** (`price_question`, etc.) — всегда отвечаем
2. **Rejection** — сразу переход в `soft_close`
3. **SPIN-логика** — проверка прогресса и data_complete
4. **Правила состояния** — специфичные для состояния действия
5. **Переходы по интенту** — стандартные переходы

### Умное пропускание фаз:
При `high_interest = True` можно пропустить Implication и Need-Payoff фазы.

## База знаний (knowledge/)

- **data.py** — факты о продуктах Wipon (учёт товаров, касса, мобильное приложение, тарифы)
- **retriever.py** — гибридный поиск:
  1. Keyword search по категориям
  2. Fallback на rubert-tiny2 embeddings (опционально)

## Тестирование

```bash
# Все тесты (145 тестов)
pytest tests/ -v

# Только тесты классификатора (100+ тестов)
pytest tests/test_classifier.py -v

# Только SPIN-тесты
pytest tests/test_spin.py -v

# Только тесты базы знаний
pytest tests/test_knowledge.py -v

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

- `ollama` + модель `qwen3:8b` — локальная LLM
- `pymorphy3` — морфология русского языка (fallback на pymorphy2)
- `sentence-transformers` — embeddings для базы знаний (опционально)
- `requests` — HTTP-клиент для Ollama API
- `pytest` — тестирование

Установка:
```bash
pip install -r requirements.txt
```
