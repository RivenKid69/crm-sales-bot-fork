# API Reference

## Основные классы

### SalesBot

Главный класс бота, оркестрирующий все компоненты.

```python
from src.bot import SalesBot
from src.llm import OllamaClient

llm = OllamaClient()
bot = SalesBot(llm)

# Или с параметрами
bot = SalesBot(
    llm=llm,
    conversation_id="abc123",    # Опционально: ID диалога
    enable_tracing=True,         # Опционально: трассировка правил
    flow_name="spin_selling",    # Опционально: flow для текущей сессии
    persona="aggressive",        # Опционально: персона (симуляции)
    client_id="client-42"        # Опционально: внешний ID клиента
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
    "visited_states": ["greeting"],
    "initial_state": "greeting",
    "fallback_used": False,
    "fallback_tier": None,
    "tone": "neutral",
    "frustration_level": 0,
    "lead_score": None,
    "objection_detected": False,
    "options": None,
    "cta_added": False,
    "cta_text": None,
    "decision_trace": None
}
```

##### `reset()`

Сбрасывает состояние для нового диалога.

```python
bot.reset()
```

##### `to_snapshot(compact_history: bool = False, history_tail_size: int = 4) -> Dict`

Сериализует полное состояние бота в snapshot.
При `compact_history=True` выполняется LLM-компакция истории (без последних 4 сообщений).

```python
snapshot = bot.to_snapshot(compact_history=True, history_tail_size=4)
```

##### `from_snapshot(snapshot: Dict, llm=None, history_tail: Optional[List[Dict]] = None) -> SalesBot`

Восстанавливает бота из snapshot.
`history_tail` обычно загружается из внешней БД истории.

```python
restored = SalesBot.from_snapshot(snapshot, llm=llm, history_tail=history_tail)
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

Примечание: `lead_score` и `decision_trace` будут `None`, если соответствующие фичи отключены.

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
#     "turn_count": 5,
#     "elapsed_seconds": 120.5,
#     "phase_attempts": {"situation": 2, "problem": 1},
#     "unique_states": 3,
#     "last_state": "spin_problem",
#     "frustration_level": 1,
#     "collected_data_count": 2
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
| `client_id` | `str` | Внешний ID клиента (CRM/мессенджер) |
| `metrics` | `ConversationMetrics` | Метрики диалога |
| `guard` | `ConversationGuard` | Защита от зацикливания |
| `lead_scorer` | `LeadScorer` | Скоринг лидов |
| `context_window` | `ContextWindow` | Расширенный контекст |
| `dialogue_policy` | `DialoguePolicy` | Policy overlays |

---

### SessionManager

Кеш активных сессий и восстановление из снапшотов.
Снапшот загружается только при отсутствии сессии в памяти.

```python
from src.session_manager import SessionManager

manager = SessionManager(
    ttl_seconds=3600,
    load_snapshot=load_snapshot,         # функция загрузки из внешней БД
    save_snapshot=save_snapshot,         # функция сохранения в внешнюю БД
    load_history_tail=load_history_tail, # последние 4 сообщения из истории
)

bot = manager.get_or_create(
    session_id="sess-1",
    llm=llm,
    client_id="client-42",
    flow_name="bant",
    config_name="tenant_alpha",
)
```

#### Основные методы

- `get_or_create(session_id, llm, client_id=None, flow_name=None, config_name=None) -> SalesBot`
- `save(session_id) -> None` — сохранить снапшот в локальный буфер
- `cleanup_expired() -> int` — TTL cleanup, возвращает количество удалённых сессий

**Примечание:** если для активной сессии приходит новый `flow_name`/`config_name`,
SessionManager выполняет “горячий” switch, пересобирая бота из snapshot.

---

### LocalSnapshotBuffer

Локальное персистентное хранилище снапшотов (SQLite, multi-process).

```python
from src.snapshot_buffer import LocalSnapshotBuffer

buffer = LocalSnapshotBuffer()
buffer.enqueue("sess-1", snapshot)
snapshot = buffer.get("sess-1")
```

---

### SessionLockManager

Межпроцессные lock'и по `session_id`.

```python
from src.session_lock import SessionLockManager

