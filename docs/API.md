# API Reference

## Основные классы

### SalesBot

Главный класс бота, оркестрирующий все компоненты.

```python
from bot import SalesBot
from llm import OllamaLLM

llm = OllamaLLM()
bot = SalesBot(llm)
```

#### Методы

##### `process(user_message: str) -> Dict`

Обрабатывает сообщение пользователя и возвращает ответ.

```python
result = bot.process("Привет, сколько стоит ваша CRM?")

# Возвращает:
{
    "response": "Здравствуйте! Тарифы начинаются от 990 ₽/мес...",
    "intent": "price_question",
    "action": "answer_question",
    "state": "greeting",
    "is_final": False,
    "spin_phase": None
}
```

##### `reset()`

Сбрасывает состояние для нового диалога.

```python
bot.reset()
```

#### Атрибуты

| Атрибут | Тип | Описание |
|---------|-----|----------|
| `classifier` | `HybridClassifier` | Классификатор интентов |
| `state_machine` | `StateMachine` | Управление состояниями |
| `generator` | `ResponseGenerator` | Генерация ответов |
| `history` | `List[Dict]` | История диалога |

---

### HybridClassifier

Гибридный классификатор интентов.

```python
from classifier import HybridClassifier

classifier = HybridClassifier()
```

#### Методы

##### `classify(message: str, context: Dict = None) -> Dict`

Классифицирует сообщение и извлекает данные.

```python
result = classifier.classify(
    message="нас 10 человек, работаем в рознице",
    context={"spin_phase": "situation"}
)

# Возвращает:
{
    "intent": "situation_provided",
    "confidence": 0.85,
    "extracted_data": {
        "company_size": 10,
        "business_type": "розничная торговля"
    },
    "debug": {
        "normalized": "нас 10 человек работаем в рознице",
        "root_intent": "situation_provided",
        "root_confidence": 0.85,
        "lemma_intent": None
    }
}
```

**Параметры context:**

| Ключ | Тип | Описание |
|------|-----|----------|
| `spin_phase` | `str` | Текущая SPIN-фаза: `situation`, `problem`, `implication`, `need_payoff` |
| `state` | `str` | Текущее состояние диалога |
| `collected_data` | `Dict` | Уже собранные данные |
| `missing_data` | `List[str]` | Недостающие поля |

---

### TextNormalizer

Нормализация текста (опечатки, сленг, слитный текст).

```python
from classifier import TextNormalizer

normalizer = TextNormalizer()
```

#### Методы

##### `normalize(text: str) -> str`

Нормализует текст.

```python
text = normalizer.normalize("скок стоит прайс?")
# → "сколько стоит цена?"

text = normalizer.normalize("сколькостоит")
# → "сколько стоит"
```

---

### DataExtractor

Извлечение структурированных данных из текста.

```python
from classifier import DataExtractor

extractor = DataExtractor()
```

#### Методы

##### `extract(text: str) -> Dict[str, Any]`

Извлекает все доступные данные из текста.

```python
data = extractor.extract("нас 10 человек, теряем примерно 10 клиентов в месяц")

# Возвращает:
{
    "company_size": 10,
    "pain_point": "потеря клиентов",
    "pain_impact": "10 клиентов в месяц"
}
```

**Извлекаемые поля:**

| Поле | Тип | Описание |
|------|-----|----------|
| `company_size` | `int` | Размер команды |
| `current_tools` | `str` | Текущие инструменты |
| `business_type` | `str` | Тип бизнеса |
| `pain_point` | `str` | Боль клиента |
| `pain_impact` | `str` | Количественные потери |
| `financial_impact` | `str` | Финансовые потери |
| `desired_outcome` | `str` | Желаемый результат |
| `value_acknowledged` | `bool` | Признание ценности |
| `contact_info` | `Dict` | Контакт (phone/email) |
| `high_interest` | `bool` | Высокий интерес |

---

### StateMachine

Управление состояниями диалога (SPIN flow).

```python
from state_machine import StateMachine

sm = StateMachine()
```

#### Методы

##### `process(intent: str, extracted_data: Dict) -> Dict`

Обрабатывает интент и определяет следующее действие.

```python
result = sm.process(
    intent="situation_provided",
    extracted_data={"company_size": 10}
)

# Возвращает:
{
    "action": "spin_situation",          # Действие для генератора
    "next_state": "spin_situation",      # Следующее состояние
    "is_final": False,                   # Диалог завершён?
    "collected_data": {"company_size": 10},
    "missing_data": ["current_tools"],   # Чего не хватает
    "goal": "Узнать ситуацию клиента",
    "spin_phase": "situation",
    "optional_data": ["business_type"]
}
```

##### `reset()`

Сбрасывает состояние.

```python
sm.reset()
```

#### Атрибуты

| Атрибут | Тип | Описание |
|---------|-----|----------|
| `state` | `str` | Текущее состояние |
| `collected_data` | `Dict` | Собранные данные |

---

### ResponseGenerator

Генерация ответов через LLM.

```python
from generator import ResponseGenerator
from llm import OllamaLLM

llm = OllamaLLM()
generator = ResponseGenerator(llm)
```

#### Методы

##### `generate(action: str, context: Dict) -> str`

Генерирует ответ на основе действия и контекста.

