# API Reference

## Основные классы

### SalesBot

Главный класс бота, оркестрирующий все компоненты.

```python
from bot import SalesBot
from llm import OllamaClient

llm = OllamaClient()
bot = SalesBot(llm)

# Или с параметрами
bot = SalesBot(
    llm=llm,
    conversation_id="abc123",    # Опционально: ID диалога
    enable_tracing=True          # Опционально: трассировка правил
)
```

#### Методы

##### `process(user_message: str) -> Dict`

Обрабатывает сообщение пользователя и возвращает ответ.

```python
result = bot.process("Привет, сколько стоит ваша CRM?")

# Возвращает:
{
    "response": "Здравствуйте! Тарифы начинаются от 990 тг/мес...",
    "intent": "price_question",
    "action": "answer_question",
    "state": "greeting",
    "is_final": False,
    "spin_phase": None,
    "fallback_used": False,
    "fallback_tier": None,
    "tone": "neutral",
    "frustration_level": 0,
    "lead_score": 50,
    "objection_detected": False,
    "options": None
}
```

##### `reset()`

Сбрасывает состояние для нового диалога.

```python
bot.reset()
```

##### `get_metrics_summary() -> Dict`

Получить сводку метрик текущего диалога.

```python
summary = bot.get_metrics_summary()
# {
#     "conversation_id": "abc123",
#     "turns": 5,
#     "duration_sec": 120,
#     "states_visited": ["greeting", "spin_situation", "spin_problem"],
#     "fallbacks_used": 0,
#     "objections_count": 1
# }
```

##### `get_lead_score() -> Dict`

Получить текущий lead score.

```python
score = bot.get_lead_score()
# {
#     "score": 65,
#     "temperature": "warm",
#     "signals": ["company_size_provided", "problem_revealed"]
# }
```

##### `get_guard_stats() -> Dict`

Получить статистику ConversationGuard.

```python
stats = bot.get_guard_stats()
# {
#     "same_state_count": 2,
#     "frustration_level": 1,
#     "interventions": []
# }
```

##### `get_disambiguation_metrics() -> Dict`

Получить метрики disambiguation.

```python
metrics = bot.get_disambiguation_metrics()
# {
#     "total_disambiguations": 3,
#     "successful_resolutions": 2,
#     "average_attempts": 1.5
# }
```

#### Атрибуты

| Атрибут | Тип | Описание |
|---------|-----|----------|
| `classifier` | `UnifiedClassifier` | Классификатор интентов |
| `state_machine` | `StateMachine` | Управление состояниями |
| `generator` | `ResponseGenerator` | Генерация ответов |
| `history` | `List[Dict]` | История диалога |
| `last_action` | `str` | Последнее действие |
| `last_intent` | `str` | Последний интент |
| `conversation_id` | `str` | ID диалога |
| `metrics` | `ConversationMetrics` | Метрики диалога |
| `guard` | `ConversationGuard` | Защита от зацикливания |
| `lead_scorer` | `LeadScorer` | Скоринг лидов |
| `context_window` | `ContextWindow` | Расширенный контекст |
| `dialogue_policy` | `DialoguePolicy` | Policy overlays |

---

### UnifiedClassifier

Адаптер для переключения между LLM и Hybrid классификаторами.

```python
from classifier import UnifiedClassifier

classifier = UnifiedClassifier()
```

#### Методы

##### `classify(message: str, context: Dict = None) -> Dict`

Классифицирует сообщение используя LLM или Hybrid в зависимости от флага `llm_classifier`.

```python
result = classifier.classify(
    message="нас 10 человек, работаем в рознице",
    context={"spin_phase": "situation"}
)

# Возвращает:
{
    "intent": "situation_provided",
    "confidence": 0.95,
    "extracted_data": {
        "company_size": 10,
        "business_type": "розничная торговля"
    },
    "method": "llm",  # или "hybrid" / "llm_fallback"
    "reasoning": "..."  # только для LLM
}
```

##### `get_stats() -> Dict`

Получить статистику классификатора.

```python
stats = classifier.get_stats()
# {
#     "active_classifier": "llm",
#     "llm_stats": {
#         "llm_calls": 100,
#         "llm_successes": 98,
#         "fallback_calls": 2,
#         "llm_success_rate": 98.0,
#         "ollama_stats": {...}
#     }
# }
```

---

### LLMClassifier

Классификатор на базе LLM с structured output через Ollama native format.

```python
from classifier.llm import LLMClassifier

classifier = LLMClassifier()
```