lock = SessionLockManager()
with lock.lock("sess-1"):
    # безопасная обработка сессии
    pass
```

---

### HistoryCompactor

LLM-компакция истории диалога при создании снапшота.

```python
from src.history_compactor import HistoryCompactor

compact, meta = HistoryCompactor.compact(
    history_full=history,
    history_tail_size=4,
    previous_compact=None,
    llm=llm,
)
```

---

### UnifiedClassifier

Адаптер для переключения между LLM и Hybrid классификаторами.

```python
from src.classifier import UnifiedClassifier

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
from src.classifier.llm import LLMClassifier

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
from src.classifier import HybridClassifier

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
from src.classifier import TextNormalizer

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
from src.classifier import DataExtractor

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
from src.llm import OllamaClient

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

##### `transition_to(next_state: str, action: Optional[str] = None, phase: Optional[str] = None, source: str = "unknown", validate: bool = True) -> bool`

Атомарно переходит в новое состояние с гарантированной консистентностью всех полей.

Это единственная точка контроля для изменения состояния, обеспечивающая синхронизацию:
- `state` — текущее состояние
- `current_phase` — фаза для этого состояния
- `last_action` — действие, вызвавшее переход

```python
# Вместо:
#   sm.state = "spin_problem"
#   sm.current_phase = "problem"  # легко забыть!

# Используйте:
success = sm.transition_to(
    next_state="spin_problem",
    action="ask_problem_questions",
    phase="problem",  # опционально (вычисляется из конфига)
    source="orchestrator"  # для отладки
)

if success:
    print(f"Переход выполнен: {sm.state}")
else:
    print("Состояние не найдено в конфиге")
```

**Параметры:**
- `next_state` (str): Целевое состояние
- `action` (Optional[str]): Действие, вызвавшее переход
- `phase` (Optional[str]): Фаза для нового состояния (вычисляется автоматически если не указана)
- `source` (str): Идентификатор источника для отладки
- `validate` (bool): Проверять ли наличие состояния в конфиге

**Возвращает:**
- `True` если переход выполнен успешно
- `False` если состояние не найдено (и validate=True)

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

### RefinementPipeline

Многоуровневый конвейер для уточнения результатов классификации через составные слои обработки.

```python
from classifier.refinement_pipeline import (
    get_refinement_pipeline,
    RefinementContext,
    register_refinement_layer
)

# Получить singleton экземпляр
pipeline = get_refinement_pipeline()
```

#### Методы RefinementPipeline

##### `refine(message: str, result: Dict, context: Optional[Dict] = None) -> Dict`

Запустить классификацию через все включённые слои обработки.

```python
# Результат из LLMClassifier
classification_result = {
    "intent": "price_question",
    "confidence": 0.85,
    "extracted_data": {"company_size": 10}
}

# Контекст диалога
context = {
    "state": "spin_situation",
    "spin_phase": "situation",
    "last_action": "ask_situation",
    "turn_number": 3,
    "collected_data": {"company_size": 10}
}

# Пройти через конвейер
refined = pipeline.refine(
    message="нас 10 человек в рознице",
    result=classification_result,
    context=context
)

# Возвращает исходный результат + поля от слоёв:
{
    "intent": "situation_provided",  # может быть переклассифицирован
    "confidence": 0.92,
    "extracted_data": {"company_size": 10, "business_type": "розничная торговля"},
    "refined": True,  # если было уточнение
    "refinement_chain": ["data_aware", "context_aware"],  # какие слои применялись
    "pipeline_time_ms": 45.2
}
```

**Параметры:**
- `message` (str): Сообщение пользователя
- `result` (Dict): Результат классификации от основного классификатора
- `context` (Dict): Контекст диалога (опционально)

**Возвращает:**
- Dict с потенциально уточненной классификацией и метаданными

##### `get_stats() -> Dict`

Получить статистику конвейера и каждого слоя.

