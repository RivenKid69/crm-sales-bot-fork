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
| `last_action` | `str` | Последнее действие (для контекста) |
| `last_intent` | `str` | Последний интент пользователя |

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
| `last_action` | `str` | Последнее действие бота |
| `last_intent` | `str` | Последний интент пользователя |

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
| `pain_category` | `str` | Категория боли (`losing_clients`, `no_control`, `manual_work`) |
| `pain_impact` | `str` | Количественные потери |
| `financial_impact` | `str` | Финансовые потери |
| `desired_outcome` | `str` | Желаемый результат |
| `value_acknowledged` | `bool` | Признание ценности |
| `contact_info` | `Dict` | Контакт (phone/email) |
| `high_interest` | `bool` | Высокий интерес |
| `option_index` | `int` | Индекс выбранного варианта (0-3) |

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
    "prev_state": "greeting",            # Предыдущее состояние
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

##### `update_data(data: Dict)`

Обновляет собранные данные.

```python
sm.update_data({"company_size": 15, "pain_point": "потеря клиентов"})
```

#### Атрибуты

| Атрибут | Тип | Описание |
|---------|-----|----------|
| `state` | `str` | Текущее состояние |
| `collected_data` | `Dict` | Собранные данные |
| `spin_phase` | `str` | Текущая SPIN-фаза |

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
| `deflect_and_continue` | Уход от цены к ситуации |
| `continue_current_goal` | Продолжение текущей цели |

#### Атрибуты

| Атрибут | Тип | Описание |
|---------|-----|----------|
| `max_retries` | `int` | Количество retry при иностранном тексте |
| `history_length` | `int` | Количество сообщений в контексте |
| `retriever_top_k` | `int` | Количество фактов из базы знаний |
| `allowed_english` | `Set[str]` | Разрешённые английские слова |

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

# → "Тарифы Wipon:\n| Тариф | Торговых точек |..."
```

##### `search(query: str, category: str = None, categories: List[str] = None, top_k: int = 3) -> List[SearchResult]`

Поиск с детальными результатами.

```python
results = retriever.search("тарифы Wipon", top_k=3)

# Возвращает:
[
    SearchResult(
        section=KnowledgeSection(topic="tariffs", ...),
        score=0.95,
        stage=MatchStage.EXACT,
        matched_keywords=["тариф"]
    ),
    ...
]
```

##### `search_with_stats(query: str, top_k: int = 3) -> Tuple[List[SearchResult], dict]`

Поиск со статистикой (для отладки и мониторинга).

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

##### `get_company_info() -> str`

Получить базовую информацию о компании.

```python
info = retriever.get_company_info()
# → "Wipon: Казахстанская IT-компания, разработчик решений..."
```

#### Функции модуля

##### `get_retriever(use_embeddings: bool = True) -> CascadeRetriever`

Получить singleton-экземпляр retriever'а.

```python
from knowledge import get_retriever

retriever = get_retriever(use_embeddings=True)
```

##### `reset_retriever() -> None`

Сбросить singleton для создания нового экземпляра.

```python
from knowledge.retriever import reset_retriever

reset_retriever()
```

---

### CategoryRouter

LLM-классификация категорий для улучшения поиска.

```python
from knowledge.category_router import CategoryRouter

router = CategoryRouter()
```

#### Методы

##### `classify(query: str, context: Dict = None) -> List[str]`

Классифицирует запрос и возвращает релевантные категории.

```python
categories = router.classify("как подключить 1С?")
# → ["integrations", "features", "support"]

# С контекстом
categories = router.classify(
    "сколько стоит?",
    context={"spin_phase": "situation"}
)
```

---

### Reranker

Cross-encoder для переоценки результатов поиска.

```python
from knowledge.reranker import Reranker

reranker = Reranker()
```

#### Методы

##### `rerank(query: str, candidates: List[SearchResult]) -> List[SearchResult]`

Переранжирует кандидатов с использованием cross-encoder.

```python
candidates = retriever.search("интеграция", top_k=10)
reranked = reranker.rerank("как подключить интеграцию с 1С?", candidates)

for r in reranked[:3]:
    print(f"{r.section.topic}: {r.score:.2f}")
```

---

### SearchResult

Результат поиска.

```python
from knowledge import SearchResult, MatchStage

