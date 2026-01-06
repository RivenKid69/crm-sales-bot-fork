# Classifier — Пакет классификации интентов

## Обзор

Пакет `classifier/` отвечает за:
1. **Нормализацию текста** — исправление опечаток, сленга, слитного текста
2. **Классификацию интентов** — определение намерения пользователя
3. **Извлечение данных** — структурированные данные из сообщения
4. **Контекстную классификацию** — учёт SPIN-фазы и истории диалога

## Структура пакета

```
classifier/
├── __init__.py              # Публичный API
├── normalizer.py            # TextNormalizer, TYPO_FIXES, SPLIT_PATTERNS
├── hybrid.py                # HybridClassifier — главный оркестратор
├── intents/                 # Классификация интентов
│   ├── __init__.py
│   ├── patterns.py          # PRIORITY_PATTERNS (214 паттернов)
│   ├── root_classifier.py   # Быстрая классификация по корням
│   └── lemma_classifier.py  # Fallback через pymorphy
└── extractors/              # Извлечение данных
    ├── __init__.py
    └── data_extractor.py    # DataExtractor
```

## Публичный API

```python
from classifier import HybridClassifier, TextNormalizer, DataExtractor
from classifier import TYPO_FIXES, SPLIT_PATTERNS, PRIORITY_PATTERNS
```

### HybridClassifier

Главный класс для классификации сообщений.

```python
classifier = HybridClassifier()

result = classifier.classify(
    message="нас 10 человек, теряем клиентов",
    context={"spin_phase": "situation"}
)

# result:
{
    "intent": "situation_provided",
    "confidence": 0.85,
    "extracted_data": {
        "company_size": 10,
        "pain_point": "теряем клиентов"
    },
    "debug": {
        "normalized": "нас 10 человек теряем клиентов",
        "root_intent": "situation_provided",
        "lemma_intent": None
    }
}
```

### TextNormalizer

Нормализация текста перед классификацией.

```python
normalizer = TextNormalizer()

# Исправление опечаток
text = normalizer.normalize("скок стоит прайс?")
# → "сколько стоит цена?"

# Разбиение слитного текста
text = normalizer.normalize("сколькостоит")
# → "сколько стоит"
```

### DataExtractor

Извлечение структурированных данных.

```python
extractor = DataExtractor()

data = extractor.extract("у нас 10 человек, работаем в розничной торговле")
# → {"company_size": 10, "business_type": "розничная торговля"}

data = extractor.extract("теряем примерно 10 клиентов в месяц")
# → {"pain_point": "теряем клиентов", "pain_impact": "10 клиентов в месяц"}
```

## Компоненты

### 1. Нормализация (normalizer.py)

#### TYPO_FIXES (663 записи)

Словарь автозамен для исправления опечаток и сленга:

```python
TYPO_FIXES = {
    # Ценовые синонимы
    "прайс": "цена",
    "прайсы": "цены",
    "ценник": "цена",

    # Сокращения
    "скок": "сколько",
    "чё": "что",
    "норм": "нормально",

    # Опечатки
    "систеа": "система",
    "функционла": "функционал",
    # ... 660+ записей
}
```

#### SPLIT_PATTERNS (170 паттернов)

Паттерны для разбиения слитного текста:

```python
SPLIT_PATTERNS = [
    ("сколькостоит", "сколько стоит"),
    ("естьинтеграция", "есть интеграция"),
    ("какаяцена", "какая цена"),
    # ... 167+ паттернов
]
```

### 2. Классификация интентов (intents/)

#### Приоритетные паттерны (patterns.py)

214 regex-паттернов для приоритетных интентов:

```python
PRIORITY_PATTERNS = [
    # Rejection (приоритет над agreement)
    (r"не\s*интересно", "rejection", 0.95),
    (r"не\s*надо", "rejection", 0.95),
    (r"отказываюсь", "rejection", 0.95),

    # Price questions
    (r"скольк\w*\s*стоит", "price_question", 0.95),
    (r"цен\w+\s*(на|за)?", "price_question", 0.90),

    # High interest signals
    (r"очень\s+интересн", "high_interest", 0.90),
    (r"хотим\s+попробовать", "high_interest", 0.85),
    # ... 208+ паттернов
]
```

**Зачем нужны приоритетные паттерны?**

Решают проблему неоднозначности. Например:
- "не интересно" содержит корень "интерес" → без паттерна определится как `agreement`
- С паттерном `r"не\s*интересно"` → корректно определяется как `rejection`