```python
stats = pipeline.get_stats()
# {
#     "enabled": True,
#     "layers": ["data_aware", "context_aware", "objection"],
#     "calls_total": 100,
#     "refinements_total": 25,
#     "refinement_rate": 0.25,
#     "avg_time_ms": 45.2,
#     "layer_stats": {
#         "data_aware": {
#             "calls_total": 100,
#             "refinements_total": 15,
#             "refinement_rate": 0.15,
#             "errors_total": 0,
#             ...
#         },
#         ...
#     }
# }
```

##### `get_layer(name: str) -> Optional[BaseRefinementLayer]`

Получить экземпляр конкретного слоя по имени.

```python
data_layer = pipeline.get_layer("data_aware")
if data_layer:
    stats = data_layer.get_stats()
```

#### BaseRefinementLayer (базовый класс)

Все слои должны наследовать от этого класса и реализовать два метода:

```python
from classifier.refinement_pipeline import (
    BaseRefinementLayer,
    RefinementContext,
    RefinementResult,
    RefinementDecision,
    LayerPriority,
    register_refinement_layer
)

@register_refinement_layer("my_custom_layer")
class MyCustomLayer(BaseRefinementLayer):
    LAYER_NAME = "my_custom_layer"
    LAYER_PRIORITY = LayerPriority.HIGH
    FEATURE_FLAG = "custom_layer_enabled"

    def _should_apply(self, ctx: RefinementContext) -> bool:
        """Проверить применимость слоя к данному сообщению."""
        # Применять только на фазе 'situation'
        return ctx.phase == "situation"

    def _do_refine(
        self,
        message: str,
        result: Dict[str, Any],
        ctx: RefinementContext
    ) -> RefinementResult:
        """Реализовать логику уточнения."""
        # Ваша логика...
        if should_refine:
            return self._create_refined_result(
                new_intent="refined_intent",
                new_confidence=0.95,
                original_intent=result.get("intent"),
                reason="reason_code",
                result=result,
                extracted_data={"new_field": "value"}
            )
        else:
            return self._pass_through(result, ctx)
```

#### RefinementContext (структура контекста)

Универсальный контекст передаваемый между всеми слоями:

```python
@dataclass
class RefinementContext:
    # Основной контекст
    message: str
    state: Optional[str] = None
    phase: Optional[str] = None
    last_action: Optional[str] = None
    last_intent: Optional[str] = None
    turn_number: int = 0

    # Собранные данные
    collected_data: Dict[str, Any] = field(default_factory=dict)
    expects_data_type: Optional[str] = None

    # Контекст возражений
    last_objection_turn: Optional[int] = None
    last_objection_type: Optional[str] = None

    # Классификация
    intent: str = "unclear"
    confidence: float = 0.0
    extracted_data: Dict[str, Any] = field(default_factory=dict)

    # Дополнительные метаданные
    metadata: Dict[str, Any] = field(default_factory=dict)

    def update_from_result(self, result: Dict) -> "RefinementContext":
        """Создать новый контекст с обновленной классификацией."""
        ...
```

#### RefinementLayerRegistry

Реестр для регистрации и поиска слоёв обработки:

```python
from classifier.refinement_pipeline import RefinementLayerRegistry

registry = RefinementLayerRegistry.get_registry()

# Регистрировать слой программно
registry.register("my_layer", MyLayerClass)

# Получить класс слоя
LayerClass = registry.get("my_layer")

# Получить экземпляр слоя (с кешированием)
layer = registry.get_layer_instance("my_layer")

# Получить все имена слоёв
names = registry.get_all_names()

# Проверить регистрацию
if registry.is_registered("my_layer"):
    print("Слой зарегистрирован")
```

#### Пример: Собственный слой обработки