@dataclass
class SearchResult:
    section: KnowledgeSection     # Найденная секция
    score: float                  # Оценка релевантности
    stage: MatchStage             # EXACT, LEMMA, SEMANTIC, NONE
    matched_keywords: List[str]   # Совпавшие keywords (для exact)
    matched_lemmas: Set[str]      # Совпавшие леммы (для lemma)
```

---

### KnowledgeSection

Один раздел знаний.

```python
from knowledge import KnowledgeSection

@dataclass
class KnowledgeSection:
    category: str           # "pricing", "features", "integrations", etc.
    topic: str              # Уникальный идентификатор темы
    keywords: List[str]     # Ключевые слова для поиска
    facts: str              # Текст с фактами
    priority: int = 5       # 1-10, выше = важнее
    embedding: List[float]  # Эмбеддинг (заполняется автоматически)
    lemmatized_keywords: Set[str]  # Леммы keywords (заполняется автоматически)
```

---

### KnowledgeBase

База знаний целиком.

```python
from knowledge import KnowledgeBase, WIPON_KNOWLEDGE

# Глобальный экземпляр (ленивая загрузка)
kb = WIPON_KNOWLEDGE

# Или загрузить явно
from knowledge import load_knowledge_base
kb = load_knowledge_base()
```

#### Методы

##### `get_by_category(category: str) -> List[KnowledgeSection]`

Получить все разделы категории.

```python
pricing_sections = kb.get_by_category("pricing")
```

##### `get_by_topic(topic: str) -> Optional[KnowledgeSection]`

Получить раздел по теме.

```python
tariffs = kb.get_by_topic("tariffs")
```

#### Атрибуты

| Атрибут | Тип | Описание |
|---------|-----|----------|
| `company_name` | `str` | Название компании ("Wipon") |
| `company_description` | `str` | Описание компании |
| `sections` | `List[KnowledgeSection]` | Все секции (1722 шт) |

---

### OllamaLLM

Интеграция с Ollama.

```python
from llm import OllamaLLM

llm = OllamaLLM()
# или с параметрами:
llm = OllamaLLM(model="qwen3:8b-fast", base_url="http://localhost:11434")
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

## Модули Phase 0-3

### FeatureFlags

Управление feature flags.

```python
from feature_flags import is_enabled, get_all_flags, FeatureFlags

# Проверка флага
if is_enabled("tone_analysis"):
    # использовать функционал

# Все флаги
flags = get_all_flags()

# Декоратор
@FeatureFlags.require("lead_scoring")
def calculate_score(data):
    pass
```

---

### Logger

Структурированное логирование.

```python
from logger import get_logger, LogContext

logger = get_logger(__name__)

# Обычное логирование
logger.info("Сообщение", user_id="123")

# Контекстное
with LogContext(conversation_id="conv_123"):
    logger.info("Внутри контекста")
```

---

### MetricsTracker

Трекинг метрик диалогов.

```python
from metrics import MetricsTracker

tracker = MetricsTracker()

tracker.start_conversation("conv_123")
tracker.track_intent("price_question")
tracker.track_state_transition("greeting", "spin_situation")
tracker.end_conversation("conv_123", outcome="success")

stats = tracker.get_stats()
```

---

### FallbackHandler

4-уровневый fallback при ошибках.

```python
from fallback_handler import FallbackHandler

handler = FallbackHandler()

response = handler.get_fallback(
    action="answer_question",
    context={"user_message": "сколько стоит?"},
    error=Exception("LLM timeout")
)
```

---

### ConversationGuard

Защита от зацикливания.

```python
from conversation_guard import ConversationGuard

guard = ConversationGuard(max_turns=50, max_same_state=5)

if guard.should_stop(history):
    return "Давайте начнём сначала."

guard.update(state="spin_situation", intent="situation_provided")

if guard.detect_loop():
    guard.break_loop()
```

---

### ToneAnalyzer

Анализ тона клиента.

```python
from tone_analyzer import ToneAnalyzer

analyzer = ToneAnalyzer()

result = analyzer.analyze("Это слишком дорого!")
# {
#     "sentiment": "negative",
#     "frustration": 0.7,
#     "urgency": 0.3,
#     "interest": 0.2
# }
```