#### RootClassifier (root_classifier.py)

Быстрая классификация по корням слов из `config.INTENT_ROOTS`:

```python
# config.py
INTENT_ROOTS = {
    "agreement": ["согласен", "да", "хорошо", "ок", "давай", "интерес"],
    "rejection": ["нет", "не надо", "отказ", "не хочу"],
    "price_question": ["цен", "стоим", "стоит", "тариф", "прайс"],
    # ...
}
```

Алгоритм:
1. Проверяем приоритетные паттерны
2. Ищем корни в тексте
3. Считаем score для каждого интента
4. Возвращаем интент с максимальным score

#### LemmaClassifier (lemma_classifier.py)

Fallback через pymorphy2/3:

```python
# Когда используется:
# - RootClassifier дал низкую уверенность (< threshold)
# - Слова в необычных формах

# Пример:
# "мне интересно" → лемма "интересный" → agreement
# "заинтересовались" → лемма "заинтересоваться" → agreement
```

### 3. Извлечение данных (extractors/)

#### DataExtractor (data_extractor.py)

Извлекает структурированные данные из сообщений.

**Поддерживаемые поля:**

| Поле | Описание | Примеры паттернов |
|------|----------|-------------------|
| `company_size` | Размер команды | "нас 10", "команда из 5", "8 официантов" |
| `current_tools` | Текущие инструменты | "Excel", "1С", "вручную", "блокнот" |
| `business_type` | Тип бизнеса | "розница", "общепит", "опт", "услуги" |
| `pain_point` | Боль клиента | "теряем клиентов", "низкие продажи" |
| `pain_impact` | Количественные потери | "10 клиентов", "3 часа в день" |
| `financial_impact` | Финансовые потери | "~50 000 в месяц" |
| `desired_outcome` | Желаемый результат | "автоматизировать", "упростить" |
| `value_acknowledged` | Признание ценности | true/false |
| `contact_info` | Контакт клиента | телефон, email |
| `high_interest` | Высокий интерес | true/false |
| `pain_category` | Категория боли | `losing_clients`, `no_control`, `manual_work` |
| `option_index` | Индекс выбранного варианта | 0-3 (для numbered responses) |

### pain_category — Категоризация боли

DataExtractor автоматически определяет категорию боли на основе ключевых слов:

```python
PAIN_CATEGORY_KEYWORDS = {
    "losing_clients": [  # Потеря клиентов, продаж
        "теря", "клиент", "отток", "упуска", "сделк", "продаж",
        "выручк", "конверси", "воронк", "недовольн"
    ],
    "no_control": [      # Отсутствие контроля
        "контрол", "вид", "прозрачн", "хаос", "статистик",
        "аналитик", "отчёт", "kpi", "руковод"
    ],
    "manual_work": [     # Ручная работа
        "excel", "эксел", "рутин", "вручную", "времен",
        "долго", "дубл", "ошиб", "путаниц"
    ]
}
```

Пример:
```python
extractor = DataExtractor()
result = extractor.extract("Мы теряем клиентов")
# → {"pain_point": "потеря клиентов", "pain_category": "losing_clients"}

result = extractor.extract("Нет контроля над менеджерами")
# → {"pain_point": "нет контроля", "pain_category": "no_control"}

result = extractor.extract("Всё ведём в Excel")
# → {"pain_point": "работа в Excel", "pain_category": "manual_work"}
```

**Примеры извлечения:**

```python
# company_size
"нас 10 человек" → {"company_size": 10}
"команда из 5 продавцов" → {"company_size": 5}
"8 официантов работает" → {"company_size": 8}

# current_tools
"пользуемся Excel" → {"current_tools": "Excel"}
"ведём учёт вручную" → {"current_tools": "вручную"}
"есть 1С" → {"current_tools": "1С"}

# pain_point (50+ паттернов)
"теряем клиентов" → {"pain_point": "потеря клиентов"}
"низкие продажи" → {"pain_point": "низкие продажи"}
"путаемся в заказах" → {"pain_point": "путаница в заказах"}

# contact_info
"+7 999 123-45-67" → {"contact_info": {"phone": "+79991234567"}}
"email@example.com" → {"contact_info": {"email": "email@example.com"}}
```

## Контекстная классификация

Классификатор учитывает текущую SPIN-фазу и историю диалога:

```python
# Без контекста
classifier.classify("10 человек")
# → intent: "info_provided"

# С контекстом фазы Situation
classifier.classify("10 человек", context={"spin_phase": "situation"})
# → intent: "situation_provided"

# С контекстом фазы Problem
classifier.classify("теряем клиентов", context={"spin_phase": "problem"})
# → intent: "problem_revealed"
```

**Маппинг фаз:**

| SPIN-фаза | Базовый интент | Контекстный интент |
|-----------|----------------|-------------------|
| `situation` | `info_provided` | `situation_provided` |
| `problem` | `info_provided` + pain | `problem_revealed` |
| `implication` | `info_provided` + impact | `implication_acknowledged` |
| `need_payoff` | `info_provided` + desire | `need_expressed` |

**Контекст предыдущего хода:**

Для интерпретации коротких ответов используется:
- `last_action` — последнее действие бота
- `last_intent` — последний интент пользователя

```python
# Бот спросил "Сколько человек в команде?"
# Пользователь ответил "10"
context = {
    "spin_phase": "situation",
    "last_action": "spin_situation"
}
classifier.classify("10", context)
# → intent: "situation_provided", extracted_data: {"company_size": 10}
```

## Веса и пороги (из settings.yaml)

```yaml
classifier:
  weights:
    root_match: 1.0       # Совпадение по корню слова
    phrase_match: 2.0     # Точное совпадение фразы
    lemma_match: 1.5      # Совпадение по лемме

  thresholds:
    high_confidence: 0.7  # Порог для быстрого возврата
    min_confidence: 0.3   # Минимальная уверенность (ниже = unclear)
```

## Расширение

### Добавление нового интента

1. **Добавить корни** в `config.INTENT_ROOTS`:
```python
INTENT_ROOTS = {
    # ...
    "new_intent": ["корень1", "корень2"],
}
```

2. **Добавить фразы** в `config.INTENT_PHRASES`:
```python
INTENT_PHRASES = {
    # ...
    "new_intent": ["фраза один", "фраза два"],
}
```

3. **(Опционально) Добавить приоритетный паттерн** в `intents/patterns.py`:
```python
PRIORITY_PATTERNS = [
    # ...
    (r"regex_pattern", "new_intent", 0.95),
]
```

### Добавление нового экстрактора

В `extractors/data_extractor.py`:

```python
def _extract_new_field(self, text: str) -> Optional[str]:
    """Извлечение нового поля"""
    patterns = [
        r"паттерн\s+(\w+)",
        r"другой\s+паттерн",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    return None

def extract(self, text: str) -> Dict[str, Any]:
    data = {}
    # ... существующие экстракторы

    new_field = self._extract_new_field(text)
    if new_field:
        data["new_field"] = new_field

    return data
```

### Добавление новой опечатки

В `normalizer.py` в словарь `TYPO_FIXES`:

```python
TYPO_FIXES = {
    # ...
    "опечтка": "опечатка",
}
```

### Добавление слитного паттерна

В `normalizer.py` в список `SPLIT_PATTERNS`:

```python
SPLIT_PATTERNS = [
    # ...
    ("новыйслитныйтекст", "новый слитный текст"),
]
```

## Тестирование

```bash
# Все тесты классификатора
pytest tests/test_classifier.py -v

# Конкретный тест
pytest tests/test_classifier.py::test_rejection_priority -v

# Тесты с покрытием
pytest tests/test_classifier.py --cov=classifier --cov-report=html
```

## Производительность

| Компонент | Время на 1000 сообщений |
|-----------|-------------------------|
| TextNormalizer | ~50ms |
| RootClassifier | ~30ms |
| LemmaClassifier | ~500ms (с pymorphy) |
| DataExtractor | ~100ms |
| **HybridClassifier (итого)** | **~200ms** (без fallback) |

Рекомендации:
- RootClassifier покрывает 90%+ случаев
- LemmaClassifier используется только при низкой уверенности
- Для максимальной скорости можно увеличить `high_confidence` порог в settings

## Статистика

| Компонент | Количество |
|-----------|------------|
| TYPO_FIXES | 699+ записей |
| SPLIT_PATTERNS | 170 паттернов |
| PRIORITY_PATTERNS | 214 паттернов |
| pain_patterns | 240+ паттернов |
| PAIN_CATEGORY_KEYWORDS | 3 категории, 30+ ключевых слов |
| Интенты в INTENT_ROOTS | ~15 интентов |
| Экстракторы в DataExtractor | 12+ полей |