```python
from classifier.refinement_pipeline import (
    register_refinement_layer,
    BaseRefinementLayer,
    LayerPriority,
    RefinementContext,
    RefinementResult,
    RefinementDecision
)
from typing import Dict, Any

@register_refinement_layer("company_size_validator")
class CompanySizeValidatorLayer(BaseRefinementLayer):
    """Валидирует и нормализует размер компании."""

    LAYER_NAME = "company_size_validator"
    LAYER_PRIORITY = LayerPriority.HIGH
    FEATURE_FLAG = "extraction_validation"

    def _should_apply(self, ctx: RefinementContext) -> bool:
        """Применять если извлечены данные о размере компании."""
        return "company_size" in ctx.extracted_data

    def _do_refine(
        self,
        message: str,
        result: Dict[str, Any],
        ctx: RefinementContext
    ) -> RefinementResult:
        """Валидировать company_size."""
        company_size = ctx.extracted_data.get("company_size")

        if isinstance(company_size, int) and 1 <= company_size <= 10000:
            # Валидно
            return self._pass_through(result, ctx)

        # Попытка исправить
        if isinstance(company_size, str):
            match = re.search(r'(\d+)', company_size)
            if match:
                corrected = int(match.group(1))
                if 1 <= corrected <= 10000:
                    return self._create_refined_result(
                        new_intent=result.get("intent"),
                        new_confidence=result.get("confidence", 0),
                        original_intent=result.get("intent"),
                        reason="normalized_company_size",
                        result=result,
                        extracted_data={"company_size": corrected}
                    )

        # Невалидно
        return self._create_refined_result(
            new_intent="unclear",
            new_confidence=0.5,
            original_intent=result.get("intent"),
            reason="invalid_company_size",
            result=result,
            extracted_data={k: v for k, v in ctx.extracted_data.items()
                           if k != "company_size"}
        )
```

---

### ResponseGenerator

Генерация ответов через Ollama.

```python
from generator import ResponseGenerator
from src.llm import OllamaClient

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

### ContextEnvelope

Единый контракт контекста для всех подсистем диалогового движка.

Собирает полный контекст из:
- Управления состояниями (state, phase, collected_data)
- Скользящего окна (Level 1: история интентов, обнаружение зацикливания)
- Структурированного контекста (Level 2: momentum, engagement, funnel_velocity)
- Эпизодической памяти (Level 3: история возражений, прорывы, эффективность действий)
- Анализа тона и защиты (frustration, guard_intervention)

```python
from context_envelope import (
    ContextEnvelope,
    ContextEnvelopeBuilder,
    ReasonCode,
    build_context_envelope
)

# Построить контекст через builder
envelope = ContextEnvelopeBuilder(
    state_machine=sm,
    context_window=cw,
    tone_info=tone_result,
    guard_info=guard_result,
    last_action="ask_situation",
    last_intent="situation_provided",
    current_intent="situation_provided",
    classification_result={
        "intent": "situation_provided",
        "extracted_data": {"company_size": 10}
    }
).build()