---

### ResponseVariations

Вариативность ответов.

```python
from response_variations import ResponseVariations

variations = ResponseVariations()

greeting = variations.get("greeting")
greeting = variations.get("greeting", history=["Здравствуйте!"])
```

---

### LeadScorer

Скоринг лидов.

```python
from lead_scoring import LeadScorer, LeadCategory

scorer = LeadScorer()

score = scorer.calculate(
    collected_data={"company_size": 10, "pain_point": "теряем клиентов"},
    conversation_history=history,
    intents=["situation_provided", "problem_revealed"]
)
# {
#     "score": 75,
#     "category": LeadCategory.WARM,
#     "factors": {...}
# }
```

---

### ObjectionHandler

Обработка возражений.

```python
from objection_handler import ObjectionHandler

handler = ObjectionHandler()

objection = handler.classify("Это слишком дорого")
strategy = handler.get_strategy(objection, context)
response = handler.generate_response(objection, strategy, llm)
```

---

### CTAGenerator

Генерация Call-to-Action.

```python
from cta_generator import CTAGenerator

generator = CTAGenerator()

cta = generator.generate(
    state="presentation",
    collected_data=data,
    lead_score=75
)
# {
#     "primary": "Давайте запишу вас на демо?",
#     "secondary": "Или могу отправить презентацию"
# }
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

```python
from settings import get_settings

s = get_settings()
```

##### `reload_settings() -> DotDict`

Перезагрузить настройки из файла.

```python
from settings import reload_settings

s = reload_settings()
```

##### `validate_settings(settings: DotDict) -> List[str]`

Валидация настроек. Возвращает список ошибок.

```python
from settings import validate_settings, get_settings

errors = validate_settings(get_settings())
if errors:
    print("Ошибки:", errors)
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
            "data_complete": "spin_problem",
            "rejection": "soft_close"
        },
        "rules": {
            "price_question": "deflect_and_continue"
        }
    },
    # ...
}
```

### PROMPT_TEMPLATES

Шаблоны промптов для LLM.

```python
PROMPT_TEMPLATES = {
    "spin_situation": """
    Ты — консультант Wipon. Задай вопрос о текущей ситуации клиента.
    История: {history}
    Собранные данные: {collected_data}
    """,
    # ...
}
```

### QUESTION_INTENTS

Интенты-вопросы (всегда отвечаем).

```python
QUESTION_INTENTS = [
    "price_question",
    "question_features",
    "question_integrations",
]
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
from knowledge import get_retriever

retriever = get_retriever()

# Получить факты для LLM
facts = retriever.retrieve("интеграция с 1С", intent="question_integrations")
print(facts)

# Детальный поиск
results = retriever.search("какие есть тарифы?", category="pricing")
for r in results:
    print(f"{r.section.topic}: {r.score:.2f} ({r.stage.value})")

# Поиск со статистикой
results, stats = retriever.search_with_stats("цены на Wipon")
print(f"Использован этап: {stats['stage_used']}")
print(f"Время: {stats['total_time_ms']:.2f}ms")
```

### Работа с настройками

```python
from settings import settings, reload_settings

# Чтение
print(f"Модель: {settings.llm.model}")
print(f"Порог lemma: {settings.retriever.thresholds.lemma}")

# После изменения settings.yaml
reload_settings()
```

### Использование Feature Flags

```python
from feature_flags import is_enabled

if is_enabled("tone_analysis"):
    from tone_analyzer import ToneAnalyzer
    analyzer = ToneAnalyzer()
    tone = analyzer.analyze(message)

    if tone["frustration"] > 0.5:
        # Адаптировать ответ
```

### Прямое использование базы знаний

```python
from knowledge import WIPON_KNOWLEDGE

# Информация о компании
print(WIPON_KNOWLEDGE.company_name)
print(WIPON_KNOWLEDGE.company_description)

# Все секции
print(f"Всего секций: {len(WIPON_KNOWLEDGE.sections)}")  # 1722

# По категории
pricing = WIPON_KNOWLEDGE.get_by_category("pricing")
print(f"Секций о тарифах: {len(pricing)}")  # 184

# По теме
tariffs = WIPON_KNOWLEDGE.get_by_topic("tariffs")
print(tariffs.facts)
```