#### Методы

##### `classify(message: str, context: Dict = None) -> Dict`

Классифицирует сообщение через LLM.

```python
result = classifier.classify(
    message="нас 10 человек, работаем в рознице",
    context={"spin_phase": "situation"}
)

# Возвращает:
{
    "intent": "situation_provided",
    "confidence": 0.95,
    "extracted_data": {
        "company_size": 10,
        "business_type": "розничная торговля",
        "pain_category": None
    },
    "method": "llm",
    "reasoning": "Клиент указал размер команды и сферу деятельности"
}
```

**Параметры context:**

| Ключ | Тип | Описание |
|------|-----|----------|
| `state` | `str` | Текущее состояние FSM |
| `spin_phase` | `str` | SPIN-фаза: `situation`, `problem`, `implication`, `need_payoff` |
| `last_action` | `str` | Последнее действие бота |
| `last_intent` | `str` | Предыдущий интент пользователя |
| `intent_history` | `List[str]` | История интентов |
| `action_history` | `List[str]` | История действий |

---

### HybridClassifier

Regex-based классификатор (используется как fallback).

```python
from classifier import HybridClassifier

classifier = HybridClassifier()
```

#### Методы

##### `classify(message: str, context: Dict = None) -> Dict`

Классифицирует сообщение через regex и pymorphy.

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
        "lemma_intent": None
    }
}
```

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
# -> "сколько стоит цена?"

text = normalizer.normalize("сколькостоит")
# -> "сколько стоит"
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
    "pain_impact": "10 клиентов в месяц",
    "pain_category": "losing_clients"
}
```

**Извлекаемые поля:**

| Поле | Тип | Описание |
|------|-----|----------|
| `company_size` | `int` | Размер команды |
| `current_tools` | `str` | Текущие инструменты |
| `business_type` | `str` | Тип бизнеса |
| `pain_point` | `str` | Боль клиента |
| `pain_category` | `str` | Категория боли (`losing_clients`, `no_control`, `manual_work`) |
| `pain_impact` | `str` | Количественные потери |
| `financial_impact` | `str` | Финансовые потери |
| `desired_outcome` | `str` | Желаемый результат |
| `value_acknowledged` | `bool` | Признание ценности |
| `contact_info` | `Dict` | Контакт (phone/email) |
| `high_interest` | `bool` | Высокий интерес |

---

### OllamaClient

Клиент для Ollama с circuit breaker, retry и structured output.

```python
from llm import OllamaClient

llm = OllamaClient()
# или с параметрами:
llm = OllamaClient(
    model="qwen3:14b",
    base_url="http://localhost:11434",
    timeout=120,
    enable_circuit_breaker=True,
    enable_retry=True
)
```

#### Методы

##### `generate(prompt: str, state: str = None, allow_fallback: bool = True) -> str`

Free-form генерация ответа.

```python
response = llm.generate(
    prompt="Ответь на вопрос клиента: сколько стоит CRM?",
    state="greeting"
)
```

##### `generate_structured(prompt: str, schema: Type[BaseModel], allow_fallback: bool = True) -> Optional[T]`

Генерация с гарантированным JSON через Ollama native format parameter.

```python
from pydantic import BaseModel

class Result(BaseModel):
    intent: str
    confidence: float

result = llm.generate_structured(prompt, Result)
# -> Result(intent="price_question", confidence=0.95)
```

##### `health_check() -> bool`

Проверка доступности Ollama.

```python
is_healthy = llm.health_check()
```

##### `get_stats_dict() -> Dict`

Статистика запросов.

```python
stats = llm.get_stats_dict()
# {
#     "total_requests": 100,
#     "successful_requests": 98,
#     "failed_requests": 2,
#     "fallback_used": 2,
#     "total_retries": 5,
#     "circuit_breaker_trips": 0,
#     "success_rate": 98.0,
#     "average_response_time_ms": 150.5,
#     "circuit_breaker_open": False
# }
```

##### `reset()`

Сбросить статистику для нового диалога.

##### `reset_circuit_breaker()`

Сбросить circuit breaker.

#### Атрибуты

| Атрибут | Тип | Описание |
|---------|-----|----------|
| `model` | `str` | Название модели |
| `base_url` | `str` | URL Ollama API |
| `timeout` | `int` | Таймаут запроса |
| `stats` | `LLMStats` | Статистика запросов |
| `is_circuit_open` | `bool` | Открыт ли circuit breaker |