# Или через удобную функцию
envelope = build_context_envelope(
    state_machine=sm,
    context_window=cw,
    tone_info=tone_result,
    guard_info=guard_result
)
```

#### ContextEnvelope (основные атрибуты)

```python
@dataclass
class ContextEnvelope:
    # === Базовый контекст ===
    state: str                              # Текущее состояние FSM
    spin_phase: Optional[str]               # Текущая SPIN-фаза
    collected_data: Dict[str, Any]          # Собранные данные о клиенте
    missing_data: List[str]                 # Недостающие требуемые данные
    last_action: Optional[str]              # Последний action бота
    last_intent: Optional[str]              # Последний intent пользователя

    # === Level 1: Sliding Window ===
    intent_history: List[str]               # История последних интентов
    action_history: List[str]               # История последних действий
    objection_count: int                    # Количество возражений в окне
    positive_count: int                     # Положительные сигналы
    has_oscillation: bool                   # Обнаружена осцилляция
    is_stuck: bool                          # Застревание в состоянии
    repeated_question: Optional[str]        # Повторный вопрос (если есть)
    confidence_trend: str                   # Тренд confidence ("increasing", "decreasing")
    avg_confidence: float                   # Средняя confidence

    # === Level 2: Structured Context ===
    momentum: float                         # Momentum score (-1 to +1)
    momentum_direction: str                 # "positive", "negative", "neutral"
    engagement_level: str                   # "high", "medium", "low", "disengaged"
    engagement_score: float                 # 0.0 to 1.0
    engagement_trend: str                   # "improving", "stable", "declining"
    funnel_velocity: float                  # Скорость прохождения по воронке
    is_progressing: bool                    # Движется ли вперёд
    is_regressing: bool                     # Откатывается ли назад

    # === Level 3: Episodic Memory ===
    first_objection_type: Optional[str]     # Тип первого возражения
    total_objections: int                   # Общее количество возражений
    repeated_objection_types: List[str]     # Типы повторных возражений
    has_breakthrough: bool                  # Был ли прорыв
    breakthrough_action: Optional[str]      # Действие приведшее к прорыву
    turns_since_breakthrough: Optional[int] # Ходов с момента прорыва
    most_effective_action: Optional[str]    # Самое эффективное действие
    least_effective_action: Optional[str]   # Наименее эффективное действие
    client_company_size: Optional[int]      # Размер компании клиента
    client_pain_points: List[str]           # Боли клиента

    # === Tone & Guard ===
    tone: Optional[str]                     # Тон: "neutral", "positive", "negative", "rushed"
    frustration_level: int                  # 0-5 (0=спокойно, 5=очень расстроен)
    should_apologize: bool                  # Нужно ли извиняться
    should_offer_exit: bool                 # Предложить ли выход
    guard_intervention: Optional[str]       # guard.intervention или None

    # === Reason Codes ===
    reason_codes: List[str]                 # Активные коды причин
```

#### Методы ContextEnvelope

##### `for_classifier() -> Dict`

Получить контекст оптимизированный для классификатора:

```python
classifier_context = envelope.for_classifier()

# Передать классификатору
result = classifier.classify(message, context=classifier_context)
```

Включает: state, spin_phase, collected_data, intent_history, объекты Level 1-3

##### `for_generator() -> Dict`

Получить контекст для генератора ответов:

```python
generator_context = envelope.for_generator()

# Генератор использует для персонализации
response = generator.generate(
    action=action,
    context=generator_context
)
```

Включает: tone, frustration, repair_signals, episodic_memory для персонализации

##### `for_policy() -> Dict`

Получить контекст для принятия решений DialoguePolicy:

```python
policy_context = envelope.for_policy()

# Policy использует для выбора overlays
decision = policy.decide(
    action=action,
    intent=intent,
    context=policy_context
)
```

Включает: momentum, engagement, objection_signals для применения policy overlays

##### `to_dict() -> Dict`

Сериализовать в словарь для логирования/хранения.

##### `add_reason(reason: ReasonCode) -> None`

Добавить код причины:

```python
envelope.add_reason(ReasonCode.REPAIR_STUCK)
envelope.add_reason(ReasonCode.MOMENTUM_POSITIVE)
```

##### `has_reason(reason: ReasonCode) -> bool`

Проверить наличие кода причины:

```python
if envelope.has_reason(ReasonCode.OBJECTION_ESCALATE):
    print("Достигнут лимит возражений")
```

#### ReasonCode (перечисление кодов причин)

```python
class ReasonCode(Enum):
    # === Repair (Level 1) ===
    REPAIR_STUCK = "repair.stuck"
    REPAIR_OSCILLATION = "repair.oscillation"
    REPAIR_REPEATED_QUESTION = "repair.repeated_question"
    REPAIR_CONFIDENCE_LOW = "repair.confidence_low"

    # === Objection (Level 3) ===
    OBJECTION_FIRST = "objection.first"
    OBJECTION_REPEAT = "objection.repeat"
    OBJECTION_REPEAT_PRICE = "objection.repeat.price"
    OBJECTION_ESCALATE = "objection.escalate"

    # === Momentum (Level 2) ===
    MOMENTUM_POSITIVE = "momentum.positive"
    MOMENTUM_NEGATIVE = "momentum.negative"
    MOMENTUM_NEUTRAL = "momentum.neutral"

    # === Engagement (Level 2) ===
    ENGAGEMENT_HIGH = "engagement.high"
    ENGAGEMENT_LOW = "engagement.low"
    ENGAGEMENT_DECLINING = "engagement.declining"

    # === Breakthrough (Level 3) ===
    BREAKTHROUGH_DETECTED = "breakthrough.detected"
    BREAKTHROUGH_WINDOW = "breakthrough.window"
    BREAKTHROUGH_CTA = "breakthrough.cta"

    # === Policy Overlays ===
    POLICY_REPAIR_MODE = "policy.repair_mode"
    POLICY_CONSERVATIVE = "policy.conservative"
    POLICY_ACCELERATE = "policy.accelerate"

    # === Guard/Fallback ===
    GUARD_INTERVENTION = "guard.intervention"
    GUARD_FRUSTRATION = "guard.frustration"