```python
response = generator.generate(
    action="transition_to_spin_problem",
    context={
        "user_message": "нас 10 человек",
        "collected_data": {"company_size": 10},
        "spin_phase": "problem"
    }
)

# → "Понял, команда из 10 человек. Какая главная сложность с учётом сейчас?"
```

**Поддерживаемые actions:**

| Action | Описание |
|--------|----------|
| `greet_back` | Ответ на приветствие |
| `answer_question` | Ответ на вопрос (с базой знаний) |
| `spin_situation` | Вопрос о ситуации |
| `spin_problem` | Вопрос о проблемах |
| `spin_implication` | Вопрос о последствиях |
| `spin_need_payoff` | Вопрос о ценности |
| `transition_to_spin_problem` | Переход S→P |
| `transition_to_spin_implication` | Переход P→I |
| `transition_to_spin_need_payoff` | Переход I→N |
| `transition_to_presentation` | Переход N→Pres |
| `presentation` | Презентация решения |
| `handle_objection` | Работа с возражением |
| `close` | Запрос контакта |
| `soft_close` | Вежливое завершение |

---

### KnowledgeRetriever

Поиск по базе знаний.

```python
from knowledge import KnowledgeRetriever

retriever = KnowledgeRetriever()
```

#### Методы

##### `search(query: str, top_k: int = 3) -> List[SearchResult]`

Поиск релевантных секций.

```python
results = retriever.search("тарифы Wipon", top_k=3)

# Возвращает:
[
    SearchResult(
        section=KnowledgeSection(id="pricing_basic", ...),
        score=0.95,
        match_type="keyword"
    ),
    ...
]
```

##### `get_context(query: str, max_tokens: int = 500) -> str`

Получить контекст для LLM.

```python
context = retriever.get_context("какие есть интеграции?")

# → "Wipon интегрируется с 1С, Telegram, WhatsApp..."
```

---

### OllamaLLM

Интеграция с Ollama.

```python
from llm import OllamaLLM

llm = OllamaLLM(model="qwen3:8b", base_url="http://localhost:11434")
```

#### Методы

##### `generate(prompt: str, system: str = None) -> str`

Генерация ответа.

```python
response = llm.generate(
    prompt="Ответь на вопрос клиента: сколько стоит CRM?",
    system="Ты — продавец CRM-системы Wipon."
)
```

---

## Конфигурация (config.py)

### INTENT_ROOTS

Словарь корней слов для быстрой классификации.

```python
INTENT_ROOTS = {
    "agreement": ["согласен", "да", "хорошо", "ок", "давай", "интерес"],
    "rejection": ["нет", "не надо", "отказ", "не хочу"],
    "price_question": ["цен", "стоим", "стоит", "тариф", "прайс"],
    "question_features": ["функци", "возможност", "умеет", "может"],
    "question_integrations": ["интеграц", "подключ", "совмест"],
    # ...
}
```

### INTENT_PHRASES

Фразы для лемматизации (fallback).

```python
INTENT_PHRASES = {
    "agreement": ["согласен", "меня устраивает", "подходит"],
    "rejection": ["не интересно", "не подходит", "не нужно"],
    # ...
}
```

### SALES_STATES

Конфигурация состояний SPIN.

```python
SALES_STATES = {
    "spin_situation": {
        "goal": "Узнать ситуацию клиента",
        "spin_phase": "situation",
        "required_data": ["company_size"],
        "optional_data": ["current_tools", "business_type"],
        "transitions": {
            "situation_provided": "spin_problem",
            "rejection": "soft_close"
        }
    },
    # ...
}
```

### PROMPTS

Шаблоны промптов для LLM.

```python
PROMPTS = {
    "spin_situation": """
    Ты — консультант Wipon. Задай вопрос о текущей ситуации клиента.
    История: {history}
    Собранные данные: {collected_data}
    """,
    # ...
}
```

---

## Типы данных

### SearchResult

```python
@dataclass
class SearchResult:
    section: KnowledgeSection
    score: float
    match_type: str  # "keyword" или "embedding"
```

### KnowledgeSection

```python
@dataclass
class KnowledgeSection:
    id: str
    category: str
    title: str
    content: str
    keywords: List[str]
```

---

## Примеры использования

### Базовый диалог

```python
from bot import SalesBot
from llm import OllamaLLM

llm = OllamaLLM()
bot = SalesBot(llm)

# Приветствие
result = bot.process("Привет!")
print(result["response"])

# Вопрос о цене
result = bot.process("Сколько стоит?")
print(result["response"])

# Информация о компании
result = bot.process("Нас 10 человек, работаем в рознице")
print(result["response"])

# Сброс
bot.reset()
```

### Отдельное использование классификатора

```python
from classifier import HybridClassifier

classifier = HybridClassifier()

# Классификация без контекста
result = classifier.classify("не интересно")
print(f"Intent: {result['intent']}")  # → rejection

# Классификация с контекстом
result = classifier.classify(
    "10 человек",
    context={"spin_phase": "situation"}
)
print(f"Intent: {result['intent']}")  # → situation_provided
print(f"Data: {result['extracted_data']}")  # → {"company_size": 10}
```

### Поиск по базе знаний

```python
from knowledge import KnowledgeRetriever

retriever = KnowledgeRetriever()

# Поиск секций
results = retriever.search("интеграция с 1С")
for r in results:
    print(f"{r.section.title}: {r.score:.2f}")

# Получение контекста для LLM
context = retriever.get_context("какие есть тарифы?")
print(context)
```