**Resilience Features:**
- **Circuit Breaker**: 5 ошибок -> 60 сек cooldown
- **Retry**: exponential backoff (1s -> 2s -> 4s)
- **Fallback**: предопределённые ответы по состояниям

---

### StateMachine

Управление состояниями диалога (SPIN flow).

```python
from state_machine import StateMachine

sm = StateMachine()
# или с трассировкой:
sm = StateMachine(enable_tracing=True)
```

#### Методы

##### `process(intent: str, extracted_data: Dict, context_envelope: ContextEnvelope = None) -> Dict`

Обрабатывает интент и определяет следующее действие.

```python
result = sm.process(
    intent="situation_provided",
    extracted_data={"company_size": 10}
)

# Возвращает:
{
    "action": "spin_situation",
    "prev_state": "greeting",
    "next_state": "spin_situation",
    "is_final": False,
    "collected_data": {"company_size": 10},
    "missing_data": ["current_tools"],
    "goal": "Узнать ситуацию клиента",
    "spin_phase": "situation",
    "optional_data": ["business_type"]
}
```

##### `reset()`

Сбрасывает состояние.

##### `update_data(data: Dict)`

Обновляет собранные данные.

##### `enter_disambiguation(options: List[Dict], extracted_data: Dict)`

Войти в режим disambiguation.

##### `exit_disambiguation()`

Выйти из режима disambiguation.

##### `resolve_disambiguation(resolved_intent: str) -> Tuple[str, str]`

Разрешить disambiguation и вернуть (state, intent).

#### Атрибуты

| Атрибут | Тип | Описание |
|---------|-----|----------|
| `state` | `str` | Текущее состояние |
| `collected_data` | `Dict` | Собранные данные |
| `spin_phase` | `str` | Текущая SPIN-фаза |
| `in_disambiguation` | `bool` | В режиме disambiguation |
| `disambiguation_context` | `Dict` | Контекст disambiguation |

---

### ResponseGenerator

Генерация ответов через Ollama.

```python
from generator import ResponseGenerator
from llm import OllamaClient

llm = OllamaClient()
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
# -> "Понял, команда из 10 человек. Какая главная сложность с учётом сейчас?"
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
| `transition_to_spin_problem` | Переход S->P |
| `presentation` | Презентация решения |
| `handle_objection` | Работа с возражением |
| `close` | Запрос контакта |
| `soft_close` | Вежливое завершение |

---

### CascadeRetriever

3-этапный поиск по базе знаний.

```python
from knowledge import get_retriever, CascadeRetriever

# Singleton (рекомендуется)
retriever = get_retriever()

# Или создать напрямую
retriever = CascadeRetriever(use_embeddings=True)
```

#### Методы

##### `retrieve(message: str, intent: str = None, state: str = None, top_k: int = None) -> str`

Получить релевантные факты для LLM контекста.

```python
facts = retriever.retrieve(
    message="сколько стоит Wipon",
    intent="price_question",
    top_k=2
)
# -> "Тарифы Wipon:\n| Тариф | Торговых точек |..."
```

##### `search(query: str, category: str = None, top_k: int = 3) -> List[SearchResult]`

Поиск с детальными результатами.

```python
results = retriever.search("тарифы Wipon", top_k=3)

for r in results:
    print(f"{r.section.topic}: {r.score:.2f} ({r.stage.value})")
```

##### `search_with_stats(query: str, top_k: int = 3) -> Tuple[List[SearchResult], dict]`

Поиск со статистикой.

```python
results, stats = retriever.search_with_stats("какие есть интеграции?")

# stats:
{
    "stage_used": "exact",
    "exact_time_ms": 1.2,
    "lemma_time_ms": 0,
    "semantic_time_ms": 0,
    "total_time_ms": 1.5
}
```

---

### CategoryRouter

LLM-классификация категорий для улучшения поиска.

```python
from knowledge.category_router import CategoryRouter
from llm import OllamaClient

router = CategoryRouter(OllamaClient(), top_k=3)
```

#### Методы

##### `route(query: str) -> List[str]`

Классифицирует запрос и возвращает релевантные категории.

```python
categories = router.route("как подключить 1С?")
# -> ["integrations", "features", "support"]
```

Поддерживает:
- Structured Output (Ollama native format) — 100% валидный JSON
- Legacy режим (generate + parsing) — обратная совместимость

---

### FeatureFlags

Управление feature flags.

```python
from feature_flags import flags

# Проверка флага (property)
if flags.llm_classifier:
    # использовать LLM