```

#### ContextEnvelopeBuilder

Builder для создания ContextEnvelope:

```python
builder = ContextEnvelopeBuilder(
    state_machine=sm,
    context_window=cw,
    tone_info={"tone": "neutral", "frustration_level": 2},
    guard_info={"intervention": None},
    last_action="ask_situation",
    last_intent="situation_provided",
    use_v2_engagement=True,  # Использовать улучшенный расчёт engagement
    current_intent="situation_provided",
    classification_result={
        "intent": "situation_provided",
        "extracted_data": {"company_size": 10},
        "secondary_signals": ["time_sensitive"]
    }
)

envelope = builder.build()
```

#### Пример использования ContextEnvelope

```python
from context_envelope import build_context_envelope, ReasonCode

# В обработчике сообщения
def process_message(message: str):
    # 1. Классификация
    classification = classifier.classify(
        message,
        context=sm.get_context()
    )

    # 2. Обновить StateMachine
    sm.update_data(classification.get("extracted_data", {}))

    # 3. Построить полный контекст
    envelope = build_context_envelope(
        state_machine=sm,
        context_window=context_window,
        tone_info=tone_analyzer.analyze(message),
        guard_info=conversation_guard.check(),
        last_action=sm.last_action,
        last_intent=sm.last_intent,
        current_intent=classification["intent"],
        classification_result=classification
    )

    # 4. Использовать контекст для разных компонентов
    # For repairs
    if envelope.is_stuck:
        envelope.add_reason(ReasonCode.POLICY_REPAIR_MODE)

    # For policy
    policy_context = envelope.for_policy()
    if envelope.momentum_direction == "positive" and envelope.is_progressing:
        policy_context["overlay"] = "accelerate"

    # For response generation
    generator_context = envelope.for_generator()
    response = generator.generate(
        action=action,
        context=generator_context
    )

    return response
```

---

### CascadeRetriever

3-этапный поиск по базе знаний.

```python
from src.knowledge import get_retriever, CascadeRetriever

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
from src.knowledge.category_router import CategoryRouter
from src.llm import OllamaClient

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

### ExtractionValidator

Валидирует и нормализует извлечённые LLM данные для предотвращения галлюцинаций.

Решает проблемы типа:
- "два-три человека" извлечено в `current_tools` вместо `company_size`
- "теряем клиентов" извлечено в `contact_info` вместо `pain_point`
- Случайный текст в `contact_info`

```python
from classifier.extractors.extraction_validator import (
    ExtractionValidator,
    validate_extracted_data,
    validate_field
)

validator = ExtractionValidator()

# Валидировать все извлечённые данные
result = validator.validate_extracted_data(
    extracted_data={
        "company_size": 10,
        "current_tools": "нас 5 человек",  # ОШИБКА: люди, не инструмент
        "contact_info": "теряем клиентов",  # ОШИБКА: боль, не контакт
        "pain_point": "проблемы с контролем"
    },
    context={"spin_phase": "situation"}
)

# Возвращает:
{
    "is_valid": False,
    "original_data": {...},
    "validated_data": {
        "company_size": 10,
        "pain_point": "проблемы с контролем"
        # current_tools и contact_info удалены
    },
    "removed_fields": ["current_tools", "contact_info"],
    "corrected_fields": {
        "current_tools": "company_size",
        "contact_info": "pain_point"
    },
    "errors": [
        "current_tools: This is a people count, not a tool",
        "contact_info: This is a pain point, not a contact"
    ],
    "warnings": [
        "'current_tools' value 'нас 5 человек' should be in 'company_size'",
        "'contact_info' value 'теряем клиентов' should be in 'pain_point'"
    ]
}
```

#### Методы ExtractionValidator

##### `validate_extracted_data(extracted_data: Dict, context: Optional[Dict] = None) -> ExtractionValidationResult`

Валидировать всю словарь извлечённых данных.

Удаляет невалидные поля и предлагает коррекции.

**Параметры:**
- `extracted_data`: Словарь от LLM extraction
- `context`: Опциональный контекст (spin_phase и т.д.)

**Возвращает:**
- `ExtractionValidationResult` с валидированными данными

##### `validate_field(field_name: str, value: Any, context: Optional[Dict] = None) -> FieldValidationResult`

Валидировать одно поле.

```python
# Проверить размер компании
result = validator.validate_field("company_size", "10")
if result.is_valid:
    print(f"Валидное значение: {result.normalized_value}")
else:
    print(f"Ошибка: {result.error}")

# Проверить контакт
result = validator.validate_field("contact_info", "+7 999 123-45-67")
print(f"Нормализовано: {result.normalized_value}")  # +7 999 123 45 67

# Проверить инструмент (может быть лично)
result = validator.validate_field("current_tools", "нас 5 человек")
if not result.is_valid:
    print(f"Предлагаемое поле: {result.suggested_field}")  # company_size
```

**Параметры:**
- `field_name`: Имя поля для валидации
- `value`: Значение для проверки
- `context`: Опциональный контекст

**Возвращает:**
- `FieldValidationResult` с результатом

#### Поддерживаемые поля

| Поле | Валидация | Примеры |
|------|-----------|---------|
| `company_size` | 1-10000 целое число | `"10"` → 10, `"нас 5 человек"` ✗ |
| `current_tools` | Известный инструмент CRM | `"Excel"`, `"1С"`, `"AmoCRM"` |
| `business_type` | Известный тип бизнеса | `"розничная торговля"`, `"IT"` |
| `contact_info` | Телефон или email | `"+7 999 123-45-67"`, `"test@example.com"` |
| `pain_point` | Строка >= 3 символов | `"теряем клиентов"` |
| `pain_category` | losing_clients, no_control, manual_work | `"losing_clients"` |
| `desired_outcome` | Строка >= 5 символов | `"автоматизировать процесс"` |

#### Примеры использования

```python
from classifier.extractors.extraction_validator import (
    validate_extracted_data,
    validate_field,
    is_valid_contact_info,
    is_valid_tool
)

# Вариант 1: Использовать глобальные функции
extracted = {
    "company_size": 10,
    "current_tools": "Excel",
    "contact_info": "+7 999 123-45-67"
}

result = validate_extracted_data(extracted)
if result.is_valid:
    validated_data = result.validated_data
    # использовать validated_data...

# Вариант 2: Быстрые проверки
if is_valid_contact_info("+7 999 123-45-67"):
    print("Валидный контакт")

if is_valid_tool("Excel"):
    print("Валидный инструмент")

# Вариант 3: Валидировать одно поле
company_result = validate_field("company_size", "пять человек")
if not company_result.is_valid:
    print(f"Ошибка: {company_result.error}")
```

---

### IntentCoverageValidator

Статическая валидация для обеспечения нулевого количества несоответствующих интентов.

Гарантирует, что:
1. Все критичные интенты имеют явные отображения
2. Все интенты из constants.yaml имеют taxonomies entries
3. Price-интенты используют `answer_with_pricing`
4. Определены category и domain defaults