# Проверка флага (метод)
if flags.is_enabled("tone_analysis"):
    # ...

# Все флаги
all_flags = flags.get_all_flags()

# Включённые флаги
enabled = flags.get_enabled_flags()

# Override флага в runtime
flags.set_override("tone_analysis", True)
flags.clear_override("tone_analysis")

# Управление группами
flags.enable_group("phase_3")
flags.disable_group("risky")
```

---

### Settings

Настройки из settings.yaml.

```python
from settings import settings

# Доступ через точку
model = settings.llm.model
threshold = settings.retriever.thresholds.lemma

# Получение по пути
value = settings.get_nested("retriever.thresholds.semantic")
```

#### Функции модуля

##### `get_settings() -> DotDict`

Получить глобальные настройки (singleton).

##### `reload_settings() -> DotDict`

Перезагрузить настройки из файла.

##### `validate_settings(settings: DotDict) -> List[str]`

Валидация настроек. Возвращает список ошибок.

---

## Pydantic Schemas

### ClassificationResult

Результат классификации интента (LLMClassifier).

```python
from classifier.llm import ClassificationResult, ExtractedData

class ExtractedData(BaseModel):
    company_size: Optional[int]
    business_type: Optional[str]
    current_tools: Optional[str]
    pain_point: Optional[str]
    pain_category: Optional[Literal["losing_clients", "no_control", "manual_work"]]
    pain_impact: Optional[str]
    financial_impact: Optional[str]
    contact_info: Optional[str]
    desired_outcome: Optional[str]
    value_acknowledged: Optional[bool]

class ClassificationResult(BaseModel):
    intent: IntentType  # 150+ интентов в 26 категориях
    confidence: float  # 0.0 - 1.0
    reasoning: str
    extracted_data: ExtractedData
```

### CategoryResult

Результат роутинга по категориям.

```python
from classifier.llm import CategoryResult

class CategoryResult(BaseModel):
    categories: List[CategoryType]  # 17 категорий
```

---

## Примеры использования

### Базовый диалог

```python
from bot import SalesBot
from llm import OllamaClient

llm = OllamaClient()
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
from classifier import UnifiedClassifier

classifier = UnifiedClassifier()

# Классификация с LLM
result = classifier.classify("не интересно")
print(f"Intent: {result['intent']}")  # -> rejection
print(f"Method: {result['method']}")  # -> llm

# С контекстом
result = classifier.classify(
    "10 человек",
    context={"spin_phase": "situation"}
)
print(f"Data: {result['extracted_data']}")  # -> {"company_size": 10}
```

### Поиск по базе знаний

```python
from knowledge import get_retriever

retriever = get_retriever()

# Получить факты для LLM
facts = retriever.retrieve("интеграция с 1С", intent="question_integrations")

# Детальный поиск
results = retriever.search("какие есть тарифы?", category="pricing")

# Со статистикой
results, stats = retriever.search_with_stats("цены на Wipon")
print(f"Использован этап: {stats['stage_used']}")
```

### Работа с Ollama

```python
from llm import OllamaClient

llm = OllamaClient()

# Health check
if llm.health_check():
    print("Ollama доступен")

# Free-form генерация
response = llm.generate("Привет!", state="greeting")

# Structured output
from pydantic import BaseModel

class Intent(BaseModel):
    name: str
    confidence: float

result = llm.generate_structured("Классифицируй: 'сколько стоит?'", Intent)
print(f"Intent: {result.name}, confidence: {result.confidence}")

# Статистика
print(llm.get_stats_dict())
```

### Использование Feature Flags

```python
from feature_flags import flags

if flags.llm_classifier:
    from classifier import UnifiedClassifier
    classifier = UnifiedClassifier()  # использует LLM
else:
    from classifier import HybridClassifier
    classifier = HybridClassifier()  # использует regex

if flags.is_enabled("tone_analysis"):
    from tone_analyzer import ToneAnalyzer
    analyzer = ToneAnalyzer()
    tone = analyzer.analyze(message)
```

### Интерактивный режим

```python
from bot import SalesBot, run_interactive
from llm import OllamaClient
from feature_flags import flags

# Включить нужные фичи
flags.enable_group("phase_3")

llm = OllamaClient()
bot = SalesBot(llm)

# Запуск интерактивного режима
run_interactive(bot)

# Команды в интерактивном режиме:
# /reset - сбросить диалог
# /status - показать состояние
# /metrics - показать метрики
# /lead - показать lead score
# /flags - показать включённые флаги
# /quit - выйти
```