```python
from validation import IntentCoverageValidator
from config_loader import ConfigLoader

loader = ConfigLoader()
config = loader.load()
flow = loader.load_flow("spin_selling")

validator = IntentCoverageValidator(config, flow)
issues = validator.validate_all()

# Проверить критичные проблемы
critical_issues = [i for i in issues if i.severity == "critical"]
if critical_issues:
    for issue in critical_issues:
        print(f"КРИТИЧНО: {issue.intent} - {issue.message}")
    raise RuntimeError("Обнаружены критичные проблемы покрытия интентов")

print(f"Валидация прошла успешно: {len(issues)} проблем найдено")
```

#### Методы IntentCoverageValidator

##### `validate_all() -> List[CoverageIssue]`

Запустить все проверки валидации.

```python
validator = IntentCoverageValidator(config, flow)
issues = validator.validate_all()

# Сортировать по severity
critical = [i for i in issues if i.severity == "critical"]
high = [i for i in issues if i.severity == "high"]
medium = [i for i in issues if i.severity == "medium"]

print(f"Критичные: {len(critical)}")
print(f"Высокие: {len(high)}")
print(f"Средние: {len(medium)}")
```

**Возвращает:**
- List[CoverageIssue] - все найденные проблемы

##### `validate_taxonomy_completeness() -> List[CoverageIssue]`

Валидировать что все интенты имеют taxonomy entries.

##### `validate_critical_intent_mappings() -> List[CoverageIssue]`

Валидировать что критичные интенты имеют явные отображения в `_universal_base`.

Критичные интенты (81% отказов без явного отображения):
- price_question, pricing_details, cost_inquiry, discount_request
- contact_provided, demo_request, callback_request
- rejection, farewell, request_human

##### `validate_price_intent_actions() -> List[CoverageIssue]`

Валидировать что price-интенты используют `answer_with_pricing` (не `answer_with_facts`).

##### `validate_category_defaults() -> List[CoverageIssue]`

Валидировать что все категории имеют fallback defaults.

##### `validate_template_existence() -> List[CoverageIssue]`

Валидировать что все referenced actions имеют шаблоны.

#### CoverageIssue (структура проблемы)

```python
@dataclass
class CoverageIssue:
    severity: str                # "critical", "high", "medium", "low"
    intent: Optional[str]        # Intent с проблемой (если применимо)
    issue_type: str              # Тип проблемы
    message: str                 # Описание для человека
    location: str                # Где найдена (файл/микс/состояние)

# Возможные типы проблем:
# - unmapped_critical: критичный интент без отображения
# - missing_taxonomy: интент без taxonomy entry
# - wrong_action: неверное действие для интента
# - missing_category_default: категория без fallback
# - missing_template: действие без шаблона
# - uncovered_fact_intent: fact-интент без паттерна
```

#### Функция удобства

```python
from validation import validate_intent_coverage

result = validate_intent_coverage(config, flow)

if result["is_valid"]:
    print("Покрытие интентов валидно!")
else:
    print(f"Найдено {result['summary']['critical']} критичных проблем")
    for issue in result["issues"]:
        print(f"  - {issue.intent}: {issue.message}")
```

---

### FeatureFlags

Управление feature flags.

```python
from src.feature_flags import flags

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
from src.settings import settings

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
from src.classifier.llm import ClassificationResult, ExtractedData

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
from src.classifier.llm import CategoryResult

class CategoryResult(BaseModel):
    categories: List[CategoryType]  # 17 категорий
```

---

## Примеры использования

### Базовый диалог

```python
from src.bot import SalesBot
from src.llm import OllamaClient

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
from src.classifier import UnifiedClassifier

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
from src.knowledge import get_retriever

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
from src.llm import OllamaClient

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
from src.feature_flags import flags

if flags.llm_classifier:
    from src.classifier import UnifiedClassifier
    classifier = UnifiedClassifier()  # использует LLM
else:
    from src.classifier import HybridClassifier
    classifier = HybridClassifier()  # использует regex

if flags.is_enabled("tone_analysis"):
    from tone_analyzer import ToneAnalyzer
    analyzer = ToneAnalyzer()
    tone = analyzer.analyze(message)
```

### Интерактивный режим

```python
from src.bot import SalesBot, run_interactive
from src.llm import OllamaClient
from src.feature_flags import flags

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
